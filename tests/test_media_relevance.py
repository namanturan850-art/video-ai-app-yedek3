"""Part 6.5: local metadata evidence + mocked official stock requests only."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.database import SCHEMA_VERSION
from app.production import narration_units,visual_blocks,scene_metadata
from app.scripts.quality import QualityService
from app.stock import relevance
from app.stock.models import score,rejection_reason,normalized_media,StockError
from app.stock.providers import PixabayStockProvider
from app.stock.download import Downloader
from app.stock.service import candidate_id
from test_stock_media import media,MP4,JPEG,pixabay_item
from test_subtitles import seed,HEADERS,no_network

TEXT='Das Bermuda Triangle liegt im Atlantik. Schiffe fahren durch das Meer und Wellen bewegen sich im Sturm. Eine Karte zeigt das Gebiet des Bermuda Triangle.'
KEY='synthetic-relevance-key-9900'


def scene(anchor='Bermuda Triangle',query='Bermuda Triangle Atlantic Ocean',context='ocean ship storm compass map'):
    return {'entities':[anchor],'location':'','primary_stock_query':query,
            'alternative_stock_queries':[anchor+' map',context],
            'visual_intent':context,'narration_text':anchor+' '+context}


def rated(description,scene_value=None,kind='video',**extra):
    return relevance.annotate(media(kind=kind,description=description,**extra),relevance.profile(scene_value or scene()),1,'Bermuda Triangle')


@pytest.mark.parametrize('anchor',['Bermuda Triangle','Titanic','Mount Everest','Tokyo subway','New York','Black Sea','World War II'])
def test_explicit_anchor_keeps_exact_entity_phrase(anchor):
    value=scene(anchor,anchor+' wide view')
    assert relevance.profile(value)['subject_anchor']==anchor
    assert relevance.queries_for(relevance.profile(value))[0]==(1,anchor)


@pytest.mark.parametrize('value,expected',[
 ({'entities':['Mount Everest'],'location':'Himalaya','stock_query':'mountain snow'},'Mount Everest'),
 ({'location':'Black Sea','stock_query':'ocean water'},'Black Sea'),
 ({'stock_query':'Bermuda Triangle Atlantic Ocean'},'Bermuda Triangle'),
 ({'stock_query':'New York city skyline'},'New York'),
 ({'visual_intent':'Mount Everest mountain snow'},'Mount Everest'),
 ({'narration_text':'Das Bermuda Triangle liegt im Atlantik.'},'Bermuda Triangle'),
])
def test_old_scene_anchor_local_priority_without_regeneration(value,expected):
    before=deepcopy(value);assert relevance.profile(value)['subject_anchor']==expected;assert value==before


@pytest.mark.parametrize('text',[
 'Das Bermuda Triangle liegt im Atlantik.', 'El Bermuda Triangle está en el océano.',
 'The Bermuda Triangle is in the ocean.', 'Le Bermuda Triangle se trouve dans l’océan.',
 'Bermuda Triangle okyanus üzerindedir.',
])
def test_multilingual_name_and_narration_are_never_translated(text):
    s=scene();s['narration_text']=text;p=relevance.profile(s)
    assert p['subject_anchor']=='Bermuda Triangle' and s['narration_text']==text
    assert relevance.evaluate(media(description='Bermuda Triangle ocean'),p)['relevance_label']=='Çok ilgili'


def test_bermuda_a_b_c_weighted_ranking_and_wrong_city_never_wins():
    a=rated('Bermuda Triangle ocean mystery');b=rated('Atlantic ocean ship waves');c=rated('city skyline buildings downtown')
    weak=rated('Atlantic ocean waves')
    assert a['relevance_score']>b['relevance_score']>weak['relevance_score']>c['relevance_score']
    assert a['relevance_label']=='Çok ilgili' and c['relevance_label']=='Zayıf eşleşme'
    # Two concrete scene concepts (ocean+ship) are contextual B-roll, never the named event.
    assert b['relevance_label']=='İlgili' and b['relevance_basis']=='contextual' and a['relevance_basis']=='direct'
    assert weak['relevance_label']=='Genel bağlantılı'
    slot={'relevance_profile':relevance.profile(scene())}
    assert relevance.choose([c,b,a],set(),slot)==a
    assert relevance.choose([b,c],set(),slot)==b
    assert relevance.choose([weak,c],set(),slot) is None
    assert relevance.choose([c],set(),slot) is None


@pytest.mark.parametrize('anchor,query,good,bad',[
 ('Titanic','Titanic ship ocean history','ship ocean history','city skyscraper buildings'),
 ('Mount Everest','Mount Everest mountain snow Himalaya','mountain snow Himalaya','beach sand palm'),
 ('Tokyo subway','Tokyo subway train metro','train metro Tokyo','forest trees woods'),
 ('storm at sea','storm at sea ocean waves','waves storm ocean','office city traffic'),
])
def test_general_context_logic_not_a_bermuda_rule(anchor,query,good,bad):
    s=scene(anchor,query,query)
    assert relevance.acceptable(rated(good,s))
    assert not relevance.acceptable(rated(bad,s))


@pytest.mark.parametrize('generic',['world people city travel beautiful view','Welt Menschen Stadt Natur','mundo gente ciudad naturaleza','monde personnes ville voyage','dunya insanlar sehir doga'])
def test_generic_words_alone_do_not_certify_relevance(generic):
    assert not relevance.acceptable(rated(generic))


def test_entity_modifier_token_alone_cannot_become_subject_match():
    for anchor,desc in [('Bermuda Triangle','triangle geometric shapes'),('New York','new beautiful people'),('Mount Everest','mount camera view')]:
        assert not relevance.acceptable(rated(desc,scene(anchor,anchor+' ocean','ocean ship')))


def test_exact_entity_bonus_requires_whole_phrase_boundaries():
    s=scene('York','York train','train')
    assert rated('York train',s)['relevance_score']>rated('Yorkshire train',s)['relevance_score']
    assert rated('Yorkshire train',s)['relevance_label']!='Çok ilgili'


def test_relevant_image_beats_unrelated_higher_quality_video():
    image=rated('Bermuda Triangle map ocean',kind='image',width=1280,height=720)
    video=rated('city skyline buildings',width=3840,height=2160)
    assert relevance.choose([video,image],set(),{'preferred_type':'stock_video','relevance_profile':relevance.profile(scene())})==image


def test_duplicate_avoidance_cannot_trade_relevance_for_variety():
    direct=rated('Bermuda Triangle ocean');weak=rated('ocean waves',mid='2');city=rated('city skyline',mid='3')
    used={(direct['provider'],direct['media_type'],direct['media_id'])}
    slot={'relevance_profile':relevance.profile(scene())}
    assert relevance.choose([direct,weak,city],used,slot) is None
    contextual=rated('ocean ship waves',mid='5')
    assert relevance.choose([direct,weak,contextual,city],used,slot)==contextual
    equal={**direct,'media_id':'4'}
    assert relevance.choose([direct,equal,city],used,slot)==equal


def test_weak_old_alternative_does_not_certify_wrong_context():
    s=scene();s['alternative_stock_queries']=['city skyline buildings','Bermuda Triangle city skyline']
    assert not relevance.acceptable(rated('city skyline buildings downtown',s))


def test_official_pixabay_tags_and_no_provider_specific_exemption():
    s=scene();p=relevance.profile(s);slot={'duration':6,'relevance_profile':p}
    fixtures=[]
    for i,tags in enumerate(('Bermuda Triangle ocean mystery','Atlantic ocean ship waves','city skyline buildings downtown'),1):
        item=pixabay_item(mid=i);item['tags']=tags;fixtures.append(item)
    calls=[]
    def respond(request):
        calls.append(request);assert request.url.path=='/api/videos/'
        assert request.url.params['key']==KEY
        return httpx.Response(200,json={'hits':fixtures})
    result=PixabayStockProvider(KEY,transport=httpx.MockTransport(respond)).search_videos('Bermuda Triangle')
    assert len(calls)==1 and [m['description'] for m in result]==[m['tags'] for m in fixtures]
    assert score(result[0],slot)>score(result[1],slot)>score(result[2],slot)
    assert rejection_reason(result[2],slot)=='relevance'


def test_future_search_hints_optional_grounded_and_same_existing_prompt():
    source=TEXT;raw={'purpose':'Context','mood':'mystery','visual_intent':'Bermuda Triangle ocean map','stock_query':'Bermuda Triangle Atlantic Ocean',
                   'alternative_stock_queries':['Bermuda Triangle map'],'media_type':'stock_video','entities':['Bermuda Triangle'],
                   'search_anchor':'Bermuda Triangle','search_context':'Atlantic Ocean map','search_alternatives':['Bermuda Triangle map aerial','ocean compass']}
    block=scene_metadata(raw,source)
    assert block['search_anchor']=='Bermuda Triangle' and block['search_context']=='Atlantic Ocean map'
    assert block['search_alternatives']==raw['search_alternatives']
    raw.update(search_anchor='Invented New Place',search_context=['bad'],search_alternatives=['Invented New Place'])
    safe=scene_metadata(raw,source)
    assert not safe['search_anchor'] and not safe['search_context'] and not safe['search_alternatives'] and safe['metadata_warnings']
    prompt=QualityService._instructions('visual')
    assert all(key in prompt for key in ('search_anchor','search_context','search_alternatives'))
    assert 'Only the seven example fields are required' in prompt


@pytest.fixture
def studio(tmp_path,request):
    with TestClient(create_app(tmp_path/'data'),headers=HEADERS) as client:
        settings=getattr(request,'param',{})
        source=settings.get('text',TEXT)
        app=client.app;st=seed(app,text=source,seconds=settings.get('seconds',12));units=narration_units(source)
        raw={**scene(),'stock_query':'Bermuda Triangle Atlantic Ocean','unit_ids':[u['unit_id'] for u in units],
             'purpose':'Meer und Gebiet zeigen','mood':'neutral','media_type':'stock_video','overlay_text':'','composition':'wide'}
        for key in ('primary_stock_query','narration_text'):raw.pop(key)
        raw.update(settings.get('scene',{}))
        blocks=visual_blocks({'scenes':[raw]},source,'de',135,units=units)
        app.state.production.save_generated(st['pid'],st['sid'],'de',blocks)
        app.state.subtitles.create(st['pid'],{'regenerate_confirmed':False})
        app.state.settings.save('pixabay',{'api_key':KEY})
        app.state.scripts.provider_factory=no_network;app.state.narration.factory=no_network;app.state.narration.downloader.download=no_network
        stock=app.state.stock;calls=[];downloads=[]
        class Provider:
            def search(self,q,kind):calls.append((q,kind));return stock.test_results(q,kind)
        stock.test_results=lambda q,kind:[];stock.factory=lambda *args:Provider()
        stock.downloader=Downloader(app.state.projects,transport=httpx.MockTransport(lambda req:(downloads.append(str(req.url)) or httpx.Response(200,headers={'Content-Type':'video/mp4' if req.url.path.endswith('.mp4') else 'image/jpeg'},content=(MP4 if req.url.path.endswith('.mp4') else JPEG)+str(req.url).encode()))))
        st.update(client=client,storage=tmp_path/'data',stock=stock,calls=calls,downloads=downloads,root=app.state.projects._path(st['pid']))
        yield st


def endpoint(st):return f'/api/projects/{st["pid"]}/production/stock'
def view(st):return st['client'].get(endpoint(st)).json()
def run(st,action='auto',slot=None,**extra):
    state=view(st);url=endpoint(st)+(f'/slots/{slot}/jobs' if slot else '/jobs')
    r=st['client'].post(url,json={'plan_id':state['plan_id'],'revision':state['revision'],'action':action,**extra});assert r.status_code==202,r.text
    st['stock'].futures[r.json()['job_id']].result(timeout=15)
    state=view(st);assert state['job']['status']=='completed',state['job'];return state


@pytest.mark.parametrize('availability',['direct','context','weak','city','image'])
def test_real_service_tiered_search_download_choice_and_weak_manual_candidates(studio,availability):
    st=studio
    def results(q,kind):
        if availability=='city':return [media('city','pixabay',kind,q,description='city skyline buildings downtown')]
        if availability=='image':return [media('map' if kind=='image' else 'city','pixabay',kind,q,description='Bermuda Triangle map' if kind=='image' else 'city skyline buildings downtown')]
        if availability=='direct':return [media('direct','pixabay',kind,q,description='Bermuda Triangle ocean mystery')]
        if availability=='weak':return [media('weak','pixabay',kind,q,description='Atlantic ocean waves')]
        return [media('context','pixabay',kind,q,description='Atlantic ocean ship waves')]
    st['stock'].test_results=results;state=run(st)
    assert state['slots']
    if availability in ('city','weak'):
        assert all(s['status']=='ai_needed' and s['selected_media'] is None for s in state['slots'])
        assert not st['downloads']
        assert all(s['candidates'] and s['candidates'][0]['relevance_label']==('Zayıf eşleşme' if availability=='city' else 'Genel bağlantılı') for s in state['slots'])
        return
    assert all(s['selected_media'] is None for s in state['slots'][1:])
    for s in state['slots'][:1]:
        m=s['selected_media'];assert m and relevance.acceptable(m)
        assert m['media_id']==('map' if availability=='image' else availability)
        if availability=='context':
            # Equally relevant fresh images can avoid repeating the same video.
            assert m['media_type'] in ('video','image')
        else:assert m['media_type']==('image' if availability=='image' else 'video')
        assert all(s[key]==m[key] for key in ('search_tier','query_used','relevance_score','relevance_label','relevance_basis'))
        assert m['relevance_basis']==('contextual' if availability=='context' else 'direct')
        assert s['subject_anchor']=='Bermuda Triangle'
    if availability=='image':
        assert st['calls'][0][1]=='video' and any(kind=='image' for q,kind in st['calls'])
        assert all(not url.endswith('.mp4') for url in st['downloads'])


def test_read_only_existing_stock_unchanged_until_explicit_research_and_sources_preserved(studio):
    st=studio;st['stock'].test_results=lambda q,kind:[media('old','pixabay',kind,q,description='Bermuda Triangle ocean')]
    old=run(st);slot=old['slots'][0];old_file=st['root']/slot['selected_media']['local_path'];old_bytes=old_file.read_bytes()
    calls=len(st['calls']);saved=deepcopy(old['slots'])
    assert view(st)['slots']==saved and len(st['calls'])==calls
    with closing(st['stock'].projects._connection()) as c:
        before={t:[dict(r) for r in c.execute('SELECT * FROM '+t+' WHERE project_id=?',(st['pid'],))] for t in ('script_versions','scene_plan_versions','narration_versions','subtitle_versions')}
    originals={str(f.relative_to(st['root'])):hashlib.sha256(f.read_bytes()).hexdigest() for d in ('script','scenes','voice','subtitles') for f in (st['root']/d).rglob('*') if f.is_file()}
    st['stock'].test_results=lambda q,kind:[media('new','pixabay',kind,q,description='Bermuda Triangle ocean map')]
    with closing(st['stock'].projects._connection()) as c,c:c.execute('DELETE FROM stock_search_cache WHERE project_id=?',(st['pid'],))
    result=run(st,'relevance_research')
    assert result['selection_version']==2 and result['selection_history'][0]['version']==1
    snapshot=json.loads((st['root']/result['selection_history'][0]['local_path']).read_text())
    assert snapshot['slots'][0]['selected_media']==slot['selected_media'] and old_file.read_bytes()==old_bytes
    assert result['slots'][0]['selected_media']['media_id']=='new'
    for name,digest in originals.items():assert hashlib.sha256((st['root']/name).read_bytes()).hexdigest()==digest
    with closing(st['stock'].projects._connection()) as c:
        assert all([dict(r) for r in c.execute('SELECT * FROM '+t+' WHERE project_id=?',(st['pid'],))]==records for t,records in before.items())
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]==SCHEMA_VERSION
    with TestClient(create_app(st['storage']),headers=HEADERS) as restarted:
        assert restarted.get(endpoint(st)).json()['slots']==result['slots']


def test_explicit_research_with_only_city_leaves_slot_unresolved_keeps_old_files(studio):
    st=studio;st['stock'].test_results=lambda q,kind:[media('old','pixabay',kind,q,description='Bermuda Triangle ocean')]
    before=run(st);old_file=st['root']/before['slots'][0]['selected_media']['local_path'];original=old_file.read_bytes()
    # Simulate the owner's older weak automatic selection, without a new download.
    with closing(st['stock'].projects._connection()) as c,c:
        state=st['stock']._load(c,st['pid'],before['plan_id'])
        for s in state['slots']:
            if s['selected_media']:s['selected_media']['description']='city skyline buildings downtown'
        st['stock']._save(c,state);c.execute('DELETE FROM stock_search_cache WHERE project_id=?',(st['pid'],))
    st['stock'].test_results=lambda q,kind:[media('city','pixabay',kind,q,description='city skyline buildings downtown')]
    result=run(st,'relevance_research')
    assert all(s['selected_media'] is None and s['status']=='ai_needed' for s in result['slots'])
    assert old_file.read_bytes()==original and len(st['downloads'])==1


def test_research_error_keeps_previous_selection_and_read_only_sources(studio):
    st=studio;st['stock'].test_results=lambda q,kind:[media('old','pixabay',kind,q,description='Bermuda Triangle ocean')]
    before=run(st)
    with closing(st['stock'].projects._connection()) as c,c:c.execute('DELETE FROM stock_search_cache WHERE project_id=?',(st['pid'],))
    def fail(*args):raise StockError('rate_limit','Pixabay kullanım sınırına ulaşıldı.')
    st['stock'].test_results=fail;state=view(st)
    r=st['client'].post(endpoint(st)+'/jobs',json={'plan_id':state['plan_id'],'revision':state['revision'],'action':'relevance_research'});assert r.status_code==202
    st['stock'].futures[r.json()['job_id']].result(timeout=15)
    after=view(st);assert after['job']['status']=='error' and after['slots'][0]['selected_media']==before['slots'][0]['selected_media']
    assert (st['root']/after['selection_history'][0]['local_path']).is_file()


def test_new_search_metadata_never_leaks_keys_and_unknown_labels_rejected(studio,caplog):
    st=studio;caplog.set_level(logging.DEBUG)
    st['stock'].test_results=lambda q,kind:[media('ok','pixabay',kind,q,description='Bermuda Triangle ocean')]
    state=run(st);assert KEY not in json.dumps(state) and KEY not in caplog.text
    bad=media();bad['relevance_label']=KEY
    with pytest.raises(StockError):normalized_media(bad)


def test_rescan_preserves_locked_slots(studio):
    st=studio;st['stock'].test_results=lambda q,kind:[media('old','pixabay',kind,q,description='Bermuda Triangle ocean')]
    old=run(st);slot=old['slots'][0]
    r=st['client'].post(endpoint(st)+f'/slots/{slot["slot_id"]}/actions',json={'plan_id':old['plan_id'],'revision':old['revision'],'action':'lock'});assert r.status_code==200
    locked=view(st)['slots'][0];count=len(st['downloads']);result=run(st,'relevance_research')
    assert result['slots'][0]==locked and len(st['downloads'])==count
