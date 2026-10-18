"""Loss-aware manual import: all media are synthetic, Gemini is mocked."""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest
from app.editor.advanced import AdvancedEditor
from app.editor.editorial import Editorial
from app.editor.manual_review import parse_response,review,legacy_item
from app.editor.models import EditorError
from test_simple_workflow import workflow
from test_plan_intervals import plan,selected
from test_advanced_editing import advanced,change


def test_multipart_response_is_strict_and_metadata_must_agree():
    a={'schema':'naman.manual-plan.v1','base':{'plan_id':'p','revision':1},'sahneler':[{'scene_id':'s'}]}
    b={'vurgular':[{'scene_id':'s','text':'Roma'}]}
    merged=parse_response('İlk bölüm\n```json\n'+json.dumps(a)+'\n```\nİkinci bölüm\n'+json.dumps(b))
    assert merged['sahneler']==a['sahneler'] and merged['vurgular']==b['vurgular'] and merged['katmanlar']==[]
    with pytest.raises(EditorError):parse_response(json.dumps(a)+' '+json.dumps({**b,'base':{'plan_id':'other'}}))


@pytest.mark.parametrize('text',[
    '{"sahneler":[],"sahneler":[]}', '{"sahneler":[{"a":1,}]}',
    '{"sahneler": [NaN]}', '{"sahneler": [{"start":1e309}]}', '{"sahneler":[]} {"vurgular":',
    '[{"sahneler":[]}]', '```python\n{"sahneler":[]}\n```',
    '{"unknown":{"sahneler":[]}}', '{"sahneler":[]} {"sahneler":[]}',
    '<think>{"sahneler":[]}</think>', '{"sahneler":[]} []',
    '{"sahneler":[]} {"vurgular":[],"base":1} {"base":2,"katmanlar":[]}',
])
def test_bad_json_is_not_repaired_or_partially_recovered(text):
    with pytest.raises(EditorError):parse_response(text)


def sample(workflow):
    client,pid=workflow;url=f'/api/projects/{pid}/editor';ed=AdvancedEditor(client.app.state.editor)
    package=client.get(url+'/manual/package').json();payload=deepcopy(package['output_template']);scene=package['narration'][0]
    item={'scene_id':scene['scene_id'],'start':scene['start'],'end':scene['end'],'text':'Roma','object_id':'one'}
    return client,pid,url,ed,package,payload,item


def test_bad_records_remain_reviewable_and_valid_edits_can_be_partially_approved(workflow):
    client,pid,url,ed,package,payload,item=sample(workflow)
    original=ed.get(pid)
    payload['katmanlar']=[item,{**item,'text':'yanlış ifade','object_id':'other'},
                          {**item,'end':999,'object_id':'bad-time'},deepcopy(item),{'scene_id':[]},42]
    validated=client.post(url+'/manual/validate',json=payload)
    assert validated.status_code==200 and not validated.json()['valid'] and len(validated.json()['import_issues'])==5
    assert not Editorial(ed.editor).drafts(pid)['drafts'] and ed.get(pid)==original
    response=client.post(url+'/manual/response-draft',json={'text':json.dumps(payload)})
    assert response.status_code==201,response.text
    draft=response.json();assert len(draft['clips'])==1 and len(draft['import_issues'])==5
    assert draft['original_response']==payload and ed.get(pid)==original
    assert '999' in draft['correction_message'] and 'Roma' in draft['correction_message']
    stored=Editorial(ed.editor).drafts(pid)['drafts'][0]
    assert stored['import_issues']==draft['import_issues']
    preview=client.get(url+f'/editorial/drafts/{draft["id"]}/preview?time=0.1')
    assert preview.status_code==200 and preview.headers['content-type']=='image/jpeg'
    approve=url+f'/editorial/drafts/{draft["id"]}/approve'
    assert client.post(approve,json={'confirmed':False,'clip_ids':selected(draft)}).status_code==422
    assert ed.get(pid)==original
    assert client.post(approve,json={'confirmed':True,'clip_ids':[draft['clips'][0]['id']]}).status_code==200
    assert len(ed.get(pid)['document']['clips'])==1
    assert len(Editorial(ed.editor).drafts(pid)['drafts'][0]['import_issues'])==5
    assert client.app.state.editor.task_package(pid)['voice']==package['voice']
    assert client.app.state.editor.task_package(pid)['subtitles']==package['subtitles']


