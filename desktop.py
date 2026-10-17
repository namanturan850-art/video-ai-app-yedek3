"""NAMAN native window. The server shares this process and shuts down with it."""
import socket
import threading
import time


def run_desktop(storage=None):
    import uvicorn
    try:
        import webview
    except ImportError as error:
        raise RuntimeError('Masaüstü bileşeni eksik. START_NAMAN.bat ile yeniden açın.') from error
    from app.main import create_app
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(storage), host='127.0.0.1', port=port,
                                          log_level='warning', access_log=False))
    worker = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, name='naman-server', daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        if not server.started:
            raise RuntimeError('NAMAN sunucusu açılamadı. Veri klasörünün yazılabilir olduğunu kontrol edin.')
        webview.create_window('NAMAN', f'http://127.0.0.1:{port}', width=1440, height=960,
                              min_size=(960, 640), text_select=True)
        # No JS/Python bridge: the existing same-origin HTTP checks remain authoritative.
        webview.start(private_mode=True)
    finally:
        server.should_exit = True
        worker.join(timeout=30)
        listener.close()
        if worker.is_alive():
            raise RuntimeError('NAMAN işlemleri kapanıyor; dosyaların kaydedilmesi için bekleyin.')
