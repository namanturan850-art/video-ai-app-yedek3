"""YouTube card: titles (≤ 97), description, tags (≤ 500 as YouTube counts,
no '#'), one AI language check; thumbnails removed. No network, no upload."""
import json
from pathlib import Path

import pytest

from app.youtube import TAGS_MAX, TITLE_MAX, YouTubeService, clean_tags, cut_title, tags_length
from test_media_director_topics import build, complete


@pytest.fixture
def topic(tmp_path, monkeypatch):
    client, pid, world, claude, fake = build(tmp_path, monkeypatch, 'bermuda', 'gemini')
    complete(client, pid)
    yield client, pid, fake, claude
    client.__exit__(None, None, None)


def prompts(fake, marker):
    return [r['contents'][0]['parts'][-1]['text'] for r in fake.requests if marker in r['contents'][0]['parts'][-1]['text']]


def test_titles_description_chapters_tags_credits_and_language_check(topic):
    client, pid, fake, claude = topic
    view = client.get(f'/api/projects/{pid}/youtube').json()
    assert view['engine'] == 'gemini' and not view['package'] and view['limits'] == {'title': 97, 'tags': 500}
    assert 'layouts' not in view and 'ai_background' not in view  # thumbnail feature removed
    r = client.post(f'/api/projects/{pid}/youtube/text')
    assert r.status_code == 200, r.text
    view = r.json(); p = view['package']
    assert len(p['titles']) == 5 and all(t['length'] <= TITLE_MAX for t in p['titles']) and p['chosen_title'] == p['titles'][0]['text']
    assert view['counts']['title'] == len(p['chosen_title']) and view['counts']['tags'] == tags_length(p['tags']) <= TAGS_MAX
    assert p['tags'] and not any('#' in t for t in p['tags']) and p['hashtags'] == ['#Doku', '#Wissen', '#Fakten']
    d = p['description']
    assert d.startswith('Was steckt wirklich dahinter?\nDie Antwort überrascht.')
    chapters = d.split('Kapitel:\n')[1].split('\n\n')[0].splitlines()
    assert len(chapters) >= 3 and chapters[0].startswith('0:00 ')
    starts = [int(c.split()[0].split(':')[0]) * 60 + int(c.split()[0].split(':')[1]) for c in chapters]
    assert starts == sorted(starts) and all(b - a >= 10 for a, b in zip(starts, starts[1:]))
    assert 'Stockmaterial: Pixabay' in d
    # One language check ran before “ready”; it saw titles, hook, summary, chapter titles and tags (not the timestamps).
    checks = prompts(fake, 'Proofread this YouTube metadata')
    assert len(checks) == 1 and '"tags"' in checks[0] and '0:00' not in checks[0]
    assert p['proofread']['status'] == 'done' and view['ready']
    sent = prompts(fake, 'Prepare YouTube metadata')[-1]
    assert f'AT MOST {TITLE_MAX} characters' in sent and 'NO "#"' in sent and 'thumbnail' not in sent.casefold()
    # Owner edits: '#' removed, too-long title refused, check is marked stale.
    r = client.put(f'/api/projects/{pid}/youtube', json={'chosen_title': 'Mein eigener Titel', 'tags': ['a', '#b', 'c d']}).json()
    assert r['package']['chosen_title'] == 'Mein eigener Titel' and r['package']['tags'] == ['a', 'b', 'c d'] and r['counts']['tags'] == 1 + 1 + 5 + 2
    assert any('#' in n for n in r['notes']) and not r['ready']
    long = client.put(f'/api/projects/{pid}/youtube', json={'chosen_title': 'x' * 98})
    assert long.status_code == 422 and '97' in long.json()['message']
    again = client.post(f'/api/projects/{pid}/youtube/check').json()
    assert again['ready'] and again['package']['chosen_title'] == 'Mein eigener Titel'
    for gone in ('frames', 'thumbnails', 'ai-background'):
        assert client.post(f'/api/projects/{pid}/youtube/{gone}', json={}).status_code in (404, 405)


