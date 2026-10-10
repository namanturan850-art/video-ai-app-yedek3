"""Part 9.8. Mocks prove contracts, not owner/live visual-model quality."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.rendering import reflow,timeline,smart_edit,files
from app.rendering.models import options
from app.stock import recovery,relevance
from app.stock.models import make_slots,StockError
from app.integrations.openmontage import visual
from app.integrations.openmontage.visual_engine import model_status,inference
from test_stock_media import studio,stock_studio,media,view
from test_rendering import ready,url,synthetic,contract,install_ready


def owner_fixture(tmp_path):
    root=tmp_path/'project';(root/'stock').mkdir(parents=True)
    slots=[];raw=[];scenes=[];metadata=[];missing={2,6,10,14,18,22,26,30,34,38,42,46,50}
    for i in range(11):
        scenes.append({'scene_id':str(i),'start':193*i/11,'end':193*(i+1)/11})
        metadata.append({'scene_id':str(i),'narration_text':'Aircraft cockpit instruments show navigation information.',
                         'primary_stock_query':'aircraft cockpit instruments','visual_intent':'aircraft cockpit navigation',
                         'alternative_stock_queries':['aircraft instruments'],'transition':'hard_cut','motion':'none'})
    for i in range(55):
        start=193*i/55;end=193*(i+1)/55;sid=str(i);m=None
        if i not in missing:
            filename=uuid4().hex+'.mp4';data=b'unit-cache-'+str(i).encode();(root/'stock'/filename).write_bytes(data)
            sha=hashlib.sha256(data).hexdigest()
            m={**media(sid,description='aircraft cockpit instruments',duration=22),'local_path':'stock/'+filename,
               'file_size':len(data),'sha256':sha,'content_type':'video/mp4'}
        s={'slot_id':sid,'scene_id':str(i//5),'order':i%5+1,'start':start,'end':end,'duration':end-start,
           'status':'complete' if m else 'pending','locked':False,
           'selected_media_local_identity':{k:m[k] for k in ('provider','media_id','media_type','local_path')} if m else None}
        r={**s,'estimated_start':start,'estimated_end':end,'selected_media':m,
           'local_validation':{'sha256':m['sha256'],'media_type':'video','duration':22,'width':1920,'height':1080} if m else {},
           'candidates':[],'warnings':[],'message':'','preferred_type':'stock_video','search_query':'aircraft cockpit instruments'}
        slots.append(s);raw.append(r)
    h={'project_id':'pid','contract_version':1,'ready':False,'source_script_version_id':'s','scene_plan_id':'p',
       'narration_version_id':'voice','subtitle_version_id':'subs','audio_duration':193,'scenes':scenes,'stock_slots':slots,'subtitles':[]}
    p={'source_script_version_id':'s','plan_id':'p','scenes':metadata}
    projects=SimpleNamespace(_path=lambda pid:root)
    return h,p,{'slots':raw},projects


def test_realistic_55_42_reflow_preserves_all_sources_and_193_seconds(tmp_path):
    h,p,state,projects=owner_fixture(tmp_path)
    h['warnings']=['Bazı stok medya yuvaları veya yerel dosyaları henüz hazır değil.','Altyazı metni farklı.']
    before=deepcopy((h,p,state))
    effective,report=reflow.build(h,p,state,projects,files.sha256)
    assert report['raw_stock_slots']==55 and report['selected_stock_assets']==42 and report['unresolved_raw_slots']==13
    assert report['effective_render_segments']==42 and report['render_ready'] and report['effective_uncovered_duration']==0
    t=timeline.build(effective,p)
    assert t['duration']==193 and sum(s['frames'] for s in t['slots'])==5790
    assert len({s['selected_media_local_identity']['media_id'] for s in t['slots']})==42
    assert all(s['duration']<=7.5 for s in t['slots'])
    assert all(s['end']==pytest.approx(n['start']) for s,n in zip(t['slots'],t['slots'][1:]))
    assert (h,p,state)==before and effective['subtitles']==h['subtitles']
    assert effective['warnings']==['Altyazı metni farklı.']


@pytest.mark.parametrize('change',['locked_gap','locked_anchor','short_source','anchor_short','missing_file','bad_hash','unverified','visual_mismatch'])
def test_reflow_refuses_unsafe_gaps(tmp_path,change):
    h,p,state,projects=owner_fixture(tmp_path)
    if change=='locked_gap':h['stock_slots'][2]['locked']=state['slots'][2]['locked']=True
    elif change=='locked_anchor':
        for i in (1,3):h['stock_slots'][i]['locked']=state['slots'][i]['locked']=True
    elif change in ('short_source','anchor_short'):
        for s in state['slots']:
            if s['selected_media']:s['local_validation']['duration']=3.6 if change=='short_source' else 1
    elif change=='missing_file':
        h['stock_slots'][0]['locked']=state['slots'][0]['locked']=True
        (projects._path('pid')/state['slots'][0]['selected_media']['local_path']).unlink()
    elif change=='bad_hash':
        h['stock_slots'][0]['locked']=state['slots'][0]['locked']=True
        state['slots'][0]['selected_media']['sha256']='bad'
    elif change=='unverified':
        for s in state['slots']:s.pop('local_validation',None)
    else:
        for s in state['slots']:s['visual_check']={'verdict':'mismatch'}
    effective,report=reflow.build(h,p,state,projects,files.sha256)
    assert not report['render_ready'] and report['effective_uncovered_duration']>0
    assert not effective['ready']


def test_locked_interval_is_unchanged_in_successful_reflow(tmp_path):
    h,p,state,projects=owner_fixture(tmp_path)
    h['stock_slots'][20]['locked']=state['slots'][20]['locked']=True
    effective,report=reflow.build(h,p,state,projects,files.sha256)
    locked=next(s for s in effective['stock_slots'] if s['slot_id']=='20')
    assert (locked['start'],locked['end'])==(h['stock_slots'][20]['start'],h['stock_slots'][20]['end'])
    assert locked['raw_slot_ids']==['20']


def test_never_merge_across_semantic_scene_boundaries(tmp_path):
    h,p,state,projects=owner_fixture(tmp_path)
    for i in range(5):state['slots'][i]['selected_media']=None;state['slots'][i]['status']='pending'
    effective,report=reflow.build(h,p,state,projects,files.sha256)
    assert not report['render_ready']
    assert all(s['scene_id']=='0' for s in effective['stock_slots'] if s['end']<=193/11+.001)


def test_exact_fact_graphic_is_restrained_and_not_invented(tmp_path):
    h,p,state,projects=owner_fixture(tmp_path)
    # No asset in scene zero; only one short real numerical cue is eligible.
    for i in range(5):state['slots'][i].update(selected_media=None,status='pending')
    h['subtitles']=[{'start':0,'end':3,'text':'193 Sekunden erklären das Thema.'}]
    p['scenes'][0]['narration_text']='193 Sekunden erklären das Thema.'
    effective,report=reflow.build(h,p,state,projects,files.sha256)
    graphics=[s for s in effective['stock_slots'] if s.get('graphic_text')]
    assert len(graphics)==1 and graphics[0]['graphic_text']==h['subtitles'][0]['text']
    assert report['graphic_seconds']<=193*.2 and not report['render_ready']
    p['scenes'][0]['narration_text']='No numeric factual source.'
    assert not any(s.get('graphic_text') for s in reflow.build(h,p,state,projects,files.sha256)[0]['stock_slots'])


def test_reflow_binding_is_invalidated_by_time_lock_or_asset_change(tmp_path):
    h,p,state,projects=owner_fixture(tmp_path)
    state['recovery_plan']={'binding':reflow.binding(h,state),'version_id':'v1'}
    assert reflow.project(h,p,state,projects,files.sha256)[1]['render_ready']
    state['slots'][0]['locked']=True
    assert reflow.project(h,p,state,projects,files.sha256)[1]['stale']


def test_default_primary_is_real_external_and_local_is_manual(ready):
    # Bypass native-regression client defaults to exercise the actual route.
    from fastapi.testclient import TestClient
    with TestClient(ready['client'].app,headers=ready['client'].headers) as c:
        state=c.get(url(ready)).json()
        assert state['montage_engine']=='openmontage' and not state['ready']
        assert 'kurulmamış' in state['readiness']['blockers'][0]['message']
        assert c.get(url(ready),params={'montage_engine':'native'}).json()['ready']
        assert c.post(url(ready)+'/jobs',json={}).json()['category']=='openmontage_unavailable'
    assert options({})['montage_engine']=='openmontage'


def test_missing_diagnostics_use_actual_counts_and_no_secret_values():
    s={'status':'pending','selected_media':None,'search_diagnostics':[
        {'category':'none','normalized_count':4,'accepted_count':2,'available_count':0,'rejected':{'orientation':1,'relevance':1}}]}
    reasons=recovery.evidence(s)
    assert set(reasons)=={'all_candidates_duplicates','portrait_or_resolution_rejected','all_candidates_irrelevant'}
    assert 'query_exhausted' not in reasons
    result=recovery.report([{**s,'missing_reasons':reasons},{'status':'complete','selected_media':{'media_id':'safe'}}])
    assert result['raw_stock_slots']==2 and result['selected_stock_assets']==1
    assert 'Authorization' not in json.dumps(result)


def test_progressive_pages_never_repeat_same_cached_query(studio,monkeypatch):
    service=studio[0].app.state.stock;pid=studio[1]['id']
    scene={'scene_id':'s','primary_stock_query':'aircraft cockpit','visual_intent':'aircraft instruments','alternative_stock_queries':['aircraft flight deck']}
    monkeypatch.setattr(service,'_handoff',lambda pid:{'scenes':[scene]})
    monkeypatch.setattr(service,'_checkpoint',lambda *a,**kw:None)
    service.settings.save('pixabay',{'api_key':'test-page-key'})
    calls=[]
    def search(pid,name,kind,q,*,page=1):calls.append((name,kind,q,page));return [],{'raw_count':0,'normalized_count':0,'rejected':{'malformed_result':0,'unsafe_url':0}},True
    monkeypatch.setattr(service,'_cache_search',search)
    slot={'slot_id':'s','scene_id':'s','duration':3.5,'search_query':'aircraft cockpit','candidates':[]}
    for _ in range(12):recovery.search(service,pid,slot,set(),{}, {'project_id':pid})
    assert len(calls)==len(set(calls)) and any(c[-1]>1 for c in calls)
    assert 'query_exhausted' in slot['missing_reasons']
    before=len(calls);recovery.search(service,pid,slot,set(),{}, {'project_id':pid});assert len(calls)==before


def test_rate_limit_is_not_persisted_as_permanent_empty_results(studio,monkeypatch):
    service=studio[0].app.state.stock;pid=studio[1]['id'];service.settings.save('pexels',{'api_key':'rate-test'})
    monkeypatch.setattr(service,'_handoff',lambda pid:{'scenes':[{'scene_id':'s','visual_intent':'ocean','primary_stock_query':'ocean'}]})
    monkeypatch.setattr(service,'_checkpoint',lambda *a,**kw:None)
    monkeypatch.setattr(service,'_cache_search',lambda *a,**kw:(_ for _ in ()).throw(StockError('rate_limit','Safe rate limit')))
    s={'scene_id':'s','duration':3,'candidates':[]};progress={}
    recovery.search(service,pid,s,set(),progress,{})
    assert 'provider_rate_limited' in s['missing_reasons'] and not s['recovery_attempts']
    assert progress['limited_providers']==['pexels']


@pytest.mark.parametrize('subject,wrong',[('aircraft cockpit instruments','dog grass'),('aircraft cockpit instruments','train passenger'),
    ('aircraft crew','barbershop haircut'),('Bermuda Triangle ocean','city skyline'),('historical aircraft crew','beach sunset')])
def test_real_frame_mismatch_overrules_polluted_tags(subject,wrong):
    profile=relevance.profile({'primary_stock_query':subject,'visual_intent':subject})
    good={**media('good',description=subject),'source_metadata':{'visual_analysis':{'verdict':'match'}}}
    bad={**media('wrong',description=subject),'source_metadata':{'visual_analysis':{'verdict':'mismatch','subject':wrong}}}
    assert relevance.evaluate(bad,profile)['relevance_score']==0
    slot={'duration':3.5,'relevance_profile':profile}
    candidates=[relevance.annotate(m,profile,1,subject) for m in (bad,good)]
    assert relevance.choose(candidates,set(),slot)['media_id']=='good'


def test_model_unavailable_degrades_honestly_without_frame_call(studio,monkeypatch):
    b=studio[0].app.state.stock.openmontage
    monkeypatch.setattr(b,'status',lambda:{'semantic_ready':False})
    monkeypatch.setattr(b,'call',lambda *a:pytest.fail('No model/weight download during analysis'))
    checked=visual.analyse(b,studio[1]['id'],media('x'),relevance.profile({'visual_intent':'aircraft'}))
    assert checked['source_metadata']['visual_analysis']['verdict']=='not_available'


def test_visual_cache_binds_sha_descriptor_and_model_and_never_leaks_key(studio,monkeypatch):
    b=studio[0].app.state.stock.openmontage;pid=studio[1]['id'];root=b.projects._path(pid)/'stock'
    path=root/(uuid4().hex+'.mp4');path.write_bytes(b'cached-media')
    m={**media('x'),'local_path':'stock/'+path.name,'file_size':path.stat().st_size,'sha256':files.sha256(path)}
    monkeypatch.setattr(b,'status',lambda:{'semantic_ready':True,'semantic_model_version':'model-v1'})
    calls=[]
    def call(op,inputs,work):calls.append(inputs);return {'results':[{'sha256':m['sha256'],'verdict':'match','model_version':'model-v1'}]}
    monkeypatch.setattr(b,'call',call);profile=relevance.profile({'visual_intent':'aircraft cockpit','primary_stock_query':'aircraft cockpit'})
    assert visual.analyse(b,pid,m,profile)['source_metadata']['visual_analysis']['verdict']=='match'
    visual.analyse(b,pid,m,profile);assert len(calls)==1
    assert str(root) not in next(root.glob('visual-*.json')).read_text()
    profile['visual_goal']='aircraft crew';visual.analyse(b,pid,m,profile);assert len(calls)==2


def test_offline_model_setup_requires_real_manifest(tmp_path):
    assert model_status(tmp_path) is None
    folder=tmp_path/'.models'/'clip-vit-base-patch32';folder.mkdir(parents=True)
    (folder/'avs-model.json').write_text('{}')
    assert model_status(tmp_path) is None


def test_cuda_failure_retries_cpu_once_without_cloud_download():
    cuda=SimpleNamespace(is_available=lambda:True);torch=SimpleNamespace(cuda=cuda)
    clip=SimpleNamespace(_DEVICE='cuda',_MODEL='old',_PROCESSOR='old');calls=[]
    def compute(value):
        calls.append(cuda.is_available())
        if cuda.is_available():raise RuntimeError('CUDA unsupported')
        return 'cpu-result'
    assert inference(compute,[],clip,torch)=='cpu-result' and calls==[True,False] and cuda.is_available()


def test_smart_job_preserves_selections_and_persists_version_without_keys(ready):
    import time
    from app.stock.service import fingerprint
    c=ready['client'];service=c.app.state.stock;pid=ready['pid'];p=service.production.handoff(pid)
    with closing(service.projects._connection()) as db,db:
        state=json.loads(db.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone()[0])
        state.update(handoff_fingerprint=fingerprint(p),bindings={},warnings=[])
        for slot in state['slots']:
            existing=slot['selected_media']
            slot['selected_media']={**media(existing['media_id'],media_type=existing['media_type'],
                width=320 if existing['media_type']=='video' else 240,
                height=240 if existing['media_type']=='video' else 320),**existing}
        originals=deepcopy([s['selected_media'] for s in state['slots']])
        db.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(state),pid))
    state=service.view(pid)
    before_fingerprint=c.app.state.rendering._inputs(pid,options({'montage_engine':'native'}))['fingerprint']
    job=service.start(pid,{'plan_id':state['plan_id'],'revision':state['revision'],'action':'smart_recovery'})
    service.futures[job['job_id']].result(timeout=30)
    result=service.view(pid)
    assert result['job']['status']=='completed',result['job']
    with closing(service.projects._connection()) as db:
        stored=json.loads(db.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone()[0])
    assert [s['selected_media'] for s in stored['slots']]==originals
    assert result['recovery_report']['render_ready'] and result['recovery_plan']['version_id']
    assert list((ready['root']/'stock').glob('recovery-*.json'))
    assert c.get(url(ready),params={'montage_engine':'native'}).json()['ready']
    assert c.app.state.rendering._inputs(pid,options({'montage_engine':'native'}))['fingerprint']==before_fingerprint
    assert all((ready['root']/name).read_bytes()==data for name,data in ready['originals'].items())


def test_real_external_reflow_fact_card_emphasis_master_audio_and_old_output(tmp_path):
    root=os.environ.get('OPENMONTAGE_TEST_ROOT')
    if not root:pytest.skip('Separate installed OpenMontage required; owner live Windows test remains pending.')
    from app.integrations.openmontage.bridge import Bridge
    from app.integrations.openmontage.provider import OpenMontageProvider
    from app.rendering import tools,probe
    from app.rendering.runner import ProcessRunner
    from test_subtitles import wav
    projects=SimpleNamespace(storage=tmp_path/'config',_path=lambda pid:tmp_path/'project');projects.storage.mkdir()
    folder=projects._path('pid')/'stock';folder.mkdir(parents=True)
    a=synthetic(folder,uuid4().hex+'.mp4',['-f','lavfi','-i','color=c=blue:s=1280x720:r=30:d=22','-c:v','libx264'])
    b=synthetic(folder,uuid4().hex+'.mp4',['-f','lavfi','-i','color=c=green:s=1280x720:r=30:d=22','-c:v','libx264'])
    voice=tmp_path/'narration.wav';voice.write_bytes(wav(10));old=tmp_path/'previous-render.mp4';old.write_bytes(b'old-version-preserved')
    h={'ready':False,'contract_version':1,'project_id':'pid','source_script_version_id':'s','scene_plan_id':'p','audio_duration':10,
       'scenes':[{'scene_id':'a','start':0,'end':8},{'scene_id':'b','start':8,'end':10}],
       'subtitles':[{'index':1,'start':0,'end':8,'text':'Electric cars on the road.'},{'index':2,'start':8,'end':10,'text':'193 Sekunden erklären das Thema.'}], 'stock_slots':[]}
    p={'plan_id':'p','source_script_version_id':'s','scenes':[
        {'scene_id':'a','narration_text':'Electric cars on the road.','visual_intent':'electric cars road','primary_stock_query':'electric cars road','transition':'hard_cut','motion':'none','importance':50},
        {'scene_id':'b','narration_text':'193 Sekunden erklären das Thema.','visual_intent':'exact narration fact','primary_stock_query':'exact narration fact','transition':'hard_cut','motion':'none','importance':90}]}
    raws=[];assets={};originals={f:files.sha256(f) for f in (a,b,voice)}
    for i,(start,end,source) in enumerate([(0,2,a),(2,4,None),(4,6,b),(6,8,None),(8,10,None)]):
        m={**media(str(i),description='electric cars road',duration=22),'local_path':'stock/'+source.name,'file_size':source.stat().st_size,'sha256':files.sha256(source)} if source else None
        s={'slot_id':str(i),'scene_id':'a' if i<4 else 'b','order':i+1 if i<4 else 1,'start':start,'end':end,'duration':end-start,'locked':False,'status':'complete' if m else 'pending',
           'selected_media_local_identity':{k:m[k] for k in ('provider','media_id','media_type','local_path')} if m else None}
        h['stock_slots'].append(s);raws.append({**s,'selected_media':m,'local_validation':{'sha256':m['sha256'],'duration':22,'media_type':'video','width':1280,'height':720} if m else {}})
        if source:assets[str(i)]={'path':source,'type':'video','duration':22,'width':1280,'height':720,'sha256':m['sha256']}
    effective,report=reflow.build(h,p,{'slots':raws},projects,files.sha256)
    assert report['render_ready'] and report['effective_render_segments']==3 and report['graphic_seconds']==2
    t=timeline.build(effective,p);edit=smart_edit.build(t,effective,'adaptive','source',subtitle_mode='emphasis',media_details=assets)
    job=tmp_path/'job';job.mkdir();graphic=next(s for s in effective['stock_slots'] if s.get('graphic_text'))
    assets[graphic['slot_id']]={'path':None,'type':'graphic','duration':None}
    plan={'temporary':job,'handoff':effective,'timeline':t,'smart_edit_plan':edit,'options':options({'encoder':'cpu','subtitle_display':'emphasis'}),'media':assets,'audio':voice,'music':None}
    reflow.apply_graphics(plan);tool=tools.discover();runner=ProcessRunner();reflow.materialize(plan,tool,runner)
    bridge=Bridge(projects,SimpleNamespace(secret_values=lambda:[],stock_config=lambda n:{}));bridge.save({'root':root})
    result=OpenMontageProvider(bridge,tool,runner).render(plan)
    actual=probe.validate(tool['ffprobe'],result['path'],10)
    assert actual['video_codec']=='h264' and actual['audio_codec']=='aac'
    assert result['metadata']['smart_edit_applied_summary']['layouts']['fact_card']>=1
    assert old.read_bytes()==b'old-version-preserved' and all(files.sha256(f)==digest for f,digest in originals.items())
    from test_smart_edit import pixels
    for moment in (.5,3.5,4.5,7.5,9.):
        rgb=pixels(result['path'],moment)
        assert sum(rgb)/len(rgb)>10  # Real video/frame output, no accidental black gap.
    card=pixels(result['path'],9.)
    assert sum(min(r,g,b)>150 for r,g,b in zip(card[::3],card[1::3],card[2::3]))>10  # Actual light card text, not its bare dark background.


def test_network_failure_remains_retryable_without_false_exhaustion(studio,monkeypatch):
    service=studio[0].app.state.stock;pid=studio[1]['id'];service.settings.save('pexels',{'api_key':'network-test'})
    monkeypatch.setattr(service,'_handoff',lambda pid:{'scenes':[{'scene_id':'s','visual_intent':'ocean','primary_stock_query':'ocean'}]})
    monkeypatch.setattr(service,'_checkpoint',lambda *a,**kw:None)
    monkeypatch.setattr(service,'_cache_search',lambda *a,**kw:(_ for _ in ()).throw(StockError('network_error','Safe network error')))
    s={'scene_id':'s','duration':3,'candidates':[]}
    recovery.search(service,pid,s,set(),{},{});assert not s['recovery_attempts'] and 'query_exhausted' not in s['missing_reasons']
    assert 'provider_unreachable' in s['missing_reasons'] and 'no_provider_results' not in s['missing_reasons']


def test_visual_candidates_share_one_bounded_local_process(studio,monkeypatch):
    b=studio[0].app.state.stock.openmontage;pid=studio[1]['id'];folder=b.projects._path(pid)/'stock';items=[]
    for i in range(4):
        path=folder/(uuid4().hex+'.mp4');path.write_bytes(str(i).encode())
        items.append({**media(str(i)),'local_path':'stock/'+path.name,'file_size':1,'sha256':files.sha256(path)})
    monkeypatch.setattr(b,'status',lambda:{'semantic_ready':True,'semantic_model_version':'v1'});calls=[]
    def call(op,inputs,work):
        calls.append(inputs);return {'results':[{'sha256':m['sha256'],'verdict':'uncertain','model_version':'v1'} for m in inputs['candidates']]}
    monkeypatch.setattr(b,'call',call)
    profile=relevance.profile({'visual_intent':'aircraft cockpit','primary_stock_query':'aircraft cockpit'})
    results=visual.analyse_many(b,pid,items,profile)
    assert len(results)==4 and len(calls)==1 and len(calls[0]['candidates'])==4
    visual.analyse_many(b,pid,items,profile);assert len(calls)==1
    assert all(m['source_metadata']['footage_role']=='contextual_broll' for m in results)
    with pytest.raises(StockError):visual.analyse_many(b,pid,items+[items[0]],profile)


def test_unsupported_local_media_cannot_pass_decode(tmp_path):
    from app.rendering.tools import discover
    path=tmp_path/'unsupported.mp4';path.write_bytes(b'not-a-real-video')
    with pytest.raises(StockError,match='çözümlenemedi'):recovery.decode(discover(),path)


def test_local_visual_process_timeout_returns_safe_error(studio,tmp_path,monkeypatch):
    import subprocess
    from app.rendering.models import RenderError
    b=studio[0].app.state.stock.openmontage
    monkeypatch.setattr(b,'status',lambda:{'ready':True})
    monkeypatch.setattr(b,'root',lambda:tmp_path)
    monkeypatch.setattr('app.rendering.tools.discover',lambda:{})
    def timeout(args,**kw):
        assert kw['timeout']==180 and kw['shell'] is False
        raise subprocess.TimeoutExpired(args,180,output='private-response-token',stderr='private-response-token')
    monkeypatch.setattr(subprocess,'run',timeout)
    with pytest.raises(RenderError) as caught:b.call('visual',{'descriptor':'aircraft','candidates':[]},tmp_path)
    assert caught.value.category=='openmontage_failed' and 'private-response-token' not in str(caught.value)
    assert not list(tmp_path.glob('om-input-*.json'))
