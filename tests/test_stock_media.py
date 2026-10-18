"""Part 6 deterministic tests. External HTTP is mocked; no live success claim."""
from contextlib import closing
from copy import deepcopy
import json
import logging
import re
from pathlib import Path
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.main import create_app
from app.providers.images import StockProvider
from app.stock.download import Downloader, safe_url, asset_path
from app.stock.models import StockError, make_slots, score
from app.stock.providers import PexelsStockProvider, PixabayStockProvider
from app.stock.service import candidate_id
from app.scripts.models import ScriptError
from test_scripts import studio, HEADERS, KEY, OTHER_KEY
from test_production import production_studio

STOCK_KEY='synthetic-stock-secret-7788'
MP4=b'\x00\x00\x00\x18ftypmp42'+b'\x00'*300
JPEG=b'\xff\xd8\xff'+b'\x00'*60


def media(mid='1',provider='pexels',kind='video',query='electric cars Germany dealership',**extra):
    host='videos.pexels.com' if provider=='pexels' else 'cdn.pixabay.com'
    imagehost='images.pexels.com' if provider=='pexels' else 'cdn.pixabay.com'
    page='https://www.pexels.com/video/electric-cars-'+mid+'/' if provider=='pexels' else 'https://pixabay.com/videos/id-'+mid+'/'
    return {'provider':provider,'media_id':mid,'media_type':kind,'source_url':page,'page_url':page,
        'creator_name':'Fixture Creator','creator_url':'','width':1920,'height':1080,
        'duration':30 if kind=='video' else None,'preview_url':'https://'+imagehost+'/preview.jpg',
        'download_url':'https://'+(host if kind=='video' else imagehost)+'/'+mid+('.mp4' if kind=='video' else '.jpg'),
        'query_used':query,'description':'electric cars Germany dealership charging showroom',
        'source_metadata':{'fixture':True},**extra}


def pexels_item(kind='video',mid=1):
    if kind=='video':
        return {'id':mid,'width':3840,'height':2160,'duration':30,'url':f'https://www.pexels.com/video/electric-cars-{mid}/',
                'image':'https://images.pexels.com/preview.jpg','user':{'name':'Creator','url':'https://www.pexels.com/@creator/'},
                'video_files':[{'file_type':'video/mp4','width':w,'height':h,'link':f'https://videos.pexels.com/{mid}-{w}.mp4'} for w,h in [(3840,2160),(1280,720),(1920,1080)]]}
    return {'id':mid,'width':4000,'height':2250,'url':f'https://www.pexels.com/photo/electric-cars-{mid}/','photographer':'Creator',
            'photographer_url':'https://www.pexels.com/@creator/','alt':'electric cars',
            'src':{'large2x':'https://images.pexels.com/large.jpeg','medium':'https://images.pexels.com/preview.jpeg'}}


def pixabay_item(kind='video',mid=1):
    common={'id':mid,'pageURL':f'https://pixabay.com/videos/id-{mid}/','tags':'electric cars','user':'Creator','user_id':10}
    if kind=='video':
        return {**common,'duration':30,'videos':{str(w):{'url':f'https://cdn.pixabay.com/{mid}-{w}.mp4','width':w,'height':h,'size':1000,'thumbnail':'https://cdn.pixabay.com/preview.jpg'} for w,h in [(3840,2160),(1280,720),(1920,1080)]}}
    return {**common,'imageWidth':4000,'imageHeight':2250,'largeImageURL':'https://pixabay.com/get/image_1280.jpg','previewURL':'https://cdn.pixabay.com/preview.jpg'}


class FakeStock:
    def __init__(self, name, calls, result=None): self.name,self.calls,self.result=name,calls,result
    def search(self,query,kind):
        self.calls.append((self.name,kind,query))
        if self.result: return self.result(self.name,query,kind)
        return [media(str(i),self.name,kind,query) for i in range(1,65)]


def base(st): return f'/api/projects/{st[1]["id"]}/production/stock'
def view(st):
    response=st[0].get(base(st));assert response.status_code==200,response.text;return response.json()
def stamp(st):
    state=view(st);return {'plan_id':state['plan_id'],'revision':state['revision']}
def finish(st,response):
    assert response.status_code==202,response.text
    st[0].app.state.stock.futures[response.json()['job_id']].result(timeout=30)
    return view(st)
def start(st,action='auto',slot=None,**extra):
    path=base(st)+(f'/slots/{slot}/jobs' if slot else '/jobs')
    return finish(st,st[0].post(path,json={**stamp(st),'action':action,**extra}))
