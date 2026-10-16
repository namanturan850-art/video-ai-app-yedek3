"""Gemini never stalls Medyayı Tamamla; media choice does not depend on
Gemini (English-only queries, local CLIP check); the nine marker
infographics. Everything offline: Gemini, stock sites and CLIP are faked."""
import base64
import io
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import test_media_director_topics as T
import test_media_relevance_paste as R
from app.main import create_app
from app.providers.base import ScriptProviderError
from app.stock.download import Downloader
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}
NOISE = {'dog', 'barber', 'office', 'skyline', 'watermark', 'watermarked', 'logo', 'traffic'}


def jpeg(colour, size=(320, 180)):
    out = io.BytesIO(); Image.new('RGB', size, colour).save(out, 'JPEG'); return out.getvalue()


def noise_ids(world):
    ids = set()
    for item in world.noise + [i for i in world.items if set(i['tags'].split()) & NOISE]:
        ids |= {str(item['id']), str(item['id'] + 900000)}
    return ids


def clip_fake(world, calls):
    """Stand-in for the CLIP model: the synthetic library's irrelevant clips (dog, office, modern city …) score low."""
    bad = noise_ids(world)
    def score(descriptor, items):
        calls.append((descriptor, len(items)))
        assert descriptor.isascii() and descriptor.startswith('a photo of')  # English description for the picture model
        return {key: ({'verdict': 'mismatch', 'score': 2, 'similarity': .17, 'contrast_margin': -.04} if key.split(':')[2] in bad
                      else {'verdict': 'match', 'score': 8, 'similarity': .29, 'contrast_margin': .03}) for key, _ in items}
    return score


def make(tmp_path, monkeypatch, text=None, *, key='rome', visual_check=False, plan='local', fast=True, language='de'):
    monkeypatch.setattr('app.stock.quality.inspect_media', lambda projects,pid,media,tools,start: {
        'accepted': True, 'sha256': media['sha256'], 'width': media['width'],
        'height': media['height'], 'duration': media.get('duration')})
    if fast: monkeypatch.setattr('app.motion.clips.raster_render', T.fast_motion)
    monkeypatch.setattr('app.stock.providers.ACTIVE', ('pexels', 'pixabay'))
    monkeypatch.setattr('app.providers.gemini_chain.PAUSE', lambda seconds: None)
    monkeypatch.setattr('app.providers.gemini_chain._strikes', {})
    data = T.TOPICS[key]
    world, director = R.World(key, data), T.Director(data)
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
    if visual_check: s.save('general', {'ai_visual_check': True})
    stock = client.app.state.stock
    stock.ai_sleep = lambda seconds, service: None
    pid = client.post('/api/projects', json={'name': data['topic'], 'topic': data['topic'], 'language': language}).json()['id']
    r = client.post(f'/api/projects/{pid}/script/paste', json={'text': text or R.pasted_text(data)})
    assert r.status_code == 201, r.text
    r = client.post(f'/api/projects/{pid}/production/plan', json={'provider': plan, 'cost_confirmed': plan != 'local', 'confirm_replace_plan': False})
    assert r.status_code == 202, r.text
    client.app.state.scripts.futures[r.json()['job_id']].result(timeout=120)
    from app.stock import providers
    stock.factory = lambda name, settings: {'pexels': providers.PexelsStockProvider, 'pixabay': providers.PixabayStockProvider}[name](
        settings.stock_config(name)['api_key'], transport=httpx.MockTransport(world.handler))
    stock.downloader = Downloader(client.app.state.projects, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={'Content-Type': 'video/mp4' if request.url.path.endswith('.mp4') else 'image/jpeg'},
                                       content=T.MP4 + str(request.url).encode() if request.url.path.endswith('.mp4') else jpeg((120, 110, 90), (1280, 720)))))
    stock.fetch_thumbnail = lambda url: jpeg((hash(url) % 255, 80, 120))
    stock.fetch_video_frames = lambda url, duration: [jpeg((40, 40 + i * 60, 90)) for i in range(3)]
    return client, pid, world, fake


