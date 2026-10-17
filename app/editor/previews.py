"""Bounded local previews. Decode only a requested frame, never the whole archive."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
from threading import BoundedSemaphore
from uuid import uuid4

from app.editor.models import EditorError
from app.projects import linked

_decoders=BoundedSemaphore(2)


@contextmanager
def decoder():
    if not _decoders.acquire(timeout=2):raise EditorError('preview_busy','Yerel önizleme hazırlanıyor; birkaç saniye sonra tekrar deneyin.',503)
    try:yield
    finally:_decoders.release()


def cache_folder(editor,pid):
    folder=editor.projects._path(pid)/'stock'/'editor-cache'
    if linked(folder):raise EditorError('unsafe_cache','Önizleme önbelleği güvenli bir yerel klasör olmalıdır.')
    folder.mkdir(exist_ok=True)
    return folder


def run(args):
    with decoder():
        try:
            done=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
            if done.returncode:raise EditorError('preview_failed','Yerel dosya için önizleme oluşturulamadı; kaynak dosyanın açıldığını kontrol edin.')
        except (OSError,subprocess.SubprocessError):raise EditorError('preview_failed','FFmpeg önizlemesi tamamlanamadı; FFmpeg ve kaynak dosyayı kontrol edin.') from None


def thumbnail(editor,pid,provider,mid):
    from app.editor.service import sha256_file
    from app.rendering.tools import discover
    path,asset=editor.archive_file(pid,provider,mid)
    if asset['media_type'] not in ('video','image'):raise EditorError('no_thumbnail','Ses dosyasında görüntü karesi yok.')
    verifier=getattr(getattr(editor.stock,'downloader',None),'verified_hash',None)
    actual=verifier(path,asset.get('sha256')) if verifier else sha256_file(path)
    if asset.get('sha256')!=actual:raise EditorError('stale_media','Kaynak dosya değişmiş. Arşivi yeniden ekleyin.',409)
    folder=cache_folder(editor,pid);target=folder/f'thumb-v1-{actual}.jpg'
    if target.is_file() and not linked(target):return target
    ffmpeg=discover()['ffmpeg'];temp=folder/(uuid4().hex+'.jpg')
    try:
        args=[ffmpeg,'-v','error','-y','-threads','1']
        if asset['media_type']=='video':args+=['-ss',str(min(.3,max(0,(asset.get('duration') or 0)/3)))]
        args+=['-i',str(path),'-vf','scale=240:135:force_original_aspect_ratio=decrease,format=yuv444p,pad=240:135:(ow-iw)/2:(oh-ih)/2','-frames:v','1','-threads','1',str(temp)]
        run(args)
        if not temp.is_file() or not temp.stat().st_size:raise EditorError('preview_failed','Kaynak videodan geçerli bir kare alınamadı.')
        os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)
    return target


def program_frame(editor,advanced,pid,time):
    from app.editor.service import sha256_file
    from app.editor.compositor import compile_graph,resolve
    from app.rendering.tools import discover
    from app.stock.download import asset_path
    view=editor.view(pid)
    if not 0<=time<=view['duration']:raise EditorError('invalid_time','Önizleme zamanı anlatım aralığında olmalıdır.')
    state=advanced.get(pid);document=state['document'];folder=cache_folder(editor,pid)
    # UI is frame sampled; don't generate a full long-documentary proxy on a seek.
    time=min(time,max(0,view['duration']-1/30));frame=round(time*30)/30
    media=[item for track in view['tracks'].values() for item in track if item.get('slot_id')]
    verifier=getattr(getattr(editor.stock,'downloader',None),'verified_hash',None)
    item=next((x for x in media if x['start']<=frame<x['end']),None)
    hashes=[];path=None
    if item and item.get('media'):
        path=asset_path(editor.projects,pid,item['media']);expected=item['media'].get('sha256')
        digest=verifier(path,expected) if verifier and expected else sha256_file(path)
        if expected and expected!=digest:raise EditorError('stale_media','Ana kaynak dosyası değişmiş; medya arşivini kontrol edin.',409)
        hashes.append(digest)
    active={**document,'clips':[c for c in document['clips'] if c['visible'] and c['start']<=frame<c['end']]}
    assets=resolve(editor.projects,pid,active,editor.archive_file,draw=True,verify=verifier)
    hashes.extend(str(a.get('sha256') or sha256_file(a['path'])) for a in assets.values())
    for transition in document['transitions']:
        if item and transition['next_slot_id']==item['slot_id'] and frame-item['start']<transition['duration']:
            previous=next((x for x in media if x['slot_id']==transition['slot_id']),None)
            if previous and previous.get('media'):
                previous_path=asset_path(editor.projects,pid,previous['media']);expected=previous['media'].get('sha256')
                digest=verifier(previous_path,expected) if verifier and expected else sha256_file(previous_path)
                if expected and digest!=expected:raise EditorError('stale_media','Geçiş kaynağı değişmiş. Arşivi kontrol edin.',409)
                hashes.append(digest)
    key=hashlib.sha256(json.dumps([document,view['stock_revision'],frame,hashes],sort_keys=True).encode()).hexdigest()
    target=folder/f'frame-v1-{key}.jpg'
    if target.is_file() and not linked(target):return target
    ffmpeg=discover()['ffmpeg'];temp=folder/(uuid4().hex+'.jpg')
    args=[ffmpeg,'-v','error','-y','-filter_complex_threads','1','-filter_threads','1','-threads','1']
    if path:
        adjustment=next((a for a in document['adjustments'] if a['slot_id']==item['slot_id']),None)
        speed=(adjustment or {}).get('transform',{}).get('speed',1)
        if item['media']['media_type']=='video':
            source_time=(item.get('clip_start') or 0)+(frame-item['start'])*speed
            source_duration=item['media'].get('duration')
            if source_duration and source_time>=source_duration:source_time%=source_duration  # existing legacy short-clip loop
            args+=['-ss',str(source_time)]
        args+=['-i',str(path)]
    else:args+=['-f','lavfi','-i','color=c=black:s=640x360:r=30:d=0.04']
    normalize='scale=640:360:force_original_aspect_ratio=increase,crop=640:360,setsar=1'
    base=f'[0:v]{normalize}[base]'
    # Match the saved, frame-counted transition without requesting a whole proxy video.
    if item:
        incoming=next((t for t in document['transitions'] if t['next_slot_id']==item['slot_id'] and t['kind'] in ('cross_dissolve','wipe') and frame-item['start']<t['duration']),None)
        if incoming:
            previous=next((x for x in media if x['slot_id']==incoming['slot_id']),None)
            if previous and previous.get('media'):
                previous_path=asset_path(editor.projects,pid,previous['media'])
                speed=next((a['transform']['speed'] for a in document['adjustments'] if a['slot_id']==previous['slot_id']),1)
                index=args.count('-i');offset=(previous.get('clip_start') or 0)+(previous['end']-previous['start']+frame-item['start'])*speed
                if previous['media']['media_type']=='video':args+=['-ss',str(offset)]
                args+=['-i',str(previous_path)]
                blend_duration=max(1/30,(round(incoming['duration']*30)-1)/30)
                u=min(1,max(0,(frame-item['start'])/blend_duration))
                blend=f'A*{1-u}+B*{u}' if incoming['kind']=='cross_dissolve' else f'if(gte(X,{640*(1-u)}),B,A)'
                base=f'[0:v]{normalize}[next];[{index}:v]{normalize}[previous];[previous][next]blend=all_expr=\'{blend}\'[base]'
        dip=next((t for t in document['transitions'] if t['kind']=='dip_black' and (t['slot_id']==item['slot_id'] or t['next_slot_id']==item['slot_id'])),None)
        if dip:
            half=dip['duration']/2
            gain=min(1,max(0,(item['end']-frame)/half if dip['slot_id']==item['slot_id'] else (frame-item['start'])/half))
            base=base.replace('[base]',f',colorchannelmixer=rr={gain}:gg={gain}:bb={gain}[base]')
    # Audio layers don't appear in a still image; their independent players remain synchronized.
    doc={**document,'clips':[c for c in document['clips'] if c['track']!='audio']}
    graph,label,_=compile_graph(args,doc,assets,base='base',folder=folder,duration=.04,width=640,height=360,
        adjustment_slots={x['slot_id']:x for x in media},frame_time=frame)
    args+=['-filter_complex',base+(';' +graph if graph else ''),'-map',f'[{label}]','-frames:v','1','-threads','1',str(temp)]
    try:
        run(args)
        if not temp.is_file() or not temp.stat().st_size:raise EditorError('preview_failed','Program karesi oluşturulamadı. Kaynak klibin kesitini kontrol edin.')
        os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)
    # Bound only our own frame cache; thumbnails retain their stable source identity.
    cached=sorted(folder.glob('frame-v1-*.jpg'),key=lambda p:p.stat().st_mtime)
    for stale in cached[:-240]:
        if not linked(stale):stale.unlink(missing_ok=True)
    return target
