"""Missing slots get actual provider requests before already-filled rechecks."""
from types import SimpleNamespace

from app.stock.director_media import MediaDirector, prioritized_targets


def target(order, reason):
    return ({'order': order, 'slot_id': f's{order}', 'estimated_start': order * 4}, reason)


def test_missing_and_retry_slots_precede_rechecks_without_reordering_each_tier():
    targets = [target(1, 'unreviewed'), target(2, 'missing'), target(3, 'motion_planned'),
               target(4, 'reselect'), target(5, 'retry_card'), target(6, 'motion_owner'),
               target(7, 'opening'), target(8, 'missing'), target(9, 'setting')]
    assert [slot['order'] for slot, _ in prioritized_targets(targets)] == [3, 6, 2, 5, 8, 1, 4, 7, 9]
    assert [slot['order'] for slot, _ in targets] == list(range(1, 10))


def make_director():
    calls = []
    def cache_search(pid, provider, kind, query, page=1):
        calls.append((provider, kind, query))
        return [], {'raw_count': 0}, False
    service = SimpleNamespace(_cache_search=cache_search, _checkpoint=lambda *a, **k: None,
                              settings=SimpleNamespace(stock_config=lambda provider: {}))
    director = MediaDirector(service, {'project_id': 'p', 'progress': {}})
    director.language = 'en'
    return director, calls


def test_late_missing_slot_gets_last_budget_request_before_early_filled_slots(monkeypatch):
    from app.stock import search_evidence
    monkeypatch.setattr(search_evidence, 'JOB_REQUESTS', 1)
    director, calls = make_director()
    # These represent the target reasons gathered by run() from a partially-filled project.
    targets = [target(1, 'unreviewed'), target(2, 'reselect'), target(249, 'missing')]
    logs = {}
    for slot, reason in prioritized_targets(targets):
        log = logs[reason] = {'searches': []}
        director.search(slot, ['image'], f'water landscape {reason}', log, provider_names=['pixabay'])
    assert len(calls) == 1
    assert logs['missing']['searches'][0].get('skipped') is None
    assert 'missing' in calls[0][2]
    assert all(logs[reason]['searches'][0]['skipped'] == 'budget' for reason in ('unreviewed', 'reselect'))


def test_exhausted_budget_has_one_summary_and_never_records_false_failure(monkeypatch):
    from app.stock import search_evidence
    monkeypatch.setattr(search_evidence, 'JOB_REQUESTS', 0)
    director, calls = make_director()
    slot, _ = target(249, 'missing')
    log = {'searches': []}
    for query in ('ocean waves', 'forest trees', 'river water'):
        assert director.search(slot, ['image', 'video'], query, log, provider_names=['pixabay', 'wikimedia']) == []
    assert not calls
    assert len(log['searches']) == 1
    assert log['searches'][0]['skipped'] == 'budget' and log['searches'][0]['count'] == 12
    assert 'search_budget_reached' in search_evidence.reasons(log)
    search_evidence.remember(slot, log, 'context', '2026-10-22T00:00:00+00:00')
    assert slot['search_attempts'] == []
    assert director.progress['search_metrics']['unique_requests'] == 0


def test_existing_query_can_be_shared_with_missing_slot_after_global_budget_fills(monkeypatch):
    from app.stock import search_evidence
    monkeypatch.setattr(search_evidence, 'JOB_REQUESTS', 1)
    director, calls = make_director()
    for order in (1, 249):
        slot, _ = target(order, 'missing')
        log = {'searches': []}
        director.search(slot, ['image'], 'ocean waves', log, provider_names=['pixabay'])
        assert all(not s.get('skipped') for s in log['searches'])
    assert len(calls) == 1  # second slot still receives the shared cached answer
    assert director.progress['search_metrics']['cache_hits'] == 1


def test_slot_limit_keeps_previously_authorized_queries_and_summarizes_new_ones(monkeypatch):
    from app.stock import search_evidence
    monkeypatch.setattr(search_evidence, 'SLOT_REQUESTS', 1)
    director, calls = make_director()
    slot, _ = target(249, 'missing')
    log = {'searches': []}
    for query in ('ocean waves', 'river water', 'forest trees', 'ocean waves'):
        director.search(slot, ['image'], query, log, provider_names=['pixabay'])
    assert len(calls) == 1
    summaries = [s for s in log['searches'] if s.get('skipped') == 'budget']
    assert len(summaries) == 1 and summaries[0]['count'] == 2
    assert director.progress['search_metrics']['cache_hits'] == 1


def test_budget_summary_does_not_hide_remaining_allowed_combinations(monkeypatch):
    from app.stock import search_evidence
    monkeypatch.setattr(search_evidence, 'JOB_REQUESTS', 1)
    director, calls = make_director()
    slot, _ = target(249, 'missing')
    log = {'searches': []}
    director.search(slot, ['image'], 'ocean waves', log, provider_names=['pixabay', 'wikimedia'])
    assert [call[0] for call in calls] == ['pixabay']
    assert sum(s.get('skipped') == 'budget' for s in log['searches']) == 1
    assert any(s.get('provider') == 'pixabay' and s.get('results') == 0 for s in log['searches'])
