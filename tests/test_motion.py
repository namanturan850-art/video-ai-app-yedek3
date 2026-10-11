"""Stage 2: motion-graphic templates, both engines, chain, timing and sound effects."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.channels import DEFAULT_STYLE, PRESETS
from app.motion import templates
from app.motion.clips import render_clip, media_record, is_motion
from app.motion.templates import MotionError, validate, build

NARRATION = ('Im Dezember 1945 verschwanden fünf Flugzeuge vor Florida. Die Ursachen sind Stürme, Strömungen und Navigationsfehler. '
             'Die Insel liegt 1000 Kilometer entfernt und 40% der Schiffe kamen 1950, 1967 und 1991 an.')
SPECS = {
    'stat': {'template': 'stat', 'data': {'value': '1945', 'label': 'verschwanden fünf Flugzeuge'}, 'emphasis': '1945'},
    'map': {'template': 'map', 'data': {'place': 'Florida', 'label': 'Flug 19', 'lat': 26.5, 'lon': -80.0}, 'emphasis': 'Florida'},
    'quote': {'template': 'quote', 'data': {'text': 'verschwanden fünf Flugzeuge vor Florida'}, 'emphasis': 'Flugzeuge'},
    'timeline': {'template': 'timeline', 'data': {'events': [{'date': '1950', 'label': 'Frachter'}, {'date': '1967', 'label': 'Yacht'}, {'date': '1991', 'label': 'Kutter'}]}, 'emphasis': '1967'},
    'compare': {'template': 'compare', 'data': {'title': 'Werte', 'items': [{'label': 'Schiffe', 'value': '40%'}, {'label': 'Entfernung', 'value': '1000'}]}, 'emphasis': '1000'},
    'list': {'template': 'list', 'data': {'title': 'Ursachen', 'items': ['Stürme', 'Strömungen', 'Navigationsfehler']}, 'emphasis': 'Navigationsfehler'},
}
KIT = {**DEFAULT_STYLE, **PRESETS['gizemli']}
FFMPEG = shutil.which('ffmpeg')


@pytest.mark.parametrize('bad', [
    {'template': 'stat', 'data': {'value': '2000', 'label': 'x'}},                      # number not spoken
    {'template': 'map', 'data': {'place': 'Atlantis', 'lat': 1, 'lon': 1}},              # place not spoken
    {'template': 'map', 'data': {'place': 'Florida', 'lat': 120, 'lon': 1}},             # impossible coordinates
    {'template': 'quote', 'data': {'text': 'Ein erfundenes Zitat'}},                     # not an exact phrase
    {'template': 'timeline', 'data': {'events': [{'date': '1800', 'label': 'x'}, {'date': '1950', 'label': 'y'}]}},
    {'template': 'list', 'data': {'items': ['nur eins']}},
    {'template': 'compare', 'data': {'items': [{'label': 'a', 'value': '77'}, {'label': 'b', 'value': '40%'}]}},
    {'template': 'code', 'data': {}}])
def test_templates_never_invent_facts(bad):
    with pytest.raises(MotionError):
        validate(bad, NARRATION)


def test_deterministic_fallback_uses_the_spoken_sentence():
    spec = templates.from_narration('Die Insel liegt 1000 Kilometer entfernt.')
    assert spec['template'] == 'stat' and spec['data']['value'].startswith('1000') and validate(spec, NARRATION)
    assert templates.from_narration('Die Ursachen sind Stürme und Strömungen.')['template'] == 'quote'


def test_counter_keeps_the_spoken_format():
    assert templates.counter_text('1.000.000', 1, 'de') == '1.000.000' and templates.counter_text('1.000.000', .5, 'de') == '500.000'
    assert templates.counter_text('40%', .5, 'de') == '20%' and templates.counter_text('1945', 0, 'de', True) == '1915'
    assert templates.counter_text('3,5 Mio.', 1, 'de') == '3,5 Mio.'


@pytest.mark.skipif(not FFMPEG, reason='FFmpeg absent')
@pytest.mark.parametrize('name', list(SPECS))
def test_each_template_renders_locally_with_the_kit(name, tmp_path):
    spec = validate(SPECS[name], NARRATION)
    path, scene, engine = render_clip(tmp_path, spec, KIT, 4.0, 2.4, ffmpeg=FFMPEG, bridge=None)
    assert engine == 'local' and path.stat().st_size > 10000
    probe = json.loads(subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', str(path)],
                                      capture_output=True, text=True, check=True).stdout)['streams'][0]
    assert (probe['width'], probe['height'], int(probe['nb_read_frames']), probe['pix_fmt']) == (1920, 1080, 120, 'yuv420p')
    frame = tmp_path / 'f.png'
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', '3.0', '-i', str(path), '-frames:v', '1', str(frame)], check=True)
    from PIL import Image
    image = Image.open(frame).convert('RGB')
    accent = tuple(int(KIT['palette']['accent'][i:i + 2], 16) for i in (1, 3, 5))
    near = sum(1 for x in range(0, 1920, 8) for y in range(0, 1080, 8) if sum(abs(a - b) for a, b in zip(image.getpixel((x, y)), accent)) < 60)
    assert near > 20, name  # the kit's accent colour marks the emphasis
    assert scene['emphasis_time'] == 2.4 and scene['sfx'] and all(-1 <= s['t'] <= 4 for s in scene['sfx'])
    again = render_clip(tmp_path, spec, KIT, 4.0, 2.4, ffmpeg=FFMPEG)
    assert again[0] == path and again[2] == 'cache'


class BrokenBridge:
    calls = 0
    def status(self, refresh=False): return {'ready': True}
    def root(self): return Path('/nonexistent-openmontage')
    def call(self, *a, **k): BrokenBridge.calls += 1; raise RuntimeError('compose failed')


@pytest.mark.skipif(not FFMPEG, reason='FFmpeg absent')
def test_openmontage_failure_or_absence_falls_back_to_local(tmp_path):
    spec = validate(SPECS['stat'], NARRATION)
    path, _, engine = render_clip(tmp_path, spec, KIT, 3.0, 1.5, ffmpeg=FFMPEG, bridge=BrokenBridge())
    assert engine == 'local' and path.is_file() and not list(tmp_path.glob('.motion-*'))
    record = media_record(path, spec, build(spec, KIT, 3.0, 1.5), engine)
    assert is_motion(record) and record['media_type'] == 'video' and record['local_path'] == 'stock/' + path.name


REMOTION = Path('/tmp/claude-0/rem/node_modules/@remotion/cli/remotion-cli.js')


@pytest.mark.skipif(not (FFMPEG and REMOTION.is_file() and shutil.which('node')), reason='local Remotion not installed (owner machine uses OpenMontage)')
def test_openmontage_remotion_composition_renders_the_same_scene(tmp_path):
    sys.path.insert(0, str(Path(__file__).parent))
    from remotion_bridge import LocalRemotionBridge
    spec = validate(SPECS['map'], NARRATION)
    bridge = LocalRemotionBridge()
    path, scene, engine = render_clip(tmp_path, spec, KIT, 3.0, 1.6, ffmpeg=FFMPEG, bridge=bridge)
    assert engine == 'openmontage' and bridge.calls[0]['edit_decisions']['bespoke']['composition_id'] == 'AVSMotion'
    from app.motion.raster import draw_frame, MapLayer
    from PIL import Image, ImageChops, ImageStat
    frame = tmp_path / 'om.png'
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-i', str(path), '-vf', 'select=eq(n\\,75)', '-frames:v', '1', str(frame)], check=True)
    local = draw_frame(scene, 75 / 30, Image.new('RGB', (1920, 1080), scene['background']),
                       {i: MapLayer(e['props']) for i, e in enumerate(scene['elements']) if e['type'] == 'map'})
    diff = ImageStat.Stat(ImageChops.difference(Image.open(frame).convert('RGB'), local)).mean
    assert max(diff) < 12, diff  # same scene, same picture (anti-aliasing aside)


@pytest.mark.skipif(not FFMPEG, reason='FFmpeg absent')
def test_render_anchors_motion_to_the_spoken_word_and_mixes_kit_sounds_under_the_voice(tmp_path):
    import hashlib
    from contextlib import closing
    from copy import deepcopy
    from uuid import uuid4
    from PIL import Image
    from app.main import create_app
    from app.production import narration_units, visual_blocks
    from app.stock.models import make_slots
    from app.stock.download import directory
    from test_production import scene
    from test_rendering import NativeRenderClient, await_job, synthetic, url
    from test_subtitles import seed, HEADERS, no_network
    text = 'Ein kurzer Anfang über das Meer. Im Jahr 1945 verschwanden fünf Flugzeuge. Ein ruhiger Abschluss folgt danach.'
    with NativeRenderClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        app = client.app
        st = seed(app, text=text, seconds=9); pid = st['pid']
        units = narration_units(st['source']); ids = [u['unit_id'] for u in units]
        motion = {**scene([ids[1]]), 'media_type': 'motion_graphic',
                  'motion_spec': {'template': 'stat', 'data': {'value': '1945', 'label': 'verschwanden fünf Flugzeuge'}, 'emphasis': '1945'}}
        blocks = visual_blocks({'scenes': [scene([ids[0]]), motion, scene(ids[2:])]}, st['source'], 'de', 135, units=units)
        assert blocks[1]['motion_spec']['template'] == 'stat' and blocks[1]['media_type'] == 'motion_graphic'
        plan = app.state.production.save_generated(pid, st['sid'], 'de', blocks)
        p = app.state.production.handoff(pid); root = app.state.projects._path(pid)
        assert p['scenes'][1]['motion_spec']['data']['value'] == '1945' and len(make_slots(p['scenes'][1])) == 1
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
        # Prepared with a deliberately wrong length/emphasis: render must re-anchor it.
        path, scene_data, engine = render_clip(directory(app.state.projects, pid), spec, DEFAULT_STYLE, motion_slot['duration'] - .5, .7, ffmpeg=FFMPEG)
        motion_slot.update(selected_media=media_record(path, spec, scene_data, engine), segment_start=None)
        state = {'project_id': pid, 'plan_id': plan['plan_id'], 'source_version_id': st['sid'], 'slots': slots, 'revision': 1}
        with closing(app.state.projects._connection()) as c, c:
            c.execute('INSERT INTO stock_plans VALUES (?,?,?,?,?)', (pid, plan['plan_id'], st['sid'], json.dumps(state), st['project']['created_at']))
        app.state.subtitles.create(pid, {'regenerate_confirmed': False})
        for owner, attribute in [(app.state.narration, 'factory'), (app.state.stock, 'factory'), (app.state.scripts, 'provider_factory')]: setattr(owner, attribute, no_network)
        cues = app.state.subtitles.handoff(pid)['subtitles']
        cue = next(c for c in cues if '1945' in c['text'])
        spoken = cue['start'] + (cue['end'] - cue['start']) * cue['text'].find('1945') / len(cue['text'])
        st.update(client=client)
        r = client.post(url(st) + '/jobs', json={'encoder': 'cpu', 'editing_style': 'basic', 'subtitle_burned': False}); assert r.status_code == 202, r.text
        state = await_job(st); assert state['job']['status'] == 'completed', state['job']
        meta = state['active']['metadata']
        assert meta['smart_edit_applied_summary'].get('sound_effects') == 2  # rise + hit at the emphasis
        assert len(list((root / 'stock').glob('*.mp4'))) >= 3  # re-anchored clip rendered next to the prepared one
        out = root / meta['output_local_path']
        # Sound: silence everywhere except the kit effects around the spoken “1945”.
        pcm = subprocess.run([FFMPEG, '-v', 'error', '-i', str(out), '-ac', '1', '-ar', '8000', '-f', 's16le', '-'], capture_output=True, check=True).stdout
        import array
        samples = array.array('h', pcm)
        loud = [i / 8000 for i in range(0, len(samples), 80) if max(abs(v) for v in samples[i:i + 80]) > 300]
        assert loud and spoken - 1.0 <= loud[0] and loud[-1] <= spoken + 1.0, (loud[:3], loud[-3:], spoken)
        peak = max(abs(v) for v in samples)
        assert peak < 32767 * .5  # low level: under the narration, never loud
        # Picture: the number is in the kit accent colour at the emphasis moment.
        frame = tmp_path / 'f.png'
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', f'{spoken + .15:.2f}', '-i', str(out), '-frames:v', '1', str(frame)], check=True)
        image = Image.open(frame).convert('RGB')
        accent = tuple(int(DEFAULT_STYLE['palette']['accent'][i:i + 2], 16) for i in (1, 3, 5))
        assert sum(1 for x in range(0, 1920, 8) for y in range(0, 1080, 8) if sum(abs(a - b) for a, b in zip(image.getpixel((x, y)), accent)) < 60) > 50
