"""Period/place rules for every video: the setting is read from the narration,
CLIP and the provider tags drop footage that contradicts it, and neutral
footage (landscape, sky, texture) stands in when nothing fits."""
import numpy as np
import pytest

from app.stock import setting as S
import test_fast_media as F
import test_media_director_topics as T


@pytest.mark.parametrize('text,topic,label,region', [
    ('Im Jahr 605 v. Chr. herrschte Nebukadnezar über Babylon. Händler am Euphrat verkauften Getreide.', '', 'antik Mezopotamya', 'mesopotamia'),
    ('In den 1960er Jahren veränderte sich Amerika. Die Menschen in New York demonstrierten.', '', "1960'lar ABD", 'usa'),
    ('Der Ozean ist tief. Wale singen in der Tiefsee.', '', 'günümüz okyanus', 'ocean'),
    ('Babil, MÖ 1750 yılında Hammurabi tarafından yönetildi.', '', 'antik Mezopotamya', 'mesopotamia'),
    ('1453 yılında İstanbul fethedildi.', '', 'Orta Çağ Anadolu', 'anatolia'),
])
def test_period_and_place_from_the_text(text, topic, label, region):
    found = S.infer([text], topic)
    assert found['label'] == label and found['regions'][0] == region


def test_counts_are_not_years():
    assert S.infer(['Rund 1200 Kilometer weit zogen 10000 Soldaten.'])['era'] is None


def test_penalties_follow_the_setting():
    babylon = S.infer(['Nebukadnezar ließ Babylon am Euphrat ausbauen, 600 v. Chr.'])
    texts = {p['text']: p['kind'] for p in S.penalties(babylon, 'a photo of market traders')}
    assert texts['people shopping in a modern store'] == 'anachronism'
    assert texts['moai stone head statues on Easter Island'] == 'place'
    assert texts['a cartoon drawing of {subject}'] == 'style' and texts['a 3D computer rendering of {subject}'] == 'style'
    sixties = S.infer(['In den 1960er Jahren fuhren in New York viele Autos.'])
    texts = {p['text'] for p in S.penalties(sixties, 'a photo of street')}
    assert 'a smartphone or a computer screen' in texts and 'power lines and electric poles' not in texts
    assert 'the New York City skyline' not in texts  # a place the video names is never a wrong place
    assert S.penalties(S.infer(['Wale singen im Ozean.']), 'a photo of whale') == []  # present-day nature: nothing to rule out


def test_tags_without_clip():
    babylon = S.infer(['Babylon am Euphrat, 600 v. Chr.'])
    assert S.tag_conflict(babylon, ' people shopping in a mall ', 'pixabay')[0] == 'anachronism'
    assert S.tag_conflict(babylon, ' moai statues easter island ', 'pixabay')[0] == 'place'
    assert S.tag_conflict(babylon, ' 3d skeleton render ', 'pixabay')[0] == 'style'
    assert S.tag_conflict(babylon, ' ancient ruins desert ', 'pixabay') is None
    assert S.tag_conflict(babylon, ' car museum relief ', 'wikimedia') is None  # archive captions may name modern things


def test_worker_marks_the_period_conflict():
    from app.integrations.openmontage.visual_engine import setting_conflict, setting_penalties
    penalties = setting_penalties([{'kind': 'anachronism', 'text': 'people shopping in a modern store', 'label': 'modern alışveriş'},
                                   {'kind': 'style', 'text': 'a cartoon drawing of {subject}', 'label': 'karikatür'}], 'a photo of market, ancient Babylon')
    assert penalties[1]['text'] == 'a cartoon drawing of market, ancient Babylon'
    target = np.array([.22, .23, .21])
    shop = np.array([[.29, .18], [.30, .19], [.28, .18]])
    assert setting_conflict(target, shop, penalties)['label'] == 'modern alışveriş'
    fine = np.array([[.17, .20], [.18, .21], [.17, .20]])
    assert setting_conflict(np.array([.28, .29, .27]), fine, penalties) is None


def babylon_text():
    return ('# Babylon\n\nIm Jahr 605 vor Christus regierte Nebukadnezar in Babylon. Auf dem Markt am Euphrat handelten Kaufleute mit Getreide. '
            'Die Mauern der Stadt waren gewaltig. Händler verkauften Stoffe und Gewürze. Priester stiegen auf die Zikkurat. '
            'Die Bauern bewässerten ihre Felder mit Kanälen. Das Reich wuchs über viele Jahrzehnte.')


