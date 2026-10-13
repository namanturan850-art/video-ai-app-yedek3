"""Opening the project/render screen must never draw motion graphics.

Regression: after the motion engine version changed, every saved motion clip
looked outdated and the render screen redrew all of them inside a page request
while holding the project lock, so the project page timed out (“Uygulamaya
ulaşılamadı”). Only the background render job draws."""
import hashlib
import json
import time
from contextlib import closing
from copy import deepcopy
from uuid import uuid4

from app.channels import DEFAULT_STYLE
from app.motion.clips import media_record, render_clip
from test_motion import FFMPEG


def test_render_view_and_job_start_never_draw_motion_clips(tmp_path, monkeypatch):
    from app.main import create_app
    from app.production import narration_units, visual_blocks
    from app.stock.models import make_slots
    from app.stock.download import directory
    from app.motion import clips
    from test_production import scene
    from test_rendering import NativeRenderClient, synthetic, url
    from test_subtitles import seed, HEADERS, no_network
    text = 'Ein kurzer Anfang über das Meer. Im Jahr 1945 verschwanden fünf Flugzeuge. Ein ruhiger Abschluss folgt danach.'
    with NativeRenderClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        app = client.app
        st = seed(app, text=text, seconds=9); pid = st['pid']
        units = narration_units(st['source']); ids = [u['unit_id'] for u in units]
        motion = {**scene([ids[1]]), 'media_type': 'motion_graphic',
                  'motion_spec': {'template': 'stat', 'data': {'value': '1945', 'label': 'verschwanden fünf Flugzeuge'}, 'emphasis': '1945'}}
        blocks = visual_blocks({'scenes': [scene([ids[0]]), motion, scene(ids[2:])]}, st['source'], 'de', 135, units=units)
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
        motion_slot = next(s for s in slots if s['scene_id'] == p['scenes'][1]['scene_id'])
        spec = p['scenes'][1]['motion_spec']
        # An outdated clip (wrong length/emphasis, like one drawn by an older motion engine).
        path, scene_data, engine = render_clip(directory(app.state.projects, pid), spec, DEFAULT_STYLE, motion_slot['duration'] - .5, .7, ffmpeg=FFMPEG)
        motion_slot.update(selected_media=media_record(path, spec, scene_data, engine), segment_start=None)
        state = {'project_id': pid, 'plan_id': plan['plan_id'], 'source_version_id': st['sid'], 'slots': slots, 'revision': 1}
        with closing(app.state.projects._connection()) as c, c:
            c.execute('INSERT INTO stock_plans VALUES (?,?,?,?,?)', (pid, plan['plan_id'], st['sid'], json.dumps(state), st['project']['created_at']))
        app.state.subtitles.create(pid, {'regenerate_confirmed': False})
        for owner, attribute in [(app.state.narration, 'factory'), (app.state.stock, 'factory'), (app.state.scripts, 'provider_factory')]: setattr(owner, attribute, no_network)

        drawn = []
        real = clips.raster_render  # the actual drawing (a cached clip is only read)
        monkeypatch.setattr(clips, 'raster_render', lambda *a, **k: drawn.append(1) or real(*a, **k))
        st.update(client=client)
        started = time.monotonic()
        for _ in range(3):
            assert client.get(url(st)).status_code == 200
            assert client.get(f'/api/projects/{pid}').status_code == 200
        assert drawn == [] and time.monotonic() - started < 10  # page requests never draw
        opts = {'encoder': 'cpu', 'editing_style': 'basic', 'subtitle_burned': False}
        from app.rendering.models import options
        inputs = app.state.rendering._inputs(pid, options(opts))
        assert drawn == [] and inputs['motion_pending'] == 1
        # The background job draws (draw=True) and the result is reused afterwards.
        drawn_inputs = app.state.rendering._inputs(pid, options(opts), True, draw=True)
        assert drawn == [1] and drawn_inputs['motion_pending'] == 0
        again = app.state.rendering._inputs(pid, options(opts))
        assert drawn == [1] and again['motion_pending'] == 0 and again['fingerprint'] == drawn_inputs['fingerprint']
