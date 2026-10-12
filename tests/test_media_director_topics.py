"""Acceptance loop for “Medyayı Tamamla”: six 3-minute topics, realistic fakes.

Pexels/Pixabay answer through httpx.MockTransport with JSON shaped like their
official API responses, so the real provider parsing, caching and download
code runs. Each topic gets a different hard situation: provider error,
timeout, no results, all portrait, few results, all results already used.
Claude is an in-memory fake that judges candidates from their tags, so we
can check that nothing unapproved is ever used. No network, no cost.
"""
from contextlib import closing
import hashlib
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.stock.download import Downloader
from fake_anthropic import FakeAnthropic, message
from test_production import scene as base_scene
from test_scripts import FakeProvider, HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}
MP4 = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom'
JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00'
STOP = {'the', 'a', 'of', 'in', 'on', 'and', 'with', 'at', 'for', 'to', 'from', 'by', 'an', 'old', 'view'}

# theme: (query, alternatives, must_show, library tags)
TOPICS = {
    'bermuda': {'topic': 'Das Bermuda-Dreieck', 'scenario': 'provider_error', 'shots': 4, 'themes': [
        ('stormy atlantic ocean waves', ['dark sea storm', 'ocean waves aerial'], 'stormy ocean water', 'ocean storm waves sea'),
        ('cargo ship at sea', ['ship sailing ocean', 'freighter waves'], 'ship on the ocean', 'ship sea cargo vessel'),
        ('vintage navy airplane flying', ['propeller plane sky', 'old aircraft flight'], 'old airplane in the sky', 'airplane propeller sky flight'),
        ('nautical map compass', ['old sea chart', 'compass navigation table'], 'map or compass', 'map compass chart navigation'),
        ('florida coastline aerial', ['miami beach aerial', 'caribbean island coast'], 'coast seen from above', 'coast aerial beach island'),
        ('ship radar screen', ['radio operator vintage', 'ship bridge instruments'], 'radar or ship instruments', 'radar instruments bridge radio')],
        'sentences': ['Im Dezember 1945 verschwanden fünf Flugzeuge der US Navy über dem Atlantik.',
                      'Das Gebiet zwischen Florida, Bermuda und Puerto Rico gilt seitdem als rätselhaft.',
                      'Schwere Stürme entstehen hier schnell und ohne lange Vorwarnung.',
                      'Viele Schiffe kreuzen diese Route jeden Tag ohne jedes Problem.',
                      'Kompasse zeigen in dieser Region manchmal leicht abweichende Werte.',
                      'Versicherer sehen hier kein höheres Risiko als auf anderen Meeren.']},
    'navigation': {'topic': 'Wie Flugzeuge navigieren', 'scenario': 'timeout', 'shots': 5, 'themes': [
        ('airplane cockpit instruments', ['pilot cockpit display', 'flight deck panel'], 'cockpit instruments', 'cockpit instruments panel pilot'),
        ('gps satellite orbit', ['satellite space earth', 'navigation satellite'], 'satellite in space', 'satellite space orbit earth'),
        ('airport control tower', ['air traffic control', 'tower radar screen'], 'control tower or radar', 'tower control radar airport'),
        ('airplane flying above clouds', ['jet clouds sunset', 'plane wing clouds'], 'airplane in the sky', 'airplane clouds sky jet'),
        ('runway landing lights', ['plane landing night', 'airport runway approach'], 'runway or landing', 'runway landing lights airport'),
        ('pilot using tablet map', ['flight plan chart', 'navigation map screen'], 'navigation map', 'map navigation chart screen')],
        'sentences': ['Ein moderner Jet kennt seine Position auf wenige Meter genau.',
                      'Früher navigierten Piloten mit Funkfeuern am Boden.',
                      'Heute senden mehr als 30 Satelliten ständig Zeitsignale zur Erde.',
                      'Im Cockpit vergleicht der Computer mehrere Quellen gleichzeitig.',
                      'Fällt ein System aus, übernimmt sofort ein zweites.',
                      'Bei der Landung führt ein Leitstrahl das Flugzeug zur Piste.']},
    'tribes': {'topic': 'Isolierte Völker', 'scenario': 'no_results', 'shots': 2, 'themes': [
        ('uncontacted tribe rainforest', ['amazon village aerial', 'remote jungle people'], 'dense rainforest', 'rainforest jungle trees'),
        ('remote island beach', ['north sentinel island', 'tropical island aerial'], 'remote island', 'island beach tropical'),
        ('amazon river aerial', ['jungle river canoe', 'river rainforest'], 'river in the jungle', 'river amazon jungle'),
        ('traditional hut thatched', ['village hut forest', 'straw hut'], 'traditional hut', 'hut village thatched'),
        ('bow and arrow hunting', ['handmade bow', 'arrow archery traditional'], 'bow and arrow', 'bow arrow hunting'),
        ('anthropologist field notes', ['researcher notebook jungle', 'field research map'], 'researcher or notes', 'notes research notebook')],
        'sentences': ['Auf der Erde leben noch etwa 100 Gruppen ohne Kontakt zur Außenwelt.',
                      'Die meisten von ihnen wohnen tief im Regenwald des Amazonas.',
                      'Viele Staaten verbieten jeden Besuch, um Krankheiten zu verhindern.',
                      'Ein einfacher Schnupfen kann für sie tödlich sein.',
                      'Forscher beobachten die Gruppen nur aus großer Entfernung.',
                      'Ihre Lebensweise zeigt, wie anpassungsfähig Menschen sind.']},
    'rome': {'topic': 'Das antike Rom', 'scenario': 'all_portrait', 'shots': 5, 'themes': [
        ('roman colosseum', ['colosseum rome aerial', 'ancient arena ruins'], 'colosseum', 'colosseum rome arena'),
        ('roman forum ruins', ['ancient columns rome', 'temple ruins italy'], 'ancient ruins', 'ruins forum columns'),
        ('roman aqueduct', ['stone aqueduct arches', 'ancient bridge arches'], 'aqueduct arches', 'aqueduct arches stone'),
        ('roman soldier reenactment', ['legionary armor', 'roman helmet shield'], 'roman soldier', 'soldier legionary armor'),
        ('ancient coins closeup', ['roman coin museum', 'old gold coins'], 'ancient coins', 'coins coin ancient'),
        ('marble statue emperor', ['roman bust museum', 'marble sculpture'], 'marble statue', 'statue marble bust')],
        'sentences': ['Rom wuchs von einem kleinen Dorf zu einem Weltreich.',
                      'Um das Jahr 100 lebten in der Stadt rund eine Million Menschen.',
                      'Aquädukte brachten täglich frisches Wasser aus den Bergen.',
                      'Im Kolosseum fanden bis zu 50000 Zuschauer Platz.',
                      'Die Legionen sicherten Grenzen von Britannien bis Ägypten.',
                      'Viele Straßen der Römer werden noch heute genutzt.']},
    'deepsea': {'topic': 'Leben in der Tiefsee', 'scenario': 'few_results', 'shots': 3, 'themes': [
        ('deep sea anglerfish', ['bioluminescent fish', 'deep ocean creature'], 'deep sea fish', 'fish anglerfish deep'),
        ('jellyfish glowing dark', ['bioluminescent jellyfish', 'jellyfish deep water'], 'jellyfish', 'jellyfish glowing'),
        ('submarine underwater lights', ['research submersible', 'rov underwater robot'], 'submersible', 'submarine submersible underwater'),
        ('hydrothermal vent', ['black smoker ocean', 'volcanic seafloor'], 'seafloor vent', 'vent seafloor smoker'),
        ('dark ocean depth', ['deep blue water', 'underwater darkness'], 'dark deep water', 'ocean deep dark water'),
        ('giant squid tentacles', ['squid underwater', 'octopus deep sea'], 'squid or octopus', 'squid octopus tentacles')],
        'sentences': ['Unterhalb von 1000 Metern dringt kein Sonnenlicht mehr ins Meer.',
                      'Viele Tiere erzeugen dort ihr eigenes Licht.',
                      'Der Druck ist hundertmal höher als an der Oberfläche.',
                      'Forscher erkunden die Tiefe mit ferngesteuerten Robotern.',
                      'An heißen Quellen am Meeresboden leben ganze Ökosysteme.',
                      'Jedes Jahr entdecken Biologen neue Arten.']},
    'blackholes': {'topic': 'Schwarze Löcher', 'scenario': 'all_used', 'shots': 4, 'themes': [
        ('black hole space', ['galaxy space animation', 'stars night sky'], 'space or stars', 'space stars galaxy'),
        ('galaxy spiral', ['milky way night', 'nebula space'], 'galaxy or stars', 'space stars galaxy'),
        ('telescope observatory', ['radio telescope dish', 'observatory dome night'], 'telescope', 'telescope observatory'),
        ('star explosion supernova', ['bright star space', 'stars night sky'], 'stars', 'space stars galaxy'),
        ('physicist chalkboard', ['equations blackboard', 'scientist writing formula'], 'equations', 'equations chalkboard'),
        ('night sky timelapse', ['stars moving sky', 'milky way timelapse'], 'night sky', 'space stars galaxy')],
        'sentences': ['Ein Schwarzes Loch ist ein Ort, an dem die Schwerkraft alles festhält.',
                      'Nicht einmal Licht kann ihm entkommen.',
                      'Im Jahr 2019 zeigte ein Foto zum ersten Mal einen solchen Schatten.',
                      'Acht Teleskope auf der ganzen Welt arbeiteten dafür zusammen.',
                      'Im Zentrum unserer Galaxie sitzt ein besonders schweres Exemplar.',
                      'Es ist etwa vier Millionen Mal schwerer als die Sonne.']}}


