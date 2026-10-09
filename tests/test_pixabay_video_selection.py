"""Part 6 Windows regression scenarios; official external HTTP/assets mocked."""
from contextlib import closing
from copy import deepcopy
import json
import logging
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.stock import relevance
from app.stock.diagnostics import safe_query
from app.stock.models import score, rejection_reason, coverage_warning, identity, StockError
from app.stock.providers import PixabayStockProvider, PexelsStockProvider
from app.stock.service import candidate_id
from test_scripts import studio, HEADERS, KEY, OTHER_KEY
from test_production import production_studio
from test_stock_media import (stock_studio, media, pixabay_item, pexels_item,
                             STOCK_KEY, FakeStock, base, view, stamp, start, mutate)


def only_pixabay(st):
    st[0].app.state.settings.clear('pexels')
    return st[0].app.state.stock


def initial_images(st):
    stock=only_pixabay(st)
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,
        lambda name,query,kind:[] if kind=='video' else [media(str(i),name,kind,query) for i in range(1,50)])
    state=start(st)
    assert state['job']['status']=='completed'
    assert all(s['selected_media']['media_type']=='image' for s in state['slots'])
    return state


def provide_cached_videos(st, *, duration=30):
    # An old cache contains normalized results which the old tag gate rejected.
    # Re-scoring this cache is required, not another API request inside 24h.
    stock=st[0].app.state.stock
    with closing(stock.projects._connection()) as connection,connection:
        rows=connection.execute("SELECT * FROM stock_search_cache WHERE media_type='video'").fetchall()
        for row in rows:
            results=[media(str(i),'pixabay','video',row['query'],description='electric cars Germany dealership EV charging station Europe modern electric vehicle showroom',duration=duration) for i in range(1,50)]
            connection.execute('UPDATE stock_search_cache SET result_json=? WHERE project_id=? AND provider=? AND media_type=? AND query=?',
                               (json.dumps(results),row['project_id'],row['provider'],row['media_type'],row['query']))
    stock.factory=lambda *args:(_ for _ in ()).throw(AssertionError('24h cache must survive'))


def test_pixabay_unrelated_broad_tags_are_weak_and_matching_tags_are_required():
    broad=media(provider='pixabay',description='transport landscape')
    matching={**broad,'description':'electric cars transport'}
    assert score(broad,{'duration':8})==-1
    assert score(matching,{'duration':8})>score(broad,{'duration':8})
    assert score(matching,{'duration':8})>=0


def test_pexels_metadata_gate_and_contract_unchanged():
    assert score(media(provider='pexels',description='ocean dolphins'),{'duration':8})==-1
    assert score(media(provider='pexels',description='electric cars'),{'duration':8})>=0
    fixture=pexels_item()
    provider=PexelsStockProvider(STOCK_KEY,transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'videos':[fixture]})))
    assert provider.search_videos('electric cars')[0]['width']==1920


@pytest.mark.parametrize('clip,tolerance,accepted',[(7.2,1.25,True),(7.2,0,False),(6.5,1.5,True),(6.4,1.5,False),(2,1.5,False),(.01,1.5,False)])
def test_duration_tolerance_and_proportional_quality_gate(clip,tolerance,accepted):
    candidate=media(provider='pixabay',duration=clip)
    assert (score(candidate,{'duration':8},tolerance)>=0)==accepted
    if accepted:
        assert coverage_warning(candidate,{'duration':8})=='Video yuva süresinden biraz kısa'


def test_tiny_slot_does_not_accept_a_tiny_fraction_of_required_clip():
    assert rejection_reason(media(provider='pixabay',duration=.1),{'duration':.8},1.5)=='duration'


def test_720p_mp4_without_4k_or_thumbnail_is_valid():
    fixture=pixabay_item();fixture['videos']={'medium':fixture['videos']['1280']}
    fixture['videos']['medium'].pop('thumbnail')
    provider=PixabayStockProvider(STOCK_KEY,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'hits':[fixture]})))
    result=provider.search_videos('electric cars')[0]
    assert (result['width'],result['height'],result['preview_url'])==(1280,720,'')
    assert score(result,{'duration':8})>=0


