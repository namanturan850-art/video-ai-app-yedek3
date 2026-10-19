"""Real local API/SQLite/Chromium + 4 s FFmpeg flow; only disposable synthetic data."""
import json
from pathlib import Path
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

SERVER=r'''
import sys,json,tempfile,socket
from pathlib import Path
sys.path.insert(0,'tests')
from app.main import create_app
from app.database import initialize_database
from test_manual_first import install_manual_example
import uvicorn
storage=Path(tempfile.mkdtemp(prefix='naman-manual-ui-',dir=tempfile.gettempdir()));initialize_database(storage)
app=create_app(storage);st=install_manual_example(app)
from contextlib import closing
from app.editor.service import VIDEO_REVIEW_VERSION
report={'render_version_id':'synthetic-report','basis':'Sentetik kayıtlı rapor UI testi; canlı Gemini çağrısı yapılmadı.','summary':'Yerel bulgu akışı',
        'issues':[{'timecode':1.,'category':'Metin','message':'Örnek bulgu','confidence':'medium','suggestion':'Bu aralığı elle kontrol edin.'}]}
with closing(app.state.projects._connection()) as c,c:c.execute('INSERT INTO archive_analysis_cache VALUES (?,?,?,?,?)',(st['pid'],'a'*64,VIDEO_REVIEW_VERSION,json.dumps(report),'test'))
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(64)
print(json.dumps({'pid':st['pid'],'port':listener.getsockname()[1],'storage':str(storage)}),flush=True)
uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False)).run(sockets=[listener])
'''


