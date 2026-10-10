"""Metadata evidence, fresh scores, English provider queries and video-first mix."""
from contextlib import closing
from copy import deepcopy
import json

import httpx
import pytest

from app.stock import relevance
from app.stock.providers import PixabayStockProvider,PexelsStockProvider
from test_stock_media import media,pixabay_item,pexels_item
from test_media_relevance import studio,scene,endpoint,view,run,KEY

AVIATION={'entities':['modern airplane cockpit navigation computer'],
 'stock_query':'modern uçak kokpit navigasyon bilgisayar ekranı dijital haritaları',
 'visual_intent':'modern aviation technology correcting magnetic readings',
 'alternative_stock_queries':['aircraft cockpit instruments','flight navigation system','cockpit GPS display']}
SOURCE='Moderne Flugzeuge nutzen Computer zur Navigation. Anzeigen im Cockpit zeigen die Instrumente. Piloten kontrollieren den Flug.'
SEED={'text':SOURCE,'scene':AVIATION}
A='airplane cockpit pilot aircraft navigation flight instruments'
B='woman train railway passenger window travel'
C='dog pet animal grass garden'
D='aircraft cockpit navigation display aviation'


def current():return relevance.profile(AVIATION)
def slot():return {'preferred_type':'stock_video','relevance_profile':current()}
def candidate(mid,desc,kind='video',**extra):return media(mid,'pixabay',kind,'aircraft cockpit navigation',description=desc,**extra)


@pytest.mark.parametrize('description',[B,C,'train railway GPS instruments','pet dog computer garden','food cooking dashboard'])
def test_unrelated_metadata_cannot_be_certified_by_query_tier_resolution_or_saved_score(description):
    m=candidate('bad',description,width=3840,height=2160,search_tier=1,relevance_score=300,relevance_label='Çok ilgili')
    original=deepcopy(m)
    assert relevance.evaluate(m,current())=={'relevance_score':0,'relevance_label':'Zayıf eşleşme'}
    assert relevance.choose([m],set(),slot()) is None and m==original
    assert relevance.ordered([m],set(),slot())[0]['relevance_label']=='Zayıf eşleşme'


def test_search_provenance_without_current_scene_evidence_fails_closed():
    m=candidate('bad',C,relevance_score=90,relevance_label='İlgili')
    assert relevance.choose([m],set(),{}) is None


@pytest.mark.parametrize('missing_video',[False,True])
def test_exact_cockpit_screenshot_regression(missing_video):
    a=candidate('a',A);b=candidate('b',B);c=candidate('c',C);d=candidate('d',D,'image')
    result=relevance.choose([b,c,d,*([] if missing_video else [a])],set(),slot())
    assert result['media_id']==('d' if missing_video else 'a')
    assert relevance.evaluate(b,current())['relevance_label']=='Zayıf eşleşme'
    assert relevance.evaluate(c,current())['relevance_label']=='Zayıf eşleşme'


def test_incidental_narration_or_polluted_alternative_cannot_certify_animal_or_rail():
    s=deepcopy(AVIATION);s['narration_text']='A woman looks through a train window. A dog rests on grass in a garden.'
    s['alternative_stock_queries']+=['aircraft cockpit dog pet grass garden','aircraft cockpit woman train railway passenger window']
    p=relevance.profile(s)
    assert relevance.evaluate(candidate('b',B),p)['relevance_score']==0
    assert relevance.evaluate(candidate('c',C),p)['relevance_score']==0


@pytest.mark.parametrize('anchor,bad',[
 ('electric aircraft cockpit','electric train railway passenger'),
 ('Tokyo subway','Tokyo forest trees'),
 ('Germany electric car','Germany electric train railway'),
])
def test_shared_descriptor_or_partial_place_name_cannot_bypass_missing_subject_domain(anchor,bad):
    p=relevance.profile({'entities':[anchor],'stock_query':anchor,'visual_intent':anchor})
    assert relevance.evaluate(candidate('bad',bad),p)['relevance_label']=='Zayıf eşleşme'
    assert relevance.choose([candidate('bad',bad)],set(),{'relevance_profile':p}) is None


