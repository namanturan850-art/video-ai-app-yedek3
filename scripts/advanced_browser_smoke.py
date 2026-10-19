"""Isolated real API + Chromium test; creates only synthetic projects under /tmp.

Run with the development machine's Playwright Python. The backend uses .venv.
No existing user project or external provider is used.
"""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

SERVER = r'''
import sys,json,tempfile,hashlib,socket
from pathlib import Path
from contextlib import closing
sys.path.insert(0,'tests')
from app.main import create_app
from app.database import initialize_database
from app.stock.service import fingerprint
from test_rendering import install_ready
import uvicorn
storage=Path(tempfile.mkdtemp(prefix='naman-advanced-api-',dir='/tmp'))
initialize_database(storage);app=create_app(storage);seed=install_ready(app);pid=seed['pid']
with closing(app.state.projects._connection()) as c,c:
    stock=json.loads(c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone()[0])
    stock.update(handoff_fingerprint=fingerprint(app.state.production.handoff(pid)),bindings={},warnings=[])
    for slot in stock['slots']:
        slot['locked']=False;media=slot['selected_media'];path=seed['root']/media['local_path']
        media.update(width=320,height=240,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),title='Sentetik video' if media['media_type']=='video' else 'Sentetik görsel',has_audio=media['media_type']=='video')
        c.execute('INSERT OR REPLACE INTO stock_assets VALUES (?,?,?,?,?)',(pid,media['provider'],media['media_id'],media['media_type'],json.dumps(media)))
    c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(stock),pid))
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(64);port=listener.getsockname()[1]
print(json.dumps({'pid':pid,'port':port,'storage':str(storage)}),flush=True)
server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
server.run(sockets=[listener])
'''


