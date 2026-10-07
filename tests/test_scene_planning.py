"""Part 5 through the existing production service/jobs, no live-provider claims."""
from contextlib import closing
from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.database import initialize_database
from app.production import normalize, visual_blocks, scene_checks
from app.scripts.models import ScriptError, word_count
from test_scripts import studio, run, KEY, OTHER_KEY, HEADERS
from test_production import production_studio, block


def route(project): return f'/api/projects/{project["id"]}/production'
def view(studio): return studio[0].get(route(studio[1])).json()
def stamp(studio):
    plan=view(studio)['plan'];return {'plan_id':plan['plan_id'],'revision':plan['revision']}
def action(studio,index,action,**extra):
    plan=view(studio)['plan']
    return studio[0].post(route(studio[1])+f'/scenes/{plan["blocks"][index]["id"]}/actions',json={**stamp(studio),'action':action,**extra})
def finish(studio,response):
    assert response.status_code==202,response.text
    studio[0].app.state.scripts.futures[response.json()['job_id']].result(timeout=5)
    job=studio[0].get(f'/api/projects/{studio[1]["id"]}/script').json()['job']
    assert job['status']=='draft',job
    return view(studio)
def generate(studio):
    return finish(studio,studio[0].post(route(studio[1])+'/plan',json={'provider':'ollama','cost_confirmed':False,'confirm_replace_plan':True}))


def test_part5_requires_approved_script_exact_message_no_provider_request(studio):
    client,project,fake,_=studio
    response=client.post(route(project)+'/plan',json={'provider':'ollama','cost_confirmed':False,'confirm_replace_plan':False})
    assert response.status_code==409 and response.json()['message']=='Önce senaryo sürümünü onaylayın.'
    assert not fake.calls and not view(studio)['approved_script']
    current=run(studio)['current']
    assert client.post(route(project)+'/plan',json={'provider':'ollama','cost_confirmed':False,'confirm_replace_plan':False}).status_code==409
    assert all(task!='visual' for task,_,_ in fake.calls)


def test_extended_scene_contract_coverage_timing_and_part6(production_studio):
    client,project,fake,data=production_studio
    plan=view(production_studio)['plan'];script=client.get(f'/api/projects/{project["id"]}/script').json()['current']
    assert view(production_studio)['coverage_complete'] and plan['status']=='ready'
    assert normalize(' '.join(b['narration'] for b in plan['blocks']))==normalize(script['text'])
    assert plan['source_script_version']==script['version'] and plan['version_id']==script['id']
    assert plan['provider']=='gemini' and plan['model']==script['model']
    total=0
    for index,b in enumerate(plan['blocks']):
        assert b['scene_id']==b['id'] and b['order']==index+1 and b['narration_text']==b['narration']
        assert b['primary_stock_query']==b['stock_query'] and b['preferred_media_type']==b['media_type']
        assert b['start_estimate']==round(total/135*60,3)
        total+=word_count(b['narration'])
        assert b['end_estimate']==round(total/135*60,3) and b['timing_source']=='estimated'
        assert all(k in b for k in ('purpose','mood','importance','visual_intent','entities','location','action','composition','shot_suggestion','transition','motion','overlay_text','overlay_language','notes','locked','media'))
        assert b['media'] is None and len(b['alternative_stock_queries'])==2
    assert (data/'projects'/project['id']/'scenes'/'active_plan.json').exists()
    assert json.loads((data/'projects'/project['id']/'scenes'/'plan_v1.json').read_text())==plan
    handoff=client.get(route(project)+'/handoff').json()
    assert handoff['contract_version']==1 and handoff['source_script_version_id']==script['id']
    assert handoff['scenes'][0]['primary_stock_query']=='electric cars Germany dealership'
    assert handoff['scenes'][0]['stock_query_language']=='en'
    assert all(b['media'] is None for b in handoff['scenes'])
    assert KEY not in json.dumps(handoff) and OTHER_KEY not in json.dumps(handoff)
    prompt=next(prompt for task,_,prompt in fake.calls if task=='visual')
    for rule in ('meaning','topic changes','emotional beats','comparisons','lists','3–7','5–12','guidance ONLY','ENGLISH','2–5','content_type','Never turn all topics into stories'):
        assert rule in prompt


