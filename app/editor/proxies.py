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
import subprocess
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
SIZES={'low':(320,180),'medium':(640,360),'high':(1280,720),'full':(1920,1080),'auto':(1280,720)}


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
        if view.get('editorial',{}).get('legacy_decorations'):
            raise EditorError('proxy_fallback','Geçiş/eski plan süslemesi için gerçek örnek kare modu kullanılıyor.')
        doc=Document().model_dump();doc['clips']=[restrict(c,start,end) for c in original['clips'] if c['visible'] and c['start']<end and c['end']>start]
        if len(doc['clips'])>32 or sum(c['kind']=='media' for c in doc['clips'])>8:raise EditorError('proxy_fallback','Bu aralıkta çok sayıda katman var; çözücü/bellek sınırı için örnek kare modu kullanılıyor.')
        verifier=getattr(getattr(editor.stock,'downloader',None),'verified_hash',None)
        assets=resolve(editor.projects,pid,doc,editor.archive_file,verify=verifier)
        bases=[];hashes=[];slots={};verified_sources=[(str(a['path']),a['sha256']) for a in assets.values() if a.get('sha256')];offsets={a['slot_id']:a for a in original['adjustments']}
        for slot in sorted((x for values in view['tracks'].values() for x in values if x.get('slot_id') and x['start']<end and x['end']>start),key=lambda s:s['start']):
            local={**slot,'start':round(max(start,slot['start'])*30)/30-start,'end':round(min(end,slot['end'])*30)/30-start};sid=slot['slot_id'];slots[sid]=local
            adjustment=offsets.get(sid);speed=(adjustment or {}).get('transform',{}).get('speed',1)
            cut=(slot.get('clip_start') or 0)+(round(max(start,slot['start'])*30)-round(slot['start']*30))/30*speed
            path=None;kind='empty'
            if slot.get('media'):
                path=asset_path(editor.projects,pid,slot['media']);expected=slot['media'].get('sha256');digest=verifier(path,expected) if verifier and expected else sha256_file(path)
                if expected and digest!=expected:raise EditorError('stale_media','Proxy kaynağı değişmiş; arşivi kontrol edin.',409)
                hashes.append(digest);verified_sources.append((str(path),digest));kind=slot['media']['media_type']
                if kind=='video':
                    from app.rendering.source_timing import editor_coverage
                    from app.rendering.tools import discover
                    tail=next((t['duration'] for t in original['transitions'] if t['slot_id']==sid and t['kind'] in ('cross_dissolve','wipe')),0.)
                    editor_coverage(path,discover().get('ffprobe'),slot.get('clip_start') or 0,slot.get('clip_end'),speed,
                                    (round(slot['end']*30)-round(slot['start']*30))/30+tail,
                                    f"Sahne {slot['scene_id']}, {slot['start']:.3f} sn ({sid})")
            bases.append({'start':local['start'],'end':local['end'],'path':path,'type':kind,'cut':cut,'source_end':slot.get('clip_end'),'speed':speed,'slot_id':sid,'original_start':round(slot['start']*30)/30-start,'original_end':round(slot['end']*30)/30-start})
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
        channels=getattr(getattr(editor,'rendering',None),'channels',None)
        kit=channels.for_project(pid)['style'] if channels else {}
        subtitle_style={**(kit.get('subtitle') or {}),'word_highlight':preferences.get('word_highlight',False)}
        cues=[deepcopy(q) for q in (subtitles.get('active') or {}).get('cues',[]) if q['start']<end and q['end']>start and display!='none' and (display!='emphasis' or q['index'] in preferences.get('important_cues',[]))]
        mix=editor.audio_settings(pid)
        base_ids={s['slot_id'] for s in bases}
        transitions=[t for t in original['transitions'] if t['slot_id'] in base_ids or t['next_slot_id'] in base_ids]
        transition_ids={t['slot_id'] for t in transitions}
        data={'version':7,'subtitle_style':subtitle_style,'document':doc,'bases':bases,'hashes':hashes,'assets':assets,'cues':cues,'mix':mix,'size':SIZES[quality],
              'original_adjustments':[a for a in original['adjustments'] if a['slot_id'] in transition_ids],'transitions':transitions,'all_slots':[{**x,'start':round(x['start']*30)/30,'end':round(x['end']*30)/30} for values in view['tracks'].values() for x in values if x.get('slot_id') in transition_ids], 'kit':kit,'language':editor.projects.get(pid).get('language','de'), 'motion_folder':str(editor.projects._path(pid)/'stock'), 'verified_sources':verified_sources,'start':start,'duration':duration,'narration':narration,'full_duration':view['duration'],'slots':slots}
        for transition in original['transitions']:
            for slot in data['all_slots']:
                if slot['slot_id']==transition['slot_id'] and slot.get('media'):
                    path=asset_path(editor.projects,pid,slot['media']);expected=slot['media'].get('sha256')
                    digest=verifier(path,expected) if verifier and expected else sha256_file(path)
                    if expected and expected!=digest:raise EditorError('stale_media','Geçiş kaynağı değişmiş.',409)
                    verified_sources.append((str(path),digest))
                    slot['proxy_path']=str(path)
                    if slot['media']['media_type']=='video':
                        from app.rendering.source_timing import editor_coverage
                        from app.rendering.tools import discover
                        speed=next((a['transform']['speed'] for a in original['adjustments'] if a['slot_id']==slot['slot_id']),1.)
                        editor_coverage(path,discover().get('ffprobe'),slot.get('clip_start') or 0,slot.get('clip_end'),speed,
                                        (round(slot['end']*30)-round(slot['start']*30))/30+(transition['duration'] if transition['kind'] in ('cross_dissolve','wipe') else 0.),
                                        f"Sahne {slot['scene_id']}, {slot['end']:.3f} sn ({slot['slot_id']})")
        from app.editor.proxy_audio import snapshot as audio_snapshot
        data['audio_key'],data['audio_data']=audio_snapshot(editor,pid,original,view,narration,mix,verifier)
        verified_sources.extend(data['audio_data']['sources'])
        key=hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()
        return key,data,state['revision']