def mutate(st,slot,action): return st[0].post(base(st)+f'/slots/{slot}/actions',json={**stamp(st),'action':action})


@pytest.fixture
def stock_studio(production_studio):
    client,project,fake,data=production_studio
    settings=client.app.state.settings;settings.save('pexels',{'api_key':STOCK_KEY});settings.save('pixabay',{'api_key':'synthetic-pixabay-key-8899'})
    calls=[];stock=client.app.state.stock
    stock.factory=lambda name,settings:FakeStock(name,calls)
    stock.downloader=Downloader(client.app.state.projects,transport=httpx.MockTransport(lambda request:httpx.Response(200,headers={'Content-Type':'video/mp4' if request.url.path.endswith('.mp4') else 'image/jpeg'},content=(MP4 if request.url.path.endswith('.mp4') else JPEG)+str(request.url).encode())))
    stock.test_calls=calls
    return production_studio


@pytest.mark.parametrize('provider,cls,item', [('pexels',PexelsStockProvider,pexels_item),('pixabay',PixabayStockProvider,pixabay_item)])
@pytest.mark.parametrize('kind',['video','image'])
def test_official_search_contract_normalization(provider,cls,item,kind):
    def handler(request):
        if provider=='pexels':
            assert request.headers['Authorization']==STOCK_KEY
            assert request.url.path==('/v1/videos/search' if kind=='video' else '/v1/search')
            assert request.url.params['query']=='electric cars'
            field='videos' if kind=='video' else 'photos'
        else:
            assert 'Authorization' not in request.headers
            assert request.url.params['key']==STOCK_KEY
            assert request.url.params['q']=='electric cars'
            assert request.url.path==('/api/videos/' if kind=='video' else '/api/')
            field='hits'
        return httpx.Response(200,json={field:[item(kind)]})
    adapter=cls(STOCK_KEY,transport=httpx.MockTransport(handler))
    assert isinstance(adapter,StockProvider)
    result=adapter.search('electric cars',kind)[0]
    assert result['provider']==provider and result['media_type']==kind
    assert result['creator_name']=='Creator' and result['media_id']=='1'
    assert result['width']==1920 if kind=='video' else result['width'] in (1880,1280)
    assert result['source_metadata']['documentation_url']
    assert STOCK_KEY not in json.dumps(result)


@pytest.mark.parametrize('cls',[PexelsStockProvider,PixabayStockProvider])
@pytest.mark.parametrize('code,category',[(401,'key_rejected'),(403,'key_rejected'),(429,'rate_limit'),(500,'upstream_error'),(400,'invalid_request')])
def test_provider_safe_errors_never_echo_response(cls,code,category,caplog):
    caplog.set_level(logging.DEBUG)
    adapter=cls(STOCK_KEY,transport=httpx.MockTransport(lambda request:httpx.Response(code,text='Authorization: '+STOCK_KEY)))
    with pytest.raises(StockError) as raised: adapter.search_videos('electric cars')
    assert raised.value.category==category and STOCK_KEY not in str(raised.value)
    assert STOCK_KEY not in caplog.text


@pytest.mark.parametrize('cls',[PexelsStockProvider,PixabayStockProvider])
@pytest.mark.parametrize('exc,category',[(httpx.ConnectError,'connection_error'),(httpx.ReadTimeout,'timeout')])
def test_network_failure_classification(cls,exc,category):
    def fail(request): raise exc(STOCK_KEY)
    with pytest.raises(StockError) as error: cls(STOCK_KEY,transport=httpx.MockTransport(fail)).search_images('electric cars')
    assert error.value.category==category and STOCK_KEY not in str(error.value)


@pytest.mark.parametrize('provider,item,cls',[('pexels',pexels_item,PexelsStockProvider),('pixabay',pixabay_item,PixabayStockProvider)])
def test_provider_response_secret_and_host_guard(provider,item,cls):
    fixture=item();fixture['user' if provider=='pexels' else 'tags']={'name':STOCK_KEY,'url':'https://www.pexels.com/@test/'} if provider=='pexels' else STOCK_KEY
    def serve(request): return httpx.Response(200,json={('videos' if provider=='pexels' else 'hits'):[fixture]})
    with pytest.raises((StockError,ScriptError)) as error: cls(STOCK_KEY,transport=httpx.MockTransport(serve)).search_videos('electric cars')
    assert STOCK_KEY not in str(error.value)