def words(text):
    return {w for w in re.findall(r'[a-z]+', text.lower()) if w not in STOP and len(w) > 2}


class World:
    """Fake stock library + provider HTTP behaviour for one topic."""
    def __init__(self, key, data):
        self.key, self.data, self.scenario = key, data, data['scenario']
        self.requests, self.items = [], []
        uid = int(hashlib.sha256(key.encode()).hexdigest()[:6], 16)
        noise = ['dog park running', 'barber shop haircut', 'city traffic night', 'office meeting laptop']
        for t, (_, _, _, tags) in enumerate(data['themes']):
            count = {'few_results': 1, 'no_results': 0}.get(self.scenario, 4)
            for n in range(count):
                for kind in ('video', 'image'):
                    self.items.append({'id': uid + t * 100 + n * 2 + (kind == 'image'), 'tags': f'{tags} m{t}{n}{kind[0]}', 'kind': kind,
                                       'portrait': self.scenario == 'all_portrait' and kind == 'video', 'duration': 8 + 3 * n})
        if self.scenario == 'all_used':  # every query returns the same three media
            self.items = [i for i in self.items if 'space stars galaxy' in i['tags']][:3]
            for i in self.items: i['duration'] = 40  # long clips: different parts may be reused
        self.noise = [{'id': uid + 5000 + i, 'tags': tag, 'kind': kind, 'portrait': False, 'duration': 15}
                      for i, tag in enumerate(noise) for kind in ('video', 'image')]

    def match(self, query, kind):
        if self.scenario == 'all_used':
            return [i for i in self.items if i['kind'] == kind]
        q = words(query)
        hits = [i for i in self.items if i['kind'] == kind and q & words(i['tags'])]
        return hits + [n for n in self.noise if n['kind'] == kind][:2]

    def handler(self, request):
        host, path = request.url.host, request.url.path
        provider = 'pexels' if 'pexels' in host else 'pixabay'
        kind = 'video' if 'videos' in path else 'image'
        query = request.url.params.get('query') or request.url.params.get('q')
        self.requests.append((provider, kind, query))
        if self.scenario == 'provider_error' and provider == 'pexels':
            return httpx.Response(500, json={'error': 'internal'})
        if self.scenario == 'timeout' and provider == 'pixabay':
            raise httpx.ReadTimeout('synthetic timeout', request=request)
        hits = self.match(query, kind)
        if provider == 'pexels':
            return httpx.Response(200, json={'videos' if kind == 'video' else 'photos': [pexels(i) for i in hits]})
        return httpx.Response(200, json={'hits': [pixabay(i) for i in hits]})


