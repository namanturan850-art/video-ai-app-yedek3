import socket
import subprocess
import sys
from pathlib import Path

import pytest

import start


def test_occupied_port_has_plain_message():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        with pytest.raises(start.StartupError, match="kullanımda"):
            start.run_server(sock.getsockname()[1], False)


def test_launcher_checks_runtime_dependencies():
    assert start.dependencies_current() is True


def test_real_http_server(tmp_path):
    import json
    import time
    import urllib.request
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    root = Path(__file__).resolve().parent.parent
    with (tmp_path / "smoke.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=root, stdout=log, stderr=log)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(100):
                assert process.poll() is None, (tmp_path / "smoke.log").read_text()
                try:
                    with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                        assert json.load(response)["status"] == "ok"
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("Server did not become ready")
            for path in ["/", "/diagnostics", "/static/app.js"]:
                with opener.open(f"http://127.0.0.1:{port}{path}") as response:
                    assert response.status == 200
            with opener.open(f"http://127.0.0.1:{port}/api/diagnostics") as response:
                assert json.load(response)["database_ok"] is True
        finally:
            process.terminate()
            process.wait(timeout=10)


def test_browser_opens_only_after_health_and_missing_ffmpeg_is_nonfatal(tmp_path, monkeypatch, capsys):
    import io
    events = []
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, url, timeout):
            events.append('health')
            return Response(b'{"status": "ok"}')
    class Process:
        finished = False
        def poll(self):
            return 0 if self.finished else None
        def wait(self):
            events.append('wait')
            self.finished = True
            return 0
    monkeypatch.setattr(start, 'LOGS', tmp_path / 'logs')
    monkeypatch.setattr(start.shutil, 'which', lambda name: None)
    monkeypatch.setattr(start.subprocess, 'Popen', lambda *args, **kwargs: Process())
    monkeypatch.setattr(start.urllib.request, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(start.webbrowser, 'open', lambda url: events.append('browser') or False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    start.run_server(port)
    assert events == ['health', 'browser', 'wait']
    output = capsys.readouterr().out
    assert 'FFmpeg bulunamadı' in output
    assert 'Tarayıcı açılamadı' in output


def test_install_failure_does_not_mark_environment_ready(tmp_path, monkeypatch):
    import types
    environment = tmp_path / 'venv'
    interpreter = environment / ('Scripts/python.exe' if start.os.name == 'nt' else 'bin/python')
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    monkeypatch.setattr(start, 'VENV', environment)
    monkeypatch.setattr(start, 'LOGS', tmp_path / 'logs')
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        return types.SimpleNamespace(returncode=1 if 'install' in args else 0)
    monkeypatch.setattr(start.subprocess, 'run', command)
    with pytest.raises(start.StartupError, match='İnternet bağlantınızı'):
        start.prepare_environment()
    assert any('install' in args for args in calls)
    assert not (environment / '.studio-requirements.sha256').exists()
