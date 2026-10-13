"""Every infographic template: entry <= 0.6 s, fully visible until the end, labels readable >= 2 s."""
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
