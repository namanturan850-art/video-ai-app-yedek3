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


# ---- a dead-end relaxed retry is remembered, so the next "Medya Tamamla" press does not repeat it ----
def counting_dead_end(director, *, provider_error=None):
    calls = []
    director.try_local_archive = lambda *a, **k: None
    director.extended_search = lambda *a, **k: None
    director.rewrite = lambda *a, **k: []
    director.merge = lambda *a, **k: False

    def fake_try_step(slot, scene, stage, kinds, queries, log, exclude):
        if stage == 'relaxed':
            calls.append(director.relax)
            if provider_error:
                log['searches'].append({'provider': 'pexels', 'media_type': 'video', 'query': 'q', 'page': 1, 'error': provider_error})
            return None
        log.setdefault('rejected', {})['setting_conflict'] = 1
        return None
    director.try_step = fake_try_step
    return calls


def test_relaxed_dead_end_is_not_repeated_on_the_next_press():
    director = make_director()
    calls = counting_dead_end(director)
    slot, scene = make_slot_and_scene()
    director.fill(slot, scene)
    assert calls == [1, 2] and slot['relaxed_failed']['context']
    director.fill(slot, scene)  # second press, nothing changed
    assert calls == [1, 2]
    assert slot['status'] == 'ai_needed' and director.progress['relaxed_skipped'] == 1


def test_relaxed_dead_end_caused_by_a_provider_error_is_retried():
    director = make_director()
    calls = counting_dead_end(director, provider_error='timeout')
    slot, scene = make_slot_and_scene()
    director.fill(slot, scene)
    assert 'relaxed_failed' not in slot
    director.fill(slot, scene)
    assert calls == [1, 2, 1, 2]


def test_relaxed_dead_end_is_retried_when_the_sentence_changes_or_the_memory_is_old():
    from datetime import datetime, timedelta, timezone
    director = make_director()
    calls = counting_dead_end(director)
    slot, scene = make_slot_and_scene()
    director.fill(slot, scene)
    scene['narration_text'] = 'Maracaibo köprüsü gece ışıklarıyla görünüyor.'  # a different sentence: a different question
    director.fill(slot, scene)
    assert calls == [1, 2, 1, 2]
    slot['relaxed_failed']['at'] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    director.fill(slot, scene)
    assert calls == [1, 2, 1, 2, 1, 2]


def test_relaxed_dead_end_is_retried_once_the_picture_judge_starts_working():
    director = make_director()
    calls = counting_dead_end(director)
    slot, scene = make_slot_and_scene()
    director.fill(slot, scene)
    director.clip = SimpleNamespace(ready=lambda: True)  # CLIP fixed since the last press
    director.fill(slot, scene)
    assert calls == [1, 2, 1, 2]
