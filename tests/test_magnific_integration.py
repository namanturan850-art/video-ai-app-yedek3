"""Offline safety/regression checks for the opt-in Magnific stock adapter."""
import json
import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.secret_store import SettingsStore
from app.settings import SettingsService
from app.stock.magnific import MagnificStockProvider
from app.stock.models import StockError
from app.stock.download import Downloader, MAGNIFIC_DAILY_LIMIT
from app.stock.director_media import MediaDirector
from test_stock_media import stock_studio
from test_production import production_studio
from test_scripts import studio
from test_settings import settings_client


def test_magnific_setting_defaults_disabled_and_does_not_echo_key(tmp_path):
    service = SettingsService(SettingsStore(tmp_path / 'secrets'))
    assert service.safe_view()['magnific']['enabled'] is False
    service.save('magnific', {'api_key': 'synthetic-magnific-key-12345', 'enabled': True})
    public = service.safe_view()['magnific']
    assert public['enabled'] is True
    assert public['has_api_key'] is True
    assert 'synthetic-magnific-key-12345' not in str(public)
    assert service.stock_config('magnific')['api_key'] == 'synthetic-magnific-key-12345'
    service.save('magnific', {'enabled': False})
    disabled = service.safe_view()['magnific']
    assert disabled['status'] == 'Kapalı'
    assert disabled['connection_test_available'] is True
    service.clear('magnific')
    assert service.safe_view()['magnific']['enabled'] is False


def test_magnific_connection_test_uses_search_only(settings_client, monkeypatch):
    calls=[]
    def search(self, query, media_type, *, page=1):
        calls.append((query,media_type,page,self.key));return []
    monkeypatch.setattr(MagnificStockProvider,'search',search)
    saved=settings_client.put('/api/settings/magnific',json={
        'api_key':'synthetic-magnific-key-12345','enabled':True})
    assert saved.status_code==200
    assert saved.json()['magnific']['status']=='Hazır'
    response=settings_client.post('/api/settings/magnific/test')
    assert response.status_code==200
    assert response.json()['result']['status']=='Hazır'
    assert calls==[('nature landscape','video',1,'synthetic-magnific-key-12345')]
    assert 'synthetic-magnific-key-12345' not in response.text


def test_magnific_connection_test_requires_saved_enabled_switch(settings_client, monkeypatch):
    settings_client.put('/api/settings/magnific',json={
        'api_key':'synthetic-magnific-key-12345','enabled':False})
    monkeypatch.setattr(MagnificStockProvider,'search',lambda *args,**kwargs:pytest.fail('disabled test must not call API'))
    result=settings_client.post('/api/settings/magnific/test').json()['result']
    assert result['status']=='Hata' and result['category']=='provider_disabled'


def test_magnific_search_is_stock_only_and_header_is_private():
    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.host == 'api.magnific.com'
        assert request.headers.get('x-magnific-api-key') == 'synthetic-key-123456'
        return httpx.Response(200,json={'data':[
            {'id': 124, 'name': 'Forest river', 'tags': ['river', 'forest'],
             'width': 1920, 'height': 1080, 'duration': 12,
             'thumbnails': [{'url': 'https://img.freepik.com/river.jpg'}],
             'previews': [{'url': 'https://videos.freepik.com/river-preview.mp4'}],
             'licenses': [{'name': 'Premium stock licence'}]},
            {'id': 125, 'name': 'AI clip', 'is_ai_generated': True,
             'width': 1920, 'height': 1080, 'duration': 9}
        ]})
    adapter=MagnificStockProvider('synthetic-key-123456',transport=httpx.MockTransport(handler))
    assert adapter.search('river','image') == []
    results=adapter.search('river','video',page=2)
    assert len(results)==1 and results[0]['provider']=='magnific'
    assert results[0]['download_url']==''
    assert results[0]['source_metadata']['license']=='Premium stock licence'
    assert len(results[0]['source_metadata']['preview_frames'])==2
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


def test_magnific_invalid_schema_and_items_without_preview_fail_closed():
    invalid=MagnificStockProvider('synthetic-key-123456',transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'data':{'unexpected':'shape'}})))
    with pytest.raises(StockError) as error:
        invalid.search('river','video')
    assert error.value.category=='invalid_response'
    no_preview=MagnificStockProvider('synthetic-key-123456',transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'data':[{'id':'123','duration':10,'width':1920,'height':1080,
                                                         'tags':['river waterfall snow']}]})))
    assert no_preview.search('Catatumbo lightning','video') == []


def test_magnific_timeout_is_safe_and_key_is_not_reported():
    key='synthetic-key-never-log-123456'
    def timeout(request):
        raise httpx.ReadTimeout('request timed out',request=request)
    provider=MagnificStockProvider(key,transport=httpx.MockTransport(timeout))
    with pytest.raises(StockError) as error:
        provider.search('river','video')
    assert error.value.category=='timeout'
    assert key not in str(error.value)


