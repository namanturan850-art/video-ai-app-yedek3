"""Hibrit montaj: yalnız grafik sahneler Remotion'da, gerisi FFmpeg; parçalar paralel."""
from copy import deepcopy
import json
import threading
import time
from pathlib import Path

import pytest

from app.integrations.openmontage import provider
from app.integrations.openmontage.bridge import PIN
from app.rendering import smart_edit, timeline
from app.rendering.models import RenderError, options
from app.rendering.parallel import run_parallel
from app.rendering.runner import ProcessRunner

SLOTS = 6


def film(tmp_path, graphic=()):
    """Six 2-second scenes with one slot each; `graphic` = indexes drawn with a panel layout."""
    h = {'ready': True, 'contract_version': 1, 'project_id': 'local', 'source_script_version_id': 's', 'scene_plan_id': 'p', 'audio_duration': 2.0 * SLOTS,
         'scenes': [], 'subtitles': [], 'stock_slots': []}
    p = {'source_script_version_id': 's', 'plan_id': 'p', 'scenes': []}
    source = tmp_path / 'source.mp4'; source.write_bytes(b'unchanged')
    for i in range(SLOTS):
        h['scenes'].append({'scene_id': f's{i}', 'start': 2.0 * i, 'end': 2.0 * i + 2})
        h['stock_slots'].append({'slot_id': str(i), 'scene_id': f's{i}', 'order': 1, 'start': 2.0 * i, 'end': 2.0 * i + 2, 'duration': 2.0, 'status': 'complete',
                                 'selected_media_local_identity': {'media_type': 'video'}})
        p['scenes'].append({'scene_id': f's{i}', 'transition': 'crossfade', 'motion': 'none', 'overlay_text': '', 'narration_text': 'Text.', 'importance': 50})
    t = timeline.build(h, p)
    media = {str(i): {'path': source, 'type': 'video', 'duration': 30, 'sha256': 'fixture'} for i in range(SLOTS)}
    edit = smart_edit.build(t, h, 'adaptive', 'source', media_details=media)
    for i in graphic:
        edit['slots'][i].update(layout='big_number', layout_window={'start': edit['slots'][i]['start'], 'end': edit['slots'][i]['end']}, texts=['1945'], number='1945')
    return h, t, edit, media


class Bridge:
    def __init__(self, tmp_path, fail=(), cancel=False):
        self.root_dir = tmp_path / 'external'; (self.root_dir / 'remotion-composer').mkdir(parents=True)
        self.props, self.calls, self.lock, self.fail, self.cancel, self.active, self.peak = [], [], threading.Lock(), set(fail), cancel, 0, 0
    def status(self, *a): return {'ready': True, 'commit': PIN[:7]}
    def root(self): return self.root_dir
    def settings_guard(self, v): pass
    def call(self, op, inputs, folder, runner=None, progress=None):
        with self.lock:
            self.calls.append((op, deepcopy(inputs))); self.active += 1; self.peak = max(self.peak, self.active)
        try:
            if op == 'trim': Path(inputs['output_path']).write_bytes(b'trim'); return {}
            props = json.loads(Path(inputs['edit_decisions']['bespoke']['props_path']).read_text())
            self.props.append(props); time.sleep(.15)
            if self.cancel: raise RenderError('render_cancelled', 'iptal')
            if any(c['slot_id'] in self.fail for c in props['clips']): raise RenderError('openmontage_failed', 'x')
            Path(inputs['output_path']).write_bytes(b'reel')
            return {}
        finally:
            with self.lock: self.active -= 1


class Pieces:
    def spawn(self): return Pieces()
    def cancel(self): pass


def delivery_capture(monkeypatch):
    seen = {}
    class Delivery:
        def __init__(self, *args): self.warnings = []
        def render(self, plan):
            seen['plan'] = plan; seen['warnings'] = list(self.warnings)
            return {'path': plan['temporary'] / 'output.mp4', 'metadata': {'render_timing': {'slot_seconds': 1.0, 'parallel_pieces': 3, 'final_seconds': 1.0}, 'warnings': []}}
    monkeypatch.setattr(provider, 'FFmpegRenderProvider', Delivery)
    return seen


def run(tmp_path, monkeypatch, graphic, bridge=None, runner=None, workers='1'):
    monkeypatch.setenv('AVS_REMOTION_WORKERS', workers)
    h, t, edit, media = film(tmp_path, graphic)
    job = tmp_path / 'job'; job.mkdir(exist_ok=True); seen = delivery_capture(monkeypatch)
    bridge = bridge or Bridge(tmp_path)
    plan = {'temporary': job, 'handoff': h, 'timeline': t, 'smart_edit_plan': edit, 'options': options({'montage_engine': 'openmontage', 'subtitle_display': 'none'}),
            'media': media, 'audio': tmp_path / 'voice.wav', 'music': None}
    result = provider.OpenMontageProvider(bridge, {}, runner).render(plan)
    return result, seen, bridge, edit, media


def test_no_graphic_slots_means_no_remotion_at_all(tmp_path, monkeypatch):
    result, seen, bridge, edit, media = run(tmp_path, monkeypatch, [])
    assert bridge.calls == [] and seen['plan']['media'] == media
    assert [s['layout'] for s in seen['plan']['smart_edit_plan']['slots']] == [s.get('layout', 'full_broll') for s in edit['slots']]
    assert result['metadata']['render_timing']['engine'] == 'ffmpeg' and result['metadata']['render_timing']['graphic_slots'] == 0