def test_missing_plan_clear_turkish_message_no_requests(studio):
    response=studio[0].get(base(studio));assert response.status_code==409
    assert response.json()['message']=='Önce güncel Görsel / Kurgu Planını hazırlayın.'


@pytest.mark.parametrize('duration,min_count',[(3,1),(12,2),(22,3),(30,4)])
def test_scene_multiple_slots_with_contiguous_timing_and_no_narration_change(duration,min_count):
    scene={'scene_id':'scene1','start_estimate':10,'end_estimate':10+duration,'narration_text':'Erste Aussage. Zweite Aussage. Dritte Aussage.',
        'visual_intent':'electric car charging','primary_stock_query':'electric car charging','alternative_stock_queries':['charging connector detail','electric car road'],
        'preferred_media_type':'stock_video','composition':'wide'}
    before=deepcopy(scene);slots=make_slots(scene)
    assert scene==before and len(slots)>=min_count
    assert slots[0]['estimated_start']==10 and slots[-1]['estimated_end']==10+duration
    assert all(a['estimated_end']==b['estimated_start'] for a,b in zip(slots,slots[1:]))
    assert sum(s['duration'] for s in slots)==pytest.approx(duration,abs=.003)
    if duration>=12: assert len({s['search_query'] for s in slots})>1


def test_full_auto_downloads_multiple_unique_video_slots_preserves_part5(stock_studio):
    st=stock_studio;client,project,_,data=st
    before=client.get(base(st).removesuffix('/stock')).json()
    state=start(st)
    assert state['job']['status']=='completed',state['job']
    assert len(state['slots'])>len(before['plan']['blocks'])
    assert all(s['status']=='complete' and s['selected_media']['media_type']=='video' for s in state['slots'])
    assert len({(s['selected_media']['provider'],s['selected_media']['media_id']) for s in state['slots']})==len(state['slots'])
    assert all((data/'projects'/project['id']/s['selected_media']['local_path']).is_file() for s in state['slots'])
    assert client.get(base(st).removesuffix('/stock')).json()==before
    assert client.app.state.stock.test_calls[0][1]=='video'
    assert state['slots'][0]['selected_media']['creator_name']=='Fixture Creator'
    mirror=json.loads((data/'projects'/project['id']/'stock/media_slots.json').read_text())
    assert mirror['slots']==[{k:v for k,v in slot.items() if k not in ('current_relevance_profile','visual_subject','display_order','status_label','coverage_warning','trim_needed','repeat_status','used_duration','source_duration','portrait_warning')} for slot in state['slots']]
    for secret in (KEY,OTHER_KEY,STOCK_KEY): assert secret not in json.dumps(state)


def test_provider_fallback_and_relevant_image_beats_unrelated_video(stock_studio):
    st=stock_studio;stock=st[0].app.state.stock
    def results(name,query,kind):
        if kind=='video': return [media('bad',name,kind,query,description='ocean dolphins sunset',duration=.01)]
        if name=='pexels': return [media(str(i),name,kind,query) for i in range(64)]
        return []
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,results)
    result=start(st)
    assert result['job']['status']=='completed'
    assert all(s['selected_media']['media_type']=='image' for s in result['slots'])
    assert any(name=='pixabay' and kind=='video' for name,kind,q in stock.test_calls)
    assert any(kind=='image' for name,kind,q in stock.test_calls)


def test_video_priority_and_short_clip_filter(stock_studio):
    st=stock_studio;stock=st[0].app.state.stock
    def results(name,query,kind):
        if name=='pexels': return [media('tiny',name,kind,query,duration=.01)] if kind=='video' else []
        return [media(str(i),name,kind,query) for i in range(64)]
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,results)
    state=start(st)
    assert all(s['selected_media']['provider']=='pixabay' and s['selected_media']['media_type']=='video' for s in state['slots'])
    assert stock.test_calls[0][1]=='video'


def test_no_stock_marks_future_only_no_image_calls(stock_studio,monkeypatch):
    st=stock_studio;stock=st[0].app.state.stock
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,lambda *args:[])
    def forbidden(*args,**kwargs): raise AssertionError('AI generation not authorized')
    monkeypatch.setattr('app.providers.images.GeminiImageProvider.generate_image',forbidden)
    monkeypatch.setattr('app.providers.images.OpenAIImageProvider.generate_image',forbidden)
    monkeypatch.setattr('app.providers.images.LocalGPUImageProvider.generate_image',forbidden)
    state=start(st);assert state['job']['status']=='completed'
    assert all(s['status']=='ai_needed' and s['selected_media'] is None for s in state['slots'])


