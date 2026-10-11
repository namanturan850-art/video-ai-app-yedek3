"""Stage 3: YouTube titles, description, chapters, tags, credits and thumbnail. No network, no upload."""
import shutil
import subprocess
from io import BytesIO

import pytest
from PIL import Image

from test_media_director_topics import build, complete


@pytest.fixture
def topic(tmp_path, monkeypatch):
    client, pid, world, claude, fake = build(tmp_path, monkeypatch, 'bermuda', 'gemini')
    complete(client, pid)
    yield client, pid, fake
    client.__exit__(None, None, None)


def test_titles_description_chapters_tags_and_credits(topic):
    client, pid, fake = topic
    view = client.get(f'/api/projects/{pid}/youtube').json()
    assert view['engine'] == 'gemini' and not view['package'] and not view['ai_background']['enabled']
    r = client.post(f'/api/projects/{pid}/youtube/text')
    assert r.status_code == 200, r.text
    p = r.json()
    assert len(p['titles']) == 5 and all(50 <= t['length'] <= 75 for t in p['titles']) and p['chosen_title'] == p['titles'][0]['text']
    assert 10 <= len(p['tags']) <= 15 and p['hashtags'] == ['#Doku', '#Wissen', '#Fakten']
    d = p['description']
    assert d.startswith('Was steckt wirklich dahinter?\nDie Antwort überrascht.')
    chapters = d.split('Kapitel:\n')[1].split('\n\n')[0].splitlines()
    assert len(chapters) >= 3 and chapters[0].startswith('0:00 ')  # YouTube chapter rules
    starts = [int(c.split()[0].split(':')[0]) * 60 + int(c.split()[0].split(':')[1]) for c in chapters]
    assert starts == sorted(starts) and all(b - a >= 10 for a, b in zip(starts, starts[1:]))
    assert 'Stockmaterial: Pixabay' in d  # credits for the stock media actually used
    sent = fake.requests[-1]['contents'][0]['parts'][-1]['text']
    assert 'video language "de"' in sent and 'COMPLEMENT the titles' in sent
    r = client.put(f'/api/projects/{pid}/youtube', json={'chosen_title': 'Mein eigener Titel', 'tags': ['a', '#b']})
    assert r.json()['chosen_title'] == 'Mein eigener Titel' and r.json()['tags'] == ['a', 'b']
    assert client.put(f'/api/projects/{pid}/youtube', json={'chosen_title': 'x' * 101}).status_code == 422
    assert client.post(f'/api/projects/{pid}/youtube/ai-background', json={'cost_confirmed': True}).status_code == 409  # off by default


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg absent')
def test_thumbnail_from_rendered_frames_three_layouts_and_png(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from test_rendering import NativeRenderClient, install_ready, url, await_job
    from test_scripts import HEADERS
    with NativeRenderClient(create_app(tmp_path / 'data'), headers=HEADERS) as c:
        st = install_ready(c.app, seconds=12); st.update(client=c, storage=tmp_path / 'data')
        assert c.post(url(st) + '/jobs', json={'encoder': 'cpu'}).status_code == 202
        assert await_job(st)['job']['status'] == 'completed'
        base = f'/api/projects/{st["pid"]}/youtube'
        assert c.get(base).json()['video_ready']
        frames = c.post(base + '/frames').json()['frames']
        assert 1 <= len(frames) <= 5
        img = Image.open(BytesIO(c.get(frames[0]['url']).content)); assert img.size == (1280, 720)
        c.put(base, json={'chosen_title': 'Das Rätsel des Bermuda-Dreiecks'})
        r = c.post(base + '/thumbnails', json={'frame': frames[0]['id'], 'text': 'Niemand kam zurück'}).json()
        assert [t['layout'] for t in r['thumbnails']] == ['left', 'banner', 'frame'] and r['warning'] == ''
        for t in r['thumbnails']:
            png = c.get(t['url'] + '?download=true')
            assert png.headers['content-disposition'].startswith('attachment') and png.content[:8] == b'\x89PNG\r\n\x1a\n'
            assert Image.open(BytesIO(png.content)).size == (1280, 720)
        repeat = c.post(base + '/thumbnails', json={'frame': frames[0]['id'], 'text': 'Rätsel Bermuda-Dreiecks'}).json()
        assert 'tekrar' in repeat['warning']  # thumbnail text should complement, not repeat, the title
        assert c.post(base + '/thumbnails', json={'frame': frames[0]['id'], 'text': 'eins zwei drei vier fünf'}).status_code == 422
        assert c.get(base + '/files/frames/..%2Fx.png').status_code in (404, 422)


def test_optional_gemini_background_needs_setting_and_consent(topic, monkeypatch):
    client, pid, fake = topic
    s = client.app.state.settings
    out = BytesIO(); Image.new('RGB', (1024, 576), (20, 40, 90)).save(out, 'PNG')
    calls = []
    monkeypatch.setattr('app.providers.images.GeminiImageProvider.generate_image',
                        lambda self, prompt, cost_confirmed=False: calls.append((prompt, cost_confirmed)) or {'mime_type': 'image/png', 'data': out.getvalue()})
    s.record_image_models('gemini', ['gemini-image-test'], s.gemini_config())
    s.save_images({'gemini_model': 'gemini-image-test', 'thumbnail_ai': True})
    view = client.get(f'/api/projects/{pid}/youtube').json()
    assert view['ai_background']['enabled'] and 'kota' in view['ai_background']['note']
    assert client.post(f'/api/projects/{pid}/youtube/ai-background', json={}).status_code == 409 and not calls  # explicit consent first
    frames = client.post(f'/api/projects/{pid}/youtube/ai-background', json={'cost_confirmed': True}).json()['frames']
    assert frames[0]['ai'] and len(calls) == 1 and 'no text' in calls[0][0]
    assert Image.open(BytesIO(client.get(frames[0]['url']).content)).size == (1280, 720)
