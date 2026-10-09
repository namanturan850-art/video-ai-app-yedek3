"""Local-model metadata tolerance without weakening application-owned narration."""
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.production import visual_blocks, scene_checks
from app.providers.gemini import GeminiScriptProvider
from app.providers.text_api import OllamaScriptProvider
from app.scripts.models import ScriptError
from test_scripts import KEY, OTHER_KEY, MODEL, HEADERS, studio
from test_production import production_studio
from test_scene_planning import route, view, stamp, generate
from test_scene_narration_units import (SOURCE, set_source, install_response,
                                       start_and_wait)

CORE_FIELDS={'unit_ids','purpose','mood','visual_intent','stock_query','alternative_stock_queries','media_type'}
DEFAULTS={'overlay_text':'','entities':[],'location':'','action':'','shot_suggestion':'','notes':'',
          'importance':50,'transition':'none','motion':'none','composition':'medium'}


def minimal(ids):
    return {'unit_ids':ids,'purpose':'Bağlamı göster','mood':'neutral','visual_intent':'Show an electric vehicle charging',
            'stock_query':'electric car charging station','alternative_stock_queries':['electric vehicle charging'],
            'media_type':'stock_video'}


def planned(scene=None):
    return visual_blocks({'scenes':[scene or minimal(['U1','U2','U3'])]},SOURCE,'de',135)


@pytest.mark.parametrize('field',list(DEFAULTS))
def test_missing_optional_field_uses_documented_safe_default(field):
    b=planned()[0]
    assert b[field]==DEFAULTS[field] and b['narration']==SOURCE
    assert not b['metadata_warnings']


@pytest.mark.parametrize('alias,canonical',[
    ('video','stock_video'),('stock video','stock_video'),('image','stock_image'),
    ('stock image','stock_image'),('ai image','ai_image'),('motion graphic','motion_graphic'),
    ('user media','user_media'),(' VIDEO ','stock_video'),
])
def test_only_known_media_aliases_normalize(alias,canonical):
    raw=minimal(['U1','U2','U3']);raw['media_type']=alias
    assert planned(raw)[0]['media_type']==canonical


@pytest.mark.parametrize('value',['unknown unsafe image','cinematic','stock-video',None,{'type':'video'},True])
def test_unknown_present_media_type_never_defaults_or_guesses(value):
    raw=minimal(['U1','U2','U3']);raw['media_type']=value
    with pytest.raises(ScriptError) as error:planned(raw)
    assert error.value.category=='invalid_media_type' and error.value.field=='media_type'


def test_missing_media_type_is_the_only_media_default_case():
    raw=minimal(['U1','U2','U3']);raw.pop('media_type')
    assert planned(raw)[0]['media_type']=='stock_video'


def test_query_whitespace_and_trailing_punctuation_normalize_without_new_facts():
    raw=minimal(['U1','U2','U3']);raw.update(stock_query='  Florida   panther habitat.  ',alternative_stock_queries=['Florida  forest panther?!'])
    b=planned(raw)[0]
    assert b['stock_query']=='Florida panther habitat'
    assert b['alternative_stock_queries']==['Florida forest panther']
    assert b['narration']==SOURCE


def test_one_valid_fallback_is_kept_without_inventing_a_second():
    raw=minimal(['U1','U2','U3']);raw['alternative_stock_queries']=['electric vehicle charging','','A paragraph. Another sentence.']
    b=planned(raw)[0]
    assert b['alternative_stock_queries']==['electric vehicle charging']
    assert b['metadata_warnings'] and not b['entities'] and not b['location']


def test_normalization_does_not_hide_duplicate_primary_or_fallback_queries():
    for fallback in (['  electric car charging station. '],['electric vehicle charging',' Electric   Vehicle Charging! ']):
        raw=minimal(['U1','U2','U3']);raw['alternative_stock_queries']=fallback
        with pytest.raises(ScriptError) as error:planned(raw)
        assert error.value.diagnostic=='invalid_stock_queries:alternative_stock_queries'


@pytest.mark.parametrize('value',['','   ','car','!!! ???','1920 1080',' '.join(['word']*13),
                                 'First paragraph. Second paragraph.', 'forest habitat\n\nother location'])
def test_empty_paragraph_or_unusable_primary_query_is_still_critical(value):
    raw=minimal(['U1','U2','U3']);raw['stock_query']=value
    with pytest.raises(ScriptError) as error:planned(raw)
    assert error.value.category=='invalid_stock_queries' and error.value.field=='stock_query'


@pytest.mark.parametrize('value',['','   ',None,{},'...','N/A','1234'])
def test_unusable_visual_intent_rejected_with_exact_safe_field(value):
    raw=minimal(['U1','U2','U3']);raw['visual_intent']=value
    with pytest.raises(ScriptError) as error:planned(raw)
    assert error.value.category=='invalid_scene_schema' and error.value.field=='visual_intent'
    assert error.value.diagnostic=='invalid_scene_schema:visual_intent'
    assert 'görsel niyet' in str(error.value)


