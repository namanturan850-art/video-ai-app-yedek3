"""Manual package UI with real Chromium/API/SQLite; no paid or remote calls."""
import json
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright
from manual_editor_browser_smoke import SERVER


def main():
    log=Path('/tmp/naman-package-browser.log').open('w')
    server=subprocess.Popen(['.venv/bin/python','-u','-c',SERVER],stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        details=json.loads(server.stdout.readline());url=f'http://127.0.0.1:{details["port"]}';pid=details['pid'];base=f'{url}/api/projects/{pid}/editor'
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1600,'height':900},permissions=['clipboard-read','clipboard-write'])
            page=context.new_page();page.set_default_timeout(25000);errors=[];requests=[]
            page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
            page.goto(f'{url}/projects/{pid}/editor');page.locator('.manual-mode-strip').wait_for()
            page.wait_for_function("!document.querySelector('#editor-content').inert")
            before=page.request.get(base+'/advanced').json();pack=page.request.get(base+'/manual/package').json();plan=pack['output_template'];scene=pack['narration'][0]
            valid={'scene_id':scene['scene_id'],'text':'Roma','object_id':'valid','start':scene['start'],'end':scene['end']}
            plan['katmanlar']=[valid,{**valid,'object_id':'repair','end':999}]
            page.get_by_role('button',name='Manuel Plan / AI paketi',exact=True).click();dialog=page.locator('.manual-dialog[open]')
            page.once('dialog',lambda d:d.dismiss());dialog.get_by_role('button',name='Gemini ile talimat ekle (ücretli)',exact=True).click()
            assert not any('/package/prepare' in r for r in requests)
            dialog.get_by_role('button',name='Paketi hazırla',exact=True).click()
            dialog.get_by_role('button',name='Tek mesajı kopyala',exact=True).wait_for()
            page.wait_for_function("!document.querySelector('.manual-dialog[open] .manual-secondary')?.disabled")
            dialog.get_by_role('button',name='Tek mesajı kopyala',exact=True).click()
            message=page.evaluate('navigator.clipboard.readText()')
            assert 'NAMAN — BELGESEL KURGU PLANI GÖREVİ' in message and json.dumps(pack['base'],ensure_ascii=False,indent=1).splitlines()[1] in message
            assert not any('/package/prepare' in r for r in requests)
            dialog.locator('input[type=file]').set_input_files({'name':'plan.json','mimeType':'application/json','buffer':json.dumps(plan).encode()})
            page.wait_for_function("document.querySelector('.naman-json-message')?.textContent.includes('Dosya yüklendi')")
            dialog.get_by_role('button',name='Planı içe aktar',exact=True).click()
            dialog.locator('.manual-import-issues').wait_for()
            assert '999' in dialog.locator('.manual-import-issues').inner_text()
            assert page.request.get(base+'/advanced').json()==before
            dialog.get_by_role('button',name='Düzeltme mesajını kopyala',exact=True).click()
            assert 'repair' in page.evaluate('navigator.clipboard.readText()')
            dialog.get_by_role('button',name='Taslağı imleçte önizle — kaydetmez',exact=True).click()
            page.wait_for_function("document.querySelector('.manual-dialog[open] img')?.naturalWidth===640")
            page.once('dialog',lambda d:d.dismiss());dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).click()
            assert page.request.get(base+'/advanced').json()==before
            dialog.get_by_role('button',name='Cevabı düzelt ve yeniden doğrula',exact=True).click()
            area=dialog.get_by_label('Dış yapay zekâ cevabı',exact=True)
            repaired=json.loads(area.input_value());assert repaired==plan
            repaired['katmanlar'][1]['end']=scene['end'];repaired['katmanlar'][1]['start']=scene['start']+1/30
            area.fill(json.dumps(repaired));dialog.get_by_role('button',name='Planı içe aktar',exact=True).click()
            dialog.locator('input[type=checkbox]').nth(1).wait_for();assert dialog.locator('.manual-import-issues').count()==0
            dialog.locator('input[type=checkbox]').nth(1).uncheck()
            dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).click()
            page.wait_for_function('async u=>(await (await fetch(u)).json()).revision>0',arg=base+'/advanced')
            state=page.request.get(base+'/advanced').json();assert len(state['document']['clips'])==1
            assert not errors,errors
            assert all(r.startswith(url) for r in requests),requests
            print(json.dumps({'passed':True,'checks':['Gemini consent cancellation','complete package clipboard','real JSON file upload','invalid operation retained','correction clipboard','real JPEG draft preview','cancelled partial approval','edit and revalidate','only selected operation persisted','no external requests'],'errors':errors}))
            browser.close()
    finally:
        server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':main()
