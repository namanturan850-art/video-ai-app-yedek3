"""Real Chromium issue/choice/confirmation controls; only disposable local fixtures."""
import json
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright
from manual_editor_browser_smoke import SERVER as BASE_SERVER

SERVER=BASE_SERVER.replace('listener=socket.socket();',r'''
view=app.state.editor.view(st['pid'])
first=sorted((s for values in view['tracks'].values() for s in values if s.get('slot_id')),key=lambda s:s['start'])[0]
with closing(app.state.projects._connection()) as c,c:
    state=app.state.stock._load(c,st['pid'],view['stock_plan_id'])
    span=max(first['end']-first['start'],(round(first['end']*30)-round(first['start']*30))/30)
    next(s for s in state['slots'] if s['slot_id']==first['slot_id'])['segment_start']=5.-span
    app.state.stock._save(c,state)
listener=socket.socket();
''')


def main():
    log=Path('/tmp/naman-transition-browser.log').open('w')
    server=subprocess.Popen(['.venv/bin/python','-u','-c',SERVER],stdout=subprocess.PIPE,stderr=log,text=True)
    try:
        details=json.loads(server.stdout.readline());url=f'http://127.0.0.1:{details["port"]}';pid=details['pid'];base=f'{url}/api/projects/{pid}/editor'
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1600,'height':900});page.set_default_timeout(25000)
            errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
            page.goto(f'{url}/projects/{pid}/editor');page.locator('.manual-mode-strip').wait_for()
            page.wait_for_function("!document.querySelector('#editor-content').inert&&document.querySelector('[data-command=split]')?.disabled===false")
            before=page.request.get(base+'/advanced').json();view=page.request.get(base).json()
            first=sorted((s for values in view['tracks'].values() for s in values if s.get('slot_id')),key=lambda s:s['start'])[0]
            pack=page.request.get(base+'/manual/package').json()['output_template']
            pack['sahneler']=[{'scene_id':first['scene_id'],'start':first['start'],'end':first['end'],'motion':'slow_zoom','transition':'crossfade'}]
            scene=next(s for s in view['scenes'] if s['scene_id']==first['scene_id'])
            pack['katmanlar']=[{'scene_id':scene['scene_id'],'text':scene['narration'].split('.')[0]}]
            page.get_by_role('button',name='Manuel Plan / AI paketi',exact=True).click()
            dialog=page.locator('.manual-dialog[open]');dialog.get_by_label('Dış yapay zekâ cevabı',exact=True).fill(json.dumps(pack))
            dialog.get_by_role('button',name='Planı içe aktar',exact=True).click()
            dialog.locator('.manual-transition-issue').wait_for();assert 'ek süresi yetersiz' in dialog.locator('.manual-transition-issue strong').inner_text()
            assert page.request.get(base+'/advanced').json()==before
            assert not any('resolve-transition' in r for r in requests)
            page.once('dialog',lambda dialog:dialog.dismiss())
            dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).click()
            assert page.request.get(base+'/advanced').json()==before
            assert not any('/approve' in r for r in requests)
            # Preserve a deliberately unselected text proposal across correction.
            dialog.locator('input[type=checkbox]').first.uncheck()
            dialog.get_by_role('combobox').select_option('hard_cut')
            assert page.request.get(base+'/advanced').json()==before
            dialog.get_by_role('button',name='Yalnız bu geçişin düzeltmesini onayla',exact=True).click()
            dialog.locator('.manual-transition-issue').wait_for(state='detached')
            assert not dialog.locator('input[type=checkbox]').first.is_checked()
            assert page.request.get(base+'/advanced').json()==before
            dialog.get_by_role('button',name='Taslağı imleçte önizle — kaydetmez',exact=True).click()
            page.wait_for_function("document.querySelector('.manual-dialog[open] img')?.naturalWidth===640")
            dialog.get_by_role('button',name='Seçilen önerileri onayla',exact=True).click()
            page.wait_for_function('async u=>(await (await fetch(u)).json()).revision>0',arg=base+'/advanced')
            state=page.request.get(base+'/advanced').json()
            assert state['document']['transitions'][0]['kind']=='cut' and not state['document']['clips']
            assert len(state['document']['adjustments'])==1 and not errors,errors
            assert all(r.startswith(url) for r in requests),requests
            print(json.dumps({'passed':True,'checks':['source/time issue visible','no automatic replacement','explicit per-transition confirmation','unselected proposal preserved','real draft JPEG preview','only selected edits applied','no external requests'],'errors':errors}))
            browser.close()
    finally:
        server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':main()