def test_youtube_counting_rules():
    assert tags_length(['abc']) == 3 and tags_length(['a b', 'c']) == 3 + 2 + 1 + 1  # quotes for spaces, commas count
    tags = clean_tags(['#Bermuda', 'bermuda', 'Bermuda Dreieck', 'x,y', '  ', '##Rätsel '])
    assert tags == ['Bermuda', 'Bermuda Dreieck', 'x', 'y', 'Rätsel']
    many = [f'suchbegriff nummer {i:02}' for i in range(40)]  # 21 chars + 2 quotes each
    kept = clean_tags(many)
    assert tags_length(kept) <= TAGS_MAX and kept == many[:len(kept)] and len(kept) < 40  # weakest (last) dropped first
    assert tags_length(kept + [many[len(kept)]]) > TAGS_MAX
    title = 'Das unglaubliche Rätsel ' * 6
    cut = cut_title(title)
    assert len(cut) <= TITLE_MAX and title.startswith(cut) and title[len(cut)] == ' '  # never inside a word


class Fake:
    def __init__(self, short):
        self.short, self.calls = short, []

    def complete_json(self, purpose, prompt, schema, **kw):
        self.calls.append(purpose)
        return {'titles': self.short}


def test_overlong_title_is_rewritten_shorter_by_ai_then_word_safe():
    long = 'Warum verschwinden im Bermuda-Dreieck seit über hundert Jahren Schiffe und Flugzeuge spurlos im Meer?'
    assert len(long) > TITLE_MAX
    svc = YouTubeService.__new__(YouTubeService)
    ai = Fake(['Warum verschwinden im Bermuda-Dreieck Schiffe und Flugzeuge spurlos?'])
    out = svc.fit_titles(ai, ['Kurz und gut', long], 'de')
    assert ai.calls == ['youtube_title_shorten'] and out == ['Kurz und gut', 'Warum verschwinden im Bermuda-Dreieck Schiffe und Flugzeuge spurlos?']
    stubborn = Fake([long + ' noch länger'])  # AI fails to shorten: word-boundary end, no cut word
    out = svc.fit_titles(stubborn, [long], 'de')[0]
    assert len(out) <= TITLE_MAX and long.startswith(out) and long[len(out)] == ' '


def test_proofread_fixes_are_applied(topic):
    client, pid, fake, claude = topic
    client.post(f'/api/projects/{pid}/youtube/text')
    original = claude.answer
    def answer(request):
        fmt = request.get('output_config', {}).get('format')
        if fmt and 'issues' in fmt['schema']['properties']:
            data = json.loads(request['messages'][0]['content'].rsplit('\n', 1)[1])
            data['titles'][0] = 'Das Rätsel des Bermuda-Dreiecks: Was steckt wirklich dahinter?'
            data['tags'] = ['#Bermuda'] + data['tags'][1:]
            from fake_anthropic import message
            return message(json.dumps({**data, 'issues': ['Başlıktaki dilbilgisi hatası düzeltildi.']}))
        return original(request)
    claude.answer = answer
    view = client.post(f'/api/projects/{pid}/youtube/check').json()
    p = view['package']
    assert p['chosen_title'] == 'Das Rätsel des Bermuda-Dreiecks: Was steckt wirklich dahinter?'
    assert p['proofread']['issues'] == ['Başlıktaki dilbilgisi hatası düzeltildi.'] and p['tags'][0] == 'Bermuda'  # '#' never survives
    assert view['ready']


def test_thumbnail_ui_and_settings_are_gone():
    js = Path('app/static/youtube.js').read_text(encoding='utf-8')
    assert 'Kapak' not in js and 'kapak' not in js and 'thumbnail' not in js.split('\n', 1)[1]
    assert 'thumbnail_ai' not in Path('app/static/image-settings.js').read_text(encoding='utf-8')
    from app.production_settings import ImageSettings
    assert 'thumbnail_ai' not in ImageSettings.model_fields
    assert not hasattr(YouTubeService, 'thumbnails') and not hasattr(YouTubeService, 'frames')
