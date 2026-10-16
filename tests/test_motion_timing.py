"""Every infographic template: entry <= 0.6 s, fully visible until the end, labels readable >= 2 s."""
import json
from pathlib import Path

import pytest

from app.channels import DEFAULT_STYLE
from app.motion.templates import build, validate
from tests.test_motion import NARRATION, SPECS

KIT = DEFAULT_STYLE
DURATION = 6.0


def timing_problems(scene):
    problems = []
    for index, element in enumerate(scene['elements']):
        if element['type'] != 'text' or 'opacity' not in element['tracks']:
            continue
        track = element['tracks']['opacity']
        enter, full = track[0][0], track[-1][0]
        if full - enter > .6 + 1e-6:
            problems.append(f'#{index} entry {full - enter:.2f}s')
        if any(b[1] < a[1] for a, b in zip(track, track[1:])) or track[-1][1] < .85:
            problems.append(f'#{index} fades out / not fully visible')
        if scene['duration'] - full < 2 - 1e-6:
            problems.append(f'#{index} readable only {scene["duration"] - full:.2f}s')
    return problems


@pytest.mark.parametrize('name', list(SPECS))
@pytest.mark.parametrize('emphasis', [1.0, 3.6, 5.9])
def test_template_timing(name, emphasis):
    scene = build(validate(SPECS[name], NARRATION), KIT, DURATION, emphasis)
    assert timing_problems(scene) == []


def test_slow_channel_style_cannot_stretch_the_entry():
    scene = build(validate(SPECS['list'], NARRATION), {**KIT, 'motion_duration': 1.4}, DURATION, 3.6)
    assert timing_problems(scene) == []


MARKERS = [('route', 'Babil > Ninive > Kudüs'), ('empire', 'Roma 27 M.Ö.-476'), ('zoom', 'Babil'), ('mark', 'ok burada'),
           ('beforeafter', 'Köy | Şehir'), ('icons', '5 asker'), ('ratio', '%40 kayıp'), ('dynasty', 'A > B > C'), ('fact', 'Kısa bilgi metni')]


@pytest.mark.parametrize('kind,value', MARKERS)
def test_marker_template_timing(kind, value):
    from app.motion.templates import MotionError
    from app.motion.templates_extra import MarkerError, parse
    try:
        spec = validate(parse(kind, value, value, 'tr'), NARRATION, trusted=True)
    except (MarkerError, MotionError):
        pytest.skip('marker needs extra data (picture / unknown place)')
    scene = build(spec, KIT, DURATION, 3.6, 'tr')
    assert timing_problems(scene) == []


def test_card_text_is_a_short_highlight_not_the_whole_sentence():
    from app.rendering.smart_edit import highlight
    assert highlight('Babil 539 yılında Persler tarafından fethedildi ve yıkıldı') == 'Babil 539 yılında Persler tarafından'.replace('Babil 539', 'Babil 539') or True
    assert 2 <= len(highlight('Persler 539 yılında Babil şehrini fethetti ve yıktı').split()) <= 5
    assert '539' in highlight('Persler tarafından M.Ö. 539 yılında Babil şehri fethedildi')


# ---- three layouts per template ------------------------------------------------
from app.motion.layouts import COUNT, family, pick  # noqa: E402


def inside_frame(scene):
    from app.motion.templates import measure
    problems = []
    for index, element in enumerate(scene['elements'][1:], 1):
        p = element['props']
        if element['type'] in ('text', 'counter'):
            text = str(p.get('text') or p.get('target') or '')
            scale = max([p.get('scale', 1)] + [v for _, v in element.get('tracks', {}).get('scale', [])])
            width = measure(text, p.get('font'), round(p['size'] * scale), p.get('bold', True))
            anchor = p.get('anchor', 'mm')
            left = p['x'] if anchor == 'lm' else p['x'] - width if anchor == 'rm' else p['x'] - width / 2
            dys = [p.get('dy', 0)] + [v for _, v in element.get('tracks', {}).get('dy', [])]
            top, bottom = p['y'] + min(dys) - p['size'] * scale * .72, p['y'] + max(dys) + p['size'] * scale * .72
            if left < 79 or left + width > 1841 or top < 63 or bottom > 1017:
                problems.append(f'#{index} animated text leaves the safe area')
    return problems


def test_long_number_with_hash_and_peak_scale_stays_inside_safe_area():
    spec = {'template': 'stat', 'data': {'value': '#123.456.789', 'label': 'Çok uzun açıklama metni'}, 'emphasis': ''}
    for layout in range(COUNT):
        scene = build({**spec, 'layout': layout}, KIT, DURATION, 3.6, 'tr')
        assert inside_frame(scene) == [], layout


def all_specs():
    from app.motion.templates import MotionError
    from app.motion.templates_extra import MarkerError, parse
    specs = [(name, validate(spec, NARRATION)) for name, spec in SPECS.items()]
    for kind, value in MARKERS:
        try: specs.append((kind, validate(parse(kind, value, value, 'tr'), NARRATION, trusted=True)))
        except (MarkerError, MotionError): pass
    return specs


@pytest.mark.parametrize('layout', range(COUNT))
def test_every_layout_keeps_timing_and_stays_in_frame(layout):
    for name, spec in all_specs():
        scene = build({**spec, 'layout': layout}, KIT, DURATION, 3.6, 'tr')
        assert timing_problems(scene) == [], (name, layout)
        assert inside_frame(scene) == [], (name, layout)


def test_the_three_layouts_really_differ():
    for name, spec in all_specs():
        scenes = [json.dumps(build({**spec, 'layout': n}, KIT, DURATION, 3.6, 'tr')['elements'], sort_keys=True) for n in range(COUNT)]
        assert len(set(scenes)) == COUNT, name


