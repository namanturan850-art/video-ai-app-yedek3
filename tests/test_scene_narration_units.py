"""Regression for real Windows narration drift; external providers are mocked."""
from contextlib import closing
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.production import (narration_units, narration_segments, scene_references,
                            visual_blocks, SCENE_ERRORS)
from app.providers.gemini import GeminiScriptProvider
from app.providers.text_api import OllamaScriptProvider
from app.scripts.models import ScriptError
from test_scripts import studio, KEY, OTHER_KEY, HEADERS, MODEL
from test_production import production_studio, scene
from test_scene_planning import route, view, generate, stamp, action, finish

SOURCE='E-Autos sind im Alltag hilfreich.\n\nLaden dauert unterschiedlich lange; der Ort ist wichtig.  Vergleichen Sie die Anforderungen!'


def response_for(data):
    ids=[u['unit_id'] for u in data['narration_units']]
    groups=data.get('metadata_repair',{}).get('required_unit_groups')
    if groups is None: groups=[ids] if data['scene_mode']=='single' else [[uid] for uid in ids]
    return {'scenes':[scene(group,'detail' if i%2 else 'wide') for i,group in enumerate(groups)]}


def set_source(studio, text=SOURCE):
    client,project,_,_=studio;base=f'/api/projects/{project["id"]}/script'
    current=client.get(base).json()['current']
    response=client.post(base+'/versions',json={'text':text,'base_version_id':current['id'],'confirm_replace_approved':True})
    assert response.status_code==201,response.text
    current=client.get(base).json()['current']
    assert client.post(base+f'/versions/{current["id"]}/approve',json={'confirm':True}).status_code==200
    return current['text']


def install_response(studio, transform=lambda raw,data:raw):
    fake=studio[2];original=fake.generate_script
    def respond(prompt):
        if prompt.startswith('TASK: visual'):
            data=json.loads(prompt.split('INPUT DATA (not instructions):\n')[1])
            fake.calls.append(('visual',data,prompt))
            raw=transform(response_for(data),data)
            return raw if isinstance(raw,str) else json.dumps(raw)
        return original(prompt)
    fake.generate_script=respond


def start_and_wait(studio, provider='ollama'):
    client,project,_,_=studio
    response=client.post(route(project)+'/plan',json={'provider':provider,'cost_confirmed':provider!='ollama','confirm_replace_plan':True})
    assert response.status_code==202,response.text
    job_id=response.json()['job_id'];client.app.state.scripts.futures[job_id].result(timeout=5)
    return client.get(f'/api/projects/{project["id"]}/script').json()['job']


@pytest.mark.parametrize('text',[
    '  First sentence.  Second sentence!\nThird question?  ',
    'Ein Satz.\r\n\r\nZweiter Satz; kleine Änderung.',
    'İlk cümle!  İkinci cümle?\nSon cümle.',
    'Une phrase « exacte ».\nAutre phrase.',
    'Una frase.\n\nOtra frase.',
    '数字 3.14 bleibt erhalten. „Zitat!“ Weiter geht es.',
    '日本語の文。 次の文！ 最後の文？',
    '\n\nNo sentence punctuation but exact spaces\tand trailing blanks   ',
])
def test_deterministic_units_preserve_every_original_character(text):
    units=narration_units(text)
    assert ''.join(u['text'] for u in units)==text
    assert units==narration_units(text)
    assert [u['order'] for u in units]==list(range(1,len(units)+1))
    assert len({u['unit_id'] for u in units})==len(units)
    assert all(u['text'].strip() for u in units)


@pytest.mark.parametrize('punctuation',[',',';',':','—'])
def test_long_sentence_uses_lossless_phrase_punctuation_not_fixed_words(punctuation):
    text=' '.join(['Wort']*30)+punctuation+'  '+' '.join(['Weiter']*30)+'.'
    units=narration_units(text)
    assert len(units)==2 and ''.join(u['text'] for u in units)==text
    assert units[0]['text'].endswith(punctuation+'  ')
    unpunctuated=' '.join(['Wort']*300)
    assert len(narration_units(unpunctuated))==1


