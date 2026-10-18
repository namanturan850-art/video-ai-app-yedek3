"""On-demand four-second Program proxies. No archive-wide/full-film rendering.

One background encoder, two decoder limit shared with still previews. Identity
contains only intersecting timeline content and verified source digests, so an
edit outside the window does not invalidate an otherwise reusable segment.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from threading import RLock
from uuid import uuid4

from app.editor.advanced import Document
from app.editor.models import EditorError
from app.editor.previews import cache_folder,run
from app.projects import linked

_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='program-proxy')
_lock=RLock()
_jobs={}
_results={}
_sources={}
SIZES={'low':(320,180),'medium':(640,360),'high':(960,540),'auto':(640,360)}


def restrict(clip,start,end):
    """Exact restriction of an animation's original domain, also used by split."""
    result=deepcopy(clip);a=max(start,clip['start']);b=min(end,clip['end']);offset=a-clip['start']
    result.update(start=a-start,end=b-start,animation_duration=clip.get('animation_duration') or clip['end']-clip['start'],
                  animation_offset=clip.get('animation_offset',0)+offset)
    result['source_start']=clip.get('source_start',0)+offset*clip['transform']['speed']
    return result


def snapshot(editor,advanced,pid,time,quality):
    from app.editor.compositor import resolve
    from app.editor.service import sha256_file
    from app.stock.download import asset_path
    from app.narration.audio import audio_path
    if quality not in SIZES or not math.isfinite(time):raise EditorError('invalid_proxy','Önizleme kalitesini ve zamanı kontrol edin.')
    with editor.projects.lock:
        view=editor.view(pid);state=advanced.get(pid);original=Document.model_validate(state['document']).model_dump()
        if not 0<=time<view['duration']:raise EditorError('invalid_time','Önizleme zamanı anlatım içinde olmalıdır.')
        start=math.floor(time/4)*4;end=min(view['duration'],start+4);duration=end-start
        # Keep unsupported graphs truthful, rather than displaying a smooth but
        # visually different version of saved transitions/legacy decorations.
        if original['transitions'] or view.get('editorial',{}).get('legacy_decorations'):
            raise EditorError('proxy_fallback','Geçiş/eski plan süslemesi için gerçek örnek kare modu kullanılıyor.')
        doc=Document().model_dump();doc['clips']=[restrict(c,start,end) for c in original['clips'] if c['visible'] and c['start']<end and c['end']>start]
        if any(c['kind']=='motion' for c in doc['clips']):raise EditorError('proxy_fallback','Yerel motion için gerçek örnek kare modu kullanılıyor; uzun motion videosu otomatik oluşturulmaz.')
        verifier=getattr(getattr(editor.stock,'downloader',None),'verified_hash',None)
        assets=resolve(editor.projects,pid,doc,editor.archive_file,verify=verifier)
        bases=[];hashes=[];slots={};verified_sources=[(str(a['path']),a['sha256']) for a in assets.values() if a.get('sha256')];offsets={a['slot_id']:a for a in original['adjustments']}
        for slot in sorted((x for values in view['tracks'].values() for x in values if x.get('slot_id') and x['start']<end and x['end']>start),key=lambda s:s['start']):
            local={**slot,'start':max(start,slot['start'])-start,'end':min(end,slot['end'])-start};sid=slot['slot_id'];slots[sid]=local
            adjustment=offsets.get(sid);speed=(adjustment or {}).get('transform',{}).get('speed',1)
            cut=(slot.get('clip_start') or 0)+(max(start,slot['start'])-slot['start'])*speed
            path=None;kind='empty'
            if slot.get('media'):
                path=asset_path(editor.projects,pid,slot['media']);expected=slot['media'].get('sha256');digest=verifier(path,expected) if verifier and expected else sha256_file(path)
                if expected and digest!=expected:raise EditorError('stale_media','Proxy kaynağı değişmiş; arşivi kontrol edin.',409)
                hashes.append(digest);verified_sources.append((str(path),digest));kind=slot['media']['media_type']
            bases.append({'start':local['start'],'end':local['end'],'path':path,'type':kind,'cut':cut,'speed':speed})
            if adjustment:
                edit=restrict({**adjustment,'start':slot['start'],'end':slot['end']},start,end)
                doc['adjustments'].append({k:v for k,v in edit.items() if k not in ('start','end','source_start')})
                if path:assets[sid]={'path':path,'type':kind,'has_audio':slot['media'].get('has_audio',False),'segment_start':cut}
        subtitles=editor.subtitles.view(pid);audio=(subtitles.get('narration') or {}).get('metadata',{}).get('audio');narration=None
        if audio:
            narration=audio_path(editor.projects,pid,audio);digest=verifier(narration,audio.get('sha256')) if verifier else sha256_file(narration)
            if digest!=audio.get('sha256'):raise EditorError('stale_media','Anlatım kaynağı değişmiş.',409)
            hashes.append(digest);verified_sources.append((str(narration),digest))
        preferences=view.get('editorial',{});display=preferences.get('subtitle_display','full')
        cues=[{**q,'start':max(start,q['start'])-start,'end':min(end,q['end'])-start} for q in (subtitles.get('active') or {}).get('cues',[]) if q['start']<end and q['end']>start and display!='none' and (display!='emphasis' or q['index'] in preferences.get('important_cues',[]))]
        mix=editor.audio_settings(pid)
        data={'version':1,'document':doc,'bases':bases,'hashes':hashes,'assets':assets,'cues':cues,'mix':mix,'size':SIZES[quality],
              'verified_sources':verified_sources,'start':start,'duration':duration,'narration':narration,'full_duration':view['duration'],'slots':slots}
        key=hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()
        return key,data,state['revision']


