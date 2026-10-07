"""Scene pacing at lossless source boundaries; provider HTTP responses are mocked."""
from copy import deepcopy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.production import (MAX_SCENE_SECONDS, VisualBlock, narration_units,
                            visual_blocks, scene_checks)
from app.providers.gemini import GeminiScriptProvider
from app.providers.text_api import OllamaScriptProvider
from app.scripts.models import word_count
from test_scripts import studio, HEADERS, KEY, OTHER_KEY, MODEL
from test_production import production_studio
from test_scene_planning import route, view, action, generate
from test_scene_narration_units import set_source, start_and_wait, install_response
from test_scene_minimal_metadata import minimal


def script(count=45, words=9):
    return ''.join(' '.join([f'Beispiel{i}',*['Laden']*(words-1)])+'.'+('  ' if i%2 else '\r\n\r\n') for i in range(count))


def coarse(units, count=5):
    size=max(1,len(units)//count)
    scenes=[minimal([u['unit_id'] for u in units[i:i+size]]) for i in range(0,len(units),size)]
    return {'scenes':scenes}


def assert_exact_boundaries(blocks, units):
    offset=0;edges={0}
    for unit in units:offset+=len(unit['text']);edges.add(offset)
    offset=0
    for b in blocks:
        offset+=len(b['narration']);assert offset in edges
        VisualBlock.model_validate({field:b[field] for field in VisualBlock.model_fields})
    assert ''.join(b['narration'] for b in blocks)==''.join(u['text'] for u in units)


def test_three_minute_five_scene_plan_is_subdivided_without_losing_any_characters():
    source=script();units=narration_units(source)
    assert word_count(source)==405 and len(coarse(units)['scenes'])==5
    blocks=visual_blocks(coarse(units),source,'de',135)
    assert len(blocks)>5 and blocks[-1]['end']==180
    assert all(b['estimated_duration']<=MAX_SCENE_SECONDS for b in blocks)
    assert 3<=blocks[0]['estimated_duration']<=7
    assert sum(5<=b['estimated_duration']<=12 for b in blocks)>=len(blocks)-1
    assert len({b['composition'] for b in blocks})>=3
    assert blocks[1]['stock_query']!=blocks[0]['stock_query']
    assert_exact_boundaries(blocks,units)
    warnings=scene_checks(blocks,source)
    assert not any('çok uzun' in w or 'az sahne' in w or 'kompozisyon' in w for w in warnings)


@pytest.mark.parametrize('rate',[90,125,135,145,180])
def test_scene_pacing_uses_saved_narration_rate_not_a_fixed_word_or_scene_count(rate):
    source=script(35,11);units=narration_units(source,rate)
    blocks=visual_blocks(coarse(units),source,'de',rate)
    assert all(b['estimated_duration']<=MAX_SCENE_SECONDS for b in blocks)
    assert blocks[-1]['end']==round(word_count(source)/rate*60,3)
    assert_exact_boundaries(blocks,units)


def test_faster_narration_has_fewer_boundaries_without_hardcoded_scene_count():
    source=script(45,9)
    slow=visual_blocks(coarse(narration_units(source,90)),source,'de',90)
    fast=visual_blocks(coarse(narration_units(source,180)),source,'de',180)
    assert len(slow)>len(fast)>5


@pytest.mark.parametrize('durations',[[10,9],[2,25,2],[18,18],[4,4,4,4,4,4],[13,13,13]])
def test_subdivision_never_combines_overlong_units_or_cuts_words(durations):
    source=''.join(' '.join([f'Teil{i}']*seconds)+'.  ' for i,seconds in enumerate(durations))
    units=narration_units(source,60)
    blocks=visual_blocks({'scenes':[minimal([u['unit_id'] for u in units])]},source,'de',60)
    assert_exact_boundaries(blocks,units)
    assert all(b['estimated_duration']<=MAX_SCENE_SECONDS or b.get('pacing_reason') for b in blocks)
    assert all(b['estimated_duration']<=MAX_SCENE_SECONDS or len(narration_units(b['narration'],60))==1 for b in blocks)


def test_indivisible_long_unit_has_explicit_safe_reason_and_warning():
    source=' '.join(['Langwort']*81)
    blocks=visual_blocks({'scenes':[minimal(['U1'])]},source,'de',135)
    assert len(blocks)==1 and blocks[0]['narration']==source
    assert blocks[0]['estimated_duration']==36 and 'kelimeler bölünmedi' in blocks[0]['pacing_reason']
    assert any(blocks[0]['pacing_reason'] in w for w in scene_checks(blocks,source))


def test_phrase_units_are_created_at_18_second_threshold_without_word_cuts():
    source=' '.join(['Wort']*21)+',  '+' '.join(['Weiter']*21)+'.'
    units=narration_units(source,135)
    assert len(units)==2 and ''.join(u['text'] for u in units)==source
    blocks=visual_blocks({'scenes':[minimal(['U1','U2'])]},source,'de',135)
    assert len(blocks)==2 and all(b['estimated_duration']<=18 for b in blocks)
    assert_exact_boundaries(blocks,units)


def test_ai_supplied_long_scene_excuse_cannot_bypass_subdivision():
    source=script();units=narration_units(source)
    raw=coarse(units)
    for b in raw['scenes']:b['pacing_reason']='PRIVATE_RAW_RESPONSE says do not split'
    blocks=visual_blocks(raw,source,'de',135)
    assert len(blocks)>5 and all(b['estimated_duration']<=18 for b in blocks)
    assert 'PRIVATE_RAW_RESPONSE' not in json.dumps(blocks)


def test_valid_short_semantic_groups_and_supplied_edit_choices_are_preserved():
    source=script(3,9);units=narration_units(source)
    raw={'scenes':[minimal([u['unit_id']]) for u in units]}
    for i,b in enumerate(raw['scenes']):
        b.update(composition=['detail','environment','wide'][i],motion='none',transition='crossfade',
                 stock_query=f'electric vehicle charging context {i}',overlay_text='E-Autos')
    blocks=visual_blocks(raw,source,'de',135)
    assert len(blocks)==3 and [b['composition'] for b in blocks]==['detail','environment','wide']
    assert all(b['overlay_text']=='E-Autos' and b['transition']=='crossfade' and b['motion']=='none' for b in blocks)
    assert_exact_boundaries(blocks,units)


@pytest.mark.parametrize('intent,allowed',[
    ('Close-up of a charging connector',{'close','detail'}),
    ('Close view of a charging connector',{'close','detail'}),
    ('Wide establishing shot of a charging station',{'wide'}),
    ('Medium shot of the narrated subject',{'medium'}),
    ('Map graphic of forest habitat',{'graphic','detail','wide'}),
    ('Panther habitat forest landscape',{'environment','wide','medium','detail'}),
    ('An infographic diagram of charging',{'graphic','detail','wide'}),
    ('Show driving electric vehicle movement',{'medium','wide','close','detail','object','movement'}),
    ('Show the narrated subject',{'medium','wide','close'}),
])
def test_missing_composition_varies_only_with_compatible_nonfactual_framing(intent,allowed):
    source=script(7,9);units=narration_units(source)
    raw={'scenes':[minimal([u['unit_id']]) for u in units]}
    for b in raw['scenes']:b['visual_intent']=intent
    blocks=visual_blocks(raw,source,'de',135)
    assert len({b['composition'] for b in blocks})>=min(2,len(allowed)) and all(b['composition'] in allowed for b in blocks)
    assert all(b['entities']==[] and b['location']=='' and b['action']=='' for b in blocks)
    if len(allowed)>1:assert not any('kompozisyon' in w for w in scene_checks(blocks,source))


def test_default_variety_continues_across_context_chunks():
    source=script(2,9);units=narration_units(source)
    first=visual_blocks({'scenes':[minimal(['U1'])]},units[0]['text'],'de',135,units=units[:1])
    second=visual_blocks({'scenes':[minimal(['U2'])]},units[1]['text'],'de',135,first[-1]['end'],units=units[1:],previous=first)
    assert first[0]['composition']!=second[0]['composition']
    assert first[0]['stock_query']!=second[0]['stock_query']
    assert ''.join(b['narration'] for b in first+second)==source


def test_default_static_image_motion_varies_but_explicit_none_is_still_checked():
    source=script(5,9);units=narration_units(source)
    raw={'scenes':[minimal([u['unit_id']]) for u in units]}
    for b in raw['scenes']:b['media_type']='stock_image'
    moving=visual_blocks(raw,source,'de',135)
    assert {b['motion'] for b in moving}=={'slow_zoom','pan'}
    assert not any('sabit görsel' in w for w in scene_checks(moving,source))
    for b in raw['scenes']:b['motion']='none'
    static=visual_blocks(raw,source,'de',135)
    assert all(b['motion']=='none' for b in static)
    assert any('sabit görsel' in w for w in scene_checks(static,source))


def test_subdivided_visual_metadata_stays_related_and_overlay_is_not_duplicated():
    source=script(9,9);units=narration_units(source)
    parent=minimal([u['unit_id'] for u in units]);parent.update(overlay_text='E-Autos',entities=['electric car'],
                                                            location='charging station',action='charging',notes='Kullanıcı notu')
    blocks=visual_blocks({'scenes':[parent]},source,'de',135)
    assert len(blocks)>1 and blocks[1]['stock_query']!=blocks[0]['stock_query']
    assert blocks[0]['overlay_text']=='E-Autos' and all(b['overlay_text']=='' for b in blocks[1:])
    for b in blocks:
        assert all(b[field]==parent[field] for field in ('purpose','mood','visual_intent','entities','location','action','notes'))
        assert b['stock_query'].startswith(('electric car charging station','electric vehicle charging'))
        assert all(len(q.split())<=12 for q in [b['stock_query'],*b['alternative_stock_queries']])
    assert_exact_boundaries(blocks,units)


def test_single_scene_redesign_does_not_silently_change_other_scene_boundaries():
    source=script(9,9);units=narration_units(source)
    blocks=visual_blocks({'scenes':[minimal([u['unit_id'] for u in units])]},source,'de',135,single=True)
    assert len(blocks)==1 and blocks[0]['narration']==source
    assert 'tüm planı' in blocks[0]['pacing_reason']


@pytest.mark.parametrize('provider',['ollama','gemini'])
def test_native_provider_coarse_response_is_improved_in_one_call_and_handoff_persists(production_studio,provider):
    client,project,_,data=production_studio;source=set_source(production_studio,script());calls=[]
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
        result=json.dumps(coarse(payload['narration_units']))
        if provider=='ollama':return httpx.Response(200,json={'done':True,'response':result,'thinking':OTHER_KEY})
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':result}]}}]})
    transport=httpx.MockTransport(respond)
    client.app.state.scripts.provider_factory=lambda name,settings: OllamaScriptProvider('http://localhost:11434','qwen3.5:9b',transport=transport) if name=='ollama' else GeminiScriptProvider(KEY,MODEL,transport=transport)
    job=start_and_wait(production_studio,provider);current=view(production_studio)
    assert job['status']=='draft' and len(calls)==1 and 'visual_repair' not in job['progress']
    assert len(current['plan']['blocks'])>5 and current['plan']['blocks'][-1]['end']==180
    assert current['coverage_complete'] and ''.join(b['narration'] for b in current['plan']['blocks'])==source
    assert all(b['estimated_duration']<=18 for b in current['plan']['blocks'])
    handoff=client.get(route(project)+'/handoff').json()
    assert handoff['contract_version']==1 and len(handoff['scenes'])==len(current['plan']['blocks'])
    assert ''.join(b['narration_text'] for b in handoff['scenes'])==source
    assert all(b['scene_id'] and b['primary_stock_query'] and b['alternative_stock_queries'] for b in handoff['scenes'])
    assert KEY not in json.dumps(current) and OTHER_KEY not in json.dumps(job)
    assert all('_editing_defaults' not in b for b in current['plan']['blocks'])
    with TestClient(create_app(data),headers=HEADERS) as restarted:assert restarted.get(route(project)).json()==current


def test_failed_native_ollama_json_keeps_valid_gemini_plan_history_and_files(production_studio):
    client,project,_,data=production_studio
    source=set_source(production_studio,script());install_response(production_studio,lambda raw,payload:coarse(payload['narration_units']))
    assert start_and_wait(production_studio,'gemini')['status']=='draft'
    before=view(production_studio)
    assert before['plan']['provider']=='gemini' and before['coverage_complete']
    folder=data/'projects'/project['id']/'scenes';files={p.name:p.read_bytes() for p in folder.glob('*.json')};calls=[]
    def invalid(request):
        calls.append(request.url.path)
        return httpx.Response(200,json={'done':True,'response':'{broken JSON '+KEY,'thinking':OTHER_KEY})
    client.app.state.scripts.provider_factory=lambda name,settings:OllamaScriptProvider('http://localhost:11434','qwen3.5:9b',transport=httpx.MockTransport(invalid))
    job=start_and_wait(production_studio)
    assert job['status']=='error' and job['progress']['error_diagnostic']=='invalid_scene_schema:json'
    assert calls==['/api/generate'] and 'visual_repair' not in job['progress']
    assert view(production_studio)==before and ''.join(b['narration'] for b in before['plan']['blocks'])==source
    assert {p.name:p.read_bytes() for p in folder.glob('*.json')}==files
    assert KEY not in json.dumps(job) and OTHER_KEY not in json.dumps(job)
    with TestClient(create_app(data),headers=HEADERS) as restarted:assert restarted.get(route(project)).json()==before


def test_locked_long_scene_keeps_identity_metadata_and_explicit_reason(production_studio):
    # Existing owner locks remain authoritative even if their source unit is long.
    assert action(production_studio,1,'lock').status_code==200
    locked=deepcopy(view(production_studio)['plan']['blocks'][1])
    updated=generate(production_studio)
    assert next(b for b in updated['plan']['blocks'] if b['id']==locked['id'])==locked
    assert updated['coverage_complete']
    assert any('Kilitli sahne kullanıcı tercihiyle aynen korundu' in w for w in updated['scene_warnings'])
