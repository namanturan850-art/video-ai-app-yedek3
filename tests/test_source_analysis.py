"""Reference video analysis: YouTube Data API (mocked) + Gemini (mocked) →
“Kaynak analizi” → adaptation brief for an original script. No network."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.integrations.youtube_data import YouTubeDataClient, duration_seconds, video_id
from app.main import create_app
from app.source_analysis import NO_YOUTUBE_KEY, PASTE_TRANSCRIPT, TITLE_ONLY
from test_media_director_topics import SOURCE_ANALYSIS
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}
URL = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=12'
TRANSCRIPT = 'In 1945 five planes vanished over the ocean. Some say a magnetic anomaly pulled them down. Scientists disagree strongly.'


class World:
    """Fake Gemini (generateContent) and YouTube Data API v3."""
    def __init__(self, read_video=True):
        self.read_video, self.gemini, self.youtube = read_video, [], []

    def gemini_handler(self, request):
        body = json.loads(request.content); self.gemini.append(body)
        parts = body['contents'][0]['parts']
        if any('file_data' in p for p in parts) and not self.read_video:
            return httpx.Response(400, json={'error': {'code': 400, 'status': 'INVALID_ARGUMENT', 'message': 'Cannot fetch content from the provided URL.'}})
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model', 'parts': [{'text': json.dumps(SOURCE_ANALYSIS)}]}, 'finishReason': 'STOP'}]})

    def youtube_handler(self, request):
        self.youtube.append(request.url)
        if request.url.path.endswith('/videos'):
            return httpx.Response(200, json={'items': [{'snippet': {'title': 'The Bermuda Triangle Mystery SOLVED?', 'description': 'What really happens…', 'tags': ['bermuda', 'mystery'],
                                                                    'channelTitle': 'Docs', 'publishedAt': '2023-01-01T00:00:00Z'},
                                                        'contentDetails': {'duration': 'PT14M3S'}, 'statistics': {'viewCount': '2500000', 'likeCount': '81000', 'commentCount': '9200'}}]})
        return httpx.Response(200, json={'items': [{'snippet': {'topLevelComment': {'snippet': {'textDisplay': f'Comment {i}: is it still dangerous today?', 'likeCount': i * 3}}}} for i in range(100)]})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    world = World()
    from app.providers import gemini
    class Patched(gemini.GeminiScriptProvider):
        def __init__(self, api_key, model='', *, transport=None):
            super().__init__(api_key, model, transport=httpx.MockTransport(lambda r: world.gemini_handler(r)))
    monkeypatch.setattr('app.providers.factory.GeminiScriptProvider', Patched)
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        s = client.app.state.settings
        s.save('gemini', {'api_key': 'synthetic-gemini-key-4444'}); s.record_gemini_models(s.gemini_config(), ['gemini-test-model']); s.save('gemini', {'model': 'gemini-test-model'})
        client.app.state.sources.youtube_factory = lambda key: YouTubeDataClient(key, transport=httpx.MockTransport(world.youtube_handler))
        yield client, world


def project(client, url='', transcript=''):
    pid = client.post('/api/projects', json={'name': 'Bermuda', 'topic': 'Das Bermuda-Dreieck', 'language': 'de', 'reference_url': url}).json()['id']
    if transcript:
        assert client.put(f'/api/projects/{pid}/source/transcript', json={'transcript': transcript}).status_code == 200
    return pid


def key(client):
    assert client.put('/api/settings/youtube', json={'api_key': 'synthetic-youtube-key-5555'}, headers=SETTINGS).status_code == 200


def test_link_analysis_reads_numbers_comments_and_video(setup):
    client, world = setup; key(client)
    pid = project(client, URL)
    view = client.post(f'/api/projects/{pid}/source/analyze').json()
    a = view['analysis']
    assert a['status'] == 'done' and a['mode'] == 'video' and not a['warnings']
    assert a['metadata']['views'] == 2500000 and a['metadata']['duration_seconds'] == 843 and a['comments_used'] == 50
    sent = world.gemini[-1]['contents'][0]['parts']
    assert sent[0] == {'file_data': {'file_uri': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}}  # documented input, nothing downloaded
    prompt = sent[-1]['text']
    assert '[297] Comment 99' in prompt and 'Comment 49:' not in prompt  # 50 most-liked of the ~100 relevant ones
    assert 'synthetic-youtube-key' not in json.dumps(world.gemini)  # YouTube key only goes to Google’s YouTube API
    assert all('key=synthetic-youtube-key-5555' in str(u) for u in world.youtube)
    brief = client.app.state.sources.brief(pid)
    assert 'ADAPT, DO NOT TRANSLATE' in brief and 'DOUBTFUL' in brief and 'manyetik' in brief.split('DOUBTFUL')[1]
    assert 'Bugün hâlâ tehlikeli mi?' in brief and 'Comment' not in brief  # viewer questions yes, raw comments no


def test_transcript_analysis_and_script_never_gets_the_transcript(setup):
    client, world = setup
    pid = project(client, '', TRANSCRIPT)
    view = client.post(f'/api/projects/{pid}/source/analyze').json()
    assert view['analysis']['mode'] == 'transcript' and view['has_transcript']
    parts = world.gemini[-1]['contents'][0]['parts']
    assert not any('file_data' in p for p in parts) and TRANSCRIPT in parts[-1]['text']
    brief = client.app.state.sources.brief(pid)
    assert brief and 'five planes vanished' not in brief and 'magnetic anomaly' not in brief  # no source wording
    # The normal script screen and the director both receive the brief, not the transcript.
    seen = {}
    scripts = client.app.state.scripts
    original = scripts.options
    def capture(payload):
        seen.update(payload); return original(payload)
    scripts.options = capture
    try: scripts.start(pid, {'provider': 'gemini'})
    except Exception: pass
    assert seen.get('reference_notes') == brief and not seen.get('reference_text')
    from app.director import script_payload
    payload = script_payload(client.app.state.projects.get(pid), {'main_message': 'x', 'hook': '', 'viewer_promise': '', 'summary': 'y', 'content_type': 'Doku', 'tone': 'ruhig', 'audience': 'alle'}, 'gemini', brief)
    assert payload['reference_notes'] == brief


def test_no_link_no_transcript_uses_title_only(setup):
    client, world = setup
    pid = project(client)
    view = client.get(f'/api/projects/{pid}/source').json()
    assert view['hint'] == TITLE_ONLY
    view = client.post(f'/api/projects/{pid}/source/analyze').json()
    assert view['analysis']['mode'] == 'title_only' and view['analysis']['warnings'] == [TITLE_ONLY]
    assert not world.gemini and not world.youtube and client.app.state.sources.brief(pid) == ''


def test_without_youtube_key_gemini_continues_with_a_warning(setup):
    client, world = setup
    pid = project(client, URL)
    a = client.post(f'/api/projects/{pid}/source/analyze').json()['analysis']
    assert a['status'] == 'done' and a['mode'] == 'video' and a['metadata'] is None and NO_YOUTUBE_KEY in a['warnings']
    assert not world.youtube


def test_unreadable_link_asks_for_transcript(setup, monkeypatch):
    client, world = setup; key(client); world.read_video = False
    pid = project(client, URL)
    a = client.post(f'/api/projects/{pid}/source/analyze').json()['analysis']
    assert PASTE_TRANSCRIPT in a['warnings'] and a['mode'] == 'metadata' and a['status'] == 'done'  # still learns from title, numbers, comments
    monkeypatch.setattr(client.app.state.settings, 'youtube_key', lambda: '')  # no key and no readable video: nothing to analyse yet
    pid2 = project(client, URL)
    b = client.post(f'/api/projects/{pid2}/source/analyze').json()['analysis']
    assert b['status'] == 'needs_transcript' and PASTE_TRANSCRIPT in b['warnings'] and NO_YOUTUBE_KEY in b['warnings']


def test_youtube_key_connection_test_and_url_parsing(setup):
    client, world = setup; key(client)
    r = client.post('/api/settings/youtube/test', headers=SETTINGS).json()
    assert r['result']['status'] == 'Hazır' and r['settings']['youtube']['has_api_key'] and 'synthetic' not in json.dumps(r)
    assert video_id('https://youtu.be/dQw4w9WgXcQ') == video_id('https://www.youtube.com/shorts/dQw4w9WgXcQ') == 'dQw4w9WgXcQ'
    assert video_id('https://evil.example/watch?v=dQw4w9WgXcQ') is None and duration_seconds('PT1H2M3S') == 3723
    bad = YouTubeDataClient('k', transport=httpx.MockTransport(lambda r: httpx.Response(400, json={'error': {'errors': [{'reason': 'keyInvalid'}]}})))
    with pytest.raises(Exception) as error:
        bad.video('dQw4w9WgXcQ')
    assert error.value.category == 'key_invalid' and 'geçersiz' in str(error.value)
    off = YouTubeDataClient('k', transport=httpx.MockTransport(lambda r: httpx.Response(403, json={'error': {'errors': [{'reason': 'commentsDisabled'}]}})))
    with pytest.raises(Exception) as error:
        off.top_comments('dQw4w9WgXcQ')
    assert error.value.category == 'comments_disabled'


def test_new_project_form_note_and_transcript_field():
    js = open('app/static/projects.js', encoding='utf-8').read()
    assert 'Video analiz edilmez' not in js and 'reference_transcript' in js and 'Transkript (yapıştır' in js and 'Kaynak analizi' in js
