"""Europeana prerequisites. Synthetic media only; no live Search API claim."""
import socket
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.stock.download import Downloader, safe_url
from app.stock.models import StockError, normalized_media
from app.youtube import YouTubeService
from app.stock.providers import EuropeanaStockProvider, archive_licence, make_stock_provider


def dns(monkeypatch, *addresses):
    def resolve(host, port, **kwargs):
        return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM,
                 6, '', (ip, port)) for ip in addresses]
    monkeypatch.setattr('app.stock.download.socket.getaddrinfo', resolve)


def candidate():
    return normalized_media({
        'provider': 'europeana', 'media_id': 'synthetic', 'media_type': 'image',
        'source_url': 'https://www.europeana.eu/item/test/1',
        'page_url': 'https://www.europeana.eu/item/test/1',
        'creator_name': 'Actual artist', 'width': 1600, 'height': 900,
        'preview_url': 'https://api.europeana.eu/test-preview',
        'download_url': 'https://museum.example/painting.png', 'query_used': 'painting',
        'source_metadata': {'author': 'Actual artist', 'title': 'Painting',
                            'license': 'CC BY 4.0',
                            'license_url': 'https://creativecommons.org/licenses/by/4.0/'}})


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.0.1',
    '169.254.169.254', '100.64.0.1', '0.0.0.0', '::1', 'fc00::1', 'fe80::1',
    '224.0.0.1', 'ff02::1', '192.0.2.1', '::ffff:127.0.0.1'])
def test_non_public_dns_answers_are_refused(monkeypatch, ip):
    dns(monkeypatch, ip)
    with pytest.raises(StockError, match='doğrulanamadı'):
        safe_url('https://museum.example/image.jpg', 'europeana')


@pytest.mark.parametrize('host', ['127.0.0.1', '[::1]', '8.8.8.8', '[2606:4700:4700::1111]'])
def test_even_public_ip_literals_are_refused(monkeypatch, host):
    dns(monkeypatch, '8.8.8.8')
    with pytest.raises(StockError):
        safe_url(f'https://{host}/image.jpg', 'europeana')


def test_all_dns_answers_must_be_public(monkeypatch):
    dns(monkeypatch, '8.8.8.8', '127.0.0.1')
    with pytest.raises(StockError):
        safe_url('https://museum.example/image.jpg', 'europeana')
    dns(monkeypatch)
    with pytest.raises(StockError):
        safe_url('https://museum.example/image.jpg', 'europeana')
    def fail(*args, **kwargs):
        raise socket.gaierror('No DNS')
    monkeypatch.setattr('app.stock.download.socket.getaddrinfo', fail)
    with pytest.raises(StockError):
        safe_url('https://museum.example/image.jpg', 'europeana')


def test_public_museum_allowed_but_preview_is_api_only(monkeypatch):
    dns(monkeypatch, '8.8.8.8', '2606:4700:4700::1111')
    url = 'https://museum.example/api/image.jpg'
    assert safe_url(url, 'europeana') == url
    assert safe_url('https://api.europeana.eu/preview', 'europeana', preview=True)
    assert safe_url(candidate()['page_url'], 'europeana', page=True)
    for bad in (url, 'https://api.europeana.eu.evil.example/preview'):
        with pytest.raises(StockError):
            safe_url(bad, 'europeana', preview=True)
    # Existing providers retain their fixed host policy.
    with pytest.raises(StockError):
        safe_url(url, 'wikimedia')


@pytest.mark.parametrize('url', ['http://museum.example/a', 'https://user@museum.example/a',
    'https://museum.example:8443/a', 'https://museum.example/a#b',
    'https://museum.example/a\\b', 'https://museum.example/a\nb'])
def test_malformed_museum_urls_still_refused(monkeypatch, url):
    dns(monkeypatch, '8.8.8.8')
    with pytest.raises(StockError):
        safe_url(url, 'europeana')


def test_download_checks_redirect_dns_and_sends_no_key(tmp_path, monkeypatch):
    dns(monkeypatch, '8.8.8.8')
    seen = []
    def respond(request):
        seen.append(request)
        assert 'x-api-key' not in request.headers and 'authorization' not in request.headers
        return httpx.Response(302, headers={'location': 'https://127.0.0.1/private'})
    with TestClient(create_app(tmp_path / 'data')) as client:
        pid = client.post('/api/projects', headers={'X-AI-Video-Studio': 'projects'},
                          json={'name': 'Europeana test'}).json()['id']
        downloader = Downloader(client.app.state.projects, transport=httpx.MockTransport(respond))
        with pytest.raises(StockError):
            downloader.download(pid, candidate())
        assert len(seen) == 1
        assert not list((client.app.state.projects._path(pid) / 'stock').glob('.download-*'))