def test_only_graphic_slots_go_to_remotion_without_trimming_the_broll(tmp_path, monkeypatch):
    result, seen, bridge, edit, media = run(tmp_path, monkeypatch, [1, 4])
    assert [c[0] for c in bridge.calls] == ['compose']  # one chunk, no trim of any stock clip
    props = bridge.props[0]
    assert [c['slot_id'] for c in props['clips']] == ['1', '4'] and props['subtitle_display'] == 'none' and props['emphasis'] == [] and props['subtitles'] == []
    first, second = props['clips']
    assert first['start_frame'] == 0 and first['end_frame'] == 60 and second['start_frame'] == 60 + first['handle'] and props['frames'] == second['end_frame'] + second['handle']
    assert all(c['transition_duration'] == 0 and c['source_in'] == edit['slots'][int(c['slot_id'])]['source_in'] for c in props['clips'])  # no ramps; the source is cut by seeking
    sent = seen['plan']; slots = sent['smart_edit_plan']['slots']
    assert [s['layout'] for s in slots] == ['full_broll'] * SLOTS  # the panel is baked into the reel
    reel = {sid: m for sid, m in sent['media'].items() if m['sha256'] == 'graphics-reel'}
    assert set(reel) == {'1', '4'} and all(m['path'].name == 'graphics.mp4' for m in reel.values())
    assert sent['media']['0'] == media['0'] and sent['media']['5'] == media['5']  # B-roll straight from its source
    offsets = [slots[1]['source_in'], slots[4]['source_in']]
    assert offsets[0] == 0 and offsets[1] > 1.9  # back to back in the reel (2 s + crossfade handle)
    for i in (1, 4):
        assert slots[i]['segments'][0]['motion_effect'] == 'none' and len(slots[i]['segments']) == 1  # no second camera move
    t = result['metadata']['render_timing']
    assert t['engine'] == 'hybrid' and t['graphic_slots'] == 2 and t['broll_slots'] == SLOTS - 2 and t['remotion_chunks'] == 1
    assert result['metadata']['smart_edit_applied_summary'] == edit['summary'] and result['metadata']['montage_engine'] == 'openmontage'
    assert media['1']['path'].read_bytes() == b'unchanged'
    assert not list((tmp_path / 'external/remotion-composer/projects').iterdir())


def test_chunks_are_rendered_in_parallel_and_cover_every_graphic_slot_once(tmp_path, monkeypatch):
    bridge = Bridge(tmp_path)
    result, seen, bridge, edit, media = run(tmp_path, monkeypatch, [0, 1, 3, 5], bridge=bridge, runner=Pieces(), workers='2')
    assert [c[0] for c in bridge.calls] == ['compose', 'compose'] and bridge.peak == 2
    reels = {sid: m['path'] for sid, m in seen['plan']['media'].items() if m['sha256'] == 'graphics-reel'}
    assert set(reels) == {'0', '1', '3', '5'} and len(set(reels.values())) == 2  # two reels
    assert result['metadata']['render_timing']['remotion_chunks'] == 2


def test_a_failed_chunk_falls_back_to_ffmpeg_layouts_for_those_slots_only(tmp_path, monkeypatch):
    result, seen, bridge, edit, media = run(tmp_path, monkeypatch, [0, 4], bridge=Bridge(tmp_path, fail={'0'}), runner=Pieces(), workers='2')
    slots = seen['plan']['smart_edit_plan']['slots']
    assert slots[0]['layout'] == 'big_number' and seen['plan']['media']['0'] == media['0']  # FFmpeg draws this one itself
    assert slots[4]['layout'] == 'full_broll' and seen['plan']['media']['4']['sha256'] == 'graphics-reel'
    assert any('Remotion' in w for w in seen['warnings']) and result['metadata']['render_timing']['graphic_slots_in_remotion'] == 1


def test_cancel_is_never_swallowed_by_the_fallback(tmp_path, monkeypatch):
    with pytest.raises(RenderError) as error:
        run(tmp_path, monkeypatch, [1], bridge=Bridge(tmp_path, cancel=True))
    assert error.value.category == 'render_cancelled'


def test_scope_all_keeps_the_old_whole_film_path_for_comparison(tmp_path, monkeypatch):
    monkeypatch.setenv('AVS_REMOTION_SCOPE', 'all')
    result, seen, bridge, edit, media = run(tmp_path, monkeypatch, [1])
    assert [c[0] for c in bridge.calls] == ['trim'] * SLOTS + ['compose']
    assert result['metadata']['render_timing']['engine'] == 'remotion_all'


def test_run_parallel_overlaps_pieces_and_reports_the_first_failure():
    active, peak, gate = [0], [0], threading.Lock()
    def job(i, runner):
        with gate: active[0] += 1; peak[0] = max(peak[0], active[0])
        time.sleep(.1)
        with gate: active[0] -= 1
        return i
    assert run_parallel(6, job, 3, Pieces()) == list(range(6)) and peak[0] == 3
    assert run_parallel(3, job, 3, None) == [0, 1, 2]  # a runner without spawn(): one after another
    cancelled = []
    class Tracking(Pieces):
        def spawn(self): piece = Tracking(); piece.cancel = lambda: cancelled.append(1); return piece
    def failing(i, runner):
        if i == 1: raise RenderError('render_failed', 'boom')
        time.sleep(.3); return i
    with pytest.raises(RenderError) as error: run_parallel(4, failing, 4, Tracking())
    assert error.value.category == 'render_failed' and cancelled


def test_spawned_runner_is_cancelled_with_its_parent_and_has_its_own_stderr(tmp_path):
    parent = ProcessRunner(); child = parent.spawn()
    assert child.commands is parent.commands and not child.cancelled()
    parent.cancel()
    assert child.cancelled()
    with pytest.raises(RenderError) as error: child.run(['ffmpeg', '-version'], tmp_path)
    assert error.value.category == 'render_cancelled'
