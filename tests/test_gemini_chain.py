"""Gemini model backup chain: a model whose daily quota is used up hands over
to the next one (scene plan, Medyayı Tamamla …); a used-up model is skipped
until the Pacific-midnight reset; a per-minute limit waits on the same model;
when every model is used up the job stops and finished slots stay.
No network: Gemini, Pexels and Pixabay are mocked."""
from datetime import timedelta

import httpx
from fastapi.testclient import TestClient

import test_media_director_topics as T
import test_media_relevance_paste as R
from app.main import create_app
from app.providers import gemini_chain
from app.providers.gemini_chain import chain_models, default_chain
from app.stock.download import Downloader
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}
LISTED = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.5-flash-lite', 'gemini-3.0-flash', 'gemini-2.5-pro', 'gemini-2.5-flash-preview-05-20',
          'gemini-2.5-flash-preview-tts', 'gemini-embedding-001', 'gemini-2.5-flash-image', 'gemini-live-2.5-flash', 'gemini-3.0-flash-lite',
          'gemini-1.5-flash', 'gemini-2.0-flash-exp']
CHAIN = ['gemini-3.0-flash', 'gemini-2.5-flash', 'gemini-2.5-flash-lite']


def test_default_chain_selected_then_flash_then_lite_newest_first_and_never_unsuitable():
    assert default_chain('gemini-2.5-flash', LISTED) == ['gemini-2.5-flash', 'gemini-3.0-flash', 'gemini-3.0-flash-lite', 'gemini-2.5-flash-lite']
    # The owner's order wins; removed or no-longer-listed models and anything below 2.5 are dropped.
    config = {'model': 'gemini-2.5-flash', 'available_models': LISTED,
              'fallback_models': ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-9.9-flash', 'gemini-2.5-flash-preview-05-20']}
    assert chain_models(config) == ['gemini-2.5-flash-lite', 'gemini-2.5-flash']
    assert chain_models({**config, 'fallback_models': ['gemini-2.5-flash-lite']}) == ['gemini-2.5-flash', 'gemini-2.5-flash-lite']  # selected stays in
    assert gemini_chain.pacific_midnight().hour in (7, 8)  # 00:00 in Los Angeles is 07:00/08:00 UTC


def build(tmp_path, monkeypatch, key='rome'):
    """A pasted-text project whose Gemini answers per model: `world.dead`
    models answer with the daily-quota 429, `world.minute` with a minute limit."""
    monkeypatch.setattr('app.motion.clips.raster_render', T.fast_motion)
    data = T.TOPICS[key]
    world, director = R.World(key, data), T.Director(data)
    fake = T.FakeGemini(director)
    calls, dead, minute = [], set(), {}

    def handler(request):
        model = request.url.path.split('/models/')[1].split(':')[0]
        calls.append(model)
        if model in dead: return T.gemini_429(free=True)
        if minute.get(model): minute[model] -= 1; return T.gemini_429()
        return fake.handler(request)
    from app.providers import gemini
    class Patched(gemini.GeminiScriptProvider):
        def __init__(self, api_key, model='', *, transport=None):
            super().__init__(api_key, model, transport=httpx.MockTransport(handler))
    monkeypatch.setattr('app.providers.factory.GeminiScriptProvider', Patched)
    client = TestClient(create_app(tmp_path / key), headers=HEADERS).__enter__()
    s = client.app.state.settings
    for name, value in (('pexels', 'synthetic-pexels-key-1111'), ('pixabay', 'synthetic-pixabay-key-2222')):
        assert client.put(f'/api/settings/{name}', json={'api_key': value}, headers=SETTINGS).status_code == 200
    s.save('gemini', {'api_key': 'synthetic-gemini-key-3333'}); s.record_gemini_models(s.gemini_config(), LISTED); s.save('gemini', {'model': 'gemini-3.0-flash'})
    view = client.get('/api/settings', headers=SETTINGS).json()['gemini']
    assert [m['model'] for m in view['fallback_chain']] == ['gemini-3.0-flash', 'gemini-2.5-flash', 'gemini-3.0-flash-lite', 'gemini-2.5-flash-lite']
    r = client.put('/api/settings/gemini', json={'fallback_models': CHAIN}, headers=SETTINGS)  # the owner's own order
    assert r.status_code == 200 and [m['model'] for m in r.json()['gemini']['fallback_chain']] == CHAIN and r.json()['gemini']['fallback_custom']
    stock = client.app.state.stock
    stock.ai_sleep = lambda seconds, service: stock.__dict__.setdefault('slept', []).append(seconds)
    from app.stock import providers
    stock.factory = lambda name, settings: {'pexels': providers.PexelsStockProvider, 'pixabay': providers.PixabayStockProvider}[name](
        settings.stock_config(name)['api_key'], transport=httpx.MockTransport(world.handler))
    stock.downloader = Downloader(client.app.state.projects, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={'Content-Type': 'video/mp4' if request.url.path.endswith('.mp4') else 'image/jpeg'},
                                       content=(T.MP4 if request.url.path.endswith('.mp4') else T.JPEG) + str(request.url).encode())))
    stock.fetch_thumbnail = lambda url: R.jpeg((hash(url) % 255, 80, 120))
    stock.fetch_video_frames = lambda url, duration: [R.jpeg((40, 40 + i * 60, 90)) for i in range(3)]
    pid = client.post('/api/projects', json={'name': data['topic'], 'language': 'de'}).json()['id']
    assert client.post(f'/api/projects/{pid}/script/paste', json={'text': R.pasted_text(data)}).status_code == 201
    return client, pid, calls, dead, minute