def test_public_museum_download_and_public_redirect(tmp_path, monkeypatch):
    from io import BytesIO
    from PIL import Image
    dns(monkeypatch, '8.8.8.8')
    image = BytesIO()
    Image.new('RGB', (1600, 900)).save(image, format='PNG')
    payload = image.getvalue()
    seen = []
    def respond(request):
        seen.append(request)
        assert 'x-api-key' not in request.headers
        if request.url.host == 'museum.example':
            return httpx.Response(302, headers={'location': 'https://cdn.museum.example/a.png'})
        return httpx.Response(200, content=payload, headers={'content-type': 'image/png'})
    with TestClient(create_app(tmp_path / 'data')) as client:
        pid = client.post('/api/projects', headers={'X-AI-Video-Studio': 'projects'},
                          json={'name': 'Europeana test'}).json()['id']
        saved = Downloader(client.app.state.projects, transport=httpx.MockTransport(respond)).download(pid, candidate())
        assert saved['file_size'] == len(payload)
        assert (client.app.state.projects._path(pid) / saved['local_path']).read_bytes() == payload
        assert [r.url.host for r in seen] == ['museum.example', 'cdn.museum.example']


def test_dns_is_checked_again_on_a_later_download(monkeypatch):
    dns(monkeypatch, '8.8.8.8')
    assert safe_url(candidate()['download_url'], 'europeana')
    dns(monkeypatch, '127.0.0.1')
    with pytest.raises(StockError):
        safe_url(candidate()['download_url'], 'europeana')


def test_europeana_credits_keep_artist_and_deduplicate_by_source():
    media = candidate()
    commons = {**media, 'provider': 'wikimedia'}
    stock = SimpleNamespace(view=lambda pid: {'slots': [
        {'selected_media': m} for m in (media, media, commons)]})
    service = YouTubeService(None, None, None, None, stock, None, None)
    credits = service.credits('project')
    assert len(credits) == 2
    assert credits[0] == {'provider': 'Europeana', 'creator': 'Actual artist',
                          'title': 'Painting', 'license': 'CC BY 4.0', 'url': media['page_url']}
    assert credits[1]['provider'] == 'Wikimedia Commons'
    description = service.description({'credits': credits}, 'tr')
    assert 'Actual artist, CC BY 4.0 (Europeana)' in description
    assert media['page_url'] in description


def search_item(**changes):
    # Synthetic contract fixture; deliberately not labelled as a live API recording.
    return {'guid': 'https://www.europeana.eu/item/test/1', 'id': '/test/1',
            'title': ['Painting'], 'dcCreator': ['Actual artist'],
            'edmIsShownBy': ['https://museum.example/painting.png'],
            'edmPreview': ['https://api.europeana.eu/test-preview'],
            'rights': ['https://creativecommons.org/licenses/by/4.0/'],
            'dataProvider': ['Museum'], **changes}


def search_provider(monkeypatch, items, *, response=None):
    from io import BytesIO
    from PIL import Image
    dns(monkeypatch, '8.8.8.8')
    image = BytesIO()
    Image.new('RGB', (1600, 900)).save(image, format='PNG')
    seen = []
    def respond(request):
        seen.append(request)
        if request.url.host == 'api.europeana.eu':
            return httpx.Response(200, json=response if response is not None else {
                'success': True, 'itemsCount': len(items), 'totalResults': len(items), 'items': items})
        assert 'x-api-key' not in request.headers
        return httpx.Response(200, content=image.getvalue(), headers={'content-type': 'image/png'})
    return EuropeanaStockProvider('private-europeana-key', transport=httpx.MockTransport(respond)), seen


@pytest.mark.parametrize('scalar', [False, True])
def test_search_contract_and_scalar_or_list_metadata(monkeypatch, scalar):
    item = search_item()
    if scalar:
        item = {k: v[0] if isinstance(v, list) else v for k, v in item.items()}
    provider, seen = search_provider(monkeypatch, [item])
    media, = provider.search_images('painting')
    request = seen[0]
    assert str(request.url).startswith('https://api.europeana.eu/record/v2/search.json?')
    assert request.headers['x-api-key'] == 'private-europeana-key'
    assert 'private-europeana-key' not in str(request.url) and 'wskey' not in request.url.params
    assert request.url.params['query'] == 'painting'
    assert request.url.params['media'] == 'true' and request.url.params['reusability'] == 'open'
    assert 0 < int(request.url.params['rows']) <= 100
    assert request.url.params.get_list('qf') == ['IMAGE_ASPECTRATIO:landscape', 'IMAGE_SIZE:large']
    assert (media['width'], media['height']) == (1600, 900) and media['duration'] is None
    assert media['creator_name'] == 'Actual artist'
    assert media['source_metadata']['data_provider'] == 'Museum'
    assert media['source_metadata']['license'] == 'CC BY 4.0'
    assert media['source_metadata']['author'] != media['source_metadata']['data_provider']


@pytest.mark.parametrize('rights', ['', None, {}, ['https://rightsstatements.org/vocab/InC/1.0/'],
    'https://creativecommons.org/licenses/by-nc/4.0/',
    'https://creativecommons.org/licenses/by-nd/4.0/',
    'https://creativecommons.org/licenses/by/4.0/evil',
    ['https://creativecommons.org/licenses/by/4.0/', 'https://creativecommons.org/licenses/by-nc/4.0/']])