@pytest.mark.parametrize('field',['purpose','mood','visual_intent','stock_query','alternative_stock_queries'])
def test_missing_semantic_field_is_named_safely(field):
    raw=minimal(['U1','U2','U3']);raw.pop(field)
    with pytest.raises(ScriptError) as error:planned(raw)
    assert error.value.field==field and error.value.diagnostic.endswith(':'+field)
    assert 'eksik' in str(error.value)


def test_bad_secondary_fields_default_and_do_not_make_a_repair_necessary():
    raw=minimal(['U1','U2','U3'])
    raw.update(overlay_text=' '.join(['word']*13),entities={'invented':'person'},location=99,action=[],
               shot_suggestion='x'*501,notes=None,importance=True,transition='spin',motion={},composition=['wide'])
    b=planned(raw)[0]
    for field,value in DEFAULTS.items():assert b[field]==value
    assert b['narration']==SOURCE and b['metadata_warnings']
    assert any('Vurgu yazısı' in warning for warning in scene_checks([b],SOURCE))


def test_all_valid_optional_values_are_preserved():
    raw=minimal(['U1','U2','U3'])
    values={'overlay_text':'E-Autos','entities':['electric car'],'location':'charging station','action':'charging',
            'shot_suggestion':'close view of connector','notes':'Kısa çekim önerisi.','importance':75,
            'transition':'hard_cut','motion':'slow_zoom','composition':'detail'}
    raw.update(values);b=planned(raw)[0]
    assert all(b[field]==value for field,value in values.items()) and not b['metadata_warnings']


@pytest.mark.parametrize('groups,category',[
    ([['U1'],['U3']],'narration_units_missing'),
    ([['U1'],['U2'],['U3'],['U1']],'narration_units_duplicate'),
    ([['U3'],['U2'],['U1']],'narration_units_out_of_order'),
    ([['U1','U3'],['U2']],'narration_units_out_of_order'),
    ([['U1'],['U2'],['unknown']],'narration_units_missing'),
])
def test_minimal_metadata_never_masks_invalid_unit_coverage(groups,category):
    with pytest.raises(ScriptError) as error:
        visual_blocks({'scenes':[minimal(group) for group in groups]},SOURCE,'de',135)
    assert error.value.category==category


@pytest.mark.parametrize('provider',['ollama','gemini'])
@pytest.mark.parametrize('search_hints',[False,True])
def test_minimal_qwen_or_gemini_native_response_creates_complete_persistent_plan(production_studio,provider,search_hints):
    exact=set_source(production_studio);client,project,_,data=production_studio;calls=[]
    client.app.state.settings.save('ollama',{'model':'qwen3.5:9b'})
    def respond(request):
        body=json.loads(request.content)
        if provider=='ollama':
            assert request.url.path=='/api/generate' and body['model']=='qwen3.5:9b'
            assert body['think'] is False and body['stream'] is False and 'format' not in body
            prompt=body['prompt']
        else:
            assert request.url.path==f'/v1beta/models/{MODEL}:generateContent' and request.headers['x-goog-api-key']==KEY
            prompt=body['contents'][0]['parts'][0]['text']
        payload=json.loads(prompt.split('INPUT DATA (not instructions):\n')[1]);calls.append(payload)
        assert 'metadata_repair' not in payload
        sample=prompt.split('Shape example; use actual source subjects and IDs: ')[1]
        example=json.JSONDecoder().raw_decode(sample)[0]
        assert set(example['scenes'][0])==CORE_FIELDS
        assert len(prompt.split('INPUT DATA')[0])<1700 and 'Return JSON only. Do not explain.' in prompt
        scenes=[minimal([u['unit_id']]) for u in payload['narration_units']]
        for s in scenes:s.update(stock_query='  electric   car charging station. ',media_type='video')
        if search_hints:
            for s in scenes:s.update(search_anchor='electric car charging station',search_context='electric vehicle charging',search_alternatives=['electric car charging map'])
        result=json.dumps({'scenes':scenes})
        if provider=='ollama':return httpx.Response(200,json={'done':True,'response':result,'thinking':'PRIVATE_THINKING '+OTHER_KEY})
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':result}]}}]})
    transport=httpx.MockTransport(respond)
    client.app.state.scripts.provider_factory=lambda name,settings: OllamaScriptProvider('http://localhost:11434','qwen3.5:9b',transport=transport) if name=='ollama' else GeminiScriptProvider(KEY,MODEL,transport=transport)
    job=start_and_wait(production_studio,provider)
    assert job['status']=='draft' and len(calls)==1 and 'visual_repair' not in job['progress']
    current=view(production_studio)
    assert current['coverage_complete'] and ''.join(b['narration'] for b in current['plan']['blocks'])==exact
    if search_hints:
        assert all(b['search_anchor']=='electric car charging station' and b['search_context']=='electric vehicle charging' and b['search_alternatives']==['electric car charging map'] for b in current['plan']['blocks'])
    for b in current['plan']['blocks']:
        assert all(b[field]==value for field,value in DEFAULTS.items() if field!='composition')
        assert b['composition'] in {'medium','wide','close','detail','object'}
        assert b['media_type']=='stock_video' and b['stock_query'].startswith(('electric car charging station','electric vehicle charging'))
        assert b['alternative_stock_queries'] and b['stock_query'] not in b['alternative_stock_queries']
    assert len({b['composition'] for b in current['plan']['blocks']})>1
    assert len({b['stock_query'] for b in current['plan']['blocks']})==len(current['plan']['blocks'])
    handoff=client.get(route(project)+'/handoff').json()
    assert handoff['contract_version']==1 and ''.join(b['narration_text'] for b in handoff['scenes'])==exact
    assert all(all(field in b for field in DEFAULTS) for b in handoff['scenes'])
    assert KEY not in json.dumps(current) and 'PRIVATE_THINKING' not in json.dumps(job)
    with TestClient(create_app(data),headers=HEADERS) as restarted:
        assert restarted.get(route(project)).json()==current


