"""One unreadable answer (Wikimedia 'invalid_response') used to switch that source off for the whole
Medyayı Tamamla job. It now takes several failures in a row, and the real cause is written to the diagnostics."""
from types import SimpleNamespace

from app.stock.director_media import MediaDirector
from app.stock.models import StockError


def make_director(answers):
    """answers: list of results or StockError for successive Wikimedia searches."""
    calls = []

    def cache_search(pid, name, kind, query, page=1):
        calls.append(query)
        answer = answers[len(calls) - 1]
        if isinstance(answer, StockError): raise answer
        return answer, {'raw_count': len(answer), 'normalized_count': len(answer), 'rejected': {}}, False
    service = SimpleNamespace(settings=SimpleNamespace(stock_config=lambda name: {}), _cache_search=cache_search,
                              _checkpoint=lambda *a, **k: None, closed=False)
    director = MediaDirector(service, {'project_id': 'p', 'progress': {}})
    director.topic = 'rome'
    return director, calls


def ask(director, query):
    log = {'searches': []}
    director.search({'slot_id': 's1', 'order': 1}, ['image'], query, log, provider_names=['wikimedia'])
    return log


def bad(category='invalid_response'):
    return StockError(category, 'x')


def test_one_unreadable_answer_does_not_switch_the_source_off():
    director, calls = make_director([bad(), []])
    ask(director, 'roman forum ruins')
    assert 'wikimedia' not in director.unavailable
    ask(director, 'colosseum arena')
    assert len(calls) == 2  # the source was asked again


def test_three_unreadable_answers_in_a_row_switch_it_off():
    director, calls = make_director([bad(), bad(), bad(), []])
    for query in ('roman forum ruins', 'colosseum arena', 'aqueduct bridge'):
        ask(director, query)
    assert director.unavailable == {'wikimedia': 'invalid_response'}


def test_a_good_answer_resets_the_count():
    director, calls = make_director([bad(), bad(), [], bad(), bad(), []])
    for query in ('roman forum ruins', 'colosseum arena', 'aqueduct bridge', 'gladiator helmet', 'senate house', 'marble statue'):
        ask(director, query)
    assert 'wikimedia' not in director.unavailable


def test_rate_limit_and_timeout_still_switch_the_source_off_at_once():
    for category in ('rate_limit', 'timeout', 'key_rejected'):
        director, calls = make_director([bad(category)])
        ask(director, 'roman forum ruins')
        assert director.unavailable == {'wikimedia': category}


def test_the_real_reason_of_an_unreadable_answer_is_a_short_safe_label():
    from app.stock.providers import response_reason
    import json
    assert response_reason(ValueError('api_error:internal_api_error_DBQueryTimeout')) == 'api_error:internal_api_error_DBQueryTimeout'
    assert response_reason(ValueError('answer_too_large')) == 'answer_too_large'
    assert response_reason(json.JSONDecodeError('x', 'y', 0)) == 'not_json'
    assert response_reason(ValueError('secret-key-123 leaked in a message')) == 'ValueError'
    assert response_reason(KeyError('mime')) == 'KeyError'


def test_unsafe_address_label_names_the_field_and_host_but_no_path_or_key():
    from app.stock.providers import unsafe_label
    assert unsafe_label('download_url', 'https://example.org/a/b.jpg?key=SECRET') == 'unsafe_url:download_url@example.org'
    assert unsafe_label('preview_url', 'http://upload.wikimedia.org/x.jpg') == 'unsafe_url:preview_url@scheme_http'
    assert unsafe_label('source_url', 'https://commons.wikimedia.org/' + 'a' * 2100) == 'unsafe_url:source_url@too_long'
    assert 'SECRET' not in unsafe_label('download_url', 'https://example.org/a?key=SECRET')
