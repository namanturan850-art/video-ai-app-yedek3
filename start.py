"""Beginner-friendly launcher. The bootstrap uses only Python's standard library."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
LOGS = ROOT / "logs"


class StartupError(Exception):
    """Safe, actionable Turkish startup message."""


def say(message: str) -> None:
    print(message, flush=True)


def dependencies_current() -> bool:
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, version = line.split("==", 1)
        try:
            if importlib.metadata.version(name) != version:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return True


def prepare_environment() -> Path:
    interpreter = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.exists():
        say("1/3 · İlk kurulum hazırlanıyor. Lütfen bekleyin…")
        venv.EnvBuilder(with_pip=True).create(VENV)
    marker = VENV / ".studio-requirements.sha256"
    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    installed = False
    if marker.exists() and marker.read_text(encoding="utf-8") == digest:
        check = subprocess.run([str(interpreter), "-c", "from start import dependencies_current; raise SystemExit(0 if dependencies_current() else 1)"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        installed = check.returncode == 0
    if not installed:
        say("1/3 · Gerekli bileşenler kuruluyor. İlk açılışta internet gerekir; lütfen bekleyin…")
        LOGS.mkdir(exist_ok=True)
        with (LOGS / "installation.log").open("w", encoding="utf-8") as log:
            pip_ready = subprocess.run([str(interpreter), "-m", "pip", "--version"], stdout=log, stderr=log).returncode == 0
            if not pip_ready:
                result = subprocess.run([str(interpreter), "-m", "ensurepip"], stdout=log, stderr=log)
                if result.returncode:
                    raise StartupError("Kurulum hazırlanamadı. Python'u python.org üzerinden yeniden kurup uygulamayı tekrar açın.")
            result = subprocess.run([str(interpreter), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-r", str(REQUIREMENTS)], cwd=ROOT, stdout=log, stderr=log)
        if result.returncode:
            raise StartupError("Bileşenler kurulamadı. İnternet bağlantınızı kontrol edip uygulamayı yeniden açın. Sorun sürerse logs klasöründeki installation.log dosyasını destek için paylaşın.")
        marker.write_text(digest, encoding="utf-8")
    else:
        say("1/3 · Kurulum hazır.")
    return interpreter


def run_server(port: int, open_browser: bool = True) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise StartupError("Uygulama adresi kullanımda. Daha önce açtığınız NAMAN penceresini kapatıp tekrar deneyin.") from error
    say("2/3 · Uygulama başlatılıyor…")
    if shutil.which("ffmpeg") is None:
        say("Bilgi: FFmpeg bulunamadı. Uygulama açılabilir; video oluşturmak için ileride FFmpeg kurulması gerekir.")
    LOGS.mkdir(exist_ok=True)
    url = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with (LOGS / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"], cwd=ROOT, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            ready = False
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with opener.open(url + "/api/health", timeout=1) as response:
                        ready = response.status == 200 and json.load(response).get("status") == "ok"
                    if ready:
                        break
                except (urllib.error.URLError, OSError, ValueError):
                    pass
                time.sleep(0.2)
            if not ready:
                raise StartupError("Uygulama açılamadı. Klasörü Belgeler klasörünüze taşıyıp tekrar deneyin. Sorun sürerse logs klasöründeki server.log dosyasını destek için paylaşın.")
            say("3/3 · Uygulama hazır. Bu pencereyi açık bırakın; kapatırsanız uygulama durur.")
            if open_browser:
                try:
                    opened = webbrowser.open(url)
                except webbrowser.Error:
                    opened = False
                if not opened:
                    say(f"Tarayıcı açılamadı. Tarayıcınızın adres çubuğuna {url} yazın.")
            else:
                say(f"Yerel adres: {url}")
            say("Kapatmak için bu pencerede Ctrl+C tuşlarına basabilirsiniz.")
            result = process.wait()
            if result:
                raise StartupError("Uygulama durdu. Bu pencereyi kapatıp uygulamayı yeniden açın.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="NAMAN")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        say("Python 3.12 veya daha yenisi gerekiyor. Python'u güncelleyip uygulamayı tekrar açın.")
        return 1
    if not 1 <= args.port <= 65535:
        say("Uygulama adresi geçersiz. START_AI_VIDEO_STUDIO.bat dosyasına çift tıklayarak açın.")
        return 1
    try:
        if Path(sys.prefix).resolve() != VENV.resolve():
            interpreter = prepare_environment()
            return subprocess.call([str(interpreter), str(ROOT / "start.py"), *sys.argv[1:]], cwd=ROOT)
        run_server(args.port, not args.no_browser)
        return 0
    except KeyboardInterrupt:
        say("Uygulama kapatıldı.")
        return 0
    except StartupError as error:
        say(str(error))
        return 1
    except (OSError, subprocess.SubprocessError, ValueError):
        say("Başlatma tamamlanamadı. Uygulama klasörünü Belgeler klasörünüze taşıyın, internet bağlantınızı kontrol edin ve yeniden açın.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