def test_repair_only_bad_operation_keeps_valid_draft_and_existing_manual_content(workflow):
    client,pid,url,ed,package,payload,item=sample(workflow)
    payload['katmanlar']=[item,{**item,'end':999,'object_id':'two'}]
    draft=client.post(url+'/manual/response-draft',json={'text':json.dumps(payload)}).json()
    repair=deepcopy(draft['original_response']);repair['katmanlar'][1].update(object_id='two',text='Roma',start=item['start'],end=item['end'])
    fixed=client.post(url+'/manual/response-draft',json={'text':json.dumps(repair)}).json()
    assert len(fixed['clips'])==2 and not fixed['import_issues']
    assert len(Editorial(ed.editor).drafts(pid)['drafts'])==2 and ed.get(pid)['revision']==0


def test_global_stale_base_is_not_salvaged(workflow):
    client,pid,url,ed,package,payload,item=sample(workflow);before=ed.get(pid)
    payload['base']['revision']+=1;payload['katmanlar']=[item]
    assert client.post(url+'/manual/response-draft',json={'text':json.dumps(payload)}).status_code==409
    assert ed.get(pid)==before and not Editorial(ed.editor).drafts(pid)['drafts']


def test_legacy_adapter_only_maps_exact_sentence_clock_and_supported_semantics():
    pack={'subtitles':{'cues':[{'start':0.,'end':1.,'text':'Roma'}]},'narration':[{'scene_id':'s','start':0.,'end':2.}]}
    item=legacy_item('vurgular',{'cumle_no':0,'ekran':['Roma']},pack)
    assert item=={'scene_id':'s','start':0.,'end':1.,'text':'Roma','effect':'none'}
    stat=legacy_item('infografikler',{'cumle_no':0,'tur':'veri','buyuk':'40','kucuk':'km'},pack)
    assert stat['template']=='stat' and stat['data']['value']=='40'
    for section,record in [('sahneler',{'cumleler':[0],'dosya':'not-real.mp4'}),('harita_sahneleri',{'cumle_bas':0,'plan':{'tur':'sema'}}),('vurgular',{'cumle_no':0,'ekran':['Roma'],'ses':'tik'})]:
        with pytest.raises(EditorError):legacy_item(section,record,pack)
    pack['narration'][0]['end']=.5
    with pytest.raises(EditorError):legacy_item('vurgular',{'cumle_no':0,'ekran':['Roma']},pack)


def test_bad_camera_conflicts_and_short_transitions_keep_valid_proposals(plan,monkeypatch):
    editorial,ed,pid,view,payload=plan
    view['tracks']['visuals'][0]['media'].update(media_type='video',duration=4.)
    monkeypatch.setattr(editorial.editor,'task_package',lambda pid:{'schema':payload['schema'],'base':payload['base'],'output_template':{**payload,**{s:[] for s in ('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar')}},'narration':view['scenes'],'subtitles':{'cues':[]}},raising=False)
    payload['sahneler']=payload['sahneler'][:2]
    payload['sahneler'].insert(1,{**payload['sahneler'][0],'object_id':'conflict'})
    before=ed.get(pid);draft=review(editorial,pid,payload)
    assert len(draft['import_issues'])==1 and len(draft['transition_issues'])==1
    assert len(draft['adjustments'])==2 and ed.get(pid)==before
    issue=draft['transition_issues'][0]
    fixed=editorial.resolve_transition(pid,draft['id'],{'confirmed':True,'issue_id':issue['id'],'option_id':'hard_cut'})
    assert fixed['import_issues']==draft['import_issues'] and ed.get(pid)==before
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':selected(fixed)})
    assert len(ed.get(pid)['document']['adjustments'])==2


