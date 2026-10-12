"""Infographics: numbers written as words count as spoken, the owner's
markers ([HARİTA], [SAYI], [ÇİZELGE], [KARŞILAŞTIR], [LİSTE]) become the
matching template directly (even when the AI is down), a plain text card is
the last choice (≤30% of motion slots). Six topics with marked texts.
No network: stock providers and Gemini are mocked."""
import json
import re

import pytest

import test_media_director_topics as T
import test_media_relevance_paste as R
from app.motion.numbers import is_spoken, spoken_numbers
from app.motion.places import lookup, spoken_places
from app.motion.templates import MotionError, from_narration, validate
from app.scripts.paste import clean


def test_numbers_written_as_words_are_read():
    assert 1945 in spoken_numbers('Im Dezember neunzehnhundertfünfundvierzig verschwanden fünf Flugzeuge.')
    assert spoken_numbers('vierzig Prozent der Schiffe') == {40}
    assert 2001 in spoken_numbers('zweitausendeins') and 340000 in spoken_numbers('dreihundertvierzigtausend Menschen')
    assert 1000000 in spoken_numbers('rund eine Million Menschen') and 23 in spoken_numbers('dreiundzwanzig')
    assert 1945 in spoken_numbers('In nineteen forty-five') and 1945 in spoken_numbers('mil novecientos cuarenta y cinco')
    assert 1945 in spoken_numbers('mille neuf cent quarante-cinq') and 90 in spoken_numbers('quatre-vingt-dix')
    assert 1945 in spoken_numbers('bin dokuz yüz kırk beş') and 40 in spoken_numbers('yüzde kırk')
    assert not spoken_numbers('Ein Schiff und eine Frau')  # articles are not numbers
    assert is_spoken('1945', 'neunzehnhundertfünfundvierzig') and is_spoken('40', 'vierzig Prozent') and not is_spoken('41', 'vierzig Prozent')


def test_validation_accepts_words_and_other_place_names():
    text = 'Im Dezember neunzehnhundertfünfundvierzig verschwand Flug neunzehn im Bermuda-Dreieck. Vierzig Prozent sagen nein.'
    assert validate({'template': 'stat', 'data': {'value': '1945', 'label': ''}}, text)['data']['value'] == '1945'
    assert validate({'template': 'stat', 'data': {'value': '40 %', 'label': ''}}, text)
    assert validate({'template': 'timeline', 'data': {'events': [{'date': '1945', 'label': 'Flug'}, {'date': '19', 'label': 'x'}]}}, text)
    assert validate({'template': 'map', 'data': {'place': 'Bermuda Triangle', 'lat': 25, 'lon': -71, 'label': ''}}, text)
    with pytest.raises(MotionError):
        validate({'template': 'stat', 'data': {'value': '1962', 'label': ''}}, text)  # still never invented
    with pytest.raises(MotionError):
        validate({'template': 'map', 'data': {'place': 'Tokio', 'lat': 35, 'lon': 139, 'label': ''}}, text)
    assert validate({'template': 'stat', 'data': {'value': '1962', 'label': ''}}, text, trusted=True)  # the owner's own marker


def test_narration_motion_prefers_numbers_dates_places_over_text():
    assert from_narration('Im Dezember neunzehnhundertfünfundvierzig startete Flug neunzehn.')['data']['value'] == '1945'
    assert from_narration('Heute fahren vierzig Prozent der Schiffe dort.')['data']['value'] == '40 %'
    assert from_narration('Von 1945 bis 1962 verschwanden Schiffe, 1991 auch.')['template'] == 'timeline'
    spec = from_narration('Das Gebiet liegt zwischen Florida und Puerto Rico.')
    assert spec['template'] == 'map' and (spec['data']['lat'], spec['data']['lon']) == lookup('Florida')[:2]
    assert from_narration('Niemand weiß, was wirklich geschah.')['template'] == 'quote'
    assert [p[0] for p in spoken_places('Rom eroberte Karthago am Mittelmeer.')] == ['Rom', 'Karthago', 'Mittelmeer']


def test_new_markers_are_read_in_any_spelling_and_never_spoken():
    raw = ('Rom wuchs schnell. [ÇİZELGE: 753 v. Chr., 146 v. Chr.] Karthago fiel. [karşılaştır: Rom | Karthago] '
           '[LISTE: Stürme; Strömungen] Ende. [Cizelge: 1945, 1962] [liste: a; b]')
    result = clean(raw)
    assert result['text'] == 'Rom wuchs schnell. Karthago fiel. Ende.' and not result['warnings']
    assert [m['type'] for m in result['markers']] == ['timeline', 'compare', 'list', 'timeline', 'list']
    assert 'ÇİZELGE' in clean('[QUATSCH: x] Satz.')['warnings'][0]  # the warning lists the new markers


