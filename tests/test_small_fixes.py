"""Stage 4: language-measured duration estimate, real narration duration on the
script screen, “Motor Durumu” components and the one-click installer. No network."""
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.integrations.openmontage import engine_status
from app.main import create_app
from app.scripts.models import duration_metrics
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}


def test_german_385_words_estimate_about_three_minutes():
    text = ' '.join(['Wort'] * 385)
    # Even a mistyped target range must not shrink the estimate (owner saw 1,4 dk).
    metrics = duration_metrics(text, 3, {'words_per_minute_min': 250, 'words_per_minute_max': 300, 'language': 'de'})
    assert metrics['spoken_rate'] == 130 and 2.8 <= metrics['estimated_minutes'] <= 3.1


def test_unknown_language_keeps_form_range():
    metrics = duration_metrics(' '.join(['w'] * 300), 2, {'words_per_minute_min': 140, 'words_per_minute_max': 160, 'language': 'xx'})
    assert metrics['estimated_minutes'] == 2.0


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        yield client


def test_script_view_reports_real_narration_duration(client, monkeypatch):
    project = client.post('/api/projects', json={'name': 'P', 'topic': 'Rom'}).json()
    assert client.get(f'/api/projects/{project["id"]}/script').json()['narration'] is None
    narration = client.app.state.narration
    monkeypatch.setattr(narration, 'view', lambda pid: {'active': {'source_script_version_id': 'v1', 'metadata': {'audio': {'duration': 181.4}}}})
    assert client.get(f'/api/projects/{project["id"]}/script').json()['narration'] == {'duration': 181.4, 'version_id': 'v1'}


class FakeBridge:
    def __init__(self, ready): self.ready = ready
    def status(self, refresh=False): return {'ready': self.ready, 'commit': 'abc1234' if self.ready else '', 'message': 'Hazır.' if self.ready else 'Kurulum gerekli'}
    def root(self, *a): raise RuntimeError('none')


def test_components_list_in_turkish_without_openmontage(monkeypatch):
    monkeypatch.setattr(engine_status.shutil, 'which', lambda name: None)
    result = engine_status.components(FakeBridge(False), discover=lambda: {})
    rows = {c['id']: c for c in result['components']}
    assert set(rows) == {'python', 'ffmpeg', 'motion_local', 'git', 'node', 'openmontage', 'remotion'}
    assert not rows['ffmpeg']['ok'] and 'FFmpeg bulunamadı' in rows['ffmpeg']['message']
    assert not rows['node']['ok'] and 'Node.js' in rows['node']['message']
    assert 'Eksikleri kur' in rows['openmontage']['message']
    assert not result['video_ready'] and not result['can_install']


def test_old_ffmpeg_is_flagged(monkeypatch):
    monkeypatch.setattr(engine_status, '_version', lambda args, pattern=None: '6.1.1' if 'ffmpeg' in args[0] else None)
    monkeypatch.setattr(engine_status.shutil, 'which', lambda name: None)
    rows = {c['id']: c for c in engine_status.components(FakeBridge(False), discover=lambda: {'ffmpeg': '/x/ffmpeg'})['components']}
    assert not rows['ffmpeg']['ok'] and 'FFmpeg 7' in rows['ffmpeg']['message'] and rows['ffmpeg']['version'] == '6.1.1'


def test_installer_runs_in_background_and_hides_urls():
    script = "print('Adim 1'); print('indir https://example.invalid/x'); print('Bitti')"
    installer = engine_status.Installer([sys.executable, '-c', script])
    assert installer.start()['status'] == 'running'
    for _ in range(100):
        if installer.view()['status'] != 'running': break
        time.sleep(0.05)
    view = installer.view()
    assert view['status'] == 'completed' and 'Bitti' in view['log'] and not any('http' in line for line in view['log'])
    failing = engine_status.Installer([sys.executable, '-c', 'raise SystemExit(3)']); failing.start()
    for _ in range(100):
        if failing.view()['status'] != 'running': break
        time.sleep(0.05)
    assert failing.view()['status'] == 'error'


def test_engine_routes_need_confirmation(client):
    view = client.get('/api/settings/openmontage/engine', headers=SETTINGS).json()
    assert view['components'] and view['install']['status'] == 'idle'
    refused = client.post('/api/settings/openmontage/engine/install', json={}, headers=SETTINGS)
    assert refused.status_code == 422 and 'onay' in refused.json()['message']