def request(editor,advanced,pid,time,quality='auto'):
    key,data,revision=snapshot(editor,advanced,pid,time,quality);folder=cache_folder(editor,pid);target=folder/f'proxy-v1-{key}.mp4'
    result={'key':key,'start':data['start'],'duration':data['duration'],'revision':revision,'width':data['size'][0],'height':data['size'][1],
            'stream_info_url':f'/api/projects/{pid}/editor/advanced/program-stream-info/{key}',
            'encoded_fps':30,'mode':'local_proxy','audio':'Projenin ortak ses miksinden kesit: normalizasyon ve ducking parça başında yeniden başlamaz.',
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
            except Exception as error:
                raise EditorError(getattr(error,'category','preview_failed'),str(error) if hasattr(error,'category') else 'Proxy hazırlanamadı. Kaynağı kontrol edip yeniden deneyin; oynatma bekletildi.') from None
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
        except Exception as error:
            raise EditorError(getattr(error,'category','preview_failed'),str(error) if hasattr(error,'category') else 'Proxy hazırlanamadı. Kaynağı kontrol edip yeniden deneyin; oynatma bekletildi.') from None
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
            else:
                from app.rendering.source_timing import input_time
                args.extend(['-ss',str(input_time(part['path'],discover().get('ffprobe'),part['cut']))])
            decode_length=length*part['speed']+.1
            if part.get('source_end') is not None:decode_length=min(decode_length,part['source_end']-part['cut'])
            args.extend(['-t',str(decode_length),'-i',str(part['path'])])
            graphs.append(f'[{n}:v]setpts=(PTS-STARTPTS)/{part["speed"]},scale={width}:{height}:force_original_aspect_ratio=increase:out_range=tv,crop={width}:{height},setsar=1,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,fps=30,tpad=stop_mode=clone:stop_duration=0.034,trim=duration={length},setpts=PTS-STARTPTS,format=yuv420p[{label}]')
        else:
            args.extend(['-f','lavfi','-i',f'color=c=black:s={width}x{height}:r=30:d={length}']);graphs.append(f'[{n}:v]null[{label}]')
        incoming=next((t for t in data.get('transitions',[]) if t['next_slot_id']==part.get('slot_id') and t['kind'] in ('cross_dissolve','wipe') and part['original_start']+t['duration']>part['start']),None)
        if incoming:
            previous=next(s for s in data['all_slots'] if s['slot_id']==incoming['slot_id'])
            path=previous.get('proxy_path')
            if not path:raise EditorError('preview_failed','Geçişin önceki kaynağı bulunamadı; kurgu değiştirilmedi.')
            speed=next((a['transform']['speed'] for a in data['original_adjustments'] if a['slot_id']==previous['slot_id']),1)
            elapsed=part['start']-part['original_start'];offset=(previous.get('clip_start') or 0)+(previous['end']-previous['start']+elapsed)*speed
            n=args.count('-i')
            if previous['media']['media_type']=='image':args.extend(['-loop','1','-framerate','30'])
            else:
                from app.rendering.source_timing import input_time
                args.extend(['-ss',str(input_time(path,discover().get('ffprobe'),offset))])
            args.extend(['-t',str(min(length,max(1/30,incoming['duration']-elapsed))*speed+.1),'-i',str(path)])
            graphs.append(f'[{n}:v]setpts=(PTS-STARTPTS)/{speed},scale={width}:{height}:force_original_aspect_ratio=increase:out_range=tv,crop={width}:{height},setsar=1,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,fps=30,format=yuv420p[tail{index}]')
            u=f'clip((T+{elapsed})/{max(1/30,(round(incoming["duration"]*30)-1)/30)},0,1)'
            blend=f'B*(1-({u}))+A*({u})' if incoming['kind']=='cross_dissolve' else f'if(gte(X,W*(1-({u}))),A,B)'
            graphs.append(f"[{label}][tail{index}]blend=all_expr='{blend}':shortest=0:repeatlast=1:enable='lt(t,{incoming['duration']-elapsed})'[blend{index}]");label=f'blend{index}'
        for transition in data.get('transitions',[]):
            if transition['kind']!='dip_black':continue
            half=transition['duration']/2
            if transition['slot_id']==part.get('slot_id'):
                gain=f'clip(({part["original_end"]-part["start"]}-T)/{half},0,1)';enabled=f'gte(t,{part["original_end"]-part["start"]-half})'
            elif transition['next_slot_id']==part.get('slot_id'):
                gain=f'clip((T+{part["start"]-part["original_start"]})/{half},0,1)';enabled=f'lt(t,{half-part["start"]+part["original_start"]})'
            else:continue
            out=f'dip{index}_{len(graphs)}'
            graphs.append(f"[{label}]geq=lum='16+(lum(X,Y)-16)*({gain})':cb='128+(cb(X,Y)-128)*({gain})':cr='128+(cr(X,Y)-128)*({gain})':enable='{enabled}'[{out}]");label=out
        inputs.append(label);cursor=part['end']
    for part in data['bases']:
        if part['start']>cursor+.001:base({'start':cursor,'end':part['start'],'path':None},len(inputs))
        base(part,len(inputs))
    if cursor<duration-.001:base({'start':cursor,'end':duration,'path':None},len(inputs))
    # concat uses microsecond timebase. Its rounded 1.466666 timestamp can be
    # one microsecond earlier than a 30fps overlay's 1.466667 timestamp, making
    # framesync reuse the previous frame every third frame after a cut. Restore
    # the exact frame clock before any overlays/adjustments consume the base.
    graphs.append(''.join(f'[{x}]' for x in inputs)+(f'concat=n={len(inputs)}:v=1:a=0' if len(inputs)>1 else 'null')+',settb=1/30,setpts=N/(30*TB)[base]')
    narration=temporary/'narration.wav'
    try:
        from app.motion.clips import render_clip
        from app.channels import DEFAULT_STYLE
        from app.motion.places import offline
        for clip in data['document']['clips']:
            if clip['kind']!='motion':continue
            style=deepcopy(data.get('kit') or DEFAULT_STYLE)
            if clip.get('motion_color'):style['palette']['accent']=clip['motion_color']
            offset=clip.get('animation_offset',0);length=clip['end']-clip['start']
            with offline():
                path,scene,_=render_clip(Path(data['motion_folder']),{**clip['motion'],'local_only':True,'clean_source':clip.get('clean_map',False)},style,clip.get('animation_duration') or length,0,language=data.get('language','de'),prefer_openmontage=False,element_edits=clip.get('motion_elements'),render_window=(offset,length),render_size=(width,height))
            data['assets'][clip['id']]={'path':path,'type':'video','has_audio':False}
            clip['source_start']=0 if '_render_start' in scene else offset

        from app.editor.proxy_audio import master
        mixed=master(folder,data['audio_key'],data['audio_data'],ffmpeg)
        run([ffmpeg,'-v','error','-y','-ss',str(data['start']),'-i',str(mixed),'-t',str(duration),'-ar','48000','-ac','2','-c:a','pcm_f32le',str(narration)])
        from app.editor.proxy_layers import flatten
        proxy_doc,proxy_assets=flatten(data['document'],data['assets'],temporary,width,height)
        graph,label,audio=compile_graph(args,proxy_doc,proxy_assets,base='base',folder=temporary,duration=duration,width=width,height=height,adjustment_slots=data['slots'],include_audio=False)
        if graph:graphs.append(graph)
        content,_,has_text=ass.create(data['cues'],[],data['full_duration'],subtitles=bool(data['cues']),overlays=False,subtitle_style=data.get('subtitle_style'))
        if has_text:
            # ASS PlayRes is the final 1080p plane; libass scales to proxy size.
            (temporary/'captions.ass').write_text(content,encoding='utf-8')
            caption=str(temporary/'captions.ass').replace('\\','/').replace(':',r'\:').replace("'",r"\'")
            font_path=str(Path(__file__).resolve().parents[1]/'static/fonts').replace('\\','/').replace(':',r'\:').replace("'",r"\'")
            graphs.append(f"[{label}]setpts=PTS+{data['start']}/TB,ass=filename='{caption}':fontsdir='{font_path}',setpts=PTS-STARTPTS[captioned]");label='captioned'
        index=args.count('-i');args+=['-i',str(narration)]
        graphs.append(f'[{index}:a]anull[audio]')
        script=temporary/'graph.txt';script.write_text(';\n'.join(graphs),encoding='utf-8')
        output=temporary/'preview.mp4'
        args+=['-filter_complex_script',str(script),'-map',f'[{label}]','-map','[audio]','-c:v','libx264','-preset','ultrafast','-crf','20','-pix_fmt','yuv420p','-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-r','30','-frames:v',str(round(duration*30)),'-threads','1','-c:a','aac','-ar','48000','-ac','2','-t',str(duration),'-movflags','+faststart',str(output)]
        run(args)
        if not output.is_file() or output.stat().st_size<100:raise EditorError('preview_failed','Proxy dosyası üretilemedi.')
        os.replace(output,target)
        cached=sorted(folder.glob('proxy-v1-*.mp4'),key=lambda p:p.stat().st_mtime)
        for stale in cached[:-48]:
            if not linked(stale):stale.unlink(missing_ok=True)
    finally:shutil.rmtree(temporary,ignore_errors=True)


# Repackage existing, validated proxies for one continuous browser decoder.
# This copies encoded packets; it does not render again or touch source media.
_stream_locks=[RLock() for _ in range(32)]


def stream(editor,pid,key):
    source=file(editor,pid,key);folder=source.parent
    target=folder/f'proxy-stream-v1-{key}.mp4';metadata=target.with_suffix('.json')
    with _stream_locks[int(key[:8],16)%len(_stream_locks)]:
        if target.is_file() and metadata.is_file() and not linked(target) and not linked(metadata):
            return target,json.loads(metadata.read_text(encoding='utf-8'))
        from app.rendering.tools import discover
        tools=discover()
        if not tools.get('ffprobe'):raise EditorError('preview_probe','Kesintisiz önizleme için FFprobe gerekli; FFmpeg kurulumunu kontrol edin.')
        temp=folder/('stream-work-'+uuid4().hex+'.mp4')
        try:
            run([tools['ffmpeg'],'-v','error','-y','-i',str(source),'-map','0:v:0','-map','0:a:0','-c','copy',
                 '-movflags','+delay_moov+default_base_moof+frag_keyframe+negative_cts_offsets','-frag_duration','1000000',str(temp)])
            # The signed CTS/edit list preserves AAC priming and uniform video
            # timestamps; empty_moov alone stretches the first video interval.
            probe=subprocess.run([tools['ffprobe'],'-v','error','-select_streams','v:0','-show_entries','stream=start_time','-of','json',str(temp)],capture_output=True,text=True,timeout=15,check=True)
            origin=float(json.loads(probe.stdout)['streams'][0]['start_time'])
            with temp.open('rb') as handle:header=handle.read(1024*1024)
            position=header.find(b'avcC')
            if position<0 or header[position+4]!=1:raise ValueError('avcC')
            codec=header[position+5:position+8].hex().upper()
            info={'mime':f'video/mp4; codecs="avc1.{codec}, mp4a.40.2"','origin':origin,
                  'url':f'/api/projects/{pid}/editor/advanced/program-stream/{key}'}
            os.replace(temp,target)
            # Metadata is published last; an incomplete pair is rebuilt safely.
            stamp=metadata.with_name(uuid4().hex+'.json')
            try:stamp.write_text(json.dumps(info),encoding='utf-8');os.replace(stamp,metadata)
            finally:stamp.unlink(missing_ok=True)
        except (OSError,ValueError,KeyError,IndexError,subprocess.SubprocessError):
            raise EditorError('preview_stream','Kesintisiz önizleme paketi hazırlanamadı. FFmpeg/FFprobe kurulumunu kontrol edip yeniden deneyin.') from None
        finally:temp.unlink(missing_ok=True)
        for stale in sorted(folder.glob('proxy-stream-v1-*.mp4'),key=lambda p:p.stat().st_mtime)[:-48]:
            if not linked(stale):
                try:stale.unlink(missing_ok=True);stale.with_suffix('.json').unlink(missing_ok=True)
                except OSError:pass  # A browser can still hold the file on Windows.
        return target,info
