"""Kapanış anı olan videoda: abone ol + zil klibi sahnede, ardından 20 sn YouTube bitiş ekranı."""
import shutil
import subprocess

import pytest

from app.channels import DEFAULT_STYLE
from app.moments.draw import END_SCREEN_SECONDS

FFMPEG = shutil.which('ffmpeg')


@pytest.mark.skipif(not FFMPEG, reason='FFmpeg absent')
@pytest.mark.parametrize('with_outro', [True, False])
def test_closing_moment_adds_a_twenty_second_end_screen_and_nothing_else(with_outro, tmp_path):
    import hashlib
    import json
    from contextlib import closing
    from copy import deepcopy
    from uuid import uuid4
    from PIL import Image
    from app.main import create_app
    from app.motion.clips import media_record, render_clip
    from app.moments.spec import moment_spec
    from app.production import narration_units, visual_blocks
    from app.stock.download import directory
    from app.stock.models import make_slots
    from test_production import scene
    from test_rendering import NativeRenderClient, synthetic, url
    from test_subtitles import seed, HEADERS, no_network
    text = 'Ein kurzer Anfang über das Meer. Eine genaue Erklärung folgt. Abonniert den Kanal und bis zum nächsten Mal.'
    with NativeRenderClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        app = client.app
        st = seed(app, text=text, seconds=9); pid = st['pid']
        units = narration_units(st['source']); ids = [u['unit_id'] for u in units]
        blocks = visual_blocks({'scenes': [scene(ids[:2]), scene(ids[2:])]}, st['source'], 'de', 135, units=units)
        plan = app.state.production.save_generated(pid, st['sid'], 'de', blocks)
        p = app.state.production.handoff(pid); root = app.state.projects._path(pid)
        clip = synthetic(root / 'stock', uuid4().hex + '.mp4', ['-f', 'lavfi', '-i', 'testsrc2=s=1280x720:d=12:r=30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p'])
        data = clip.read_bytes()
        stock = {'provider': 'pixabay', 'media_id': 'v1', 'media_type': 'video', 'local_path': 'stock/' + clip.name, 'file_size': len(data),
                 'sha256': hashlib.sha256(data).hexdigest(), 'width': 1280, 'height': 720, 'duration': 12.0, 'content_type': 'video/mp4', 'description': 'x', 'source_metadata': {}}
        slots = []
        for s in p['scenes']:
            for slot in make_slots(s):
                slots.append({**slot, 'status': 'complete', 'selected_media': deepcopy(stock), 'segment_start': 6.0 if slots else None})
        if with_outro:
            last = slots[-1]
            spec = moment_spec('outro', 'subscribe', 'Titel', 'Kanal')
            path, scene_data, engine = render_clip(directory(app.state.projects, pid), spec, DEFAULT_STYLE, last['duration'], 1.0, ffmpeg=FFMPEG)
            last.update(selected_media=media_record(path, spec, scene_data, engine), segment_start=None)
        state = {'project_id': pid, 'plan_id': plan['plan_id'], 'source_version_id': st['sid'], 'slots': slots, 'revision': 1}
        with closing(app.state.projects._connection()) as c, c:
            c.execute('INSERT INTO stock_plans VALUES (?,?,?,?,?)', (pid, plan['plan_id'], st['sid'], json.dumps(state), st['project']['created_at']))
        if with_outro: app.state.settings.save('general', {'end_screen': True})  # the end screen is off unless the owner switches it on
        app.state.subtitles.create(pid, {'regenerate_confirmed': False})
        for owner, attribute in [(app.state.narration, 'factory'), (app.state.stock, 'factory'), (app.state.scripts, 'provider_factory')]: setattr(owner, attribute, no_network)
        st.update(client=client)
        r = client.post(url(st) + '/jobs', json={'encoder': 'cpu', 'editing_style': 'adaptive', 'subtitle_burned': False}); assert r.status_code == 202, r.text
        import time
        deadline = time.monotonic() + 300  # drawing the 20 s end screen + 29 s film encode
        while client.get(url(st)).json()['job']['status'] in ('queued', 'preparing', 'rendering', 'validating') and time.monotonic() < deadline: time.sleep(.2)
        state = client.get(url(st)).json(); assert state['job']['status'] == 'completed', state['job']
        meta = state['active']['metadata']; out = root / meta['output_local_path']
        extra = END_SCREEN_SECONDS if with_outro else 0
        assert meta['duration'] == pytest.approx(9 + extra, abs=.1)
        if not with_outro:
            return
        # The narration part is untouched: stock picture at 1 s; the end screen is one flat colour in the middle.
        frame = tmp_path / 'end.png'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', f'{9 + 10:.2f}', '-i', str(out), '-frames:v', '1', str(frame)], check=True)
        image = Image.open(frame).convert('RGB')
        centre = {image.getpixel((x, y)) for x in range(300, 1700, 100) for y in range(200, 900, 100)}
        assert len(centre) <= 3, len(centre)  # (video compression noise aside) room for YouTube's end-screen elements
        early = tmp_path / 'early.png'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', '1.0', '-i', str(out), '-frames:v', '1', str(early)], check=True)
        assert len({Image.open(early).convert('RGB').getpixel((x, y)) for x in range(300, 1700, 100) for y in range(200, 900, 100)}) > 10