def pexels(i):
    w, h = (1080, 1920) if i['portrait'] else (1920, 1080)
    slug = i['tags'].replace(' ', '-')
    if i['kind'] == 'video':
        return {'id': i['id'], 'width': w, 'height': h, 'duration': i['duration'], 'url': f'https://www.pexels.com/video/{slug}-{i["id"]}/',
                'image': f'https://images.pexels.com/videos/{i["id"]}/preview-0.jpg', 'user': {'name': 'Synthetic', 'url': 'https://www.pexels.com/@synthetic'},
                'video_files': [{'link': f'https://videos.pexels.com/video-files/{i["id"]}/hd.mp4', 'file_type': 'video/mp4', 'width': w, 'height': h}],
                'video_pictures': [{'id': n, 'nr': n, 'picture': f'https://images.pexels.com/videos/{i["id"]}/pictures/preview-{n}.jpg'} for n in range(4)]}
    return {'id': i['id'], 'width': 4000, 'height': 2667, 'url': f'https://www.pexels.com/photo/{slug}-{i["id"]}/', 'alt': i['tags'],
            'photographer': 'Synthetic', 'photographer_url': 'https://www.pexels.com/@synthetic',
            'src': {'large2x': f'https://images.pexels.com/photos/{i["id"]}/large.jpeg', 'medium': f'https://images.pexels.com/photos/{i["id"]}/medium.jpeg'}}


def pixabay(i):
    w, h = (1080, 1920) if i['portrait'] else (1920, 1080)
    base = {'id': i['id'] + 900000, 'pageURL': f'https://pixabay.com/videos/id-{i["id"]}/', 'tags': i['tags'].replace(' ', ', '),
            'user': 'synthetic', 'user_id': 7}
    if i['kind'] == 'video':
        return {**base, 'duration': i['duration'], 'videos': {'large': {'url': f'https://cdn.pixabay.com/video/{i["id"]}_large.mp4', 'width': w, 'height': h,
                                                                       'thumbnail': f'https://cdn.pixabay.com/video/{i["id"]}_large.jpg'}}}
    return {**base, 'pageURL': f'https://pixabay.com/photos/id-{i["id"]}/', 'imageWidth': 4000, 'imageHeight': 2667,
            'largeImageURL': f'https://pixabay.com/get/{i["id"]}_1280.jpg', 'previewURL': f'https://cdn.pixabay.com/photo/{i["id"]}_150.jpg'}