def test_exact_context_batches_do_not_cut_units_or_remove_whitespace():
    text='\n\n'.join(' '.join([f'Wort{i}']*230)+'.  ' for i in range(6))
    segments=narration_segments(text)
    assert len(segments)==3 and ''.join(s['text'] for s in segments)==text
    assert all(s['text'].rstrip().endswith('.') for s in segments)


@pytest.mark.parametrize('groups,category',[
    ([['U1'],['U3']],'narration_units_missing'),
    ([['U1'],['U2'],['unknown']],'narration_units_missing'),
    ([['U1'],['U1'],['U2'],['U3']],'narration_units_duplicate'),
    ([['U2'],['U1'],['U3']],'narration_units_out_of_order'),
    ([['U1','U3'],['U2']],'narration_units_out_of_order'),
    ([['U2','U1'],['U3']],'narration_units_out_of_order'),
    ([['U1'],[],['U2','U3']],'narration_units_missing'),
    ([['U1'],[True],['U2','U3']],'invalid_scene_schema'),
])
def test_missing_duplicate_reordered_noncontiguous_and_unknown_ids_rejected(groups,category):
    units=narration_units(SOURCE)
    with pytest.raises(ScriptError) as error:
        visual_blocks({'scenes':[scene(group) for group in groups]},SOURCE,'de',135,units=units)
    assert error.value.category==category and str(error.value)==SCENE_ERRORS[category]


@pytest.mark.parametrize('change,category',[
    ({'stock_query':'car'},'invalid_stock_queries'),
    ({'alternative_stock_queries':['car road']},'invalid_stock_queries'),
    ({'alternative_stock_queries':['car road','car road']},'invalid_stock_queries'),
    ({'overlay_text':' '.join(['word']*13)},'invalid_overlay'),
    ({'overlay_text':'x'*151},'invalid_overlay'),
    ({'media_type':'unknown'},'invalid_media_type'),
    ({'transition':'spin'},'invalid_transition'),
    ({'motion':'spin'},'invalid_transition'),
    ({'composition':'invalid'},'invalid_composition'),
    ({'importance':101},'invalid_scene_schema'),
    ({'purpose':'   '},'invalid_scene_schema'),
])
def test_visual_metadata_has_specific_safe_categories(change,category):
    raw={'scenes':[scene(['U1','U2','U3'])]};raw['scenes'][0].update(change)
    with pytest.raises(ScriptError) as error: visual_blocks(raw,SOURCE,'de',135)
    assert error.value.category==category and str(error.value)==SCENE_ERRORS[category]


@pytest.mark.parametrize('copied_narration',[
    SOURCE.replace('.','!').replace('  ',' '),
    SOURCE.replace('hilfreich','nützlich'),
    SOURCE.lower(),
    'A completely unrelated copied narration '+KEY,
])
def test_windows_copy_drift_is_irrelevant_to_application_owned_narration(production_studio,copied_narration):
    exact=set_source(production_studio)
    def drift(raw,data):
        for s in raw['scenes']:s.update(narration=copied_narration,narration_text=copied_narration)
        return raw
    install_response(production_studio,drift)
    result=generate(production_studio)
    assert ''.join(b['narration'] for b in result['plan']['blocks'])==exact
    assert result['coverage_complete'] and KEY not in json.dumps(result)
    data=production_studio[2].calls[-1][1];prompt=production_studio[2].calls[-1][2]
    assert 'text' not in data and ''.join(u['text'] for u in data['narration_units'])==exact
    assert 'NEVER narration or narration_text' in prompt and '"narration":"exact source sentences"' not in prompt


def test_trailing_explanation_and_markdown_json_do_not_become_narration(production_studio):
    exact=set_source(production_studio)
    install_response(production_studio,lambda raw,data:'```json\n'+json.dumps(raw)+'\n```\nHere is the scene plan.')
    result=generate(production_studio)
    assert ''.join(b['narration'] for b in result['plan']['blocks'])==exact
    assert 'Here is' not in json.dumps(result)


