"""Actual large-file import UI -> background progress -> draft -> explicit approval."""
import json
from pathlib import Path
import os,shutil,subprocess,sys,tempfile,time
from playwright.sync_api import sync_playwright
from manual_editor_browser_smoke import SERVER


def main():
    python=Path('.venv')/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    with tempfile.TemporaryFile(mode='w+') as log:
        server=subprocess.Popen([str(python) if python.is_file() else sys.executable,'-u','-c',SERVER],stdout=subprocess.PIPE,stderr=log,text=True)
        try:
            info=json.loads(server.stdout.readline());pid=info['pid'];url=f'http://127.0.0.1:{info["port"]}';base=f'{url}/api/projects/{pid}/editor'
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
                page=browser.new_page(extra_http_headers={'X-AI-Video-Studio':'projects'},viewport={'width':1366,'height':900});page.set_default_timeout(30000)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)));requests=[];page.on('request',lambda r:requests.append(r.url))
                pack=page.request.get(base+'/manual/package').json();plan=pack['output_template'];scene=pack['narration'][0]
                plan['katmanlar']=[{'scene_id':scene['scene_id'],'start':i*.001,'end':i*.001+.04,'text':'Roma','effect':'none','object_id':str(i)} for i in range(150)]
                text=json.dumps(plan,ensure_ascii=False,indent=100);assert len(text)>200000
                before=page.request.get(base+'/advanced').json();view=page.request.get(base).json()
                page.goto(f'{url}/projects/{pid}/editor');page.locator('.manual-mode-strip').wait_for()
                page.get_by_role('button',name='Manuel Plan / AI paketi',exact=True).click();dialog=page.locator('.manual-dialog[open]')
                dialog.locator('input[type=file]').set_input_files({'name':'large-plan.json','mimeType':'application/json','buffer':text.encode()})
                assert dialog.get_by_label('Dış yapay zekâ cevabı',exact=True).input_value()==text
                started=time.monotonic()
                with page.expect_response(lambda r:r.url.endswith('/manual/response-jobs') and r.request.method=='POST') as submitted:
                    dialog.get_by_role('button',name='Cevabı içe aktar',exact=True).click()
                assert submitted.value.status==202
                assert dialog.get_by_role('button',name='Cevabı içe aktar',exact=True).is_disabled()
                dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).wait_for()
                assert len(dialog.locator('input[type=checkbox]').all())==150
                assert page.request.get(base+'/advanced').json()==before
                dialog.get_by_role('button',name='Taslağı imleçte önizle — kaydetmez',exact=True).click()
                page.wait_for_function("document.querySelector('.manual-dialog[open] img')?.naturalWidth>0")
                # Closing/previewing is read-only; choose only the first proposal.
                boxes=dialog.locator('input[type=checkbox]')
                for i in range(1,150):boxes.nth(i).uncheck()
                dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).click()
                page.wait_for_function('async u=>(await (await fetch(u)).json()).document.clips.length===1',arg=base+'/advanced')
                after=page.request.get(base).json()
                assert after['tracks']==view['tracks']
                assert any('/manual/response-jobs/' in u for u in requests)
                assert not any('/manual/package/prepare' in u for u in requests)
                assert not errors,errors
                result={'passed':True,'characters':len(text),'operations':150,'approved':1,'seconds':round(time.monotonic()-started,2),'browser_errors':errors,
                    'checks':['real JSON file upload','202 background job and status polling','draft only before consent','real JPEG preview','only selected proposal applied','media narration subtitles preserved','no paid call']}
                print(json.dumps(result));Path(os.environ.get('NAMAN_MANUAL_IMPORT_REPORT',str(Path(tempfile.gettempdir())/'naman-manual-import-ui.json'))).write_text(json.dumps(result),encoding='utf-8')
                browser.close()
        finally:server.terminate();server.wait(timeout=15)


if __name__=='__main__':main()
