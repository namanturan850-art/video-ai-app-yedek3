"""The app works without Gemini: busy (503), quota full or the AI look
switched off never stop scene planning or Medyayı Tamamla. Candidates are
then scored locally and marked; one click re-checks them when Gemini is
back. Fewer requests (one look per scene, one picture per candidate, shared
verdict cache). Scene-plan clean-up (map → infographic, symbolic → concrete,
no copied neighbour queries). No network: everything paid is mocked."""
import json
import re

import httpx

import test_gemini_chain as C
import test_media_director_topics as T
from app.scripts.local_plan import plan_scenes
from app.scripts.query_refine import concrete, refine

SETTINGS = {'X-AI-Video-Studio': 'settings'}


def build(tmp_path, monkeypatch, key='rome'):
    monkeypatch.setattr('app.providers.gemini_chain.PAUSE', lambda seconds: None)
    monkeypatch.setattr('app.providers.gemini_chain._strikes', {})
    client, pid, calls, dead, minute = C.build(tmp_path, monkeypatch, key)
    busy = set()
    factory = __import__('app.providers.factory', fromlist=['GeminiScriptProvider'])
    patched = factory.GeminiScriptProvider
    class Busy(patched):  # Gemini answers “503 server busy” for the models in `busy`
        def _request(self, client, method, path, **kwargs):
            if self.model in busy and ':generateContent' in path:
                calls.append(self.model)
                from app.providers.base import ScriptProviderError
                raise ScriptProviderError('Google Gemini API şu anda yanıt veremiyor. Daha sonra tekrar deneyin.', 503, category='upstream_error', upstream_status=503)
            return super()._request(client, method, path, **kwargs)
    monkeypatch.setattr(factory, 'GeminiScriptProvider', Busy)
    return client, pid, calls, dead, busy


def plan(client, pid, provider='gemini'):
    r = client.post(f'/api/projects/{pid}/production/plan', json={'provider': provider, 'cost_confirmed': provider != 'local', 'confirm_replace_plan': False})
    assert r.status_code == 202, r.text
    client.app.state.scripts.futures[r.json()['job_id']].result(timeout=60)
    return client.get(f'/api/projects/{pid}/production').json()['plan']


def stock_slots(view):
    return [s for s in view['slots'] if s['selected_media']['provider'] in ('pexels', 'pixabay', 'wikimedia') and not s.get('continuation_of')]


def no_fallback_motion(view):
    return all(s['selected_media']['provider'] != 'generated' or (s.get('director') or {}).get('stage') in ('motion_planned', 'motion_owner', 'motion')
               for s in view['slots'])


def test_gemini_always_busy_media_still_completes_locally_then_one_click_recheck(tmp_path, monkeypatch):
    client, pid, calls, dead, busy = build(tmp_path, monkeypatch)
    try:
        assert plan(client, pid)['blocks']
        busy.update(C.CHAIN)  # every model answers 503 from now on
        before = len(calls)
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed', view['job']
        summary = view['media_summary']
        assert summary['missing'] == 0 and summary['videos'] + summary['images'] > 0  # stock media, not an empty project
        local = stock_slots(view)
        assert local and all(s['local_review'] and s['needs_ai_review'] and not s.get('ai_review') for s in local)  # “yapay zekâ onayı yok”
        assert summary['unchecked'] == len(local) and 'yapay zekâ onayı bekliyor' in summary['text']
        assert 'Medya seçimi durmadı' in view['job']['progress']['message']
        # The chain moved down all three models (two 503s each → 15 min off), then the job went on locally.
        assert set(calls[before:]) == set(C.CHAIN)
        marks = client.app.state.settings.gemini_exhausted()
        assert set(marks) == set(C.CHAIN)
        diag = client.get(f'/api/projects/{pid}/production/stock/diagnostics').json()
        tried = diag['gemini_models_tried']
        assert all(tried[m]['errors'].get('upstream_error') for m in C.CHAIN)  # every attempt: model + error
        assert diag['jobs'][0]['progress']['local_mode'] == 'down'
        # Gemini is back: one click re-checks only the unchecked slots with the AI.
        busy.clear()
        assert client.post('/api/settings/gemini/quota-reset', headers=SETTINGS).status_code == 200
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['unchecked'] == 0
        assert all((s.get('ai_review') or {}).get('approved') for s in stock_slots(view))
    finally:
        client.__exit__(None, None, None)


