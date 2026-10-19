from app.motion.looks import look_of, restyle
from app.motion.templates import build, validate

from app.channels import DEFAULT_STYLE
from tests.test_motion import NARRATION

KIT = DEFAULT_STYLE


def specs():
    out = []
    for n in range(8):
        text = 'Ursachen %d' % n
        out.append(validate({'template': 'list', 'data': {'title': text, 'items': ['Stürme', 'Strömungen', 'Navigationsfehler']}, 'emphasis': 'Navigationsfehler'}, NARRATION))
    return out


def test_look_is_deterministic_and_varies_between_specs():
    items = specs()
    assert [look_of(s) for s in items] == [look_of(s) for s in items]
    assert len({look_of(s) for s in items}) >= 3


def test_restyled_scene_keeps_entry_and_readable_time():
    for spec in specs():
        scene = build(spec, KIT, 8., 3.)
        for e in scene['elements']:
            t = e['tracks'].get('opacity')
            if e['type'] == 'text' and t:
                assert t[-1][0] - t[0][0] <= .6 + 1e-6
                assert scene['duration'] - t[-1][0] >= 2 - 1e-6


def test_entrance_direction_differs_between_cards_but_the_brand_accent_stays():
    rises = set()
    for spec in specs():
        scene = build(spec, KIT, 8., 3.)
        fills = {str(v).lower() for e in scene['elements'] for v in e['props'].values() if isinstance(v, str)}
        assert KIT['palette']['accent'].lower() in fills
        rises.add(tuple(round(e['tracks']['dy'][0][1], 1) for e in scene['elements'] if 'dy' in e['tracks'])[:1])
    assert len(rises) >= 2


def test_moments_and_maps_are_untouched():
    spec = {'template': 'map'}
    scene = {'elements': [], 'duration': 5}
    assert restyle(scene, spec, KIT) is scene
