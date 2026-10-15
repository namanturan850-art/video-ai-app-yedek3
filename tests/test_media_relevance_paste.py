"""Six topics from PASTED text (no AI script writing): scene plan → Medyayı
Tamamla with deliberately irrelevant candidates in every search (dog, barber,
office, modern city, watermarked footage). None of them may ever be chosen;
only 7+/10 stock media is used; every slot is filled. No network."""
import base64
import io
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import test_media_director_topics as T
from app.main import create_app
from app.stock.download import Downloader
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}
IRRELEVANT = ['dog park running', 'barber shop haircut', 'office meeting laptop', 'modern city skyline traffic',
              'stormy ocean waves watermark', 'roman colosseum logo watermarked']
NOISE_WORDS = {'dog', 'barber', 'office', 'skyline', 'watermark', 'watermarked', 'logo', 'traffic'}


def jpeg(colour):
    out = io.BytesIO(); Image.new('RGB', (64, 36), colour).save(out, 'JPEG'); return out.getvalue()


class World(T.World):
    """The topic library plus irrelevant candidates returned for EVERY query."""
    def __init__(self, key, data):
        super().__init__(key, data)
        base = 7_000_000 + len(key) * 1000
        self.noise = [{'id': base + i * 2 + (kind == 'image'), 'tags': tag, 'kind': kind, 'portrait': False, 'duration': 20}
                      for i, tag in enumerate(IRRELEVANT) for kind in ('video', 'image')]

    def match(self, query, kind):
        hits = super().match(query, kind)
        return [h for h in hits if h not in self.noise] + [n for n in self.noise if n['kind'] == kind]


def pasted_text(data, words=390):
    out, n = [], 0
    while sum(len(s.split()) for s in out) < words:
        out.append(data['sentences'][n % 6]); n += 1
    paragraphs = [' '.join(out[i:i + 4]) for i in range(0, len(out), 4)]
    paragraphs[0] = '[GÖRSEL: ' + data['themes'][0][0] + '] ' + paragraphs[0]  # the owner's own visual note
    return '# ' + data['topic'] + '\n\n' + '\n\n'.join(paragraphs)


def build(tmp_path, monkeypatch, key):
    monkeypatch.setattr('app.stock.quality.inspect_media', lambda projects,pid,media,tools,start: {
        'accepted': True, 'sha256': media['sha256'], 'width': media['width'],
        'height': media['height'], 'duration': media.get('duration')})
    monkeypatch.setattr('app.motion.clips.raster_render', T.fast_motion)
    monkeypatch.setattr('app.stock.providers.ACTIVE', ('pexels', 'pixabay'))  # synthetic two-provider library (Commons: test_wikimedia.py)
    data = T.TOPICS[key]
    world, director = World(key, data), T.Director(data)
    fake = T.FakeGemini(director)
    from app.providers import gemini
    class Patched(gemini.GeminiScriptProvider):
        def __init__(self, api_key, model='', *, transport=None):
            super().__init__(api_key, model, transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr('app.providers.factory.GeminiScriptProvider', Patched)
    client = TestClient(create_app(tmp_path / key), headers=HEADERS).__enter__()
    s = client.app.state.settings
    for name, value in (('pexels', 'synthetic-pexels-key-1111'), ('pixabay', 'synthetic-pixabay-key-2222')):
        assert client.put(f'/api/settings/{name}', json={'api_key': value}, headers=SETTINGS).status_code == 200
    s.save('gemini', {'api_key': 'synthetic-gemini-key-3333'}); s.record_gemini_models(s.gemini_config(), ['gemini-test-model']); s.save('gemini', {'model': 'gemini-test-model'})
    s.save('general', {'ai_visual_check': True})  # Gemini looks at the candidates (off by default)
    stock = client.app.state.stock
    stock.ai_sleep = lambda seconds, service: None
    pid = client.post('/api/projects', json={'name': data['topic'], 'language': 'de'}).json()['id']
    r = client.post(f'/api/projects/{pid}/script/paste', json={'text': pasted_text(data)})
    assert r.status_code == 201, r.text
    r = client.post(f'/api/projects/{pid}/production/plan', json={'provider': 'gemini', 'cost_confirmed': True, 'confirm_replace_plan': False})
    assert r.status_code == 202, r.text
    client.app.state.scripts.futures[r.json()['job_id']].result(timeout=60)
    plan = client.get(f'/api/projects/{pid}/production').json()['plan']
    assert plan and plan['blocks'][0]['stock_query'] == data['themes'][0][0]  # [GÖRSEL] wins
    from app.stock import providers
    stock.factory = lambda name, settings: {'pexels': providers.PexelsStockProvider, 'pixabay': providers.PixabayStockProvider}[name](
        settings.stock_config(name)['api_key'], transport=httpx.MockTransport(world.handler))
    stock.downloader = Downloader(client.app.state.projects, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={'Content-Type': 'video/mp4' if request.url.path.endswith('.mp4') else 'image/jpeg'},
                                       content=(T.MP4 if request.url.path.endswith('.mp4') else T.JPEG) + str(request.url).encode())))
    stock.fetch_thumbnail = lambda url: jpeg((hash(url) % 255, 80, 120))
    stock.fetch_video_frames = lambda url, duration: [jpeg((40, 40 + i * 60, 90)) for i in range(3)]  # start/middle/end
    return client, pid, world, fake


def tags_of(world, media):
    wanted = int(media['media_id']) - (900000 if media['provider'] == 'pixabay' else 0)
    return next((i['tags'] for i in world.items + world.noise if i['id'] == wanted), '')