def test_real_adapter_counts_normalization_and_quality_then_cache(stock_studio,caplog):
    st=stock_studio;stock=only_pixabay(st);calls=[]
    valid=pixabay_item(mid=101);valid['tags']='electric cars Germany dealership EV charging station Europe modern electric vehicle showroom'
    low=deepcopy(valid);low['id']=102
    for variant in low['videos'].values(): variant.update(width=640,height=360)
    short=deepcopy(valid);short.update(id=103,duration=.01)
    unsafe=deepcopy(valid);unsafe['id']=104
    for variant in unsafe['videos'].values():variant['url']='https://evil.example/104.mp4?token=download-private'
    malformed={'id':105,'tags':STOCK_KEY,'Authorization':STOCK_KEY}
    notmp4=deepcopy(valid);notmp4['id']=106
    for variant in notmp4['videos'].values():variant['url']='https://cdn.pixabay.com/106.webm'
    def respond(request):
        calls.append(request.url.path)
        assert request.url.path=='/api/videos/'
        return httpx.Response(200,json={'hits':[valid,low,short,unsafe,malformed,notmp4]})
    stock.factory=lambda name,settings:PixabayStockProvider(STOCK_KEY,transport=httpx.MockTransport(respond))
    caplog.set_level(logging.DEBUG)
    slot=view(st)['slots'][0]['slot_id'];state=start(st,'search',slot)
    diag=state['slots'][0]['search_diagnostics'][0]
    assert diag['raw_count']==6 and diag['normalized_count']==3 and diag['accepted_count']==1
    assert diag['rejected']=={'resolution':1,'duration':1,'relevance':0,'orientation':0,'malformed_result':2,'unsafe_url':1}
    assert diag['summary'].startswith('Pixabay video: 6 sonuç → 3 kullanılabilir → 1 uygun aday')
    assert state['slots'][0]['candidates'][0]['media_id']=='101'
    assert calls==['/api/videos/']
    cached=start(st,'search',slot)['slots'][0]['search_diagnostics'][0]
    assert cached['cached'] and cached['raw_count']==6 and calls==['/api/videos/']
    for private in (STOCK_KEY,KEY,OTHER_KEY,'download-private','evil.example','Authorization:'):
        assert private not in caplog.text and private not in json.dumps(state)
    assert 'rejected_duration=1' in caplog.text


def test_only_pixabay_relevant_video_without_exact_full_phrase(stock_studio):
    st=stock_studio;stock=only_pixabay(st);calls=[]
    def respond(request):
        calls.append(request.url.path)
        assert request.url.path=='/api/videos/'
        fixtures=[pixabay_item(mid=i) for i in range(1,50)]
        for fixture in fixtures:fixture['tags']='Germany cars dealership electric Europe station charging EV showroom vehicle modern'
        return httpx.Response(200,json={'hits':fixtures})
    stock.factory=lambda name,settings:PixabayStockProvider(STOCK_KEY,transport=httpx.MockTransport(respond))
    state=start(st)
    assert state['job']['status']=='completed'
    assert state['media_mix']['selected_videos']==len(state['slots'])
    assert state['media_mix']['selected_images']==state['media_mix']['unresolved_slots']==0
    assert calls and set(calls)=={'/api/videos/'}


def test_no_usable_video_falls_back_to_images_and_all_image_warning(stock_studio):
    st=stock_studio;stock=only_pixabay(st)
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,
        lambda name,q,kind:[media(str(i),name,kind,q,duration=.01 if kind=='video' else None) for i in range(1,50)])
    state=start(st)
    assert {k:state['media_mix'][k] for k in ('total_slots','selected_videos','selected_images','unresolved_slots','video_ratio_percent','video_target_range')}=={'total_slots':len(state['slots']),'selected_videos':0,'selected_images':len(state['slots']),'unresolved_slots':0,'video_ratio_percent':0,'video_target_range':[80,95]}
    assert any(w.startswith('Hiç stok video seçilmedi.') for w in state['warnings'])
    assert any(kind=='video' for name,kind,q in stock.test_calls) and any(kind=='image' for name,kind,q in stock.test_calls)


