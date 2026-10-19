import os
import stat

import pytest

from app.editor import manual_brief
from app.motion import html_layer
from app.rendering import tools


def fake_ffmpeg(tmp_path, version, name):
    path = tmp_path / name
    path.write_text(f'#!/bin/sh\necho "ffmpeg version {version} Copyright (c) the FFmpeg developers"\n', encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def package(seconds=60.0):
    contract = {'html_katmanlari': html_layer.contract()}
    return {'project': {'name': 'T', 'topic': 'Konu', 'language': 'tr'},
            'narration': [{'scene_id': 's1', 'start': 0.0, 'end': seconds, 'text': 'Sıcaklık 28 derece.'}],
            'sentence_index': [], 'output_template': {'schema': 'naman.manual-plan.v1'}, 'output_contract': contract,
            'base': {'plan_id': 'p', 'revision': 1}, 'archive': [], 'editing_slots': [], 'maps': [],
            'animation_reference_selection': {'rules': [], 'scenes': []}}


def test_density_scales_with_duration_and_is_in_the_message():
    assert manual_brief.density(1) == (5, 8) and manual_brief.density(10) == (50, 80)
    assert manual_brief.density(0.1) == (2, 3)  # never asks for fewer than two
    text = manual_brief.brief(package(60.0))
    assert 'YOĞUNLUK HEDEFİ' in text and 'yaklaşık 5–8 öneri' in text
    assert 'zorunda değilsin' not in text


@pytest.mark.skipif(os.name == 'nt', reason='fake FFmpeg is a shell script')
def test_incompatible_ffmpeg_major_gets_a_fix_message(tmp_path):
    bad = fake_ffmpeg(tmp_path, '9.0.2-essentials_build-www.gyan.dev', 'ffmpeg9')
    good = fake_ffmpeg(tmp_path, '7.1.1-essentials_build-www.gyan.dev', 'ffmpeg7')
    assert 'FFmpeg 7.1.1' in tools.compat_warning(bad)
    assert tools.compat_warning(good) == ''
    assert tools.compat_warning(tmp_path / 'yok') == ''  # unknown tool: no false alarm