class Director:
    """Fake Claude: writes the topic script/plan and judges media by tags."""
    def __init__(self, data):
        self.data, self.script, self.approved, self.calls = data, FakeProvider(), {}, []

    def __call__(self, request):
        answer = self.answer(request)
        # Realistic usage: ~4 characters per text token, ~300 tokens per
        # 640x360 preview image, plus the system prompt.
        content = request['messages'][0]['content']
        blocks = content if isinstance(content, list) else [{'type': 'text', 'text': content}]
        text = sum(len(b.get('text', '')) for b in blocks) + len(request.get('system', ''))
        images = sum(b['type'] == 'image' for b in blocks)
        output = answer.content[-1].text
        answer.usage.input_tokens, answer.usage.output_tokens = text // 4 + 300 * images, len(output) // 4 + 20
        return answer

    def answer(self, request):
        self.calls.append(request)
        content = request['messages'][0]['content']
        if isinstance(content, list):
            return self.judge(content)
        fmt = request['output_config'].get('format')
        if fmt and 'issues' in fmt['schema']['properties']:  # YouTube language check: echo, nothing to fix
            return message(json.dumps({**json.loads(content.rsplit('\n', 1)[1]), 'issues': []}))
        if fmt and fmt['schema'].get('required') == ['titles']:  # shorten over-long titles
            return message(json.dumps({'titles': [t[:90].rsplit(' ', 1)[0] for t in content.split('TITLES:\n', 1)[1].splitlines()]}))
        if fmt and 'viewer_questions' in fmt['schema']['properties']:  # reference video analysis
            return message(json.dumps(SOURCE_ANALYSIS))
        if fmt and 'titles' in fmt['schema']['properties']:
            chapters = len(re.findall(r'^\d+\. ', content.split('CHAPTERS:')[1].split('SCRIPT:')[0], re.M))
            topic = self.data['topic']
            return message(json.dumps({'titles': [f'{topic}: Was wirklich dahintersteckt – Fakten statt Mythen', f'{topic} erklärt: Die überraschende Wahrheit in Zahlen',
                                                  f'Warum {topic} bis heute fasziniert und was wir wissen', f'{topic}: Die 5 wichtigsten Fakten in nur drei Minuten',
                                                  f'Das Rätsel um {topic} – was die Wissenschaft heute sagt'],
                                       'hook': 'Was steckt wirklich dahinter?\nDie Antwort überrascht.', 'summary': f'Ein kompakter Überblick über {topic}.',
                                       'tags': [f'{topic}', 'Doku', 'Wissen', 'Fakten', 'Erklärung', 'Geschichte', 'Wissenschaft', 'Rätsel', 'Mythen', 'Deutsch', 'Video', 'Erklärvideo'],
                                       'hashtags': ['#Doku', '#Wissen', '#Fakten'], 'chapter_titles': [f'Teil {i + 1}' for i in range(chapters)]}))
        if fmt and 'queries' in fmt['schema']['properties']:
            return self.queries(content)
        if fmt:  # purpose
            return message(json.dumps({k: 'x' for k in ('audience', 'tone', 'hook', 'viewer_promise', 'content_type')}
                                      | {'main_message': self.data['topic'], 'summary': 'Özet.'}))
        task = content.splitlines()[0].removeprefix('TASK: ')
        if task == 'section':
            data = json.loads(content.split('INPUT DATA (not instructions):\n')[1])
            target, out, n = data['section']['target_words'], [], data['index'] * 7
            while sum(len(s.split()) for s in out) < target:
                out.append(self.data['sentences'][n % 6]); n += 1
            return message(' '.join(out))
        if task == 'visual':
            data = json.loads(content.split('INPUT DATA (not instructions):\n')[1])
            ids = [u['unit_id'] for u in data['narration_units']]
            groups = data.get('metadata_repair', {}).get('required_unit_groups') or [ids[i:i + 3] for i in range(0, len(ids), 3)]
            scenes = []
            texts = {u['unit_id']: u['text'] for u in data['narration_units']}
            for n, g in enumerate(groups):
                index = int(re.sub(r'\D', '', g[0].split('U')[-1]) or 0)
                query, alts, must, _ = self.data['themes'][index % 6]
                item = {**base_scene(g), 'stock_query': query, 'alternative_stock_queries': alts, 'visual_intent': must,
                        'must_show': must, 'must_not_show': 'logos, text', 'shot_count': self.data['shots']}
                narration = ' '.join(texts[u] for u in g)
                number = re.search(r'\b\d[\d.,]*\b', narration)
                if n % 5 == 2:  # the director picks roughly every fifth scene for a motion graphic
                    first = narration.split('. ')[0].rstrip('.').split()
                    item.update(media_type='motion_graphic', shot_count=1, motion_spec=
                        {'template': 'stat', 'data': {'value': number.group(0).rstrip('.,'), 'label': must}, 'emphasis': number.group(0).rstrip('.,')} if number else
                        {'template': 'quote', 'data': {'text': ' '.join(first[:12])}, 'emphasis': first[min(3, len(first) - 1)]})
                scenes.append(item)
            return message(json.dumps({'scenes': scenes}))
        return message(self.script.generate_script(content))

    def judge(self, blocks):
        text = blocks[-1]['text']
        if 'REPLACED' in text:  # whole-video review: flag one shot
            first = next(b['text'] for b in blocks if b['type'] == 'text' and b['text'].startswith('Slot '))
            return message(json.dumps({'replace': [{'slot': int(first.split()[1]), 'reason': 'Komşu çekime çok benziyor.'}]}))
        must = words(re.search(r'MUST show: (.*)', text).group(1))
        verdicts = []
        for b in blocks:
            m = b['type'] == 'text' and re.match(r'Candidate (\d+):.*Provider tags: (.*)', b['text'])
            if not m: continue
            tags = m.group(2)
            ok = bool(must & words(tags))
            if ok: self.approved.setdefault(text.split('\n')[0], set()).add(tags)
            verdicts.append({'candidate': int(m.group(1)), 'score': 8 if ok else 2, 'approved': ok,
                             'reason': 'Sahnedeki konuyu açıkça gösteriyor.' if ok else 'Konuyla ilgisiz.'})
        self.approved_tags = {t for s in self.approved.values() for t in s}
        return message(json.dumps({'verdicts': verdicts}), input_tokens=2500, output_tokens=200)

    def queries(self, text):
        must = re.search(r'MUST show: (.*)', text).group(1)
        themes = self.data['themes']  # the owner's [GÖRSEL] note can replace the planned MUST show
        theme = next((t for t in themes if t[2] == must), None) or next((t for t in themes if t[0] in must), themes[0])
        if 'BROADER' in text:
            return message(json.dumps({'queries': [theme[3].split()[0] + ' landscape', must, 'documentary atmosphere']}))
        return message(json.dumps({'queries': [theme[3], theme[3].split()[-1] + ' closeup', must + ' cinematic']}))