def test_single_video_discovery_preserves_old_image_until_download_and_restart(stock_studio):
    st=stock_studio;old=initial_images(st);provide_cached_videos(st)
    slot=old['slots'][0];path=st[3]/'projects'/st[1]['id']/slot['selected_media']['local_path']
    original=path.read_bytes();stock=st[0].app.state.stock;download=stock.downloader.download;calls=[]
    def track(*args):calls.append(args);return download(*args)
    stock.downloader.download=track
    found=start(st,'search_videos',slot['slot_id'])
    target=found['slots'][0]
    assert target['selected_media']==slot['selected_media'] and not calls
    assert target['candidates'] and all(m['media_type']=='video' for m in target['candidates'])
    assert all(d['media_type']=='video' and d['cached'] and d['raw_count'] is None for d in target['search_diagnostics'])
    selected=start(st,'select',slot['slot_id'],candidate_id=candidate_id(target['candidates'][0]))
    assert selected['job']['status']=='completed' and selected['slots'][0]['selected_media']['media_type']=='video'
    assert len(calls)==1 and path.read_bytes()==original
    assert all(a['selected_media']==b['selected_media'] for a,b in zip(old['slots'][1:],selected['slots'][1:]))
    with TestClient(create_app(st[3]),headers=HEADERS) as restarted:
        assert restarted.get(base(st)).json()['slots']==selected['slots']
        handoff=restarted.get(base(st)+'/handoff').json()
        assert handoff['contract_version']==1 and handoff['ready'] and not handoff['rendered']
    assert identity(slot['selected_media'])!=identity(target['candidates'][0])  # Same ID, distinct type.


@pytest.mark.parametrize('action',['select','replace_images'])
def test_failed_video_download_preserves_assignment_and_file(stock_studio,action):
    st=stock_studio;old=initial_images(st);provide_cached_videos(st)
    slot=old['slots'][0];path=st[3]/'projects'/st[1]['id']/slot['selected_media']['local_path'];original=path.read_bytes()
    found=start(st,'search_videos',slot['slot_id'])
    st[0].app.state.stock.downloader.transport=httpx.MockTransport(lambda request:httpx.Response(503,text=STOCK_KEY))
    state=start(st,action,slot['slot_id'] if action=='select' else None,
                **({'candidate_id':candidate_id(found['slots'][0]['candidates'][0])} if action=='select' else {}))
    assert state['job']['status']=='error'
    assert state['slots'][0]['selected_media']==slot['selected_media'] and state['slots'][0]['status']=='complete'
    assert path.read_bytes()==original and STOCK_KEY not in json.dumps(state)


def test_video_only_without_candidates_keeps_image_no_image_search(stock_studio):
    st=stock_studio;old=initial_images(st);stock=st[0].app.state.stock;before=len(stock.test_calls)
    state=start(st,'search_videos',old['slots'][0]['slot_id'])
    assert state['job']['status']=='completed' and state['slots'][0]['selected_media']==old['slots'][0]['selected_media']
    assert state['slots'][0]['candidates']==[] and 'Mevcut görsel korundu' in state['slots'][0]['message']
    assert all(kind=='video' for name,kind,q in stock.test_calls[before:])
    # Specific image discovery can finish before broader video tiers are cached.
    # First video-only search may fill them; a repeated one is fully cached.
    count=len(stock.test_calls);start(st,'search_videos',old['slots'][0]['slot_id']);assert len(stock.test_calls)==count