def main():
    output=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/naman-advanced-browser');output.mkdir(exist_ok=True,parents=True)
    log=(output/'server.log').open('w')
    process=subprocess.Popen(['.venv/bin/python','-u','-c',SERVER],stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        details=json.loads(process.stdout.readline());url=f'http://127.0.0.1:{details["port"]}';pid=details['pid']
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1366,'height':768});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'{url}/projects/{pid}/editor');page.locator('.advanced-monitor-tabs').wait_for()
            page.locator('.workspace-media-card').filter(has_text='Sentetik görsel').click()
            page.locator('.workspace-overflow summary').click()
            page.get_by_role('button',name='Seçili arşivi imlece ekle',exact=True).click()
            try:page.locator('.advanced-clip').wait_for(timeout=15000)
            except Exception:
                print('ADD CLIP FAILURE',page.locator('.workspace-statusbar .provider-status').inner_text(),page.request.get(f'{url}/api/projects/{pid}/editor/advanced').json(),errors,flush=True)
                page.screenshot(path=str(output/'failure.png'));raise
            page.locator('.workspace-overflow summary').click()
            page.locator('.advanced-clip').click()
            page.get_by_role('button',name='Efektler',exact=True).click()
            page.get_by_label('Parlaklık',exact=True).fill('0.15')
            page.get_by_label('Siyah-beyaz',exact=True).check()
            page.get_by_role('button',name='Kaydet ve gerçek önizlemeyi güncelle',exact=True).click()
            page.wait_for_function("!document.querySelector('.naman-inspector')?.dataset.saving")
            page.get_by_role('button',name='Keyframe',exact=True).click()
            page.locator('.advanced-form>select').select_option('scale')
            page.get_by_role('button',name='İmleçte keyframe ekle',exact=True).click()
            page.locator('.advanced-keyframe').wait_for()
            page.locator('.workspace-overflow summary').click()
            seek=page.get_by_role('textbox',name='Saniyeye git',exact=True);seek.fill('00:00:01.000');seek.press('Tab')
            page.locator('.workspace-overflow summary').click()
            page.locator('.advanced-form>select').select_option('scale')
            page.get_by_role('button',name='İmleçte keyframe ekle',exact=True).click()
            page.locator('.advanced-keyframe').nth(1).wait_for()
            page.get_by_role('spinbutton',name='Keyframe değeri',exact=True).nth(1).fill('1.5')
            page.get_by_role('button',name='Kaydet ve gerçek önizlemeyi güncelle',exact=True).click()
            page.wait_for_function("!document.querySelector('.naman-inspector')?.dataset.saving")
            doc=page.request.get(f'{url}/api/projects/{pid}/editor/advanced').json()
            assert len(doc['document']['clips'][0]['keyframes'])==2,doc
            assert doc['document']['clips'][0]['effects']['monochrome']
            page.get_by_label('İşaretleyiciler menüsü',exact=True).click()
            page.get_by_role('button',name='İmleçte işaretleyici ekle',exact=True).click()
            page.get_by_role('textbox',name='Ad',exact=True).fill('Gerçek kayıt')
            page.get_by_role('button',name='İşaretleyiciyi kaydet',exact=True).click()
            page.locator('.advanced-marker').wait_for();page.keyboard.press('Escape')
            page.reload();page.locator('.advanced-marker').wait_for();page.locator('.advanced-clip').wait_for()
            endpoint=f'{url}/api/projects/{pid}/editor/advanced'
            def saved_after(revision):
                page.wait_for_function("async a=>(await (await fetch(a.url)).json()).revision>a.revision",arg={'url':endpoint,'revision':revision})
                page.wait_for_function("!document.querySelector('.naman-inspector')?.dataset.saving")
            def document():return page.request.get(endpoint).json()
            # Keyframe deletion is a real write; independent supplementary history restores it.
            page.locator('.advanced-clip').click()
            page.get_by_role('button',name='Keyframe',exact=True).click()
            revision=document()['revision']
            page.locator('.advanced-keyframe').last.get_by_role('button',name='Sil',exact=True).click()
            saved_after(revision);assert len(document()['document']['clips'][0]['keyframes'])==1
            page.locator('.workspace-overflow summary').click()
            revision=document()['revision'];page.get_by_role('button',name='Ek kurgu geri al',exact=True).click();saved_after(revision)
            assert len(document()['document']['clips'][0]['keyframes'])==2
            page.locator('.workspace-overflow summary').click()
            # Marker update/delete/undo is persistent and scoped to this test project.
            page.locator('.advanced-marker').click();page.get_by_role('textbox',name='Not',exact=True).fill('Kalıcı not')
            revision=document()['revision'];page.get_by_role('button',name='İşaretleyiciyi kaydet',exact=True).click();saved_after(revision)
            assert document()['document']['markers'][0]['note']=='Kalıcı not'
            page.locator('.advanced-marker').click();revision=document()['revision'];page.locator('.advanced-dialog').get_by_role('button',name='Sil',exact=True).click();saved_after(revision)
            assert not document()['document']['markers']
            page.locator('.workspace-overflow summary').click();revision=document()['revision'];page.get_by_role('button',name='Ek kurgu geri al',exact=True).click();saved_after(revision)
            page.locator('.workspace-overflow summary').click()
            # Leave room to move the clip without changing the narration duration.
            page.locator('.advanced-clip').click();page.get_by_label('Bitiş (sn)',exact=True).fill('2')
            revision=document()['revision'];page.get_by_role('button',name='Kaydet ve gerçek önizlemeyi güncelle',exact=True).click();saved_after(revision)
            bounds=page.locator('.advanced-clip').bounding_box();revision=document()['revision']
            page.mouse.move(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2);page.mouse.down();page.mouse.move(bounds['x']+bounds['width']/2+12,bounds['y']+bounds['height']/2,steps=5);page.mouse.up();saved_after(revision)
            assert document()['document']['clips'][0]['start']>0
            # Delete removes a timeline reference, and Undo restores its source and edits.
            page.locator('.advanced-clip').click();page.locator('.advanced-clip').focus();revision=document()['revision'];page.keyboard.press('Delete');saved_after(revision)
            assert not document()['document']['clips']
            page.locator('.workspace-overflow summary').click();revision=document()['revision'];page.get_by_role('button',name='Ek kurgu geri al',exact=True).click();saved_after(revision)
            page.locator('.workspace-overflow summary').click();assert len(document()['document']['clips'])==1
            page.wait_for_function("document.querySelector('.advanced-program-frame')?.naturalWidth===640",timeout=30000)
            archive=page.request.get(f'{url}/api/projects/{pid}/editor/archive').json()
            video=next(item for item in archive['items'] if item['media_type']=='video')
            thumbnail=page.request.get(url+video['thumbnail_url'])
            assert thumbnail.status==200,(thumbnail.status,thumbnail.text() if thumbnail.status!=200 else '')
            thumb=page.locator('img[data-thumbnail]').first
            if not thumb.count():print('THUMBNAIL DOM',page.locator('.workspace-media-grid').inner_html(),flush=True)
            thumb.wait_for()
            page.wait_for_function("document.querySelector('img[data-thumbnail]')?.naturalWidth===240",timeout=30000)
            # Source playback uses its own clock and Program pauses it when returning.
            page.locator('.workspace-media-card').filter(has_text='Sentetik video').click()
            before=page.locator('.naman-time-input').input_value()
            page.get_by_role('button',name='Kaynak',exact=True).click()
            page.locator('.workspace-source-media video').evaluate('(v)=>v.play()')
            page.wait_for_function("document.querySelector('.workspace-source-media video').currentTime>0.05")
            assert page.locator('.naman-time-input').input_value()==before
            page.get_by_role('button',name='Yan yana',exact=True).click();assert page.locator('.advanced-dual').count()==1
            page.get_by_role('button',name='Program',exact=True).click()
            assert page.locator('.workspace-source-media video').evaluate('(v)=>v.paused')
            # OS-style Files DataTransfer must use the real secure upload route first.
            image=next(item for item in archive['items'] if item['media_type']=='image')
            payload=base64.b64encode(page.request.get(url+image['preview_url']).body()).decode()
            transfer=page.evaluate_handle("b=>{const d=new DataTransfer();d.items.add(new File([Uint8Array.from(atob(b),c=>c.charCodeAt(0))],'drop-test.png',{type:'image/png'}));return d;}",payload)
            with page.expect_response(lambda r:r.url.endswith('/editor/archive/upload') and r.request.method=='POST') as uploaded:
                page.locator('.naman-layout').dispatch_event('drop',{'dataTransfer':transfer})
            assert uploaded.value.status==201,uploaded.value.text()
            page.locator('.advanced-monitor-tabs').wait_for();page.locator('.workspace-media-card').filter(has_text='drop-test').wait_for()
            assert len(document()['document']['clips'])==1
            # Blank-lane HTML5 media drop creates a supplementary layer, not a base-slot replacement.
            lane=page.locator('.naman-track').nth(1).locator('.naman-lane');rect=lane.bounding_box()
            transfer=page.evaluate_handle("ref=>{const d=new DataTransfer();d.setData('application/x-naman-media',JSON.stringify(ref));return d;}",{'provider':image['provider'],'media_id':image['media_id']})
            revision=document()['revision'];lane.dispatch_event('drop',{'dataTransfer':transfer,'clientX':rect['x']+20,'clientY':rect['y']+10});saved_after(revision)
            assert len(document()['document']['clips'])==2 and document()['document']['clips'][-1]['track']=='layers'
            # Restore the single animated clip, split it at the playhead, then undo.
            page.locator('.workspace-overflow summary').click();revision=document()['revision'];page.get_by_role('button',name='Ek kurgu geri al',exact=True).click();saved_after(revision)
            original=document()['document']['clips'][0];middle=(original['start']+original['end'])/2
            seek=page.get_by_role('textbox',name='Saniyeye git',exact=True);seek.fill(str(middle));seek.press('Tab');page.locator('.workspace-overflow summary').click()
            page.locator('.advanced-clip').click();revision=document()['revision'];page.keyboard.press('Control+k');saved_after(revision)
            split=document()['document']['clips'];assert len(split)==2 and split[0]['end']==split[1]['start'],split
            page.locator('.workspace-overflow summary').click();revision=document()['revision'];page.get_by_role('button',name='Ek kurgu geri al',exact=True).click();saved_after(revision);page.locator('.workspace-overflow summary').click()
            page.wait_for_function("rev=>{const image=document.querySelector('.advanced-program-frame');return image?.naturalWidth===640&&+image.dataset.revision===rev;}",arg=document()['revision'],timeout=30000)
            for width,height in [(1366,768),(1600,900),(1920,1080),(1093,614)]:
                page.set_viewport_size({'width':width,'height':height})
                metrics=page.evaluate("""()=>({scroll:document.documentElement.scrollHeight,height:innerHeight,tracks:[...document.querySelectorAll('.naman-track')].map(n=>n.getBoundingClientRect().bottom),bottom:document.querySelector('.naman-timeline').getBoundingClientRect().bottom})""")
                assert metrics['scroll']<=height and len(metrics['tracks'])==4 and max(metrics['tracks'])<=metrics['bottom'],metrics
                page.screenshot(path=str(output/f'advanced-{width}x{height}.png'))
            assert not errors,errors
            browser.close()
        print(json.dumps({'passed':True,'project':pid,'isolated_storage':details['storage'],'checks':['real save/reload','effect','keyframe add/edit/delete/undo','marker add/edit/delete/undo','clip trim/move/split/delete/undo','blank-lane media drop','independent source/program/dual monitors','OS file drop secure upload','decoded FFmpeg frame at latest revision','FFmpeg thumbnail','four viewport layouts'],'artifacts':str(output)},ensure_ascii=False))
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()


if __name__=='__main__':main()