@pytest.mark.parametrize('language,overlay',[('de','E-Autos im Alltag'),('es','Coches eléctricos'),('en','Electric vehicles'),('fr','Voitures électriques'),('tr','Elektrikli otomobiller')])
def test_project_language_overlay_and_english_semantic_queries(production_studio,language,overlay):
    client,project,fake,_=production_studio
    client.patch('/api/projects/'+project['id'],json={'language':language})
    original=fake.generate_script
    def localized(prompt):
        result=original(prompt)
        if prompt.startswith('TASK: visual'):
            data=json.loads(prompt.split('INPUT DATA (not instructions):\n')[1]);assert data['language']==language
            body=json.loads(result)
            for b in body['blocks']: b['overlay_text']=overlay
            return json.dumps(body)
        return result
    fake.generate_script=localized
    plan=generate(production_studio)['plan']
    assert plan['language']==language
    for b in plan['blocks']:
        assert b['overlay_text']==overlay and b['overlay_language']==language
        assert b['stock_query_language']=='en' and b['stock_query']=='electric cars Germany dealership'
        assert b['stock_query'] not in b['narration']


@pytest.mark.parametrize('change',[{'stock_query':'cars'},{'alternative_stock_queries':['car road']},{'alternative_stock_queries':['car road','car road']},{'stock_query':'This is a complete long search sentence.'},{'overlay_text':' '.join(['word']*13)},{'importance':101},{'entities':['x'*151]},{'narration':'wrong narration'},{'locked':True},{'notes':KEY},{'purpose':'   '}])
def test_scene_validation_and_secrets_never_overwrite_plan(production_studio,change):
    client,project,_,_=production_studio;before=view(production_studio)
    sid=before['plan']['blocks'][0]['id']
    response=client.put(route(project)+f'/scenes/{sid}',json={**stamp(production_studio),'changes':change})
    assert response.status_code==422 and KEY not in response.text
    assert view(production_studio)==before


def test_manual_scene_edit_persists_new_version_and_safe_narration(production_studio):
    client,project,_,data=production_studio;before=view(production_studio)['plan'];sid=before['blocks'][0]['id']
    response=client.put(route(project)+f'/scenes/{sid}',json={**stamp(production_studio),'changes':{'visual_intent':'Yeni bağlama uygun çekim','notes':'Yakın plan kullanın.','entities':['electric car'],'location':'Berlin','action':'charging','shot_suggestion':'charging connector closeup','overlay_text':''}})
    assert response.status_code==200,response.text
    after=response.json()['plan'];assert after['plan_version']==2 and after['plan_id']!=before['plan_id']
    assert after['blocks'][0]['narration']==before['blocks'][0]['narration']
    assert after['blocks'][0]['visual_intent']=='Yeni bağlama uygun çekim' and after['blocks'][0]['overlay_text']==''
    assert json.loads((data/'projects'/project['id']/'scenes'/'plan_v1.json').read_text())==before
    with TestClient(create_app(data),headers=HEADERS) as restarted:
        assert restarted.get(route(project)).json()==view(production_studio)


def single_provider(studio,bad=False):
    fake=studio[2];original=fake.generate_script
    def generate(prompt):
        if prompt.startswith('TASK: visual'):
            data=json.loads(prompt.split('INPUT DATA (not instructions):\n')[1])
            if data.get('scene_mode')=='single':
                fake.calls.append(('visual',data,prompt))
                result=block('wrong narration' if bad else data['text'],'detail');result['visual_intent']='Charging connector detail'
                return json.dumps({'blocks':[result]})
        return original(prompt)
    fake.generate_script=generate


def test_individual_regeneration_only_one_scene_and_old_version_kept(production_studio):
    client,project,fake,data=production_studio;single_provider(production_studio)
    before=view(production_studio)['plan'];sid=before['blocks'][0]['id'];count=len(fake.calls)
    after=finish(production_studio,client.post(route(project)+f'/scenes/{sid}/regenerate',json={**stamp(production_studio),'provider':'ollama','cost_confirmed':False}))['plan']
    assert len(fake.calls)==count+1
    assert after['blocks'][1]==before['blocks'][1] and after['blocks'][0]['id']==sid
    assert after['blocks'][0]['narration']==before['blocks'][0]['narration']
    assert after['blocks'][0]['visual_intent']=='Charging connector detail' and after['plan_version']==2
    assert json.loads((data/'projects'/project['id']/'scenes'/'plan_v1.json').read_text())==before