def test_single_scene_backend_keeps_exact_narration_and_nonvisual_fields(production_studio):
    set_source(production_studio);install_response(production_studio);generate(production_studio)
    before=view(production_studio)['plan'];target=before['blocks'][0];client,project,_,_=production_studio
    def redesign(raw,data):
        for s in raw['scenes']:s.update(narration='rewritten source',purpose='changed purpose',mood='changed mood',importance=1,entities=['new person'],location='other location',action='other action',visual_intent='new visual intent')
        return raw
    install_response(production_studio,redesign)
    after=finish(production_studio,client.post(route(project)+f'/scenes/{target["id"]}/regenerate',json={**stamp(production_studio),'provider':'ollama','cost_confirmed':False}))['plan']
    assert after['blocks'][1:]==before['blocks'][1:]
    for key in ('id','narration','purpose','mood','importance','entities','location','action'):
        assert after['blocks'][0][key]==target[key]
    assert after['blocks'][0]['visual_intent']=='new visual intent'


def test_lock_boundaries_are_never_sent_or_consumed_by_unlocked_unit_requests(production_studio):
    exact=set_source(production_studio);install_response(production_studio);generate(production_studio)
    assert action(production_studio,1,'lock').status_code==200
    locked=view(production_studio)['plan']['blocks'][1];count=len(production_studio[2].calls)
    result=generate(production_studio)
    assert result['plan']['blocks'][1]==locked and result['coverage_complete']
    assert ''.join(b['narration'] for b in result['plan']['blocks'])==exact
    requests=[d for task,d,_ in production_studio[2].calls[count:] if task=='visual']
    assert len(requests)==2
    assert all(locked['narration'].strip() not in ''.join(u['text'] for u in d['narration_units']) for d in requests)
    assert not set(u['unit_id'] for u in requests[0]['narration_units']) & set(u['unit_id'] for u in requests[1]['narration_units'])


def test_ollama_one_metadata_repair_preserves_grouping_without_copying_raw_output(production_studio):
    set_source(production_studio);before=view(production_studio);calls=[]
    def first_bad(raw,data):
        calls.append(data)
        if not data.get('metadata_repair'):
            for s in raw['scenes']:s.update(stock_query='car',notes='PRIVATE_RAW_PROVIDER_BODY',narration=KEY)
        else:
            assert view(production_studio)==before
            assert 'PRIVATE_RAW_PROVIDER_BODY' not in json.dumps(data)
        return raw
    install_response(production_studio,first_bad)
    result=generate(production_studio)
    assert len(calls)==2 and calls[1]['metadata_repair']['safe_error_category']=='invalid_stock_queries'
    assert result['coverage_complete']
    job=production_studio[0].get(f'/api/projects/{production_studio[1]["id"]}/script').json()['job']
    assert job['progress']['visual_repair']['attempted'] and job['progress']['visual_repair']['status']=='succeeded'
    assert 'PRIVATE_RAW_PROVIDER_BODY' not in json.dumps(job) and KEY not in json.dumps(job)


def test_failed_repair_never_repeats_on_resume_or_restart_and_logs_only_safe_category(production_studio,caplog):
    set_source(production_studio);before=view(production_studio);calls=[]
    def invalid(raw,data):
        calls.append(data)
        for s in raw['scenes']:s.update(stock_query='car',notes='PRIVATE_RAW_PROVIDER_BODY '+KEY)
        return raw
    install_response(production_studio,invalid)
    with caplog.at_level(logging.INFO,logger='uvicorn.error.providers'):job=start_and_wait(production_studio)
    assert job['status']=='error' and job['progress']['error_category']=='invalid_stock_queries'
    assert len(calls)==2 and view(production_studio)==before
    assert job['progress']['visual_repair']['status']=='failed'
    client,project,_,data=production_studio
    with TestClient(create_app(data),headers=HEADERS) as restarted:
        restarted.app.state.scripts.provider_factory=client.app.state.scripts.provider_factory
        result=restarted.post(f'/api/projects/{project["id"]}/script/jobs/{job["id"]}/resume',json={'confirm_replace_approved':False})
        assert result.status_code==202
        restarted.app.state.scripts.futures[job['id']].result(timeout=5)
        assert restarted.get(route(project)).json()==before
    assert len(calls)==2
    assert 'category=invalid_stock_queries' in caplog.text
    assert KEY not in caplog.text and 'PRIVATE_RAW_PROVIDER_BODY' not in caplog.text
    assert 'PRIVATE_RAW_PROVIDER_BODY' not in json.dumps(job)
    for path in (data/'projects'/project['id']).rglob('*.json'):
        assert 'PRIVATE_RAW_PROVIDER_BODY' not in path.read_text() and KEY not in path.read_text()