SOURCE_ANALYSIS = {'summary': 'Bermuda Üçgeni’ndeki kayıpları ve olası açıklamaları anlatıyor.', 'topic': 'Bermuda Üçgeni',
                   'sections': [{'title': 'Gizem', 'summary': 'Kaybolan uçaklar'}, {'title': 'Açıklamalar', 'summary': 'Hava ve okyanus akıntıları'}, {'title': 'Sonuç', 'summary': 'Gerçek risk düşük'}],
                   'hook': {'type': 'şaşırtıcı soru', 'description': 'Neden bu kadar çok gemi kayboldu?'}, 'pacing': 'hızlı', 'tone': 'merak uyandıran',
                   'ending': 'efsaneyi çürüten kapanış', 'facts': [{'claim': '1945’te beş uçak kayboldu', 'doubtful': False, 'note': ''},
                                                                   {'claim': 'Bölgede manyetik anomali uçakları düşürür', 'doubtful': True, 'note': 'kanıt yok'}],
                   'why_it_works': ['Merak uyandıran başlık', 'Yüksek beğeni oranı'], 'title_strategy': 'Soru + gizem kelimesi',
                   'audience_reactions': ['İzleyiciler sonucu sevdi'], 'viewer_questions': ['Bugün hâlâ tehlikeli mi?']}


class FakeGemini:
    """Gemini generateContent over httpx.MockTransport, answered by the same
    fake director so both engines face identical decisions."""
    def __init__(self, director):
        self.director, self.requests, self.fail = director, [], None

    def handler(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        if self.fail:
            failure = self.fail(len(self.requests))
            if failure: return failure
        parts = body['contents'][0]['parts']
        last = parts[-1]['text']
        if 'generationConfig' in body:
            prompt, schema = last.split('\n\nReturn ONLY one JSON object (no Markdown) that matches this JSON Schema: ')
            schema = json.loads(schema)
            self.video_urls = getattr(self, 'video_urls', []) + [p['file_data']['file_uri'] for p in parts if 'file_data' in p]
            blocks = [{'type': 'image'} if 'inlineData' in p else {'type': 'text', 'text': p['text']} for p in parts[:-1] if 'file_data' not in p]
            props = schema['properties']
            if 'verdicts' in props or 'replace' in props:
                content = blocks + [{'type': 'text', 'text': prompt}]
            else:
                content = prompt
            fake = {'messages': [{'content': content}], 'output_config': {'format': {'schema': schema}}}
        else:
            fake = {'messages': [{'content': last}], 'output_config': {}}
        text = self.director(fake).content[-1].text
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [{'text': text}]}, 'finishReason': 'STOP'}]})


