"""“Motor Durumu”: what the render engines need, in plain Turkish, plus a
one-click OpenMontage install (runs the same isolated installer)."""
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _version(args, pattern=r'(\d+(?:\.\d+)+)'):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
        match = re.search(pattern, (r.stdout or '') + (r.stderr or ''))
        return match.group(1) if r.returncode == 0 and match else None
    except (OSError, subprocess.SubprocessError):
        return None


def components(bridge, discover=None):
    from app.rendering.tools import discover as default_discover
    tool = (discover or default_discover)()
    items = []
    def add(key, name, ok, version, message, needed_for):
        items.append({'id': key, 'name': name, 'ok': bool(ok), 'version': version or '', 'message': message, 'needed_for': needed_for})
    add('python', 'Python', sys.version_info >= (3, 10), sys.version.split()[0], 'Uygulama çalışıyor.', 'Uygulama')
    ffmpeg = tool.get('ffmpeg')
    fv = _version([ffmpeg, '-version'], r'ffmpeg version n?(\d+(?:\.\d+)*)') if ffmpeg else None
    major = int(fv.split('.')[0]) if fv and fv.split('.')[0].isdigit() else None
    add('ffmpeg', 'FFmpeg', ffmpeg and (major is None or major >= 7), fv,
        'Hazır.' if ffmpeg and (major is None or major >= 7) else 'FFmpeg 7 veya yenisi gerekli: eski sürüm video birleştirmede hata verir. FFmpeg’i güncelleyin.' if ffmpeg else
        'FFmpeg bulunamadı. Windows’ta “winget install ffmpeg” ile kurup uygulamayı yeniden açın.', 'Video oluşturma (zorunlu)')
    try:
        from PIL import __version__ as pillow
    except ImportError:
        pillow = None
    add('motion_local', 'Yerel motion çizici (Pillow)', pillow, pillow, 'Hazır — OpenMontage yoksa motion grafikler bununla çizilir.' if pillow else 'Pillow eksik; START_AI_VIDEO_STUDIO.bat paketleri yeniden kurar.', 'Motion yedeği')
    git = shutil.which('git')
    add('git', 'Git', git, _version([git, '--version']) if git else None, 'Hazır.' if git else 'Git yok. git-scm.com adresinden “Git for Windows” kurun.', 'OpenMontage kurulumu')
    node = shutil.which('node')
    nv = _version([node, '--version'], r'v(\d+(?:\.\d+)*)') if node else None
    node_ok = bool(nv and int(nv.split('.')[0]) >= 18)
    add('node', 'Node.js', node_ok, nv, 'Hazır.' if node_ok else 'Node.js 18 veya yenisi gerekli. nodejs.org adresinden LTS sürümünü kurun.', 'OpenMontage / Remotion')
    status = bridge.status(True)
    root = None
    try: root = bridge.root()
    except Exception: pass
    present = bool(root and root.exists())
    add('openmontage', 'OpenMontage', status.get('ready'), status.get('commit', ''),
        status.get('message') if present or status.get('ready') else 'Kurulu değil. Aşağıdaki “Eksikleri kur” düğmesiyle kurabilirsiniz (Git ve Node.js gerekir).', 'Ana montaj motoru')
    cli = root / 'remotion-composer' / 'node_modules' / '@remotion' / 'cli' / 'package.json' if root else None
    remotion = None
    if cli and cli.is_file():
        match = re.search(r'"version"\s*:\s*"([^"]+)"', cli.read_text(encoding='utf-8', errors='replace'))
        remotion = match.group(1) if match else None
    add('remotion', 'Remotion', remotion and status.get('ready'), remotion, 'Hazır.' if remotion and status.get('ready') else 'OpenMontage kurulumu Remotion’u da kurar.', 'OpenMontage çizimi')
    ready = all(i['ok'] for i in items if i['id'] in ('python', 'ffmpeg', 'motion_local'))
    return {'components': items, 'video_ready': ready, 'openmontage_ready': bool(status.get('ready')),
            'summary': ('Tüm motorlar hazır.' if status.get('ready') and ready else
                        'Video oluşturulabilir; motion grafikler yerel çiziciyle yapılır. OpenMontage isteğe bağlıdır.' if ready else
                        'Video oluşturmak için eksik bileşen var; kırmızı satırlara bakın.'),
            'can_install': bool(git and node_ok and not status.get('ready'))}


class Installer:
    """One-click base OpenMontage install in the background (no prompts)."""
    def __init__(self, command=None):
        self.command = command or [sys.executable, str(ROOT / 'install_openmontage.py'), '--yes']
        self.lock, self.state = threading.Lock(), {'status': 'idle', 'log': []}

    def view(self):
        with self.lock:
            return {'status': self.state['status'], 'log': self.state['log'][-20:]}

    def start(self):
        with self.lock:
            if self.state['status'] == 'running':
                return self.view()
            self.state = {'status': 'running', 'log': ['Kurulum başladı. Bu işlem internet hızına göre 5–20 dakika sürebilir.']}
        threading.Thread(target=self._run, daemon=True).start()
        return self.view()

    def _run(self):
        try:
            process = subprocess.Popen(self.command, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace')
            for line in process.stdout:
                line = line.strip()
                if line and 'http' not in line.casefold():
                    with self.lock: self.state['log'].append(line[:300])
            code = process.wait()
            with self.lock:
                self.state['status'] = 'completed' if code == 0 else 'error'
                if code: self.state['log'].append('Kurulum tamamlanamadı. Mesajlara bakın; mevcut projeler etkilenmedi.')
        except OSError:
            with self.lock:
                self.state.update(status='error'); self.state['log'].append('Kurulum programı başlatılamadı.')
