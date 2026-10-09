from app.stock.identities import identity_keys, duplicate as media_duplicate
"""Checkpointed stock assignment over the active Part 5 handoff, project scoped."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import math
import time
from uuid import uuid4

from app.projects import now
from app.scripts.engine import SecretGuard
from app.scripts.models import ScriptError
from app.stock.download import Downloader, asset_path, mirror, archive_selection
from app.stock import relevance
from app.stock.models import (StockError, identity, make_slots, normalized_media, score,
                              DEFAULT_VIDEO_TOLERANCE, rejection_reason, coverage_warning)
from app.stock.diagnostics import REASONS, CATEGORIES, normalization_counts, safe_query, search_summary, log_search
from app.stock.providers import make_stock_provider

LOG = logging.getLogger('uvicorn.error.stock')
PLAN_REQUIRED = 'Önce güncel Görsel / Kurgu Planını hazırlayın.'
ACTIVE = ('queued','running')
STATUSES = {'pending':'Bekliyor','searching':'Aranıyor','candidates':'Adaylar hazır',
            'downloading':'İndiriliyor','complete':'Tamamlandı','error':'Hata',
            'ai_needed':'AI görsel gerekebilir'}


def fingerprint(handoff):
    return hashlib.sha256(json.dumps(handoff,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def scene_binding(scene):
    return (scene['narration_text'], scene['start_estimate'], scene['end_estimate'])


class StockService:
    def __init__(self, production, settings):
        self.production, self.settings = production, settings
        self.projects = production.projects
        self.factory = make_stock_provider
        self.downloader = Downloader(self.projects)
        self.executor = ThreadPoolExecutor(max_workers=2,thread_name_prefix='stock-media')
        self.futures = {}
        self.closed = False

    def close(self):
        self.closed = True
        self.executor.shutdown(wait=True, cancel_futures=True)

    def recover(self):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute("UPDATE stock_jobs SET status='error',error_message=?,updated_at=? WHERE status IN ('queued','running')",
                               ('İşlem uygulama kapanırken durdu. Tamamlanan dosyalar korundu; Devam Et deyin.',now()))

    def _handoff(self, project_id):
        self.projects.get(project_id)
        try: return self.production.handoff(project_id)
        except ScriptError: raise StockError('plan_required',PLAN_REQUIRED,409) from None

    def _guard(self, value):
        SecretGuard(self.settings.secret_values()).validate(value)

    def _load(self, connection, project_id, plan_id):
        row = connection.execute('SELECT state_json FROM stock_plans WHERE project_id=? AND plan_id=?',(project_id,plan_id)).fetchone()
        return json.loads(row[0]) if row else None

    def _save(self, connection, state):
        self._guard(state)
        state['revision'] += 1
        state['updated_at'] = now()
        connection.execute('INSERT INTO stock_plans VALUES (?,?,?,?,?) ON CONFLICT(project_id,plan_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at',
                           (state['project_id'],state['plan_id'],state['source_version_id'],json.dumps(state,ensure_ascii=False),state['updated_at']))

    def _mirror(self, state):
        # SQLite is authoritative. A mirror failure never invalidates downloads.
        try: mirror(self.projects,state['project_id'],state['plan_id'],state)
        except (OSError, StockError): LOG.warning('stock operation=mirror category=local_storage')

    def _ensure(self, connection, handoff):
        project_id, plan_id = handoff['project_id'],handoff['plan_id']
        saved = self._load(connection,project_id,plan_id)
        stamp = fingerprint(handoff)
        if saved and saved['handoff_fingerprint']==stamp: return saved
        row = connection.execute('SELECT state_json FROM stock_plans WHERE project_id=? ORDER BY updated_at DESC LIMIT 1',(project_id,)).fetchone()
        previous = saved or (json.loads(row[0]) if row else None)
        state = {'project_id':project_id,'plan_id':plan_id,'source_version_id':handoff['source_script_version_id'],
                 'handoff_fingerprint':stamp,'revision':saved['revision'] if saved else 0,
                 'slots':[],'bindings':{},'warnings':[],'updated_at':now()}
        old_scenes = {}
        old_locked = []
        if previous and previous['source_version_id']==state['source_version_id']:
            for sid,binding in previous['bindings'].items():
                old_scenes[tuple(binding)] = [s for s in previous['slots'] if s['scene_id']==sid]
            old_locked = [s for s in previous['slots'] if s['locked'] and s['selected_media']]
        for scene in handoff['scenes']:
            sid = scene['scene_id']
            binding = scene_binding(scene)
            state['bindings'][sid] = binding
            old = old_scenes.get(binding)
            if old:
                slots = deepcopy(old)
                for slot in slots:
                    slot['scene_id'] = sid
                    if not slot['locked']:
                        slot['visual_goal'] = scene['visual_intent']
                        queries = [scene['primary_stock_query'],*scene['alternative_stock_queries']]
                        query = queries[min(slot['order']-1,len(queries)-1)]
                        if query != slot['search_query']: slot['candidates'] = []
                        slot.update(search_query=query,fallback_queries=[q for q in queries if q!=query],
                                    preferred_type=scene['preferred_media_type'],composition=scene['composition'])
            else:
                # A refreshed semantic scene may have different boundaries. Preserve
                # each locked visual interval, splitting its assignment at a new
                # scene boundary only. Narration/scene models are never rewritten.
                anchors = []
                for locked in old_locked:
                    a = max(scene['start_estimate'],locked['estimated_start'])
                    b = min(scene['end_estimate'],locked['estimated_end'])
                    if b-a < .001: continue
                    anchor = deepcopy(locked)
                    anchor.update(scene_id=sid,estimated_start=round(a,3),estimated_end=round(b,3),duration=round(b-a,3))
                    if a > locked['estimated_start']+.001:
                        anchor['slot_id']=uuid4().hex
                        anchor['warnings'].append('Kilitli medya yeni sahne sınırında paylaşıldı. Sonraki aşamada kesme zamanını kontrol edin.')
                    anchors.append(anchor)
                slots=[];cursor=scene['start_estimate']
                for anchor in sorted(anchors,key=lambda s:s['estimated_start']):
                    if anchor['estimated_start']>cursor+.001:
                        slots.extend(make_slots({**scene,'start_estimate':cursor,'end_estimate':anchor['estimated_start']}))
                    slots.append(anchor);cursor=anchor['estimated_end']
                if scene['end_estimate']>cursor+.001:
                    slots.extend(make_slots({**scene,'start_estimate':cursor,'end_estimate':scene['end_estimate']}))
                for index,slot in enumerate(slots): slot['order']=index+1
            state['slots'].extend(slots)
        if previous and any(s['locked'] and s['slot_id'] not in {n['slot_id'] for n in state['slots']} for s in previous['slots']):
            state['warnings'].append('Sahne sınırları veya senaryo değişti. Eski kilitli medya önceki plan kaydında korundu; yeni sahneleri kontrol edin.')
        self._save(connection,state)
        self._mirror(state)
        return state

    def _job(self, row):
        if not row: return None
        value = dict(row);value['progress'] = json.loads(value.pop('progress_json'))
        return value

    def view(self, project_id):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            handoff = self._handoff(project_id)
            state = self._ensure(connection,handoff)
            public = deepcopy(state)
            for slot in public['slots']:
                repeated=media_duplicate(slot['selected_media'],[x['selected_media'] for x in public['slots'] if x['slot_id']!=slot['slot_id']])
                slot['repeat_status']='Manuel tekrar kullanım' if repeated and slot.get('manual_reuse') else 'Daha önce kullanılmış' if repeated else 'Benzersiz'
                scene=next(s for s in handoff['scenes'] if s['scene_id']==slot['scene_id'])
                current_profile=relevance.profile(scene,slot)
                slot['subject_anchor']=current_profile['subject_anchor']
                # Read-only display refresh: never replace an existing asset or
                # overwrite archived history merely because the page is opened.
                if slot['selected_media']:
                    slot['selected_media'].update(relevance.evaluate(slot['selected_media'],current_profile))
                    slot.update({k:slot['selected_media'][k] for k in ('relevance_score','relevance_label')})
                slot['candidates']=[{**m,**relevance.evaluate(m,current_profile)} for m in slot['candidates']]
                if slot['selected_media']:
                    try: asset_path(self.projects,project_id,slot['selected_media'])
                    except (StockError,OSError):
                        slot['status']='error';slot['message']='Yerel dosya eksik veya değişmiş. Kilidi açıp Eksik Medyaları Tamamla deyin.'
                slot['status_label'] = STATUSES.get(slot['status'],'Bekliyor')
                slot['coverage_warning'] = coverage_warning(slot['selected_media'],slot)
                slot['trim_needed'] = bool(slot['selected_media'] and slot['selected_media']['media_type']=='video'
                                           and slot['selected_media']['duration']>slot['duration']+.05)
            rows = connection.execute('SELECT * FROM stock_jobs WHERE project_id=? AND plan_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',
                                      (project_id,handoff['plan_id'])).fetchone()
            public['job'] = self._job(rows)
            public['providers'] = {name:bool(self.settings.stock_config(name).get('api_key')) for name in ('pexels','pixabay')}
            media = [s['selected_media'] for s in public['slots'] if s['status']=='complete' and s['selected_media']]
            public['media_mix'] = {'total_slots':len(public['slots']),
                                   'selected_videos':sum(m['media_type']=='video' for m in media),
                                   'selected_images':sum(m['media_type']=='image' for m in media),
                                   'unresolved_slots':len(public['slots'])-len(media)}
            public['media_mix']['video_ratio_percent']=round(100*public['media_mix']['selected_videos']/len(media)) if media else 0
            public['media_mix']['video_target_range']=[75,90]
            if len(media)>=3 and not public['media_mix']['selected_videos'] and any(s['preferred_type']=='stock_video' for s in public['slots']):
                public['warnings'].append('Hiç stok video seçilmedi. Yalnız uygun görsel bulunduysa bu korunur; ilgisiz video oranı artırmak için seçilmez. Arama Tanısı bölümünü kontrol edin.')
            duplicates = sum(media_duplicate(m,media[:i]) for i,m in enumerate(media))
            locked=[s['selected_media'] for s in public['slots'] if s['locked'] and s['selected_media']]
            if any(media_duplicate(m,locked[:i]) for i,m in enumerate(locked)):public['warnings'].append('Aynı medya birden fazla kilitli alanda kullanılıyor.')
            if duplicates: public['warnings'].append('Aynı stok medya birden fazla yuvada kullanılıyor. İsterseniz Değiştir ile çeşitlendirin.')
            if len(media)>=3 and any(all(m['media_type']=='image' for m in media[i:i+3]) for i in range(len(media)-2)):
                public['warnings'].append('Art arda durağan görseller var. Uygun video adaylarını kontrol edin.')
            if len(public['slots'])>=3 and any(all(s['composition']==public['slots'][i]['composition'] for s in public['slots'][i:i+3]) for i in range(len(public['slots'])-2)):
                public['warnings'].append('Benzer çekim kompozisyonları tekrarlanıyor. Medya önizlemelerini karşılaştırın.')
            self._guard(public)
            return public

    def _idle(self, connection, project_id):
        if connection.execute("SELECT 1 FROM stock_jobs WHERE project_id=? AND status IN ('queued','running')",(project_id,)).fetchone():
            raise StockError('busy','Medya işlemi sürüyor. Tamamlanmasını bekleyin.',409)

    def _stamp(self, state, payload):
        if not isinstance(payload,dict) or payload.get('plan_id')!=state['plan_id'] or payload.get('revision')!=state['revision']:
            raise StockError('stale','Medya planı değişti. Yenileyip tekrar deneyin.',409)

    def _slot(self, state, slot_id):
        for slot in state['slots']:
            if slot['slot_id']==slot_id: return slot
        raise StockError('missing_slot','Medya yuvası bulunamadı. Planı yenileyin.',404)

    def mutate(self, project_id, slot_id, payload):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            state = self._ensure(connection,self._handoff(project_id))
            self._stamp(state,payload);self._idle(connection,project_id)
            if set(payload)-{'plan_id','revision','action'}: raise StockError('invalid_input','Medya işlemini kontrol edin.',422)
            slot = self._slot(state,slot_id)
            action = payload.get('action')
            if action=='unlock': slot['locked']=False
            elif action=='lock':
                if not slot['selected_media'] or slot['status']!='complete':
                    raise StockError('no_selection','Önce medya seçip indirin.',409)
                asset_path(self.projects,project_id,slot['selected_media']);slot['locked']=True
            elif action=='remove':
                if slot['locked']: raise StockError('locked','Önce medya kilidini açın.',409)
                slot.update(selected_media=None,status='pending',message='',warnings=[])
                # Project cache file stays; removing a slot never deletes shared assets.
            else: raise StockError('invalid_action','Bu medya işlemi kullanılamıyor.',422)
            self._save(connection,state);self._mirror(state)
        return self.view(project_id)

    def start(self, project_id, payload, *, slot_id=None):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            handoff = self._handoff(project_id);state = self._ensure(connection,handoff)
            self._stamp(state,payload);self._idle(connection,project_id)
            if set(payload)-{'plan_id','revision','action','candidate_id','allow_duplicate','video_duration_tolerance_seconds'}:
                raise StockError('invalid_input','Medya işlemini kontrol edin.',422)
            action = payload.get('action')
            if action not in ('auto','missing','search','select','search_videos','replace_images','relevance_research'): raise StockError('invalid_action','Bu medya işlemi kullanılamıyor.',422)
            if (action in ('search','select','search_videos')) != bool(slot_id): raise StockError('invalid_input','Geçerli medya yuvasını seçin.',422)
            tolerance = payload.get('video_duration_tolerance_seconds',state.get('search_options',{}).get('video_duration_tolerance_seconds',DEFAULT_VIDEO_TOLERANCE))
            if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or not 0<=tolerance<=1.5:
                raise StockError('invalid_input','Kısa video toleransı 0 ile 1,5 saniye arasında olmalı.',422)
            progress = {'completed':[],'percent':0,'message':'Medya işlemi hazırlanıyor.','category':'none',
                        'handoff_fingerprint':state['handoff_fingerprint'],
                        'video_duration_tolerance_seconds':tolerance,'search_diagnostics':[]}
            if slot_id:
                slot = self._slot(state,slot_id)
                if slot['locked']: raise StockError('locked','Önce medya kilidini açın.',409)
                if action=='search_videos' and (not slot['selected_media'] or slot['selected_media']['media_type']!='image'):
                    raise StockError('invalid_input','Videoyla değiştirmek için bir görsel yuvası seçin.',422)
                if action=='select':
                    candidate = next((m for m in slot['candidates'] if candidate_id(m)==payload.get('candidate_id')),None)
                    if not candidate: raise StockError('invalid_candidate','Aday artık listede değil. Yeniden Ara deyin.',422)
                    cached=connection.execute('SELECT metadata_json FROM stock_assets WHERE project_id=? AND provider=? AND media_id=? AND media_type=?',(project_id,candidate['provider'],candidate['media_id'],candidate['media_type'])).fetchone()
                    if cached:candidate={**candidate,'sha256':json.loads(cached[0]).get('sha256')}
                    duplicate = media_duplicate(candidate,[s['selected_media'] for s in state['slots'] if s['slot_id']!=slot_id])
                    if duplicate and payload.get('allow_duplicate') is not True:
                        raise StockError('duplicate','Bu medya başka yuvada kullanılıyor. Başka aday seçin veya tekrar kullanımını onaylayın.',409)
                    progress['candidate'] = candidate
                    progress['duplicate'] = duplicate
                    progress['allow_duplicate'] = payload.get('allow_duplicate') is True
            if action=='replace_images' and not any(self._replaceable(s) for s in state['slots']):
                raise StockError('no_selection','Video tercihli, kilitsiz görsel yuvası bulunamadı.',422)
            if not any(self.settings.stock_config(name).get('api_key') for name in ('pexels','pixabay')) and action!='select':
                raise StockError('missing_key','Ayarlar → Pexels veya Pixabay bölümünde API anahtarını kaydedin.',422)
            if 'video_duration_tolerance_seconds' in payload:
                state['search_options']={'video_duration_tolerance_seconds':tolerance}
                self._save(connection,state);self._mirror(state)
            if action=='relevance_research':
                self._guard(state)
                try:history=archive_selection(self.projects,project_id,state)
                except OSError:raise StockError('local_storage','Önceki medya seçimleri kaydedilemedi. Boş alanı kontrol edip tekrar deneyin.',409) from None
                state.setdefault('selection_history',[]).append(history)
                state['selection_version']=history['version']+1
                self._save(connection,state);self._mirror(state)
            job_id = uuid4().hex;created = now()
            connection.execute('INSERT INTO stock_jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                (job_id,project_id,state['plan_id'],action,slot_id,'queued',json.dumps(progress,ensure_ascii=False),'',created,created))
        self.futures[job_id] = self.executor.submit(self._run,job_id)
        return {'job_id':job_id}

    @staticmethod
    def _replaceable(slot):
        return (not slot['locked'] and slot['preferred_type']=='stock_video' and slot['selected_media']
                and slot['selected_media']['media_type']=='image')

    def resume(self, project_id, job_id, payload):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            state = self._ensure(connection,self._handoff(project_id))
            self._stamp(state,payload);self._idle(connection,project_id)
            row = connection.execute('SELECT * FROM stock_jobs WHERE id=? AND project_id=?',(job_id,project_id)).fetchone()
            if (not row or row['plan_id']!=state['plan_id'] or row['status']!='error'
                    or json.loads(row['progress_json']).get('handoff_fingerprint')!=state['handoff_fingerprint']):
                raise StockError('stale_job','Bu işlem sürdürülemez. Güncel planda Eksik Medyaları Tamamla deyin.',409)
            connection.execute("UPDATE stock_jobs SET status='queued',error_message='',updated_at=? WHERE id=?",(now(),job_id))
        self.futures[job_id] = self.executor.submit(self._run,job_id)
        return {'job_id':job_id}

    def _checkpoint(self, job, progress, *, slot=None, status='running', error=''):
        project_id = job['project_id']
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            handoff = self._handoff(project_id)
            state = self._load(connection,project_id,job['plan_id'])
            if (not state or handoff['plan_id']!=job['plan_id'] or state['handoff_fingerprint']!=fingerprint(handoff)
                    or progress.get('handoff_fingerprint')!=state['handoff_fingerprint']):
                raise StockError('stale_plan','Aktif sahne planı değişti. Tamamlanan dosyalar korundu; güncel planda Eksik Medyaları Tamamla deyin.',409)
            if slot:
                current = self._slot(state,slot['slot_id'])
                if current['locked']: raise StockError('locked','Kilitli medya değiştirilmedi.',409)
                current.update(slot);self._save(connection,state);self._mirror(state)
            self._guard(progress)
            connection.execute('UPDATE stock_jobs SET status=?,progress_json=?,error_message=?,updated_at=? WHERE id=?',
                               (status,json.dumps(progress,ensure_ascii=False),error,now(),job['id']))

    def _cache_search(self, project_id, name, kind, query):
        canonical = query[:100] if name=='pixabay' else query
        with self.projects.lock, closing(self.projects._connection()) as connection:
            row = connection.execute('SELECT result_json,created_at FROM stock_search_cache WHERE project_id=? AND provider=? AND media_type=? AND query=?',
                                     (project_id,name,kind,canonical)).fetchone()
            if row and datetime.fromisoformat(row['created_at']) > datetime.now(timezone.utc)-timedelta(hours=24):
                saved = json.loads(row['result_json'])
                results = saved if isinstance(saved,list) else saved['results']
                counts = normalization_counts(saved.get('normalization') if isinstance(saved,dict) else None,len(results))
                return results,counts,True
        provider = self.factory(name,self.settings)
        try: results = provider.search(canonical,kind)
        except StockError as error:
            error.search_diagnostic = normalization_counts(getattr(provider,'last_diagnostic',None),0)
            raise
        results = [normalized_media(m) for m in results]
        self._guard(results)
        counts = normalization_counts(getattr(provider,'last_diagnostic',None),len(results))
        saved = {'cache_version':2,'results':results,'normalization':counts}
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute('INSERT OR REPLACE INTO stock_search_cache VALUES (?,?,?,?,?,?)',
                               (project_id,name,kind,canonical,json.dumps(saved,ensure_ascii=False),now()))
        return results,counts,False

    def _record_diagnostic(self,name,kind,query,counts,ranked,used,rejected,cached,category,slot,progress):
        diagnostic = {'provider':name,'media_type':kind,
                      'query':safe_query(query,self.settings.secret_values()),
                      'raw_count':counts['raw_count'],'normalized_count':counts['normalized_count'],
                      'accepted_count':len(ranked),'available_count':sum(identity(m) not in used for m in ranked),
                      'rejected':{**rejected,**counts['rejected']},'cached':cached,
                      'category':category if category in CATEGORIES else 'invalid_response'}
        diagnostic['summary'] = search_summary(diagnostic)
        slot.setdefault('search_diagnostics',[]).append(diagnostic)
        progress['search_diagnostics'] = [*progress.get('search_diagnostics',[]),diagnostic][-12:]
        log_search(diagnostic)

    def _search(self, project_id, slot, used, progress, job, *, video_only=False):
        candidates, failures, unavailable = {}, [], set()
        scene=next(s for s in self._handoff(project_id)['scenes'] if s['scene_id']==slot['scene_id'])
        profile=relevance.profile(scene,slot)
        slot.update(subject_anchor=profile['subject_anchor'],relevance_profile=profile)
        queries=relevance.queries_for(profile)
        tolerance = progress.get('video_duration_tolerance_seconds',DEFAULT_VIDEO_TOLERANCE)
        slot['search_diagnostics'] = []
        # Search related videos first, then related images, before general but
        # compatible footage. Type never certifies content relevance.
        phases=[('video',(1,2,3),relevance.RELATED)]
        if video_only:phases.append(('video',(4,),relevance.MINIMUM))
        else:
            phases.extend([('image',(1,2,3),relevance.RELATED),
                           ('video',(4,),relevance.MINIMUM),('image',(4,),relevance.MINIMUM)])
        for kind,tiers,threshold in phases:
            for tier,query in queries:
                if tier not in tiers:continue
                for name in ('pexels','pixabay'):
                    if name in unavailable or not self.settings.stock_config(name).get('api_key'): continue
                    progress['message']=f"Sahne medyası aranıyor · {name.title()} {'video' if kind=='video' else 'görsel'}"
                    self._checkpoint(job,progress)
                    rejected = {reason:0 for reason in REASONS[:3]}
                    try: results,counts,cached = self._cache_search(project_id,name,kind,query)
                    except StockError as error:
                        counts = getattr(error,'search_diagnostic',normalization_counts(None,0))
                        self._record_diagnostic(name,kind,query,counts,[],used,rejected,False,error.category,slot,progress)
                        self._checkpoint(job,progress,slot=slot)
                        failures.append(error);unavailable.add(name)
                        continue
                    eligible = []
                    for media in results:
                        reason = rejection_reason(media,slot,tolerance,technical_only=True)
                        if reason: rejected[reason] += 1
                        else:
                            rated=relevance.annotate(media,profile,tier,query)
                            if not relevance.acceptable(rated,profile):rejected['relevance']+=1
                            else:eligible.append(rated)
                            previous=candidates.get(identity(rated))
                            if previous is None or relevance.rank(rated,slot)>relevance.rank(previous,slot):candidates[identity(rated)]=rated
                    ranked = sorted(eligible,key=lambda m:relevance.rank(m,slot),reverse=True)
                    self._record_diagnostic(name,kind,query,counts,ranked,used,rejected,cached,'none',slot,progress)
                    self._checkpoint(job,progress,slot=slot)
                # Exhaust specific/context VIDEO before IMAGE. A related video
                # already satisfies the soft video-first goal; never chase images
                # merely for a few extra points. Weak video cannot pass this gate.
                best=relevance.choose(list(candidates.values()),used,slot)
                if best and best['relevance_score']>=threshold and best['media_type']==kind:
                    return relevance.ordered(list(candidates.values()),used,slot),failures
        return relevance.ordered(list(candidates.values()),used,slot),failures

    def _run(self, job_id):
        started = time.monotonic();category = 'success';job = None
        try:
            with self.projects.lock, closing(self.projects._connection()) as connection:
                row = connection.execute('SELECT * FROM stock_jobs WHERE id=?',(job_id,)).fetchone()
                if not row: return
                job = self._job(row)
                state = self._load(connection,job['project_id'],job['plan_id'])
            progress = job['progress'];self._checkpoint(job,progress)
            slots = [deepcopy(s) for s in state['slots'] if not job['slot_id'] or s['slot_id']==job['slot_id']]
            if job['action']=='replace_images': slots = [s for s in slots if self._replaceable(s)]
            selections={s['slot_id']:s['selected_media'] for s in state['slots'] if s['selected_media']}
            if job['action']=='relevance_research':
                # Locked reservations win. Of unlocked duplicates only the first
                # occurrence owns the identity; later slots must find new media.
                reservations=[s for s in state['slots'] if s['locked'] and s['selected_media']]
                for old in state['slots']:
                    if old['locked'] or not old['selected_media']:continue
                    if media_duplicate(old['selected_media'],[r['selected_media'] for r in reservations]):selections.pop(old['slot_id'],None)
                    else:reservations.append(old)
            for index,slot in enumerate(slots):
                if self.closed: raise StockError('interrupted','İşlem durdu. Tamamlanan medya korundu; Devam Et deyin.')
                progress['percent'] = int(index/max(1,len(slots))*100)
                if slot['locked']: continue
                if slot['slot_id'] in progress['completed']: continue
                used=set().union(*(identity_keys(value) for key,value in selections.items() if key!=slot['slot_id']))
                if job['action'] in ('auto','missing') and slot['selected_media'] and slot['status']=='complete':
                    try:
                        asset_path(self.projects,job['project_id'],slot['selected_media'])
                        continue
                    except (StockError,OSError): pass
                progress['slot_id']=slot['slot_id'];progress['scene_id']=slot['scene_id'];progress['slot_order']=slot['order']
                # Keep existing selected media throughout replacement/search failures.
                progress['message']=f"Medya {index+1}/{len(slots)} aranıyor"
                self._checkpoint(job,progress)
                if job['action']=='select': candidates = [progress['candidate']];failures=[]
                else:
                    candidates,failures = self._search(job['project_id'],slot,used,progress,job,
                                                     video_only=job['action'] in ('search_videos','replace_images'))
                    slot['candidates']=candidates
                    self._checkpoint(job,progress,slot=slot)
                if job['action'] in ('search','search_videos'):
                    if not candidates and failures: raise failures[-1]
                    if not slot['selected_media']: slot['status']='candidates' if candidates else 'ai_needed'
                    slot['message']='Adayları önizleyip birini seçin.' if candidates else ('Uygun video bulunamadı. Mevcut görsel korundu.' if job['action']=='search_videos' else 'Uygun stok medya bulunamadı.')
                    self._checkpoint(job,progress,slot=slot)
                else:
                    if job['action']=='select':
                        scene=next(s for s in self._handoff(job['project_id'])['scenes'] if s['scene_id']==slot['scene_id'])
                        slot['relevance_profile']=relevance.profile(scene,slot)
                        m=candidates[0]
                        chosen_candidate=relevance.annotate(m,slot['relevance_profile'],m.get('search_tier') or 1,m['query_used'])
                    else:chosen_candidate=relevance.choose(candidates,used,slot)
                    duplicate=bool(chosen_candidate and identity(chosen_candidate) in used)
                    if chosen_candidate is None:
                        if failures: raise failures[-1]
                        if job['action']=='relevance_research' and slot['selected_media'] and (not relevance.acceptable(relevance.evaluate(slot['selected_media'],slot['relevance_profile']),slot['relevance_profile']) or bool(identity_keys(slot['selected_media'])&used)):
                            slot['selected_media']=None;selections.pop(slot['slot_id'],None)
                            for key in ('search_tier','query_used','relevance_score','relevance_label'):slot.pop(key,None)
                        if not slot['selected_media']: slot['status']='ai_needed'
                        slot['message']=('Uygun video bulunamadı. Mevcut görsel korundu.' if job['action']=='replace_images' else 'Uygun ve kullanılmamış stok medya bulunamadı.')
                        self._checkpoint(job,progress,slot=slot)
                    else:
                        progress['message']=f"Medya {index+1}/{len(slots)} indiriliyor"
                        if not slot['selected_media']: slot['status']='downloading'
                        self._checkpoint(job,progress,slot=slot)
                        chosen = self.downloader.download(job['project_id'],chosen_candidate)
                        while identity_keys(chosen)&used and job['action']!='select':
                            used.update(identity_keys(chosen));chosen_candidate=relevance.choose(candidates,used,slot)
                            if chosen_candidate is None:break
                            chosen=self.downloader.download(job['project_id'],chosen_candidate)
                        if job['action']!='select' and identity_keys(chosen)&used:
                            # Files stay archived, but duplicate bytes never become an automatic selection.
                            if job['action']=='relevance_research' or not slot['selected_media']:
                                slot.update(selected_media=None,status='ai_needed');selections.pop(slot['slot_id'],None)
                            slot['message']='Uygun ve kullanılmamış stok medya bulunamadı.'
                            self._checkpoint(job,progress,slot=slot);progress['completed'].append(slot['slot_id']);continue
                        if job['action']=='select' and identity_keys(chosen)&used and not progress.get('allow_duplicate'):
                            raise StockError('duplicate','Bu medya başka yuvada kullanılıyor. Tekrar kullanımını onaylayın.',409)
                        self._guard(chosen)
                        slot.update(manual_reuse=job['action']=='select' and bool(identity_keys(chosen)&used),selected_media=chosen,status='complete',message='İndirildi. Anlatıma uygunluğu Önizle ile kontrol edin.',warnings=[])
                        slot.update({key:chosen.get(key) for key in ('search_tier','query_used','provider_query','relevance_score','relevance_label')})
                        if job['action']!='select' and slot['preferred_type']=='stock_video' and chosen['media_type']=='image':
                            slot['warnings'].append('Daha ilgili görsel seçildi. Render sırasında yerel kamera hareketi kullanılabilir.')
                        if duplicate or progress.get('duplicate'): slot['warnings'].append('Bu medya projede tekrar kullanılıyor. Değiştir ile başka aday seçebilirsiniz.')
                        if chosen['width']<1800 or chosen['height']<1000: slot['warnings'].append('Kaynak çözünürlüğü 1080p sınıfından düşük. Uygun daha yüksek çözünürlüklü aday varsa değiştirin.')
                        selections[slot['slot_id']]=chosen;self._checkpoint(job,progress,slot=slot)
                progress['completed'].append(slot['slot_id'])
                self._checkpoint(job,progress)
            progress.update(percent=100,message='Medya işlemi tamamlandı. Önizlemeleri kontrol edin.',category='none')
            self._checkpoint(job,progress,status='completed')
        except Exception as error:
            category = error.category if isinstance(error,StockError) else 'unexpected_backend'
            safe_message = str(error) if isinstance(error,StockError) else 'Medya işlemi tamamlanamadı. Tamamlanan dosyalar korundu; Devam Et deyin.'
            safe_message = SecretGuard(self.settings.secret_values()).clean(safe_message)
            if job:
                with self.projects.lock, closing(self.projects._connection()) as connection, connection:
                    progress = job['progress'];progress['category']=category
                    progress = SecretGuard(self.settings.secret_values()).clean(progress)
                    state = self._load(connection,job['project_id'],job['plan_id'])
                    if state and progress.get('slot_id'):
                        failed = next((s for s in state['slots'] if s['slot_id']==progress['slot_id']),None)
                        if failed and not failed['selected_media'] and not failed['locked']:
                            failed.update(status='error',message=safe_message)
                            self._save(connection,state);self._mirror(state)
                    connection.execute("UPDATE stock_jobs SET status='error',progress_json=?,error_message=?,updated_at=? WHERE id=?",
                                       (json.dumps(progress,ensure_ascii=False),safe_message,now(),job_id))
        finally:
            LOG.info('stock operation=job result=%s category=%s elapsed_ms=%.0f',
                     'success' if category=='success' else 'failure',category,(time.monotonic()-started)*1000)

    def handoff(self, project_id):
        state = self.view(project_id)
        slots = []
        for slot in state['slots']:
            media = slot['selected_media']
            complete = slot['status']=='complete' and media is not None
            slots.append({'scene_id':slot['scene_id'],'slot_id':slot['slot_id'],'order':slot['order'],
                          'estimated_start':slot['estimated_start'],'estimated_end':slot['estimated_end'],
                          'slot_duration':slot['duration'],'status':slot['status'],'locked':slot['locked'],
                          **({key:media[key] for key in ('media_type','local_path','duration','width','height','provider','media_id')} if complete else
                             {key:None for key in ('media_type','local_path','duration','width','height','provider','media_id')}),
                          'coverage_warning':coverage_warning(media,slot) if complete else '',
                          'trim_needed':bool(complete and media['media_type']=='video' and media['duration']>slot['duration']+0.05)})
        return {'contract_version':1,'project_id':project_id,'plan_id':state['plan_id'],
                'source_script_version_id':state['source_version_id'],'timing_source':'estimated',
                'ready':all(s['status']=='complete' for s in slots),'slots':slots,'rendered':False}


def candidate_id(media):
    return media['provider']+':'+media['media_type']+':'+media['media_id']
