"""Wikimedia Commons as a stock source (no key) and Pexels switched off.
Only commercially usable licences; author/licence/link kept and written to
the YouTube description; history/museum/map scenes ask Commons first; the
same AI relevance check as every other source. No network: the documented
MediaWiki API answers are mocked."""
import shutil
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

import test_media_director_topics as T
import test_media_relevance_paste as R
from app.main import create_app
from app.stock import providers
from app.stock.download import Downloader
from app.stock.providers import WikimediaStockProvider, commercial_licence
from app.youtube import YouTubeService
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}


def meta(licence, artist='<a href="https://commons.wikimedia.org/wiki/User:Ann">Ann Example</a>', **extra):
    out = {'LicenseShortName': {'value': licence, 'source': 'commons-desc-page'},
           'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by-sa/4.0'},
           'Artist': {'value': artist}, 'ImageDescription': {'value': '<p>Relief of a Roman legion</p>'}}
    out.update({k: {'value': v} for k, v in extra.items()})
    return out


def page(pageid, title, licence, *, mime='image/jpeg', index=1, **extra):
    info = {'url': f'https://upload.wikimedia.org/wikipedia/commons/a/ab/{pageid}.{"webm" if mime == "video/webm" else "jpg"}',
            'descriptionurl': f'https://commons.wikimedia.org/wiki/File:{pageid}', 'width': 4000, 'height': 2667, 'size': 2_000_000,
            'mime': mime, 'mediatype': 'VIDEO' if mime == 'video/webm' else 'BITMAP', 'extmetadata': meta(licence, **extra)}
    if mime == 'video/webm':
        info.update(duration=95.5, thumburl=f'https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/{pageid}.webm/1920px--{pageid}.webm.jpg',
                    thumbwidth=1920, thumbheight=1080, width=1920, height=1080, size=9_000_000)
    else:
        info.update(thumburl=f'https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/{pageid}.jpg/1920px-{pageid}.jpg', thumbwidth=1920, thumbheight=1280)
    return {'pageid': pageid, 'ns': 6, 'title': f'File:{title}', 'index': index, 'imageinfo': [info]}


def test_only_commercially_usable_licences_pass():
    for ok in ('Public domain', 'PD-old', 'CC0', 'CC BY 4.0', 'CC BY-SA 3.0', 'CC BY-SA 2.0 de', 'CC BY 2.5'):
        assert commercial_licence(meta(ok)), ok
    for bad in ('CC BY-NC 2.0', 'CC BY-ND 4.0', 'CC BY-NC-SA 3.0', 'CC BY-NC-ND 4.0', 'GFDL', 'Fair use', 'All rights reserved', ''):
        assert commercial_licence(meta(bad)) is None, bad
    assert commercial_licence(meta('CC BY 4.0', NonFree='true')) is None
    assert commercial_licence(meta('CC BY 4.0', Restrictions='trademarked')) is None