def gemini_429(free=False):
    violation = {'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier' if free else 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'}
    return httpx.Response(429, headers={'Retry-After': '7'}, json={'error': {'code': 429, 'details': [
        {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [violation]}]}})


def fast_motion(scene, output, ffmpeg):
    import subprocess
    subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=0x101823:s=1920x1080:r=30:d={scene["duration"]}',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(output)], check=True)


def build(tmp_path, monkeypatch, key, engine='gemini'):
    monkeypatch.setattr('app.motion.clips.raster_render', fast_motion)
    # These tests exercise the choosing logic on a synthetic two-provider library;
    # Commons and the Pexels switch have their own tests (test_wikimedia.py).
    monkeypatch.setattr('app.stock.providers.ACTIVE', ('pexels', 'pixabay'))
    data = TOPICS[key]
    world, claude = World(key, data), Director(data)
    if engine == 'claude':
        fake = FakeAnthropic(claude)
        monkeypatch.setattr('app.providers.claude._client', lambda k: fake)
    else:
        fake = FakeGemini(claude)
        from app.providers import gemini
        class Patched(gemini.GeminiScriptProvider):
            def __init__(self, api_key, model='', *, transport=None):
                super().__init__(api_key, model, transport=httpx.MockTransport(fake.handler))
        monkeypatch.setattr('app.providers.factory.GeminiScriptProvider', Patched)
    client = TestClient(create_app(tmp_path / key), headers=HEADERS).__enter__()
    s = client.app.state.settings
    for name, value in (('pexels', 'synthetic-pexels-key-1111'), ('pixabay', 'synthetic-pixabay-key-2222')):
        assert client.put(f'/api/settings/{name}', json={'api_key': value}, headers=SETTINGS).status_code == 200
    if engine == 'claude':
        assert client.put('/api/settings/claude', json={'api_key': 'sk-ant-synthetic-topic-key-0001', 'default_engine': True}, headers=SETTINGS).status_code == 200
    else:
        s.save('gemini', {'api_key': 'synthetic-gemini-key-3333'})
        s.record_gemini_models(s.gemini_config(), ['gemini-test-model'])
        s.save('gemini', {'model': 'gemini-test-model'})
    s.save('general', {'ai_visual_check': True})  # the AI looks at the candidates (off by default)
    assert s.ai_engine() == engine
    client.app.state.stock.ai_sleep = lambda seconds, service: client.app.state.stock.__dict__.setdefault('slept', []).append(seconds)
    pid = client.post('/api/projects', json={'name': key, 'topic': data['topic'], 'language': 'de', 'target_duration_minutes': 3}).json()['id']
    r = client.post(f'/api/projects/{pid}/director/run', json={'cost_confirmed': True})
    assert r.status_code == 202, r.text
    client.app.state.director.futures[pid].result(timeout=60)
    state = client.get(f'/api/projects/{pid}/director').json()['state']
    assert state['status'] == 'done' and state['provider'] == engine, state
    if engine == 'gemini':  # the director's scene notes are requested from Gemini too
        visual = [r['contents'][0]['parts'][-1]['text'] for r in fake.requests if r['contents'][0]['parts'][-1]['text'].startswith('TASK: visual')]
        assert visual and all('must_show' in text for text in visual)
    stock = client.app.state.stock
    from app.stock import providers
    stock.factory = lambda name, settings: {'pexels': providers.PexelsStockProvider, 'pixabay': providers.PixabayStockProvider}[name](
        settings.stock_config(name)['api_key'], transport=httpx.MockTransport(world.handler))
    stock.downloader = Downloader(client.app.state.projects, transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={'Content-Type': 'video/mp4' if request.url.path.endswith('.mp4') else 'image/jpeg'},
                                       content=(MP4 if request.url.path.endswith('.mp4') else JPEG) + str(request.url).encode())))
    stock.fetch_thumbnail = lambda url: JPEG + url.encode()
    return client, pid, world, claude, fake


def complete(client, pid, slot_id=None):
    base = f'/api/projects/{pid}/production/stock'
    view = client.get(base).json()
    url = f'{base}/slots/{slot_id}/jobs' if slot_id else f'{base}/jobs'
    r = client.post(url, json={'plan_id': view['plan_id'], 'revision': view['revision'], 'action': 'reselect' if slot_id else 'complete_media'})
    assert r.status_code == 202, r.text
    client.app.state.stock.futures[r.json()['job_id']].result(timeout=120)
    return client.get(base).json()