def test_quote_is_the_last_choice_and_capped_at_thirty_percent():
    from app.stock.director_media import MediaDirector, QUOTE_SHARE
    assert QUOTE_SHARE == .30
    d = MediaDirector.__new__(MediaDirector)
    quote = {'provider': 'generated', 'media_type': 'video', 'source_metadata': {'motion': {'template': 'quote'}}}
    stat = {'provider': 'generated', 'media_type': 'video', 'source_metadata': {'motion': {'template': 'stat'}}}
    d.slots = [{'selected_media': quote}, {'selected_media': stat}, {'selected_media': stat}]
    assert d.quote_full()  # 2 of 4 would be text cards
    d.slots = [{'selected_media': quote}] + [{'selected_media': stat}] * 6
    assert not d.quote_full()  # 2 of 8 is fine
    d.card_texts = set()
    scene = {'start_estimate': 0, 'end_estimate': 10, 'entities': [],
             'narration_text': 'Niemand weiß, was wirklich geschah. Später kamen achtzig Schiffe vorbei.'}
    assert d.motion_spec({'estimated_start': 0, 'estimated_end': 3}, scene)['template'] == 'stat'  # not the nearer quote


MARKED = {
    'bermuda': ['Im Dezember neunzehnhundertfünfundvierzig verschwanden fünf Flugzeuge über dem Atlantik. [SAYI: 1945]',
                'Das Gebiet zwischen Florida, Bermuda und Puerto Rico gilt seitdem als rätselhaft. [HARİTA: Bermuda Triangle]',
                'Danach folgten weitere Fälle. [ÇİZELGE: 1945, 1962, 1991]',
                'Experten nennen drei Ursachen. [LİSTE: Stürme; Strömungen; Menschliche Fehler]',
                'Statistisch ist das Gebiet nicht gefährlicher. [KARŞILAŞTIR: Bermuda-Dreieck | Andere Meere]'],
    'navigation': ['Heute senden mehr als dreißig Satelliten ständig Zeitsignale zur Erde. [SAYI: 30]',
                   'Die Technik hat sich stark verändert. [ÇİZELGE: 1960, 1995, 2020]',
                   'Piloten nutzen mehrere Hilfen. [LİSTE: Funkfeuer; Satelliten; Leitstrahl]',
                   'Früher und heute ist der Unterschied groß. [KARŞILAŞTIR: Funkfeuer | GPS]'],
    'tribes': ['Auf der Erde leben noch etwa hundert Gruppen ohne Kontakt zur Außenwelt. [SAYI: 100]',
               'Die meisten von ihnen wohnen tief im Regenwald des Amazonas. [HARİTA: Amazonas]',
               'Eine Gruppe lebt auf einer Insel im Indischen Ozean. [HARİTA: North Sentinel]',
               'Der Schutz hat klare Regeln. [LİSTE: Kein Besuch; Kein Kontakt; Beobachtung aus der Ferne]'],
    'rome': ['Rom wuchs von einem kleinen Dorf zu einem Weltreich. [HARİTA: Rom]',
             'Um das Jahr hundert lebten in der Stadt rund eine Million Menschen. [SAYI: eine Million]',
             'Die Geschichte der Stadt ist lang. [ÇİZELGE: 753 v. Chr., 146 v. Chr., 476]',
             'Rom und Karthago kämpften lange um das Mittelmeer. [KARŞILAŞTIR: Rom: 1000000 | Karthago: 400000]'],
    'deepsea': ['Unterhalb von tausend Metern dringt kein Sonnenlicht mehr ins Meer. [SAYI: 1000 m]',
                'Der tiefste Punkt liegt im Pazifik. [HARİTA: Marianengraben]',
                'Das Leben dort ist hart. [LİSTE: Hoher Druck; Kälte; Dunkelheit]'],
    'blackholes': ['Im Jahr zweitausendneunzehn zeigte ein Foto zum ersten Mal einen solchen Schatten. [SAYI: 2019]',
                   'Es ist etwa vier Millionen Mal schwerer als die Sonne. [KARŞILAŞTIR: Sonne: 1 | Sagittarius A*: 4000000]',
                   'Forscher brauchten dafür viel Technik. [LİSTE: Acht Teleskope; Atomuhren; Supercomputer]'],
}
KIND_TEMPLATE = {'SAYI': 'stat', 'HARİTA': 'map', 'ÇİZELGE': 'timeline', 'KARŞILAŞTIR': 'compare', 'LİSTE': 'list'}


