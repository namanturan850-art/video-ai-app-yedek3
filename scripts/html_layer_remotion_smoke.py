"""Real Remotion render of one sanitized HTML/CSS layer through NAMAN's worker.

Usage: python scripts/html_layer_remotion_smoke.py OPENMONTAGE_LIKE_ROOT
The root needs remotion-composer/node_modules with remotion + @remotion/cli and
a downloaded headless browser (npx remotion browser ensure). No other OpenMontage
part is used. Checks exact frame count, transparent background and that each
frame shows the CSS animation at that frame's exact time.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_worker(om_root):
    sys.argv = [sys.argv[0], str(om_root)]  # the worker reads its root from argv[1]
    spec = importlib.util.spec_from_file_location('naman_worker', ROOT / 'app/integrations/openmontage/worker.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalBridge:
    """Same contract as Bridge.call, but in-process so a failure shows its real cause."""

    def __init__(self, om_root):
        self.om_root = Path(om_root).resolve()
        self.worker = load_worker(self.om_root)

    def status(self):
        return {'ready': True}

    def root(self):
        return self.om_root

    def call(self, operation, inputs, folder, runner=None, progress=None):
        return self.worker.work(operation, inputs)


def alpha(path, frame, x, y):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-vf', f'select=eq(n\\,{frame})', '-frames:v', '1',
                                   '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'])
    offset = (y * 1920 + x) * 4
    return raw[offset:offset + 4]


def main(om_root):
    from app.motion import html_layer
    html, css = html_layer.sanitize(
        '<div class="kutu">NAMAN</div>',
        '.kutu{position:absolute;left:760px;top:440px;width:400px;height:200px;background:#ff0000;color:#fff;'
        'font:700 64px Arial,sans-serif;display:flex;align-items:center;justify-content:center;animation:gor 1s linear both}'
        '@keyframes gor{from{opacity:0}to{opacity:1}}')
    folder = Path(tempfile.mkdtemp(prefix='naman-html-'))
    started = time.monotonic()
    path = html_layer.render(LocalBridge(om_root), folder, {'html': html, 'css': css}, 1.0, 'ffmpeg')
    seconds = time.monotonic() - started
    stream = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', str(path)]))['streams'][0]
    report = {'seconds': round(seconds, 1), 'codec': stream['codec_name'], 'pix_fmt': stream['pix_fmt'], 'frames': int(stream['nb_read_frames']),
              'corner_alpha': [alpha(path, f, 10, 10)[3] for f in (0, 15, 29)],
              'box_rgba': {f: list(alpha(path, f, 800, 470)) for f in (0, 15, 29)}}
    print('HTML LAYER REPORT:', json.dumps(report))
    assert report['codec'] == 'qtrle' and report['pix_fmt'] == 'argb' and report['frames'] == 30, report
    assert report['corner_alpha'] == [0, 0, 0], 'background must stay transparent'
    box = report['box_rgba']
    assert box[0][3] <= 20, 'frame 0 must be the animation start (opacity 0)'
    assert 100 <= box[15][3] <= 156, 'frame 15 must be half way (opacity ~0.5)'
    assert box[29][3] >= 220 and box[29][0] >= 200, 'frame 29 must be nearly opaque red'
    print('HTML layer render OK')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
