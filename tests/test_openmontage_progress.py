"""OpenMontage worker: real Remotion frame progress and a stall watchdog (no flat 30-minute cap)."""
import importlib.util
import io
import sys
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parent.parent / 'app' / 'integrations' / 'openmontage' / 'worker.py'


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['worker.py', str(tmp_path), 'doctor'])
    spec = importlib.util.spec_from_file_location('avs_worker_under_test', WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_renderer(tmp_path, body):
    script = tmp_path / 'fake_render.py'
    script.write_text(body, encoding='utf-8')
    return [sys.executable, str(script)]


def test_frame_progress_is_reported_to_the_parent(worker, tmp_path, monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr(sys, '__stdout__', out)
    args = fake_renderer(tmp_path, "import sys\nfor i in (50, 100):\n    sys.stdout.write(f'Rendered {i}/100\\r');sys.stdout.flush()\nsys.stdout.write('Encoded 100/100\\n')\n")
    worker.render_with_progress(args, tmp_path, 30)
    values = [int(line.split('=')[1]) for line in out.getvalue().split() if line.startswith('out_time_us=')]
    assert values == sorted(values) and values[0] == 450_000 and values[-1] == 1_000_000


def test_a_stuck_renderer_is_stopped_by_the_stall_watchdog(worker, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'STALL_SECONDS', 2)
    args = fake_renderer(tmp_path, "import time\ntime.sleep(60)\n")
    with pytest.raises(RuntimeError, match='stalled'):
        worker.render_with_progress(args, tmp_path, 120)
