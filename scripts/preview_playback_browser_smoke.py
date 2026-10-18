"""Measure actual decoded browser frames across prepared 720p proxy boundaries.

Uses only disposable synthetic project data. No external AI/provider requests.
"""
import json
from pathlib import Path
import subprocess
import time
from playwright.sync_api import sync_playwright
from manual_editor_browser_smoke import SERVER


def main():
    seconds=64
    log=Path('/tmp/naman-playback-browser.log').open('w')
    server=subprocess.Popen(['.venv/bin/python','-u','-c',SERVER.replace('install_manual_example(app)',f'install_manual_example(app,seconds={seconds})')],stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        details=json.loads(server.stdout.readline());url=f'http://127.0.0.1:{details["port"]}';pid=details['pid'];base=f'{url}/api/projects/{pid}/editor'
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
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
            prepare=[]
            for t in range(0,seconds,4):
                started=time.monotonic()
                r=page.request.post(base+'/advanced/program-proxy',data={'time':float(t),'quality':'auto'});assert r.ok,r.text()
                meta=r.json()
                while meta['status']!='ready':
                    assert time.monotonic()-started<180,'Proxy preparation timed out'
                    time.sleep(.2);r=page.request.get(base+'/advanced/program-proxy-status/'+meta['key']);assert r.ok,r.text();meta=r.json()
                assert (meta['width'],meta['height'],meta['encoded_fps'])==(1280,720,30)
                prepare.append(round(time.monotonic()-started,2))
            page.goto(f'{url}/projects/{pid}/editor')
            page.wait_for_function("document.querySelectorAll('.naman-track').length===7&&!document.querySelector('#editor-content').inert")
            page.wait_for_function("Array.from(document.querySelectorAll('.advanced-program-proxy')).some(v=>!v.hidden&&v.readyState>=2)")
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
            page.locator('.workspace-monitor-deck button').filter(has_text='Oynat').first.click()
            page.wait_for_function("seconds=>document.querySelector('.naman-time-input')?.value.split(':').reduce((sum,n)=>sum*60+Number(n),0)>=seconds-.1",arg=seconds,timeout=(seconds+20)*1000)
            # Allow final queued frame callback.
            page.wait_for_timeout(100)
            measured=page.evaluate('''()=>{clearInterval(window.samplePlayback);window.observePlayback.disconnect();const f=window.playbackFrames;return {frames:f.length,seconds:(f.at(-1).now-f[0].now)/1000,fps:(f.length-1)*1000/(f.at(-1).now-f[0].now),maxGap:Math.max(...f.slice(1).map((x,i)=>(x.now-f[i].now)/1000)),sizes:[...new Set(f.map(x=>`${x.width}x${x.height}`))],samples:window.playbackSamples.length,frames_detail:f,events:window.playbackEvents};}''')
            Path('/tmp/naman-playback-metrics.json').write_text(json.dumps(measured),encoding='utf-8')
            detail=measured.pop('frames_detail');events=measured.pop('events')
            assert measured['seconds']>=seconds-2,measured
            assert measured['fps']>=27,measured
            assert measured['maxGap']<.5,measured
            assert measured['sizes']==['1280x720'],measured
            # Seeking back after the last segment must never swap in a stale queued video.
            page.locator('.naman-time-input').evaluate("e=>{e.value='00:00:08.000';e.dispatchEvent(new Event('change'));}")
            page.wait_for_function("Array.from(document.querySelectorAll('.advanced-program-proxy')).some(v=>!v.hidden&&v.readyState>=2&&v.currentTime<.1)")
            page.locator('.workspace-monitor-deck button').filter(has_text='Oynat').first.click()
            page.wait_for_function("Array.from(document.querySelectorAll('.advanced-program-proxy')).some(v=>!v.hidden&&!v.paused&&v.currentTime>1)")
            page.locator('.workspace-monitor-deck button').filter(has_text='Duraklat').first.click()
            assert not errors,errors
            print(json.dumps({'passed':True,'duration':seconds,'overlapping_layers':5,'prepare_seconds':prepare,'browser':measured,'errors':errors}))
            browser.close()
    finally:
        server.terminate();server.wait(timeout=15);log.close()


if __name__=='__main__':main()