def test_magnific_mov_download_redirect_normalizes_and_reuses_cache(stock_studio, tmp_path):
    """One entirely synthetic MOV exercises signed-link isolation and 30 fps H.264 output."""
    source=tmp_path/'fixture.mov'
    done=subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=640x360:r=24',
                         '-t','1','-c:v','mpeg4',str(source)],capture_output=True)
    if done.returncode:
        pytest.skip('FFmpeg synthetic MOV fixture could not be created')
    body=source.read_bytes(); calls=[]
    def handler(request):
        calls.append(str(request.url))
        if request.url.host=='api.magnific.com':
            assert request.url.path=='/v1/videos/stock123/download'
            return httpx.Response(200,json={'data':{'url':'https://cdn.freepik.com/original.mov?token=temporary-secret'}})
        if request.url.host=='cdn.freepik.com':
            return httpx.Response(302,headers={'location':'https://videos.freepik.com/final.mov?signature=temporary-secret'})
        return httpx.Response(200,headers={'content-type':'video/quicktime'},content=body)
    st=stock_studio; settings=st[0].app.state.settings
    settings.save('magnific',{'api_key':'synthetic-magnific-key-12345','enabled':True})
    downloader=Downloader(st[0].app.state.projects,transport=httpx.MockTransport(handler));downloader.settings=settings
    media={'provider':'magnific','media_id':'stock123','media_type':'video','source_url':'','page_url':'',
           'creator_name':'Magnific / Freepik','creator_url':'','width':640,'height':360,'duration':1,
           'preview_url':'https://img.freepik.com/preview.jpg','download_url':'','query_used':'storm',
           'description':'Catatumbo lightning storm','source_metadata':{'license':'Premium','source':'Magnific'}}
    saved=downloader.download(st[1]['id'],media)
    probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,pix_fmt,r_frame_rate',
                          '-of','json',str(st[3]/'projects'/st[1]['id']/saved['local_path'])],capture_output=True,text=True)
    stream=json.loads(probe.stdout)['streams'][0]
    assert stream=={'codec_name':'h264','pix_fmt':'yuv420p','r_frame_rate':'30/1'}
    assert saved['source_metadata']['license']=='Premium'
    assert 'temporary-secret' not in json.dumps(saved)
    before=len(calls)
    assert downloader.download(st[1]['id'],media)['local_path']==saved['local_path']
    assert len(calls)==before
    usage=json.loads((st[3]/'magnific_download_usage.json').read_text())
    assert usage['attempts']==usage['completed']==1


def test_magnific_daily_guard_blocks_before_api(stock_studio):
    st=stock_studio; settings=st[0].app.state.settings
    settings.save('magnific',{'api_key':'synthetic-magnific-key-12345','enabled':True})
    usage=st[3]/'magnific_download_usage.json'
    usage.write_text(json.dumps({'day':datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                                 'attempts':MAGNIFIC_DAILY_LIMIT,'completed':0}))
    downloader=Downloader(st[0].app.state.projects,transport=httpx.MockTransport(
        lambda request:pytest.fail('quota guard must run before HTTP')));downloader.settings=settings
    media={'provider':'magnific','media_id':'blocked1','media_type':'video'}
    with pytest.raises(StockError) as error:
        downloader.download(st[1]['id'],media)
    assert error.value.category=='rate_limit'


def test_disabling_magnific_blocks_even_cached_search(stock_studio):
    st=stock_studio; stock=st[0].app.state.stock; settings=st[0].app.state.settings
    settings.save('magnific',{'api_key':'synthetic-magnific-key-12345','enabled':True})
    candidate={'provider':'magnific','media_id':'cached1','media_type':'video','source_url':'','page_url':'',
               'creator_name':'Magnific','creator_url':'','width':1920,'height':1080,'duration':10,
               'preview_url':'https://img.freepik.com/preview.jpg','download_url':'','query_used':'storm',
               'description':'lightning storm','source_metadata':{}}
    stock.magnific_factory=lambda key:SimpleNamespace(last_diagnostic={},search=lambda *args,**kwargs:[candidate])
    assert stock._cache_search(st[1]['id'],'magnific','video','storm')[0]
    settings.save('magnific',{'enabled':False})
    with pytest.raises(StockError) as error:
        stock._cache_search(st[1]['id'],'magnific','video','storm')
    assert error.value.category=='missing_key'


@pytest.mark.parametrize('verdict,selected',[
    ({'approved':True,'score':9,'local':True}, False),
    ({'approved':True,'score':9,'local':True,'clip_approved':True}, True),
])
def test_premium_runs_after_free_pages_and_requires_visual_verdict(verdict, selected):
    director=MediaDirector.__new__(MediaDirector);calls=[];taken=[]
    director.service=SimpleNamespace(settings=SimpleNamespace(
        stock_config=lambda name:{'enabled':True,'api_key':'synthetic-key'}))
    director.providers=lambda scene:['pixabay','wikimedia']
    media={'provider':'magnific','media_type':'video','media_id':'premium1'}
    def search(slot,kinds,query,log,scene,page=1,provider_names=None):
        calls.append((query,page,tuple(provider_names or [])))
        return [media] if provider_names==['magnific'] else []
    director.search=search
    director.pool=lambda slot,results,log,exclude,scene:results
    director.judge=lambda slot,scene,candidates:{('magnific','video','premium1'):verdict}
    director.order=lambda slot,candidates,verdicts:candidates
    director.take=lambda slot,item,result,stage,log:taken.append(stage) or True
    result=director.extended_search({}, {}, ['Catatumbo lightning'], {'searches':[]}, set())
    assert calls[:2]==[('Catatumbo lightning',2,('pixabay','wikimedia')),
                       ('Catatumbo lightning',3,('pixabay','wikimedia'))]
    assert calls[2]==('Catatumbo lightning',1,('magnific',))
    assert result is selected
    assert taken==(['premium_video'] if selected else [])