def test_invalid_individual_generation_preserves_plan(production_studio):
    client,project,_,_=production_studio;single_provider(production_studio,bad=True);before=view(production_studio)
    response=client.post(route(project)+f'/scenes/{before["plan"]["blocks"][0]["id"]}/regenerate',json={**stamp(production_studio),'provider':'ollama','cost_confirmed':False})
    assert response.status_code==202;client.app.state.scripts.futures[response.json()['job_id']].result(timeout=5)
    assert view(production_studio)==before


def test_lock_bulk_regeneration_preserves_anchor_and_skips_its_request(production_studio):
    client,project,fake,_=production_studio
    assert action(production_studio,0,'lock').status_code==200
    before=view(production_studio)['plan'];locked=before['blocks'][0];count=len(fake.calls)
    after=generate(production_studio)['plan']
    assert after['blocks'][0]==locked and after['blocks'][0]['id']==locked['id']
    assert len(fake.calls)==count+1
    requested=fake.calls[-1][1]['text']
    assert normalize(requested)==normalize(before['blocks'][1]['narration'])
    assert normalize(' '.join(b['narration'] for b in after['blocks']))==normalize(' '.join(b['narration'] for b in before['blocks']))


@pytest.mark.parametrize('operation',['split','merge','up','down'])
def test_locked_scene_structural_edits_and_neighbor_moves_blocked(production_studio,operation):
    assert action(production_studio,0,'lock').status_code==200
    before=view(production_studio)
    assert action(production_studio,0,operation,split_at=10).status_code==409
    assert view(production_studio)==before
    if operation=='up': assert action(production_studio,1,'up').status_code==409


def test_locked_scene_cannot_be_edited_or_individually_regenerated(production_studio):
    client,project,_,_=production_studio;action(production_studio,0,'lock');before=view(production_studio);sid=before['plan']['blocks'][0]['id']
    assert client.put(route(project)+f'/scenes/{sid}',json={**stamp(production_studio),'changes':{'notes':'change'}}).status_code==409
    assert client.post(route(project)+f'/scenes/{sid}/regenerate',json={**stamp(production_studio),'provider':'ollama','cost_confirmed':False}).status_code==409
    assert action(production_studio,0,'unlock').json()['plan']['blocks'][0]['locked'] is False


def test_all_locked_bulk_plan_makes_no_provider_requests(production_studio):
    action(production_studio,0,'lock');action(production_studio,1,'lock');before=view(production_studio)['plan'];count=len(production_studio[2].calls)
    after=generate(production_studio)['plan']
    assert after['blocks']==before['blocks'] and len(production_studio[2].calls)==count


def test_locked_real_timing_is_not_changed_by_bulk_regeneration(production_studio):
    client,project,_,_=production_studio;plan=view(production_studio)['plan']
    timings=[{'text':b['narration'],'start':float(i*40),'end':float((i+1)*40)} for i,b in enumerate(plan['blocks'])]
    assert client.put(route(project)+'/timing',json={'timings':timings}).status_code==200
    action(production_studio,0,'lock');locked=view(production_studio)['plan']['blocks'][0]
    after=generate(production_studio)['plan']
    assert after['blocks'][0]==locked and after['timing_source']=='mixed'


def test_stale_failed_job_cannot_replace_newer_plan_on_resume(production_studio):
    client,project,_,_=production_studio;single_provider(production_studio,bad=True)
    response=client.post(route(project)+f'/scenes/{view(production_studio)["plan"]["blocks"][0]["id"]}/regenerate',json={**stamp(production_studio),'provider':'ollama','cost_confirmed':False})
    job_id=response.json()['job_id'];client.app.state.scripts.futures[job_id].result(timeout=5)
    action(production_studio,0,'lock');before=view(production_studio)
    response=client.post(f'/api/projects/{project["id"]}/script/jobs/{job_id}/resume',json={'confirm_replace_approved':False})
    assert response.status_code==409 and view(production_studio)==before


def test_replaying_completed_plan_job_does_not_duplicate_history(production_studio):
    client,project,_,_=production_studio;before=view(production_studio)
    job=client.get(f'/api/projects/{project["id"]}/script').json()['job']
    inputs=client.app.state.scripts.repository.job(job['id']);inputs=json.loads(inputs['input_json'])
    client.app.state.production.save_generated(project['id'],inputs['version_id'],before['plan']['language'],before['plan']['blocks'],True,job_id=job['id'])
    assert view(production_studio)==before


