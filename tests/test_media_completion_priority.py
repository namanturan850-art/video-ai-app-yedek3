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
