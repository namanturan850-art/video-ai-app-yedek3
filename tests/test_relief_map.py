"""Colour relief map: offline elevation + Natural Earth areas, [BÖLGE] / [OK] / [YAKINLAŞ]."""
import subprocess

import numpy as np
import pytest
from PIL import Image

from app.motion import relief
from app.motion.templates_extra import MarkerError, parse


@pytest.mark.parametrize('name,kind', [('Bretagne', 'region'), ('Guyane', 'adm1'), ('Bayern', 'adm1'), ('Lombardia', 'region'),
                                       ('Noord-Holland', 'adm1'), ('Andalucía', 'region'), ('Minas Gerais', 'adm1'), ('Brasil', 'country'),
                                       ('Deutschland', 'country'), ('Italia', 'country'), ('Vallée du Rhône', 'river'), ('Martinique', 'adm1')])
def test_areas_of_many_countries_are_found_offline(name, kind):
    unit = relief.find(name)
    assert unit and unit['kind'] == kind and (unit['polygons'] or unit['lines'])


def test_markers_become_relief_specs():
    assert parse('region', 'Bretagne')['data'] == {'mode': 'region', 'target': 'Bretagne', 'source': 'Bretagne'}
    assert parse('arrow', 'Lyon > Marseille')['data']['mode'] == 'arrow'
    assert parse('zoom', 'Guyane')['template'] == 'relief'
    with pytest.raises(MarkerError): parse('region', 'Atlantis-Nirgendwo')
    with pytest.raises(MarkerError): parse('arrow', 'Lyon')


def test_paste_knows_the_new_markers():
    from app.scripts.paste import KINDS
    assert KINDS['BOLGE'] == 'region' and KINDS['OK'] == 'arrow'


def test_elevation_colours_and_flat_sea():
    z = relief.grid()
    assert z.shape == (1081, 2160) and z.max() > 6000 and z.min() < -9000  # ETOPO: Himalaya, ocean trenches
    picture = np.asarray(relief.terrain(relief.view_around((-5.2, 47.2, -1.0, 49.0)), 480, 270), dtype=np.float32)
    sea = picture[100:160, 10:60]  # Atlantic west of Brittany
    assert sea.std(axis=(0, 1)).max() < 1.5  # one flat, clean blue
    alps = np.asarray(relief.terrain(relief.view_around((5.5, 44.5, 8.5, 46.5)), 480, 270), dtype=np.float32)
    assert alps[..., 0].max() - alps[..., 0].min() > 60  # heights change the colour


def test_relief_clip_label_and_highlight_on_the_first_frame(tmp_path):
    from app.channels import DEFAULT_STYLE
    from app.motion.raster import render
    from app.motion.templates import build
    scene = build(parse('region', 'Bretagne'), DEFAULT_STYLE, 1.0, .6, 'fr')
    out = tmp_path / 'relief.mp4'
    assert render(scene, out, 'ffmpeg') == 30
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(out), '-frames:v', '1', str(tmp_path / 'f0.png')], check=True)
    frame = np.asarray(Image.open(tmp_path / 'f0.png').convert('RGB'), dtype=np.int16)
    red = (frame[..., 0] > 150) & (frame[..., 1] < 110) & (frame[..., 2] < 110)
    white = (frame > 235).all(axis=-1)
    assert red.mean() > .03  # the area is filled red
    middle = white[400:680, 700:1400]
    assert middle.mean() > .01  # the bold white label is fully visible on frame 0