def test_search_then_manual_select_replace_lock_remove_and_cache_reuse(stock_studio):
    st=stock_studio;client=st[0];slot=view(st)['slots'][0]['slot_id']
    state=start(st,'search',slot);assert state['slots'][0]['candidates'] and state['slots'][0]['selected_media'] is None
    directory=st[3]/'projects'/st[1]['id']/'stock';assert not list(directory.glob('*.mp4'))
    first,second=state['slots'][0]['candidates'][:2]
    state=start(st,'select',slot,candidate_id=candidate_id(first));local=state['slots'][0]['selected_media']['local_path']
    state=start(st,'select',slot,candidate_id=candidate_id(second));assert state['slots'][0]['selected_media']['media_id']==second['media_id']
    assert mutate(st,slot,'lock').status_code==200
    locked=deepcopy(view(st)['slots'][0]);state=start(st,'missing');assert state['slots'][0]==locked
    assert client.post(base(st)+f'/slots/{slot}/jobs',json={**stamp(st),'action':'search'}).status_code==409
    assert mutate(st,slot,'remove').status_code==409
    assert mutate(st,slot,'unlock').status_code==200
    assert mutate(st,slot,'remove').status_code==200
    assert (st[3]/'projects'/st[1]['id']/local).exists()
    # Removing another slot does not delete this project's shared file.
    client.app.state.stock.downloader.transport=httpx.MockTransport(lambda r:(_ for _ in ()).throw(AssertionError('Must use cached file')))
    state=start(st,'select',slot,candidate_id=candidate_id(first),allow_duplicate=True)
    assert state['job']['status']=='completed' and state['slots'][0]['selected_media']['local_path']==local


def test_unavoidable_duplicate_warning_and_manual_confirmation(stock_studio):
    st=stock_studio;stock=st[0].app.state.stock
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,lambda name,query,kind:[media('same',name,kind,query)])
    stock.settings.clear('pixabay')
    state=start(st);assert state['job']['status']=='completed'
    assert state['slots'][0]['selected_media'] and all(s['selected_media'] is None for s in state['slots'][1:])
    slot=state['slots'][1]
    response=st[0].post(base(st)+f'/slots/{slot["slot_id"]}/jobs',json={**stamp(st),'action':'select','candidate_id':candidate_id(slot['candidates'][0])})
    assert response.status_code==409 and response.json()['category']=='duplicate'
    confirmed=start(st,'select',slot['slot_id'],candidate_id=candidate_id(slot['candidates'][0]),allow_duplicate=True)
    assert confirmed['slots'][1]['repeat_status']=='Manuel tekrar kullanım'


def test_partial_download_failure_resume_does_not_start_over(stock_studio):
    st=stock_studio;stock=st[0].app.state.stock;original=stock.downloader.download;calls=[];failure=[True]
    def download(project,media):
        calls.append((media['provider'],media['media_id']))
        if len(calls)==2 and failure[0]: raise StockError('download_connection','Medya indirme tamamlanamadı.')
        return original(project,media)
    stock.downloader.download=download
    failed=start(st);assert failed['job']['status']=='error'
    first=deepcopy(failed['slots'][0]);assert first['status']=='complete'
    failure[0]=False
    resumed=finish(st,st[0].post(base(st)+f'/jobs/{failed["job"]["id"]}/resume',json=stamp(st)))
    assert resumed['job']['status']=='completed' and resumed['slots'][0]==first
    assert calls.count((first['selected_media']['provider'],first['selected_media']['media_id']))==1


def test_restart_persistence_handoff_preview_and_no_secrets(stock_studio):
    st=stock_studio;state=start(st);first=state['slots'][0];mutate(st,first['slot_id'],'lock');state=view(st)
    response=st[0].get(base(st)+f'/slots/{first["slot_id"]}/preview');assert response.status_code==200 and response.content==MP4+first['selected_media']['download_url'].encode()
    response=st[0].get(base(st)+f'/slots/{first["slot_id"]}/preview',headers={'Range':'bytes=0-11'});assert response.status_code==206
    handoff=st[0].get(base(st)+'/handoff').json();assert handoff['ready'] and not handoff['rendered']
    assert handoff['slots'][0]['trim_needed'] and handoff['slots'][0]['locked']
    assert all(slot['local_path'].startswith('stock/') for slot in handoff['slots'])
    with TestClient(create_app(st[3]),headers=HEADERS) as restarted:
        after=restarted.get(base(st)).json();assert after['slots']==state['slots']
        assert restarted.get('/api/health').status_code==200
    for secret in (KEY,OTHER_KEY,STOCK_KEY):
        assert secret not in json.dumps(handoff)
        for path in (st[3]/'projects'/st[1]['id']).rglob('*.json'): assert secret not in path.read_text()