def test_complete_package_gemini_multipart_draft_approval_short_real_render(workflow,monkeypatch):
    from test_rendering import await_job
    client,pid,url,ed,package,payload,item=sample(workflow);calls=[]
    def complete(purpose,prompt,*args,**kwargs):
        calls.append((purpose,prompt));return {'instructions':['Gerçek kaynakları ve kilitleri koru; yalnız NAMAN işlemleri öner.']}
    monkeypatch.setattr('app.providers.factory.make_script_provider',lambda *a,**k:SimpleNamespace(complete_json=complete))
    assert client.post(url+'/manual/package/prepare',json={}).status_code==409 and not calls
    pack=client.post(url+'/manual/package/prepare',json={'cost_confirmed':True}).json()
    assert pack['prepared_by']=='gemini' and pack['sentence_index'] and pack['editing_slots']
    assert all('media' in slot for slot in pack['editing_slots'])
    video=next(x for x in pack['archive'] if x['media_type']=='video')
    timing={k:item[k] for k in ('scene_id','start','end')}
    payload['sahneler']=[{**timing,'media':{k:video[k] for k in ('provider','media_id','sha256')},'source_start':.1,'motion':'pan'}]
    payload['infografikler']=[{**timing,'template':'stat','data':{'value':'40','label':'kilómetros'}}]
    payload['harita_sahneleri']=[{**timing,'template':'map','data':{'place':'Roma','label':'Roma','lat':41.9,'lon':12.5}}]
    payload['vurgular']=[{**timing,'text':'Roma','effect':'pulse'}]
    payload['katmanlar']=[item]
    first={k:v for k,v in payload.items() if k!='katmanlar'}
    second={'katmanlar':[item,{**item,'object_id':'bad','start':999}]}
    before=ed.get(pid)
    response=client.post(url+'/manual/response-draft',json={'text':json.dumps(first)+'\n```json\n'+json.dumps(second)+'\n```'})
    assert response.status_code==201,response.text
    draft=response.json();assert len(draft['clips'])==5 and len(draft['import_issues'])==1 and ed.get(pid)==before
    assert client.get(url+f'/editorial/drafts/{draft["id"]}/preview?time=0.1').status_code==200
    assert client.post(url+f'/editorial/drafts/{draft["id"]}/approve',json={'confirmed':True,'clip_ids':selected(draft)}).status_code==200
    assert client.post(f'/api/projects/{pid}/render/jobs',json={'encoder':'cpu'}).status_code==202
    result=await_job({'client':client,'pid':pid});assert result['job']['status']=='completed',result
    assert len(calls)==1 and {c['kind'] for c in ed.get(pid)['document']['clips']}=={'media','motion','text'}


def test_imported_archive_video_uses_existing_clip_pipeline_and_preserves_sources(workflow):
    client,pid,url,ed,package,payload,item=sample(workflow)
    video=next(a for a in package['archive'] if a['media_type']=='video')
    ref={k:video[k] for k in ('provider','media_id','sha256')}
    before=ed.editor.view(pid);old=ed.get(pid)
    payload['sahneler']=[{'scene_id':item['scene_id'],'media':ref,'source_start':.1,'motion':'slow_zoom','object_id':'source-video'},
                         {'scene_id':item['scene_id'],'media':ref,'source_start':999.,'object_id':'short-video'}]
    response=client.post(url+'/manual/response-draft',json={'text':json.dumps(payload)})
    assert response.status_code==201,response.text
    draft=response.json();assert len(draft['clips'])==1 and len(draft['import_issues'])==1
    assert draft['import_issues'][0]['category']=='short_source' and 'short-video' in draft['correction_message']
    clip=draft['clips'][0];assert clip['kind']=='media' and clip['keyframes'] and clip['source_start']==.1
    assert ed.get(pid)==old and client.get(url+f'/editorial/drafts/{draft["id"]}/preview?time=0.1').status_code==200
    assert client.post(url+f'/editorial/drafts/{draft["id"]}/approve',json={'confirmed':True,'clip_ids':selected(draft)}).status_code==200
    assert ed.editor.view(pid)['tracks']==before['tracks']


