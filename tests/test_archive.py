"""Internet Archive as a stock source (no key; films only; PD / CC0 / CC BY / CC BY-SA only).
No network: the documented advancedsearch + metadata answers (docs/INTERNET_ARCHIVE.md) are mocked."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.stock.download import safe_url
from app.stock.models import StockError
from app.stock.providers import ArchiveStockProvider, archive_licence, archive_seconds
from test_scripts import HEADERS

SETTINGS = {'X-AI-Video-Studio': 'settings'}
PD = 'http://creativecommons.org/publicdomain/mark/1.0/'


def files(identifier, *, width=640, height=480, length='612.40', size=48_000_000, thumbs=5, extra=()):
    out = [{'name': f'{identifier}.mpeg', 'source': 'original', 'format': 'MPEG2', 'size': '900000000'},
           {'name': f'{identifier}_512kb.mp4', 'source': 'derivative', 'format': 'h.264', 'size': str(size),
            'width': str(width), 'height': str(height), 'length': length}]
    out += [{'name': f'{identifier}.thumbs/{identifier}_{i:06d}.jpg', 'source': 'derivative', 'format': 'Thumbnail'} for i in range(1, thumbs + 1)]
    return out + list(extra)


def metadata(identifier, licence=PD, **kwargs):
    return {'server': 'ia800300.us.archive.org', 'dir': f'/21/items/{identifier}',
            'metadata': {'identifier': identifier, 'title': f'{identifier} film', 'mediatype': 'movies',
                         'description': '<p>Ships at sea, 1948.</p>', 'creator': 'Jam Handy Organization', **({'licenseurl': licence} if licence else {})},
            'files': files(identifier, **kwargs)}


def handler(items, seen=None):
    def respond(request):
        if seen is not None: seen.append(request)
        if request.url.path == '/advancedsearch.php':
            return httpx.Response(200, json={'responseHeader': {'status': 0}, 'response': {'numFound': len(items), 'start': 0,
                                  'docs': [{'identifier': i, 'title': i} for i in items]}})
        identifier = request.url.path.removeprefix('/metadata/')
        return httpx.Response(200, json=items[identifier]) if identifier in items else httpx.Response(404)
    return respond


def test_licence_and_length_parsing():
    assert archive_licence(PD) == ('Public Domain Mark', PD)
    assert archive_licence('https://creativecommons.org/publicdomain/zero/1.0/')[0] == 'CC0'
    assert archive_licence('http://creativecommons.org/licenses/by/3.0/')[0] == 'CC BY 3.0'
    assert archive_licence('https://creativecommons.org/licenses/by-sa/4.0/')[0] == 'CC BY-SA 4.0'
    for bad in ('http://creativecommons.org/licenses/by-nc/3.0/', 'http://creativecommons.org/licenses/by-nd/3.0/',
                'http://creativecommons.org/licenses/by-nc-sa/2.0/', 'https://example.com/licence', '', None):
        assert archive_licence(bad) is None, bad
    assert archive_seconds('612.40') == pytest.approx(612.4) and archive_seconds('00:10:12') == 612 and archive_seconds('x') is None


def test_documented_requests_and_normalisation():
    seen = []
    items = {'ShipsAtSea1948': metadata('ShipsAtSea1948'),
             'NcFilm': metadata('NcFilm', licence='http://creativecommons.org/licenses/by-nc/3.0/'),
             'NoLicence': metadata('NoLicence', licence=None),
             'TinyFilm': metadata('TinyFilm', width=320, height=240)}
    provider = ArchiveStockProvider('', transport=httpx.MockTransport(handler(items, seen)))
    found = provider.search('ships at sea', 'video')
    search = seen[0]
    assert search.url.host == 'archive.org' and search.url.path == '/advancedsearch.php'
    assert 'mediatype:(movies)' in search.url.params['q'] and 'licenseurl:*publicdomain*' in search.url.params['q']
    assert r'licenseurl:*licenses\/by\/*' in search.url.params['q'] and 'licenses/by/' not in search.url.params['q']  # unescaped slashes break the live search
    assert search.url.params.get_list('fl[]') == ['identifier', 'title', 'licenseurl'] and search.url.params['output'] == 'json'
    assert {r.url.path for r in seen[1:]} == {f'/metadata/{i}' for i in items}
    assert [m['source_metadata']['identifier'] for m in found] == ['ShipsAtSea1948']  # NC, unlicensed and 320x240 films never offered
    m = found[0]
    assert m['provider'] == 'archive' and m['media_type'] == 'video' and m['duration'] == pytest.approx(612.4)
    assert (m['width'], m['height']) == (640, 480)
    assert m['download_url'] == 'https://ia800300.us.archive.org/21/items/ShipsAtSea1948/ShipsAtSea1948_512kb.mp4'
    assert m['page_url'] == 'https://archive.org/details/ShipsAtSea1948'
    assert m['source_metadata']['license'] == 'Public Domain Mark' and m['creator_name'] == 'Jam Handy Organization'
    assert len(m['source_metadata']['preview_frames']) == 3 and m['preview_url'].endswith('_000001.jpg')
    assert 'Ships at sea, 1948.' in m['description'] and '<p>' not in m['description']
    for url in (m['download_url'], m['preview_url']): safe_url(url, 'archive')
    safe_url(m['page_url'], 'archive', page=True)


def test_images_make_no_network_call_and_hd_file_is_preferred():
    def forbid(request): raise AssertionError('image search must not reach the network')
    assert ArchiveStockProvider('', transport=httpx.MockTransport(forbid)).search('ships', 'image') == []
    hd = {'name': 'Film_HD.mp4', 'format': 'h.264 HD', 'size': '150000000', 'width': '1440', 'height': '1080', 'length': '600'}
    items = {'Film': metadata('Film', extra=[hd])}
    m = ArchiveStockProvider('', transport=httpx.MockTransport(handler(items))).search('film', 'video')[0]
    assert (m['width'], m['height']) == (1440, 1080) and m['download_url'].endswith('/Film_HD.mp4')


def test_unsafe_server_and_too_big_files_are_skipped():
    bad_server = metadata('Elsewhere'); bad_server['server'] = 'evil.example.com'
    items = {'Elsewhere': bad_server, 'Huge': metadata('Huge', size=900_000_000), 'NoLength': metadata('NoLength', length='')}
    assert ArchiveStockProvider('', transport=httpx.MockTransport(handler(items))).search('film', 'video') == []
    with pytest.raises(StockError):
        safe_url('https://evil.example.com/21/items/x/x.mp4', 'archive')
    with pytest.raises(StockError):
        safe_url('https://ia800300.us.archive.org.evil.com/x.mp4', 'archive')


def test_search_error_is_a_stock_error():
    broken = ArchiveStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(StockError):
        broken.search('ships', 'video')


def test_settings_providers_youtube_credit_and_quality_rule(tmp_path):
    from app.stock.director_media import MediaDirector

    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        view = client.get('/api/settings', headers=SETTINGS).json()
        assert view['archive']['status'] == 'Hazır' and 'Anahtar gerekmez' in view['archive']['message']
        d = MediaDirector.__new__(MediaDirector); d.service, d.unavailable = client.app.state.stock, {}
        rome = {'visual_intent': 'ancient roman forum ruins', 'narration_text': 'Rom wuchs zu einem Weltreich.'}
        assert d.providers(rome)[:2] == ['wikimedia', 'archive']
        pid = client.post('/api/projects', json={'name': 'Arşiv', 'language': 'de'}).json()['id']
        media = {'provider': 'archive', 'media_id': 'ShipsAtSea1948', 'page_url': 'https://archive.org/details/ShipsAtSea1948',
                 'creator_name': 'Jam Handy Organization', 'source_metadata': {'title': 'Ships', 'license': 'Public Domain Mark', 'author': 'Jam Handy Organization'}}
        service = client.app.state.youtube
        service.stock.view = lambda p: {'slots': [{'selected_media': media}]}
        assert service.credits(pid) == [{'provider': 'Internet Archive', 'creator': 'Jam Handy Organization', 'title': 'Ships',
                                         'license': 'Public Domain Mark', 'url': media['page_url']}]
