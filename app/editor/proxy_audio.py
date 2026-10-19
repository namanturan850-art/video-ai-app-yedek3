"""One full audio state per approved mix; video proxies only slice its clock.

Uses the existing final audio operators. No video/animation is rendered here.
"""
from copy import deepcopy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
from app.editor.advanced import Document
from app.editor.compositor import resolve,compile_graph
from app.editor.previews import run
from app.editor.models import EditorError
from app.projects import linked


def snapshot(editor,pid,document,view,narration,mix,verifier):
    from app.stock.download import asset_path
    from app.editor.service import sha256_file
    doc=Document().model_dump();candidates=[]
    # Silent pictures/videos outside the current window are not audio inputs.
    # Reading their files here would make an unrelated missing image block sound.
    with closing(editor.projects._connection()) as connection:
        for clip in document['clips']:
            if not clip['visible'] or clip['kind']!='media':continue
            if not (clip['transform']['volume'] or any(k['property']=='volume' for k in clip['keyframes'])):continue
            ref=clip['media'];row=connection.execute('SELECT media_type,metadata_json FROM stock_assets WHERE project_id=? AND provider=? AND media_id=?',(pid,ref['provider'],ref['media_id'])).fetchone()
            if clip['track']=='audio' or row and (row['media_type']=='audio' or row['media_type']=='video' and json.loads(row['metadata_json']).get('has_audio',False)):
                candidates.append(deepcopy(clip))
    doc['clips']=candidates
    assets=resolve(editor.projects,pid,doc,editor.archive_file,verify=verifier)
    doc['clips']=[c for c in doc['clips'] if assets[c['id']].get('has_audio') or assets[c['id']]['type']=='audio']
    assets={c['id']:assets[c['id']] for c in doc['clips']};slots={}
    known={x['slot_id']:x for values in view['tracks'].values() for x in values if x.get('slot_id')}
    for adjustment in document['adjustments']:
        if not (adjustment['transform']['volume'] or any(k['property']=='volume' for k in adjustment['keyframes'])):continue
        slot=known.get(adjustment['slot_id']);media=(slot or {}).get('media') or {}
        if not media.get('has_audio'):continue
        path=asset_path(editor.projects,pid,media);expected=media.get('sha256');digest=verifier(path,expected) if verifier else sha256_file(path)
        if expected and digest!=expected:raise EditorError('stale_media','Sesli görüntü kaynağı değişmiş; arşivi kontrol edin.',409)
        sid=slot['slot_id'];doc['adjustments'].append(deepcopy(adjustment));slots[sid]={**slot,'start':round(slot['start']*30)/30,'end':round(slot['end']*30)/30}
        assets[sid]={'path':path,'type':'video','has_audio':True,'sha256':digest,'segment_start':slot.get('clip_start') or 0}
    data={'version':1,'document':doc,'assets':assets,'slots':slots,'mix':mix,'duration':view['duration'],'narration':narration}
    data['sources']=[(str(a['path']),a['sha256']) for a in assets.values() if a.get('sha256')]
    data['narration_sha256']=verifier(narration,None) if verifier and narration else sha256_file(narration) if narration else None
    key=hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()
    return key,data


def master(folder,key,data,ffmpeg):
    from app.rendering.engine import LOUDNESS
    target=folder/f'proxy-audio-v1-{key}.flac'
    if target.is_file() and not linked(target):return target
    work=folder/('audio-work-'+uuid4().hex+'.flac');duration=data['duration'];mix=data['mix']
    args=[ffmpeg,'-v','error','-y','-filter_complex_threads','1','-threads','1']
    graph,_,audio=compile_graph(args,data['document'],data['assets'],folder=folder,duration=duration,adjustment_slots=data['slots'],narration=data['narration'],audio_only=True)
    index=args.count('-i')
    if data['narration']:args+=['-i',str(data['narration'])]
    else:args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
    voice=f'[{index}:a]aresample=48000,apad,atrim=duration={duration},asetpts=PTS-STARTPTS,volume={mix.get("narration_volume",1)}'
    fi=min(duration/2,max(0,mix.get('narration_fade_in',0)));fo=min(duration/2,max(0,mix.get('narration_fade_out',0)))
    if fi:voice+=f',afade=t=in:st=0:d={fi}'
    if fo:voice+=f',afade=t=out:st={max(0,duration-fo)}:d={fo}'
    pieces=[graph] if graph else [];pieces.append(voice+','+LOUDNESS+'[master]')
    pieces.append('[master]'+''.join(f'[{a}]' for a in audio)+(f'amix=inputs={len(audio)+1}:duration=first:normalize=0,alimiter=limit=0.84:level=false' if audio else 'anull')+'[mixed]')
    script=folder/('audio-graph-'+uuid4().hex+'.txt')
    try:
        script.write_text(';\n'.join(pieces),encoding='utf-8')
        run(args+['-filter_complex_script',str(script),'-map','[mixed]','-vn','-ar','48000','-ac','2','-c:a','flac','-sample_fmt','s32','-t',str(duration),str(work)])
        os.replace(work,target)
    finally:work.unlink(missing_ok=True);script.unlink(missing_ok=True)
    for old in sorted(folder.glob('proxy-audio-v1-*.flac'),key=lambda p:p.stat().st_mtime)[:-2]:
        if old!=target and not linked(old):
            try:old.unlink(missing_ok=True)
            except OSError:pass
    return target
