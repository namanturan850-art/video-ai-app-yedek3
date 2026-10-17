from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import re
from uuid import uuid4

from app.editor.models import EditorError
from app.stock.download import asset_path

TRACKS = ('emphasis', 'layers', 'maps', 'infographics', 'visuals', 'audio', 'subtitles')
ANALYZER_VERSION = 'naman-frames-v1'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class EditorService:
    """Adapter over authoritative production/stock/subtitle records."""
    def __init__(self, production, stock, subtitles, settings):
        self.production, self.stock, self.subtitles, self.settings = production, stock, subtitles, settings
        self.projects = production.projects

    def _active(self, project_id):
        production = self.production.view(project_id)
        if not production['plan']:
            raise EditorError('plan_required', 'Önce Görsel ve Kurgu Hazırlığı ekranında bir sahne planı oluşturun.', 409)
        return production['plan']

    def view(self, project_id):
        plan = self._active(project_id)
        stock = self.stock.view(project_id)
        subtitle_state = self.subtitles.view(project_id)
        active_subtitles = subtitle_state.get('active') or {}
        cues = active_subtitles.get('cues') or []
        audio = (subtitle_state.get('narration') or {}).get('metadata', {}).get('audio') or {}
        slots = stock.get('slots') or []
        duration = max([float(q.get('end', 0)) for q in cues] + [float(b.get('end', 0)) for b in plan['blocks']] + [0.0])
        scenes = []
        for block in plan['blocks']:
            scene_id = block['id']
            scene_slots = [s for s in slots if s.get('scene_id') == scene_id]
            start, end = float(block.get('start', 0)), float(block.get('end', 0))
            scenes.append({'scene_id': scene_id, 'start': start, 'end': end, 'locked': bool(block.get('locked')),
                           'narration': block.get('narration', ''), 'transition': block.get('transition', ''),
                           'motion': block.get('motion', ''), 'overlay_text': block.get('overlay_text', ''),
                           'composition': block.get('composition', ''), 'slots': [self._public_slot(s) for s in scene_slots]})
        tracks = {name: [] for name in TRACKS}
        for scene in scenes:
            base = {'scene_id': scene['scene_id'], 'start': scene['start'], 'end': scene['end']}
            tracks['visuals'].extend([{**base, 'slot_id': s['slot_id'], 'media': s.get('selected_media'),
                                       'clip_start': s.get('clip_start', 0)} for s in scene['slots']])
            motion = scene.get('motion') or ''
            if motion in ('map', 'route', 'schema'): tracks['maps'].append({**base, 'type': motion})
            if motion in ('number', 'compare', 'card', 'chart', 'infographic'): tracks['infographics'].append({**base, 'type': motion})
            if scene.get('overlay_text'): tracks['layers'].append({**base, 'text': scene['overlay_text']})
        for cue in cues:
            tracks['subtitles'].append({'start': cue['start'], 'end': cue['end'], 'text': cue['text'], 'index': cue['index']})
            words = cue['text'].split()
            step = (cue['end'] - cue['start']) / max(1, len(words))
            tracks['emphasis'].extend({'start': cue['start'] + i * step, 'end': cue['start'] + (i + 1) * step,
                                       'text': word, 'timing': 'estimated'} for i, word in enumerate(words))
        if audio: tracks['audio'].append({'start': 0, 'end': float(audio.get('duration') or duration),
                                          'url': f'/api/projects/{project_id}/narration/versions/{subtitle_state["narration"]["id"]}/audio'})
        return {'brand': 'NAMAN', 'contract_version': 1, 'project_id': project_id, 'plan_id': plan['plan_id'],
                'revision': plan['revision'], 'duration': duration, 'fps': 30, 'scenes': scenes, 'tracks': tracks,
                'track_order': list(TRACKS), 'audio_ready': bool(audio), 'subtitle_timing': subtitle_state.get('timing_source'),
                'warnings': stock.get('warnings', []) + ([subtitle_state['message']] if subtitle_state.get('message') else [])}

    @staticmethod
    def _public_slot(slot):
        media = deepcopy(slot.get('selected_media'))
        if media:
            for key in list(media):
                if key.endswith('_url') and key not in ('source_url',): media.pop(key, None)
        return {'slot_id': slot['slot_id'], 'scene_id': slot.get('scene_id'), 'start': slot.get('estimated_start', 0),
                'end': slot.get('estimated_end', 0), 'locked': bool(slot.get('locked')), 'status': slot.get('status'),
                'selected_media': media, 'clip_start': slot.get('segment_start') or 0}

    def archive(self, project_id):
        self.projects.get(project_id)
        with self.projects.lock, closing(self.projects._connection()) as connection:
            rows = connection.execute('SELECT * FROM stock_assets WHERE project_id=? ORDER BY provider,media_id',(project_id,)).fetchall()
            ranges = {(r['provider'], r['media_id']): dict(r) for r in connection.execute('SELECT * FROM media_clip_ranges WHERE project_id=?',(project_id,))}
        result=[]
        for row in rows:
            meta=json.loads(row['metadata_json']); item={'provider':row['provider'],'media_id':row['media_id'],'media_type':row['media_type'],**meta}
            try:
                path=asset_path(self.projects,project_id,item)
                identity=item.get('sha256') or sha256_file(path)
            except Exception:
                continue
            rights=item.get('source_metadata') or {}
            saved=ranges.get((row['provider'],row['media_id']))
            result.append({'provider':row['provider'],'media_id':row['media_id'],'media_type':row['media_type'],
                           'sha256':identity,'duration':item.get('duration'),'source_url':item.get('source_url',''),
                           'rights':{k:rights.get(k) for k in ('license','license_url','author','page_url') if rights.get(k)},
                           'clip_range': {'start':saved['start_seconds'],'end':saved['end_seconds'],'revision':saved['revision']} if saved else None})
        return {'project_id':project_id,'items':result,'count':len(result),'reuse_policy':'Yerel hash eşleşirse yeniden indirilmez.'}

    def set_range(self, project_id, provider, media_id, payload):
        if set(payload) != {'sha256','start','end','revision'} or not all(finite(payload[k]) for k in ('start','end','revision')):
            raise EditorError('invalid_range','Klip başlangıç, bitiş ve sürüm bilgilerini kontrol edin.')
        if payload['start'] < 0 or payload['end'] <= payload['start'] or type(payload['revision']) is not int:
            raise EditorError('invalid_range','Klip bitişi başlangıçtan sonra olmalıdır.')
        archive=next((x for x in self.archive(project_id)['items'] if x['provider']==provider and x['media_id']==media_id),None)
        if not archive or archive['sha256'] != payload['sha256']:
            raise EditorError('stale_media','Yerel medya değişti. Arşivi yenileyip tekrar deneyin.',409)
        if finite(archive.get('duration')) and payload['end'] > archive['duration'] + .001:
            raise EditorError('invalid_range','Klip aralığı medya süresini aşamaz.')
        current=archive.get('clip_range');expected=current['revision'] if current else 0
        if payload['revision'] != expected: raise EditorError('stale_revision','Klip aralığı değişti. Sayfayı yenileyin.',409)
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute('''INSERT INTO media_clip_ranges VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,provider,media_id) DO UPDATE SET sha256=excluded.sha256,start_seconds=excluded.start_seconds,
                end_seconds=excluded.end_seconds,rights_json=excluded.rights_json,revision=excluded.revision,updated_at=excluded.updated_at''',
                (project_id,provider,media_id,payload['sha256'],payload['start'],payload['end'],json.dumps(archive['rights'],ensure_ascii=False),expected+1,now()))
        return next(x for x in self.archive(project_id)['items'] if x['provider']==provider and x['media_id']==media_id)

    def task_package(self, project_id):
        plan=self._active(project_id); project=self.projects.get(project_id)
        return {'schema':'naman.manual-plan.v1','instructions':['Yalnız verilen anlatımı kullanın; yeni olgusal iddia eklemeyin.','Kilitli sahneleri ve medyayı değiştirmeyin.'],
                'project':{'id':project_id,'name':project['name'],'topic':project['topic'],'language':project['language']},
                'base':{'plan_id':plan['plan_id'],'revision':plan['revision']},
                'required_sections':['sahneler','infografikler','harita_sahneleri','vurgular','katmanlar'],
                'narration':[{'scene_id':b['id'],'text':b['narration'],'locked':bool(b.get('locked'))} for b in plan['blocks']],
                'output_template':{'schema':'naman.manual-plan.v1','base':{'plan_id':plan['plan_id'],'revision':plan['revision']},
                                   'sahneler':[],'infografikler':[],'harita_sahneleri':[],'vurgular':[],'katmanlar':[]}}

    def validate_import(self, project_id, payload):
        plan=self._active(project_id); errors=[]
        required={'schema','base','sahneler','infografikler','harita_sahneleri','vurgular','katmanlar'}
        if not isinstance(payload,dict): errors.append('JSON kökü bir nesne olmalıdır.'); payload={}
        missing=required-set(payload); extra=set(payload)-required
        if missing: errors.append('Eksik bölümler: '+', '.join(sorted(missing)))
        if extra: errors.append('Bilinmeyen bölümler: '+', '.join(sorted(extra)))
        if payload.get('schema')!='naman.manual-plan.v1': errors.append('schema değeri naman.manual-plan.v1 olmalıdır.')
        base=payload.get('base') or {}
        if base!={'plan_id':plan['plan_id'],'revision':plan['revision']}: errors.append('Temel plan değişmiş; güncel görev paketini yeniden alın.')
        known={b['id']:b for b in plan['blocks']}
        for section in ('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar'):
            items=payload.get(section)
            if not isinstance(items,list): errors.append(f'{section} bir liste olmalıdır.'); continue
            for index,item in enumerate(items):
                if not isinstance(item,dict) or item.get('scene_id') not in known: errors.append(f'{section}[{index}] geçerli scene_id içermelidir.'); continue
                if known[item['scene_id']].get('locked') and len(item)>1: errors.append(f'{item["scene_id"]} kilitli; değiştirilemez.')
        diff=self._diff(plan,payload) if not errors else []
        correction='\n'.join(f'- {e}' for e in errors)
        return {'valid':not errors,'errors':errors,'correction_message':('JSON düzeltmeleri:\n'+correction) if errors else '',
                'base_plan_id':plan['plan_id'],'base_revision':plan['revision'],'changes':diff}

    def _diff(self, plan, payload):
        changes=[]
        for section,field in (('sahneler','scene'),('infografikler','infographic'),('harita_sahneleri','map'),('vurgular','emphasis'),('katmanlar','layer')):
            for item in payload.get(section,[]):
                if len(item)>1: changes.append({'scene_id':item['scene_id'],'kind':field,'after':{k:v for k,v in item.items() if k!='scene_id'}})
        return changes

    def import_plan(self, project_id, payload):
        check=self.validate_import(project_id,payload)
        if not check['valid']: raise EditorError('invalid_import','JSON doğrulanamadı; hiçbir değişiklik kaydedilmedi.',422,check['errors'])
        plan=deepcopy(self._active(project_id)); by_id={b['id']:b for b in plan['blocks']}
        for item in payload['sahneler']:
            target=by_id[item['scene_id']]
            for src,dst in (('transition','transition'),('motion','motion'),('overlay_text','overlay_text'),('composition','composition')):
                if src in item: target[dst]=str(item[src])[:500]
        overlay_map={}
        for section,kind in (('infografikler','infographic'),('harita_sahneleri','map'),('vurgular','emphasis'),('katmanlar','layer')):
            for item in payload[section]: overlay_map.setdefault(item['scene_id'],[]).append({'kind':kind,**{k:v for k,v in item.items() if k!='scene_id'}})
        for scene_id,overlays in overlay_map.items(): by_id[scene_id]['naman_overlays']=overlays
        parent=plan['plan_id']; self.production._save(project_id,plan,new_version=True)
        with self.projects.lock,closing(self.projects._connection()) as connection,connection:
            connection.execute('INSERT INTO editor_revisions VALUES (?,?,?,?,?,?,?)',(uuid4().hex,project_id,plan['plan_id'],parent,'manual_import',json.dumps(payload,ensure_ascii=False),now()))
        return {'imported':True,'plan_id':plan['plan_id'],'revision':plan['revision'],'parent_plan_id':parent,'changes':check['changes']}

    def rollback(self, project_id, target_plan_id, payload):
        if payload != {'confirm':True}: raise EditorError('confirmation_required','Geri alma için açık onay gereklidir.')
        with self.projects.lock,closing(self.projects._connection()) as connection:
            row=connection.execute('SELECT plan_json FROM scene_plan_versions WHERE project_id=? AND id=?',(project_id,target_plan_id)).fetchone()
        if not row: raise EditorError('missing_revision','Plan sürümü bulunamadı.',404)
        target=json.loads(row[0]); copy=deepcopy(target); parent=self._active(project_id)['plan_id']
        self.production._save(project_id,copy,new_version=True)
        return {'rolled_back':True,'plan_id':copy['plan_id'],'parent_plan_id':parent,'restored_from':target_plan_id}

    def analyze(self, project_id, provider, media_id, payload):
        if set(payload)-{'enabled'} or type(payload.get('enabled')) is not bool: raise EditorError('invalid_request','Analiz seçimini kontrol edin.')
        media=next((x for x in self.archive(project_id)['items'] if x['provider']==provider and x['media_id']==media_id),None)
        if not media: raise EditorError('missing_media','Arşiv medyası bulunamadı.',404)
        with self.projects.lock,closing(self.projects._connection()) as connection:
            cached=connection.execute('SELECT result_json FROM archive_analysis_cache WHERE project_id=? AND sha256=? AND analyzer_version=?',(project_id,media['sha256'],ANALYZER_VERSION)).fetchone()
        if cached: return {**json.loads(cached[0]),'cached':True}
        if not payload['enabled']:
            return {'enabled':False,'cached':False,'message':'Gemini arşiv analizi kapalıdır; editör ve arşiv çalışmaya devam eder.','clips':[]}
        duration=float(media.get('duration') or 0)
        boundaries=self._shot_boundaries(project_id,provider,media_id,duration)
        clips=[{'start':a,'end':b,'sample_at':round((a+b)/2,3),'description':'Gemini yorumu bekleniyor','source':'ffmpeg_shot'}
               for a,b in zip(boundaries,boundaries[1:]) if b-a>=.25][:30]
        result={'enabled':True,'cached':False,'analysis_basis':'FFmpeg çekim geçişleri ve örnek kare zamanları; tam video Gemini’ye gönderilmez.',
                'clips':clips,'gemini_status':'not_called','message':'Gemini sağlayıcısı çağrılmadı; yerel çekim analizi kullanılabilir.'}
        with self.projects.lock,closing(self.projects._connection()) as connection,connection:
            connection.execute('INSERT INTO archive_analysis_cache VALUES (?,?,?,?,?)',(project_id,media['sha256'],ANALYZER_VERSION,json.dumps(result,ensure_ascii=False),now()))
        return result

    def _shot_boundaries(self, project_id, provider, media_id, duration):
        with self.projects.lock,closing(self.projects._connection()) as connection:
            row=connection.execute('SELECT media_type,metadata_json FROM stock_assets WHERE project_id=? AND provider=? AND media_id=?',
                                   (project_id,provider,media_id)).fetchone()
        if not row or row['media_type']!='video': return [0.0,duration] if duration else [0.0]
        item={'provider':provider,'media_id':media_id,'media_type':row['media_type'],**json.loads(row['metadata_json'])}
        try: path=asset_path(self.projects,project_id,item)
        except Exception: return [0.0,duration] if duration else [0.0]
        command=['ffmpeg','-hide_banner','-nostdin','-i',str(path),'-vf',"select='gt(scene,0.32)',showinfo",'-an','-f','null','-']
        try:
            completed=subprocess.run(command,capture_output=True,text=True,timeout=min(120,max(15,int(duration/2) if duration else 15)),check=False)
            points=[float(x) for x in re.findall(r'pts_time:([0-9.]+)',completed.stderr)]
        except (OSError,subprocess.TimeoutExpired,ValueError): points=[]
        values=[0.0]+[round(x,3) for x in points if .1<x<duration-.1]+([round(duration,3)] if duration else [])
        return sorted(set(values))
