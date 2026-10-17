import sys
from types import SimpleNamespace

import desktop


def test_desktop_uses_native_window_and_stops_server(monkeypatch):
    events=[]
    class Listener:
        def bind(self, address): events.append(('bind',address))
        def listen(self, count): pass
        def getsockname(self): return ('127.0.0.1',43210)
        def close(self): events.append('closed')
    class Server:
        started=False
        should_exit=False
        def __init__(self, config): self.config=config
        def run(self, sockets):
            self.started=True
            while not self.should_exit: desktop.time.sleep(.001)
            events.append('stopped')
    fake_webview=SimpleNamespace(
        create_window=lambda title,url,**kw: events.append((title,url,kw)),
        start=lambda **kw: events.append(('window',kw)))
    monkeypatch.setitem(sys.modules,'webview',fake_webview)
    monkeypatch.setitem(sys.modules,'uvicorn',SimpleNamespace(Server=Server,Config=lambda app,**kw:(app,kw)))
    monkeypatch.setattr('app.main.create_app',lambda storage:'application')
    monkeypatch.setattr(desktop.socket,'socket',lambda *args:Listener())
    desktop.run_desktop()
    window=next(event for event in events if isinstance(event,tuple) and event[0]=='NAMAN')
    assert window[1]=='http://127.0.0.1:43210'
    assert 'stopped' in events and events[-1]=='closed'
