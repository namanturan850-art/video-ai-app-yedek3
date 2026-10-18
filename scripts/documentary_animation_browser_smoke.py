"""Actual manual dialog + API/SQLite/Chromium; only disposable synthetic data."""
import json
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright
from manual_editor_browser_smoke import SERVER


def main():
    log=Path('/tmp/naman-animation-browser.log').open('w')
    server=subprocess.Popen(['.venv/bin/python','-u','-c',SERVER],stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        details=json.loads(server.stdout.readline());url=f'http://127.0.0.1:{details["port"]}';pid=details['pid'];base=f'{url}/api/projects/{pid}/editor'
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1600,'height':900});page.set_default_timeout(25000)
            errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
            page.goto(f'{url}/projects/{pid}/editor');page.locator('.manual-mode-strip').wait_for()
            page.wait_for_function("!document.querySelector('#editor-content').inert")
            before=page.request.get(base+'/advanced').json();view=page.request.get(base).json()
            assert page.locator('.naman-track').count()==7
            page.get_by_role('button',name='Manuel Plan / AI paketi',exact=True).click()
            dialog=page.locator('.manual-dialog[open]');pack=json.loads(dialog.get_by_label('Hazır AI paketi',exact=True).input_value())
            assert pack['animation_capabilities']['canvas']['fps']==30
            plan=pack['output_template'];scene=pack['narration'][0]
            record={'scene_id':scene['scene_id'],'start':scene['start'],'end':min(scene['end'],scene['start']+1.),'data':pack['animation_capabilities']['examples']['science']}
            bad=json.loads(json.dumps(record));bad['data']['objects'][0]['kind']='shader_script'
            plan['animasyon_sahneleri']=[record,bad]
            dialog.locator('input[type=file]').set_input_files({'name':'animation.json','mimeType':'application/json','buffer':json.dumps(plan).encode()})
            page.wait_for_function("document.querySelector('.naman-json-message')?.textContent.includes('Dosya yüklendi')")
            dialog.get_by_role('button',name='Cevabı içe aktar',exact=True).click()
            dialog.locator('.manual-import-issues').wait_for();assert 'kind' in dialog.locator('.manual-import-issues').inner_text()
            assert 'Belgesel animasyonu · 5 nesne · DEMO' in dialog.inner_text()
            assert page.request.get(base+'/advanced').json()==before
            dialog.get_by_role('button',name='Taslağı imleçte önizle — kaydetmez',exact=True).click()
            page.wait_for_function("document.querySelector('.manual-dialog[open] img')?.naturalWidth===640")
            page.once('dialog',lambda d:d.dismiss());dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).click()
            assert page.request.get(base+'/advanced').json()==before
            page.once('dialog',lambda d:d.accept());dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).click()
            page.wait_for_function('async u=>(await (await fetch(u)).json()).revision>0',arg=base+'/advanced')
            state=page.request.get(base+'/advanced').json()
            assert len(state['document']['clips'])==1 and state['document']['clips'][0]['motion']['template']=='documentary'
            assert page.request.get(base).json()['tracks']==view['tracks']
            assert not errors,errors
            assert all(r.startswith(url) for r in requests),requests
            print(json.dumps({'passed':True,'checks':['seven existing tracks','capabilities in package','animation JSON file upload','invalid animation isolated','friendly draft and demo label','real draft JPEG','cancelled approval','explicit valid-only approval','original sources preserved','no external calls'],'errors':errors}))
            browser.close()
    finally:
        server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':main()
