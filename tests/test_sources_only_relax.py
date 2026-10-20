"""Manuel Kurgu (sources_only) had no way to get more automatic matches: a slot the
period/geography rule emptied went straight to 'manual medya atayın', even though the
exact same "try again with looser rules" mechanism already existed for motion-graphic
slots (MediaDirector.relaxed/relax_pass). fill() now offers that same free, local-only
retry to a slot that is about to end with nothing, before giving up to the owner.
No network, no AI: MediaDirector built directly, every provider call stubbed."""
from types import SimpleNamespace

from app.stock.director_media import MediaDirector


def make_director():
    director = MediaDirector(SimpleNamespace(), {'project_id': 'test', 'progress': {}})
    director.memo, director.card_texts, director.sources_only = {}, set(), True
    return director


def make_slot_and_scene():
    slot = {'slot_id': 's1', 'scene_id': 'sc1', 'order': 1, 'estimated_start': 0.0, 'estimated_end': 4.0,
            'duration': 4.0, 'search_query': 'maracaibo bridge', 'fallback_queries': [], 'preferred_type': 'stock_video'}
    scene = {'scene_id': 'sc1', '_shot_bound': True, 'narration_text': 'Si buscas Maracaibo en una postal.',
              'scene_context': 'Si buscas Maracaibo en una postal.', 'primary_stock_query': 'maracaibo bridge',
              'alternative_stock_queries': [], 'visual_subject': {'queries': []}}
    return slot, scene


def stub_dead_ends(director, *, reject_as_setting_conflict, relaxed_outcome):
    """Every normal stock step finds nothing; a plain miss vs. a period/place rule
    miss is the only difference the new code is supposed to act on."""
    director.try_local_archive = lambda *a, **k: None
    director.extended_search = lambda *a, **k: None
    director.rewrite = lambda *a, **k: []
    director.merge = lambda *a, **k: False

    def fake_try_step(slot, scene, stage, kinds, queries, log, exclude):
        if stage == 'relaxed':
            return relaxed_outcome
        if reject_as_setting_conflict:
            log.setdefault('rejected', {})
            log['rejected']['setting_conflict'] = log['rejected'].get('setting_conflict', 0) + 1
        return None
    director.try_step = fake_try_step


def test_setting_blocked_slot_gets_a_relaxed_retry_before_giving_up():
    director = make_director()
    stub_dead_ends(director, reject_as_setting_conflict=True, relaxed_outcome='chosen')
    slot, scene = make_slot_and_scene()
    director.unresolved = lambda *a, **k: (_ for _ in ()).throw(AssertionError('manuel medya istenmemeli: gevşetilmiş arama bir sonuç buldu'))
    director.fill(slot, scene)
    assert slot.get('setting_relaxed') == 1
    assert 'gevşetildi' in slot.get('message', '')


def test_relaxed_retry_still_empty_falls_back_to_manual_as_before():
    director = make_director()
    stub_dead_ends(director, reject_as_setting_conflict=True, relaxed_outcome=None)
    slot, scene = make_slot_and_scene()
    director.fill(slot, scene)
    assert slot['status'] == 'ai_needed'
    assert slot['selected_media'] is None
    assert 'manuel medya atayın' in slot['message']


def test_a_plain_miss_without_a_setting_conflict_never_tries_relaxed_rules():
    director = make_director()
    stub_dead_ends(director, reject_as_setting_conflict=False, relaxed_outcome='chosen')
    slot, scene = make_slot_and_scene()
    director.fill(slot, scene)
    assert slot['status'] == 'ai_needed'  # relaxed() was offered 'chosen' but never asked, since nothing points to a setting conflict
    assert not slot.get('setting_relaxed')