def test_bulk_replacement_keeps_locked_and_intentional_images_files_and_script(stock_studio):
    st=stock_studio;old=initial_images(st);stock=st[0].app.state.stock
    script=st[0].get(base(st).removesuffix('/stock')).json()
    mutate(st,old['slots'][0]['slot_id'],'lock')
    with closing(stock.projects._connection()) as connection,connection:
        saved=stock._load(connection,st[1]['id'],old['plan_id'])
        saved['slots'][1]['preferred_type']='stock_image'
        stock._save(connection,saved)
    provide_cached_videos(st)
    before=view(st);paths=[st[3]/'projects'/st[1]['id']/s['selected_media']['local_path'] for s in before['slots']]
    originals=[p.read_bytes() for p in paths]
    result=start(st,'replace_images')
    assert result['job']['status']=='completed'
    assert result['slots'][:2]==before['slots'][:2]
    assert all(s['selected_media']['media_type']=='video' for s in result['slots'][2:])
    assert [p.read_bytes() for p in paths]==originals
    assert st[0].get(base(st).removesuffix('/stock')).json()==script
    assert result['media_mix']['selected_images']==2
    assert all(d['media_type']=='video' for d in result['job']['progress']['search_diagnostics'])
    locked=st[0].post(base(st)+f'/slots/{before["slots"][0]["slot_id"]}/jobs',json={**stamp(st),'action':'search_videos'})
    assert locked.status_code==409 and locked.json()['category']=='locked'


def test_short_selected_clip_handoff_warning_no_trim_no_render(stock_studio):
    st=stock_studio;old=initial_images(st);provide_cached_videos(st)
    slot=next(s for s in old['slots'] if s['duration']>4)
    stock=st[0].app.state.stock
    with closing(stock.projects._connection()) as connection,connection:
        saved=stock._load(connection,st[1]['id'],old['plan_id'])
        next(s for s in saved['slots'] if s['slot_id']==slot['slot_id']).pop('pacing_version',None)  # Existing Part 9.6 short-source tolerance remains supported.
        stock._save(connection,saved)
        rows=connection.execute("SELECT * FROM stock_search_cache WHERE media_type='video'").fetchall()
        for row in rows:
            clips=json.loads(row['result_json'])
            for clip in clips:clip['duration']=slot['duration']-.8
            connection.execute('UPDATE stock_search_cache SET result_json=? WHERE project_id=? AND provider=? AND media_type=? AND query=?',
                               (json.dumps(clips),row['project_id'],row['provider'],row['media_type'],row['query']))
    found=start(st,'search_videos',slot['slot_id']);target=next(s for s in found['slots'] if s['slot_id']==slot['slot_id'])
    selected=start(st,'select',slot['slot_id'],candidate_id=candidate_id(target['candidates'][0]))
    target=next(s for s in selected['slots'] if s['slot_id']==slot['slot_id'])
    assert target['coverage_warning']=='Video yuva süresinden biraz kısa' and not target['trim_needed']
    handoff=st[0].get(base(st)+'/handoff').json();target=next(s for s in handoff['slots'] if s['slot_id']==slot['slot_id'])
    assert not target['trim_needed'] and target['coverage_warning']=='Video yuva süresinden biraz kısa'
    assert handoff['ready'] and not handoff['rendered']


@pytest.mark.parametrize('value',[-1,1.6,'1.25',True,None,[]])
def test_duration_tolerance_validation(stock_studio,value):
    st=stock_studio
    result=st[0].post(base(st)+'/jobs',json={**stamp(st),'action':'auto','video_duration_tolerance_seconds':value})
    assert result.status_code==422 and 'toleransı' in result.json()['message']


def test_duration_tolerance_configuration_persists(stock_studio):
    st=stock_studio;slot=view(st)['slots'][0]['slot_id']
    state=start(st,'search',slot,video_duration_tolerance_seconds=.5)
    assert state['search_options']['video_duration_tolerance_seconds']==.5
    with TestClient(create_app(st[3]),headers=HEADERS) as restarted:
        assert restarted.get(base(st)).json()['search_options']==state['search_options']


def test_used_video_is_excluded_unique_image_then_unresolved(stock_studio):
    st=stock_studio;stock=only_pixabay(st)
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,
        lambda name,q,kind:[media('only-video' if kind=='video' else 'new-image',name,kind,q,
            description='electric cars Germany dealership EV charging station Europe modern electric vehicle showroom')])
    state=start(st)
    assert state['slots'][0]['selected_media']['media_type']=='video'
    assert state['slots'][1]['selected_media']['media_type']=='image'
    assert all(s['selected_media'] is None for s in state['slots'][2:])
    assert any(kind=='image' for name,kind,q in stock.test_calls)
    assert not any(s['manual_reuse'] for s in state['slots'] if s['selected_media'])


