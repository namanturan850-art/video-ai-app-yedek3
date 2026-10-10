"""Original stdlib bridge, executed ONLY by the external installation's Python.

Imports upstream tools in that isolated process; never imports them into our app.
No agent, TTS, script generator, paid source, raw error or credential persistence.
"""
import contextlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(sys.argv[1]).resolve()
FREE=('archive_org','nasa','wikimedia')
# Upstream base_tool loads .env at import time. Override every declared name,
# preserving only explicitly supplied runtime stock keys; never copy its values.
env_file=ROOT/'.env'
if env_file.is_file():
    for line in env_file.read_text(encoding='utf-8',errors='replace').splitlines():
        name=line.strip().removeprefix('export ').partition('=')[0].strip()
        if name and name.replace('_','').isalnum():os.environ.setdefault(name,'')
logging.disable(logging.CRITICAL)
sys.path.insert(0,str(ROOT))


def execute(tool,inputs):
    tool.run_command=command
    # Bypass upstream's automatic trace wrapper: it may persist raw source URLs.
    fn=getattr(type(tool).execute,'__wrapped__',None)
    return fn(tool,inputs) if fn else tool.execute(inputs)


def browser():
    # Read-only query to the pinned Remotion package. Never install at render.
    code="const f=require('./node_modules/@remotion/renderer/dist/browser/BrowserFetcher.js');const r=f.getRevisionInfo('headless-shell');console.log(r.local&&f.readVersionFile('headless-shell')===f.TESTED_VERSION?r.executablePath:'');"
    r=subprocess.run([shutil.which('node'),'-e',code],cwd=ROOT/'remotion-composer',shell=False,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=15)
    path=r.stdout.strip() if r.returncode==0 else ''
    if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):return path
    # Trusted local discovery, never a browser-supplied executable path.
    for name in ('chromium','chromium-browser','google-chrome'):
        p=shutil.which(name)
        if p and Path(p).resolve().is_file():return str(Path(p).resolve())
    raise ValueError('browser_missing')


def command(args,*,timeout=None,cwd=None):
    if not isinstance(args,list) or not args:raise ValueError('command_invalid')
    if args[0]=='npx':
        if args[1]!='remotion':raise ValueError('command_invalid')
        args=[shutil.which('node'),str(ROOT/'remotion-composer/node_modules/@remotion/cli/remotion-cli.js'),*args[2:]]
        if args[2]=='render':args.append('--browser-executable='+browser())
    elif args[0] in ('ffmpeg','ffprobe'):args=[shutil.which(args[0]),*args[1:]]
    else:raise ValueError('command_invalid')
    if not args[0]:raise ValueError('dependency_missing')
    args=['-/filter_complex' if a=='-filter_complex_script' else a for a in args]
    result=subprocess.run(args,cwd=cwd,shell=False,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=min(timeout or 1800,1800))
    if result.returncode:raise RuntimeError('external_command_failed')
    return result


def work(operation,inputs):
    spec=importlib.util.spec_from_file_location('avs_visual_engine',Path(__file__).with_name('visual_engine.py'))
    visual=importlib.util.module_from_spec(spec);spec.loader.exec_module(visual)
    if operation in ('visual','semantic'):
        status=visual.model_status(ROOT)
        if not status:raise ValueError('semantic_model_missing')
        os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        if operation=='visual':return visual.analyse(ROOT,inputs,command)
        from lib import clip_embedder
        clip_embedder._MODEL_ID=str(status['folder'])
    if operation=='doctor':
        from tools.video.video_compose import VideoCompose
        from tools.video.stock_sources import available_sources
        node=command(['npx','remotion','versions'],timeout=15,cwd=ROOT/'remotion-composer')
        browser()
        weights=visual.model_status(ROOT)
        return {'sources':[s.name for s in available_sources() if s.name in FREE],
                'semantic_ready':bool(weights and all(importlib.util.find_spec(n) for n in ('torch','transformers','cv2'))),
                'semantic_model_version':weights['version'] if weights else ''}
    if operation in ('search','semantic'):
        from tools.video.stock_sources import available_sources
        names=[s.name for s in available_sources() if s.name in (*FREE,'pexels','pixabay_video')]
        if not names:raise ValueError('source_missing')
        inputs={**inputs,'sources':names}
        if operation=='search':
            from tools.video.direct_clip_search import DirectClipSearch
            result=execute(DirectClipSearch(),inputs)
            if not result.success:raise ValueError('search_failed')
            clips=result.data.get('clips',[])
        else:
            from tools.video.corpus_builder import CorpusBuilder
            from tools.video.clip_search import ClipSearch
            corpus={k:v for k,v in inputs.items() if k not in ('output_dir','clips_per_query','extract_thumbnails','timeout_seconds')}
            corpus.update(corpus_dir=inputs['output_dir'],max_new_clips=4)
            built=execute(CorpusBuilder(),corpus)
            if not built.success:raise ValueError('semantic_failed')
            ranked=execute(ClipSearch(),{'operation':'rank_for_slot','corpus_dir':inputs['output_dir'],'query_text':inputs['queries'][0]['query'],'kind':'video','k':4})
            if not ranked.success:raise ValueError('semantic_failed')
            clips=[]
            for hit in ranked.data.get('results',[])[:4]:
                record=hit['record'];clips.append({**record,'path':str(Path(inputs['output_dir'])/record['local_path'])})
        # Bounded verified record fields; discard all raw errors/headers/payloads.
        fields=('clip_id','source','source_id','source_url','path','duration','width','height','creator','license','source_tags','kind')
        return {'clips':[{k:c.get(k) for k in fields} for c in clips[:4]]}
    if operation=='trim':
        from tools.video.video_trimmer import VideoTrimmer
        result=execute(VideoTrimmer(),inputs)
        if not result.success:raise ValueError('trim_failed')
        return {'output':inputs['output_path']}
    if operation=='compose':
        from tools.video.video_compose import VideoCompose
        result=execute(VideoCompose(),inputs)
        if not result.success:raise ValueError('compose_failed')
        return {'output':inputs['output_path']}
    raise ValueError('operation_invalid')


if __name__=='__main__':
    target=None
    try:
        if sys.argv[2]=='doctor':operation='doctor';inputs={}
        else:
            payload=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'));operation=payload['operation'];inputs=payload['inputs'];target=Path(payload['result_path'])
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):data=work(operation,inputs)
        result={'success':True,'data':data}
        if operation=='doctor':result.update(data)
    except Exception:result={'success':False,'category':'external_engine_failed'}
    if target:target.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    else:print(json.dumps(result))
    sys.exit(0 if result['success'] else 1)
