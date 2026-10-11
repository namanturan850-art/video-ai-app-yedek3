"""Contextual B-roll for named scenes: owner's real failure examples.

Metadata-only checks. They prove the ranking contract, not real visual content.
"""
import pytest

from app.stock import relevance

BERMUDA={'entities':['Bermuda Triangle'],'primary_stock_query':'Bermuda Triangle Atlantic Ocean',
         'alternative_stock_queries':['Bermuda Triangle map','ocean ship storm compass map'],
         'visual_intent':'ocean ship storm compass map aircraft',
         'narration_text':'Im Bermuda-Dreieck verschwanden Schiffe und Flugzeuge spurlos.'}
COCKPIT={'primary_stock_query':'modern airplane cockpit navigation computer',
         'visual_intent':'animasyonlu diyagram ataletsel navigasyon sistemi gps düzeltmesi',
         'narration_text':'Das Navigationssystem korrigiert die Position des Flugzeugs.'}


def verdict(scene,description):
    profile=relevance.profile(scene);result=relevance.evaluate({'description':description},profile)
    return result,relevance.acceptable(result,profile)


@pytest.mark.parametrize('description',['ship at sea in a storm','old nautical map and compass','cargo ship ocean waves',
                                        'airplane flying over the ocean','Schiff Meer Sturm'])
def test_named_scene_accepts_two_concrete_context_concepts_as_contextual(description):
    result,ok=verdict(BERMUDA,description)
    assert ok and result['relevance_label']=='İlgili' and result['relevance_basis']=='contextual'


@pytest.mark.parametrize('description',['ocean waves','storm over the sea','beautiful beach sand','city skyline buildings',
                                        'dog on a ship at sea','food on a boat by the ocean','triangle geometric shapes'])
def test_named_scene_rejects_single_weak_concept_or_off_topic_subject(description):
    assert not verdict(BERMUDA,description)[1]


def test_named_direct_match_always_ranks_above_contextual():
    direct,_=verdict(BERMUDA,'Bermuda Triangle ocean map');context,_=verdict(BERMUDA,'ship ocean storm compass map')
    assert direct['relevance_score']>context['relevance_score'] and direct['relevance_basis']=='direct'
    # Contextual score is capped so many matching tags cannot imitate a named match.
    assert context['relevance_score']<relevance.STRONG


@pytest.mark.parametrize('description',['dog running in park','woman sitting in a train','barber haircut salon',
                                        'computer screen technology office','gps navigation car dashboard screen'])
def test_cockpit_navigation_scene_never_accepts_owner_reported_wrong_footage(description):
    assert not verdict(COCKPIT,description)[1]


@pytest.mark.parametrize('description',['pilot in airplane cockpit','aircraft cockpit instruments navigation display'])
def test_cockpit_navigation_scene_accepts_real_cockpit_footage(description):
    assert verdict(COCKPIT,description)[1]


def test_contextual_basis_survives_media_normalization():
    from app.stock.models import normalized_media
    media={'provider':'pexels','media_type':'video','media_id':'1','source_url':'https://www.pexels.com/video/1/',
           'page_url':'https://www.pexels.com/video/1/','width':1920,'height':1080,'duration':8,'preview_url':'https://images.pexels.com/1.jpg',
           'download_url':'https://videos.pexels.com/1.mp4','query_used':'ship','relevance_label':'İlgili','relevance_basis':'contextual'}
    assert normalized_media(media)['relevance_basis']=='contextual'