def test_specific_tier_precedes_broader_video_fallback(stock_studio):
    st=stock_studio;stock=only_pixabay(st);slot=view(st)['slots'][0]
    stock.factory=lambda name,settings:FakeStock(name,stock.test_calls,
        lambda name,q,kind:[] if q==relevance.provider_query(slot['subject_anchor'],slot['subject_anchor']) else [media('alternate',name,kind,q,description='electric cars Germany dealership EV charging station Europe modern electric vehicle showroom')])
    state=start(st,'search',slot['slot_id'])
    assert state['slots'][0]['candidates'],(slot,stock.test_calls,state['job'])
    assert state['slots'][0]['candidates'][0]['media_type']=='video'
    assert state['slots'][0]['candidates'][0]['query_used']!=stock.test_calls[0][2]
    assert state['slots'][0]['candidates'][0]['relevance_score']>=relevance.MINIMUM
    assert stock.test_calls[0][1]=='video'


def test_all_malformed_response_has_safe_diagnostics_preserves_old_image(stock_studio,caplog):
    st=stock_studio;old=initial_images(st);stock=st[0].app.state.stock
    with closing(stock.projects._connection()) as connection,connection:
        connection.execute("UPDATE stock_search_cache SET created_at='2000-01-01T00:00:00+00:00'")
    caplog.set_level(logging.DEBUG)
    stock.factory=lambda name,settings:PixabayStockProvider(STOCK_KEY,transport=httpx.MockTransport(
        lambda r:httpx.Response(200,json={'hits':[{'id':1,'body':STOCK_KEY}]})))
    state=start(st,'search_videos',old['slots'][0]['slot_id'])
    assert state['job']['status']=='error' and state['slots'][0]['selected_media']==old['slots'][0]['selected_media']
    diag=state['slots'][0]['search_diagnostics'][0]
    assert diag['raw_count']==1 and diag['normalized_count']==diag['accepted_count']==0
    assert diag['rejected']['malformed_result']==1 and diag['category']=='invalid_response'
    assert STOCK_KEY not in caplog.text and STOCK_KEY not in json.dumps(state)


def test_37_existing_images_visible_preserved_and_missing_counted(stock_studio):
    st=stock_studio;old=initial_images(st);stock=st[0].app.state.stock
    with closing(stock.projects._connection()) as connection,connection:
        saved=stock._load(connection,st[1]['id'],old['plan_id'])
        # Upgrade an existing saved assignment record. No new download/rebuild.
        saved['slots']=[{**deepcopy(saved['slots'][i%len(saved['slots'])]),'slot_id':f'existing-{i}'} for i in range(37)]
        stock._save(connection,saved)
    state=view(st)
    assert {k:state['media_mix'][k] for k in ('total_slots','selected_videos','selected_images','unresolved_slots','video_ratio_percent','video_target_range')}=={'total_slots':37,'selected_images':37,'selected_videos':0,'unresolved_slots':0,'video_ratio_percent':0,'video_target_range':[80,95]}
    assert any(w.startswith('Hiç stok video seçilmedi.') for w in state['warnings'])
    with TestClient(create_app(st[3]),headers=HEADERS) as restarted:
        assert restarted.get(base(st)).json()['slots']==state['slots']
    path=st[3]/'projects'/st[1]['id']/state['slots'][0]['selected_media']['local_path'];path.unlink()
    missing=view(st)
    affected=sum(s['selected_media']['local_path']==state['slots'][0]['selected_media']['local_path'] for s in state['slots'])
    assert missing['media_mix']['unresolved_slots']==affected


@pytest.mark.parametrize('query',[STOCK_KEY,quote(STOCK_KEY),f'https://cdn.pixabay.com/v.mp4?token=private','token: private',quote('https://cdn.pixabay.com/a?key=private')])
def test_diagnostic_query_redacts_keys_urls_and_download_tokens(query):
    safe=safe_query(query,(STOCK_KEY,))
    assert STOCK_KEY not in safe and 'private' not in safe and 'https://' not in safe
