"""Actual Chromium, HTTP API and SQLite; synthetic media, mocked stock only."""
import json
from pathlib import Path
import subprocess
from playwright.sync_api import sync_playwright

SERVER = r'''
import sys,json,tempfile,socket
from pathlib import Path
sys.path.insert(0,'tests')
from app.database import initialize_database
from app.main import create_app
from test_stock_recovery_integration import setup_recovery
import uvicorn
storage=Path(tempfile.mkdtemp(prefix='naman-stock-browser-',dir='/tmp'));initialize_database(storage)
app=create_app(storage);st,calls,downloads=setup_recovery(app)
stock=app.state.stock;view=stock.view(st['pid'])
job=stock.start(st['pid'],{'plan_id':view['plan_id'],'revision':view['revision'],'action':'complete_media'})
stock.futures[job['job_id']].result(timeout=60)
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
print(json.dumps({'pid':st['pid'],'port':listener.getsockname()[1],'storage':str(storage),'provider_calls':len(calls),'downloads':len(downloads)}),flush=True)
uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',log_level='warning',access_log=False)).run(sockets=[listener])
'''


def main():
    out=Path('/tmp/naman-stock-browser-proof');out.mkdir(exist_ok=True)
    with (out/'server.log').open('w') as log:
        process=subprocess.Popen(['.venv/bin/python','-u','-c',SERVER],stdout=subprocess.PIPE,stderr=log,text=True)
        try:
            data=json.loads(process.stdout.readline());base=f'http://127.0.0.1:{data["port"]}';pid=data['pid'];metrics={}
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':1440,'height':960},accept_downloads=True,permissions=['clipboard-read','clipboard-write'])
                page=context.new_page();page.set_default_timeout(20000);page.add_init_script('window.showSaveFilePicker=undefined;')
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'{base}/projects/{pid}/production');page.locator('#stock-summary').filter(has_text='3/32').wait_for()
                assert page.locator('.stock-missing-diagnostic').count()==29
                assert 'undefined: missing' not in page.locator('#production-content').inner_text()
                assert 'Otomatik grafik eklenmez' in page.locator('#stock-controls').inner_text()
                first=page.locator('.stock-missing-diagnostic').first;first.locator('summary').click()
                assert first.locator('.stock-diagnostic-scroll').evaluate('(e)=>e.clientHeight<=340&&e.scrollHeight>e.clientHeight')
                assert first.get_by_role('button',name='Yalnız yeni alternatifleri ara').count()==1
                with page.expect_download() as waiting:page.locator('#stock-diagnostics').click()
                download=waiting.value;assert not download.failure();download.save_as(out/'diagnostics.json')
                report=json.loads((out/'diagnostics.json').read_text());assert len(report['slots'])==32
                assert 'local_path' not in json.dumps(report) and data['storage'] not in json.dumps(report) and 'synthetic-recovery-secret' not in json.dumps(report)
                metrics['download']={'slots':32,'filename':download.suggested_filename,'schema':report['schema_version']}
                page.locator('#stock-diagnostics-copy').click();page.get_by_text('Tanılama panoya kopyalandı.',exact=False).wait_for()
                assert len(json.loads(page.evaluate('navigator.clipboard.readText()'))['slots'])==32
                metrics['clipboard']='native clipboard readback passed'
                page.evaluate("()=>{navigator.clipboard.writeText=async()=>{throw new Error('denied')}}")
                page.locator('#stock-diagnostics-copy').click();fallback=page.locator('#stock-diagnostics-text');fallback.wait_for(state='visible')
                assert len(json.loads(fallback.input_value())['slots'])==32
                metrics['clipboard_fallback']='selectable JSON text passed'
                page.route('**/stock/diagnostics',lambda route:route.fulfill(status=503,content_type='application/json',body=json.dumps({'message':'Sentetik tanı hatası'})))
                page.locator('#stock-diagnostics').click();page.locator('#stock-diagnostics-status').filter(has_text='kaydedilemedi').wait_for()
                metrics['http_error']='visible Turkish failure passed';page.unroute('**/stock/diagnostics')
                page.evaluate("()=>{window.showSaveFilePicker=async()=>{let e=new Error('cancel');e.name='AbortError';throw e;}}")
                page.locator('#stock-diagnostics').click();page.locator('#stock-diagnostics-status').filter(has_text='iptal edildi').wait_for()
                metrics['picker_cancel']='honest cancellation passed'
                page.evaluate("()=>{window.showSaveFilePicker=async()=>({name:'Chosen.json',createWritable:async()=>({write:async t=>{window.savedDiagnostic=t},close:async()=>{window.closedDiagnostic=true}})})}")
                page.locator('#stock-diagnostics').click();page.locator('#stock-diagnostics-status').filter(has_text='Kaydedildi: Chosen.json').wait_for()
                assert page.evaluate('window.closedDiagnostic') and len(json.loads(page.evaluate('window.savedDiagnostic'))['slots'])==32
                metrics['picker_adapter']='save/write/close and visible filename passed; native picker not automated'
                api=page.request.get(f'{base}/api/projects/{pid}/production/stock/diagnostics');assert api.status==200 and 'attachment' in api.headers['content-disposition']
                forbidden=page.request.post(f'{base}/api/projects/{pid}/production/stock/jobs',headers={'Origin':'https://evil.invalid','X-AI-Video-Studio':'projects'},data={});assert forbidden.status==403
                metrics['same_origin']='foreign mutation rejected 403'
                assert not errors,errors
                page.screenshot(path=str(out/'stock-recovery.png'),full_page=False)
                metrics.update({'missing_panels':29,'selected_images':3,'generated_motion':0,'js_errors':errors,'provider_calls':data['provider_calls'],'downloads':data['downloads'],'windows_webview2':'not available; smoke steps documented'})
                browser.close()
            (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2));print(json.dumps(metrics,ensure_ascii=False,indent=2))
        finally:
            process.terminate();process.wait(timeout=20)


if __name__=='__main__':main()