def test_plan_refresh_keeps_locked_media_for_same_source(stock_studio):
    st=stock_studio;start(st);old=next(s for s in view(st)['slots'] if s['duration']>3);mutate(st,old['slot_id'],'lock');locked=next(s for s in view(st)['slots'] if s['slot_id']==old['slot_id'])
    response=st[0].post(base(st).removesuffix('/stock')+'/plan',json={'provider':'ollama','cost_confirmed':False,'confirm_replace_plan':True})
    assert response.status_code==202;st[0].app.state.scripts.futures[response.json()['job_id']].result(timeout=30)
    state=view(st)
    carried=next(s for s in state['slots'] if s['slot_id']==locked['slot_id'])
    assert carried['locked'] and carried['selected_media']==locked['selected_media']


@pytest.mark.parametrize('url',['http://videos.pexels.com/a.mp4','https://127.0.0.1/a','https://videos.pexels.com.evil.test/a','https://user:password@videos.pexels.com/a','https://videos.pexels.com:8443/a','https://videos.pexels.com/a#fragment','https://videos.pexels.com\\@evil.test/a','https://api.pexels.com/v1/search'])
def test_download_unsafe_url_rejected(url):
    with pytest.raises(StockError): safe_url(url,'pexels')


@pytest.mark.parametrize('failure',['html','oversize','incomplete','unsafe_redirect','signature','http','network'])
def test_download_failure_cleanup_no_complete_cache_record(stock_studio,failure):
    st=stock_studio;project=st[1]['id']
    def handler(request):
        if failure=='html':return httpx.Response(200,headers={'content-type':'text/html'},content=b'<html>error</html>')
        if failure=='oversize':return httpx.Response(200,headers={'content-type':'video/mp4','content-length':'999999999'})
        if failure=='incomplete':return httpx.Response(200,headers={'content-type':'video/mp4','content-length':str(len(MP4)+30)},content=MP4)
        if failure=='unsafe_redirect':return httpx.Response(302,headers={'location':'https://localhost/admin'})
        if failure=='signature':return httpx.Response(200,headers={'content-type':'video/mp4'},content=b'invalid-file'*10)
        if failure=='network':raise httpx.ReadTimeout(STOCK_KEY)
        return httpx.Response(403,text=STOCK_KEY)
    downloader=Downloader(st[0].app.state.projects,transport=httpx.MockTransport(handler))
    with pytest.raises(StockError) as error:downloader.download(project,media())
    assert STOCK_KEY not in str(error.value)
    folder=st[3]/'projects'/project/'stock';assert not list(folder.glob('*.mp4')) and not list(folder.glob('*.part'))
    with closing(st[0].app.state.projects._connection()) as connection: assert connection.execute('SELECT count(*) FROM stock_assets').fetchone()[0]==0


def test_download_only_same_project_cache_reused(stock_studio):
    st=stock_studio;downloader=st[0].app.state.stock.downloader;first=downloader.download(st[1]['id'],media());count=[]
    original=downloader.transport
    def http(request):count.append(str(request.url));return httpx.Response(200,headers={'content-type':'video/mp4'},content=MP4)
    downloader.transport=httpx.MockTransport(http)
    assert downloader.download(st[1]['id'],media())['local_path']==first['local_path'] and not count
    other=st[0].post('/api/projects',json={'name':'Other','topic':'Different','target_duration_minutes':1}).json()
    second=downloader.download(other['id'],media());assert count and second['local_path']!=first['local_path']


def test_download_symlink_folder_and_traversal_refused(stock_studio,tmp_path):
    st=stock_studio;folder=st[3]/'projects'/st[1]['id']/'stock';folder.rmdir();outside=tmp_path/'outside';outside.mkdir();folder.symlink_to(outside,target_is_directory=True)
    with pytest.raises(StockError): st[0].app.state.stock.downloader.download(st[1]['id'],media())
    assert not list(outside.iterdir())
    folder.unlink();folder.mkdir()
    with pytest.raises(StockError): asset_path(st[0].app.state.projects,st[1]['id'],{'local_path':'stock/../../app.db','file_size':1})