def test_documented_api_request_and_normalisation():
    seen = []
    def handler(request):
        seen.append(request)
        if request.url.params['gsrsearch'].startswith('nothing'):
            return httpx.Response(200, json={'batchcomplete': True})  # no hits: the API sends no 'query'
        pages = [page(11, 'Trajan column relief.jpg', 'CC BY-SA 4.0', index=2), page(12, 'Legion relief NC.jpg', 'CC BY-NC 2.0', index=1),
                 page(13, 'Roman soldiers video.webm', 'CC BY 3.0', mime='video/webm', index=3)]
        if 'filetype:video' in request.url.params['gsrsearch']: pages = [pages[2]]
        else: pages = pages[:2]
        return httpx.Response(200, json={'batchcomplete': True, 'query': {'pages': pages}})
    provider = WikimediaStockProvider('', transport=httpx.MockTransport(handler))
    images = provider.search('roman legion relief', 'image')
    request = seen[0]
    assert request.url.host == 'commons.wikimedia.org' and request.url.path == '/w/api.php'
    params = dict(request.url.params)
    assert params['action'] == 'query' and params['generator'] == 'search' and params['gsrnamespace'] == '6' and params['prop'] == 'imageinfo'
    assert params['gsrsearch'] == 'roman legion relief filetype:bitmap' and 'extmetadata' in params['iiprop'] and 'key' not in params
    assert request.headers['user-agent'].startswith('AIVideoStudio/') and 'github.com' in request.headers['user-agent']
    assert [m['media_id'] for m in images] == ['11']  # the NC file never becomes a candidate
    m = images[0]
    assert m['provider'] == 'wikimedia' and m['download_url'].startswith('https://upload.wikimedia.org/') and (m['width'], m['height']) == (1920, 1280)
    assert m['creator_name'] == 'Ann Example' and m['source_metadata']['license'] == 'CC BY-SA 4.0' and m['source_metadata']['author'] == 'Ann Example'
    assert m['page_url'] == 'https://commons.wikimedia.org/wiki/File:11' and 'Trajan column relief' in m['description'] and 'Roman legion' in m['description']
    video = provider.search('roman soldiers', 'video')[0]
    assert video['duration'] == 60 and video['source_metadata']['original_mime'] == 'video/webm'  # first minute only
    assert provider.search('nothing at all', 'image') == []
    provider.search('roman legion relief', 'image', page=2)
    assert seen[-1].url.params['gsroffset'] == '30'


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg needed for the WebM → MP4 conversion')
def test_webm_is_converted_to_mp4_on_download(tmp_path):
    webm = tmp_path / 'clip.webm'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=640x360:d=3:r=25', '-c:v', 'libvpx', '-b:v', '300k', str(webm)], check=True)
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        pid = client.post('/api/projects', json={'name': 'Rom', 'language': 'de'}).json()['id']
        media = page(13, 'Roman soldiers video.webm', 'CC BY 3.0', mime='video/webm')
        provider = WikimediaStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'query': {'pages': [media]}})))
        candidate = provider.search('roman soldiers', 'video')[0]
        agents = []
        def cdn(request):
            agents.append(request.headers.get('user-agent'))
            return httpx.Response(200, headers={'Content-Type': 'video/webm'}, content=webm.read_bytes())
        saved = Downloader(client.app.state.projects, transport=httpx.MockTransport(cdn)).download(pid, candidate)
        assert saved['local_path'].endswith('.mp4') and saved['content_type'] == 'video/mp4'
        path = client.app.state.projects._path(pid) / saved['local_path']
        assert path.read_bytes()[4:8] == b'ftyp' and saved['file_size'] == path.stat().st_size
        assert agents[0].startswith('AIVideoStudio/')  # the CDN is told who is downloading


def wiki_handler(world, log):
    """Commons answers like the documented API: for every query one relevant CC BY-SA file,
    one relevant but NC file (must never be used) and one irrelevant CC0 file."""
    def handler(request):
        search = request.url.params['gsrsearch'].replace(' filetype:bitmap', '').replace(' filetype:video', '')
        log.append(search)
        if 'filetype:video' in request.url.params['gsrsearch']:
            return httpx.Response(200, json={'batchcomplete': True})
        base = 4_000_000 + (abs(hash(search)) % 100_000) * 10
        return httpx.Response(200, json={'query': {'pages': [
            page(base + 1, f'{search} museum relief.jpg', 'CC BY-SA 4.0', index=1),
            page(base + 2, f'{search} engraving.jpg', 'CC BY-NC-SA 2.0', index=2),
            page(base + 3, 'Office meeting laptop.jpg', 'CC0', index=3)]}})
    return handler


