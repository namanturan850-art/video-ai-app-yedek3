"""Manual package/draft round trip; real SQLite, synthetic media, no cloud calls."""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.editor.advanced import AdvancedEditor
from app.editor.history import History
from test_manual_first import install_manual_example
from test_scripts import HEADERS


@pytest.fixture
def workflow(tmp_path):
    with TestClient(create_app(tmp_path),headers=HEADERS) as client:
        st=install_manual_example(client.app)
        yield client,st['pid']


def test_gemini_package_contains_context_but_never_writes_timeline(workflow,monkeypatch):
    client,pid=workflow;editor=client.app.state.editor;advanced=AdvancedEditor(editor);history=History(editor)
    before=advanced.get(pid);events=history.snapshot(pid);requests=[]
    def complete(purpose,prompt,schema,**kwargs):
        requests.append((purpose,prompt))
        return {'instructions':['Verilen cümle ve medya listesini kullan.']}
    monkeypatch.setattr('app.providers.factory.make_script_provider',lambda *a,**k:SimpleNamespace(complete_json=complete))
    base=f'/api/projects/{pid}/editor'
    assert client.post(base+'/manual/package/prepare',json={}).status_code==409
    assert requests==[]
    response=client.post(base+'/manual/package/prepare',json={'cost_confirmed':True})
    assert response.status_code==200,response.text
    pack=response.json();assert pack['prepared_by']=='gemini'
    assert pack['narration'] and pack['subtitles']['cues'] and pack['visuals'] and pack['sounds']
    assert pack['voice']['version_id'] and pack['voice']['audio']['duration']>0
    assert pack['timeline']==before
    assert all(x['start'] is not None and x['start']<x['end'] for x in pack['narration'])
    assert pack['output_contract']['sahneler']['composition']==['wide']
    assert pack['output_contract']['harita_sahneleri']['templates']==['map']
    assert 'local_path' not in json.dumps(pack) and 'api_key' not in json.dumps(pack)
    assert requests[0][0]=='manual_plan_package' and 'output_template' in requests[0][1]
    assert advanced.get(pid)==before and history.snapshot(pid)==events


def test_text_response_is_draft_then_only_explicit_approval_persists(workflow):
    client,pid=workflow;base=f'/api/projects/{pid}/editor';editor=client.app.state.editor;advanced=AdvancedEditor(editor)
    pack=client.get(base+'/manual/package').json();plan=deepcopy(pack['output_template'])
    scene=editor.view(pid)['scenes'][0]
    plan['katmanlar']=[{'scene_id':scene['scene_id'],'text':'Roma','start':scene['start'],'end':scene['end']}]
    before=advanced.get(pid)
    response=client.post(base+'/manual/response-draft',json={'text':'Plan hazır:\n```json\n'+json.dumps(plan)+'\n```'})
    assert response.status_code==201,response.text
    draft=response.json();assert advanced.get(pid)==before
    response=client.post(base+f'/editorial/drafts/{draft["id"]}/approve',json={'confirmed':True,'clip_ids':[c['id'] for c in draft['clips']]})
    assert response.status_code==200,response.text
    assert AdvancedEditor(editor).get(pid)['document']['clips'][0]['text']=='Roma'
    assert client.get(base+'/advanced/program-frame?time=0').status_code==200
    saved=advanced.get(pid)
    for text in ('yalnız serbest açıklama',json.dumps(plan)+' '+json.dumps(plan),'```python\n'+json.dumps(plan)+'\n```'):
        assert client.post(base+'/manual/response-draft',json={'text':text}).status_code==422
        assert advanced.get(pid)==saved


def test_package_rejects_context_that_changed_during_gemini(workflow,monkeypatch):
    client,pid=workflow;editor=client.app.state.editor;original=editor.task_package;calls=0
    def package(_):
        nonlocal calls
        calls+=1;result=original(pid)
        if calls>1:result['stock']['revision']=999
        return result
    monkeypatch.setattr(editor,'task_package',package)
    monkeypatch.setattr('app.providers.factory.make_script_provider',lambda *a,**k:SimpleNamespace(complete_json=lambda *a,**k:{'instructions':['Kuralları koru.']}))
    response=client.post(f'/api/projects/{pid}/editor/manual/package/prepare',json={'cost_confirmed':True})
    assert response.status_code==409,response.text
    assert AdvancedEditor(editor).get(pid)['document']['clips']==[]


