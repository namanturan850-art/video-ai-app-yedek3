"""Version-scoped optional YouTube tools; suggestions never alter scripts silently."""
from contextlib import closing
import json
import time
import logging
from uuid import uuid4

from app.projects import now
from app.scripts.engine import YouTubeScriptEngine, SecretGuard, translation_chunks, assert_original
from app.scripts.models import ScriptError
from app.scripts.storage import dumps
from app.providers.base import ScriptProviderError
from app.production import (SCENE_ERRORS, SCENE_FIELDS, SCENE_METADATA_ERRORS, scene_error, scene_references,
                            narration_units, exact_source_slices, visual_blocks)

KINDS = ('retention', 'hooks', 'alternatives', 'claims', 'visual')
RATINGS = ('Güçlü', 'Orta', 'Geliştirilebilir')
CRITERIA = ('opening_10_30_seconds', 'hook', 'slow_sections', 'repetition', 'transitions', 'overload', 'pacing', 'section_length', 'curiosity', 'payoff', 'ending')


class QualityService:
    def __init__(self, scripts):
        self.scripts, self.projects = scripts, scripts.projects
        self.repo = scripts.repository

    def results(self, project_id):
        self.projects.get(project_id)
        with closing(self.projects._connection()) as connection:
            return [{key: row[key] for key in ('id', 'version_id', 'kind', 'language', 'created_at')} | {'result': json.loads(row['result_json'])} for row in connection.execute('SELECT * FROM script_artifacts WHERE project_id=? ORDER BY created_at DESC', (project_id,))]

    def resume(self, project_id, job_id, confirmed, *, visual_repair_cost_confirmed=False):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            self.repo._idle(connection, project_id)
            job = self.repo.job(job_id)
            if job['project_id'] != project_id or job['status'] != 'error':
                raise ScriptError('Bu işlem sürdürülemez.', 409)
            if json.loads(job['progress_json']).get('retry_not_before', 0) > time.time():
                raise ScriptError('Sağlayıcının istek sınırı nedeniyle bir süre bekleyip Devam Et deyin.', 429)
            current = self.repo.view(project_id)['current']
            if not current or current['id'] not in (json.loads(job['input_json'])['version_id'], json.loads(job['progress_json']).get('version_id')):
                raise ScriptError('Senaryo sürümü değişti. Bu sürüm için yeniden analiz edin.', 409)
            if job['action'] in ('visual','visual_scene'):
                self.production.require_approved(project_id)
                if json.loads(job['options_json'])['language']!=self.projects.get(project_id)['language']:
                    raise ScriptError('Proje dili değişti. Yeni dil için plan hazırlayın.',409)
                with closing(self.projects._connection()) as reader:
                    committed=reader.execute('SELECT 1 FROM scene_plan_versions WHERE origin_job_id=?',(job_id,)).fetchone()
                if not committed: self.production.check_snapshot(project_id,json.loads(job['input_json']).get('plan_snapshot'))
                progress=json.loads(job['progress_json'])
                repair=progress.get('visual_repair',{})
                if repair.get('status')=='awaiting_cost_confirmation' and not repair.get('attempted'):
                    if not visual_repair_cost_confirmed:
                        raise ScriptError('Tek görsel düzeltme ek API kotası veya ücret kullanabilir. Devam etmeden önce maliyet onayı verin.',409)
                    repair['status']='confirmed'
                    connection.execute('UPDATE script_jobs SET progress_json=? WHERE id=?',(dumps(progress),job_id))
            if job['action'] == 'apply': self.repo.protect(connection, project_id, confirmed)
            provider, model, guard = self.scripts._provider(job['provider'])
            if model != job['model']: raise ScriptError('Aynı modeli seçip yeniden deneyin.', 409)
            connection.execute("UPDATE script_jobs SET status='queued',error_message='' WHERE id=?", (job_id,))
        self.scripts.futures[job_id] = self.scripts.executor.submit(self._run, job_id, provider, guard)
        return {'job_id': job_id}

    def start(self, project_id, kind, payload):
        expected = {'provider', 'cost_confirmed', 'confirm_replace_plan'} if kind == 'visual' else {'provider', 'cost_confirmed'}
        if kind not in KINDS or set(payload) != expected or type(payload['cost_confirmed']) is not bool or kind == 'visual' and type(payload['confirm_replace_plan']) is not bool:
            raise ScriptError('Geçerli bir analiz aracı ve sağlayıcı seçin.')
        return self._enqueue(project_id, kind, payload)

    def start_scene(self, project_id, scene_id, payload):
        if set(payload)!={'provider','cost_confirmed','plan_id','revision'} or type(payload['cost_confirmed']) is not bool:
            raise ScriptError('Sahne sağlayıcısını ve maliyet onayını kontrol edin.')
        return self._enqueue(project_id,'visual_scene',{**payload,'scene_id':scene_id})

    def apply(self, project_id, artifact_id, payload):
        if set(payload) != {'selection', 'confirm_replace_approved', 'cost_confirmed'} or not isinstance(payload['selection'], list) or not payload['selection'] or any(type(x) is not int for x in payload['selection']) or len(set(payload['selection'])) != len(payload['selection']) or type(payload['confirm_replace_approved']) is not bool or type(payload['cost_confirmed']) is not bool:
            raise ScriptError('Uygulanacak önerileri seçin ve onay tercihini belirtin.')
        with closing(self.projects._connection()) as connection:
            row = connection.execute('SELECT * FROM script_artifacts WHERE id=? AND project_id=?', (artifact_id, project_id)).fetchone()
        current = self.repo.view(project_id)['current']
        if not row or not current or row['version_id'] != current['id']:
            raise ScriptError('Öneri geçerli senaryo sürümüne ait değil. Bu sürüm için yeniden analiz edin.', 409)
        result = json.loads(row['result_json'])
        if row['kind'] == 'retention':
            items = result['suggestions']
        elif row['kind'] == 'hooks':
            items = [{'scope': 'opening', 'replacement': text} for text in result['hooks']]
            if len(payload['selection']) != 1:
                raise ScriptError('Tek bir açılış seçin.')
        else:
            raise ScriptError('Bu sonuç yalnızca görüntüleme/seçim içindir; senaryo metnini otomatik değiştirmez.')
        if any(not 0 <= index < len(items) for index in payload['selection']):
            raise ScriptError('Geçerli bir öneri seçin.')
        return self._enqueue(project_id, 'apply', {'provider': current['provider'], **payload}, selected=[items[index] for index in payload['selection']])

    def choose(self, project_id, artifact_id, payload):
        if set(payload) != {'choices'} or not isinstance(payload['choices'], dict):
            raise ScriptError('Alternatif seçimlerini kontrol edin.')
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            self.repo._idle(connection, project_id)
            row = connection.execute('SELECT * FROM script_artifacts WHERE project_id=? AND id=?', (project_id, artifact_id)).fetchone()
            if not row or row['kind'] != 'alternatives': raise ScriptError('Alternatifler bulunamadı.', 404)
            result = json.loads(row['result_json'])
            for key, index in payload['choices'].items():
                if key not in ('opening', 'title', 'thumbnail_text', 'intro', 'CTA', 'description') or type(index) is not int or not 0 <= index < len(result[key]):
                    raise ScriptError('Geçerli alternatifleri seçin.')
            result['selected'] = {**result.get('selected', {}), **payload['choices']}
            connection.execute('UPDATE script_artifacts SET result_json=? WHERE id=?', (dumps(result), artifact_id))
        self.repo._file(project_id, 'tool_' + artifact_id + '.json', dumps(result))
        return {'message': 'Seçimler kaydedildi. Senaryo metni değişmedi.'}

    def _enqueue(self, project_id, kind, payload, selected=None):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            self.repo._idle(connection, project_id)
            current = self.repo._public_version(self.repo._current(connection, project_id), full=True)
            if kind in ('visual','visual_scene'): current=self.production.require_approved(project_id)
            if not current:
                raise ScriptError('Önce senaryo oluşturun.')
            if kind == 'visual':
                if self.production.view(project_id)['plan'] and not payload['confirm_replace_plan']:
                    raise ScriptError('Mevcut görsel planı değiştirmek için açık onay gerekli.', 409)
            if kind == 'apply':
                self.repo.protect(connection, project_id, payload['confirm_replace_approved'])
            provider, model, guard = self.scripts._provider(payload['provider'])
            if payload['provider'] != 'ollama' and not payload['cost_confirmed']:
                raise ScriptError('Bu AI işlemi API kotası veya ücret kullanabilir. İşlemi başlatmadan önce onay verin.', 409)
            inputs = {'version_id': current['id'], 'text': current['text'], 'content_type': current['content_type'], 'selected': selected, 'confirm_replace_plan': payload.get('confirm_replace_plan', False)}
            saved_options=dict(current['options'])
            if kind in ('visual','visual_scene'):
                saved_options['language']=self.projects.get(project_id)['language']
                inputs['plan_snapshot']=self.production.snapshot(project_id)
                if kind=='visual': inputs['planning_segments']=self.production.planning_segments(project_id,current)
                else:
                    plan,_=self.production.editable_plan(project_id,payload)
                    block=self.production._scene(plan,payload['scene_id'])
                    if block['locked']: raise ScriptError('Önce sahnenin kilidini açın.',409)
                    inputs.update(base_plan=plan,scene_id=block['id'],text=block['narration'])
                    rate=(saved_options['words_per_minute_min']+saved_options['words_per_minute_max'])/2
                    inputs['planning_segments']=[{'text':block['narration'],'narration_units':narration_units(block['narration'],rate)}]
            guard.validate(inputs)
            job_id, stamp = uuid4().hex, now()
            progress = {'phase': kind, 'percent': 0, 'sections': [], 'version_id': None}
            connection.execute('INSERT INTO script_jobs (id,project_id,provider,model,action,status,options_json,input_json,progress_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (job_id, project_id, payload['provider'], model, kind, 'queued', dumps(saved_options), dumps(inputs), dumps(progress), stamp, stamp))
        self.scripts.futures[job_id] = self.scripts.executor.submit(self._run, job_id, provider, guard)
        return {'job_id': job_id, 'message': 'İşlem başladı. Önceki senaryo korunuyor.'}

    def _run(self, job_id, provider, guard):
        started, category = time.monotonic(), 'success'
        failed_field=None
        job = self.repo.job(job_id)
        inputs, options, progress = (json.loads(job[key]) for key in ('input_json', 'options_json', 'progress_json'))
        engine = YouTubeScriptEngine(provider, guard)
        kind = job['action']
        visual = kind in ('visual','visual_scene')
        def save_visual(blocks):
            if kind=='visual_scene':
                return self.production.save_scene_generated(job['project_id'],inputs,blocks[0],job['provider'],job['model'],job_id)
            return self.production.save_generated(job['project_id'],inputs['version_id'],options['language'],blocks,inputs['confirm_replace_plan'],
                    provider=job['provider'],model=job['model'],job_id=job_id,snapshot=inputs.get('plan_snapshot'))
        def checkpoint(status):
            if self.scripts.stopping.is_set(): raise ScriptError('Uygulama kapatıldığı için işlem durdu; tamamlanan parçalar korundu.')
            self.repo.checkpoint(job_id, status, guard.clean(progress))
        try:
            if progress.get('version_id') or progress.get('artifact_id'):
                if visual and progress.get('artifact_id'):
                    save_visual([block for part in progress['parts'] for block in part])
                progress.update(phase='done', percent=100)
                checkpoint('draft')
                return
            checkpoint('analyzing')
            segments=inputs.get('planning_segments',[{'text':inputs['text']}]) if visual else None
            if visual and any('narration_units' not in segment and not segment.get('locked_block') for segment in segments):
                # Resume pre-fix jobs from their original source, not normalized AI copies.
                exact=exact_source_slices([segment['text'] for segment in segments],inputs['text'])
                rate=(options['words_per_minute_min']+options['words_per_minute_max'])/2
                for index,(segment,text) in enumerate(zip(segments,exact)):
                    if not segment.get('locked_block'):
                        segment.update(text=text,narration_units=narration_units(text,rate,prefix=f'S{index+1}U'))
                inputs['planning_segments']=segments
                with self.projects.lock, closing(self.projects._connection()) as connection,connection:
                    connection.execute('UPDATE script_jobs SET input_json=? WHERE id=?',(dumps(guard.clean(inputs)),job_id))
            chunks = [segment['text'] for segment in segments] if visual else translation_chunks(inputs['text'], 600)
            if kind == 'apply':
                texts = [section['text'] for section in progress['sections']]
                for index, text in enumerate(chunks):
                    if index < len(texts): continue
                    texts.append(engine.ask('apply_suggestions', {'language': options['language'], 'selected_suggestions': inputs['selected'], 'segment': text, 'index': index, 'segment_count': len(chunks)},
                        'Apply ONLY selected suggestions relevant to this segment, leave unrelated wording/claims intact. '
                        'Opening replacement applies ONLY to segment index zero. No new claims, no false promises, '
                        'no extra ending for intermediate segments. Return the complete revised segment narration only.'))
                    progress['sections'].append({'title': f'Bölüm {index+1}', 'text': texts[-1], 'context': ''})
                    progress['percent'] = round((index+1)/len(chunks)*90)
                    checkpoint('generating')
                current = self.repo.view(job['project_id'])['current']
                assert_original('\n\n'.join(texts), options)
                self.repo.create_version(job['project_id'], '\n\n'.join(texts), job['provider'], job['model'], {**options, 'provider': job['provider']}, current['content_type'],
                    {'consistent': False, 'issues': ['Seçilen önerilerle yeni taslak oluşturuldu. Önceki sürüm korunur; onaylamadan önce inceleyin.']}, generated=True, job_id=job_id, progress=progress)
            else:
                parts = progress.setdefault('parts', [])
                for index, text in enumerate(chunks[:1] if kind in ('hooks', 'alternatives') else chunks):
                    if index < len(parts): continue
                    if visual and segments[index].get('locked_block'):
                        parts.append([segments[index]['locked_block']]);progress['percent']=round((index+1)/len(chunks)*90);checkpoint('analyzing');continue
                    data={'language': options['language'], 'text': text, 'is_video_opening': index == 0, 'is_video_ending': index == len(chunks)-1, 'content_outline': [chunk[:250] for chunk in (chunks[:79] + chunks[-1:])] if kind in ('hooks', 'alternatives') else [], 'segment_index': index, 'segment_count': len(chunks), 'content_type': inputs['content_type']}
                    if visual:
                        data.pop('text')
                        data['narration_units']=segments[index]['narration_units']
                        data.update(scene_mode='single' if kind=='visual_scene' else 'semantic',topic=self.projects.get(job['project_id'])['topic'],
                                    speech_rate_min=options['words_per_minute_min'],speech_rate_max=options['words_per_minute_max'])
                        prior=[block for part in parts for block in part][-3:]
                        data['previous_visuals']=[{key:b.get(key) for key in ('visual_intent','composition','media_type','entities','location','stock_query')} for b in prior]
                    if visual:
                        start = parts[-1][-1]['end'] if parts else 0
                        parts.append(self._visual_part(engine,data,text,options,start,job,progress,checkpoint,kind=='visual_scene'))
                    else:
                        raw = engine.structured(kind,data,self._instructions(kind))
                        parts.append(self._validate(kind, raw, options['language']))
                    progress['percent'] = round((index+1)/len(chunks)*90)
                    checkpoint('analyzing')
                    if kind in ('hooks', 'alternatives'):
                        break  # Opening plus truthful subject; never an enormous prompt.
                result = {'blocks': [block for part in parts for block in part]} if visual else self._merge(kind, parts)
                artifact_id = uuid4().hex
                with self.projects.lock, closing(self.projects._connection()) as connection, connection:
                    connection.execute('INSERT INTO script_artifacts VALUES (?,?,?,?,?,?,?)', (artifact_id, job['project_id'], inputs['version_id'], kind, options['language'], dumps(guard.clean(result)), now()))
                    progress['artifact_id'] = artifact_id
                    connection.execute('UPDATE script_jobs SET progress_json=? WHERE id=?', (dumps(progress), job_id))
                self.repo._file(job['project_id'], 'tool_' + artifact_id + '.json', dumps(result))
                if visual: save_visual(result['blocks'])
            progress.pop('error_category',None)
            progress.pop('error_field',None)
            progress.pop('error_diagnostic',None)
            progress.update(phase='done', percent=100)
            checkpoint('draft')
        except Exception as error:
            allowed_categories=set(SCENE_ERRORS)|{'quota_limit','free_quota_exhausted','rate_limit','billing_quota','key_rejected','no_internet','local_connection','network_error','generation_timeout','gemini_timeout','model_unavailable','invalid_response','invalid_json','thinking_unsupported','empty_response','upstream_error'}
            category = error.category if isinstance(error,(ScriptProviderError,ScriptError)) and error.category in allowed_categories else 'tool_error'
            field=getattr(error,'field',None)
            failed_field=field if isinstance(field,str) and field in SCENE_FIELDS else None
            diagnostic=f'{category}:{failed_field}' if failed_field else category
            allowed = {'quota_limit': 'Kullanım sınırına ulaşıldı.', 'free_quota_exhausted': 'Gemini ücretsiz API kotasını kontrol edin.', 'rate_limit': 'İstek hız sınırına ulaşıldı.', 'billing_quota': 'API bakiye/kota sınırını kontrol edin.', 'no_internet': 'Sağlayıcı bağlantısı kurulamadı.', 'local_connection': 'Yerel Ollama sunucusuna ulaşılamadı.', 'network_error': 'API HTTP bağlantısı tamamlanamadı.', 'thinking_unsupported': 'Bu Ollama modeli mevcut ayarlarla reasoning modunu kapatamıyor.', 'invalid_json': 'Sağlayıcı tek ve geçerli JSON döndürmedi.', 'empty_response': 'Sağlayıcı boş son yanıt döndürdü.'}
            message = str(error) if isinstance(error, ScriptError) else allowed.get(category, 'AI aracı tamamlanamadı. Tekrar deneyin.')
            with self.projects.lock, closing(self.projects._connection()) as connection, connection:
                saved = json.loads(connection.execute('SELECT progress_json FROM script_jobs WHERE id=?', (job_id,)).fetchone()['progress_json'])
                if saved.get('visual_repair',{}).get('status')=='running':
                    saved['visual_repair'].update(status='failed',error_category=category,error_field=failed_field)
                saved.update(error_category=category,error_field=failed_field,error_diagnostic=diagnostic,
                             retry_not_before=time.time() + (error.retry_after if isinstance(error, ScriptProviderError) else 0))
                connection.execute("UPDATE script_jobs SET status='error',error_message=?,progress_json=?,updated_at=? WHERE id=?", (guard.clean(message) + ' Önceki sürüm ve tamamlanan parçalar korundu.', dumps(saved), now(), job_id))
        finally:
            logging.getLogger('uvicorn.error.providers').info('provider=%s operation=%s category=%s field=%s elapsed_ms=%.0f', job['provider'], kind, category, failed_field or 'none', (time.monotonic() - started) * 1000)

    def _visual_part(self, engine, data, source, options, start, job, progress, checkpoint, single):
        """One job-wide repair budget; persist consent/attempt before any extra call."""
        units=data['narration_units'];index=data['segment_index']
        instructions=self._instructions('visual').replace('"first supplied unit_id"',json.dumps(units[0]['unit_id']))
        instructions+=' Use the actual IDs in narration_units; the example shows the response shape, not the complete scene plan.'
        if single: instructions+=' Return EXACTLY ONE scene containing all supplied unit IDs.'
        def ask(payload, *, repair=False):
            prompt=instructions
            if repair:
                prompt='Correct only scene metadata for required_unit_groups. Do not change groups or narration. '+self._visual_example(units[0]['unit_id'])+' Return JSON only. Do not explain.'
            try: return engine.structured('visual',payload,prompt)
            except (ScriptError,ScriptProviderError) as error:
                if error.category in ('invalid_json','schema_invalid'): raise scene_error('invalid_scene_schema','json') from None
                raise
        def reconstruct(raw):
            return visual_blocks(raw,source,options['language'],(options['words_per_minute_min']+options['words_per_minute_max'])/2,start,units=units,single=single)
        repair=progress.get('visual_repair')
        if not repair or repair['segment_index']!=index:
            raw=ask(data)
            try: return reconstruct(raw)
            except ScriptError as error:
                if error.category not in SCENE_METADATA_ERRORS or repair and repair.get('attempted'): raise
                # Missing/duplicate/reordered references are never repaired automatically.
                groups=scene_references(raw,units)
                if single: groups=[[uid for group in groups for uid in group]]
                repair={'segment_index':index,'unit_groups':groups,'error_category':error.category,'error_field':getattr(error,'field',None),
                        'attempted':False,'status':'ready' if job['provider']=='ollama' else 'awaiting_cost_confirmation'}
                progress['visual_repair']=repair;checkpoint('analyzing')
        if repair.get('attempted'):
            error=scene_error(repair['error_category'],repair.get('error_field')) if repair['error_category'] in SCENE_ERRORS else ScriptError('Tek görsel düzeltme tamamlanamadı.',category=repair['error_category'])
            error.args=(str(error)+' Tek görsel düzeltme denemesi kullanıldı; isterseniz yeni plan işlemi başlatın.',)
            raise error
        if job['provider']!='ollama' and repair['status']!='confirmed':
            error=scene_error(repair['error_category'],repair.get('error_field'))
            error.args=(str(error)+' Tek düzeltme ek API kotası veya ücret kullanabilir; Plan İşlemine Devam Et ile onay verin.',)
            raise error
        repair.update(attempted=True,status='running');checkpoint('analyzing')
        raw=ask({'language':data['language'],'scene_mode':data['scene_mode'],'narration_units':units,
                 'metadata_repair':{'safe_error_category':repair['error_category'],'failed_field':repair.get('error_field'),
                                    'required_unit_groups':repair['unit_groups']}},repair=True)
        if scene_references(raw,units)!=repair['unit_groups']: raise scene_error('invalid_scene_schema','unit_ids')
        blocks=reconstruct(raw)
        repair['status']='succeeded'
        return blocks

    @staticmethod
    def _visual_example(unit_id):
        return 'Shape example; use actual source subjects and IDs: '+json.dumps({'scenes':[{
            'unit_ids':[unit_id],'purpose':'Show context','mood':'neutral','visual_intent':'Show the narrated subject in context',
            'stock_query':'subject relevant environment','alternative_stock_queries':['subject relevant action'],'media_type':'stock_video'}]})

    @staticmethod
    def _instructions(kind):
        if kind=='visual':
            return ('Group narration_units by meaning, topic changes, important facts, examples, comparisons, lists, emotional beats and section transitions. '
                    'Use every unit_id exactly once, in source order and contiguous groups. NEVER narration or narration_text; the application owns exact text. '
                    'Adapt to content_type; never turn factual topics into stories. Opening 3–7 / main 5–12 second beats are guidance ONLY, not fixed lengths. '
                    'Use relevant ENGLISH primary stock queries and 1–5 DIFFERENT alternatives, each 2–12 words. Prefer stock_video; other types: stock_image, ai_image, motion_graphic, user_media. '
                    'Use previous_visuals to avoid unrelated repetition. No invented facts or claims of existing media. '
                    'Only the seven example fields are required. Optional: overlay_text (project language, max 12 words), entities, location, action, shot_suggestion. Omit uncertain optional fields. '
                    +QualityService._visual_example('first supplied unit_id')+' Return JSON only. Do not explain.')
        common = 'Use the selected target language for generated narration/titles/CTA; explanations to the user in Turkish. No invented facts, false promises or verification claims. '
        return common + {
            'retention': 'Evaluate opening 10–30 seconds, hook, slow sections, repetition, transitions, overload, pacing, section length, curiosity, payoff and ending. Return JSON {"ratings":{"opening_10_30_seconds":"Orta","hook":"Orta","slow_sections":"Orta","repetition":"Orta","transitions":"Orta","overload":"Orta","pacing":"Orta","section_length":"Orta","curiosity":"Orta","payoff":"Orta","ending":"Orta"},"suggestions":[{"scope":"opening or specific segment","suggestion":"Turkish actionable suggestion"}]}. Ratings only Güçlü, Orta, Geliştirilebilir.',
            'hooks': 'Create EXACTLY three distinct optional opening hooks in the target language based on actual subject/content. Do not promise unseen content. Return JSON {"hooks":["...","...","..."]}.',
            'alternatives': 'Create 2–3 truthful options EACH for opening, title, thumbnail_text, intro, CTA and description in the target language. No automatic selection. Return JSON with those six keys, each a string array.',
            'claims': 'Identify dates/statistics/prices/health/scientific/history/financial/specification/named-event claims requiring verification. Do not claim verified. Return JSON {"claims":[{"statement":"exact relevant statement","reason":"Turkish reason"}]}. Empty list if none.'}[kind]

    @staticmethod
    def _validate(kind, result, language):
        def strings(values, minimum, maximum):
            return isinstance(values, list) and minimum <= len(values) <= maximum and all(isinstance(x, str) and x.strip() and len(x) <= 3000 for x in values)
        valid = False
        if kind == 'retention':
            valid = isinstance(result.get('ratings'), dict) and set(result['ratings']) == set(CRITERIA) and all(value in RATINGS for value in result['ratings'].values()) and isinstance(result.get('suggestions'), list) and len(result['suggestions']) <= 20 and all(isinstance(item, dict) and set(item) == {'scope', 'suggestion'} and all(isinstance(x, str) and 0 < len(x) <= 3000 for x in item.values()) for item in result['suggestions'])
        elif kind == 'hooks': valid = strings(result.get('hooks'), 3, 3)
        elif kind == 'alternatives': valid = all(strings(result.get(key), 2, 3) for key in ('opening', 'title', 'thumbnail_text', 'intro', 'CTA', 'description'))
        elif kind == 'claims': valid = isinstance(result.get('claims'), list) and len(result['claims']) <= 100 and all(isinstance(item, dict) and set(item) == {'statement', 'reason'} and all(isinstance(value, str) and 0 < len(value) <= 3000 for value in item.values()) for item in result['claims'])
        if not valid:
            raise ScriptError('AI aracı beklenen biçimde sonuç döndürmedi. Tekrar deneyin.')
        if kind == 'claims':
            for claim in result['claims']:
                claim.update(status='Doğrulama gerektirebilir.', verified=False, sources=[])
        return {**result, 'language': language}

    @staticmethod
    def _merge(kind, parts):
        result = parts[0]
        if kind == 'claims': result['claims'] = [item for part in parts for item in part['claims']]
        if kind == 'retention':
            result['suggestions'] = [item for part in parts for item in part['suggestions']][:50]
            for criterion in CRITERIA:
                if criterion in ('opening_10_30_seconds', 'hook'):
                    result['ratings'][criterion] = parts[0]['ratings'][criterion]
                elif criterion in ('payoff', 'ending'):
                    result['ratings'][criterion] = parts[-1]['ratings'][criterion]
                else:
                    result['ratings'][criterion] = max((part['ratings'][criterion] for part in parts), key=RATINGS.index)
        return result