@pytest.mark.parametrize('expected,good,bad',[
 ('aircraft cockpit','aircraft cockpit aviation','train passenger railway'),
 ('animal pet','dog pet animal','food cooking kitchen'),
 ('food cooking','food meal cuisine','city buildings downtown'),
 ('ocean ship','ocean ship waves','pet dog garden'),
 ('mountain snow','mountain snow alpine','beach sand palm'),
 ('forest trees','forest woods trees','train railway'),
 ('beach sand','beach sand coast','mountain snow'),
 ('car charging','car vehicle charging','dog animal'),
 ('computer screen','computer display technology','food meal'),
])
def test_small_general_conflict_groups_require_actual_expected_metadata(expected,good,bad):
    p=relevance.profile({'entities':[expected],'stock_query':expected,'visual_intent':expected})
    assert relevance.evaluate(candidate('good',good),p)['relevance_score']>=relevance.MINIMUM
    assert relevance.evaluate(candidate('bad',bad),p)['relevance_label']=='Zayıf eşleşme'


def test_slightly_stronger_image_does_not_displace_related_video():
    video=candidate('video','aircraft cockpit navigation computer aviation')
    image=candidate('image','aircraft cockpit navigation computer aviation instruments','image')
    v=relevance.evaluate(video,current())['relevance_score'];i=relevance.evaluate(image,current())['relevance_score']
    assert v>=25 and 0<i-v<=relevance.VIDEO_TOLERANCE
    assert relevance.choose([image,video],set(),slot())['media_type']=='video'


def test_duplicate_variety_cannot_break_video_tolerance_or_drop_to_general_band():
    image=candidate('image',D,'image');video=candidate('reused',A)
    fresh=candidate('unused','aircraft cockpit navigation aviation')
    assert relevance.evaluate(fresh,current())['relevance_score']>=25
    used={(video['provider'],video['media_type'],video['media_id'])}
    assert relevance.choose([image,video,fresh],used,slot())['media_id']=='unused'


def test_strong_named_image_beats_only_general_video():
    p=relevance.profile(scene());s={'preferred_type':'stock_video','relevance_profile':p}
    image=candidate('image','Bermuda Triangle ocean map','image');video=candidate('video','Atlantic ocean ship waves')
    assert relevance.evaluate(image,p)['relevance_score']>=60
    # Contextual ship footage is acceptable, but a named direct match still wins.
    assert relevance.evaluate(video,p)['relevance_basis']=='contextual'
    assert relevance.evaluate(video,p)['relevance_score']<relevance.evaluate(image,p)['relevance_score']-relevance.VIDEO_TOLERANCE
    assert relevance.choose([video,image],set(),s)['media_type']=='image'


def test_soft_mix_dominates_video_without_forcing_irrelevant_video_or_image_quota():
    video=candidate('video','aircraft cockpit navigation computer aviation')
    image=candidate('image','aircraft cockpit navigation computer aviation instrument','image')
    selections=[relevance.choose([image,video] if i%4 else [image,candidate('wrong',C)],set(),slot()) for i in range(8)]
    assert sum(m['media_type']=='video' for m in selections)==6
    assert max(sum(m['media_type']=='image' for m in selections[i:i+3]) for i in range(6))<3
    assert all(m['media_id']!='wrong' for m in selections)
    assert all(relevance.choose([image,video],set(),slot())['media_type']=='video' for _ in range(8))  # 100% is allowed.


@pytest.mark.parametrize('query',[
 'modern uçak kokpit navigasyon bilgisayar ekranı dijital haritaları',
 'moderne Flugzeug Cockpit Navigation Computer Bildschirme',
 'avión cabina navegación computadora pantalla',
 'avion cabine navigation ordinateur écran',
 'modern airplane cockpit navigation computer',
])
def test_provider_queries_concise_english_without_mixed_descriptive_sentences(query):
    value=relevance.provider_query(query,AVIATION['entities'][0])
    assert 2<=len(value.split())<=6
    assert 'cockpit' in value and ('aircraft' in value or 'aviation' in value)
    assert all(w in relevance.WORDS or w=='buildings' for w in value.split())


@pytest.mark.parametrize('name',['Bermuda Triangle','Titanic','Mount Everest','Tokyo','New York','Black Sea','World War II'])
def test_provider_query_never_translates_or_splits_proper_name(name):
    value=relevance.provider_query(name+' ocean map',name)
    assert value.startswith(name) and len(value.split())<=6