def test_media_job_drops_conflicting_footage_and_shows_the_setting(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, babylon_text())
    try:
        wrong = set()
        for n, tags in enumerate(('people shopping mall market', 'moai statues easter island', 'cartoon market traders')):
            item = {'id': 8_300_000 + n * 2 + 1, 'tags': tags, 'kind': 'video', 'portrait': False, 'duration': 12}
            world.items.insert(0, item); wrong |= {str(item['id']), str(item['id'] + 900000)}
        asked = []
        good = F.clip_fake(world, [])
        def score(descriptor, items, penalties=()):
            asked.append([p['kind'] for p in penalties])
            return good(descriptor, items)
        client.app.state.stock.clip_scorer = score
        view = T.complete(client, pid)
        job = view['job']
        assert job['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert job['progress']['setting']['label'] == 'antik Mezopotamya'
        assert asked and all({'anachronism', 'style', 'place'} <= set(kinds) for kinds in asked)
        assert not any(s["selected_media"]["media_id"] in wrong for s in view["slots"]), [(s["selected_media"]["provider"], s["selected_media"].get("description"), s.get("local_review")) for s in view["slots"] if s["selected_media"]["media_id"] in wrong]
        plan = client.get(f'/api/projects/{pid}/production').json()['plan']
        assert plan['setting']['label'] == 'antik Mezopotamya'
        assert 'Dönem ve yer' in client.get('/static/stock.js').text and 'Dönem ve yer' in client.get('/static/production.js').text
    finally:
        client.__exit__(None, None, None)


def test_clip_conflict_is_rejected_with_a_turkish_reason(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, babylon_text())
    try:
        good = F.clip_fake(world, [])
        hit = set()
        def score(descriptor, items, penalties=()):
            out = good(descriptor, items)
            for n, (key, _) in enumerate(items):  # every third candidate “looks like” a modern shop
                if n % 3 == 0 and descriptor != 'a photo of ancient Mesopotamia':
                    out[key] = {'verdict': 'mismatch', 'score': 2, 'conflict': {'kind': 'anachronism', 'label': 'modern alışveriş'}}; hit.add(key)
            return out
        client.app.state.stock.clip_scorer = score
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        chosen = {':'.join((s['selected_media']['provider'], s['selected_media']['media_type'], str(s['selected_media']['media_id']))) for s in view['slots']}
        assert hit and not chosen & hit
        assert view['job']['progress']['setting_rejected'].get('anachronism', 0) >= 1
        reasons = [j.get('reason', '') for s in view['slots'] for j in (s.get('director') or {}).get('judged', [])]
        assert any('dönemle çelişiyor (modern alışveriş)' in r for r in reasons)
    finally:
        client.__exit__(None, None, None)


def test_neutral_footage_when_nothing_fits(tmp_path, monkeypatch):
    text = ('# Alltag\n\nDie Kaufleute handelten mit Getreide und Wein. Die Priester beteten still im Tempel. '
            'Die Bauern arbeiteten hart auf den Feldern. Die Kinder spielten mit kleinen Steinen. '
            'Die Frauen webten bunte Stoffe für den Winter. Die Soldaten bewachten die Tore der Stadt.')
    client, pid, world, fake = F.make(tmp_path, monkeypatch, text)  # topic “Das antike Rom”: ancient Rome
    try:
        world.items.insert(0, {'id': 8_400_001, 'tags': 'old stone texture wall', 'kind': 'video', 'portrait': False, 'duration': 60})
        def score(descriptor, items, penalties=()):  # nothing matches the sentences; the neutral stone texture does
            return {key: ({'verdict': 'uncertain', 'score': 6} if key.split(':')[2] in ('8400001', '9300001') and 'old stone texture' in descriptor
                          else {'verdict': 'mismatch', 'score': 2}) for key, _ in items}
        client.app.state.stock.clip_scorer = score
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert view['job']['progress']['setting']['label'] == 'antik Roma'
        neutral = [s for s in view['slots'] if (s.get('director') or {}).get('stage') == 'neutral']
        assert neutral, [(st.get('result'), st.get('judged'), (s.get('director') or {}).get('rejected')) for s in view['slots'] for st in (s.get('director') or {}).get('steps', []) if st['stage'] == 'neutral'][:2]
        assert all('Nötr görüntü' in s['message'] and s['selected_media']['media_id'] in ('8400001', '9300001') for s in neutral)
    finally:
        client.__exit__(None, None, None)


def test_earlier_picks_are_checked_once_and_conflicts_chosen_again(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch, babylon_text())
    try:
        good = F.clip_fake(world, [])
        client.app.state.stock.clip_scorer = lambda descriptor, items: good(descriptor, items)
        with monkeypatch.context() as older:  # a run from before the period check
            older.setattr(S, 'infer', lambda texts, topic='': S.describe(None, None, []))
            older.setattr(S, 'for_scene', lambda setting, text: setting)
            first = T.complete(client, pid)
        assert not any(s.get('setting_check') for s in first['slots']), [s.get('setting_check') for s in first['slots']]
        stock = [s for s in first['slots'] if s['selected_media']['provider'] in ('pexels', 'pixabay') and not s.get('continuation_of')]
        target = stock[0]['selected_media']
        name = f'{target["provider"]}:{target["media_type"]}:{target["media_id"]}'
        rechecked = []
        def score(descriptor, items, penalties=()):
            out = good(descriptor, items)
            if name in out and penalties:
                rechecked.append(descriptor)
                out[name] = {'verdict': 'mismatch', 'score': 2, 'conflict': {'kind': 'place', 'label': 'Paskalya Adası'}}
            return out
        client.app.state.stock.clip_scorer = score
        second = T.complete(client, pid)
        assert second['job']['status'] == 'completed' and second['media_summary']['missing'] == 0
        assert rechecked and second['job']['progress']['setting_reselected'] >= 1
        assert not any(s['selected_media']['media_id'] == target['media_id'] and s['selected_media']['provider'] == target['provider'] for s in second['slots'])
        assert all((s.get('setting_check') or {}).get('label') == 'antik Mezopotamya' for s in second['slots']
                   if s['selected_media']['provider'] in ('pexels', 'pixabay') and not s.get('continuation_of'))
        rechecked.clear()
        third = T.complete(client, pid)
        assert third['job']['status'] == 'completed' and 'setting_reselected' not in third['job']['progress']  # checked once, remembered
    finally:
        client.__exit__(None, None, None)
