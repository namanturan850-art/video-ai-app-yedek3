"""Part 9.9 recovery: shared gaps, continuous-take coverage, multi-round search in one click."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.rendering import reflow, timeline, smart_edit, files
from app.stock import recovery
from test_stock_media import media
from test_rendering import ready, synthetic


def fixture(tmp_path, layout, source_seconds=22):
    """layout: list of (scene_id, seconds, has_media)."""
    root = tmp_path / 'project'; (root / 'stock').mkdir(parents=True, exist_ok=True)
    scenes = []; slots = []; raws = []; cursor = 0.; assets = {}; meta = []; order = {}
    for i, (scene_id, seconds, has_media) in enumerate(layout):
        start, end = cursor, cursor + seconds; cursor = end
        if not scenes or scenes[-1]['scene_id'] != scene_id:
            scenes.append({'scene_id': scene_id, 'start': start, 'end': end})
            meta.append({'scene_id': scene_id, 'narration_text': 'Ships cross the stormy ocean.', 'primary_stock_query': 'ship ocean storm',
                         'visual_intent': 'ship ocean storm', 'transition': 'crossfade', 'motion': 'none', 'importance': 50, 'mood': 'mysterious'})
        else: scenes[-1]['end'] = end
        order[scene_id] = order.get(scene_id, 0) + 1
        m = None
        if has_media:
            data = f'clip-{i}'.encode(); name = uuid4().hex + '.mp4'; (root / 'stock' / name).write_bytes(data)
            m = {**media(str(i), description='ship ocean storm', duration=source_seconds), 'local_path': 'stock/' + name,
                 'file_size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'content_type': 'video/mp4'}
            assets[str(i)] = {'path': root / 'stock' / name, 'type': 'video', 'duration': source_seconds, 'width': 1920, 'height': 1080, 'sha256': m['sha256']}
        s = {'slot_id': str(i), 'scene_id': scene_id, 'order': order[scene_id], 'start': start, 'end': end, 'duration': seconds,
             'status': 'complete' if m else 'pending', 'locked': False,
             'selected_media_local_identity': {k: m[k] for k in ('provider', 'media_id', 'media_type', 'local_path')} if m else None}
        slots.append(s)
        raws.append({**s, 'selected_media': m, 'local_validation': {'sha256': m['sha256'], 'media_type': 'video', 'duration': source_seconds,
                                                                     'width': 1920, 'height': 1080} if m else {}})
    h = {'project_id': 'pid', 'contract_version': 1, 'ready': False, 'source_script_version_id': 's', 'scene_plan_id': 'p',
         'audio_duration': cursor, 'scenes': scenes, 'stock_slots': slots, 'subtitles': []}
    p = {'source_script_version_id': 's', 'plan_id': 'p', 'scenes': meta}
    return h, p, {'slots': raws}, SimpleNamespace(_path=lambda pid: root), assets


def test_whole_empty_short_scene_is_covered_by_one_continuous_take(tmp_path):
    # The owner's case: a short scene with no relevant unique media (2.8 s).
    h, p, state, projects, assets = fixture(tmp_path, [('a', 4, True), ('a', 4, True), ('b', 2.8, False), ('c', 4, True), ('c', 4, True)])
    before = deepcopy((h, p, state))
    effective, report = reflow.build(h, p, state, projects, files.sha256)
    assert report['render_ready'] and report['effective_uncovered_duration'] == 0
    assert report['continued_seconds'] == pytest.approx(2.8)
    gap = next(s for s in effective['stock_slots'] if s['slot_id'] == '2')
    assert gap['continuation_of'] == '1' and gap['selected_media_local_identity'] == effective['stock_slots'][1]['selected_media_local_identity']
    t = timeline.build(effective, p)
    assert t['duration'] == pytest.approx(18.8) and sum(s['frames'] for s in t['slots']) == round(18.8 * 30)
    details = {**assets, '2': assets['1']}
    plan = smart_edit.build(t, effective, 'adaptive', 'src', media_details=details, seed='1')
    first, cont = plan['slots'][1], plan['slots'][2]
    # Same take continues where it stopped: no second, different cut of the clip.
    assert cont['source_in'] == pytest.approx(first['source_out'], abs=1e-5)
    assert cont['source_out'] <= 22 and first['transition_out'] == 'hard_cut' and cont['transition_in'] == 'hard_cut'
    assert all(seg['base_zoom'] >= .12 for seg in cont['segments']) and cont['continuation_of'] == '1'
    assert (h, p, state) == before


def test_locked_or_too_long_gap_is_never_continued(tmp_path):
    h, p, state, projects, _ = fixture(tmp_path, [('a', 4, True), ('b', 7, False), ('c', 4, True)])
    _, report = reflow.build(h, p, state, projects, files.sha256)
    assert not report['render_ready'] and report['effective_uncovered_duration'] == pytest.approx(7)
    h, p, state, projects, _ = fixture(tmp_path / 'locked', [('a', 4, True), ('b', 2, False), ('c', 4, True)])
    for i in (0, 2): h['stock_slots'][i]['locked'] = state['slots'][i]['locked'] = True
    _, report = reflow.build(h, p, state, projects, files.sha256)
    assert not report['render_ready']


def test_continuation_never_exceeds_the_real_source(tmp_path):
    h, p, state, projects, _ = fixture(tmp_path, [('a', 4, True), ('b', 2.8, False), ('c', 4, True)], source_seconds=5)
    _, report = reflow.build(h, p, state, projects, files.sha256)
    assert not report['render_ready'] and report['continued_seconds'] == 0


def test_gap_too_big_for_one_neighbour_is_shared_by_both(tmp_path):
    h, p, state, projects, _ = fixture(tmp_path, [('a', 8, True), ('a', 3, False), ('a', 8, True)])
    effective, report = reflow.build(h, p, state, projects, files.sha256)
    assert report['render_ready'] and report['continued_seconds'] == 0 and report['effective_render_segments'] == 2
    left, right = effective['stock_slots']
    assert left['duration'] <= reflow.VIDEO_MERGE_MAX + 1e-6 and right['duration'] <= reflow.VIDEO_MERGE_MAX + 1e-6
    assert left['end'] == pytest.approx(right['start']) and left['duration'] + right['duration'] == pytest.approx(19)
    timeline.build(effective, p)


def test_one_click_keeps_searching_while_it_makes_progress(ready, monkeypatch):
    c = ready['client']; service = c.app.state.stock; pid = ready['pid']
    from app.stock.service import fingerprint
    folder = ready['root'] / 'stock'
    clip = synthetic(folder, uuid4().hex + '.mp4', ['-f', 'lavfi', '-i', 'color=c=red:s=1920x1080:r=30:d=12', '-c:v', 'libx264'])
    digest = files.sha256(clip)
    found = {**media('fresh', description='new', duration=12), 'local_path': 'stock/' + clip.name, 'file_size': clip.stat().st_size, 'sha256': digest}
    with closing(service.projects._connection()) as db, db:
        state = json.loads(db.execute('SELECT state_json FROM stock_plans WHERE project_id=?', (pid,)).fetchone()[0])
        state.update(handoff_fingerprint=fingerprint(service.production.handoff(pid)), bindings={}, warnings=[])
        for slot in state['slots']:
            existing = slot['selected_media']
            slot['selected_media'] = {**media(existing['media_id'], media_type=existing['media_type'],
                width=320 if existing['media_type'] == 'video' else 240, height=240 if existing['media_type'] == 'video' else 320), **existing}
        target = state['slots'][0]['slot_id']
        state['slots'][0].update(selected_media=None, status='pending', locked=False)
        db.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?', (json.dumps(state), pid))
    calls = []
    def search(service_, pid_, slot, used, progress, job):
        calls.append(slot['slot_id'])
        if calls.count(slot['slot_id']) == 1:
            # First pass stops at the per-slot search limit with nothing found.
            progress['recovery_calls'] = progress.get('recovery_calls', 0) + recovery.SLOT_CALLS
            slot['missing_reasons'] = ['search_budget_reached']; return [], []
        return [found], []
    monkeypatch.setattr(recovery, 'search', search)
    monkeypatch.setattr(recovery.relevance, 'choose', lambda candidates, used, slot: candidates[0] if candidates else None)
    service.downloader.download = lambda pid_, m: m
    state = service.view(pid)
    job = service.start(pid, {'plan_id': state['plan_id'], 'revision': state['revision'], 'action': 'smart_recovery'})
    service.futures[job['job_id']].result(timeout=60)
    result = service.view(pid)
    assert result['job']['status'] == 'completed', result['job']
    assert calls.count(target) == 2  # one click, second round
    assert next(s for s in result['slots'] if s['slot_id'] == target)['selected_media']['media_id'] == 'fresh'


def test_real_render_of_continuous_take_keeps_exact_duration(tmp_path):
    from app.rendering import tools, probe
    from app.rendering.engine import FFmpegRenderProvider
    from app.rendering.models import options
    from app.rendering.runner import ProcessRunner
    from test_subtitles import wav
    h, p, state, projects, assets = fixture(tmp_path, [('a', 3, True), ('b', 2.5, False), ('c', 3, True)])
    for i, raw in enumerate(state['slots']):
        if not raw['selected_media']: continue
        clip = synthetic(tmp_path / 'project' / 'stock', uuid4().hex + '.mp4', ['-f', 'lavfi', '-i', ('testsrc2' if i == 0 else 'smptehdbars') + '=s=1920x1080:r=30:d=22', '-c:v', 'libx264', '-preset', 'ultrafast'])
        sha = files.sha256(clip); raw['selected_media'].update(local_path='stock/' + clip.name, sha256=sha, file_size=clip.stat().st_size); raw['local_validation']['sha256'] = sha
        h['stock_slots'][i]['selected_media_local_identity']['local_path'] = 'stock/' + clip.name
        assets[str(i)].update(path=clip, sha256=sha)
    effective, report = reflow.build(h, p, state, projects, files.sha256)
    assert report['render_ready'] and report['continued_seconds'] == pytest.approx(2.5)
    t = timeline.build(effective, p); details = {**assets, '1': assets['0']}
    plan = smart_edit.build(t, effective, 'adaptive', 'src', media_details=details, subtitle_mode='none')
    voice = tmp_path / 'voice.wav'; voice.write_bytes(wav(8.5)); job = tmp_path / 'job'; job.mkdir()
    result = FFmpegRenderProvider(tools.discover(), ProcessRunner()).render({'temporary': job, 'timeline': t, 'handoff': effective, 'smart_edit_plan': plan,
        'options': options({'encoder': 'cpu', 'subtitle_display': 'none'}), 'media': {k: v for k, v in details.items()}, 'audio': voice, 'music': None})
    assert abs(result['metadata']['duration'] - 8.5) <= .04 and result['metadata']['width'] == 1920