def main():
    output=Path('/tmp/naman-manual-browser');output.mkdir(exist_ok=True)
    log=(output/'server.log').open('w');server=subprocess.Popen(['.venv/bin/python','-u','-c',SERVER],stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        details=json.loads(server.stdout.readline());url=f'http://127.0.0.1:{details["port"]}';pid=details['pid'];endpoint=f'{url}/api/projects/{pid}/editor'
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1366,'height':768});page.set_default_timeout(15000)
            errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
            def state():return page.request.get(endpoint+'/advanced').json()
            def ready():
                page.locator('.manual-mode-strip').wait_for()
                page.wait_for_function("document.querySelector('[aria-label=\"Geri al · Ctrl+Z\"]')?.disabled===false&&document.querySelector('#editor-content')?.dataset.loading!=='1'&&document.querySelector('#editor-content')?.dataset.editing!=='1'")
            def saved(revision):
                page.wait_for_function('async a=>(await (await fetch(a.url)).json()).revision>a.rev',arg={'url':endpoint+'/advanced','rev':revision})
                page.wait_for_function("!document.querySelector('.naman-inspector')?.dataset.saving")
            def seek(time):
                page.locator('.workspace-overflow summary').click();box=page.get_by_role('textbox',name='Saniyeye git',exact=True);box.fill(str(time));box.press('Tab');page.locator('.workspace-overflow summary').click()
            page.goto(f'{url}/projects/{pid}/editor');ready()
            assert page.get_by_role('combobox',name='Kurgu modu',exact=True).input_value()=='manual'
            view=page.request.get(endpoint).json();assert not view['tracks']['emphasis'] and not view['tracks']['layers']
            for item in (x for values in view['tracks'].values() for x in values if x.get('slot_id')):
                response=page.request.get(url+item['preview_url']);assert response.status==200,response.text()
            metrics=page.evaluate("()=>({deck:document.querySelector('.workspace-monitor-deck').getBoundingClientRect().top,frame:document.querySelector('.workspace-program-surface').getBoundingClientRect().bottom,rail:document.querySelectorAll('.workspace-tool-rail button').length})")
            assert metrics['deck']>=metrics['frame']-1 and metrics['rail']==9,metrics
            first=next(item for items in view['tracks'].values() for item in items if item.get('slot_id'))
            page.locator(f'.naman-clip[data-slot-id="{first["slot_id"]}"]').click();page.get_by_role('button',name='Sil · Delete',exact=True).click();page.locator('.empty-slot').wait_for()
            assert state()['document']['empty_slots']==[first['slot_id']]
            page.get_by_role('button',name='Geri al · Ctrl+Z',exact=True).click();page.locator('.empty-slot').wait_for(state='detached');ready()
            page.get_by_role('button',name='Yinele · Ctrl+Shift+Z',exact=True).click();page.locator('.empty-slot').wait_for();ready()
            page.locator('.empty-slot').click();page.locator('.workspace-media-card').filter(has_text='Sentetik görsel').click()
            page.get_by_role('button',name='Seçili görüntü yuvasına ata',exact=True).click();page.locator('.empty-slot').wait_for(state='detached');ready()
            assert not state()['document']['empty_slots']
            seek(0);revision=state()['revision'];page.get_by_role('button',name='T+ Yazı Ekle',exact=True).click();saved(revision)
            page.locator('.workspace-inspector > .workspace-tabs').get_by_role('tab',name='Metin',exact=True).click()
            page.locator('.advanced-form textarea').fill('Texto manual — Roma')
            page.get_by_label('Font',exact=True).select_option('montserrat');page.get_by_label('Kalınlık',exact=True).select_option('bold');page.get_by_label('Arka plan kutusu',exact=True).check()
            revision=state()['revision'];page.get_by_role('button',name='Kaydet ve gerçek önizlemeyi güncelle',exact=True).click();saved(revision)
            assert state()['document']['clips'][0]['font']=='montserrat'
            frame=page.request.get(endpoint+'/advanced/program-frame?time=0');assert frame.status==200,frame.text()
            page.locator('.advanced-panel-tabs').get_by_role('button',name='Keyframe',exact=True).click();page.locator('.advanced-form>select').select_option('scale')
            revision=state()['revision'];page.get_by_role('button',name='İmleçte keyframe ekle',exact=True).click();saved(revision)
            seek(1);revision=state()['revision'];page.get_by_role('button',name='İmleçte keyframe ekle',exact=True).click();saved(revision)
            page.get_by_role('spinbutton',name='Keyframe değeri',exact=True).nth(1).fill('1.2');revision=state()['revision'];page.get_by_role('button',name='Kaydet ve gerçek önizlemeyi güncelle',exact=True).click();saved(revision)
            seek(0);page.get_by_role('button',name='+ Harita Ekle',exact=True).click()
            dialog=page.locator('.manual-dialog[open]');dialog.get_by_label('Yer adı',exact=True).fill('Roma');dialog.get_by_label('Etiket',exact=True).fill('');dialog.get_by_label('Enlem',exact=True).fill('41.9');dialog.get_by_label('Boylam',exact=True).fill('12.5');dialog.get_by_label('Bitiş',exact=True).fill('0.3')
            revision=state()['revision'];dialog.get_by_role('button',name='Yerel katmanı doğrula ve ekle',exact=True).click();saved(revision)
            assert any(c['clean_map'] for c in state()['document']['clips'])
            seek(.5);page.get_by_role('button',name='+ İnfografik Ekle',exact=True).click();dialog=page.locator('.manual-dialog[open]');dialog.get_by_label('Değer',exact=True).fill('40');dialog.get_by_label('Etiket',exact=True).fill('kilómetros');dialog.get_by_label('Bitiş',exact=True).fill('0.8')
            revision=state()['revision'];dialog.get_by_role('button',name='Yerel katmanı doğrula ve ekle',exact=True).click();saved(revision)
            page.locator('.naman-clip[data-track=subtitles]').first.click();page.get_by_label('Altyazı metni',exact=True).fill('Subtítulo corregido')
            page.get_by_label('Önemli yer olarak göster',exact=True).check();page.get_by_role('button',name='Altyazı revizyonunu kaydet',exact=True).click();ready()
            page.wait_for_function("document.querySelector('.naman-caption')?.textContent.includes('Subtítulo')")
            subtitle_state=page.request.get(f'{url}/api/projects/{pid}/subtitles').json()['active'];cue=subtitle_state['cues'][0]
            page.locator('.naman-clip[data-track=subtitles]').first.click();stock_before=page.request.get(endpoint).json()['stock_revision']
            page.get_by_role('button',name='Çoğalt',exact=True).click()
            assert page.request.get(endpoint).json()['stock_revision']==stock_before
            page.get_by_role('button',name='Kes/Böl · C',exact=True).click();clip=page.locator('.naman-clip[data-track=subtitles]').first;bounds=clip.bounding_box();clip.click(position={'x':bounds['width']/2,'y':bounds['height']/2})
            page.wait_for_function('async a=>(await (await fetch(a.url)).json()).active.cues.length===a.count',arg={'url':f'{url}/api/projects/{pid}/subtitles','count':len(subtitle_state['cues'])+1});ready();page.get_by_role('button',name='Seçim · V',exact=True).click()
            page.locator('.workspace-monitor-deck input[type=range]').evaluate("e=>{e.value='80';e.dispatchEvent(new Event('input',{bubbles:true}));}");page.wait_for_function("document.querySelector('.workspace-monitor-deck input[type=range]')?.value==='80'")
            subtitle_url=f'{url}/api/projects/{pid}/subtitles';before_sub=page.request.get(subtitle_url).json()['active']
            trim=page.locator('.naman-clip[data-track=subtitles] .trim-handle.left').first.bounding_box()
            page.mouse.move(trim['x']+trim['width']/2,trim['y']+trim['height']/2);page.mouse.down();page.mouse.move(trim['x']+trim['width']/2+9,trim['y']+trim['height']/2,steps=4);page.mouse.up()
            page.wait_for_function('async a=>(await (await fetch(a.url)).json()).active.id!==a.id',arg={'url':subtitle_url,'id':before_sub['id']});ready()
            trimmed=page.request.get(subtitle_url).json()['active'];assert trimmed['cues'][0]['start']>before_sub['cues'][0]['start']
            box=page.locator('.naman-clip[data-track=subtitles]').first.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
            page.mouse.move(x,y);page.mouse.down();page.mouse.move(x-9,y,steps=4);page.mouse.up()
            page.wait_for_function('async a=>(await (await fetch(a.url)).json()).active.id!==a.id',arg={'url':subtitle_url,'id':trimmed['id']});ready()
            moved=page.request.get(subtitle_url).json()['active']['cues'][0];assert moved['start']<trimmed['cues'][0]['start']
            assert abs((moved['end']-moved['start'])-(trimmed['cues'][0]['end']-trimmed['cues'][0]['start']))<.001
            page.get_by_role('combobox',name='Altyazı gösterimi',exact=True).select_option('emphasis');ready()
            seek(0);page.get_by_role('button',name='+ Ses / Müzik',exact=True).click();dialog=page.locator('.manual-dialog[open]');dialog.get_by_label('Bitiş',exact=True).fill('3');dialog.get_by_label('Konuşmada kıs (ducking)',exact=True).check()
            revision=state()['revision'];dialog.get_by_role('button',name='Seçilen sesi timeline’a ekle',exact=True).click();saved(revision)
            count=len(state()['document']['clips']);page.reload();ready();assert len(state()['document']['clips'])==count
            assert page.get_by_role('combobox',name='Altyazı gösterimi',exact=True).input_value()=='emphasis'
            assert page.locator('.workspace-menubar summary').all_text_contents()==['Dosya','Düzen','Görünüm']
            assert page.get_by_role('button',name='Otomatik Kurgu — Taslak',exact=True).count()==0
            page.get_by_role('button',name='Manuel Plan / AI paketi',exact=True).click();dialog=page.locator('.manual-dialog[open]')
            before=state();package=page.request.get(endpoint+'/manual/package').json()
            page.route('**/manual/package/prepare',lambda route:route.fulfill(json={**package,'prepared_by':'gemini','gemini_instructions':['Sentetik paket görevi']}))
            page.once('dialog',lambda d:d.accept());dialog.get_by_role('button',name='Gemini ile talimat ekle (ücretli)',exact=True).click()
            page.wait_for_function("document.querySelector('[aria-label=\"Hazır AI paketi\"]')?.value.includes('gemini_instructions')")
            assert state()==before
            dialog.get_by_label('Dış yapay zekâ cevabı',exact=True).fill('{bad json');dialog.get_by_role('button',name='Planı içe aktar',exact=True).click()
            page.wait_for_function("document.querySelector('.manual-dialog[open] .naman-json-message')?.textContent.includes('geçerli JSON')")
            dialog.get_by_role('button',name='Kapat',exact=True).click()
            pack=page.request.get(endpoint+'/manual/package').json()['output_template']
            for key in ('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar'):pack[key]=[]
            scene=view['scenes'][0];pack['katmanlar']=[{'scene_id':scene['scene_id'],'text':scene['narration'].split('.')[0],'start':scene['start'],'end':scene['end']}]
            page.get_by_role('button',name='Manuel Plan / AI paketi',exact=True).click();dialog=page.locator('.manual-dialog[open]');dialog.get_by_label('Dış yapay zekâ cevabı',exact=True).fill('Plan hazır:\n```json\n'+json.dumps(pack)+'\n```');dialog.get_by_role('button',name='Planı içe aktar',exact=True).click();dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).wait_for()
            assert len(state()['document']['clips'])==count
            revision=state()['revision'];dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).click();saved(revision);ready()
            assert len(state()['document']['clips'])==count+1
            page.get_by_role('button',name='Geri al · Ctrl+Z',exact=True).click();page.wait_for_function('async a=>(await (await fetch(a.url)).json()).document.clips.length===a.count',arg={'url':endpoint+'/advanced','count':count});ready()
            page.locator('.workspace-overflow summary').click();page.get_by_role('button',name='Gemini ile Videoyu Kontrol Et',exact=True).click();dialog=page.locator('.manual-dialog[open]');assert dialog.get_by_role('button',name='Onayla ve örnek kare analizi başlat',exact=True).is_disabled();assert not any('/quality/review-request' in r for r in requests);dialog.get_by_role('button',name='Kayıtlı raporları aç — servis çağrısı yapmaz',exact=True).click();dialog.get_by_role('button',name='Çözüldü',exact=True).click();page.wait_for_function("document.querySelector('.manual-review-finding strong')?.textContent.includes('resolved')");dialog.get_by_role('button',name='Zaman koduna git',exact=True).click();page.locator('.workspace-overflow summary').click();seek(0)
            assert not any('/quality/review-request' in r for r in requests)
            revision=state()['revision']
            page.wait_for_function("rev=>{const image=document.querySelector('.advanced-program-frame');return image?.naturalWidth===640&&+image.dataset.revision===rev;}",arg=revision,timeout=30000)
            for width,height in [(1366,768),(1600,900),(1920,1080),(1650,900),(1093,614)]:
                page.set_viewport_size({'width':width,'height':height});metrics=page.evaluate("()=>({height:innerHeight,scroll:document.documentElement.scrollHeight,tracks:[...document.querySelectorAll('.naman-track')].map(n=>n.getBoundingClientRect().bottom),bottom:document.querySelector('.naman-timeline').getBoundingClientRect().bottom})")
                assert metrics['scroll']<=height and len(metrics['tracks'])==4 and max(metrics['tracks'])<=metrics['bottom'],metrics
                page.screenshot(path=str(output/f'manual-{width}x{height}.png'))
            page.goto(f'{url}/projects/{pid}/render');page.locator('#render-create').wait_for()
            page.wait_for_function("document.querySelector('#render-editing-style')?.disabled===true")
            contrast=page.locator('.music-panel').evaluate("el=>({background:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color})")
            assert contrast['background'] in ('rgb(35, 35, 39)','rgb(44, 44, 50)'),contrast
            assert page.locator('#render-engine').input_value()=='native' and page.locator('#render-music-enabled').is_disabled()
            page.screenshot(path=str(output/'render-music.png'))
            assert not errors,errors
            response=page.request.post(f'{url}/api/projects/{pid}/render/jobs',headers={'X-AI-Video-Studio':'projects'},data={'encoder':'cpu'})
            assert response.status==202,response.text();job=response.json()
            deadline=time.monotonic()+120
            while True:
                result=page.request.get(f'{url}/api/projects/{pid}/render').json()
                assert result.get('job',{}).get('status') not in ('error','cancelled'),result
                if result.get('job',{}).get('status')=='completed':break
                assert time.monotonic()<deadline,result
                page.wait_for_timeout(250)
            assert result['active'],result
            assert abs(result['active']['metadata']['duration']-4)<.04
            assert result['active']['metadata']['advanced_editor']['clips']==count
            browser.close()
        print(json.dumps({'passed':True,'project':pid,'storage':details['storage'],'checks':['manual defaults/no automatic layers','monitor controls/9 tools','base delete/undo/redo/refill','text style/keyframes','clean map','infographic','subtitle real version/important mode','timeline music/ducking','reopen','JSON validation/approval/undo','Gemini package mock/read-only timeline','Gemini consent/cached finding/status/timecode/no call','five viewport layouts','dark music panel','real 4-second FFmpeg output'],'artifacts':str(output)},ensure_ascii=False))
    except Exception:
        print('BROWSER ERRORS',locals().get('errors',[]),flush=True)
        raise
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        log.close()


if __name__=='__main__':main()