def check(client, pid, claude, view):
    """Finish conditions 1-4 for one project; returns the table row."""
    slots = view['slots']
    assert view['job']['status'] == 'completed', view['job']                         # (4) never an error
    summary = view['media_summary']
    assert summary['missing'] == 0 and summary['missing_seconds'] == 0, summary      # (1)
    usage = {}
    for s in slots:
        m = s['selected_media']
        assert s['status'] == 'complete' and m, s
        if m['provider'] == 'generated' or s.get('continuation_of'):
            continue
        assert s['ai_review']['approved'] and m['description'] in claude.approved_tags, (s['order'], m['description'])  # (2)
        usage.setdefault((m['provider'], m['media_type'], m['media_id']), []).append(s)
    for k, group in usage.items():                                                   # (3)
        if len(group) > 1:
            assert k[1] == 'video', k
            spans = sorted(((s.get('segment_start') or 0), (s.get('segment_start') or 0) + s['duration']) for s in group)
            assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), (k, spans)
    return summary


@pytest.mark.parametrize('engine', ['gemini', 'claude'])
@pytest.mark.parametrize('key', list(TOPICS))
def test_three_minute_topic_fills_every_slot_with_approved_or_generated_media(key, engine, tmp_path, monkeypatch):
    client, pid, world, claude, fake = build(tmp_path, monkeypatch, key, engine)
    try:
        with closing(sqlite3_connect(client)) as c:
            before = (c.execute('SELECT text FROM script_versions WHERE project_id=?', (pid,)).fetchall(),
                      c.execute('SELECT plan_json FROM project_production WHERE project_id=?', (pid,)).fetchall())
        view = complete(client, pid)
        summary = check(client, pid, claude, view)
        with closing(sqlite3_connect(client)) as c:                                  # (5) narration source untouched
            after = (c.execute('SELECT text FROM script_versions WHERE project_id=?', (pid,)).fetchall(),
                     c.execute('SELECT plan_json FROM project_production WHERE project_id=?', (pid,)).fetchall())
        assert before == after
        # A second press keeps everything and does not search again.
        requests = len(world.requests)
        again = complete(client, pid)
        assert again['media_summary']['filled'] == summary['filled'] and len(world.requests) == requests
        # Per-slot re-selection never leaves the slot empty.
        target = next(s for s in again['slots'] if s['selected_media']['provider'] != 'generated' and not s.get('continuation_of')) if summary['videos'] + summary['images'] else again['slots'][0]
        view = complete(client, pid, target['slot_id'])
        check(client, pid, claude, view)
        usage = client.get(f'/api/projects/{pid}/ai-usage').json()
        diag = client.get(f'/api/projects/{pid}/production/stock/diagnostics')
        assert diag.status_code == 200 and 'attachment' in diag.headers['content-disposition']
        assert 'synthetic-pexels-key' not in diag.text and 'sk-ant' not in diag.text
        calls = len(fake.requests)
        print(f'\nRESULT {engine} {key}: {summary["text"]} · motion {summary["motion_percent"]}% of time · AI calls {calls} · paid ${usage["total_cost_usd"]:.4f}')
        # Motion only where the director planned it or no stock fits: with a
        # stock-rich library the screen's 25% warning never shows.
        if key in ('bermuda', 'rome'):
            assert summary['motion_slot_percent'] <= 25 and not any('motion grafik (hedef' in w for w in again['warnings'])
        assert not any((s.get('director') or {}).get('stage') == 'motion_balance' for s in again['slots'])  # no forced motion
        planned = [s for s in again['slots'] if (s.get('director') or {}).get('stage') == 'motion_planned']
        assert planned and all(s['selected_media']['media_type'] == 'video' for s in planned)
        if engine == 'gemini': assert usage['total_cost_usd'] == 0  # nothing billed through Claude
    finally:
        client.__exit__(None, None, None)


def sqlite3_connect(client):
    import sqlite3
    return sqlite3.connect(client.app.state.database)


def no_fallback_motion(view):
    """Nothing became motion because the AI was down: only director-planned motion."""
    return all((s.get('director') or {}).get('stage') in (None, 'motion_planned') or s['selected_media']['provider'] != 'generated'
               for s in view['slots'] if s.get('selected_media'))


def ai_never_blamed(view):
    """Motion only where no stock fitted, never “because the AI was unreachable”."""
    return not any('ulaşılamadı' in (s.get('message') or '') for s in view['slots'])


def local_slots(view):
    return [s for s in view['slots'] if s.get('selected_media') and s['selected_media']['provider'] != 'generated' and not s.get('continuation_of')
            and not (s.get('ai_review') or {}).get('approved')]


