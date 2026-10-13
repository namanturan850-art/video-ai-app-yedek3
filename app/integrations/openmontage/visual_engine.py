"""Original local frame-check adapter, loaded only in the external environment."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
from uuid import uuid4

MODEL='openai/clip-vit-base-patch32'  # Verified upstream lib.clip_embedder._MODEL_ID.
NEGATIVES=('a dog on grass','a passenger inside a train','a barbershop haircut',
           'a city skyline','a beach sunset','a forest','an aircraft cockpit instruments',
           'an aircraft flight crew','open ocean water','a ship navigation compass')


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def save(path,value):
    temporary=path.with_name('.write-'+uuid4().hex)
    try:
        temporary.write_text(json.dumps(value));os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def inference(fn,value,clip,torch):
    try:return fn(value)
    except RuntimeError:
        if clip._DEVICE!='cuda':raise
        # Unsupported CUDA architecture/OOM: retry CPU once, same local model.
        clip._MODEL=None;clip._PROCESSOR=None
        original=torch.cuda.is_available;torch.cuda.is_available=lambda:False
        try:return fn(value)
        finally:torch.cuda.is_available=original


def model_status(root):
    folder=root/'.models'/'clip-vit-base-patch32'
    try:
        manifest=json.loads((folder/'avs-model.json').read_text())
        if (manifest.get('weights')!='pytorch_model.bin' or not re.fullmatch(r'[a-f0-9]{64}',str(manifest.get('sha256','')))
                or type(manifest.get('size')) is not int or manifest['size']<=0):return None
        weight=folder/manifest['weights']
        if manifest['model']!=MODEL or not weight.is_file() or weight.stat().st_size!=manifest['size']:return None
        if weight.is_symlink() or folder.is_symlink():return None
        return {'folder':folder,'weight':weight,'version':manifest['sha256'],'size':manifest['size']}
    except (OSError,ValueError,KeyError,TypeError):return None


# Medyayı Tamamla: never-wanted footage the owner named (dog, office, modern city …).
FRAME_NEGATIVES=('a dog','people working in a modern office','a modern city skyline with skyscrapers','a laptop computer on a desk',
                 'a smartphone screen','cars in modern street traffic','a business meeting','a selfie of a smiling person',
                 'a supermarket','an empty white background','text on a plain background')


def clip_score(target,margin):
    """0-10 for the screen: 5 = no better than the unwanted pictures, 10 = clearly the described scene."""
    return max(0,min(10,round(5+margin*120)-(2 if target<.20 else 0)))


def score_frames(root,inputs):
    """Preview frames (JPEG files the app already has) of up to 32 stock
    candidates against one English description, one model load. Returns
    per candidate: verdict match/mismatch/uncertain, similarity, margin, score 0-10."""
    status=model_status(root)
    if not status:raise ValueError('semantic_model_missing')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    from lib import clip_embedder
    from lib.clip_embedder import embed_images,embed_texts
    import torch
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    if sha(status['weight'])!=status['version']:raise ValueError('semantic_model_changed')
    clip_embedder._MODEL_ID=str(status['folder'])
    descriptor=str(inputs['descriptor'])[:300]
    words=set(re.findall(r'[a-z]+',descriptor.casefold()))-{'a','an','the','of','in','on','with'}
    negatives=[n for n in FRAME_NEGATIVES+NEGATIVES if not set(re.findall(r'[a-z]+',n))&words] or ['unrelated footage']
    penalties=setting_penalties(inputs.get('penalties'),descriptor)
    texts=inference(embed_texts,[descriptor,*negatives,*(p['text'] for p in penalties)],clip_embedder,torch)
    split=1+len(negatives)
    results=[]
    for item in inputs['candidates'][:32]:
        frames=[Path(p) for p in item['frames'][:3]]
        if not frames or any(not f.is_file() or f.is_symlink() or not f.is_absolute() for f in frames):raise ValueError('source_missing')
        images=inference(embed_images,frames,clip_embedder,torch)
        scores=images@texts.T;target=float(scores[:,0].mean());other=float(scores[:,1:split].mean(axis=0).max())
        margin=target-other
        votes=int((scores[:,0]>scores[:,1:split].max(axis=1)+.01).sum())
        verdict='match' if target>=.20 and margin>=.015 and votes>=min(2,len(images)) else 'mismatch' if margin<=-.02 else 'uncertain'
        result={'key':str(item['key'])[:200],'verdict':verdict,'similarity':round(target,4),'contrast_margin':round(margin,4),
                'score':clip_score(target,margin),'model':MODEL,'sample_count':len(images)}
        conflict=setting_conflict(scores[:,0],scores[:,split:],penalties)
        if conflict:result.update(verdict='mismatch',score=min(result['score'],2),conflict=conflict)
        results.append(result)
    return {'results':results}


def setting_penalties(raw,descriptor):
    """Prompts for what contradicts the video's period/place (app/stock/setting.py).
    '{subject}' becomes the shot's own subject: “a cartoon drawing of <subject>”
    against “a photo of <subject>” leaves only the look to decide."""
    subject=re.sub(r'^(a|an)\s+(documentary\s+)?photo\s+of\s+','',descriptor,flags=re.I).strip() or 'a scene'
    out=[]
    for item in (raw or [])[:30]:
        if not isinstance(item,dict) or not isinstance(item.get('text'),str) or item.get('kind') not in ('anachronism','style','place'):continue
        text=item['text'].replace('{subject}',subject)[:200]
        out.append({'kind':item['kind'],'text':text,'label':str(item.get('label',''))[:60]})
    return out


def setting_conflict(target,scores,penalties):
    """The penalty prompt the frames resemble MORE than the shot's description
    (on average and in at least half of the frames), or None."""
    if not penalties:return None
    best=None
    for index,item in enumerate(penalties):
        column=scores[:,index];lead=float(column.mean())-float(target.mean())
        frames=int((column>target).sum())
        need=.0 if item['kind']=='style' else .005  # style prompts carry the same subject: any lead counts
        if lead>need and frames*2>=len(target) and float(column.mean())>=.18 and (best is None or lead>best['lead']):
            best={'kind':item['kind'],'label':item['label'],'text':item['text'][:120],'similarity':round(float(column.mean()),4),'lead':round(lead,4)}
    return best


def analyse(root,inputs,command):
    status=model_status(root)
    if not status:raise ValueError('semantic_model_missing')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    from lib import clip_embedder
    from lib.clip_embedder import embed_images,embed_texts,model_info
    import numpy as np
    import torch
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    if sha(status['weight'])!=status['version']:raise ValueError('semantic_model_changed')
    clip_embedder._MODEL_ID=str(status['folder'])
    cache=root/'.avs-visual-cache';cache.mkdir(exist_ok=True)
    if cache.is_symlink():raise ValueError('cache_path')
    if sum(1 for _ in cache.iterdir())>5000:raise ValueError('semantic_cache_limit')
    descriptor=inputs['descriptor'][:300]
    # Relative contrast is a heuristic, never an authenticity/confidence claim.
    negatives=[n for n in NEGATIVES if not set(n.split())&set(descriptor.casefold().split())-{'a','an','the','on','inside'}]
    if not negatives:negatives=['unrelated footage']
    text_key=hashlib.sha256((status['version']+descriptor+json.dumps(negatives)).encode()).hexdigest()
    text_file=cache/('text-'+text_key+'.json')
    if text_file.is_symlink():raise ValueError('cache_path')
    if text_file.exists():texts=np.array(json.loads(text_file.read_text()),dtype=np.float32)
    else:
        texts=inference(embed_texts,[descriptor,*negatives],clip_embedder,torch);save(text_file,texts.tolist())
    results=[]
    for item in inputs['candidates'][:4]:
        source=Path(item['path'])
        if not source.is_file() or source.is_symlink() or not source.is_absolute():raise ValueError('source_missing')
        source_sha=sha(source)
        if source_sha!=item['sha256']:raise ValueError('source_changed')
        key=hashlib.sha256((source_sha+status['version']+'frames-20-50-80-v1').encode()).hexdigest()
        vector_file=cache/('frames-'+key+'.json')
        if vector_file.is_symlink():raise ValueError('cache_path')
        if vector_file.exists():images=np.array(json.loads(vector_file.read_text()),dtype=np.float32)
        else:
            with tempfile.TemporaryDirectory(prefix='avs-frames-',dir=cache) as work:
                frames=[]
                fractions=(.2,.5,.8) if item['media_type']=='video' else (0.,)
                for i,fraction in enumerate(fractions):
                    frame=Path(work)/f'frame-{i}.jpg'
                    args=['ffmpeg','-v','error','-y']
                    if fraction:args+=['-ss',str(float(item['duration'])*fraction)]
                    args+=['-i',str(source),'-frames:v','1','-vf','scale=512:-2',str(frame)]
                    command(args,timeout=30);frames.append(frame)
                images=inference(embed_images,frames,clip_embedder,torch);save(vector_file,images.tolist())
        scores=images@texts.T;target=float(scores[:,0].mean());other=float(scores[:,1:].mean(axis=0).max())
        margin=target-other
        votes=int((scores[:,0]>scores[:,1:].max(axis=1)+.01).sum())
        verdict='match' if target>=.20 and margin>=.015 and votes>=min(2,len(images)) else 'mismatch' if margin<=-.025 else 'uncertain'
        results.append({'sha256':source_sha,'verdict':verdict,'similarity':round(target,4),'contrast_margin':round(margin,4),
                        'model':MODEL,'model_version':status['version'],'sample_count':len(images),'device':model_info()['device']})
    return {'results':results}