def test_background_job_project_deletion_and_stale_plan_guards(stock_studio):
    st=stock_studio;stock=st[0].app.state.stock;entered=Event();release=Event();original=stock.downloader.download
    def pause(project,media):entered.set();assert release.wait(8);return original(project,media)
    stock.downloader.download=pause
    response=st[0].post(base(st)+'/jobs',json={**stamp(st),'action':'auto'});assert response.status_code==202 and entered.wait(5)
    try:
        assert st[0].request('DELETE','/api/projects/'+st[1]['id'],json={'confirm':True}).status_code==409
    finally:release.set()
    stock.futures[response.json()['job_id']].result(timeout=30)


def test_schema6_upgrade_preserves_existing_data_and_vault(stock_studio):
    st=stock_studio;state=start(st);database=st[3]/'app.db';vault=(st[3]/'secrets/settings.enc').read_bytes() if (st[3]/'secrets/settings.enc').exists() else None
    with closing(st[0].app.state.projects._connection()) as connection,connection:
        connection.execute("UPDATE app_metadata SET value='6' WHERE key='schema_version'")
    initialize_database(st[3]);assert view(st)['slots']==state['slots']
    assert st[0].app.state.settings.stock_config('pexels')['api_key']==STOCK_KEY

@pytest.mark.parametrize('provider,cls,item',[('pexels',PexelsStockProvider,pexels_item),('pixabay',PixabayStockProvider,pixabay_item)])
def test_settings_encrypted_save_clear_connection_test_and_no_key_echo(tmp_path,monkeypatch,provider,cls,item,caplog):
    caplog.set_level(logging.DEBUG)
    def factory(name,settings):
        assert name==provider
        key=settings.stock_config(name)['api_key']
        assert key==STOCK_KEY
        def http(request):return httpx.Response(200,json={('photos' if provider=='pexels' else 'hits'):[item('image')]})
        return cls(key,transport=httpx.MockTransport(http))
    monkeypatch.setattr('app.stock.providers.make_stock_provider',factory)
    with TestClient(create_app(tmp_path/'data'),headers={'X-AI-Video-Studio':'settings'}) as client:
        response=client.put('/api/settings/'+provider,json={'api_key':STOCK_KEY});assert response.status_code==200
        assert STOCK_KEY not in response.text and response.json()[provider]['masked_api_key'].endswith('7788')
        response=client.post('/api/settings/'+provider+'/test');assert response.status_code==200
        assert response.json()['result']['status']=='Hazır' and STOCK_KEY not in response.text
        store=client.app.state.settings.store
        assert STOCK_KEY.encode() not in store.vault_path.read_bytes()
        assert store.read()[provider]['api_key']==STOCK_KEY
        assert client.delete('/api/settings/'+provider).json()[provider]['has_api_key'] is False
    assert STOCK_KEY not in caplog.text