def test_claude_outage_continues_locally_and_next_press_rechecks(tmp_path, monkeypatch):
    import anthropic
    from fake_anthropic import api_error
    client, pid, world, claude, fake = build(tmp_path, monkeypatch, 'deepsea', 'claude')
    try:
        healthy = fake.responder
        fake.responder = lambda request: api_error(anthropic.APIConnectionError, 0)
        view = complete(client, pid)
        job = view['job']
        assert job['status'] == 'completed' and view['media_summary']['missing'] == 0, job  # never stops
        assert 'Claude şu anda yanıt vermiyor' in job['progress']['message'] and 'Medya seçimi durmadı' in job['progress']['message']
        assert client.app.state.stock.slept  # temporary error: waited and retried before going local
        assert ai_never_blamed(view)
        assert local_slots(view) and all(s['needs_ai_review'] for s in local_slots(view))  # “yapay zekâ onayı yok”
        fake.responder = healthy
        view = complete(client, pid)  # one click: the AI looks at them
        summary = check(client, pid, claude, view)
        assert summary['videos'] + summary['images'] > 0 and not local_slots(view)
    finally:
        client.__exit__(None, None, None)


def test_gemini_quota_mid_job_continues_locally_and_rechecks(tmp_path, monkeypatch):
    client, pid, world, claude, fake = build(tmp_path, monkeypatch, 'bermuda')
    try:
        start = len(fake.requests)
        fake.fail = lambda n: gemini_429(free=True) if n > start + 6 else None  # daily free quota runs out mid-job
        view = complete(client, pid)
        job = view['job']
        assert job['status'] == 'completed' and view['media_summary']['missing'] == 0, job
        assert 'günlük ücretsiz kotası doldu' in job['progress']['message']
        assert job['progress']['ai_failure']['category'] == 'free_quota_exhausted'  # the real error is kept for the diagnostics file
        assert ai_never_blamed(view)  # no slot fell to motion because of the AI
        approved = {s['slot_id']: s['selected_media']['media_id'] for s in view['slots']
                    if (s.get('ai_review') or {}).get('approved') and not s.get('continuation_of')}
        assert approved and local_slots(view)  # AI-approved before the quota ran out, local after
        assert view['media_summary']['unchecked'] == len(local_slots(view))
        assert not client.app.state.stock.__dict__.get('slept')  # a daily quota is not waited out
        diag = client.get(f'/api/projects/{pid}/production/stock/diagnostics').json()
        assert diag['jobs'][0]['progress']['ai_failure']['category'] == 'free_quota_exhausted'
        assert set(client.app.state.settings.gemini_exhausted()) == {'gemini-test-model'}  # skipped until the Pacific-midnight reset
        fake.fail = None
        assert client.post('/api/settings/gemini/quota-reset', headers=SETTINGS).status_code == 200  # “next day”
        view = complete(client, pid)  # the re-check
        summary = check(client, pid, claude, view)
        changed = [k for k, v in approved.items() if next(s for s in view['slots'] if s['slot_id'] == k)['selected_media']['media_id'] != v]
        assert len(changed) <= 1  # AI-approved picks stay (the whole-video look may swap one near-duplicate shot)
        assert summary['videos'] > 0 and not local_slots(view)
    finally:
        client.__exit__(None, None, None)


def test_gemini_minute_limit_that_does_not_clear_goes_local_after_short_waits(tmp_path, monkeypatch):
    client, pid, world, claude, fake = build(tmp_path, monkeypatch, 'rome')
    try:
        start = len(fake.requests)
        fake.fail = lambda n: gemini_429() if n > start + 3 else None
        view = complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert 'kota/hız sınırına takıldı' in view['job']['progress']['message']
        assert len(client.app.state.stock.slept) == 3 and ai_never_blamed(view)
    finally:
        client.__exit__(None, None, None)


def test_gemini_per_minute_limit_waits_and_still_chooses_stock(tmp_path, monkeypatch):
    client, pid, world, claude, fake = build(tmp_path, monkeypatch, 'rome')
    try:
        fake.fail = lambda n: gemini_429() if n % 3 == 0 else None  # every third request hits the minute limit
        view = complete(client, pid)
        summary = check(client, pid, claude, view)
        assert summary['videos'] > 0 and summary['cards'] == 0
        assert client.app.state.stock.slept and set(client.app.state.stock.slept) == {7}  # waited Retry-After, then retried
    finally:
        client.__exit__(None, None, None)


def test_without_any_ai_engine_media_is_chosen_locally(tmp_path, monkeypatch):
    client, pid, world, claude, fake = build(tmp_path, monkeypatch, 'rome')
    try:
        monkeypatch.setattr(client.app.state.settings, 'ai_engine', lambda: None)
        before = len(fake.requests)
        view = complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert view['job']['progress']['local_mode'] == 'no_engine' and len(fake.requests) == before
        assert local_slots(view)
    finally:
        client.__exit__(None, None, None)
