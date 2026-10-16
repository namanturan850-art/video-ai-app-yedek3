"""Offline safety/regression checks for the opt-in Magnific stock adapter."""
import httpx
import pytest

from app.secret_store import SettingsStore
from app.settings import SettingsService
from app.stock.magnific import MagnificStockProvider
from app.stock.models import StockError


def test_magnific_setting_defaults_disabled_and_does_not_echo_key(tmp_path):
    service = SettingsService(SettingsStore(tmp_path / 'secrets'))
    assert service.safe_view()['magnific']['enabled'] is False
    service.save('magnific', {'api_key': 'synthetic-magnific-key-12345', 'enabled': True})
    public = service.safe_view()['magnific']
    assert public['enabled'] is True
    assert public['has_api_key'] is True
    assert 'synthetic-magnific-key-12345' not in str(public)
    assert service.stock_config('magnific')['api_key'] == 'synthetic-magnific-key-12345'
    service.clear('magnific')
    assert service.safe_view()['magnific']['enabled'] is False


def test_magnific_search_is_stock_only_and_header_is_private():
    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.host == 'api.magnific.com'
        assert request.headers.get('x-magnific-api-key') == 'synthetic-key-123456'
        return httpx.Response(200,json={'data':[
            {'id': 124, 'name': 'Forest river', 'tags': ['river', 'forest'],
             'width': 1920, 'height': 1080, 'duration': 12,
             'thumbnails': [{'url': 'https://img.freepik.com/river.jpg'}]},
            {'id': 125, 'name': 'AI clip', 'is_ai_generated': True,
             'width': 1920, 'height': 1080, 'duration': 9}
        ]})
    adapter=MagnificStockProvider('synthetic-key-123456',transport=httpx.MockTransport(handler))
    assert adapter.search('river','image') == []
    results=adapter.search('river','video',page=2)
    assert len(results)==1 and results[0]['provider']=='magnific'
    assert results[0]['download_url']==''
    assert 'synthetic-key-123456' not in str(results)
    assert requests[0].url.params['page']=='2'


def test_magnific_download_endpoint_not_called_during_search():
    paths = []
    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/download'):
            return httpx.Response(200,json={'data':{'url':'https://joy1.videvo.net/verify_download_video.php?verify=example'}})
        return httpx.Response(200,json={'data':[]})
    api=MagnificStockProvider('synthetic-key-123456',transport=httpx.MockTransport(handler))
    assert api.search('anything','video') == []
    assert paths==['/v1/videos']
    assert api.download_link('123').startswith('https://joy1.videvo.net/')
    assert paths==['/v1/videos','/v1/videos/123/download']


@pytest.mark.parametrize('status,category',[(401,'key_rejected'),(403,'key_rejected'),(429,'rate_limit')])
def test_magnific_provider_fails_closed(status,category):
    api=MagnificStockProvider('synthetic-key-123456',transport=httpx.MockTransport(
        lambda request:httpx.Response(status,text='synthetic-key-123456')))
    with pytest.raises(StockError) as error:api.search('river','video')
    assert error.value.category==category
    assert 'synthetic-key-123456' not in str(error.value)
