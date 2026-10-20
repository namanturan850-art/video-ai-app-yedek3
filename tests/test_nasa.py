"""NASA Image and Video Library as a stock source (no key; images only).
No network: the documented images-api.nasa.gov response shape (verified live,
see docs/NASA_IMAGE_LIBRARY.md) is mocked."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.stock import providers
from app.stock.download import Downloader
from app.stock.models import StockError
from app.stock.providers import NASAStockProvider
from test_scripts import HEADERS
from app.main import create_app

SETTINGS = {'X-AI-Video-Studio': 'settings'}


def item(nasa_id, title, *, copyright=None, missing_dims=False):
    data = {'nasa_id': nasa_id, 'title': title, 'media_type': 'image', 'center': 'JPL',
            'date_created': '1998-06-04T00:00:00Z', 'description': 'A combined view.',
            'keywords': ['Earth', 'Galileo'], 'secondary_creator': 'NASA/JPL/USGS'}
    if copyright: data['copyright'] = copyright
    links = [{'href': f'https://images-assets.nasa.gov/image/{nasa_id}/{nasa_id}~orig.jpg', 'rel': 'preview', 'render': 'image', 'width': 1700, 'height': 2164, 'size': 267383},
             {'href': f'https://images-assets.nasa.gov/image/{nasa_id}/{nasa_id}~medium.jpg', 'rel': 'alternate', 'render': 'image', 'width': 1005, 'height': 1280, 'size': 120000},
             {'href': f'https://images-assets.nasa.gov/image/{nasa_id}/{nasa_id}~thumb.jpg', 'rel': 'preview', 'render': 'image', 'width': 502, 'height': 640, 'size': 40000}]
    if missing_dims: links = [{'href': links[0]['href'], 'rel': 'preview', 'render': 'image'}]
    return {'data': [data], 'links': links}


def test_documented_api_request_and_normalisation():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'collection': {'href': '…', 'items': [item('PIA00342', 'The Earth & Moon')]}})
    provider = NASAStockProvider('', transport=httpx.MockTransport(handler))
    images = provider.search('earth moon', 'image')
    request = seen[0]
    assert request.url.host == 'images-api.nasa.gov' and request.url.path == '/search'
    assert dict(request.url.params)['media_type'] == 'image' and 'key' not in request.url.params
    assert len(images) == 1
    m = images[0]
    assert m['provider'] == 'nasa' and m['media_id'] == 'PIA00342' and m['media_type'] == 'image' and m['duration'] is None
    assert m['download_url'] == 'https://images-assets.nasa.gov/image/PIA00342/PIA00342~orig.jpg' and (m['width'], m['height']) == (1700, 2164)
    assert m['preview_url'].endswith('~thumb.jpg')
    assert m['page_url'] == 'https://images.nasa.gov/details/PIA00342'
    assert m['creator_name'] == 'NASA/JPL/USGS' and 'Earth & Moon' in m['description']
    assert m['source_metadata']['center'] == 'JPL' and m['source_metadata']['keywords'] == ['Earth', 'Galileo']


def test_video_search_makes_no_network_call():
    def handler(request):
        raise AssertionError('video search should never reach the network')
    provider = NASAStockProvider('', transport=httpx.MockTransport(handler))
    assert provider.search('earth', 'video') == [] and provider.search_videos('earth') == []


def test_copyrighted_exception_and_missing_dimensions_are_skipped():
    def handler(request):
        return httpx.Response(200, json={'collection': {'items': [
            item('PIA00342', 'Normal', ),
            item('COPYRIGHTED1', 'Has rights holder', copyright='Example Photographer'),
            item('NODIMS1', 'No usable rendition', missing_dims=True),
        ]}})
    provider = NASAStockProvider('', transport=httpx.MockTransport(handler))
    images = provider.search('earth', 'image')
    assert [m['media_id'] for m in images] == ['PIA00342']


def test_no_hits_and_upstream_error():
    empty = NASAStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'collection': {'items': []}})))
    assert empty.search('nothing at all specific', 'image') == []
    broken = NASAStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(StockError):
        broken.search('earth', 'image')


def test_download_only_from_the_asset_host(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        pid = client.post('/api/projects', json={'name': 'Uzay', 'language': 'de'}).json()['id']
        provider = NASAStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'collection': {'items': [item('PIA00342', 'The Earth & Moon')]}})))
        candidate = provider.search('earth', 'image')[0]
        saved = Downloader(client.app.state.projects, transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={'Content-Type': 'image/jpeg'}, content=b'\xff\xd8\xff' + str(request.url).encode()))
        ).download(pid, candidate)
        assert saved['provider'] == 'nasa' and saved['local_path'].endswith('.jpg')


def test_settings_show_nasa_as_ready_without_a_key(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        view = client.get('/api/settings', headers=SETTINGS).json()
        assert view['nasa']['status'] == 'Hazır' and 'Anahtar gerekmez' in view['nasa']['message']


def test_nasa_is_offered_as_a_free_provider(tmp_path):
    from app.stock.director_media import MediaDirector
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        d = MediaDirector.__new__(MediaDirector); d.service, d.unavailable = client.app.state.stock, {}
        assert 'nasa' in d.providers({'narration_text': 'Der Mars hat zwei Monde.'})


def test_youtube_credit_has_no_license_but_names_nasa(tmp_path):
    from app.youtube import YouTubeService
    media = {'provider': 'nasa', 'media_id': 'PIA00342', 'page_url': 'https://images.nasa.gov/details/PIA00342',
              'source_metadata': {'title': 'The Earth & Moon', 'center': 'JPL'}}
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        pid = client.post('/api/projects', json={'name': 'Uzay', 'language': 'de'}).json()['id']
        service = client.app.state.youtube
        service.stock.view = lambda p: {'slots': [{'selected_media': media}]}
        credits = service.credits(pid)
        assert credits == [{'provider': 'NASA', 'creator': 'JPL', 'title': 'The Earth & Moon', 'license': '', 'url': media['page_url']}]
        text = YouTubeService.description({'hook': 'Hook', 'summary': 'Zusammenfassung', 'credits': credits}, 'de')
        assert 'NASA — JPL' in text
