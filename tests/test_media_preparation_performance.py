"""Offline regressions: no live API, model downloads or production projects."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event, Lock
from types import SimpleNamespace
import hashlib
import time

import httpx
import pytest

from app.stock.search_session import SearchSession, ProviderGate, canonical_query
from app.stock.models import StockError, make_slots
from app.scripts.query_clean import english_query, scope_query
from app.stock.setting import infer, for_scene


def test_search_session_singleflight_and_mutation_isolation():
    session, entered, release = SearchSession(), Event(), Event()
    calls = []
    def operation():
        calls.append(1); entered.set(); assert release.wait(3)
        return [{'description': 'original'}], {}, False
    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(session.call, ('pixabay', 'video', 'ocean', 1), operation)
        assert entered.wait(3)
        b = pool.submit(session.call, ('pixabay', 'video', 'ocean', 1), operation)
        deadline = time.monotonic() + 3
        while session.shared != 1 and time.monotonic() < deadline: time.sleep(.001)
        release.set()
        first, second = a.result(3), b.result(3)
    first[0][0]['description'] = 'changed'
    assert calls == [1] and second[0][0]['description'] == 'original'
    assert session.call(('pixabay', 'video', 'ocean', 1), operation)[2]


def test_normalization_does_not_merge_different_meanings_or_pages():
    assert canonical_query('  Ocean   SHIP ', 'pixabay') == 'ocean ship'
    assert canonical_query('Mexico city', 'pixabay') != canonical_query('New Mexico city', 'pixabay')
    session, calls = SearchSession(), []
    for key in [('pixabay', 'video', 1), ('pixabay', 'image', 1), ('pixabay', 'video', 2), ('wikimedia', 'video', 1)]:
        session.call(key, lambda: calls.append(1) or [])
    assert len(calls) == 4


def test_cache_ttl_eviction_and_failure_recovery(monkeypatch):
    import app.stock.search_session as module
    now = [0.]; monkeypatch.setattr(module, 'monotonic', lambda: now[0])
    session = SearchSession(limit=2, ttl=10)
    session.call('a', lambda: [1]); session.call('b', lambda: [2]); session.call('c', lambda: [3])
    assert len(session.entries) == 2 and 'a' not in session.entries
    now[0] = 11
    assert session.call('b', lambda: [4]) == [4]
    with pytest.raises(StockError):
        session.call('fail', lambda: (_ for _ in ()).throw(StockError('timeout', 'Bekleyin')))
    assert session.call('fail', lambda: [5]) == [5]


def test_provider_cooldown_and_independent_sources(monkeypatch):
    import app.stock.search_session as module
    now = [0.]; monkeypatch.setattr(module, 'monotonic', lambda: now[0])
    gate, calls = ProviderGate(), []
    def limited():
        calls.append(1); raise StockError('rate_limit', 'Bekleyin')
    for _ in range(3):
        with pytest.raises(StockError): gate.call('pixabay', limited)
    assert calls == [1]
    assert gate.call('wikimedia', lambda: 'ok') == 'ok'
    now[0] = 61
    assert gate.call('pixabay', lambda: 'ok') == 'ok'


def test_provider_parallelism_is_bounded():
    gate, lock, active, peak = ProviderGate(), Lock(), [0], [0]
    def work():
        with lock: active[0] += 1; peak[0] = max(peak[0], active[0])
        time.sleep(.01)
        with lock: active[0] -= 1
    with ThreadPoolExecutor(8) as pool: list(pool.map(lambda _: gate.call('pixabay', work), range(12)))
    assert peak[0] == 2


@pytest.mark.parametrize('word', ['Pero', 'solo', 'Sólo', 'para', 'aunque', 'mientras'])
def test_spanish_function_words_never_turn_into_places(word):
    query = english_query(f'{word} Tijuana city Mexico', 'es', limit=8)
    assert word.casefold() not in query.casefold().split()
    assert 'Surakarta' not in query and 'Belem' not in query
    assert 'Tijuana' in query


@pytest.mark.parametrize('query,narration,expected', [
    ('Tijuana city USA', 'Tijuana tiene edificios modernos.', 'Tijuana city'),
    ('Monterrey mountains Belem', 'Monterrey está entre montañas.', 'Monterrey mountains'),
    ('Surakarta Mexico', 'Surakarta is in Indonesia.', 'Surakarta'),
    ('Tijuana Mexico', 'Tijuana is a city.', 'Tijuana Mexico'),
    ('Tijuana San Diego border', 'Tijuana and San Diego share a border.', 'Tijuana San Diego border'),
    ('Maracaibo Catatumbo lightning', 'Maracaibo and Catatumbo experience lightning.', 'Maracaibo Catatumbo lightning'),
])
def test_search_geography_scoped_to_spoken_shot(query, narration, expected):
    assert scope_query(query, narration) == expected


def test_scene_geography_overrides_majority_even_in_modern_mode():
    for mode in ('auto', 'modern'):
        setting = infer(['New York USA skyline.'] * 6, mode=mode)
        assert setting['regions'] == ['usa']
        for name in ('Tijuana', 'Monterrey', 'Mexico'):
            scene = for_scene(setting, f'{name} city today.')
            assert scene['regions'] == ['mexico'] and 'USA' not in scene['label_en']
        assert for_scene(setting, 'Lake Maracaibo and Catatumbo lightning.')['regions'] == ['venezuela']
        assert for_scene(setting, 'Surakarta city today.')['regions'] == []
    assert 'usa' not in infer(['Latin America and South America.'])['regions']


def scene(seconds=30, narration=None, **extra):
    return {'scene_id': 's', 'start_estimate': 0, 'end_estimate': seconds,
            'narration_text': narration or 'The ocean waves move toward the rocky shore. ' * 6,
            'primary_stock_query': 'ocean waves', 'alternative_stock_queries': ['rocky shore'],
            'visual_intent': 'ocean', 'preferred_media_type': 'stock_video', 'composition': 'wide', **extra}


def test_adaptive_new_15_minute_plan_keeps_clock_and_fast_beats():
    source = scene()
    legacy = make_slots(source)
    fresh = make_slots(source, adaptive=True)
    assert 180 <= len(fresh) * 30 <= 220
    assert len(fresh) < len(legacy)
    assert fresh[0]['estimated_start'] == 0 and fresh[-1]['estimated_end'] == 30
    assert sum(s['duration'] for s in fresh) == pytest.approx(30)
    assert all(a['estimated_end'] == b['estimated_start'] for a, b in zip(fresh, fresh[1:]))
    dense = make_slots(scene(narration='One short sentence. ' * 35), adaptive=True)
    assert len(dense) > len(fresh) and min(s['duration'] for s in dense) < 4
    assert source == scene()
    assert 'adaptive_pacing_version' not in legacy[0]


def test_preview_cache_is_bounded_and_keeps_failed_reads():
    from app.stock.preview_cache import PreviewCache
    cache, calls = PreviewCache(max_bytes=10, max_entries=2), []
    assert cache.get('failed', lambda: calls.append(1) or []) == ([], False)
    assert cache.get('failed', lambda: pytest.fail('do not repeat failed download')) == ([], True)
    block = [{'source': {'data': '123456'}}]
    cache.get('a', lambda: block); cache.get('b', lambda: block)
    assert cache.bytes <= 10 and len(cache.entries) <= 2 and calls == [1]


def test_verified_hash_detects_same_size_edit_and_replacement(tmp_path):
    from app.stock.download import Downloader
    downloader = Downloader(None)
    path = tmp_path / 'asset'; path.write_bytes(b'original')
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert downloader.verified_hash(path, sha) == sha
    assert downloader.verified_hash(path, sha) == sha and downloader.hash_cache_hits == 1
    path.write_bytes(b'modified')
    assert downloader.verified_hash(path, sha) != sha
    other = tmp_path / 'other'; other.write_bytes(b'original'); other.replace(path)
    assert downloader.verified_hash(path, sha) == sha


def test_embedding_batches_bounded_and_model_and_frame_invalidate():
    import numpy as np
    from app.integrations.openmontage import visual_engine as v
    v._EMBEDDINGS.clear(); sizes = []
    def encode(values):
        sizes.append(len(values)); return np.ones((len(values), 512), dtype=np.float32)
    keys = [('image', 'a', str(i)) for i in range(72)]
    try:
        v.embedded(list(range(72)), keys, encode, None, None)
        v.embedded(list(range(72)), keys, encode, None, None)
        assert sizes == [24, 24, 24]
        v.embedded([0], [('image', 'b', '0')], encode, None, None)
        v.embedded([0], [('image', 'a', 'changed')], encode, None, None)
        assert sizes[-2:] == [1, 1]
    finally: v._EMBEDDINGS.clear()


@pytest.mark.parametrize('body,category,raw', [
    ({'data': []}, 'empty', 0),
    ({'data': [{'id': 1, 'duration': 8, 'width': 1920, 'height': 1080}]}, 'filtered', 1),
    ({'data': [{'unexpected': 'shape'}]}, 'parse_error', 1),
])
def test_magnific_empty_filtered_and_parse_failures_are_distinct(body, category, raw):
    from app.stock.magnific import MagnificStockProvider
    provider = MagnificStockProvider('synthetic-only', transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    if category == 'parse_error':
        with pytest.raises(StockError): provider.search('ocean', 'video')
    else: assert provider.search('ocean', 'video') == []
    assert provider.last_diagnostic['result_category'] == category
    assert provider.last_diagnostic['raw_count'] == raw
    assert 'synthetic-only' not in str(provider.last_diagnostic)


def test_wall_time_is_separate_from_nested_totals(monkeypatch):
    import app.stock.performance as p
    tick = [0.]; monkeypatch.setattr(p, 'monotonic', lambda: tick[0])
    job, progress = {}, {'timings': {'clip': {'seconds': 10}, 'judging': {'seconds': 12}}}
    p.update_wall(job, progress); tick[0] = 15; p.update_wall(job, progress)
    assert progress['performance']['active_wall_seconds'] == 15
    assert progress['performance']['nested_stages'] == {'clip': 'judging'}


def test_explicit_empty_provider_list_never_falls_back():
    from app.stock.director_media import MediaDirector
    director = MediaDirector(SimpleNamespace(_cache_search=lambda *a, **k: pytest.fail('No provider should run')),
                             {'project_id': 'p', 'progress': {}})
    assert director.search({'order': 1}, ['video'], 'ocean waves', {'searches': []}, provider_names=[]) == []


def test_failed_premium_provider_is_not_forced_on_every_slot():
    from app.stock.director_media import MediaDirector
    calls = []
    def failed(*args, **kwargs):
        calls.append(1); raise StockError('rate_limit', 'Bekleyin')
    service = SimpleNamespace(_cache_search=failed, _checkpoint=lambda *a, **k: None)
    director = MediaDirector(service, {'project_id': 'p', 'progress': {}})
    for _ in range(3):
        assert director.search({'order': 1}, ['video'], 'ocean waves', {'searches': []}, provider_names=['magnific']) == []
    assert calls == [1] and director.progress['api_errors'] == {'magnific:rate_limit': 1}
    resumed = MediaDirector(service, {'project_id': 'p', 'progress': director.progress})
    assert resumed.unavailable == {}  # transient failures do not survive resume


def test_motion_identical_parallel_renders_share_completed_output(tmp_path, monkeypatch):
    from app.motion import clips
    calls = []
    monkeypatch.setattr(clips.templates, 'build', lambda *a: {'duration': 1, 'elements': []})
    def raster(scene, output, ffmpeg):
        calls.append(1); time.sleep(.02); output.write_bytes(b'synthetic-video')
    monkeypatch.setattr(clips, 'raster_render', raster)
    spec = {'template': 'quote', 'data': {'text': 'same'}}
    with ThreadPoolExecutor(2) as pool:
        outputs = list(pool.map(lambda _: clips.render_clip(tmp_path, spec, {}, 1, .5, ffmpeg='fake'), range(2)))
    assert calls == [1] and outputs[0][0] == outputs[1][0]
    assert {o[2] for o in outputs} == {'cache', 'local'}


def test_frontend_separates_nested_timings_and_cache_counts():
    from pathlib import Path
    page = (Path(__file__).parents[1] / 'app/static/stock.js').read_text()
    assert 'CLIP (judging içinde)' in page and 'Aşama süreleri toplanmaz' in page
    assert 'active_wall_seconds' in page and 'unique_queries' in page
    assert 'quality_cache_hits' in page and 'motion_cache_hits' in page


def test_legacy_query_cache_survives_normalization(stock_studio):
    from contextlib import closing
    import json
    from app.projects import now
    from test_stock_media import media
    client, project, _, _ = stock_studio
    service = client.app.state.stock
    with closing(service.projects._connection()) as connection, connection:
        connection.execute('INSERT OR REPLACE INTO stock_search_cache VALUES (?,?,?,?,?,?)',
            (project['id'], 'pixabay', 'video', '  Ocean   WAVES ', json.dumps([media(provider='pixabay')]), now()))
    before = len(service.test_calls)
    result, counts, cached = service._cache_search(project['id'], 'pixabay', 'video', 'ocean waves')
    assert cached and result and len(service.test_calls) == before


def test_service_coalesces_concurrent_case_variants(stock_studio):
    from test_stock_media import media
    client, project, _, _ = stock_studio
    service, entered, release, calls = client.app.state.stock, Event(), Event(), []
    def read(query, kind):
        calls.append(query); entered.set(); assert release.wait(3)
        return [media(provider='pixabay')]
    service.factory = lambda *args: SimpleNamespace(search=read)
    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(service._cache_search, project['id'], 'pixabay', 'video', 'Ocean waves')
        assert entered.wait(3)
        b = pool.submit(service._cache_search, project['id'], 'pixabay', 'video', '  OCEAN   waves ')
        deadline = time.monotonic() + 3
        while service.search_reads.shared < 1 and time.monotonic() < deadline: time.sleep(.001)
        release.set(); first, second = a.result(3), b.result(3)
    assert len(calls) == 1 and first[0] == second[0] and second[2]


def test_saved_legacy_slots_are_never_adaptively_regenerated(stock_studio):
    from contextlib import closing
    import json
    client, project, _, _ = stock_studio
    service = client.app.state.stock
    handoff = service._handoff(project['id'])
    with service.projects.lock, closing(service.projects._connection()) as connection, connection:
        state = service._ensure(connection, handoff)
        state['slots'] = [slot for scene in handoff['scenes'] for slot in make_slots(scene)]
        service._save(connection, state)
        before = json.dumps(state, sort_keys=True)
        restored = service._ensure(connection, handoff)
        assert json.dumps(restored, sort_keys=True) == before
        assert all('adaptive_pacing_version' not in slot for slot in restored['slots'])


@pytest.mark.parametrize('response,expected', [
    ({'error': {'code': 'maxlag'}}, 'rate_limit'),
    ({'error': {'code': 'badvalue'}}, 'invalid_response'),
    ({'query': {'pages': 'changed-schema'}}, 'invalid_response'),
    ({'query': 'changed-schema'}, 'invalid_response'),
    ({'query': {'pages': [None]}}, 'invalid_response'),
])
def test_wikimedia_errors_are_not_empty_results(response, expected):
    from app.stock.providers import WikimediaStockProvider
    provider = WikimediaStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response)))
    with pytest.raises(StockError) as error: provider.search('ancient temple', 'image')
    assert error.value.category == expected


def test_retry_after_prevents_early_reentry(monkeypatch):
    from app.stock.providers import PixabayStockProvider
    import app.stock.search_session as module
    tick = [0.]; monkeypatch.setattr(module, 'monotonic', lambda: tick[0])
    calls = []
    def limited(request):
        calls.append(1); return httpx.Response(429, headers={'Retry-After': '120'})
    provider = PixabayStockProvider('synthetic-only', transport=httpx.MockTransport(limited))
    gate = ProviderGate()
    with pytest.raises(StockError): gate.call('pixabay', lambda: provider.search('ocean', 'video'))
    tick[0] = 61
    with pytest.raises(StockError): gate.call('pixabay', lambda: provider.search('ocean', 'video'))
    assert calls == [1]


from test_stock_media import stock_studio
from test_production import production_studio
from test_scripts import studio


def test_old_query_cannot_pollute_clip_descriptor_geography():
    from app.stock.director_media import clip_descriptor
    source = {'scene_id': 's', 'narration_text': 'Tijuana city streets in Mexico.',
              'primary_stock_query': 'Tijuana city Mexico'}
    descriptor = clip_descriptor({'search_query': 'Tijuana city USA'}, source, 'en', {'label_en': 'present-day Mexico'})
    assert 'Tijuana' in descriptor and 'USA' not in descriptor


def test_catatumbo_only_shot_does_not_inherit_usa_query():
    assert scope_query('Catatumbo lightning USA', 'Catatumbo lightning illuminates the sky.') == 'Catatumbo lightning'


def test_continent_name_never_becomes_usa_in_automatic_queries():
    from app.scripts.query_clean import place_english
    from app.motion.places import spoken_places
    assert place_english('America') == ''
    assert all(name != 'America' for name, _, _ in spoken_places('Latin America and South America.'))
    assert 'USA' not in english_query('Latin America coast', 'es', strict=True)


def test_fact_dense_new_scenes_keep_shorter_shots():
    generic = make_slots(scene(), adaptive=True)
    factual = make_slots(scene(narration='In 1980, 1982, 1984, 1986, 1988 and 1990 the figures were 10, 20, 30, 40 and 50 percent.'), adaptive=True)
    assert len(factual) > len(generic)


def test_clip_worker_reports_only_bounded_numeric_cache_metrics(tmp_path):
    from app.stock.clip_check import ClipCheck
    bridge = SimpleNamespace(status=lambda: {'semantic_ready': True, 'semantic_model_version': 'synthetic'},
        call=lambda *a: {'results': [{'key': 'one', 'verdict': 'match', 'score': 8}],
                         'metrics': {'image_vector_hits': 3, 'text_vector_hits': 4, 'unsafe_url': 'https://secret.invalid'}})
    checker = ClipCheck(SimpleNamespace(openmontage=bridge))
    checker.score('ocean waves', [('one', [b'fake-frame'])], tmp_path)
    assert checker.metrics == {'image_vector_hits': 3, 'text_vector_hits': 4}


def test_changed_media_cannot_reuse_same_sentence_verdict():
    from app.stock.verdict_cache import cache_key
    media = {'provider': 'pixabay', 'media_type': 'video', 'media_id': 'one',
             'preview_url': 'https://cdn.pixabay.com/old.jpg'}
    original = cache_key(media, 'same-sentence')
    assert original == cache_key(deepcopy(media), 'same-sentence')
    assert original != cache_key({**media, 'preview_url': 'https://cdn.pixabay.com/new.jpg'}, 'same-sentence')
    assert original != cache_key({**media, 'sha256': 'changed-bytes'}, 'same-sentence')
    assert original != cache_key(media, 'different-sentence')