def test_legacy_archive_reference_is_exact_and_unknown_files_remain_visible():
    pack={'subtitles':{'cues':[{'start':0.,'end':1.,'text':'Roma'}]},'narration':[{'scene_id':'s','start':0.,'end':2.}],
          'archive':[{'file_name':'exact.mp4','media_type':'video','provider':'local','media_id':'v','sha256':'a'*64}]}
    item=legacy_item('sahneler',{'cumleler':[0],'dosya':'exact.mp4','kaynak_bas':.5},pack)
    assert item['media']['media_id']=='v' and item['source_start']==.5 and item['end']==1.
    for name in ('Exact.mp4','../exact.mp4','C:\\exact.mp4','missing.mp4'):
        with pytest.raises(EditorError):legacy_item('sahneler',{'cumleler':[0],'dosya':name},pack)


def test_unsupported_cut_does_not_discard_camera_in_the_same_operation(plan,monkeypatch):
    editorial,ed,pid,view,payload=plan
    monkeypatch.setattr(editorial.editor,'task_package',lambda pid:{'schema':payload['schema'],'base':payload['base'],'output_template':{**payload,**{s:[] for s in ('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar')}},'narration':view['scenes'],'subtitles':{'cues':[]}},raising=False)
    payload['sahneler']=[{'scene_id':'scene-1','start':0.,'end':1.,'motion':'pan','transition':'crossfade','object_id':'camera-and-bad-cut'}]
    draft=review(editorial,pid,payload)
    assert len(draft['adjustments'])==1 and not draft['transitions'] and len(draft['import_issues'])==1
    assert draft['import_issues'][0]['original']['transition']=='crossfade'
    assert draft['import_issues'][0]['retained_fields']==['motion'] and 'motion=none' in draft['correction_message']
    assert draft['accepted_response']['sahneler'][0]['transition']=='none' and ed.get(pid)['revision']==0


def test_parser_preserves_braces_and_fences_inside_json_string_data():
    item={'sahneler':[],'katmanlar':[{'text':'{"inside": "```python"}'}]}
    assert parse_response('```json\n'+json.dumps(item)+'\n```')['katmanlar']==item['katmanlar']


def test_malformed_operations_are_reported_without_http_500(workflow):
    client,pid,url,ed,package,payload,item=sample(workflow);before=ed.get(pid)
    for section,records in [
        ('sahneler',[{'motion':[]},{'media':[]},{'source_start':[]},{'object_id':{}},{'transition':{}},{'start':{}}]),
        ('harita_sahneleri',[{'template':[],'data':{}},{'template':'map','data':None}]),
        ('katmanlar',[{'text':{}},{'scene_id':{}},{'object_id':[],'text':'Roma'}])]:
        plan=deepcopy(payload);plan[section]=[{**item,**r} for r in records]
        response=client.post(url+'/manual/response-draft',json={'text':json.dumps(plan)})
        assert response.status_code==201,response.text
        assert len(response.json()['import_issues'])==len(records) and ed.get(pid)==before


def test_partial_review_preserves_locked_media_manual_edits_voice_and_subtitles(plan,monkeypatch):
    editorial,ed,pid,view,payload=plan
    change(ed,pid,lambda d:d['clips'].append({'id':'b'*32,'kind':'text','track':'layers','text':'Manuel karar','locked':True,'start':20.,'end':22.}))
    change(ed,pid,lambda d:d['adjustments'].append({'slot_id':'slot-1','transform':{'rotation':17.}}))
    view['tracks']['visuals'][0]['locked']=True
    monkeypatch.setattr(editorial.editor,'task_package',lambda pid:{'schema':payload['schema'],'base':payload['base'],'output_template':{**payload,**{s:[] for s in ('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar')}},'narration':view['scenes'],'subtitles':{'cues':[]}},raising=False)
    payload['sahneler']=payload['sahneler'][:2];before=ed.get(pid);sources=deepcopy(view)
    draft=review(editorial,pid,payload)
    assert len(draft['import_issues'])==1 and draft['import_issues'][0]['category']=='locked'
    assert ed.get(pid)==before and view==sources
    editorial.approve(pid,draft['id'],{'confirmed':True,'clip_ids':selected(draft)})
    after=ed.get(pid)['document']
    assert after['clips']==before['document']['clips']
    assert before['document']['adjustments'][0] in after['adjustments']
    assert view==sources