def plan(client, pid):
    r = client.post(f'/api/projects/{pid}/production/plan', json={'provider': 'gemini', 'cost_confirmed': True, 'confirm_replace_plan': False})
    assert r.status_code == 202, r.text
    client.app.state.scripts.futures[r.json()['job_id']].result(timeout=60)
    return client.get(f'/api/projects/{pid}/production').json()['plan']


def test_first_two_models_used_up_the_third_finishes_plan_and_media(tmp_path, monkeypatch):
    client, pid, calls, dead, minute = build(tmp_path, monkeypatch)
    try:
        dead.update(CHAIN[:2])  # daily quota of the first two models is gone
        assert plan(client, pid)['blocks']  # the scene plan switches too
        assert set(calls) == {*CHAIN} and calls.count(CHAIN[0]) == 1 and calls.count(CHAIN[1]) == 1  # each used-up model asked once, then skipped
        marks = client.app.state.settings.gemini_exhausted()
        assert set(marks) == set(CHAIN[:2])
        view = client.get('/api/settings', headers=SETTINGS).json()['gemini']
        assert [bool(m['exhausted_until']) for m in view['fallback_chain']] == [True, True, False]  # shown in Settings
        before = len(calls)
        result = T.complete(client, pid)
        assert result['job']['status'] == 'completed', result['job']
        assert result['media_summary']['missing'] == 0
        assert set(calls[before:]) == {CHAIN[2]}  # used-up models are not tried again today
        stock = [s for s in result['slots'] if s['selected_media']['provider'] in ('pexels', 'pixabay') and not s.get('continuation_of')]
        assert stock and all(s['ai_review']['model'] == CHAIN[2] for s in stock)  # every slot records the deciding model
        assert 'seçen model: 2.5-flash-lite (' in result['media_summary']['text']  # the summary line names the models
        assert result['media_summary']['models'] == {CHAIN[2]: len(stock)}
        # After the Pacific-midnight reset the first model is used again.
        reset = gemini_chain.pacific_midnight() + timedelta(minutes=1)
        monkeypatch.setattr(gemini_chain, 'now_utc', lambda: reset)
        assert client.app.state.settings.gemini_exhausted() == {}
    finally:
        client.__exit__(None, None, None)