def test_unconfigured_settings_and_health_no_provider_network(tmp_path,monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('No network without key')
    monkeypatch.setattr('app.stock.providers.httpx.Client',forbidden)
    with TestClient(create_app(tmp_path),headers={'X-AI-Video-Studio':'settings'}) as client:
        assert client.get('/api/health').status_code==200
        for name in ('pexels','pixabay'):
            result=client.post('/api/settings/'+name+'/test').json()
            assert result['result']['category']=='missing_key'


def test_api_rejects_arbitrary_candidate_url_unknown_fields_and_cross_project(stock_studio):
    st=stock_studio;slot=view(st)['slots'][0]['slot_id']
    for payload in ({'action':'select','candidate_id':'pexels:video:99999'},
                    {'action':'select','download_url':'http://localhost/private'},
                    {'action':'unknown'},{'action':'auto','api_key':STOCK_KEY}):
        response=st[0].post(base(st)+f'/slots/{slot}/jobs',json={**stamp(st),**payload})
        assert response.status_code==422 and STOCK_KEY not in response.text
    state=view(st);assert state['slots'][0]['selected_media'] is None
    response=st[0].post(base(st)+'/jobs',json={'plan_id':'wrong','revision':state['revision'],'action':'auto'})
    assert response.status_code==409
    assert st[0].post(base(st)+'/jobs',json={**stamp(st),'action':'auto'},headers={'Origin':'https://evil.test'}).status_code==403


def test_failed_replacement_keeps_selected_media(stock_studio):
    st=stock_studio;state=start(st);old=deepcopy(state['slots'][0]);slot=old['slot_id']
    def fail(project,media):raise StockError('download_connection','Medya indirme tamamlanamadı.')
    st[0].app.state.stock.downloader.download=fail
    after=start(st,'select',slot,candidate_id=candidate_id(old['candidates'][1]),allow_duplicate=True)
    assert after['job']['status']=='error' and after['slots'][0]['selected_media']==old['selected_media']
    assert after['slots'][0]['status']=='complete'


def test_missing_file_not_reported_complete_handoff_and_refilled(stock_studio):
    st=stock_studio;state=start(st);slot=state['slots'][0]
    (st[3]/'projects'/st[1]['id']/slot['selected_media']['local_path']).unlink()
    assert view(st)['slots'][0]['status']=='error'
    handoff=st[0].get(base(st)+'/handoff').json();assert not handoff['ready'] and handoff['slots'][0]['local_path'] is None
    after=start(st,'missing');assert after['job']['status']=='completed' and after['slots'][0]['status']=='complete'


def test_restart_recovery_checkpoints_not_restart_from_scene1(stock_studio):
    st=stock_studio;state=start(st);first=deepcopy(state['slots'][0])
    with closing(st[0].app.state.projects._connection()) as connection,connection:
        connection.execute("UPDATE stock_jobs SET status='running' WHERE id=?",(state['job']['id'],))
    with TestClient(create_app(st[3]),headers=HEADERS) as reopened:
        recovered=reopened.get(base(st)).json()
        assert recovered['job']['status']=='error' and recovered['slots'][0]==first
        assert 'Devam Et' in recovered['job']['error_message']


def test_project_search_cache_24_hours_and_other_projects_independent(stock_studio):
    st=stock_studio;stock=st[0].app.state.stock;slot=view(st)['slots'][0]['slot_id']
    start(st,'search',slot);count=len(stock.test_calls);start(st,'search',slot);assert len(stock.test_calls)==count
    with closing(st[0].app.state.projects._connection()) as connection,connection:
        connection.execute("UPDATE stock_search_cache SET created_at='2000-01-01T00:00:00+00:00'")
    start(st,'search',slot);assert len(stock.test_calls)>count


def test_stale_active_plan_cannot_attach_or_resume_old_stock_job(stock_studio):
    st=stock_studio;stock=st[0].app.state.stock;entered=Event();release=Event();original=stock.downloader.download
    def pause(project,media):entered.set();assert release.wait(8);return original(project,media)
    stock.downloader.download=pause
    response=st[0].post(base(st)+'/jobs',json={**stamp(st),'action':'auto'});assert entered.wait(5)
    try:
        plan=st[0].get(base(st).removesuffix('/stock')).json()['plan']
        edited=st[0].put(base(st).removesuffix('/stock')+f'/scenes/{plan["blocks"][0]["id"]}',json={'plan_id':plan['plan_id'],'revision':plan['revision'],'changes':{'notes':'Changed safely'}})
        assert edited.status_code==200
        view(st) # Simulate a browser refreshing while the download is in progress.
    finally:release.set()
    stock.futures[response.json()['job_id']].result(timeout=30)
    state=view(st);assert all(s['selected_media'] is None for s in state['slots'])
    assert st[0].post(base(st)+f'/jobs/{response.json()["job_id"]}/resume',json=stamp(st)).status_code==409


def test_unsafe_download_redirect_never_requests_other_origin(stock_studio):
    st=stock_studio;calls=[]
    def handler(request):calls.append(str(request.url));return httpx.Response(302,headers={'location':'https://evil.test/steal'})
    downloader=Downloader(st[0].app.state.projects,transport=httpx.MockTransport(handler))
    with pytest.raises(StockError):downloader.download(st[1]['id'],media())
    assert len(calls)==1


def test_three_minutes_nine_semantic_scenes_creates_natural_visual_beats():
    scenes=[]
    for index in range(9):
        scene={'scene_id':str(index),'start_estimate':index*20,'end_estimate':(index+1)*20,
            'narration_text':'First useful point. Second useful point. A relevant comparison. Final specific point.',
            'visual_intent':'electric cars','primary_stock_query':'electric cars road','alternative_stock_queries':['charging connector detail','electric vehicle showroom'],
            'preferred_media_type':'stock_video','composition':'wide'}
        scenes.append(scene)
    before=deepcopy(scenes);slots=[slot for scene in scenes for slot in make_slots(scene)]
    assert scenes==before and 45<=len(slots)<=65
    assert slots[0]['estimated_start']==0 and slots[-1]['estimated_end']==180
    assert all(slot['duration']<=5.5 for slot in slots)


def test_changed_scene_boundaries_keep_locked_visual_intervals(stock_studio):
    st=stock_studio;start(st);old=next(s for s in view(st)['slots'] if s['duration']>3);mutate(st,old['slot_id'],'lock');locked=next(s for s in view(st)['slots'] if s['slot_id']==old['slot_id'])
    # Split inside the original locked visual interval, using the existing Part 5
    # deterministic narration boundary API. This never modifies the source text.
    production=st[0].app.state.production;pid=st[1]['id'];plan=production.view(pid)['plan'];block=next(b for b in plan['blocks'] if b['scene_id']==locked['scene_id'])
    text=block['narration'];boundary=re.search(r'\S+\s+',text).end()
    result=st[0].post(base(st).removesuffix('/stock')+f'/scenes/{block["id"]}/actions',json={'plan_id':plan['plan_id'],'revision':plan['revision'],'action':'split','split_at':boundary})
    assert result.status_code==200,result.text
    state=view(st);preserved=[s for s in state['slots'] if s['locked'] and s['selected_media']['local_path']==locked['selected_media']['local_path']]
    assert preserved and any(s['slot_id']==locked['slot_id'] for s in preserved)
    assert sum(s['duration'] for s in preserved)==pytest.approx(locked['duration'],abs=.003)
    assert production.view(pid)['coverage_complete']
    assert all(a['estimated_end']<=b['estimated_start']+.002 for a,b in zip(state['slots'],state['slots'][1:]))


def test_pixabay_connection_probe_uses_required_24hour_cache(tmp_path,monkeypatch):
    calls=[]
    def factory(name,settings):
        def handler(request):calls.append(request.url.path);return httpx.Response(200,json={'hits':[pixabay_item('image')]})
        return PixabayStockProvider(settings.stock_config(name)['api_key'],transport=httpx.MockTransport(handler))
    monkeypatch.setattr('app.stock.providers.make_stock_provider',factory)
    with TestClient(create_app(tmp_path),headers={'X-AI-Video-Studio':'settings'}) as client:
        client.put('/api/settings/pixabay',json={'api_key':STOCK_KEY})
        assert client.post('/api/settings/pixabay/test').json()['result']['status']=='Hazır'
        result=client.post('/api/settings/pixabay/test').json()['result'];assert 'önbellek' in result['message'] and len(calls)==1
        client.put('/api/settings/pixabay',json={'api_key':STOCK_KEY+'new'})
        client.post('/api/settings/pixabay/test');assert len(calls)==2


def test_unexpected_backend_error_is_safe_json_and_app_remains_up(stock_studio,monkeypatch):
    st=stock_studio
    def unexpected(*args):raise RuntimeError('Authorization: '+STOCK_KEY)
    monkeypatch.setattr(st[0].app.state.stock,'view',unexpected)
    response=st[0].get(base(st))
    assert response.status_code==500 and response.json()['category']=='unexpected_backend'
    assert STOCK_KEY not in response.text and 'RuntimeError' not in response.text and 'Traceback' not in response.text
    assert st[0].get('/api/health').status_code==200


def test_secret_echo_in_provider_metadata_never_persisted_or_logged(stock_studio,caplog):
    st=stock_studio;stock=st[0].app.state.stock;caplog.set_level(logging.INFO)
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,lambda name,query,kind:[media('bad',name,kind,query,creator_name=STOCK_KEY)])
    state=start(st);assert state['job']['status']=='error'
    assert STOCK_KEY not in json.dumps(state) and STOCK_KEY not in caplog.text
    with closing(stock.projects._connection()) as connection:
        for table,column in [('stock_plans','state_json'),('stock_jobs','progress_json'),('stock_search_cache','result_json'),('stock_assets','metadata_json')]:
            assert all(STOCK_KEY not in row[0] for row in connection.execute('SELECT '+column+' FROM '+table))


def test_pexels_numeric_video_page_url_is_valid_but_not_verified_relevant():
    item=pexels_item();item['url']='https://www.pexels.com/video/1093662/'
    normalized=PexelsStockProvider(STOCK_KEY).normalize_result(item,'video','electric cars')
    assert normalized['description']==''
    assert score(normalized,{'duration':6})==-1
    from app.stock.models import rejection_reason
    assert rejection_reason(normalized,{'duration':6},technical_only=True) is None