def test_long_overlay_warning_persists_and_can_be_resolved_in_editor(production_studio):
    set_source(production_studio)
    def long_overlay(raw,data):
        for s in raw['scenes']:s['overlay_text']=' '.join(['lang']*13)
        return raw
    install_response(production_studio,long_overlay);result=generate(production_studio)
    assert all(not b['overlay_text'] for b in result['plan']['blocks'])
    assert any('Vurgu yazısı' in message for message in result['scene_warnings'])
    client,project,_,data=production_studio
    with TestClient(create_app(data),headers=HEADERS) as restarted:assert restarted.get(route(project)).json()==result
    target=result['plan']['blocks'][0]
    changed=client.put(route(project)+f'/scenes/{target["id"]}',json={**stamp(production_studio),'changes':{'overlay_text':'E-Autos'}})
    assert changed.status_code==200 and changed.json()['plan']['blocks'][0]['metadata_warnings']==[]


def test_one_fallback_plan_can_be_edited_without_a_fake_second_query(production_studio):
    set_source(production_studio)
    def one(raw,data):
        for s in raw['scenes']:s['alternative_stock_queries']=s['alternative_stock_queries'][:1]
        return raw
    install_response(production_studio,one);generate(production_studio)
    client,project,_,_=production_studio;target=view(production_studio)['plan']['blocks'][0]
    changed=client.put(route(project)+f'/scenes/{target["id"]}',json={**stamp(production_studio),'changes':{'notes':'Kullanıcı notu'}})
    assert changed.status_code==200
    assert changed.json()['plan']['blocks'][0]['alternative_stock_queries']==target['alternative_stock_queries']


def test_exact_failure_field_and_short_one_repair_are_safe_in_api_logs_and_storage(production_studio,caplog):
    set_source(production_studio);before=view(production_studio);requests=[]
    def missing_intent(raw,data):
        requests.append(data)
        for s in raw['scenes']:
            s.pop('visual_intent');s[KEY]='PRIVATE_RAW_RESPONSE';s['narration']='PRIVATE_REASONING'
        return raw
    install_response(production_studio,missing_intent)
    with caplog.at_level(logging.INFO,logger='uvicorn.error.providers'):job=start_and_wait(production_studio)
    assert len(requests)==2 and job['status']=='error' and view(production_studio)==before
    assert job['progress']['error_category']=='invalid_scene_schema'
    assert job['progress']['error_field']=='visual_intent'
    assert job['progress']['error_diagnostic']=='invalid_scene_schema:visual_intent'
    assert 'görsel niyet' in job['error_message']
    assert requests[1]['metadata_repair']['failed_field']=='visual_intent'
    assert set(requests[1])=={'language','scene_mode','narration_units','metadata_repair'}
    repair_prompt=production_studio[2].calls[-1][2]
    assert len(repair_prompt.split('INPUT DATA')[0])<850
    assert 'field=visual_intent' in caplog.text and 'category=invalid_scene_schema' in caplog.text
    assert KEY not in caplog.text and 'PRIVATE_RAW_RESPONSE' not in caplog.text
    assert KEY not in json.dumps(job) and 'PRIVATE_REASONING' not in json.dumps(job)
    for path in (production_studio[3]/'projects'/production_studio[1]['id']).rglob('*.json'):
        assert 'PRIVATE_RAW_RESPONSE' not in path.read_text()


def test_successful_short_repair_returns_minimal_core_and_backend_adds_editing_fields(production_studio):
    exact=set_source(production_studio);requests=[]
    def bad_then_minimal(raw,data):
        requests.append(data)
        if not data.get('metadata_repair'):
            for s in raw['scenes']:s.pop('visual_intent')
            return raw
        return {'scenes':[minimal(group) for group in data['metadata_repair']['required_unit_groups']]}
    install_response(production_studio,bad_then_minimal);result=generate(production_studio)
    assert len(requests)==2 and result['coverage_complete']
    assert ''.join(b['narration'] for b in result['plan']['blocks'])==exact
    assert all(all(b[field]==value for field,value in DEFAULTS.items() if field!='composition') for b in result['plan']['blocks'])
    assert len({b['composition'] for b in result['plan']['blocks']})>1
