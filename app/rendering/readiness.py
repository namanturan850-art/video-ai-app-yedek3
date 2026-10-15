"""Read-only, safe blockers; a preview never licenses an incomplete render."""
from contextlib import closing
from copy import deepcopy
import json
from app.scripts.models import ScriptError
from app.narration.audio import audio_path
from app.narration.models import script_fingerprint
from app.stock.download import asset_path
from app.rendering import smart_edit,timeline


def inspect(service,pid,tool,source,error,engine_status=None):
    r={'ready':False,'narration_ready':False,'subtitles_ready':False,'ffmpeg_ready':bool(tool['found']),
       'stock_ready':False,'unresolved_stock_slots':0,'stale_stock_slots':0,'missing_files':0,'blockers':[],'quality_warnings':[]}
    def block(code,message,screen):r['blockers'].append({'code':code,'message':message,'screen':screen})
    h=service.subtitles.handoff(pid)
    with closing(service.projects._connection()) as c:
        row=c.execute('SELECT active_version_id FROM narration_state WHERE project_id=?',(pid,)).fetchone()
        if row and row[0]:
            try:
                voice=service.subtitles.narration._version(c,pid,row[0])
                approved=service.subtitles.narration._approved(pid)
                if (voice['metadata']['status']=='completed' and approved['id']==voice['source_script_version_id']
                        and script_fingerprint(approved['text'])==voice['metadata']['script_fingerprint']):
                    path=audio_path(service.projects,pid,voice['metadata']['audio'])
                    r['narration_ready']=service._hash(path)==voice['metadata']['audio']['sha256']
            except (ScriptError,OSError,KeyError,TypeError):pass
        active=c.execute('SELECT active_version_id FROM subtitle_state WHERE project_id=?',(pid,)).fetchone()
        r['subtitles_ready']=bool(active and active[0] and service.subtitles.pipeline_status(pid)=='Hazır')
        try:p=service.production.handoff(pid)
        except ScriptError:p=None
        row=c.execute('SELECT source_version_id,state_json FROM stock_plans WHERE project_id=? AND plan_id=?',(pid,p['plan_id'])).fetchone() if p else None
        state=json.loads(row['state_json']) if row else None
        if state:
            from app.stock.service import fingerprint
            slots=state['slots'];stale=not p or row['source_version_id']!=p['source_script_version_id'] or bool(state.get('handoff_fingerprint') and state['handoff_fingerprint']!=fingerprint(p))
            if stale:r['stale_stock_slots']=len(slots)
            for slot in slots:
                m=slot.get('selected_media')
                if not m or slot['status']!='complete':r['unresolved_stock_slots']+=1;continue
                proof=slot.get('local_validation') or {}
                if proof.get('accepted') is False:
                    block('quality_rejected','Bir medyanın kalite kontrolü başarısız. Medya ekranında bu yuvayı kontrol edin.','production')
                if m.get('provider')!='generated' and (m.get('width',0)<1280 or m.get('height',0)<720 or m.get('width',0)<=m.get('height',0)):
                    r['quality_warnings'].append({'slot_id':slot['slot_id'],'message':'Mevcut seçim yatay HD standardının altında; seçim korundu.'})
                try:asset_path(service.projects,pid,m)
                except (ScriptError,OSError):r['missing_files']+=1
            r['stock_ready']=bool(slots and not stale and not r['unresolved_stock_slots'] and not r['missing_files'])
    if not r['narration_ready']:block('narration_missing','Seslendirme eksik veya güncel değil.','narration')
    if not r['subtitles_ready']:block('subtitle_stale' if active and active[0] else 'subtitle_missing','Aktif altyazı/zamanlama güncel değil.' if active and active[0] else 'Altyazı ve zamanlama eksik.','subtitles')
    if not state:block('stock_stale','Stok planı henüz hazır değil veya güncel değil.','production')
    elif r['stale_stock_slots']:block('stock_stale','Stok planı güncel değil.','production')
    if r['unresolved_stock_slots']:block('stock_unresolved',f"{r['unresolved_stock_slots']} medya yuvasında uygun medya yok.",'production')
    if r['missing_files']:block('media_file_missing',f"{r['missing_files']} yerel medya dosyası eksik veya değişmiş.",'production')
    if not r['ffmpeg_ready']:block('ffmpeg_missing','FFmpeg bulunamadı. Ayarlar ekranında Durumu Yenile ile kontrol edin.','settings')
    if engine_status and not engine_status['ready']:block('openmontage_missing',engine_status['message'],'settings')
    if not source and not r['blockers']:block(getattr(error,'category','source_stale'),str(error) if error else 'Video kaynakları güncel değil.','production')
    r['ready']=bool(source and not r['blockers']);return r,h,p


def estimated_plan(h,p,opts):
    if not p or not h.get('scenes') or not h.get('stock_slots'):return None
    projected=deepcopy(h);projected['ready']=True
    for s in projected['stock_slots']:
        s['status']='complete'
        s['selected_media_local_identity']=s.get('selected_media_local_identity') or {'media_type':'video'}
    try:
        t=timeline.build(projected,p)
        seed=opts.get('edit_variation_seed') or smart_edit.digest(h)[:16]
        plan=smart_edit.build(t,h,opts['editing_style'],smart_edit.digest(h),seed=seed,subtitle_mode=opts.get('subtitle_display') or 'full')
        plan['estimated']=True;plan['fingerprint']=smart_edit.digest({k:v for k,v in plan.items() if k!='fingerprint'});return plan
    except (ScriptError,ValueError,KeyError,TypeError):return None