def request(editor,advanced,pid,time,quality='auto'):
    key,data,revision=snapshot(editor,advanced,pid,time,quality);folder=cache_folder(editor,pid);target=folder/f'proxy-v1-{key}.mp4'
    result={'key':key,'start':data['start'],'duration':data['duration'],'revision':revision,'width':data['size'][0],'height':data['size'][1],
            'encoded_fps':30,'mode':'local_proxy','audio':'Yerel FFmpeg miks: aynı ducking/eğriler; kısa pencere loudnorm ve compressor başlangıcı finalden farklı olabilir.',
            'url':f'/api/projects/{pid}/editor/advanced/program-proxy/{key}',
            'status_url':f'/api/projects/{pid}/editor/advanced/program-proxy-status/{key}'}
    token=(str(folder),key)
    with _lock:
        _results[token]=result
        _sources[token]=data
        for old in list(_results)[:-96]:
            if old not in _jobs or _jobs[old].done():_results.pop(old,None);_sources.pop(old,None)
    if target.is_file() and not linked(target):return {**result,'status':'ready','cache_hit':True}
    token=(str(folder),key)
    with _lock:
        job=_jobs.get(token)
        if job and job.done():
            try:job.result()
            except Exception:raise EditorError('proxy_fallback','Proxy bu kaliteyle hazırlanamadı; örnek kare moduna geçildi. Daha düşük kaliteyi deneyin.') from None
            return {**result,'status':'ready','cache_hit':False}
        if job is None:
            # Drop completed futures; never accumulate a queue while scrubbing.
            for old in [k for k,v in _jobs.items() if v.done()]:_jobs.pop(old,None)
            if sum(not v.done() for v in _jobs.values())>=2:raise EditorError('preview_busy','Önizleme hazırlanıyor; şimdilik örnek kare modu kullanılıyor.',503)
            _jobs[token]=_executor.submit(build,folder,target,data)
    return {**result,'status':'preparing','cache_hit':False}


def file(editor,pid,key):
    import re
    if not re.fullmatch('[a-f0-9]{64}',key):raise EditorError('invalid_proxy','Önizleme kimliği geçersiz.',404)
    path=cache_folder(editor,pid)/f'proxy-v1-{key}.mp4'
    if not path.is_file() or linked(path):raise EditorError('proxy_missing','Önizleme henüz hazır değil.',404)
    token=(str(path.parent),key)
    with _lock:data=_sources.get(token)
    if data is None:raise EditorError('proxy_missing','Önce güncel kurgu için önizleme isteyin.',404)
    from app.editor.service import sha256_file
    verifier=getattr(getattr(editor.stock,'downloader',None),'verified_hash',None)
    for source,digest in data.get('verified_sources',[]):
        if (verifier(Path(source),digest) if verifier else sha256_file(Path(source)))!=digest:raise EditorError('stale_media','Önizleme kaynağı değişmiş; önizlemeyi yenileyin.',409)
    return path


def status(editor,pid,key):
    import re
    if not re.fullmatch('[a-f0-9]{64}',key):raise EditorError('invalid_proxy','Önizleme kimliği geçersiz.',404)
    token=(str(cache_folder(editor,pid)),key)
    with _lock:result=_results.get(token);job=_jobs.get(token)
    if result is None:raise EditorError('proxy_missing','Önizlemeyi yeniden isteyin.',404)
    if job and job.done():
        try:job.result()
        except Exception:raise EditorError('proxy_fallback','Proxy hazırlanamadı; daha düşük kaliteyi veya örnek kare modunu kullanın.') from None
    ready=(cache_folder(editor,pid)/f'proxy-v1-{key}.mp4').is_file()
    return {**result,'status':'ready' if ready else 'preparing','cache_hit':ready}


