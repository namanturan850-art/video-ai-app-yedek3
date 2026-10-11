"""Real FFmpeg render of director media: portrait clip on a blurred backdrop,
two non-overlapping parts of one long clip, a generated card and its
continuation. Local only (FFmpeg + Pillow), no network."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import shutil
import subprocess
from uuid import uuid4

import pytest

from app.main import create_app
from app.production import narration_units, visual_blocks
from app.stock.cards import render_card
from app.stock.models import make_slots
from test_production import scene
from test_rendering import NativeRenderClient, await_job, synthetic, url
from test_subtitles import seed, HEADERS, no_network


def media(path, mid, kind, w, h, duration=None, provider='pixabay'):
    data = path.read_bytes()
    return {'provider': provider, 'media_id': mid, 'media_type': kind, 'local_path': 'stock/' + path.name, 'file_size': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'width': w, 'height': h, 'duration': duration,
            'content_type': 'video/mp4' if kind == 'video' else 'image/png', 'description': mid, 'source_metadata': {}}


@pytest.fixture
def director_render(tmp_path):
    if not shutil.which('ffmpeg'): pytest.skip('FFmpeg absent')
    with NativeRenderClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        app = client.app
        st = seed(app, text='Ein kurzer Anfang über das Meer. Eine genaue Erklärung folgt jetzt. Im Jahr 1945 geschah es. Ein ruhiger Abschluss.', seconds=8)
        pid = st['pid']
        units = narration_units(st['source']); ids = [u['unit_id'] for u in units]
        blocks = visual_blocks({'scenes': [scene(ids[:2]), scene(ids[2:])]}, st['source'], 'de', 135, units=units)
        plan = app.state.production.save_generated(pid, st['sid'], 'de', blocks)
        p = app.state.production.handoff(pid); root = app.state.projects._path(pid)
        portrait = synthetic(root / 'stock', uuid4().hex + '.mp4', ['-f', 'lavfi', '-i', 'testsrc2=s=720x1280:d=12:r=30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p'])
        card_path = root / 'stock' / (uuid4().hex + '.png'); render_card(card_path, 'number', 'Im Jahr 1945 geschah es')
        clip = media(portrait, 'portrait1', 'video', 720, 1280, 12.0)
        card = media(card_path, 'card-x', 'image', 1920, 1080, provider='generated')
        slots = []
        for s in p['scenes']:
            template = make_slots(s)[0]
            a, b = s['start_estimate'], s['end_estimate']; mid = round((a + b) / 2, 3)
            for order, (x, y) in enumerate(((a, mid), (mid, b)), 1):
                slots.append({**deepcopy(template), 'slot_id': uuid4().hex, 'order': order, 'estimated_start': x, 'estimated_end': y, 'duration': round(y - x, 3), 'status': 'complete'})
        slots[0].update(selected_media=deepcopy(clip), segment_start=None)
        slots[1].update(selected_media=deepcopy(clip), segment_start=6.0)          # other part of the same long clip
        slots[2].update(selected_media=deepcopy(card))
        slots[3].update(selected_media=deepcopy(card), continuation_of=slots[2]['slot_id'])
        state = {'project_id': pid, 'plan_id': plan['plan_id'], 'source_version_id': st['sid'], 'slots': slots, 'revision': 1}
        with closing(app.state.projects._connection()) as c, c:
            c.execute('INSERT INTO stock_plans VALUES (?,?,?,?,?)', (pid, plan['plan_id'], st['sid'], json.dumps(state), st['project']['created_at']))
        app.state.subtitles.create(pid, {'regenerate_confirmed': False})
        for owner, attribute in [(app.state.narration, 'factory'), (app.state.stock, 'factory'), (app.state.scripts, 'provider_factory')]: setattr(owner, attribute, no_network)
        st.update(client=client, root=root, slots=slots)
        yield st


def frame(path, seconds, out):
    subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-y', '-ss', str(seconds), '-i', str(path), '-frames:v', '1', str(out)], check=True)
    from PIL import Image
    return Image.open(out).convert('RGB')


@pytest.mark.parametrize('style', ['basic', 'adaptive'])
def test_render_portrait_blur_segments_and_cards(director_render, tmp_path, style):
    st = director_render; c = st['client']
    handoff = c.app.state.subtitles.handoff(st['pid'])
    raw = {s['slot_id']: s for s in handoff['stock_slots']}
    assert raw[st['slots'][3]['slot_id']]['continuation_of'] == st['slots'][2]['slot_id'] and raw[st['slots'][1]['slot_id']]['segment_start'] == 6.0
    r = c.post(url(st) + '/jobs', json={'encoder': 'cpu', 'editing_style': style}); assert r.status_code == 202, r.text
    state = await_job(st); assert state['job']['status'] == 'completed', state['job']
    out = st['root'] / state['active']['metadata']['output_local_path']
    first = frame(out, 0.8, tmp_path / 'a.png')
    # Left/right of the portrait clip: blurred picture, not flat padding.
    side = [first.getpixel((x, y)) for x in range(20, 400, 40) for y in range(100, 1000, 100)]
    # Old behaviour was flat padding colour 0x101823 (16,24,35).
    assert len(set(side)) >= 3 and max(sum(p) for p in side) > 150 and (16, 24, 35) not in side, side[:5]
    import os
    if os.environ.get("KEEP_FRAMES"): import shutil as s; s.copy(out, os.environ["KEEP_FRAMES"])
    end = frame(out, 7.2, tmp_path / "b.png")
    assert end.getpixel((960, 20))[2] > end.getpixel((960, 20))[0]  # card navy background, not black