@pytest.mark.parametrize('provider',['gemini','openai'])
def test_second_cloud_call_requires_separate_consent_and_keeps_same_provider(production_studio,provider):
    exact=set_source(production_studio);before=view(production_studio);calls=[]
    def first_bad(raw,data):
        calls.append(data)
        if not data.get('metadata_repair'):raw['scenes'][0]['media_type']='invalid'
        return raw
    install_response(production_studio,first_bad)
    job=start_and_wait(production_studio,provider)
    assert job['status']=='error' and len(calls)==1 and view(production_studio)==before
    assert job['progress']['visual_repair']['status']=='awaiting_cost_confirmation'
    client,project,_,data=production_studio;url=f'/api/projects/{project["id"]}/script/jobs/{job["id"]}/resume'
    assert client.post(url,json={'confirm_replace_approved':False}).status_code==409
    assert client.post(url,json={'confirm_replace_approved':False,'visual_repair_cost_confirmed':False}).status_code==409
    assert client.post(url,json={'confirm_replace_approved':False,'visual_repair_cost_confirmed':'true'}).status_code==422
    assert len(calls)==1
    with TestClient(create_app(data),headers=HEADERS) as restarted:
        restarted.app.state.scripts.provider_factory=client.app.state.scripts.provider_factory
        response=restarted.post(url,json={'confirm_replace_approved':False,'visual_repair_cost_confirmed':True})
        assert response.status_code==202
        restarted.app.state.scripts.futures[job['id']].result(timeout=5)
        assert restarted.get(f'/api/projects/{project["id"]}/script').json()['job']['status']=='draft'
        result=restarted.get(route(project)).json()
        assert ''.join(b['narration'] for b in result['plan']['blocks'])==exact
        assert result['plan']['provider']==provider
    assert len(calls)==2


@pytest.mark.parametrize('failure',['missing','duplicate','reordered','malformed'])
def test_unreliable_reference_coverage_is_never_automatically_repaired(production_studio,failure):
    set_source(production_studio);before=view(production_studio);calls=[]
    def invalid(raw,data):
        calls.append(data)
        if failure=='missing':raw['scenes'].pop()
        elif failure=='duplicate':raw['scenes'].append(raw['scenes'][0])
        elif failure=='reordered':raw['scenes'].reverse()
        else:return 'not JSON '+KEY
        return raw
    install_response(production_studio,invalid);job=start_and_wait(production_studio)
    assert job['status']=='error' and len(calls)==1 and view(production_studio)==before
    assert 'visual_repair' not in job['progress'] and KEY not in json.dumps(job)


def test_repair_budget_is_one_for_whole_plan_not_one_per_segment(production_studio):
    text='\n\n'.join(' '.join([f'Wort{i}']*230)+'.' for i in range(6))
    set_source(production_studio,text);before=view(production_studio);calls=[]
    def bad_initial(raw,data):
        calls.append(data)
        if not data.get('metadata_repair'):raw['scenes'][0]['stock_query']='car'
        return raw
    install_response(production_studio,bad_initial);job=start_and_wait(production_studio)
    assert job['status']=='error' and job['progress']['error_category']=='invalid_stock_queries'
    assert len(calls)==3  # First segment + one repair + failed second segment.
    assert len(job['progress']['parts'])==1 and view(production_studio)==before
    assert job['progress']['visual_repair']['attempted']