@pytest.mark.parametrize('provider,kind',[('pixabay','video'),('pexels','image'),('pexels','video')])
def test_official_provider_metadata_not_query_provenance_drives_gate(provider,kind):
    item=(pixabay_item if provider=='pixabay' else pexels_item)(kind)
    if provider=='pixabay':item['tags']=C
    elif kind=='image':item['alt']=C
    else:item['url']='https://www.pexels.com/video/dog-pet-animal-grass-garden-1/'
    def respond(req):return httpx.Response(200,json={('hits' if provider=='pixabay' else 'photos' if kind=='image' else 'videos'):[item]})
    cls=PixabayStockProvider if provider=='pixabay' else PexelsStockProvider
    m=cls(KEY,transport=httpx.MockTransport(respond)).search('aircraft cockpit navigation',kind)[0]
    assert 'dog' in m['description'] and relevance.evaluate(m,current())['relevance_label']=='Zayıf eşleşme'


@pytest.mark.parametrize('studio',[SEED],indirect=True)
@pytest.mark.parametrize('available',['video','image','weak'])
def test_real_service_searches_related_videos_first_and_weak_results_never_download(studio,available):
    st=studio
    def results(q,kind):
        if kind=='video':return [candidate('a',A) if available=='video' else candidate('b',B),candidate('c',C,relevance_score=100,relevance_label='İlgili')]
        return [candidate('d',D,'image')] if available=='image' else [candidate('c',C,'image')]
    st['stock'].test_results=results;state=run(st)
    if available=='weak':
        assert not st['downloads']
        assert all(s['status']=='ai_needed' and not s['selected_media'] for s in state['slots'])
        assert all(m['relevance_label']=='Zayıf eşleşme' for s in state['slots'] for m in s['candidates'])
    else:
        assert state['slots'][0]['selected_media']['media_id']==('a' if available=='video' else 'd')
        assert all(s['selected_media'] is None for s in state['slots'][1:])
        if available=='video':
            assert st['calls'][0][1]=='video'  # Later short slots may search images after the sole unique video is reserved.
            assert state['media_mix']['video_ratio_percent']==100
        else:assert state['media_mix']['selected_images']==1
    assert state['media_mix']['video_target_range']==[80,95]
    assert all('uçak' not in q and len(q.split())<=6 for q,kind in st['calls'])
    assert KEY not in json.dumps(state)


@pytest.mark.parametrize('studio',[SEED],indirect=True)
def test_context_video_searched_before_even_highly_related_image(studio):
    st=studio
    def results(q,kind):
        if kind=='video' and 'instrument' in q:return [candidate('related',A)]
        if kind=='image':return [candidate('strong-image',D,'image')]
        return []
    st['stock'].test_results=results;state=run(st)
    assert state['slots'][0]['selected_media']['media_id']=='related'
    assert state['slots'][1]['selected_media']['media_id']=='strong-image'  # New short slot uses the distinct relevant fallback.
    assert all(s['selected_media'] is None for s in state['slots'][2:])
    assert st['calls'][0][1]=='video'
    assert len({s['selected_media']['media_id'] for s in state['slots'] if s['selected_media']})==2


@pytest.mark.parametrize('studio',[SEED],indirect=True)
def test_view_recomputes_stale_saved_label_without_replacing_asset_or_history(studio):
    st=studio;st['stock'].test_results=lambda q,kind:[candidate('wrong',C)]
    initial=view(st)
    wrong=st['stock'].downloader.download(st['pid'],candidate('wrong',C,relevance_label='İlgili',relevance_score=90))
    service=st['stock'];original=(st['root']/wrong['local_path']).read_bytes()
    with closing(service.projects._connection()) as db,db:
        state=service._load(db,st['pid'],initial['plan_id'])
        state['slots'][0].update(selected_media=wrong,status='complete',relevance_label='İlgili',relevance_score=90)
        service._save(db,state);before=db.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(st['pid'],)).fetchone()[0]
    public=view(st);m=public['slots'][0]['selected_media']
    assert m['media_id']=='wrong' and m['relevance_label']=='Zayıf eşleşme' and m['relevance_score']==0
    assert (st['root']/m['local_path']).read_bytes()==original
    with closing(service.projects._connection()) as db:
        assert db.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(st['pid'],)).fetchone()[0]==before
    rebuilt=run(st,'relevance_research')
    assert rebuilt['slots'][0]['selected_media'] is None and rebuilt['selection_history']
    assert (st['root']/wrong['local_path']).read_bytes()==original
