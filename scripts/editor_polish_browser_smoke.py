"""Real API/SQLite/Chromium group/curve/proxy checks; synthetic /tmp only."""
import json
import subprocess
from pathlib import Path
import time
from playwright.sync_api import sync_playwright
from manual_editor_browser_smoke import SERVER as BASE_SERVER
SERVER=BASE_SERVER.replace('install_manual_example(app)','install_manual_example(app,seconds=480)').replace('listener=socket.socket();',r'''
with closing(app.state.projects._connection()) as c,c:
    row=c.execute("SELECT * FROM stock_assets WHERE project_id=? AND media_type='image' LIMIT 1",(st['pid'],)).fetchone()
    for i in range(500):
        item=json.loads(row['metadata_json']);item['media_id']='perf-'+str(i);item['title']='Sentetik arşiv '+str(i)
        c.execute('INSERT INTO stock_assets VALUES (?,?,?,?,?)',(st['pid'],row['provider'],item['media_id'],'image',json.dumps(item)))
listener=socket.socket();
''')


def main():
    out=Path('/tmp/naman-polish-browser');out.mkdir(exist_ok=True)
    log=(out/'server.log').open('w');server=subprocess.Popen(['.venv/bin/python','-u','-c',SERVER],stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        data=json.loads(server.stdout.readline());base=f'http://127.0.0.1:{data["port"]}';pid=data['pid'];api=f'{base}/api/projects/{pid}/editor';metrics={};headers={'X-AI-Video-Studio':'projects'}
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'],headless=True);page=browser.new_page(viewport={'width':1366,'height':768});page.set_default_timeout(20000)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def state():return page.request.get(api+'/advanced').json()
            def wait_revision(revision):
                end=time.monotonic()+20
                while state()['revision']==revision and time.monotonic()<end:page.wait_for_timeout(50)
                assert state()['revision']>revision,page.locator('.provider-status').all_text_contents()
            def open_selection():
                if not page.locator('.advanced-selection-list').evaluate('(e)=>e.open'):page.locator('.advanced-selection-list summary').click()
            def loaded():page.locator('.manual-mode-strip').wait_for();page.locator('[aria-label="Program önizleme kalitesi"]').wait_for()
            start=time.monotonic();page.goto(f'{base}/projects/{pid}/editor');loaded();metrics['first_open_ms']=round((time.monotonic()-start)*1000,1)
            quality=page.get_by_role('combobox',name='Program önizleme kalitesi');quality.select_option('frames')
            for _ in range(2):
                revision=state()['revision'];page.get_by_role('button',name='T+ Yazı Ekle',exact=True).click();page.wait_for_function('(rev)=>document.querySelector(".advanced-program-frame")?.dataset.revision!=null',arg=revision)
                page.wait_for_timeout(100)
                end=time.monotonic()+15
                while state()['revision']==revision and time.monotonic()<end:page.wait_for_timeout(50)
                assert state()['revision']>revision
            clips=page.locator('.advanced-clip');assert clips.count()==2
            clips.last.click();open_selection();page.locator('.advanced-selection-list input').first.check();page.locator('.advanced-selection-list input').nth(1).check();page.get_by_role('spinbutton',name='Grup zaman farkı (sn)').fill('0.5');revision=state()['revision'];page.get_by_role('button',name='Grubu taşı',exact=True).click()
            wait_revision(revision);assert state()['revision']==revision+1
            assert [c['start'] for c in state()['document']['clips']]==[.5,.5]
            revision=state()['revision'];page.get_by_role('button',name='Geri al · Ctrl+Z',exact=True).click();wait_revision(revision);loaded();assert all(c['start']==0 for c in state()['document']['clips'])
            page.locator('.advanced-clip').last.click();open_selection();page.locator('.advanced-selection-list input').first.check();page.locator('.advanced-panel-tabs').get_by_role('button',name='Keyframe',exact=True).click();assert page.locator('svg[aria-label="Keyframe eğri editörü"]').count()==1
            # Fill two real points through API, then reopen and edit graph controls.
            s=state();s['document']['clips'][0]['keyframes']=[{'property':'x','time':0.,'value':-50.},{'property':'x','time':3.,'value':50.,'interpolation':'bezier','bezier':[.1,.2,.7,.9]}]
            response=page.request.put(api+'/advanced',headers=headers,data=s);assert response.status==200,response.text()
            page.reload();loaded();page.get_by_role('combobox',name='Program önizleme kalitesi').select_option('frames');page.locator('.advanced-clip').last.click();open_selection();page.locator('.advanced-selection-list input').first.check();page.locator('.advanced-panel-tabs').get_by_role('button',name='Keyframe',exact=True).click();page.get_by_role('spinbutton',name='Bezier Y1',exact=True).fill('.65');revision=state()['revision'];page.get_by_role('button',name='Kaydet ve gerçek önizlemeyi güncelle',exact=True).click();wait_revision(revision);assert state()['document']['clips'][0]['keyframes'][1]['bezier'][1]==.65
            page.get_by_role('combobox',name='Program önizleme kalitesi').select_option('low');page.wait_for_function('()=>{const v=document.querySelector(".advanced-program-proxy");return v&&!v.hidden&&v.readyState>=2}',timeout=45000)
            v=page.locator('.advanced-program-proxy');assert v.evaluate('(v)=>v.videoWidth')==320
            page.get_by_role('button',name='Oynat / Duraklat · Space',exact=True).click();page.wait_for_timeout(1400);metrics['playback_mode_and_fps']=page.locator('.advanced-preview-info').inner_text();metrics['proxy_audio_current_time']=v.evaluate('(v)=>v.currentTime');page.get_by_role('button',name='Durdur',exact=True).click()
            page.get_by_role('button',name='Kaynak',exact=True).click();page.wait_for_timeout(200);assert v.is_hidden();page.get_by_role('button',name='Program',exact=True).click()
            s=state();s['document']['clips'].append({'id':'c'*32,'kind':'motion','track':'infographics','start':0.,'end':.4,'motion':{'template':'stat','data':{'value':'40 km','label':'Rota'}}})
            response=page.request.put(api+'/advanced',headers=headers,data=s);assert response.status==200,response.text()
            page.reload();loaded();page.get_by_role('combobox',name='Program önizleme kalitesi').select_option('frames');page.locator('[data-advanced-id="'+('c'*32)+'"]').click(force=True)
            page.locator('.advanced-panel-tabs').get_by_role('button',name='Motion',exact=True).click();page.get_by_role('button',name='Kaynak nesnelerini ayrı düzenle',exact=True).click();page.get_by_role('combobox',name='Motion kaynak nesnesi').wait_for()
            page.get_by_role('checkbox',name='Nesneyi göster',exact=True).uncheck();revision=state()['revision'];page.get_by_role('button',name='Nesne ayarlarını kaydet',exact=True).click();wait_revision(revision)
            motion=next(c for c in state()['document']['clips'] if c['id']=='c'*32);assert motion['motion_elements'][0]['visible'] is False and len(motion['motion_elements'][0]['source_signature'])==64
            response=page.request.get(api+'/advanced/program-frame?time=0.2');assert response.status==200,response.text()
            metrics['motion_object_preview']='API + persisted source signature + actual FFmpeg program frame passed'
            # Real persisted dense document: seek intersects only a few of 200 clips.
            s=state();s['document']['clips']=[{'id':f'{i+1:032x}','kind':'text','track':'layers','start':round(i*2.3,4),'end':round(i*2.3+.75,4),'text':f'Katman {i}'} for i in range(200)]
            response=page.request.put(api+'/advanced',headers=headers,data=s);assert response.status==200,response.text()
            start=time.monotonic();page.reload();loaded();metrics['dense_200_open_ms']=round((time.monotonic()-start)*1000,1);start=time.monotonic();page.reload();loaded();metrics['dense_200_second_open_ms']=round((time.monotonic()-start)*1000,1);page.get_by_role('combobox',name='Program önizleme kalitesi').select_option('frames');assert page.locator('.advanced-clip').count()==200
            seek=page.get_by_role('textbox',name='Saniyeye git',exact=True);page.locator('.workspace-overflow summary').click();seek.fill('230');start=time.monotonic();seek.press('Tab');page.wait_for_function('()=>document.querySelector(".naman-time")?.textContent.includes("00:03:50.000")');metrics['seek_ui_ms']=round((time.monotonic()-start)*1000,1);page.locator('.workspace-overflow summary').click();
            start=time.monotonic();page.locator('.advanced-clip').nth(100).click(force=True);page.locator('.advanced-form').wait_for();metrics['selection_ms']=round((time.monotonic()-start)*1000,1)
            start=time.monotonic();response=page.request.get(api+'/archive');assert response.status==200;metrics['archive_api_ms']=round((time.monotonic()-start)*1000,1);metrics['archive_items']=len(response.json()['items']);metrics['project_duration_seconds']=page.request.get(api).json()['duration'];assert metrics['project_duration_seconds']==480;page.locator('.workspace-media-card').first.wait_for();card=page.locator('.workspace-media-card').first;assert card.bounding_box()['height']>=100;assert card.locator('.workspace-media-thumb').bounding_box()['height']>35;metrics['archive_card_height']=card.bounding_box()['height']
            metrics['js_heap_bytes']=page.evaluate('()=>performance.memory?.usedJSHeapSize||null')
            for width,height in [(1366,768),(1600,900),(1920,1080),(1093,614),(1280,720)]:
                page.set_viewport_size({'width':width,'height':height});assert page.locator('.naman-track').count()==7
                assert page.evaluate('()=>document.documentElement.scrollHeight<=innerHeight'),(width,height)
            page.screenshot(path=str(out/'polish-editor.png'));assert not errors,errors
            metrics['errors']=errors;metrics['platform']='Linux Chromium; Windows/WebView2 değil';metrics['proxy']='320x180 30fps encoded; measured playback field above' 
            (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2));print(json.dumps(metrics,ensure_ascii=False))
            browser.close()
    finally:
        server.terminate()
        try:server.wait(timeout=20)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        log.close()


if __name__=='__main__':main()
