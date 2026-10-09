"""Live-owner regressions. Official APIs remain mocked; no live claims."""
from contextlib import closing
from copy import deepcopy
import pytest
from app.stock import relevance
from app.stock.identities import identity_keys
from test_stock_media import media
from test_media_relevance import studio,view,run

OWNER={'search_anchor':'belgesel tarzı röportaj eski','primary_stock_query':"eski siyah beyaz fotoğraf vintage uçak kokpiti yorgun mürettebat 1930",
       'visual_intent':'Geçmişteki mürettebat koşulları yorgunluk alkol ile modern düzenlenmiş ortamlar arasındaki fark',
       'alternative_stock_queries':['aircraft cockpit pilot crew vintage'],'entities':[]}

@pytest.mark.parametrize('style',['documentary style interview old','belgesel tarzı röportaj eski','dokumentarisch interview alt','documental entrevista antiguo','documentaire entretien ancien'])
def test_style_never_subject(style):
    p=relevance.profile({**OWNER,'search_anchor':style,'entities':[style]})
    assert p['specificity']=='domain_specific'
    assert set(p['anchor_tokens'])&{'aircraft','crew','cockpit'}
    assert not set(relevance.tokens(style))&set(p['anchor_tokens'])
    assert all(len(q.split())<=5 for _,q in relevance.queries_for(p))

@pytest.mark.parametrize('description',['man barber haircut people','sunset ocean landscape','train railway crew','documentary interview old people'])
def test_owner_wrong_person_landscape_rejected(description):
    p=relevance.profile(OWNER)
    assert relevance.choose([media(description=description)],set(),{'relevance_profile':p}) is None


def test_owner_related_aircraft_accepted_and_unique_alternative_wins():
    p=relevance.profile(OWNER);slot={'relevance_profile':p};a=media('a',description='aircraft cockpit pilot crew vintage');b=media('b',description='aircraft cockpit crew')
    assert relevance.choose([a,b],identity_keys(a),slot)['media_id']=='b'
    assert relevance.choose([a],identity_keys(a),slot) is None

@pytest.mark.parametrize('field',['page_url','source_url','download_url','sha256'])
def test_aliases_and_byte_hash_cannot_evade_reuse(field):
    a=media('a',description='aircraft cockpit crew');b=media('b',description='aircraft cockpit crew')
    if field=='sha256':a[field]=b[field]='a'*64
    else:b[field]=a[field]+'?tracking=harmless'
    assert relevance.choose([b],identity_keys(a),{'relevance_profile':relevance.profile(OWNER)}) is None


def test_generic_ocean_can_use_genuinely_matching_metadata():
    p=relevance.profile({'stock_query':'stormy ocean','visual_intent':'ocean storm waves'})
    assert p['specificity']=='generic_visual'
    assert relevance.choose([media(description='ocean storm waves')],set(),{'relevance_profile':p})


def test_rescan_deduplicates_old_unlocked_selections_preserves_files(studio):
    st=studio;st['stock'].test_results=lambda q,kind:[media('same','pixabay',kind,q,description='Bermuda Triangle ocean')]
    old=run(st);first=old['slots'][0]['selected_media'];path=st['root']/first['local_path'];before=path.read_bytes()
    with closing(st['stock'].projects._connection()) as db,db:
        state=st['stock']._load(db,st['pid'],old['plan_id'])
        for slot in state['slots']:slot.update(selected_media=deepcopy(first),status='complete')
        st['stock']._save(db,state)
    result=run(st,'relevance_research')
    assert result['slots'][0]['selected_media']['media_id']=='same'
    assert all(s['selected_media'] is None for s in result['slots'][1:])
    assert path.read_bytes()==before and result['selection_history']


def test_two_locked_duplicates_are_untouched_and_warn(studio):
    st=studio;st['stock'].test_results=lambda q,kind:[media('same','pixabay',kind,q,description='Bermuda Triangle ocean')]
    old=run(st);first=old['slots'][0]['selected_media']
    with closing(st['stock'].projects._connection()) as db,db:
        state=st['stock']._load(db,st['pid'],old['plan_id'])
        for slot in state['slots']:slot.update(selected_media=deepcopy(first),status='complete',locked=True)
        st['stock']._save(db,state)
    result=run(st,'relevance_research')
    assert all(s['locked'] and s['selected_media']==first for s in result['slots'])
    assert 'Aynı medya birden fazla kilitli alanda kullanılıyor.' in result['warnings']

@pytest.mark.parametrize('name',['Black Sea','World War II'])
def test_named_subject_with_style_like_word_remains_named_and_requires_evidence(name):
    p=relevance.profile({'entities':[name],'stock_query':name+' ocean map','visual_intent':name+' ocean map'})
    assert p['subject_anchor']==name and p['specificity']=='named_specific'
    assert relevance.choose([media(description='Atlantic ocean map ship')],set(),{'relevance_profile':p}) is None
    assert relevance.choose([media(description=name+' ocean map')],set(),{'relevance_profile':p})
