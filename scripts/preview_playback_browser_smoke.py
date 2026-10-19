"""Measure actual decoded browser frames across prepared 720p proxy boundaries.

Uses only disposable synthetic project data. No external AI/provider requests.
"""
import json
from pathlib import Path
import subprocess
import time
import os
import sys
import tempfile
import shutil
from playwright.sync_api import sync_playwright
from manual_editor_browser_smoke import SERVER


def main():
    seconds=int(os.environ.get("NAMAN_PLAYBACK_SECONDS","64"))
    real_videos=os.environ.get('NAMAN_PLAYBACK_REAL_VIDEOS')=='1'
    if real_videos and seconds!=12:raise ValueError('Real video fixture uses exactly 12 seconds.')
    log=(Path(tempfile.gettempdir())/'naman-playback-browser.log').open('w')
    server_python=Path('.venv')/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    fixture=SERVER.replace('install_manual_example(app)',f'install_manual_example(app,seconds={seconds})')
    if real_videos:fixture=fixture.replace('from test_manual_first import install_manual_example','from test_source_timing import install_videos as install_manual_example')
    server=subprocess.Popen([str(server_python) if server_python.is_file() else sys.executable,'-u','-c',fixture],stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        details=json.loads(server.stdout.readline());url=f'http://127.0.0.1:{details["port"]}';pid=details['pid'];base=f'{url}/api/projects/{pid}/editor'
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('NAMAN_BROWSER_EXECUTABLE') or shutil.which('chromium'),headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(extra_http_headers={'X-AI-Video-Studio':'projects'},viewport={'width':1366,'height':768});page.set_default_timeout(30000)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            pack=page.request.get(base+'/manual/package').json();plan=pack['output_template']
            assert pack['animation_reference_selection']['catalog_count']==300
            for scene in pack['narration']:
                start=scene['start']
                while start<scene['end']:
                    end=min(scene['end'],start+30)
                    plan['animasyon_sahneleri'].append({'scene_id':scene['scene_id'],'start':start,'end':end,'data':pack['animation_capabilities']['examples']['diagram']})
                    start=end
            before=page.request.get(base+'/advanced').json()
            response=page.request.post(base+'/manual/response-draft',data={'text':json.dumps(plan)});assert response.status==201,response.text()
            draft=response.json();assert not draft['import_issues'],draft
            assert page.request.get(base+'/advanced').json()==before
            ids=[c['id'] for c in draft['clips']]
            rejected=page.request.post(base+f'/editorial/drafts/{draft["id"]}/approve',data={'confirmed':False,'clip_ids':ids});assert rejected.status==422
            approved=page.request.post(base+f'/editorial/drafts/{draft["id"]}/approve',data={'confirmed':True,'clip_ids':ids});assert approved.ok,approved.text()
            state=page.request.get(base+'/advanced').json()
            # Four additional overlapping text layers exercise multi-layer playback.
            for i in range(4):state['document']['clips'].append({'id':str(i+1)*32,'kind':'text','track':'layers','start':0.,'end':float(seconds),'text':'Belgesel '+str(i),'transform':{'y':i*90.-170.}})
            saved=page.request.put(base+'/advanced',data=state);assert saved.ok,saved.text()
            prepare=[]  # Deliberately cold: the UI schedules every proxy itself.
            opened=time.monotonic()
            page.goto(f'{url}/projects/{pid}/editor')
            page.wait_for_function("document.querySelectorAll('.naman-track').length===4&&!document.querySelector('#editor-content').inert")
            if os.environ.get('NAMAN_PLAYBACK_QUALITY')=='full':page.get_by_label('Program önizleme kalitesi',exact=True).select_option('full')
            try:page.wait_for_function("Array.from(document.querySelectorAll('.advanced-program-proxy')).some(v=>!v.hidden&&v.readyState>=2)",timeout=180000)
            except Exception:
                # Report what the monitor actually showed instead of a bare timeout.
                state=page.evaluate('''()=>({info:document.querySelector('.advanced-preview-info')?.textContent,
                  status:document.querySelector('.provider-status')?.textContent,
                  h264:typeof MediaSource!=='undefined'&&MediaSource.isTypeSupported('video/mp4; codecs="avc1.640028,mp4a.40.2"'),
                  player:typeof NAMANProgramPlayer,
                  videos:Array.from(document.querySelectorAll('.advanced-program-proxy')).map(v=>({hidden:v.hidden,ready:v.readyState,network:v.networkState,error:v.error&&v.error.code,src:(v.src||'').slice(0,40)}))})''')
                print('MONITOR STATE:',json.dumps(state,ensure_ascii=False))
                print('PAGE ERRORS:',errors[-5:])
                probe=page.request.post(base+'/advanced/program-proxy',data={'time':0,'quality':'high'})
                print('PROXY API:',probe.status,probe.text()[:400])
                log.flush();print('SERVER LOG TAIL:',(Path(tempfile.gettempdir())/'naman-playback-browser.log').read_text(errors='replace')[-700:])
                # No traceback: keep these lines inside the CI annotation tail.
                raise SystemExit('Program proxy never became visible within 180 s.')
            initial_proxy_seconds=time.monotonic()-opened
            # Observe every dynamically preloaded video, and count frames only when visible.
            page.evaluate('''()=>{
              window.playbackFrames=[];window.playbackSamples=[];window.playbackEvents=[];const seen=new WeakSet();
              const watch=()=>document.querySelectorAll('.advanced-program-proxy').forEach(v=>{
                if(seen.has(v))return;seen.add(v);['playing','pause','ended','waiting','seeking','seeked','loadeddata','error'].forEach(name=>v.addEventListener(name,()=>window.playbackEvents.push({name,now:performance.now(),media:v.currentTime,src:v.src,hidden:v.hidden}))); 
                const frame=(now,m)=>{if(!v.hidden&&!v.paused)window.playbackFrames.push({now,media:m.mediaTime,width:v.videoWidth,height:v.videoHeight,src:v.src});if(v.isConnected)v.requestVideoFrameCallback(frame);};
                v.requestVideoFrameCallback(frame);
              });watch();window.observePlayback=new MutationObserver(watch);window.observePlayback.observe(document.body,{childList:true,subtree:true});
              window.samplePlayback=setInterval(()=>{const v=[...document.querySelectorAll('.advanced-program-proxy')].find(v=>!v.hidden);window.playbackSamples.push({now:performance.now(),visible:!!v,playing:!!v&&!v.paused,media:v?.currentTime});},50);
            }''')
            started=time.monotonic()
            page.locator('.workspace-monitor-deck button').filter(has_text='Oynat').first.click()
            page.wait_for_function("Array.from(document.querySelectorAll('.advanced-program-proxy')).some(v=>!v.hidden&&!v.paused&&v.currentTime>.05)",timeout=240000)
            startup_seconds=time.monotonic()-started
            page.wait_for_function("seconds=>document.querySelector('.naman-time-input')?.value.split(':').reduce((sum,n)=>sum*60+Number(n),0)>=seconds-.1",arg=seconds,timeout=(seconds+20)*1000)
            # Allow final queued frame callback.
            page.wait_for_timeout(100)
            measured=page.evaluate('''()=>{clearInterval(window.samplePlayback);window.observePlayback.disconnect();const f=window.playbackFrames;return {frames:f.length,seconds:(f.at(-1).now-f[0].now)/1000,fps:(f.length-1)*1000/(f.at(-1).now-f[0].now),maxGap:Math.max(...f.slice(1).map((x,i)=>(x.now-f[i].now)/1000)),sizes:[...new Set(f.map(x=>`${x.width}x${x.height}`))],samples:window.playbackSamples.length,frames_detail:f,events:window.playbackEvents};}''')
            (Path(tempfile.gettempdir())/'naman-playback-metrics.json').write_text(json.dumps(measured),encoding='utf-8')
            detail=measured.pop('frames_detail');events=measured.pop('events')
            assert len({f['src'] for f in detail})==1 and detail[0]['src'].startswith('blob:'), 'Continuous decoder was replaced'
            boundary_gaps=[(b['now']-a['now'])/1000 for a,b in zip(detail,detail[1:]) if int(a['media']/4)!=int(b['media']/4)]
            measured['maxBoundaryGap']=max(boundary_gaps,default=0)
            assert measured['maxBoundaryGap']<.067,measured
            assert not any(e['name']=='waiting' and .1<e['media']<seconds-.1 for e in events),events
            assert measured['seconds']>=seconds-2,measured
            assert measured['fps']>=29,measured
            assert measured['maxGap']<.12,measured
            assert measured['sizes']==(['1920x1080'] if os.environ.get('NAMAN_PLAYBACK_QUALITY')=='full' else ['1280x720']),measured
            playing=page.locator('.workspace-monitor-deck button').filter(has_text='Duraklat')
            if playing.count():playing.first.click()
            # Seeking back after the last segment must never swap in a stale queued video.
            page.locator('.naman-time-input').evaluate("e=>{e.value='00:00:08.000';e.dispatchEvent(new Event('change'));}")
            page.wait_for_function("Array.from(document.querySelectorAll('.advanced-program-proxy')).some(v=>!v.hidden&&v.readyState>=2&&v.currentTime>=8&&v.currentTime<8.15)")
            page.locator('.workspace-monitor-deck button').filter(has_text='Oynat').first.click()
            page.wait_for_function("Array.from(document.querySelectorAll('.advanced-program-proxy')).some(v=>!v.hidden&&!v.paused&&v.currentTime>9)")
            page.locator('.workspace-monitor-deck button').filter(has_text='Duraklat').first.click()
            # Audio settings are saved independently of the timeline revision.
            # They must invalidate the existing muxed buffer as well.
            before_mix=page.request.get(base+'/advanced').json()
            previous_src=page.locator('.advanced-program-proxy').evaluate('v=>v.currentSrc')
            page.get_by_label('Diğer araçlar',exact=True).click()
            page.get_by_role('button',name='Ses miks ayarları',exact=True).click()
            page.get_by_label('Anlatım ses seviyesi',exact=True).fill('0.5')
            page.get_by_role('button',name='Ses miks ayarlarını kaydet',exact=True).click()
            page.wait_for_function("src=>[...document.querySelectorAll('.advanced-program-proxy')].some(v=>v.currentSrc!==src&&!v.hidden&&v.readyState>=2)",arg=previous_src,timeout=60000)
            assert page.request.get(base).json()['audio_settings']['narration_volume']==.5
            assert page.request.get(base+'/advanced').json()['document']==before_mix['document']
            assert not errors,errors
            result={'passed':True,'duration':seconds,'real_video_sources':real_videos,'overlapping_layers':5,'initial_proxy_seconds':round(initial_proxy_seconds,2),'startup_seconds':round(startup_seconds,2),'cold_cache':True,'browser':measured,'errors':errors}
            Path(os.environ.get('NAMAN_PLAYBACK_REPORT',str(Path(tempfile.gettempdir())/'naman-playback-results.json'))).write_text(json.dumps(result),encoding='utf-8')
            print(json.dumps(result))
            browser.close()
    finally:
        server.terminate();server.wait(timeout=15);log.close()


if __name__=='__main__':main()