def test_split_merge_retime_and_complete_narration(production_studio):
    before=view(production_studio)['plan'];text=before['blocks'][0]['narration'];at=text.index(' ')+1
    split=action(production_studio,0,'split',split_at=at);assert split.status_code==200,split.text
    split_plan=split.json()['plan'];assert len(split_plan['blocks'])==3
    assert split_plan['blocks'][0]['id']==before['blocks'][0]['id']
    assert len({b['id'] for b in split_plan['blocks']})==3
    assert normalize(' '.join(b['narration'] for b in split_plan['blocks']))==normalize(' '.join(b['narration'] for b in before['blocks']))
    assert split_plan['blocks'][-1]['end']==before['blocks'][-1]['end']==120
    merged=action(production_studio,0,'merge').json()['plan']
    assert [b['narration'] for b in merged['blocks']]==[b['narration'] for b in before['blocks']]
    assert merged['plan_version']==3 and [b['order'] for b in merged['blocks']]==[1,2]


@pytest.mark.parametrize('split_at',[0,-1,True,1,999999,'12'])
def test_invalid_split_does_not_drop_text(production_studio,split_at):
    before=view(production_studio);assert action(production_studio,0,'split',split_at=split_at).status_code==422
    assert view(production_studio)==before


def test_move_visual_design_preserves_approved_narration_order(production_studio):
    before=view(production_studio)['plan'];after=action(production_studio,0,'down').json()['plan']
    assert [b['narration'] for b in after['blocks']]==[b['narration'] for b in before['blocks']]
    assert [b['id'] for b in after['blocks']]==[b['id'] for b in before['blocks']]
    assert after['blocks'][0]['composition']==before['blocks'][1]['composition']
    restored=action(production_studio,1,'up').json()['plan']
    assert restored['blocks']==before['blocks'] and view(production_studio)['coverage_complete']


def test_plan_versions_confirmed_selection_and_project_isolation(production_studio):
    client,project,_,data=production_studio;before=view(production_studio)['plan'];generate(production_studio)
    path=route(project)+f'/versions/{before["plan_id"]}/select'
    assert client.post(path,json={'confirm':False}).status_code==409
    restored=client.post(path,json={'confirm':True}).json()
    assert restored['plan']==before and restored['versions'][1]['active']
    other=client.post('/api/projects',json={'name':'Other','topic':'Other'}).json()
    assert client.post(route(other)+f'/versions/{before["plan_id"]}/select',json={'confirm':True}).status_code==404
    with TestClient(create_app(data)) as restarted: assert restarted.get(route(project)).json()==restored


def test_outdated_plan_after_script_edit_no_silent_overwrite(production_studio):
    client,project,_,_=production_studio;before=view(production_studio)['plan'];script_route=f'/api/projects/{project["id"]}/script'
    current=client.get(script_route).json()['current']
    response=client.post(script_route+'/versions',json={'text':current['text']+' Ein zusätzlicher eigener Satz.','base_version_id':current['id'],'confirm_replace_approved':True})
    assert response.status_code==201,response.text
    old=view(production_studio);assert old['plan']['status']=='outdated' and not old['coverage_complete']
    assert old['plan']['blocks']==before['blocks']
    assert client.get(route(project)+'/handoff').status_code==409
    assert action(production_studio,0,'lock').status_code==409
    new_script=client.get(script_route).json()['current']
    client.post(script_route+f'/versions/{new_script["id"]}/approve',json={'confirm':True})
    new=generate(production_studio);assert new['plan']['version_id']==new_script['id'] and new['plan']['status']=='ready'
    assert new['versions'][1]['status']=='outdated'


def test_stale_editor_snapshot_prevents_lost_update(production_studio):
    client,project,_,_=production_studio;old=stamp(production_studio);sid=view(production_studio)['plan']['blocks'][0]['id']
    action(production_studio,0,'lock');before=view(production_studio)
    assert client.put(route(project)+f'/scenes/{sid}',json={**old,'changes':{'notes':'late edit'}}).status_code==409
    assert view(production_studio)==before


def test_schema5_upgrade_imports_legacy_plan_preserving_all_data(production_studio):
    client,project,_,data=production_studio;before=view(production_studio)['plan'];vault=(data/'secrets/settings.enc').read_bytes()
    legacy=deepcopy(before)
    for key in ('plan_id','plan_version','revision','provider','model','created_at'):legacy.pop(key)
    with closing(client.app.state.projects._connection()) as db,db:
        db.execute('DROP TABLE scene_plan_versions');db.execute("UPDATE app_metadata SET value='5' WHERE key='schema_version'")
        db.execute('UPDATE project_production SET plan_json=? WHERE project_id=?',(json.dumps(legacy),project['id']))
    initialize_database(data);initialize_database(data)
    after=view(production_studio)
    assert after['plan']['blocks']==before['blocks'] and len(after['versions'])==1
    assert after['plan']['version_id']==before['version_id'] and after['plan']['provider']=='legacy'
    assert (data/'secrets/settings.enc').read_bytes()==vault
    assert client.get(f'/api/projects/{project["id"]}/script').json()['current']['id']==before['version_id']