def test_quota_full_on_every_model_media_completes_without_stopping(tmp_path, monkeypatch):
    client, pid, calls, dead, busy = build(tmp_path, monkeypatch)
    try:
        plan(client, pid)
        dead.update(C.CHAIN)  # daily quota of every model used up
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert stock_slots(view) and no_fallback_motion(view)
        assert 'günlük ücretsiz kotası doldu' in view['job']['progress']['message']
    finally:
        client.__exit__(None, None, None)


def test_ai_visual_check_off_sends_no_gemini_request(tmp_path, monkeypatch):
    client, pid, calls, dead, busy = build(tmp_path, monkeypatch)
    try:
        plan(client, pid)
        r = client.put('/api/settings/general', json={'content_language': 'de', 'ai_visual_check': False}, headers=SETTINGS)
        assert r.status_code == 200 and r.json()['general']['ai_visual_check'] is False
        before = len(calls)
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert len(calls) == before  # not a single Gemini request
        assert view['job']['progress']['local_mode'] == 'off' and stock_slots(view)
        page = open('app/static/settings.js', encoding='utf-8').read()
        assert "name: 'ai_visual_check'" in page and 'Yapay zekâ görsel kontrolü' in page
    finally:
        client.__exit__(None, None, None)


def test_two_503_in_a_row_switch_model_for_15_minutes(tmp_path, monkeypatch):
    client, pid, calls, dead, busy = build(tmp_path, monkeypatch)
    try:
        busy.add(C.CHAIN[0])
        assert plan(client, pid)['blocks']  # the plan job switched to the next model
        marks = client.app.state.settings.gemini_exhausted()
        from datetime import datetime
        from app.providers.gemini_chain import now_utc
        assert set(marks) == {C.CHAIN[0]}
        minutes = (datetime.fromisoformat(marks[C.CHAIN[0]]) - now_utc()).total_seconds() / 60
        assert 14 <= minutes <= 15.1  # skipped for 15 minutes, not for the day
        assert calls.count(C.CHAIN[0]) == 2 and C.CHAIN[1] in calls
    finally:
        client.__exit__(None, None, None)


def test_one_request_per_scene_one_picture_per_candidate_and_shared_cache(tmp_path, monkeypatch):
    client, pid, calls, dead, busy = build(tmp_path, monkeypatch)
    try:
        plan(client, pid)
        view = T.complete(client, pid)
        scenes = len({s['scene_id'] for s in view['slots']})
        requests = view['ai_requests']['last_job']
        slots = len(view['slots'])
        assert 0 < requests <= scenes + slots // 3, (requests, scenes, slots)  # about one look per scene, not one per slot
        assert view['ai_requests']['total'] == requests
        page = open('app/static/stock.js', encoding='utf-8').read()
        assert 'Yapay zekâ isteği: son işte' in page
    finally:
        client.__exit__(None, None, None)
    # Same topic in a new project of the same app: the AI is not asked again for the same clips.
    client2, pid2, calls2, dead2, busy2 = build(tmp_path / 'second', monkeypatch)
    try:
        storage = client2.app.state.projects.storage
        first = (tmp_path / 'rome')
        cache = list(first.rglob('ai_verdict_cache.json'))
        assert cache, 'verdict cache not written'
        target = storage / 'ai_verdict_cache.json'
        target.write_bytes(cache[0].read_bytes())  # (one data folder per app in real use)
        plan(client2, pid2)
        view = T.complete(client2, pid2)
        assert view['job']['status'] == 'completed'
        assert view['job']['progress'].get('ai_cached', 0) > 0
        assert view['ai_requests']['last_job'] < requests
    finally:
        client2.__exit__(None, None, None)


def test_judge_sends_one_picture_per_candidate():
    from app.stock.director_media import collage
    import base64, io
    from PIL import Image
    def block(colour):
        out = io.BytesIO(); Image.new('RGB', (320, 180), colour).save(out, 'JPEG')
        return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': base64.b64encode(out.getvalue()).decode()}}
    one = collage([block((255, 0, 0)), block((0, 255, 0)), block((0, 0, 255))])
    image = Image.open(io.BytesIO(base64.b64decode(one['source']['data'])))
    assert image.height == 240 and image.width > 3 * 400  # three frames side by side in ONE picture