def test_commons_in_medyayi_tamamla_same_relevance_check_and_youtube_sources(tmp_path, monkeypatch):
    client, pid, world, fake = R.build(tmp_path, monkeypatch, 'rome')
    monkeypatch.setattr('app.stock.providers.ACTIVE', ('pixabay', 'wikimedia'))  # the real setting: Pexels off
    try:
        assert client.put('/api/settings/pexels', json={'api_key': 'synthetic-pexels-key-1111'}, headers=SETTINGS).status_code == 200  # a saved key
        log, stock = [], client.app.state.stock
        wiki = httpx.MockTransport(wiki_handler(world, log))
        stock.factory = lambda name, settings: (providers.WikimediaStockProvider('', transport=wiki) if name == 'wikimedia' else
                                                providers.PixabayStockProvider(settings.stock_config(name)['api_key'], transport=httpx.MockTransport(world.handler)))
        stock.downloader = Downloader(client.app.state.projects, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={'Content-Type': 'video/mp4' if request.url.path.endswith('.mp4') else 'image/jpeg'},
                                           content=(T.MP4 if request.url.path.endswith('.mp4') else T.JPEG) + str(request.url).encode())))
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert not any(provider == 'pexels' for provider, _, _ in world.requests)  # Pexels is off even with a key
        assert log  # Commons was searched
        commons = [s for s in view['slots'] if s['selected_media']['provider'] == 'wikimedia']
        assert commons, 'no Commons media chosen for an ancient-Rome video'
        for s in commons:
            m = s['selected_media']
            assert s['ai_review']['score'] >= 7  # same 7/10 relevance rule
            assert m['source_metadata']['license'] == 'CC BY-SA 4.0' and int(m['media_id']) % 10 == 1  # never the NC or the irrelevant file
            assert m['media_type'] == 'image' and m['creator_name'] == 'Ann Example'
        # YouTube description: “Görsel kaynakları” (Bildquellen) with title, author, licence and link.
        credits = client.app.state.youtube.credits(pid)
        sources = [c for c in credits if c.get('license') and c['provider'] == 'Wikimedia Commons']  # (a map infographic adds a GeoNames line)
        assert sources and all(c['url'].startswith('https://commons.wikimedia.org/wiki/File:') for c in sources)
        text = YouTubeService.description({'hook': 'Hook', 'summary': 'Summary', 'credits': credits}, 'de')
        assert 'Bildquellen:' in text and 'Ann Example, CC BY-SA 4.0 (Wikimedia Commons) https://commons.wikimedia.org/wiki/File:' in text
        assert 'Görsel kaynakları:' in YouTubeService.description({'credits': credits}, 'tr')
    finally:
        client.__exit__(None, None, None)


def test_history_scenes_ask_commons_first_and_settings_show_sources(tmp_path):
    from app.stock.director_media import MediaDirector, historic
    rome = {'visual_intent': 'ancient roman forum ruins', 'narration_text': 'Rom wuchs zu einem Weltreich.'}
    space = {'visual_intent': 'galaxy spiral night sky', 'narration_text': 'Schwarze Löcher sind schwer.'}
    assert historic(rome) and historic({'visual_intent': 'old nautical map', 'narration_text': ''}) and historic({'narration_text': 'Im Jahr 1492 …'})
    assert not historic(space)
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        assert client.put('/api/settings/pixabay', json={'api_key': 'synthetic-pixabay-key-2222'}, headers=SETTINGS).status_code == 200
        d = MediaDirector.__new__(MediaDirector); d.service, d.unavailable = client.app.state.stock, {}
        assert d.providers(rome) == ['wikimedia', 'pixabay', 'nasa'] and d.providers(space) == ['pixabay', 'wikimedia', 'nasa']  # NASA: no key either
        view = client.get('/api/settings', headers=SETTINGS).json()
        assert view['wikimedia']['status'] == 'Hazır' and 'Anahtar gerekmez' in view['wikimedia']['message']
        assert view['pexels']['status'] == 'Kullanılmıyor' and 'API anahtarı' not in view['pexels']['message']  # empty key: no warning
