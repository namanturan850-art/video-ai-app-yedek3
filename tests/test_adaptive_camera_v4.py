"""Adaptive edit v4: sub-pixel camera, topic rhythm, punch-in splits, card-safe transitions."""
import shutil
import subprocess

import pytest

from app.rendering import smart_edit, timeline
from test_smart_edit import owner_shape, handoffs


def plan_for(mood=None, h_p=None, seed='1'):
    h, p = h_p or owner_shape()
    if mood:
        for scene in p['scenes']: scene['mood'] = mood
    return smart_edit.build(timeline.build(h, p), h, 'adaptive', 's', seed=seed), h, p


@pytest.mark.parametrize('mood,profile', [('geheimnisvoll', 'calm'), ('gizemli ve sakin', 'calm'), ('mysterious', 'calm'),
                                          ('spannend', 'energetic'), ('heyecanlı', 'energetic'), ('dramatic', 'energetic'),
                                          ('neutral', 'balanced'), (None, 'balanced')])
def test_project_rhythm_comes_from_scene_moods_in_five_languages(mood, profile):
    plan, _, _ = plan_for(mood)
    assert plan['edit_profile'] == profile and plan['edit_profile_label']


def test_every_full_broll_shot_moves_and_neighbours_differ():
    plan, _, _ = plan_for()
    broll = [s for s in plan['slots'] if s['layout'] == 'full_broll']
    assert broll and all(seg['motion_effect'] != 'none' for s in broll for seg in s['segments'])
    assert all(seg['camera_curve'] == 'eased' for s in plan['slots'] for seg in s['segments'])
    firsts = [s['segments'][0]['motion_effect'] for s in plan['slots']]
    repeats = sum(a == b for a, b in zip(firsts, firsts[1:]))
    assert repeats <= len(firsts) // 3


def test_video_moves_less_than_stills_and_profiles_scale_strength():
    calm, _, _ = plan_for('ruhig'); energetic, _, _ = plan_for('spannend')
    strength = lambda plan: max(seg['motion_strength'] for s in plan['slots'] for seg in s['segments'])
    assert strength(calm) < strength(energetic) <= .07
    assert smart_edit.PROFILES['calm']['video'] < smart_edit.PROFILES['calm']['image']


def test_long_shot_is_split_by_clear_punch_in_not_tiny_jump():
    h, p = handoffs(14); h['subtitles'] = []  # plain B-roll, no card
    plan, _, _ = plan_for(h_p=(h, p))
    assert plan['slots'][0]['layout'] == 'full_broll'
    segments = plan['slots'][0]['segments']
    assert len(segments) >= 2 and segments[0]['base_zoom'] == 0 and segments[1]['base_zoom'] >= .1
    assert segments[-1]['end_frame'] == plan['slots'][0]['segments'][-1]['end_frame']
    assert sum(s['frames'] for s in segments) == round(14 * 30)


def test_transitions_never_overlap_card_text():
    for seed in map(str, range(10)):
        plan, h, p = plan_for(seed=seed)
        for previous, current in zip(plan['slots'], plan['slots'][1:]):
            seconds = previous['transition_duration']
            if not seconds: continue
            for item, edge in ((previous, 'end'), (current, 'start')):
                window = item.get('layout_window')
                if not window: continue
                if edge == 'end': assert window['end'] <= item['end'] - seconds
                else: assert window['start'] >= item['start'] + seconds


def test_master_clock_unchanged_by_adaptive_v4():
    h, p = owner_shape(); t = timeline.build(h, p)
    plan = smart_edit.build(t, h, 'adaptive', 's', seed='7')
    assert [(s['start'], s['end']) for s in t['slots']] == [(s['start'], s['end']) for s in plan['slots']]
    for slot, item in zip(t['slots'], plan['slots']):
        assert sum(seg['frames'] for seg in item['segments']) == slot['frames']


def _centroids(vf, ffmpeg, image, frames=90):
    import numpy as np
    raw = subprocess.run([ffmpeg, '-v', 'error', '-loop', '1', '-framerate', '30', '-t', str(frames / 30), '-i', str(image),
                          '-vf', vf + ',format=gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    out = []
    for f in np.frombuffer(raw, np.uint8).reshape(-1, 1080, 1920).astype(float):
        w = np.clip(f - 40, 0, None); ys, xs = np.indices(f.shape); s = w.sum(); out.append(((w * xs).sum() / s, (w * ys).sum() / s))
    return np.array(out)


@pytest.mark.parametrize('effect', ['push_in', 'pan_right', 'push_out'])
def test_real_camera_is_subpixel_smooth(tmp_path, effect):
    np = pytest.importorskip('numpy')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg: pytest.skip('Optional FFmpeg absent')
    if 'perspective' not in subprocess.run([ffmpeg, '-hide_banner', '-filters'], capture_output=True, text=True).stdout:
        pytest.skip('FFmpeg build without perspective filter')
    image = tmp_path / 'dot.png'
    subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=1920x1080', '-vf',
                    'drawbox=x=1500:y=250:w=9:h=9:color=white:t=fill', '-frames:v', '1', str(image)], check=True)
    segment = {'frames': 90, 'motion_effect': effect, 'motion_strength': .05, 'camera_curve': 'eased'}
    c = _centroids('scale=1920:1080' + smart_edit.camera(segment, length=90), ffmpeg, image)
    velocity = np.diff(c, axis=0); accel = np.diff(velocity, axis=0)
    assert np.hypot(*(c[-1] - c[0])) > 5          # it really moves
    assert np.sqrt((accel ** 2).mean()) < .3      # no whole-pixel stepping (zoompan measured ~0.76)
    assert np.abs(velocity[:, 0]).max() < 3       # gentle: no jumps
