r"""Windows-only NAMAN editor smoke test using the installed WebView2 runtime.

Usage from the repository root:
  .venv\Scripts\python scripts\webview2_editor_smoke.py PROJECT_ID [DATA_DIR]

The script is read-only: it opens an existing project, waits for the editor,
checks that loading ended and seven tracks exist, then closes the window.
"""
import json
import platform
import socket
import sys
import threading
import time
from pathlib import Path


def main():
    if platform.system() != 'Windows':
        raise SystemExit('Bu smoke testi yalnız Windows WebView2 ortamında çalışır.')
    if len(sys.argv) not in (2, 3) or len(sys.argv[1]) != 32:
        raise SystemExit('Kullanım: webview2_editor_smoke.py PROJECT_ID [DATA_DIR]')
    import uvicorn
    import webview
    from app.main import create_app

    project_id=sys.argv[1]
    storage=Path(sys.argv[2]).resolve() if len(sys.argv)==3 else None
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listener.bind(('127.0.0.1',0));listener.listen(16);port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(storage),host='127.0.0.1',port=port,
                                         log_level='warning',access_log=False))
    worker=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);worker.start()
    deadline=time.monotonic()+30
    while not server.started and worker.is_alive() and time.monotonic()<deadline:time.sleep(.05)
    if not server.started:raise SystemExit('NAMAN yerel sunucusu başlatılamadı.')
    result={'ok':False,'message':'WebView2 kontrolü tamamlanamadı.'}
    window=webview.create_window('NAMAN WebView2 Smoke',f'http://127.0.0.1:{port}/projects/{project_id}/editor',
                                 width=1280,height=820,hidden=True)

    def check():
        try:
            end=time.monotonic()+30
            while time.monotonic()<end:
                state=window.evaluate_js("""(() => {
                  const root=document.querySelector('#editor-content');
                  const status=root?.querySelector('.provider-status')?.textContent||'';
                  return {status,tracks:root?.querySelectorAll('.naman-track').length||0,
                          retry:[...document.querySelectorAll('button')].some(x=>x.textContent.includes('Yeniden Dene'))};
                })()""")
                if state and state.get('tracks')==7 and 'yükleniyor' not in state.get('status','').lower():
                    result.update(ok=True,message='Kurgu WebView2 içinde açıldı; yedi iz hazır.',state=state);break
                if state and state.get('retry'):
                    result.update(message='Kurgu hata ekranına düştü.',state=state);break
                time.sleep(.25)
        finally:webview.windows[0].destroy()

    window.events.loaded += check
    try:webview.start(gui='edgechromium',private_mode=True)
    finally:
        server.should_exit=True;worker.join(timeout=30);listener.close()
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['ok'] else 1)


if __name__=='__main__':main()