ROWS = {}


@pytest.mark.parametrize('key', list(T.TOPICS))
def test_pasted_topic_fills_every_slot_and_never_picks_irrelevant_media(key, tmp_path, monkeypatch):
    client, pid, world, fake = build(tmp_path, monkeypatch, key)
    try:
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed', view['job']
        summary = view['media_summary']
        assert summary['missing'] == 0
        chosen = [s for s in view['slots'] if s.get('selected_media') and s['selected_media']['provider'] in ('pexels', 'pixabay')]
        for slot in chosen:
            tags = tags_of(world, slot['selected_media'])
            assert not (set(re.findall(r'[a-z]+', tags)) & NOISE_WORDS), (key, tags)  # nothing irrelevant, nothing watermarked
            assert (slot.get('ai_review') or {}).get('score', 0) >= 7  # only 7+/10 stock media
        # Every video candidate shown to the AI came as ONE picture (its start/middle/end frames side by side).
        for request in fake.requests:
            parts = request['contents'][0]['parts']
            if not any('Candidate' in p.get('text', '') for p in parts): continue
            for i, part in enumerate(parts):
                if re.match(r'Candidate \d+: video', part.get('text', '')):
                    assert 'inlineData' in parts[i + 1] and 'inlineData' not in parts[i + 2], (key, part['text'][:60])
            assert sum(1 for p in parts if re.match(r'Candidate \d+:', p.get('text', ''))) <= 16  # one look per scene: ≤4 per slot, ≤16 in all
        progress = view['job']['progress']
        filtered = progress.get('irrelevant_filtered', 0)
        assert filtered > 0  # the irrelevant ones were seen and dropped
        ROWS[key] = {'slots': summary['total'], 'videos': summary['videos'], 'images': summary['images'], 'cards': summary['cards'],
                     'motion': summary['motion'], 'missing': summary['missing'], 'relevance': summary['relevance_average'], 'filtered': filtered}
        print(f'\nROW {key} ' + json.dumps(ROWS[key], ensure_ascii=False))
    finally:
        client.__exit__(None, None, None)


def test_owner_rejection_is_remembered_and_explained_to_the_ai(tmp_path, monkeypatch):
    client, pid, world, fake = build(tmp_path, monkeypatch, 'rome')
    try:
        view = T.complete(client, pid)
        slot = next(s for s in view['slots'] if s.get('selected_media', {}).get('provider') in ('pexels', 'pixabay'))
        old = slot['selected_media']
        before = len(fake.requests)
        base = f'/api/projects/{pid}/production/stock'
        r = client.post(f'{base}/slots/{slot["slot_id"]}/jobs', json={'plan_id': view['plan_id'], 'revision': view['revision'], 'action': 'reselect',
                                                                       'reason': 'modern bina görünüyor'})
        assert r.status_code == 202, r.text
        client.app.state.stock.futures[r.json()['job_id']].result(timeout=120)
        after = client.get(base).json()
        new = next(s for s in after['slots'] if s['slot_id'] == slot['slot_id'])['selected_media']
        assert (new['provider'], new['media_id']) != (old['provider'], old['media_id'])
        # Every candidate look after the rejection carries the reason (none is needed when the rest is decided
        # without the AI: cached verdicts, or modern office/traffic clips that the period check drops by their tags).
        looks = [' '.join(p.get('text', '') for p in r['contents'][0]['parts']) for r in fake.requests[before:]]
        looks = [t for t in looks if 'Candidate' in t]
        assert all('REJECTED' in t and 'modern bina görünüyor' in t for t in looks)
        T.complete(client, pid)  # a whole new pass never brings it back
        final = client.get(base).json()
        assert not any(s.get('selected_media', {}).get('media_id') == old['media_id'] and s['selected_media']['provider'] == old['provider'] for s in final['slots'])
    finally:
        client.__exit__(None, None, None)


def test_prefilter_threshold_and_tiers_unit():
    from app.stock.director_media import APPROVE_SCORE, CANDIDATES, MediaDirector, relevance_summary
    assert APPROVE_SCORE == 7 and CANDIDATES == 4
    d = MediaDirector.__new__(MediaDirector)
    d.rejected_keys, d.rejected_hashes = {('pexels', 'video', '9')}, set()
    scene = {'must_not_show': 'modern cars, modern buildings, office, people talking to camera'}
    media = lambda mid, tags: {'provider': 'pexels', 'media_type': 'video', 'media_id': mid, 'description': tags, 'query_used': ''}
    assert d.prefilter(media('1', 'ancient forum ruins columns'), scene) is None
    assert d.prefilter(media('2', 'rome street modern buildings traffic'), scene) == 'must_not_show'
    assert d.prefilter(media('3', 'business office meeting'), scene) == 'must_not_show'
    assert d.prefilter(media('4', 'colosseum stock preview watermark'), scene) == 'watermark_or_logo'
    assert d.prefilter(media('9', 'colosseum'), scene) == 'owner_rejected'
    filled = [{'slot_id': 'a', 'selected_media': {'provider': 'pexels', 'media_type': 'video'}, 'ai_review': {'score': 8}},
              {'slot_id': 'b', 'selected_media': {'provider': 'pixabay', 'media_type': 'image'}, 'ai_review': {'score': 10}},
              {'slot_id': 'c', 'selected_media': {'provider': 'generated', 'media_type': 'video'}, 'ai_review': None}]
    assert relevance_summary(filled) == {'relevance_average': 9.0, 'relevance_low_slots': ['a']}  # 7–8 flagged for a first look
