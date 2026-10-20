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
import re
import subprocess
import sys
import threading
import time

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


STALL_SECONDS=300  # no new frame for this long = the renderer is stuck
TOTAL_SECONDS=7200
FRAMES=re.compile(r'(Rendered|Encoded)\s+(\d+)/(\d+)')


def report(fraction):
    # Our parent reads `out_time_us` lines from this process's real stdout.
    real=sys.__stdout__
    if real:
        real.write(f'out_time_us={int(max(0,min(1,fraction))*1_000_000)}\n');real.flush()


def render_with_progress(args,cwd,timeout):
    """Remotion render: real frame progress to the parent, stall watchdog instead of a flat cap."""
    process=subprocess.Popen(args,cwd=cwd,shell=False,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    state={'fraction':0.,'seen':time.monotonic(),'tail':''}

    def read():
        buffer=''
        while True:
            char=process.stdout.read(1)
            if not char:break
            if char not in '\r\n':
                buffer+=char
                if len(buffer)>400:buffer=buffer[-200:]
                continue
            state['tail']=(state['tail']+buffer+'\n')[-2000:]  # in-process diagnostics only; main() never returns it
            match=FRAMES.search(buffer);buffer=''
            if match and int(match.group(3)):
                part=int(match.group(2))/int(match.group(3))
                fraction=part*.9 if match.group(1)=='Rendered' else .9+part*.1
                if fraction>state['fraction']:
                    state['fraction']=fraction;state['seen']=time.monotonic();report(fraction)
    reader=threading.Thread(target=read,daemon=True);reader.start()
    started=time.monotonic();limit=min(timeout or TOTAL_SECONDS,TOTAL_SECONDS)
    try:
        while process.poll() is None:
            time.sleep(1)
            now=time.monotonic()
            if now-state['seen']>STALL_SECONDS or now-started>limit:
                process.kill();raise RuntimeError('external_command_stalled')
    finally:
        if process.poll() is None:process.kill()
        reader.join(5)
    if process.returncode:raise RuntimeError('external_command_failed: '+state['tail'][-1500:])
    report(1.)
    return subprocess.CompletedProcess(args,0,'','')


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
    if args[0]==shutil.which('node') and 'render' in args[:4]:return render_with_progress(args,cwd,timeout)
    result=subprocess.run(args,cwd=cwd,shell=False,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=min(timeout or 1800,1800))
    if result.returncode:raise RuntimeError('external_command_failed')
    return result


_VISUAL = None


def work(operation,inputs):
    global _VISUAL
    if _VISUAL is None:
        spec=importlib.util.spec_from_file_location('avs_visual_engine',Path(__file__).with_name('visual_engine.py'))
        _VISUAL=importlib.util.module_from_spec(spec);spec.loader.exec_module(_VISUAL)
    visual=_VISUAL
    if operation in ('visual','semantic','frames'):
        status=visual.model_status(ROOT)
        if not status:raise ValueError('semantic_model_missing')
        os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        if operation=='visual':return visual.analyse(ROOT,inputs,command)
        if operation=='frames':return visual.score_frames(ROOT,inputs)
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
        names=[s.name for s in available_sources() if s.name in (*FREE,'pixabay_video')]
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
    if operation=='html_layer':
        # NAMAN's own sanitized HTML/CSS layer -> transparent PNG frames.
        composer=(ROOT/'remotion-composer').resolve();projects=composer/'projects'
        entry=Path(inputs['entry']).resolve();props=Path(inputs['props_path']).resolve();out=Path(inputs['output_dir']).resolve()
        if entry.name!='index.tsx' or props.name!='props.json' or not entry.is_relative_to(projects) or not props.is_relative_to(projects):raise ValueError('path_invalid')
        if out.is_relative_to(ROOT) or not out.is_dir():raise ValueError('path_invalid')
        frames=inputs['frames']
        if type(frames) is not int or not 1<=frames<=30*30:raise ValueError('frames_invalid')
        command(['npx','remotion','render',str(entry),'NAMANHtmlLayer',str(out),'--sequence','--image-format=png',
                 '--props='+str(props),'--concurrency=1'],timeout=1800,cwd=composer)
        made=[p for p in out.iterdir() if p.suffix.lower()=='.png']
        if len(made)!=frames:raise ValueError('frames_missing')
        return {'output':str(out),'frames':len(made)}
    raise ValueError('operation_invalid')


def failure_detail(error):
    """The real reason CLIP stopped (class, short message, where, torch/GPU state).
    Goes only to the diagnostics file; the frames job sends no credentials."""
    import traceback
    text=' '.join(str(error).split())[:240]
    try:
        last=traceback.extract_tb(error.__traceback__)[-1];where=f' @ {Path(last.filename).name}:{last.lineno}'
    except Exception:where=''
    info=''
    torch=sys.modules.get('torch')
    if torch is not None:
        try:info=f' [torch {torch.__version__}; cuda={bool(torch.cuda.is_available())}]'
        except Exception:info=' [torch bilgisi okunamadı]'
    return {'error_class':type(error).__name__,'detail':text+where+info}


def serve_frames():
    # One sequential model owner; module/model objects survive between batches.
    for line in sys.stdin:
        try:
            if len(line)>2_000_000:raise ValueError('input_too_large')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                data=work('frames',json.loads(line))
            result={'success':True,'data':data}
        except Exception as error:
            result={'success':False,'category':'external_engine_failed',**failure_detail(error)}
        sys.__stdout__.write(json.dumps(result)+'\n');sys.__stdout__.flush()


if __name__=='__main__' and sys.argv[2]=='--serve-frames':
    serve_frames()
elif __name__=='__main__':
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