def test_bad_scene_count_repetition_and_diversity_warn_without_unrelated_changes():
    source=' '.join('word'+str(i) for i in range(300))
    scenes=visual_blocks({'blocks':[block(source)]},source,'de',135)
    warnings=scene_checks(scenes,source)
    assert any('az sahne' in w for w in warnings) and any('çok uzun' in w for w in warnings)
    parts=[block('Sentence '+str(i)+'.') for i in range(4)]
    for p in parts:p['media_type']='stock_image'
    scenes=visual_blocks({'blocks':parts},' '.join(p['narration'] for p in parts),'de',135)
    warnings=scene_checks(scenes,' '.join(p['narration'] for p in parts))
    for phrase in ('çok kısa','tekrarlanıyor','kompozisyon','sabit görsel'):
        assert any(phrase in w for w in warnings)
    reversed_text=' '.join(b['narration'] for b in reversed(scenes))
    assert any('aynı sırayla' in w for w in scene_checks(scenes,reversed_text))


def test_no_missing_or_reordered_narration_is_accepted():
    for parts in ([block('First sentence.')],[block('Second sentence.'),block('First sentence.')]):
        with pytest.raises(ScriptError):visual_blocks({'blocks':parts},'First sentence. Second sentence.','de',135)


def test_cost_consent_before_individual_or_bulk_cloud_generation(production_studio):
    client,project,fake,_=production_studio;count=len(fake.calls);sid=view(production_studio)['plan']['blocks'][0]['id']
    assert client.post(route(project)+f'/scenes/{sid}/regenerate',json={**stamp(production_studio),'provider':'gemini','cost_confirmed':False}).status_code==409
    assert client.post(route(project)+'/plan',json={'provider':'gemini','cost_confirmed':False,'confirm_replace_plan':True}).status_code==409
    assert len(fake.calls)==count


def test_long_script_batches_complete_coverage_and_contextual_continuity(production_studio):
    client,project,fake,_=production_studio
    client.patch('/api/projects/'+project['id'],json={'target_duration_minutes':20})
    current=run(production_studio,{'confirm_replace_approved':True})['current']
    client.post(f'/api/projects/{project["id"]}/script/versions/{current["id"]}/approve',json={'confirm':True})
    count=len(fake.calls);result=generate(production_studio)
    calls=[inputs for task,inputs,_ in fake.calls[count:] if task=='visual']
    assert len(calls)==5 and calls[0]['previous_visuals']==[] and calls[1]['previous_visuals']
    assert result['coverage_complete'] and result['plan']['blocks'][-1]['end']==1200
    assert normalize(' '.join(b['narration'] for b in result['plan']['blocks']))==normalize(current['text'])
    assert any('az sahne' in w for w in result['scene_warnings'])


def test_json_mirror_failure_resume_repairs_files_without_second_generation(production_studio,monkeypatch):
    client,project,fake,data=production_studio;production=client.app.state.production;original=production._mirror;failed=[False]
    def once(*args,**kwargs):
        if not failed[0]:failed[0]=True;raise ScriptError('Plan JSON dosyası kaydedilemedi.',503)
        return original(*args,**kwargs)
    monkeypatch.setattr(production,'_mirror',once)
    response=client.post(route(project)+'/plan',json={'provider':'ollama','cost_confirmed':False,'confirm_replace_plan':True})
    job_id=response.json()['job_id'];client.app.state.scripts.futures[job_id].result(timeout=5)
    assert len(view(production_studio)['versions'])==2
    count=len(fake.calls)
    response=client.post(f'/api/projects/{project["id"]}/script/jobs/{job_id}/resume',json={'confirm_replace_approved':False})
    assert response.status_code==202;client.app.state.scripts.futures[job_id].result(timeout=5)
    assert len(fake.calls)==count and len(view(production_studio)['versions'])==2
    saved=json.loads((data/'projects'/project['id']/'scenes'/'active_plan.json').read_text())
    assert saved==view(production_studio)['plan']