def test_scene_plan_clean_up_map_symbolic_and_neighbours():
    assert concrete('bird caged in wooden box symbolizing Hiskija') == 'bird caged in wooden box'
    assert concrete('map showing deportations of the Israelites') == 'map'[:0] or concrete('map showing deportations of the Israelites') == ''
    blocks = [{'narration': 'Die Assyrer kamen aus Ninive nach Jerusalem.', 'stock_query': 'map showing deportations from Jerusalem',
               'alternative_stock_queries': ['ancient city walls ruins'], 'media_type': 'stock_video', 'entities': [], 'visual_intent': 'map'},
              {'narration': 'Hiskija betete.', 'stock_query': 'bird caged in wooden box symbolizing Hiskija',
               'alternative_stock_queries': ['ancient king praying temple'], 'media_type': 'stock_video', 'entities': ['Hiskija'], 'visual_intent': 'x'},
              {'narration': 'Die Mauern hielten.', 'stock_query': 'ancient city walls ruins', 'alternative_stock_queries': ['stone gate old city'],
               'media_type': 'stock_video', 'entities': [], 'visual_intent': 'x'},
              {'narration': 'Die Mauern hielten weiter.', 'stock_query': 'ancient city walls ruins', 'alternative_stock_queries': ['torch lit corridor'],
               'media_type': 'stock_video', 'entities': [], 'visual_intent': 'x'}]
    out = refine(json.loads(json.dumps(blocks)))
    assert out[0]['media_type'] == 'motion_graphic' and out[0]['motion_spec']['template'] == 'map'  # Jerusalem is a known place
    assert out[0]['motion_spec']['data']['place'] == 'Jerusalem'
    assert out[1]['stock_query'] == 'bird caged in wooden box'  # concrete part only
    mains = [b['stock_query'] for b in out]
    assert all(mains[i] not in mains[max(0, i - 2):i] for i in range(len(mains)))  # never a copy of the two scenes before
    for b in out:
        queries = [b['stock_query'], *b['alternative_stock_queries']]
        assert all(2 <= len(q.split()) <= 12 and not re.search(r'[.!?;]', q) for q in queries) and len(set(map(str.casefold, queries))) == len(queries)


def test_no_ai_local_plan_and_never_ollama_by_itself(tmp_path, monkeypatch):
    client, pid, calls, dead, busy = build(tmp_path, monkeypatch)
    try:
        busy.update(C.CHAIN)
        r = client.post(f'/api/projects/{pid}/production/plan', json={'provider': 'gemini', 'cost_confirmed': True, 'confirm_replace_plan': False})
        client.app.state.scripts.futures[r.json()['job_id']].result(timeout=60)
        job = client.get(f'/api/projects/{pid}/script').json()['job']
        assert job['status'] == 'error' and job['provider'] == 'gemini'  # no silent switch to Ollama
        assert client.get(f'/api/projects/{pid}/script').json()['default_provider'] == 'gemini'
        js = open('app/static/production.js', encoding='utf-8').read()
        assert 'Yapay zekâsız yerel planla devam et' in js and 'Ollama ile planla' in js
        before = len(calls)
        result = plan(client, pid, 'local')  # the owner chose the no-AI plan
        assert result['blocks'] and result['provider'] == 'local' and len(calls) == before
        view = T.complete(client, pid)  # and media still completes (Gemini busy → local scoring)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
    finally:
        client.__exit__(None, None, None)
    scenes = plan_scenes([{'unit_id': f'U{i}', 'text': t} for i, t in enumerate(
        ['Rom wuchs zu einem Weltreich.', 'Das Kolosseum fasste viele Zuschauer.', 'Aquädukte brachten Wasser.', 'Legionen sicherten Grenzen.'])], 'Das antike Rom')
    assert sum(len(s['unit_ids']) for s in scenes) == 4 and all(len(s['stock_query'].split()) >= 2 for s in scenes)


def test_history_scene_rejects_modern_pixabay_footage():
    from app.stock.director_media import MediaDirector
    d = MediaDirector.__new__(MediaDirector)
    d.rejected_keys, d.rejected_hashes = set(), set()
    scene = {'visual_intent': 'ancient roman forum ruins', 'narration_text': 'Im antiken Rom …'}
    media = lambda provider, tags: {'provider': provider, 'media_type': 'video', 'media_id': '1', 'description': tags, 'query_used': 'roman forum'}
    assert d.prefilter(media('pixabay', 'rome city traffic car modern'), scene) == 'modern_in_history'
    assert d.prefilter(media('pixabay', 'roman forum ruins columns'), scene) is None
    assert d.prefilter(media('pixabay', 'office laptop'), {'visual_intent': 'space galaxy', 'narration_text': 'Sterne'}) is None