def test_model_switch_mid_job_continues_and_all_used_up_stops_keeping_finished_slots(tmp_path, monkeypatch):
    client, pid, calls, dead, minute = build(tmp_path, monkeypatch)
    try:
        plan(client, pid)
        start = len(calls)
        import app.providers.factory as factory
        original = factory.GeminiScriptProvider
        class Counting(original):  # the first model runs out after a few looks, the next one later, the last one too
            def complete_json(self, *args, **kwargs):
                used = len(calls) - start
                if self.model == CHAIN[0] and used >= 4: dead.add(CHAIN[0])
                if self.model == CHAIN[1] and used >= 8: dead.add(CHAIN[1])
                if self.model == CHAIN[2] and used >= 12: dead.add(CHAIN[2])
                return super().complete_json(*args, **kwargs)
        monkeypatch.setattr(factory, 'GeminiScriptProvider', Counting)
        view = T.complete(client, pid)
        job = view['job']
        assert job['status'] == 'error' and job['progress']['category'] == 'ai_paused', job
        assert 'yedek zincirindeki tüm modellerin (3.0-flash, 2.5-flash, 2.5-flash-lite) günlük ücretsiz kotası doldu' in job['error_message']
        decided = {s['ai_review']['model'] for s in view['slots'] if (s.get('ai_review') or {}).get('model')}
        assert decided >= {CHAIN[0], CHAIN[1]}  # the job moved down the chain and went on
        kept = {s['slot_id']: s['selected_media']['media_id'] for s in view['slots'] if s.get('selected_media') and s['selected_media']['provider'] != 'generated'}
        assert kept and not any(s['status'] == 'error' for s in view['slots'])  # finished slots stay; the rest wait
        assert all((s.get('director') or {}).get('stage') in (None, 'motion_planned') or s['selected_media']['provider'] != 'generated'
                   for s in view['slots'] if s.get('selected_media'))  # nothing fell to motion
        # Next day (or after clearing the marks in Settings) the job continues where it stopped.
        dead.clear(); monkeypatch.setattr(factory, 'GeminiScriptProvider', original)
        assert client.post('/api/settings/gemini/quota-reset', headers=SETTINGS).status_code == 200
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert all(next(s for s in view['slots'] if s['slot_id'] == k)['selected_media']['media_id'] == v for k, v in kept.items())
    finally:
        client.__exit__(None, None, None)


def test_minute_limit_waits_on_the_same_model_without_switching(tmp_path, monkeypatch):
    client, pid, calls, dead, minute = build(tmp_path, monkeypatch)
    try:
        plan(client, pid)
        start = len(calls)
        minute[CHAIN[0]] = 2  # two per-minute 429s, then fine
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed'
        assert set(calls[start:]) == {CHAIN[0]} and client.app.state.stock.slept == [7, 7]  # waited Retry-After, same model
        assert client.app.state.settings.gemini_exhausted() == {}
    finally:
        client.__exit__(None, None, None)


def test_chain_order_settings_validation(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        s = client.app.state.settings
        s.save('gemini', {'api_key': 'synthetic-gemini-key-3333'}); s.record_gemini_models(s.gemini_config(), LISTED); s.save('gemini', {'model': 'gemini-2.5-flash'})
        r = client.put('/api/settings/gemini', json={'fallback_models': ['gemini-2.5-flash', 'gemini-4.0-flash']}, headers=SETTINGS)
        assert r.status_code == 422 and 'Modelleri Getir' in r.json()['message']
        r = client.put('/api/settings/gemini', json={'fallback_models': None}, headers=SETTINGS)
        assert r.status_code == 200 and not r.json()['gemini']['fallback_custom']
        view = r.json()['gemini']
        assert {c['model'] for c in view['fallback_candidates']} == set()  # every suitable model is already in the automatic chain
        page = open('app/static/settings.js', encoding='utf-8').read()
        assert 'Yedek model sırası' in page and 'draggable = true' in page and "'Çıkar'" in page