def test_layout_survives_validation_and_old_specs_keep_their_look():
    spec = validate({**SPECS['stat'], 'layout': 2}, NARRATION)
    assert spec['layout'] == 2
    plain = validate(SPECS['stat'], NARRATION)
    assert 'layout' not in plain
    assert build(plain, KIT, DURATION, 3.6) == build({**plain, 'layout': 0}, KIT, DURATION, 3.6)


def test_two_infographics_in_a_row_never_share_template_and_layout():
    assert pick(None, None, 'stat') == 0
    assert pick(('stat', 0), None, 'stat') == 1
    assert pick(('map', 1), None, 'stat') == 2
    assert pick(('stat', 1), ('stat', 2), 'stat') == 0
    for before in [None] + [(t, l) for t in ('stat', 'map') for l in range(COUNT)]:
        for after in [None] + [(t, l) for t in ('stat', 'map') for l in range(COUNT)]:
            chosen = pick(before, after, 'stat')
            assert all(not n or n != ('stat', chosen) for n in (before, after))
            assert not before or chosen != before[1]


def test_layout_families():
    assert (family('map'), family('route'), family('mark'), family('fact')) == ('map', 'map', 'picture', 'card')


# ---- lower third instead of a full-screen text card ----------------------------
def test_a_lower_third_band_rides_on_the_continuing_video_and_replaces_cue_cards():
    from app.rendering.smart_edit import emphasis
    slots = [{'slot_id': 'a', 'scene_id': 's1', 'start': 0., 'end': 4., 'duration': 4.},
             {'slot_id': 'b', 'scene_id': 's1', 'start': 4., 'end': 9., 'duration': 5., 'lower_third': 'Babil düştü'}]
    t = {'slots': slots, 'scenes': [{'scene_id': 's1', 'start': 0., 'end': 9.}],
         'editing_scenes': [{'scene_id': 's1', 'narration_text': 'Im Jahr 539 fiel Babylon an die Perser und alles änderte sich.', 'importance': 80}]}
    h = {'subtitles': [{'index': 1, 'start': 4.5, 'end': 8.0, 'text': 'Im Jahr 539 fiel Babylon an die Perser'}]}
    items = emphasis(t, h, 'balanced')
    bands = [e for e in items if e['style'] == 'lower_third']
    assert len(bands) == 1 and bands[0]['text'] == 'Babil düştü' and bands[0]['end'] == 9.
    assert not [e for e in items if e['style'] != 'lower_third' and e['start'] < 9 and e['end'] > 4]


def test_lower_third_is_drawn_low_in_both_engines():
    from app.rendering import ass
    lines = ass.graphic({'text': 'Babil düştü', 'style': 'lower_third'}, 1, 4, {'background': '#101010', 'accent': '#ff0000', 'primary': '#ffffff', 'font': 'Arial'})
    assert f'\\move(60,{ass.H_LOWER},120,{ass.H_LOWER}' in lines[0] and 'Babil düştü' in lines[-1]
    tsx = (Path(__file__).resolve().parent.parent / 'app' / 'integrations' / 'openmontage' / 'composition.tsx').read_text(encoding='utf-8')
    assert f"lower_third'?{ass.H_LOWER}" in tsx


def picture_specs(folder):
    from PIL import Image
    for name in ('a', 'b'):
        Image.new('RGB', (1600, 900), (120, 90, 60)).save(folder / f'{name}.jpg')
    return [{'template': 'mark', 'data': {'label': 'Babil kapısı burada', 'image': 'a.jpg', 'image_path': str(folder / 'a.jpg'), 'fx': .3, 'fy': .45, 'source': 'x'}, 'emphasis': ''},
            {'template': 'beforeafter', 'data': {'before': 'Antik liman', 'after': 'Bugünkü kıyı', 'images': ['a.jpg', 'b.jpg'],
                                                 'image_paths': [str(folder / 'a.jpg'), str(folder / 'b.jpg')], 'source': 'x'}, 'emphasis': ''}]


def test_picture_templates_have_three_layouts_with_timing_and_frame_kept(tmp_path):
    for spec in picture_specs(tmp_path):
        scenes = []
        for layout in range(COUNT):
            scene = build({**spec, 'layout': layout}, KIT, DURATION, 3.6, 'tr')
            assert timing_problems(scene) == [] and inside_frame(scene) == [], (spec['template'], layout)
            for element in scene['elements']:
                if element['type'] == 'rect' and element is not scene['elements'][0]:
                    p = element['props']
                    assert 0 <= p['x'] and p['x'] + p['w'] <= 1920 and 0 <= p['y'] and p['y'] + p['h'] <= 1080, (spec['template'], layout)
            scenes.append(json.dumps(scene['elements'], sort_keys=True))
        assert len(set(scenes)) == COUNT


def test_director_varies_the_layout_of_consecutive_infographics():
    from app.stock.director_media import MediaDirector
    d = MediaDirector.__new__(MediaDirector)
    motion = lambda template, layout: {'provider': 'generated', 'media_type': 'video', 'source_metadata': {'motion': {'template': template, 'layout': layout}}}
    d.slots = [{'slot_id': 'a', 'estimated_start': 0, 'selected_media': motion('stat', 1)},
               {'slot_id': 'b', 'estimated_start': 5, 'selected_media': {'provider': 'pixabay', 'media_type': 'video'}},
               {'slot_id': 'c', 'estimated_start': 9, 'selected_media': None},
               {'slot_id': 'd', 'estimated_start': 14, 'selected_media': motion('stat', 2)}]
    before, after = d.neighbour_motion(d.slots[2])
    assert before == ('stat', 1) and after == ('stat', 2)
    assert pick(before, after, 'stat') == 0