def marked_text(key, words=390):
    data = T.TOPICS[key]
    paragraphs = [' '.join(MARKED[key][i:i + 2]) for i in range(0, len(MARKED[key]), 2)]
    out, n = [], 0
    while sum(len(p.split()) for p in paragraphs + out) < words:
        out.append(data['sentences'][n % 6]); n += 1
    paragraphs += [' '.join(out[i:i + 4]) for i in range(0, len(out), 4)]
    paragraphs[0] = '[GÖRSEL: ' + data['themes'][0][0] + '] ' + paragraphs[0]
    return '# ' + data['topic'] + '\n\n' + '\n\n'.join(paragraphs)


def owner_slots(view):
    return [s for s in view['slots'] if (s.get('director') or {}).get('stage') == 'motion_owner']


def test_marked_scenes_become_infographics_even_when_the_ai_quota_is_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(R, 'pasted_text', lambda data: marked_text('bermuda'))
    client, pid, world, fake = R.build(tmp_path, monkeypatch, 'bermuda')
    try:
        fake.fail = lambda n: T.gemini_429(free=True)  # no AI at all during Medyayı Tamamla
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0  # never stops
        assert view['job']['progress']['local_mode'] == 'down'
        templates = sorted(s['selected_media']['source_metadata']['motion']['template'] for s in owner_slots(view))
        assert templates == ['compare', 'list', 'map', 'stat', 'timeline']  # every marker drawn, none as a text card
        pin = next(s for s in owner_slots(view) if s['selected_media']['source_metadata']['motion']['template'] == 'map')
        assert (pin['selected_media']['source_metadata']['motion']['data']['lat'], pin['selected_media']['source_metadata']['motion']['data']['lon']) == (25.0, -71.0)
        stock = [s for s in view['slots'] if s['selected_media']['provider'] != 'generated']
        assert stock and all(s.get('needs_ai_review') or s.get('continuation_of') for s in stock)  # chosen locally, marked for the AI
    finally:
        client.__exit__(None, None, None)


ROWS = {}


@pytest.mark.parametrize('key', list(T.TOPICS))
def test_six_marked_topics(key, tmp_path, monkeypatch):
    monkeypatch.setattr(R, 'pasted_text', lambda data: marked_text(key))
    client, pid, world, fake = R.build(tmp_path, monkeypatch, key)
    try:
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed', view['job']
        summary = view['media_summary']
        assert summary['missing'] == 0
        wanted = sorted(KIND_TEMPLATE[m.group(1)] for line in MARKED[key] for m in re.finditer(r'\[(SAYI|HARİTA|ÇİZELGE|KARŞILAŞTIR|LİSTE):', line))
        got = sorted(s['selected_media']['source_metadata']['motion']['template'] for s in owner_slots(view))
        assert got == wanted, (key, got, wanted)
        templates = summary['motion_templates']
        motion = sum(templates.values())
        if key in ('bermuda', 'rome'):  # stock-rich topics: text cards stay the exception
            assert templates.get('quote', 0) <= max(1, round(.3 * motion)), templates
        elif templates.get('quote', 0) > .3 * motion:  # stock-poor, number-free sentences: said plainly on screen
            assert any('yazı kartı' in w for w in view['warnings'])
        for s in view['slots']:
            if s['selected_media']['provider'] in ('pexels', 'pixabay'):
                assert (s.get('ai_review') or {}).get('score', 0) >= 7
        ROWS[key] = {'slots': summary['total'], 'stock_video': summary['videos'], 'image': summary['images'],
                     **{k: templates.get(t, 0) for k, t in (('number', 'stat'), ('map', 'map'), ('timeline', 'timeline'), ('compare', 'compare'), ('list', 'list'), ('text', 'quote'))},
                     'cards': summary['cards'], 'merged': summary['merged'], 'missing': summary['missing'], 'relevance': summary['relevance_average'],
                     'motion_share': summary['motion_slot_percent']}
        print(f'\nROW {key} ' + json.dumps(ROWS[key], ensure_ascii=False))
    finally:
        client.__exit__(None, None, None)