def build(folder,target,data):
    from app.editor.compositor import compile_graph
    from app.rendering.tools import discover
    from app.rendering.engine import LOUDNESS
    from app.rendering import ass
    ffmpeg=discover()['ffmpeg'];width,height=data['size'];duration=data['duration'];temporary=folder/('proxy-work-'+uuid4().hex);temporary.mkdir()
    args=[ffmpeg,'-v','error','-y','-filter_complex_threads','1','-filter_threads','1','-threads','1']
    graphs=[];inputs=[];cursor=0
    def base(part,index):
        nonlocal cursor
        length=part['end']-part['start']
        if length<=0:return
        label=f'base{index}';n=args.count('-i')
        if part['path']:
            if part['type']=='image':args.extend(['-loop','1','-framerate','30'])
            else:args.extend(['-stream_loop','-1','-ss',str(part['cut'])])
            args.extend(['-t',str(length*part['speed']+.1),'-i',str(part['path'])])
            graphs.append(f'[{n}:v]setpts=(PTS-STARTPTS)/{part["speed"]},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30,trim=duration={length},setpts=PTS-STARTPTS,format=yuv420p[{label}]')
        else:
            args.extend(['-f','lavfi','-i',f'color=c=black:s={width}x{height}:r=30:d={length}']);graphs.append(f'[{n}:v]null[{label}]')
        inputs.append(label);cursor=part['end']
    for part in data['bases']:
        if part['start']>cursor+.001:base({'start':cursor,'end':part['start'],'path':None},len(inputs))
        base(part,len(inputs))
    if cursor<duration-.001:base({'start':cursor,'end':duration,'path':None},len(inputs))
    graphs.append(''.join(f'[{x}]' for x in inputs)+(f'concat=n={len(inputs)}:v=1:a=0' if len(inputs)>1 else 'null')+'[base]')
    narration=temporary/'narration.wav'
    try:
        if data['narration']:
            run([ffmpeg,'-v','error','-y','-ss',str(data['start']),'-i',str(data['narration']),'-t',str(duration),'-ar','48000','-ac','2',str(narration)])
        else:run([ffmpeg,'-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(duration),str(narration)])
        graph,label,audio=compile_graph(args,data['document'],data['assets'],base='base',folder=temporary,duration=duration,width=width,height=height,adjustment_slots=data['slots'],narration=narration)
        if graph:graphs.append(graph)
        content,_,has_text=ass.create(data['cues'],[],duration,subtitles=bool(data['cues']),overlays=False)
        if has_text:
            # ASS PlayRes is the final 1080p plane; libass scales to proxy size.
            (temporary/'captions.ass').write_text(content,encoding='utf-8')
            caption=str(temporary/'captions.ass').replace('\\','/').replace(':',r'\:').replace("'",r"\'")
            graphs.append(f"[{label}]ass=filename='{caption}'[captioned]");label='captioned'
        index=args.count('-i');args+=['-i',str(narration)];mix=data['mix'];gain=mix.get('narration_volume',1)
        voice=f'[{index}:a]aresample=48000,apad,atrim=duration={duration},asetpts=PTS-STARTPTS,volume={gain}'
        fi=mix.get('narration_fade_in',0);fo=mix.get('narration_fade_out',0);start=data['start']
        if fi:voice+=f",volume='min(1,(t+{start})/{fi})':eval=frame"
        if fo:voice+=f",volume='max(0,min(1,({data['full_duration']}-t-{start})/{fo}))':eval=frame"
        graphs.append(voice+','+LOUDNESS+'[master]')
        graphs.append('[master]'+''.join(f'[{a}]' for a in audio)+(f'amix=inputs={len(audio)+1}:duration=first:normalize=0,alimiter=limit=0.84:level=false' if audio else 'anull')+'[audio]')
        script=temporary/'graph.txt';script.write_text(';\n'.join(graphs),encoding='utf-8')
        output=temporary/'preview.mp4'
        args+=['-filter_complex_script',str(script),'-map',f'[{label}]','-map','[audio]','-c:v','libx264','-preset','ultrafast','-crf','26','-pix_fmt','yuv420p','-r','30','-frames:v',str(round(duration*30)),'-threads','1','-c:a','aac','-ar','48000','-ac','2','-t',str(duration),'-movflags','+faststart',str(output)]
        run(args)
        if not output.is_file() or output.stat().st_size<100:raise EditorError('preview_failed','Proxy dosyası üretilemedi.')
        os.replace(output,target)
        cached=sorted(folder.glob('proxy-v1-*.mp4'),key=lambda p:p.stat().st_mtime)
        for stale in cached[:-48]:
            if not linked(stale):stale.unlink(missing_ok=True)
    finally:shutil.rmtree(temporary,ignore_errors=True)