def stock_slots(view):
    return [s for s in view['slots'] if s['selected_media']['provider'] in ('pexels', 'pixabay') and not s.get('continuation_of')]


# ---- A: Gemini never holds the job ------------------------------------------------
def test_chain_asks_at_most_three_models_once_each(monkeypatch):
    from app.providers import gemini_chain
    monkeypatch.setattr(gemini_chain, '_strikes', {})
    marks, asked = {}, []
    class Settings:
        def gemini_exhausted(self): return dict(marks)
        def mark_gemini_exhausted(self, model, until): marks[model] = until
    class Busy:
        def __init__(self, key, model): self.model = model
        def complete_json(self, *a, **k):
            asked.append(self.model)
            raise ScriptProviderError('busy', 503, category='upstream_error')
    models = [f'gemini-2.5-flash-{i}' for i in range(6)]
    chain = gemini_chain.GeminiChain('synthetic-key-123', models, Settings(), Busy)
    with pytest.raises(ScriptProviderError) as error:
        chain.complete_json('x', 'y', {})
    assert asked == models[:3] and getattr(error.value, 'chain_exhausted', False)  # three models, one attempt each, then the caller goes local
    assert set(marks) == set(models[:3])


def test_picture_requests_use_a_45_second_timeout(monkeypatch):
    from app.providers.gemini import GeminiScriptProvider
    seen = []
    provider = GeminiScriptProvider('synthetic-gemini-key-3333', 'gemini-test-model')
    monkeypatch.setattr(provider, '_generate', lambda parts, json_mode=False, system=None, timeout=None: seen.append(timeout) or '{"ok": true}')
    image = {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': base64.b64encode(jpeg((1, 2, 3))).decode()}}
    provider.complete_json('media_select', 'rate', {'type': 'object', 'required': ['ok']}, images=[image])
    provider.complete_json('plan', 'text only', {'type': 'object', 'required': ['ok']})
    assert seen == [45, None]  # pictures: 45 s; text keeps the normal limit


def test_no_gemini_answer_in_the_first_minute_whole_job_goes_local(tmp_path, monkeypatch):
    client, pid, world, fake = make(tmp_path, monkeypatch, visual_check=True)
    try:
        monkeypatch.setattr('app.stock.director_media.FIRST_ANSWER_SECONDS', 1.5)  # (60 s in the app)
        monkeypatch.setattr('app.stock.director_media.PROGRESS_TICK', .2)
        import app.providers.factory as factory
        original = factory.GeminiScriptProvider
        class Hanging(original):  # every picture request hangs (like the 180 s time-outs of the diagnostics file)
            def complete_json(self, *args, **kwargs):
                time.sleep(4); raise ScriptProviderError('timeout', 504, category='gemini_timeout')
        monkeypatch.setattr(factory, 'GeminiScriptProvider', Hanging)
        started = time.monotonic()
        view = T.complete(client, pid)
        elapsed = time.monotonic() - started
        job = view['job']
        assert job['status'] == 'completed' and view['media_summary']['missing'] == 0, job
        assert job['progress']['local_mode'] == 'down' and '1 sn' not in job['progress']['local_reason']
        assert job['progress']['ai_failure']['category'] == 'gemini_timeout'
        assert elapsed < 60, elapsed  # the 4 s hangs were not waited out one after another
        assert job['progress']['ai_requests'] == 1  # one look timed out → no further Gemini request
    finally:
        client.__exit__(None, None, None)


def test_picture_batch_503_diagnosed_and_sent_one_by_one(tmp_path, monkeypatch):
    client, pid, world, fake = make(tmp_path, monkeypatch, visual_check=True)
    try:
        import app.providers.factory as factory
        original = factory.GeminiScriptProvider
        sizes = []
        class BatchBusy(original):
            def complete_json(self, purpose, prompt, schema, *, images=(), **kwargs):
                pictures = sum(1 for b in images if b.get('type') == 'image')
                sizes.append(pictures)
                if pictures > 1: raise ScriptProviderError('busy', 503, category='upstream_error', upstream_status=503)
                return super().complete_json(purpose, prompt, schema, images=images, **kwargs)
        monkeypatch.setattr(factory, 'GeminiScriptProvider', BatchBusy)
        view = T.complete(client, pid)
        job = view['job']
        assert job['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert 'görsel toplu istek 503 verdi' in job['progress']['gemini_503_diagnosis']
        probe = sizes.index(0)
        assert sizes[probe - 1] > 1 and 1 in sizes[probe + 1:] and max(sizes[probe + 1:]) <= 1  # text check, then one picture per request
        assert max(sizes) <= 4  # never more than four pictures per request
        assert all(s['ai_review']['approved'] for s in stock_slots(view))
    finally:
        client.__exit__(None, None, None)


def test_plan_goes_local_when_gemini_hangs(tmp_path, monkeypatch):
    monkeypatch.setattr('app.scripts.quality.PLAN_DEADLINE', 1)  # (90 s in the app)
    import app.providers.gemini as gemini
    original = gemini.GeminiScriptProvider.generate_script
    monkeypatch.setattr(gemini.GeminiScriptProvider, 'generate_script', lambda self, prompt: time.sleep(3) or original(self, prompt))
    client, pid, world, fake = make(tmp_path, monkeypatch, plan='gemini')
    try:
        job = client.get(f'/api/projects/{pid}/script').json()['job']
        assert job['status'] == 'draft' and 'kendi kurallarıyla' in job['progress']['local_fallback']['message']
        plan = client.get(f'/api/projects/{pid}/production').json()['plan']
        assert plan['blocks'] and all(b['stock_query'].isascii() for b in plan['blocks'])
    finally:
        client.__exit__(None, None, None)


# ---- B: media choice without Gemini ------------------------------------------------
@pytest.mark.parametrize('query,expected', [
    ('Christus Handvoll Stadttor', 'jesus christ city gate'),
    ('Siebenhundertfünf Christus Leichnam', 'jesus christ burial'),
    ('Kudüs surları', 'Jerusalem city walls'),
    ('v. Chr. 586 Babylon Zerstörung', 'Babylon'),
    # Known place names are preserved before adjective/stem translation.
    ('eski Mısır tapınağı', 'old Egypt temple'),
    ('airplane cockpit at night', 'airplane cockpit at night'),
    ('black hole space', 'black hole space'),
])
def test_stock_queries_are_english_only(query, expected):
    from app.scripts.query_clean import english_query
    assert english_query(query, 'de') == expected


def test_local_plan_queries_have_no_german_or_turkish_words():
    from app.scripts.local_plan import plan_scenes
    units = [{'unit_id': f'U{i}', 'text': t} for i, t in enumerate([
        'Im Jahr siebenhundertfünf vor Christus stand eine Handvoll Männer am Stadttor.',
        'Der Leichnam wurde aus der Stadt getragen.', 'Die Assyrer zogen von Ninive nach Jerusalem.', 'Dann kam der Sturm.'])]
    for scene in plan_scenes(units, 'Das alte Jerusalem', 'de'):
        for query in [scene['stock_query'], *scene['alternative_stock_queries']]:
            assert query.isascii() and not {'handvoll', 'christus', 'stadttor', 'leichnam', 'chr'} & set(query.casefold().split()), query
            assert not any(w in query.casefold().split() for w in ('siebenhundertfünf', 'vor', 'nach', 'der', 'die')), query


def test_clip_drops_irrelevant_candidates_and_shows_the_score(tmp_path, monkeypatch):
    client, pid, world, fake = make(tmp_path, monkeypatch)
    try:
        calls = []
        client.app.state.stock.clip_scorer = clip_fake(world, calls)
        before = len(fake.requests)
        view = T.complete(client, pid)
        job = view['job']
        assert job['status'] == 'completed' and view['media_summary']['missing'] == 0
        after = fake.requests[before:]
        assert not any(p.get('inline_data') or p.get('inlineData') for r in after for p in r['contents'][0]['parts'])  # picture check off by default: no picture sent
        assert len(after) <= 1  # only the one Turkish translation request of the media screen
        chosen = stock_slots(view)
        assert chosen and not any(s['selected_media']['media_id'] in noise_ids(world) for s in chosen)
        assert all(s['local_review']['method'] == 'clip' and s['local_review']['clip']['score'] >= 7 and not s['needs_ai_review'] for s in chosen)
        assert calls and max(n for _, n in calls) <= 24 and 'clip_warning' not in job['progress']
        assert job['progress']['clip_ready'] is True
        motion = sum(s['selected_media']['provider'] == 'generated' and not s.get('continuation_of') for s in view['slots'])
        # This fixture offers portrait videos only: quality wins over the old
        # arbitrary motion quota. Landscape photos / relevant graphics remain.
        assert all(s['selected_media']['width'] > s['selected_media']['height'] for s in chosen)
        assert not any(s.get('setting_relaxed') for s in view['slots'])
    finally:
        client.__exit__(None, None, None)


def test_without_clip_a_plain_warning_and_the_job_still_finishes(tmp_path, monkeypatch):
    client, pid, world, fake = make(tmp_path, monkeypatch)
    try:
        view = T.complete(client, pid)
        job = view['job']
        assert job['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert 'INSTALL_OPENMONTAGE_SEMANTIC.bat' in job['progress']['clip_warning']
        assert not any(s['selected_media']['media_id'] in noise_ids(world) for s in stock_slots(view))
        motion = sum(s['selected_media']['provider'] == 'generated' and not s.get('continuation_of') for s in view['slots'])
        assert not any(s.get('setting_relaxed') for s in view['slots'])
        assert all(s['selected_media']['width'] > s['selected_media']['height'] for s in stock_slots(view))
        page = client.get('/static/stock.js').text
        assert 'stock-clip-warning' in page and 'Yerel görüntü modeli (CLIP)' in page
    finally:
        client.__exit__(None, None, None)


def test_gemini_on_is_asked_only_about_candidates_clip_is_unsure_of(tmp_path, monkeypatch):
    client, pid, world, fake = make(tmp_path, monkeypatch, visual_check=True)
    try:
        bad = noise_ids(world)
        unsure = set()
        def score(descriptor, items):
            out = {}
            for n, (key, _) in enumerate(items):
                if key.split(':')[2] in bad: out[key] = {'verdict': 'mismatch', 'score': 2}
                elif n % 2: out[key] = {'verdict': 'uncertain', 'score': 6}; unsure.add(key)
                else: out[key] = {'verdict': 'match', 'score': 8}
            return out
        client.app.state.stock.clip_scorer = score
        before = len(fake.requests)
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        asked = [r for r in fake.requests[before:] if any('Candidate' in p.get('text', '') for p in r['contents'][0]['parts'])]
        assert asked and unsure
        for request in asked:  # only CLIP-undecided candidates reach Gemini
            texts = [p['text'] for p in request['contents'][0]['parts'] if p.get('text', '').startswith('Candidate')]
            assert texts and all('CLIP): uncertain' in t for t in texts)
    finally:
        client.__exit__(None, None, None)


# ---- C: the nine marker infographics ------------------------------------------------
MARKED = {
    'history': ('Das antike Rom',
                'Die Assyrer zogen mit ihrem Heer nach Westen. [ROTA: Ninive > Babil > Kudüs > Atlantis-Nirgendwo] '
                'Ihr Reich wuchs über drei Jahrhunderte. [İMPARATORLUK: Assyrien 911-612 v. Chr.] '
                'Die Säulen des Tempels stehen bis heute. [İŞARETLE: Die Säulen des Tempels] '
                'Zehntausend Soldaten belagerten die Stadt. [İKON: 10000 Soldaten] '
                'Auf David folgte Salomo. [HANEDAN: David > Salomo > Rehabeam, Jerobeam] '
                'Die Mauern waren riesig. [BİLGİ: Babylons Mauern waren so breit, dass Wagen darauf fahren konnten.] '
                'Rom wuchs von einem kleinen Dorf zu einem Weltreich. Aquädukte brachten täglich frisches Wasser aus den Bergen.'),
    'geography': ('Leben in der Tiefsee',
                  'Der Kilimandscharo ist der höchste Berg Afrikas. [YAKINLAŞ: Kilimandscharo] '
                  'Rund 71 Prozent der Erde sind mit Wasser bedeckt. [ORAN: %71 Wasser bedeckt die Erde] '
                  'Wo früher ein Hafen war, ist heute Land. [ÖNCESONRA: Antiker Hafen | Heutige Küste] '
                  'Viele Schiffe fuhren über das Meer. Das Meer ist tief und dunkel. Tiere leben dort in völliger Finsternis.'),
    'space': ('Schwarze Löcher',
              'Die Raketen starteten in Florida. [ROTA: Kennedy Space Center > Houston] '
              'Im Sonnensystem kreisen acht Planeten. [İKON: 8 Planeten] '
              'Ein Tag auf der Venus ist lang. [BİLGİ: Ein Tag auf der Venus dauert länger als ein ganzes Venusjahr.] '
              'Sterne entstehen in riesigen Gaswolken. Galaxien enthalten Milliarden Sterne.'),
}


@pytest.mark.parametrize('topic', list(MARKED))
def test_markers_become_infographics_on_every_topic(topic, tmp_path, monkeypatch):
    title, text = MARKED[topic]
    key = {'history': 'rome', 'geography': 'deepsea', 'space': 'blackholes'}[topic]
    client, pid, world, fake = make(tmp_path, monkeypatch, f'# {title}\n\n{text}', key=key)
    try:
        client.app.state.stock.clip_scorer = clip_fake(world, [])
        for n, tags in enumerate(('ancient harbor ruins', 'coast today beach', 'temple columns ruins')):  # photos for İŞARETLE / ÖNCESONRA
            world.items.append({'id': 8_100_000 + n * 2 + 1, 'tags': tags, 'kind': 'image', 'portrait': False, 'duration': 8})
        narration = client.get(f'/api/projects/{pid}/script').json()['current']['text']
        assert '[' not in narration and 'İMPARATORLUK' not in narration and 'Atlantis' not in narration  # markers never reach narration/subtitles
        view = T.complete(client, pid)
        job = view['job']
        assert job['status'] == 'completed' and view['media_summary']['missing'] == 0, job
        made = {s['selected_media']['source_metadata']['motion']['template'] for s in view['slots']
                if s['selected_media']['provider'] == 'generated' and (s['selected_media'].get('source_metadata') or {}).get('owner_hint')}
        wanted = {'history': {'route', 'empire', 'mark', 'icons', 'dynasty', 'fact'}, 'geography': {'relief', 'ratio', 'beforeafter'},
                  'space': {'route', 'icons', 'fact'}}[topic]
        assert wanted <= made, made
        if topic == 'history':  # a place that is not in the offline list is reported, never guessed
            assert any('Atlantis-Nirgendwo' in w for w in job['progress'].get('marker_warnings', [])), job['progress'].get('marker_warnings')
    finally:
        client.__exit__(None, None, None)


def test_every_new_template_renders_a_full_hd_clip(tmp_path):
    from app.channels import DEFAULT_STYLE
    from app.motion.clips import render_clip
    from app.motion.templates_extra import parse
    from app.rendering.tools import discover
    folder = tmp_path / 'stock'; folder.mkdir()
    for name, colour in (('a.jpg', (200, 170, 120)), ('b.jpg', (40, 80, 140))):
        (folder / name).write_bytes(jpeg(colour, (1600, 1000)))
    cases = [('route', 'Ninive > Babil > Kudüs'), ('empire', 'Osmanlı 1299-1683'), ('zoom', 'Babil'), ('mark', 'Die Säulen'),
             ('beforeafter', 'Antiker Hafen | Heutige Küste'), ('icons', '10000 asker'), ('ratio', '%40 Küste'),
             ('dynasty', 'Davud > Süleyman > Rehavam, Yeroboam'), ('fact', 'Babil surları iki araba genişliğindeydi.')]
    for kind, value in cases:
        spec = parse(kind, value, language='tr')
        if kind == 'mark': spec['data']['image'] = 'a.jpg'
        if kind == 'beforeafter': spec['data']['images'] = ['a.jpg', 'b.jpg']
        path, scene, engine = render_clip(folder, spec, DEFAULT_STYLE, 1.0, .6, language='tr', bridge=object())
        assert engine == 'local' and path.stat().st_size > 1000, kind  # always the local renderer (never OpenMontage)
        assert scene['width'] == 1920 and scene['height'] == 1080
    from app.motion.raster import MapLayer, Pictures, draw_frame
    spec = parse('empire', 'Assyrien 911-612 v. Chr.', language='de')
    from app.motion import templates
    scene = templates.build(spec, DEFAULT_STYLE, 6., 3., 'de')
    base = Image.new('RGB', (1920, 1080), scene['background'])
    frame = draw_frame(scene, 5.9, base, {i: MapLayer(e['props']) for i, e in enumerate(scene['elements']) if e['type'] == 'map'}, Pictures())
    assert len(set(frame.resize((64, 36)).getdata())) > 20  # never an empty frame
    assert discover().get('ffmpeg')


def test_marker_errors_are_plain_turkish_and_places_are_offline():
    from app.motion.templates_extra import MarkerError, parse
    from app.motion.places import find, country_name
    with pytest.raises(MarkerError) as error:
        parse('route', 'Atlantis-Nirgendwo > Mu-Kontinent')
    assert 'bulunamadı' in error.value.message
    with pytest.raises(MarkerError):
        parse('ratio', 'viel Wasser')
    assert find('Kudüs')['name'] == 'Jerusalem' and find('Byzanz')['name'] == 'Istanbul' and find('Ninova')['modern'].startswith('Mosul')
    assert find('Hierosolyma')['name'] == 'Jerusalem'  # ancient ↔ modern names (GeoNames)
    assert country_name(find('Köln'), 'de') == 'Deutschland' and country_name(find('Köln'), 'tr') == 'Almanya'
    assert find('Kennedy Space Center')['name'] == 'Cape Canaveral'  # never a small town that shares one word


def test_suggestions_stay_within_a_quarter_of_the_scenes():
    from app.scripts.query_refine import suggest_infographics
    narr = ['Im Kolosseum fanden bis zu 50000 Zuschauer Platz.', 'Rund 71 % der Erde sind mit Wasser bedeckt.',
            'Die Armee zog von Ninive nach Jerusalem.', 'Zwischen 1945 und 1991 änderte sich alles.', 'Es war ein dunkler Tag.',
            'Der Wind wehte.', 'Die Nacht kam.', 'Alle schliefen.']
    blocks = [{'narration': n, 'entities': [], 'media_type': 'stock_video'} for n in narr]
    suggest_infographics(blocks)
    suggested = [b for b in blocks if b.get('motion_suggested')]
    assert 1 <= len(suggested) <= 2 and all(b['media_type'] == 'motion_graphic' for b in suggested)