def test_missing_map_source_uses_only_local_map_and_never_infographic(monkeypatch):
    from app.stock.director_media import MediaDirector
    director=MediaDirector.__new__(MediaDirector);director.owner={};director.sources_only=True
    director.language='tr';director._release=lambda slot:None
    calls=[]
    director.motion=lambda slot,scene,log,spec,stage:calls.append((spec,stage))
    director.unresolved=lambda slot,log:log.update(missing=True)
    slot={'slot_id':'one','estimated_start':0,'estimated_end':2}
    scene={'scene_id':'s','narration_text':'Roma','motion_spec':{'template':'map','data':{'place':'Roma','lat':41.9,'lon':12.5}}}
    director.handle(slot,scene,'source_map')
    assert calls[0][0]['template']=='map' and calls[0][1]=='source_map'
    scene['motion_spec']={'template':'stat','data':{'value':'40'}}
    assert director.handle(slot,scene,'source_map')['missing']
    assert len(calls)==1


def test_media_completion_schedules_maps_but_leaves_infographics_empty(workflow,monkeypatch):
    from contextlib import closing
    from app.stock.director_media import MediaDirector
    client,pid=workflow;stock=client.app.state.stock;projects=client.app.state.projects
    with closing(projects._connection()) as connection:
        state=stock._load(connection,pid,stock.view(pid)['plan_id'])
    source=deepcopy(next(s['selected_media'] for s in state['slots'] if s.get('selected_media')))
    for slot in state['slots']:slot.update(selected_media=None,status='pending')
    with closing(projects._connection()) as connection,connection:stock._save(connection,state)
    original=stock._handoff
    def handoff(_):
        result=deepcopy(original(pid))
        for i,scene in enumerate(result['scenes']):
            scene['owner_hints']=[]
            scene['motion_spec']=({'template':'map','data':{'place':'Roma','label':'Roma','lat':41.9,'lon':12.5},'emphasis':''} if i==0 else
                                  {'template':'stat','data':{'value':'40','label':''},'emphasis':''})
        return result
    monkeypatch.setattr(stock,'_handoff',handoff)
    for name in ('try_local_archive','try_step','extended_search'):
        monkeypatch.setattr(MediaDirector,name,lambda *a,**k:False)
    calls=[]
    def draw(self,slot,scene,log,spec=None,stage='motion'):
        calls.append((spec,stage));assert spec['template']=='map' and stage=='source_map'
        slot.update(selected_media={**source,'provider':'generated','media_id':'test-source-map','source_metadata':{'motion':spec}},status='complete')
        log['steps'].append({'stage':stage,'label':'Harita kaynağı','result':'chosen'})
    monkeypatch.setattr(MediaDirector,'motion',draw)
    current=stock.view(pid)
    job=stock.start(pid,{'plan_id':current['plan_id'],'revision':current['revision'],'action':'complete_media'})
    stock.futures[job['job_id']].result(timeout=30)
    result=stock.view(pid)
    assert result['job']['status']=='completed' and not result['job']['progress'].get('slot_errors'),result['job']
    assert len(calls)==1
    assert sum(bool(slot.get('selected_media')) for slot in result['slots'])==1
    assert AdvancedEditor(client.app.state.editor).get(pid)['document']['clips']==[]


def test_subtitle_frame_boundary_is_compared_at_storage_precision():
    from app.subtitles.models import validate_cues, SubtitleError
    split=41/30
    cues=validate_cues([{'start':0.,'end':split,'text':'Birinci'},
                        {'start':split,'end':2.,'text':'İkinci'}],2.)
    assert cues[0]['end']==cues[1]['start']==1.367
    with pytest.raises(SubtitleError,match='örtüşmemeli'):
        validate_cues([{'start':0.,'end':split,'text':'Birinci'},
                       {'start':split-.01,'end':2.,'text':'İkinci'}],2.)