def test_non_open_or_ambiguous_licences_never_downloaded(monkeypatch, rights):
    provider, seen = search_provider(monkeypatch, [search_item(rights=rights)])
    assert provider.search_images('painting') == []
    assert len(seen) == 1


@pytest.mark.parametrize('rights', ['https://creativecommons.org/publicdomain/zero/1.0/',
    'https://creativecommons.org/publicdomain/mark/1.0/',
    'https://creativecommons.org/licenses/by/4.0/',
    'https://creativecommons.org/licenses/by-sa/4.0/'])
def test_each_allowed_licence(monkeypatch, rights):
    provider, seen = search_provider(monkeypatch, [search_item(rights=rights)])
    assert len(provider.search_images('painting')) == 1
    assert archive_licence(rights)


def test_by_author_required_and_museum_is_not_an_author(monkeypatch):
    provider, seen = search_provider(monkeypatch, [search_item(dcCreator=[])])
    assert provider.search_images('painting') == [] and len(seen) == 1


def test_external_previews_are_not_offered(monkeypatch):
    provider, seen = search_provider(monkeypatch, [search_item(edmPreview='https://museum.example/preview')])
    assert provider.search_images('painting')[0]['preview_url'] == ''


@pytest.mark.parametrize('response', [[], {'success': False, 'error': 'private-europeana-key'},
    {'success': True, 'itemsCount': '0', 'totalResults': 0},
    {'success': True, 'itemsCount': 1, 'totalResults': 1, 'items': []},
    {'success': True, 'itemsCount': 0, 'totalResults': -1, 'items': []}])
def test_bad_search_responses_fail_safely(monkeypatch, response):
    provider, seen = search_provider(monkeypatch, [], response=response)
    with pytest.raises(StockError) as error:
        provider.search_images('painting')
    assert error.value.category == 'invalid_response'
    assert 'private-europeana-key' not in str(error.value)


def test_zero_hits_video_and_pagination(monkeypatch):
    provider, seen = search_provider(monkeypatch, [])
    assert provider.search_images('painting') == []
    assert provider.search_videos('painting') == []
    assert provider.search('painting', 'image', page=2) == []
    assert len(seen) == 1


def test_image_header_failure_does_not_invent_dimensions(monkeypatch):
    provider, seen = search_provider(monkeypatch, [search_item()])
    def fail(url):
        raise OSError('unreadable image')
    monkeypatch.setattr(provider, 'image_dimensions', fail)
    assert provider.search_images('painting') == []


def test_key_never_leaks_via_museum_url(monkeypatch):
    provider, seen = search_provider(monkeypatch, [search_item(
        edmIsShownBy='https://museum.example/painting?key=private-europeana-key')])
    with pytest.raises(StockError):
        provider.search_images('painting')
    assert len(seen) == 1


def test_settings_factory_and_connection_test(tmp_path, monkeypatch):
    with TestClient(create_app(tmp_path / 'data')) as client:
        settings = client.app.state.settings
        assert not settings.stock_config('europeana').get('api_key')
        from app.stock.director_media import MediaDirector
        director = MediaDirector.__new__(MediaDirector)
        director.service = SimpleNamespace(settings=settings)
        director.unavailable = {}
        assert 'europeana' not in director.providers()
        headers = {'X-AI-Video-Studio': 'settings'}
        saved = client.put('/api/settings/europeana', headers=headers,
                           json={'api_key': 'europeana-test-key'})
        assert saved.status_code == 200, saved.text
        assert 'europeana-test-key' not in saved.text
        assert isinstance(make_stock_provider('europeana', settings), EuropeanaStockProvider)
        assert 'europeana' in director.providers()
        monkeypatch.setattr(EuropeanaStockProvider, 'search_images', lambda self, query: [])
        result = client.post('/api/settings/europeana/test', headers=headers)
        assert result.status_code == 200, result.text
        assert result.json()['result']['status'] == 'Hazır'
        assert '0 kullanılabilir görsel' in result.json()['result']['message']


@pytest.mark.parametrize('status,category', [(401, 'key_rejected'), (429, 'rate_limit'), (503, 'upstream_error')])
def test_search_http_failures(status, category):
    provider = EuropeanaStockProvider('private-europeana-key', transport=httpx.MockTransport(
        lambda request: httpx.Response(status, headers={'retry-after': '9'})))
    with pytest.raises(StockError) as error:
        provider.search_images('painting')
    assert error.value.category == category
    if status == 429: assert error.value.retry_after == 9


@pytest.mark.parametrize('mime,body', [('video/mp4', b'not-an-image'), ('image/png', b'invalid')])
def test_non_images_and_invalid_headers_are_skipped(monkeypatch, mime, body):
    dns(monkeypatch, '8.8.8.8')
    def respond(request):
        if request.url.host == 'api.europeana.eu':
            return httpx.Response(200, json={'success': True, 'itemsCount': 1, 'totalResults': 1, 'items': [search_item()]})
        return httpx.Response(200, content=body, headers={'content-type': mime})
    provider = EuropeanaStockProvider('private-europeana-key', transport=httpx.MockTransport(respond))
    assert provider.search_images('painting') == []
