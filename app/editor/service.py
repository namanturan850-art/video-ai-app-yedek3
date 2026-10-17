from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import base64
import json
import math
from pathlib import Path
import subprocess
import re
import os
import array
import io
import zipfile
from uuid import uuid4
from functools import wraps

from app.editor.models import EditorError
from app.subtitles.models import SubtitleError
from app.stock.download import asset_path

TRACKS = ('emphasis', 'layers', 'maps', 'infographics', 'visuals', 'audio', 'subtitles')
DEFAULT_AUDIO_SETTINGS = {'narration_volume': 1.0, 'narration_fade_in': 0.0,
                          'narration_fade_out': 0.0, 'sfx_volume': 0.10, 'sfx_levels': {}}
ANALYZER_VERSION = 'naman-frames-v2'
VIDEO_REVIEW_VERSION = 'naman-final-video-review-v1'
MAP_TEMPLATES = {'map','route','empire','zoom','relief','region','arrow'}
INFOGRAPHIC_TEMPLATES = {'stat','timeline','compare','list','beforeafter','icons','ratio','dynasty','fact'}
EMPHASIS_TEMPLATES = {'mark'}


def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.projects.lock:
            return method(self, *args, **kwargs)
    return call


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
    def __init__(self, production, stock, subtitles, settings, rendering=None):
        self.production, self.stock, self.subtitles, self.settings = production, stock, subtitles, settings
        self.rendering = rendering
        self.projects = production.projects
        self._waveforms = {}

    def _waveform(self,project_id,audio):
        """Return bounded peaks from the actual narration PCM; never synthesize a waveform."""
        identity=audio.get('sha256')
        if not identity:return None
        if identity in self._waveforms:return self._waveforms[identity]
        try:
            from app.narration.audio import audio_path
            from app.rendering.tools import discover
            path=audio_path(self.projects,project_id,audio);ffmpeg=discover().get('ffmpeg')
            if not ffmpeg:return None
            done=subprocess.run([ffmpeg,'-v','error','-i',str(path),'-ac','1','-ar','100','-f','s16le','pipe:1'],capture_output=True,timeout=45,stdin=subprocess.DEVNULL)
            if done.returncode or not done.stdout:return None
            samples=array.array('h');samples.frombytes(done.stdout);bins=160;step=max(1,math.ceil(len(samples)/bins))
            peaks=[round(max((abs(v) for v in samples[i:i+step]),default=0)/32768,3) for i in range(0,len(samples),step)][:bins]
            self._waveforms[identity]=peaks
            if len(self._waveforms)>32:self._waveforms.pop(next(iter(self._waveforms)))
            return peaks
        except (OSError,subprocess.SubprocessError,ValueError):return None

    def _active(self, project_id):
        production = self.production.view(project_id)
        if not production['plan']:
            raise EditorError('plan_required', 'Önce Görsel ve Kurgu Hazırlığı ekranında bir sahne planı oluşturun.', 409)
        return production['plan']

    def audio_settings(self, project_id):
        if not hasattr(self.projects,'_connection'):
            return {'project_id':project_id,**deepcopy(DEFAULT_AUDIO_SETTINGS)}
        self.projects.get(project_id)
        with self.projects.lock, closing(self.projects._connection()) as connection:
            row=connection.execute('SELECT * FROM editor_audio_settings WHERE project_id=?',(project_id,)).fetchone()
        if not row:return {'project_id':project_id,**deepcopy(DEFAULT_AUDIO_SETTINGS)}
        try:levels=json.loads(row['sfx_levels_json'])
        except (TypeError,ValueError):levels={}
        return {'project_id':project_id,'narration_volume':row['narration_volume'],
                'narration_fade_in':row['narration_fade_in'],'narration_fade_out':row['narration_fade_out'],
                'sfx_volume':row['sfx_volume'],'sfx_levels':levels if isinstance(levels,dict) else {}}

    @serialized
    def save_audio_settings(self,project_id,payload):
        expected=set(DEFAULT_AUDIO_SETTINGS)
        if not isinstance(payload,dict) or set(payload)!=expected:
            raise EditorError('invalid_audio_settings','Ses ayarı alanlarını kontrol edin.')
        values={key:payload.get(key) for key in expected-{'sfx_levels'}}
        limits={'narration_volume':(0,2),'narration_fade_in':(0,30),
                'narration_fade_out':(0,30),'sfx_volume':(0,.5)}
        if any(not finite(values[key]) or not limits[key][0]<=values[key]<=limits[key][1] for key in values):
            raise EditorError('invalid_audio_settings','Ses seviyesi veya fade süresi izin verilen aralıkta değil.')
        levels=payload['sfx_levels']
        if not isinstance(levels,dict) or len(levels)>200 or any(
                not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key)
                or not finite(value) or not 0<=value<=.5 for key,value in levels.items()):
            raise EditorError('invalid_audio_settings','Klip başına SFX seviyelerini kontrol edin.')
        self.projects.get(project_id)
        with closing(self.projects._connection()) as connection,connection:
            connection.execute('''INSERT INTO editor_audio_settings VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(project_id) DO UPDATE SET narration_volume=excluded.narration_volume,
                narration_fade_in=excluded.narration_fade_in,narration_fade_out=excluded.narration_fade_out,
                sfx_volume=excluded.sfx_volume,sfx_levels_json=excluded.sfx_levels_json,updated_at=excluded.updated_at''',
                (project_id,values['narration_volume'],values['narration_fade_in'],values['narration_fade_out'],
                 values['sfx_volume'],json.dumps(levels,sort_keys=True,separators=(',',':')),now()))
        return self.audio_settings(project_id)

    def view(self, project_id):
        plan = self._active(project_id)
        stock = self.stock.view(project_id)
        subtitle_state = self.subtitles.view(project_id)
        active_subtitles = subtitle_state.get('active') or {}
        cues = active_subtitles.get('cues') or []
        audio = (subtitle_state.get('narration') or {}).get('metadata', {}).get('audio') or {}
        slots = stock.get('slots') or []
        try:
            timing = self.subtitles.handoff(project_id) if hasattr(self.subtitles,'handoff') else {}
        except (EditorError,SubtitleError):
            timing = {}
        scene_times = {s['scene_id']: s for s in timing.get('scenes', [])}
        slot_times = {s['slot_id']: s for s in timing.get('stock_slots', [])}
        slots = [dict(s, estimated_start=slot_times[s['slot_id']]['start'],
                      estimated_end=slot_times[s['slot_id']]['end']) if s['slot_id'] in slot_times else s for s in slots]
        duration = max([float(q.get('end', 0)) for q in cues] + [float(b.get('end', 0)) for b in plan['blocks']] + [0.0])
        scenes = []
        for block in plan['blocks']:
            scene_id = block['id']
            scene_slots = [s for s in slots if s.get('scene_id') == scene_id]
            start, end = float(block.get('start', 0)), float(block.get('end', 0))
            if scene_id in scene_times:
                start, end = scene_times[scene_id]['start'], scene_times[scene_id]['end']
            scenes.append({'scene_id': scene_id, 'start': start, 'end': end, 'locked': bool(block.get('locked')),
                           'narration': block.get('narration', ''), 'transition': block.get('transition', ''),
                           'motion': block.get('motion', ''), 'overlay_text': block.get('overlay_text', ''),
                           'composition': block.get('composition', ''), 'naman_overlays':deepcopy(block.get('naman_overlays') or []),
                           'slots': [self._public_slot(s) for s in scene_slots]})
        tracks = {name: [] for name in TRACKS}
        for scene in scenes:
            base = {'scene_id': scene['scene_id'], 'start': scene['start'], 'end': scene['end']}
            for slot in scene['slots']:
                media=slot.get('selected_media') or {}; spec=((media.get('source_metadata') or {}).get('motion') or {})
                template=spec.get('template')
                item={**base,'start':slot['start'],'end':slot['end'],'slot_id':slot['slot_id'],'media':media or None,
                      'locked':slot.get('locked',False),'clip_start':slot.get('clip_start',0),'clip_end':slot.get('clip_end'),
                      'label':self._clip_label(media,template),'preview_url':f'/api/projects/{project_id}/production/stock/slots/{slot["slot_id"]}/preview'}
                if template in MAP_TEMPLATES: tracks['maps'].append({**item,'kind':'map','type':template,'motion_spec':spec})
                elif template in INFOGRAPHIC_TEMPLATES: tracks['infographics'].append({**item,'kind':'infographic','type':template,'motion_spec':spec})
                elif template in EMPHASIS_TEMPLATES: tracks['emphasis'].append({**item,'kind':'emphasis','type':template,'motion_spec':spec})
                elif template: tracks['layers'].append({**item,'kind':'layer','type':template,'motion_spec':spec})
                else: tracks['visuals'].append(item)
            motion = scene.get('motion') or ''
            if motion in ('map', 'route', 'schema') and not any(x.get('scene_id')==scene['scene_id'] and x.get('slot_id') for x in tracks['maps']): tracks['maps'].append({**base, 'type': motion})
            if motion in ('number', 'compare', 'card', 'chart', 'infographic') and not any(x.get('scene_id')==scene['scene_id'] and x.get('slot_id') for x in tracks['infographics']): tracks['infographics'].append({**base, 'type': motion})
            if scene.get('overlay_text'): tracks['layers'].append({**base, 'text': scene['overlay_text']})
            for overlay in scene['naman_overlays']:
                item={**base,**overlay}
                if overlay['kind']=='map': tracks['maps'].append(item)
                elif overlay['kind']=='infographic': tracks['infographics'].append(item)
                elif overlay['kind']=='emphasis': tracks['emphasis'].append(item)
                elif overlay['kind']=='layer': tracks['layers'].append(item)
        for cue in cues:
            tracks['subtitles'].append({'start': cue['start'], 'end': cue['end'], 'text': cue['text'], 'index': cue['index']})
            words = cue['text'].split()
            step = (cue['end'] - cue['start']) / max(1, len(words))
            tracks['emphasis'].extend({'start': cue['start'] + i * step, 'end': cue['start'] + (i + 1) * step,
                                       'text': word, 'timing': 'estimated'} for i, word in enumerate(words))
        if audio: tracks['audio'].append({'start': 0, 'end': float(audio.get('duration') or duration),
                                          'url': f'/api/projects/{project_id}/narration/versions/{subtitle_state["narration"]["id"]}/audio',
                                          'waveform_url':f'/api/projects/{project_id}/editor/waveform'})
        return {'brand': 'NAMAN', 'contract_version': 1, 'project_id': project_id, 'plan_id': plan['plan_id'],
                'revision': plan['revision'], 'stock_plan_id':stock.get('plan_id'), 'stock_revision':stock.get('revision'),
                'duration': timing.get('audio_duration') or duration, 'fps': 30, 'scenes': scenes, 'tracks': tracks,
                'track_order': list(TRACKS), 'audio_ready': bool(audio), 'subtitle_timing': subtitle_state.get('timing_source'),
                'stock_job':stock.get('job'),'subtitle_version_id':active_subtitles.get('id') or active_subtitles.get('version_id'),
                'audio_settings':self.audio_settings(project_id),
                'warnings': stock.get('warnings', []) + ([subtitle_state['message']] if subtitle_state.get('message') else [])}

    def waveform(self,project_id):
        subtitle_state=self.subtitles.view(project_id);audio=((subtitle_state.get('narration') or {}).get('metadata') or {}).get('audio') or {}
        return {'peaks':self._waveform(project_id,audio) or [],'source':'decoded_narration_pcm' if audio else 'no_active_narration'}

    @staticmethod
    def _public_slot(slot):
        media = deepcopy(slot.get('selected_media'))
        if media:
            for key in list(media):
                if key.endswith('_url') and key not in ('source_url',): media.pop(key, None)
        return {'slot_id': slot['slot_id'], 'scene_id': slot.get('scene_id'), 'start': slot.get('estimated_start', 0),
                'end': slot.get('estimated_end', 0), 'locked': bool(slot.get('locked')), 'status': slot.get('status'),
                'selected_media': media, 'clip_start': slot.get('segment_start') or 0,
                'clip_end':slot.get('segment_end')}

    @staticmethod
    def _clip_label(media, template=None):
        if template:
            from app.motion.templates import TEMPLATES
            return TEMPLATES.get(template,template)
        value=(media or {}).get('description') or (media or {}).get('title')
        return ' '.join(str(value).split())[:70] if value else ('Video' if (media or {}).get('media_type')=='video' else 'Görsel')

    @serialized
    def update_timeline(self, project_id, payload):
        required={'plan_id','revision','scene_id','slots'}
        if not isinstance(payload,dict) or set(payload)!=required or not isinstance(payload.get('slots'),list) or not payload['slots']:
            raise EditorError('invalid_timeline','Zaman çizelgesi değişikliklerini kontrol edin.')
        timing=self.subtitles.handoff(project_id)
        scene_time=next((s for s in timing.get('scenes',[]) if s['scene_id']==payload['scene_id']),None)
        if not scene_time: raise EditorError('stale_timing','Ses ve altyazı zamanlaması değişti. Sayfayı yenileyin.',409)
        handoff=self.stock._handoff(project_id)
        scene_source=next((s for s in handoff['scenes'] if s['scene_id']==payload['scene_id']),None)
        if not scene_source: raise EditorError('stale_timeline','Sahne planı değişti. Sayfayı yenileyin.',409)
        with closing(self.projects._connection()) as connection,connection:
            state=self.stock._ensure(connection,handoff);self.stock._stamp(state,payload);self.stock._idle(connection,project_id)
            plan=self._active(project_id);scene=next((b for b in plan['blocks'] if b['id']==payload['scene_id']),None)
            if not scene or scene.get('locked'): raise EditorError('locked','Kilitli sahnenin zamanlaması değiştirilemez.',409)
            current=[s for s in state['slots'] if s['scene_id']==payload['scene_id']]
            before=[deepcopy(s) for s in current]
            incoming=payload['slots']
            ids=[x.get('slot_id') for x in incoming]
            if len(ids)!=len(set(ids)) or set(ids)!={s['slot_id'] for s in current}:
                raise EditorError('stale_timeline','Sahne klipleri değişti. Sayfayı yenileyin.',409)
            cursor=float(scene_time['start']); prepared=[]
            for index,item in enumerate(incoming,1):
                if not isinstance(item,dict) or set(item)-{'slot_id','start','end','source_start','source_end'}:
                    raise EditorError('invalid_timeline','Klip alanlarını kontrol edin.')
                if not finite(item.get('start')) or not finite(item.get('end')):
                    raise EditorError('invalid_timeline','Klip başlangıç ve bitişi sayı olmalıdır.')
                start,end=round(item['start']*30)/30,round(item['end']*30)/30
                if abs(start-cursor)>.018 or end-start<1/30-.001:
                    raise EditorError('timeline_gap','Sahne içinde boşluk veya üst üste binme olamaz; komşu klip sınırını da taşıyın.')
                slot=next(s for s in current if s['slot_id']==item['slot_id'])
                if slot.get('locked'): raise EditorError('locked','Kilitli klip taşınamaz veya kesilemez.',409)
                media=slot.get('selected_media') or {};source_start=item.get('source_start',slot.get('segment_start') or 0)
                source_end=item.get('source_end',source_start+(end-start))
                if not finite(source_start) or not finite(source_end) or source_start<0 or source_end<=source_start:
                    raise EditorError('invalid_range','Kaynak klip aralığını kontrol edin.')
                if media.get('media_type')=='video' and (not finite(media.get('duration')) or source_end>media['duration']+.001 or source_end-source_start+.001<end-start):
                    raise EditorError('invalid_range','Kaynak video aralığı gösterim süresini karşılamalı ve dosya sınırında kalmalıdır.')
                prepared.append((slot,start,end,source_start,source_end,index));cursor=end
            if abs(cursor-float(scene_time['end']))>.018:
                raise EditorError('timeline_gap','Sahnenin görüntüleri seslendirme süresinin tamamını kapsamalıdır.')
            estimate_start=float(scene_source['start_estimate']);estimate_duration=float(scene_source['end_estimate'])-estimate_start
            actual_duration=float(scene_time['end'])-float(scene_time['start'])
            for slot,start,end,source_start,source_end,index in prepared:
                a=estimate_start+(start-float(scene_time['start']))/actual_duration*estimate_duration
                b=estimate_start+(end-float(scene_time['start']))/actual_duration*estimate_duration
                slot.update(order=index,duration=round(b-a,6),estimated_start=round(a,6),estimated_end=round(b,6),
                            segment_start=source_start,segment_end=source_end)
            self.stock._save(connection,state)
            after=[deepcopy(s) for s in state['slots'] if s['scene_id']==payload['scene_id']]
            connection.execute('INSERT INTO editor_revisions VALUES (?,?,?,?,?,?,?)',
                (uuid4().hex,project_id,state['plan_id'],state['plan_id'],'timeline_edit',json.dumps({'request':payload,'before':before,'after':after},ensure_ascii=False),now()))
        self.stock._mirror(state)
        return self.view(project_id)

    @serialized
    def timeline_history(self,project_id,direction,payload):
        if direction not in ('undo','redo') or not isinstance(payload,dict) or set(payload)!={'plan_id','revision'}:
            raise EditorError('invalid_timeline','Geri alma isteğini kontrol edin.')
        handoff=self.stock._handoff(project_id)
        with closing(self.projects._connection()) as connection,connection:
            state=self.stock._ensure(connection,handoff);self.stock._stamp(state,payload);self.stock._idle(connection,project_id)
            rows=connection.execute("SELECT id,kind,payload_json FROM editor_revisions WHERE project_id=? AND kind IN ('timeline_edit','timeline_undo','timeline_redo') ORDER BY created_at,id",(project_id,)).fetchall()
            done=[];undone=[];records={}
            for row in rows:
                try: record=json.loads(row['payload_json'])
                except (ValueError,TypeError): continue
                if row['kind']=='timeline_edit' and isinstance(record,dict) and 'before' in record and 'after' in record:
                    records[row['id']]=record;done.append(row['id']);undone.clear()
                elif row['kind']=='timeline_undo' and record.get('target') in done:
                    done.remove(record['target']);undone.append(record['target'])
                elif row['kind']=='timeline_redo' and record.get('target') in undone:
                    undone.remove(record['target']);done.append(record['target'])
            target=(done[-1] if direction=='undo' and done else undone[-1] if direction=='redo' and undone else None)
            if not target: raise EditorError('nothing_to_'+direction,'Bu yönde uygulanabilecek zaman çizelgesi değişikliği yok.',409)
            snapshot=records[target]['before' if direction=='undo' else 'after'];ids={s.get('slot_id') for s in snapshot}
            current={s['slot_id']:s for s in state['slots'] if s['slot_id'] in ids}
            if set(current)!=ids or any(s.get('locked') for s in current.values()):
                raise EditorError('stale_timeline','Klipler değişti veya kilitlendi; geçmiş uygulanamadı.',409)
            for saved in snapshot:
                slot=current[saved['slot_id']]
                for key in ('order','duration','estimated_start','estimated_end','segment_start','segment_end'):
                    if key in saved: slot[key]=deepcopy(saved[key])
                    else: slot.pop(key,None)
            self.stock._save(connection,state)
            connection.execute('INSERT INTO editor_revisions VALUES (?,?,?,?,?,?,?)',
                (uuid4().hex,project_id,state['plan_id'],state['plan_id'],'timeline_'+direction,json.dumps({'target':target},ensure_ascii=False),now()))
        self.stock._mirror(state)
        return self.view(project_id)

    def edit_motion(self, project_id, slot_id, payload):
        if not isinstance(payload,dict) or set(payload)!={'plan_id','revision','motion'}:
            raise EditorError('invalid_input','Animasyon düzenleme alanlarını kontrol edin.')
        return self.stock.start(project_id,{**payload,'action':'motion_edit'},slot_id=slot_id)

    @serialized
    def edit_clip(self,project_id,slot_id,payload):
        if not isinstance(payload,dict) or set(payload)-{'plan_id','revision','action','at','locked'} or set(payload)<{'plan_id','revision','action'}:
            raise EditorError('invalid_clip_edit','Klip işlemini kontrol edin.')
        action=payload['action']
        if action not in ('split','duplicate','lock'):
            raise EditorError('invalid_clip_edit','Desteklenmeyen klip işlemi.')
        handoff=self.stock._handoff(project_id);timing=self.subtitles.handoff(project_id)
        with closing(self.projects._connection()) as connection,connection:
            state=self.stock._ensure(connection,handoff);self.stock._stamp(state,payload);self.stock._idle(connection,project_id)
            slot=next((s for s in state['slots'] if s['slot_id']==slot_id),None)
            if not slot: raise EditorError('stale_timeline','Klip değişti. Sayfayı yenileyin.',409)
            plan=self._active(project_id);scene=next((s for s in plan['blocks'] if s['id']==slot['scene_id']),None)
            if not scene or scene.get('locked'): raise EditorError('locked','Kilitli sahne değiştirilemez.',409)
            before=[deepcopy(s) for s in state['slots'] if s['scene_id']==slot['scene_id']]
            if action=='lock':
                if type(payload.get('locked')) is not bool: raise EditorError('invalid_clip_edit','Kilit seçimini kontrol edin.')
                slot['locked']=payload['locked']
            else:
                if slot.get('locked'): raise EditorError('locked','Kilitli klip bölünemez veya çoğaltılamaz.',409)
                estimate_start=float(slot.get('estimated_start',0));estimate_end=float(slot.get('estimated_end',estimate_start+slot.get('duration',0)))
                if estimate_end-estimate_start<2/30: raise EditorError('clip_too_short','Klip bölmek için çok kısa.',409)
                scene_source=next((s for s in handoff['scenes'] if s['scene_id']==slot['scene_id']),None)
                scene_time=next((s for s in timing.get('scenes',[]) if s['scene_id']==slot['scene_id']),None)
                if not scene_source or not scene_time: raise EditorError('stale_timing','Ses zamanlaması değişti. Sayfayı yenileyin.',409)
                source_span=float(scene_source['end_estimate'])-float(scene_source['start_estimate']);actual_span=float(scene_time['end'])-float(scene_time['start'])
                actual_start=float(scene_time['start'])+(estimate_start-float(scene_source['start_estimate']))/source_span*actual_span
                actual_end=float(scene_time['start'])+(estimate_end-float(scene_source['start_estimate']))/source_span*actual_span
                if action=='split':
                    at=payload.get('at')
                    if not finite(at) or at<=actual_start+1/30-.001 or at>=actual_end-1/30+.001:
                        raise EditorError('invalid_split','Oynatma imleci seçili klibin içinde olmalıdır.')
                    fraction=(at-actual_start)/(actual_end-actual_start)
                else: fraction=.5
                boundary=estimate_start+(estimate_end-estimate_start)*fraction;copy=deepcopy(slot);copy['slot_id']=uuid4().hex
                old_source_start=float(slot.get('segment_start') or 0);old_source_end=slot.get('segment_end')
                if action=='split' and finite(old_source_end):
                    source_boundary=old_source_start+(float(old_source_end)-old_source_start)*fraction
                    slot['segment_end']=source_boundary;copy['segment_start']=source_boundary
                slot.update(duration=boundary-estimate_start,estimated_end=boundary)
                copy.update(duration=estimate_end-boundary,estimated_start=boundary,estimated_end=estimate_end,locked=False)
                index=state['slots'].index(slot);state['slots'].insert(index+1,copy)
                ordered=sorted((s for s in state['slots'] if s['scene_id']==slot['scene_id']),key=lambda s:(s.get('estimated_start',0),s.get('order',0)))
                for number,item in enumerate(ordered,1): item['order']=number
            self.stock._save(connection,state)
            after=[deepcopy(s) for s in state['slots'] if s['scene_id']==slot['scene_id']]
            connection.execute('INSERT INTO editor_revisions VALUES (?,?,?,?,?,?,?)',
                (uuid4().hex,project_id,state['plan_id'],state['plan_id'],'timeline_edit',json.dumps({'request':payload,'before':before,'after':after},ensure_ascii=False),now()))
        self.stock._mirror(state)
        return self.view(project_id)

    def archive(self, project_id):
        self.projects.get(project_id)
        with self.projects.lock, closing(self.projects._connection()) as connection:
            rows = connection.execute('SELECT * FROM stock_assets WHERE project_id=? ORDER BY provider,media_id',(project_id,)).fetchall()
            ranges = {(r['provider'], r['media_id']): dict(r) for r in connection.execute('SELECT * FROM media_clip_ranges WHERE project_id=?',(project_id,))}
        result=[];skipped=0
        for row in rows:
            try:
                meta=json.loads(row['metadata_json'])
                if not isinstance(meta,dict):raise ValueError('metadata')
                item={'provider':row['provider'],'media_id':row['media_id'],'media_type':row['media_type'],**meta}
                path=asset_path(self.projects,project_id,item)
                identity=item.get('sha256')
                if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9]{64}',identity):raise ValueError('identity')
            except Exception:
                skipped+=1
                continue
            rights=item.get('source_metadata') or {}
            saved=ranges.get((row['provider'],row['media_id']))
            result.append({'provider':row['provider'],'media_id':row['media_id'],'media_type':row['media_type'],
                           'sha256':identity,'duration':item.get('duration'),'source_url':item.get('source_url',''),
                           'title':item.get('title') or item.get('description') or row['media_id'],
                           'preview_url':f'/api/projects/{project_id}/editor/archive/{row["provider"]}/{row["media_id"]}/preview',
                           'rights':{k:rights.get(k) for k in ('license','license_url','author','page_url') if rights.get(k)},
                           'clip_range': {'start':saved['start_seconds'],'end':saved['end_seconds'],'revision':saved['revision']} if saved else None})
        return {'project_id':project_id,'items':result,'count':len(result),'skipped_count':skipped,
                'warning':f'{skipped} bozuk veya eksik arşiv kaydı atlandı.' if skipped else '',
                'reuse_policy':'Yerel hash eşleşirse yeniden indirilmez.'}

    @serialized
    def import_local(self, project_id, temporary, original_name):
        """Adopt a validated user-selected file into this project's immutable archive."""
        extension=Path(original_name).suffix.lower()
        formats={'.mp4':('video','video/mp4'),'.jpg':('image','image/jpeg'),'.jpeg':('image','image/jpeg'),
                 '.png':('image','image/png'),'.webp':('image','image/webp'),'.mp3':('audio','audio/mpeg'),
                 '.wav':('audio','audio/wav')}
        if extension not in formats:
            raise EditorError('unsupported_upload','MP4, JPG, PNG, WebP, MP3 veya WAV dosyası seçin.')
        media_type,mime=formats[extension]
        head=Path(temporary).read_bytes()[:16]
        valid=(mime=='video/mp4' and len(head)>=12 and head[4:8]==b'ftyp') or \
              (mime=='image/jpeg' and head.startswith(b'\xff\xd8\xff')) or \
              (mime=='image/png' and head.startswith(b'\x89PNG\r\n\x1a\n')) or \
              (mime=='image/webp' and head.startswith(b'RIFF') and head[8:12]==b'WEBP') or \
              (mime=='audio/wav' and head.startswith(b'RIFF') and head[8:12]==b'WAVE') or \
              (mime=='audio/mpeg' and (head.startswith(b'ID3') or (len(head)>1 and head[0]==0xff and head[1]&0xe0==0xe0)))
        if not valid: raise EditorError('invalid_upload','Dosya içeriği uzantısıyla eşleşmiyor.')
        digest=sha256_file(Path(temporary));media_id=digest[:32];canonical='.jpg' if extension=='.jpeg' else extension
        folder=Path(temporary).parent;target=folder/(media_id+canonical)
        if target.exists():
            if sha256_file(target)!=digest: raise EditorError('local_storage','Aynı adlı arşiv dosyası değişmiş.',409)
        else: os.replace(temporary,target)
        duration=None
        if media_type in ('video','audio'):
            try:
                from app.rendering.tools import discover
                probe=discover().get('ffprobe')
                done=subprocess.run([probe,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(target)],capture_output=True,text=True,timeout=20,stdin=subprocess.DEVNULL) if probe else None
                duration=float(done.stdout.strip()) if done and done.returncode==0 else None
            except (OSError,ValueError,subprocess.SubprocessError): duration=None
        metadata={'provider':'local','media_id':media_id,'media_type':media_type,'title':Path(original_name).stem[:160],
                  'description':Path(original_name).stem[:160],'local_path':'stock/'+target.name,'file_size':target.stat().st_size,
                  'sha256':digest,'content_type':mime,'duration':duration,'downloaded_at':now(),
                  'source_metadata':{'license':'Kullanıcı tarafından sağlandı','author':'Proje sahibi'}}
        with closing(self.projects._connection()) as connection,connection:
            self.projects._row(connection,project_id)
            connection.execute('INSERT OR REPLACE INTO stock_assets VALUES (?,?,?,?,?)',
                (project_id,'local',media_id,media_type,json.dumps(metadata,ensure_ascii=False)))
        return {'item':next(x for x in self.archive(project_id)['items'] if x['provider']=='local' and x['media_id']==media_id)}

    def set_range(self, project_id, provider, media_id, payload):
        if set(payload) != {'sha256','start','end','revision'} or not all(finite(payload[k]) for k in ('start','end','revision')):
            raise EditorError('invalid_range','Klip başlangıç, bitiş ve sürüm bilgilerini kontrol edin.')
        if payload['start'] < 0 or payload['end'] <= payload['start'] or type(payload['revision']) is not int:
            raise EditorError('invalid_range','Klip bitişi başlangıçtan sonra olmalıdır.')
        archive=next((x for x in self.archive(project_id)['items'] if x['provider']==provider and x['media_id']==media_id),None)
        if not archive or archive['sha256'] != payload['sha256']:
            raise EditorError('stale_media','Yerel medya değişti. Arşivi yenileyip tekrar deneyin.',409)
        path,_=self.archive_file(project_id,provider,media_id)
        if sha256_file(path)!=payload['sha256']:
            raise EditorError('stale_media','Yerel medya değişti. Arşivi yenileyip tekrar deneyin.',409)
        if finite(archive.get('duration')) and payload['end'] > archive['duration'] + .001:
            raise EditorError('invalid_range','Klip aralığı medya süresini aşamaz.')
        current=archive.get('clip_range');expected=current['revision'] if current else 0
        if payload['revision'] != expected: raise EditorError('stale_revision','Klip aralığı değişti. Sayfayı yenileyin.',409)
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            row = connection.execute('SELECT revision FROM media_clip_ranges WHERE project_id=? AND provider=? AND media_id=?',
                                     (project_id, provider, media_id)).fetchone()
            if payload['revision'] != (row[0] if row else 0):
                raise EditorError('stale_revision','Klip aralığı değişti. Sayfayı yenileyin.',409)
            connection.execute('''INSERT INTO media_clip_ranges VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,provider,media_id) DO UPDATE SET sha256=excluded.sha256,start_seconds=excluded.start_seconds,
                end_seconds=excluded.end_seconds,rights_json=excluded.rights_json,revision=excluded.revision,updated_at=excluded.updated_at''',
                (project_id,provider,media_id,payload['sha256'],payload['start'],payload['end'],json.dumps(archive['rights'],ensure_ascii=False),expected+1,now()))
        return next(x for x in self.archive(project_id)['items'] if x['provider']==provider and x['media_id']==media_id)

    def archive_file(self, project_id, provider, media_id):
        with self.projects.lock, closing(self.projects._connection()) as connection:
            self.projects._row(connection, project_id)
            row = connection.execute('SELECT media_type,metadata_json FROM stock_assets WHERE project_id=? AND provider=? AND media_id=?',
                                     (project_id, provider, media_id)).fetchone()
            if not row:
                raise EditorError('missing_media','Arşiv medyası bulunamadı.',404)
            item = {**json.loads(row['metadata_json']), 'provider':provider, 'media_id':media_id, 'media_type':row['media_type']}
            return asset_path(self.projects, project_id, item), item

    def assign(self, project_id, slot_id, payload):
        required = {'plan_id','revision','provider','media_id','sha256','start','end'}
        if set(payload) != required or not all(finite(payload[k]) for k in ('start','end')):
            raise EditorError('invalid_range','Medya ve klip aralığını kontrol edin.')
        if payload['start'] < 0 or payload['end'] <= payload['start']:
            raise EditorError('invalid_range','Klip bitişi başlangıçtan sonra olmalıdır.')
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            plan = self._active(project_id)
            state = self.stock._ensure(connection,self.stock._handoff(project_id))
            self.stock._stamp(state,payload)
            self.stock._idle(connection,project_id)
            slot = self.stock._slot(state,slot_id)
            scene = next(b for b in plan['blocks'] if b['id']==slot['scene_id'])
            if slot['locked'] or scene.get('locked'):
                raise EditorError('locked','Kilitli sahne veya medya değiştirilemez. Önce kilidi açın.',409)
            path, item = self.archive_file(project_id,payload['provider'],payload['media_id'])
            if sha256_file(path) != payload['sha256']:
                raise EditorError('stale_media','Yerel medya değişti. Arşivi yenileyin.',409)
            times = self.subtitles.handoff(project_id).get('stock_slots',[]) if hasattr(self.subtitles,'handoff') else []
            duration = next((s['duration'] for s in times if s['slot_id']==slot_id),slot['duration'])
            if item['media_type']=='video':
                if not finite(item.get('duration')) or payload['end'] > item['duration']+.001:
                    raise EditorError('invalid_range','Klip aralığı medya süresini aşamaz.')
                if payload['end']-payload['start']+.001 < duration:
                    raise EditorError('short_clip',f'Seçilen aralık en az {duration:.2f} saniye olmalıdır; sahne süresi korunur.')
            slot.update(selected_media=item,status='complete',segment_start=payload['start'] if item['media_type']=='video' else 0,
                        segment_end=payload['end'],message='Yerel arşivden atandı.',warnings=[])
            slot.pop('continuation_of',None)
            self.stock._save(connection,state)
        self.stock._mirror(state)
        return self.view(project_id)

    def revisions(self, project_id):
        self.projects.get(project_id)
        with self.projects.lock, closing(self.projects._connection()) as connection:
            rows = connection.execute('SELECT id FROM scene_plan_versions WHERE project_id=? ORDER BY rowid DESC',(project_id,)).fetchall()
        return {'items':[{'plan_id':r[0]} for r in rows]}

    def task_package(self, project_id):
        plan=self._active(project_id); project=self.projects.get(project_id)
        return {'schema':'naman.manual-plan.v1','instructions':['Yalnız verilen anlatımı kullanın; yeni olgusal iddia eklemeyin.','Kilitli sahneleri ve medyayı değiştirmeyin.'],
                'project':{'id':project_id,'name':project['name'],'topic':project['topic'],'language':project['language']},
                'base':{'plan_id':plan['plan_id'],'revision':plan['revision']},
                'required_sections':['sahneler','infografikler','harita_sahneleri','vurgular','katmanlar'],
                'narration':[{'scene_id':b['id'],'text':b['narration'],'locked':bool(b.get('locked'))} for b in plan['blocks']],
                'output_template':{'schema':'naman.manual-plan.v1','base':{'plan_id':plan['plan_id'],'revision':plan['revision']},
                                   'sahneler':[],'infografikler':[],'harita_sahneleri':[],'vurgular':[],'katmanlar':[]}}

    def task_package_zip(self,project_id):
        package=self.task_package(project_id);stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('NAMAN_GOREV_PAKETI.json',json.dumps(package,ensure_ascii=False,indent=2))
            archive.writestr('NAMAN_CIKTI_SABLONU.json',json.dumps(package['output_template'],ensure_ascii=False,indent=2))
            archive.writestr('OKU.txt','Görev paketini yapay zekâya verin. Dönen JSON yalnız NAMAN_CIKTI_SABLONU yapısında olmalıdır. NAMAN içinde Doğrula demeden plan uygulanmaz.\n')
        return stream.getvalue()

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
        choices = {'transition':{'none','hard_cut','crossfade','fade'},
                   'motion':{'none','slow_zoom','pan','ken_burns','overlay','emphasis_text'},
                   'composition':{'wide','medium','close','detail','person','object','environment','movement','graphic'}}
        for section in ('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar'):
            items=payload.get(section)
            if not isinstance(items,list): errors.append(f'{section} bir liste olmalıdır.'); continue
            for index,item in enumerate(items):
                if not isinstance(item,dict) or item.get('scene_id') not in known: errors.append(f'{section}[{index}] geçerli scene_id içermelidir.'); continue
                if known[item['scene_id']].get('locked') and len(item)>1: errors.append(f'{item["scene_id"]} kilitli; değiştirilemez.')
                allowed = ({'scene_id',*choices,'overlay_text'} if section=='sahneler' else
                           {'scene_id','template','data','emphasis'} if section in ('infografikler','harita_sahneleri') else
                           {'scene_id','text','effect'})
                if set(item)-allowed: errors.append(f'{section}[{index}] desteklenmeyen alan içeriyor.')
                if section=='sahneler':
                    for key, options in choices.items():
                        if key in item and (not isinstance(item[key],str) or item[key] not in options):
                            errors.append(f'{section}[{index}] {key} geçersiz.')
                    if 'overlay_text' in item and (not isinstance(item['overlay_text'],str) or len(item['overlay_text'])>150):
                        errors.append('Katman metni en fazla 150 karakter olmalıdır.')
                elif section in ('infografikler','harita_sahneleri'):
                    from app.motion.templates import validate, MotionError
                    try:
                        if section=='harita_sahneleri' and item.get('template')!='map': raise MotionError('map template')
                        if section=='infografikler' and item.get('template')=='map': raise MotionError('infographic template')
                        validate({k:v for k,v in item.items() if k!='scene_id'},known[item['scene_id']]['narration'],known[item['scene_id']].get('entities',[]))
                    except (MotionError,ValueError,TypeError,AttributeError):
                        errors.append(f'{section}[{index}] animasyon verisi veya anlatım eşleşmesi geçersiz.')
                else:
                    if not isinstance(item.get('text'),str) or not 1<=len(item['text'])<=150:
                        errors.append(f'{section}[{index}] kısa bir text alanı gerektirir.')
                    elif item['text'].casefold() not in known[item['scene_id']]['narration'].casefold():
                        errors.append(f'{section}[{index}] text sahne anlatımında aynen geçmelidir.')
                    if item.get('effect','pulse') not in ('pulse','glitch','none'):
                        errors.append(f'{section}[{index}] effect geçersiz.')
        diff=self._diff(plan,payload) if not errors else []
        correction='\n'.join(f'- {e}' for e in errors)
        return {'valid':not errors,'errors':errors,'correction_message':('JSON düzeltmeleri:\n'+correction) if errors else '',
                'base_plan_id':plan['plan_id'],'base_revision':plan['revision'],'changes':diff}

    def _diff(self, plan, payload):
        changes=[]
        for section,field in (('sahneler','scene'),('infografikler','infographic'),('harita_sahneleri','map'),('vurgular','emphasis'),('katmanlar','layer')):
            for item in payload.get(section,[]):
                if len(item)>1:
                    block=next(b for b in plan['blocks'] if b['id']==item['scene_id'])
                    before=({k:block.get(k) for k in item if k!='scene_id'} if field=='scene' else block.get('naman_overlays',[]))
                    changes.append({'scene_id':item['scene_id'],'kind':field,'before':before,'after':{k:v for k,v in item.items() if k!='scene_id'}})
        return changes

    @serialized
    def import_plan(self, project_id, payload):
        check=self.validate_import(project_id,payload)
        if not check['valid']: raise EditorError('invalid_import','JSON doğrulanamadı; hiçbir değişiklik kaydedilmedi.',422,check['errors'])
        plan=deepcopy(self._active(project_id)); by_id={b['id']:b for b in plan['blocks']}
        self.production.editable_plan(project_id,payload['base'])
        with closing(self.projects._connection()) as connection:
            self.stock._idle(connection,project_id)
        for item in payload['sahneler']:
            target=by_id[item['scene_id']]
            for src,dst in (('transition','transition'),('motion','motion'),('overlay_text','overlay_text'),('composition','composition')):
                if src in item: target[dst]=str(item[src])[:500]
        overlay_map={}
        for section,kind in (('infografikler','infographic'),('harita_sahneleri','map'),('vurgular','emphasis'),('katmanlar','layer')):
            for item in payload[section]: overlay_map.setdefault(item['scene_id'],[]).append({'kind':kind,**{k:v for k,v in item.items() if k!='scene_id'}})
        from app.motion.templates import validate as validate_motion, MotionError
        for scene_id,overlays in overlay_map.items():
            target=by_id[scene_id];target['naman_overlays']=overlays
            motion=next((o for o in overlays if o['kind'] in ('map','infographic') and o.get('template') and isinstance(o.get('data'),dict)),None)
            if motion:
                try: target['motion_spec']=validate_motion({'template':motion['template'],'data':motion['data'],'emphasis':motion.get('emphasis','')},target['narration'],target.get('entities') or [])
                except MotionError as error: raise EditorError('invalid_import',f'{scene_id} animasyonu anlatımla doğrulanamadı: {error}. Hiçbir değişiklik kaydedilmedi.') from None
            layer=next((o for o in overlays if o['kind']=='layer' and o.get('text')),None)
            if layer: target['overlay_text']=str(layer['text'])[:100]
        parent=plan['plan_id']; self.production._save(project_id,plan,new_version=True)
        with self.projects.lock,closing(self.projects._connection()) as connection,connection:
            connection.execute('INSERT INTO editor_revisions VALUES (?,?,?,?,?,?,?)',(uuid4().hex,project_id,plan['plan_id'],parent,'manual_import',json.dumps(payload,ensure_ascii=False),now()))
        return {'imported':True,'plan_id':plan['plan_id'],'revision':plan['revision'],'parent_plan_id':parent,'changes':check['changes']}

    @serialized
    def rollback(self, project_id, target_plan_id, payload):
        if set(payload)!={'confirm','plan_id','revision'} or payload['confirm'] is not True:
            raise EditorError('confirmation_required','Geri alma için açık onay ve güncel plan sürümü gereklidir.')
        active,_ = self.production.editable_plan(project_id,payload)
        with self.projects.lock,closing(self.projects._connection()) as connection:
            self.stock._idle(connection,project_id)
            row=connection.execute('SELECT plan_json FROM scene_plan_versions WHERE project_id=? AND id=?',(project_id,target_plan_id)).fetchone()
        if not row: raise EditorError('missing_revision','Plan sürümü bulunamadı.',404)
        target=json.loads(row[0]); copy=deepcopy(target); parent=self._active(project_id)['plan_id']
        if target['version_id']!=active['version_id']:
            raise EditorError('stale_source','Başka bir metin sürümünün planı geri alınamaz.',409)
        if any(b.get('locked') for b in active['blocks']) or any(s.get('locked') for s in self.stock.view(project_id)['slots']):
            raise EditorError('locked','Geri alma kilitli seçimleri etkileyebilir. Önce kilitleri gözden geçirin.',409)
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
        result={'enabled':True,'cached':False,'analysis_basis':'FFmpeg çekim geçişleri ve en fazla üç örnek kare; tam video Gemini’ye gönderilmez.',
                'clips':clips,'gemini_status':'disabled','message':'Gemini görsel kontrolü Ayarlar bölümünde kapalı; yerel çekim analizi kullanılabilir.'}
        if self.settings and self.settings.ai_visual_check():
            result.update(self._gemini_descriptions(project_id,provider,media_id,clips))
        with self.projects.lock,closing(self.projects._connection()) as connection,connection:
            connection.execute('INSERT INTO archive_analysis_cache VALUES (?,?,?,?,?)',(project_id,media['sha256'],ANALYZER_VERSION,json.dumps(result,ensure_ascii=False),now()))
        return result

    def video_review(self,project_id,payload):
        if payload!={'confirm':True} or type(payload.get('confirm')) is not bool:
            raise EditorError('confirmation_required','Gemini incelemesi için açık onay gereklidir.')
        if not self.rendering: raise EditorError('render_required','Render servisi kullanılamıyor.',409)
        if not self.settings or not self.settings.ai_visual_check():
            raise EditorError('gemini_disabled','Önce Ayarlar bölümünde Gemini görsel kontrolünü açın.',409)
        view=self.rendering.view(project_id);version=view.get('active')
        if not version or version.get('status')!='completed' or version.get('video_missing'):
            raise EditorError('render_required','Önce tamamlanmış videoyu aktif seçin.',409)
        path=self.rendering.export(project_id,version['id']);identity=sha256_file(path)
        with self.projects.lock,closing(self.projects._connection()) as connection:
            cached=connection.execute('SELECT result_json FROM archive_analysis_cache WHERE project_id=? AND sha256=? AND analyzer_version=?',(project_id,identity,VIDEO_REVIEW_VERSION)).fetchone()
        if cached:return {**json.loads(cached[0]),'cached':True}
        duration=float(version.get('metadata',{}).get('duration') or self.view(project_id)['duration'] or 0)
        samples=[round(duration*i/9,3) for i in range(1,9)] if duration>0 else []
        images=[]
        for at in samples:
            try:
                frame=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-ss',str(at),'-i',str(path),'-frames:v','1','-vf','scale=640:-2','-q:v','6','-f','image2pipe','-vcodec','mjpeg','-'],capture_output=True,timeout=20,check=False).stdout
            except (OSError,subprocess.TimeoutExpired):frame=b''
            if frame and len(frame)<=2_000_000:images.append({'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':base64.b64encode(frame).decode()},'timecode':at})
        if not images: raise EditorError('frame_error','Bitmiş videodan örnek kare çıkarılamadı.',409)
        editor=self.view(project_id);context={'sampling_notice':f'Videonun tamamı değil, {len(images)} örnek kare inceleniyor.',
                 'samples':[x['timecode'] for x in images],'subtitles':editor['tracks']['subtitles'],
                 'scenes':[{k:s[k] for k in ('scene_id','start','end','narration')} for s in editor['scenes']]}
        schema={'type':'object','required':['summary','issues'],'properties':{'summary':{'type':'string'},'issues':{'type':'array','items':{'type':'object','required':['timecode','category','message','severity'],'properties':{'timecode':{'type':'number'},'category':{'type':'string'},'message':{'type':'string'},'severity':{'type':'string'}}}}}}
        try:
            from app.providers.factory import make_script_provider
            ai=make_script_provider('gemini',self.settings,chain=False)
            answer=ai.complete_json('finished_video_sample_review','Yalnız verilen örnek kareleri ve zaman verisini değerlendir. Her karenin incelendiğini iddia etme. Yanlış medya, harita, taşan yazı, altyazı zamanı, tekrar ve aşırı motion sorunlarını Türkçe raporla.\n'+json.dumps(context,ensure_ascii=False),schema,images=[{k:v for k,v in image.items() if k!='timecode'} for image in images],max_tokens=900,timeout=45)
            if not isinstance(answer.get('summary'),str) or not isinstance(answer.get('issues'),list):raise ValueError('review')
        except Exception as error:
            from app.providers.base import ScriptProviderError
            if isinstance(error,(ScriptProviderError,ValueError,OSError)):
                raise EditorError('gemini_unavailable','Gemini video incelemesi tamamlanamadı; video ve render korunuyor.',503) from None
            raise
        result={'cached':False,'basis':context['sampling_notice'],'sample_timecodes':context['samples'],'summary':' '.join(answer['summary'].split())[:1000],
                'issues':answer['issues'][:100],'render_version_id':version['id']}
        with self.projects.lock,closing(self.projects._connection()) as connection,connection:
            connection.execute('INSERT INTO archive_analysis_cache VALUES (?,?,?,?,?)',(project_id,identity,VIDEO_REVIEW_VERSION,json.dumps(result,ensure_ascii=False),now()))
        return result

    def _gemini_descriptions(self, project_id, provider, media_id, clips):
        """One opt-in request, max three compressed frames; failure keeps local analysis usable."""
        if not clips:
            return {'gemini_status':'skipped','message':'Analiz edilecek video karesi bulunamadı.'}
        path,_ = self.archive_file(project_id,provider,media_id)
        images=[]
        for clip in clips[:3]:
            command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-ss',str(clip['sample_at']),'-i',str(path),
                     '-frames:v','1','-vf','scale=640:-2','-q:v','5','-f','image2pipe','-vcodec','mjpeg','-']
            try:
                frame=subprocess.run(command,capture_output=True,timeout=20,check=False).stdout
            except (OSError,subprocess.TimeoutExpired):
                frame=b''
            if frame and len(frame)<=2_000_000:
                images.append({'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':base64.b64encode(frame).decode()}})
        if not images:
            return {'gemini_status':'frame_error','message':'Örnek kareler çıkarılamadı; yerel çekim sınırları korundu.'}
        schema={'type':'object','required':['descriptions'],'properties':{'descriptions':{'type':'array','items':{'type':'string'}}}}
        try:
            from app.providers.factory import make_script_provider
            ai=make_script_provider('gemini',self.settings,chain=False)
            answer=ai.complete_json('archive_frame_analysis',
                'Her kareyi sırayla, yalnız görünür olgularla, Türkçe ve en fazla 20 kelimeyle açıkla. Kimlik tahmini yapma.',
                schema,images=images,max_tokens=240,timeout=25)
            descriptions=answer.get('descriptions')
            if not isinstance(descriptions,list) or len(descriptions)!=len(images) or any(not isinstance(x,str) or not x.strip() for x in descriptions):
                raise ValueError('descriptions')
            updated=deepcopy(clips)
            for clip,description in zip(updated,descriptions):
                clip.update(description=' '.join(description.split())[:240],source='gemini_sample_frame')
            return {'clips':updated,'gemini_status':'complete','message':'Gemini örnek kare açıklamaları önbelleğe kaydedildi.'}
        except Exception as error:
            from app.providers.base import ScriptProviderError
            if not isinstance(error,(ScriptProviderError,ValueError,OSError)):
                raise
            return {'gemini_status':'unavailable','message':'Gemini analizi tamamlanamadı; yerel çekim sınırları kullanılmaya devam ediyor.'}

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
