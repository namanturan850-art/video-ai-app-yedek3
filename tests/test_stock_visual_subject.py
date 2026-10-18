from types import SimpleNamespace
from app.stock.visual_subject import analyze, contradiction
from app.stock.shot import bind
from app.stock import relevance
from app.stock.director_media import MediaDirector, key
from app.stock.setting import infer, for_scene


def scene(text):
    return {'scene_id':'s','narration_text':text,'start_estimate':0,'end_estimate':5,
            'primary_stock_query':'São Paulo skyline','entities':['São Paulo']}


def slot():
    return {'estimated_start':0,'estimated_end':5,'duration':5,'search_query':'huge lake surface night reflection'}


def test_lake_lightning_queries_include_the_event_without_invented_location():
    bound=bind(scene('Cuanto más grande el lago, más rayos. La relación es casi lineal.'),slot(),'es')
    queries=[bound['primary_stock_query'],*bound['alternative_stock_queries']]
    assert queries[0]=='lightning lake'
    assert 'lake aerial view' in queries
    assert not any('Venezuela' in q or 'night' in q for q in queries)
    assert not bound['entities']


def test_university_is_attribution_not_visual_subject_or_scene_geography():
    text='São Paulo Üniversitesi tarafından yapılan bir araştırma onlarca tropikal gölü karşılaştırdı. İki faktör: gölün büyüklüğü ve yakındaki dağlar.'
    bound=bind({**scene(text),'location':'São Paulo'},slot(),'tr')
    assert 'lake' in bound['primary_stock_query']
    assert 'São Paulo' not in bound['entities']
    assert bound['location']==''
    assert bound['visual_subject']['institutions']==['São Paulo Üniversitesi']
    assert bound['narration_text']==text
    setting=infer(['Venezuela tropical lake',text], 'Venezuela')
    assert for_scene(setting,text)['regions']==setting['regions']
    assert not for_scene(setting,text).get('scene_override')
    profile=relevance.profile(bound,slot())
    assert contradiction({'description':'São Paulo city skyline buildings'},profile)
    assert relevance.evaluate({'description':'São Paulo city skyline'},profile)['relevance_score']==0


def test_attribution_removal_is_conservative_and_explicit_visual_hint_wins():
    assert not analyze('São Paulo Üniversitesi binası şehir merkezinde.')['institutions']
    sc=scene('São Paulo Üniversitesi tropikal gölleri araştırdı.')
    sc['owner_hints']=[{'type':'visual','value':'university campus buildings'}]
    assert 'campus' in bind(sc,slot(),'en')['primary_stock_query']


def test_waterfall_is_not_wind_or_current_even_with_positive_visual_analysis():
    bound=bind(scene('Ve kara rüzgârları tüm kıyılardan merkeze doğru eser. Tüm bu akıntılar ılık suyun üzerinde buluşur.'),slot(),'tr')
    profile=relevance.profile(bound,slot())
    media={'description':'waterfall water river','source_metadata':{'visual_analysis':{'verdict':'match'}}}
    assert relevance.evaluate(media,profile)['relevance_score']==0


def test_low_clip_needs_independent_strong_evidence_and_query_is_not_evidence():
    director=MediaDirector.__new__(MediaDirector)
    sc=bind(scene('lake wind current'),slot(),'en')
    s=slot();s['relevance_profile']=relevance.profile(sc,s)
    wrong={'provider':'pixabay','media_id':'wrong','media_type':'video','description':'waterfall water lake',
           'query_used':'lake wind current','clip':{'score':5}}
    good={**wrong,'media_id':'good','description':'lake wind current surface'}
    decisions=director.local_judge(s,sc,[wrong,good])
    assert not decisions[key(wrong)]['approved']
    assert decisions[key(good)]['approved']
    assert 'güçlü' in decisions[key(good)]['reason']


def test_high_clip_cannot_override_an_explicit_subject_conflict():
    import base64
    director=MediaDirector.__new__(MediaDirector)
    sc=bind(scene('lake wind current'),slot(),'en');s={**slot(),'order':1}
    media={'provider':'pixabay','media_id':'fall','media_type':'video','description':'waterfall river water'}
    from app.stock.director_media import key_text
    director.clip=SimpleNamespace(ready=lambda:True,score=lambda *a:{key_text(media):{'verdict':'match','score':9}},broken=False,metrics={})
    director.frames=lambda m:[{'source':{'data':base64.b64encode(b'fake frame bytes').decode()}}]
    director.where=lambda sc:{};director.language='en';director.progress={};director.pid='test';director.job={}
    director.service=SimpleNamespace(projects=None,_checkpoint=lambda *a,**kw:None)
    # directory() is only needed to hand a cache path to the mocked CLIP scorer.
    from unittest.mock import patch
    with patch('app.stock.director_media.directory',return_value=None):
        decision=director.clip_judge(s,sc,[media],descriptor='lake wind current')[key(media)]
    assert not decision['approved'] and decision['score']==0


def test_correct_named_archive_can_survive_uncertain_clip_with_explicit_reason():
    director=MediaDirector.__new__(MediaDirector)
    sc={'primary_stock_query':'Titanic ship ocean','visual_intent':'Titanic ship ocean','entities':['Titanic']}
    s={'relevance_profile':relevance.profile(sc)}
    media={'provider':'wikimedia','media_id':'archive','media_type':'image','description':'Titanic ship ocean archival photograph','clip':{'score':5}}
    verdict=director.local_judge(s,sc,[media])[key(media)]
    assert verdict['approved'] and verdict['local'] and not verdict.get('clip_approved')
    assert 'güçlü' in verdict['reason']


def test_spanish_research_does_not_turn_lakes_into_lagos_or_institution_into_brazil():
    from app.stock.setting import infer, for_scene
    text=('Un estudio de la Universidad de São Paulo comparó decenas de lagos tropicales. '
          'Encontró que dos factores pesan mucho: el tamaño del lago y las montañas cercanas.')
    sc={**scene(text),'entities':['Sao Paulo','Lagos'],'location':'Sao Paulo'}
    bound=bind(sc,slot(),'es')
    assert relevance.profile(bound,slot())['subject_anchor']=='lake mountain'
    assert bound['entities']==[] and bound['location']==''
    assert 'Lagos' not in bound['primary_stock_query']
    setting=infer(['Venezuela Maracaibo',text],'Venezuela')
    assert for_scene(setting,text)['regions']==setting['regions']


def test_lowercase_basin_and_currents_are_not_city_names_but_real_places_survive():
    for word in ('cuenca','corrientes','lagos'):
        analyzed=analyze('Observamos '+word+' tropicales.')
        assert word in analyzed['ambiguous_places']
        assert word not in analyzed['location_text']
        assert word.title() not in analyzed['query_text']
    for name in ('Lagos','Corrientes','Cuenca','Black Sea','black sea'):
        assert name in analyze('Travel to '+name+'.')['location_text']