def test_repair_cannot_change_validated_unit_groups(production_studio):
    set_source(production_studio);before=view(production_studio);calls=[]
    def regroup(raw,data):
        calls.append(data)
        if not data.get('metadata_repair'):raw['scenes'][0]['stock_query']='car'
        else:raw['scenes']=[scene([u['unit_id'] for u in data['narration_units']])]
        return raw
    install_response(production_studio,regroup);job=start_and_wait(production_studio)
    assert len(calls)==2 and job['progress']['error_category']=='invalid_scene_schema'
    assert view(production_studio)==before


def test_failed_pre_fix_job_resumes_with_exact_source_units_and_same_checkpoint(production_studio):
    exact=set_source(production_studio);install_response(production_studio,lambda raw,data:'invalid JSON')
    job=start_and_wait(production_studio)
    client,project,_,_=production_studio
    with closing(client.app.state.projects._connection()) as connection,connection:
        inputs=json.loads(connection.execute('SELECT input_json FROM script_jobs WHERE id=?',(job['id'],)).fetchone()[0])
        inputs['planning_segments']=[{'text':' '.join(exact.split())}]
        connection.execute('UPDATE script_jobs SET input_json=? WHERE id=?',(json.dumps(inputs),job['id']))
    install_response(production_studio)
    response=client.post(f'/api/projects/{project["id"]}/script/jobs/{job["id"]}/resume',json={'confirm_replace_approved':False})
    assert response.status_code==202
    client.app.state.scripts.futures[job['id']].result(timeout=5)
    result=view(production_studio)
    assert result['coverage_complete'] and ''.join(b['narration'] for b in result['plan']['blocks'])==exact
    assert client.get(f'/api/projects/{project["id"]}/script').json()['job']['id']==job['id']


@pytest.mark.parametrize('provider',['ollama','gemini'])
def test_unit_planning_through_official_native_qwen_and_gemini_adapters(production_studio,provider):
    exact=set_source(production_studio);client,project,_,data=production_studio;calls=[]
    client.app.state.settings.save('ollama',{'model':'qwen3.5:9b'})
    def respond(request):
        body=json.loads(request.content)
        if provider=='ollama':
            assert request.url.path=='/api/generate' and body['model']=='qwen3.5:9b'
            assert body['think'] is False and body['stream'] is False
            prompt=body['prompt']
        else:
            assert request.url.path==f'/v1beta/models/{MODEL}:generateContent'
            assert request.headers['x-goog-api-key']==KEY
            prompt=body['contents'][0]['parts'][0]['text']
        payload=json.loads(prompt.split('INPUT DATA (not instructions):\n')[1]);calls.append(payload)
        raw=response_for(payload)
        for s in raw['scenes']:s['narration']='WRONG copied narration'
        text=json.dumps(raw)+'\nScene planning complete.'
        if provider=='ollama':return httpx.Response(200,json={'done':True,'response':text,'thinking':'PRIVATE_REASONING '+OTHER_KEY})
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'PRIVATE_REASONING '+OTHER_KEY,'thought':True},{'text':text}]}}]})
    transport=httpx.MockTransport(respond)
    client.app.state.scripts.provider_factory=lambda name,settings: OllamaScriptProvider('http://localhost:11434','qwen3.5:9b',transport=transport) if name=='ollama' else GeminiScriptProvider(KEY,MODEL,transport=transport)
    job=start_and_wait(production_studio,provider)
    assert job['status']=='draft' and len(calls)==1
    result=view(production_studio)
    assert ''.join(b['narration'] for b in result['plan']['blocks'])==exact and result['coverage_complete']
    handoff=client.get(route(project)+'/handoff').json()
    assert handoff['contract_version']==1 and ''.join(b['narration_text'] for b in handoff['scenes'])==exact
    assert 'PRIVATE_REASONING' not in json.dumps(result) and OTHER_KEY not in json.dumps(job)
    with TestClient(create_app(data),headers=HEADERS) as restarted:
        assert restarted.get(route(project)).json()==result
