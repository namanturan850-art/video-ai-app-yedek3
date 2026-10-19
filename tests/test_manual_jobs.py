"""Bounded background review, large valid JSON, isolation and explicit approval."""
from copy import deepcopy
import json
import time
from threading import Event

from app.editor.advanced import AdvancedEditor
from app.editor.editorial import Editorial
from app.editor.manual_review import parse_response,MAX_RESPONSE_CHARS
from app.editor.models import EditorError
from test_simple_workflow import workflow
import pytest


def wait(client,url):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        response=client.get(url);assert response.status_code==200,response.text
        job=response.json()
        if job['status'] in ('completed','failed'):return job
        time.sleep(.02)
    raise AssertionError('review did not complete')


def payload_for(client,pid,count=150):
    base=f'/api/projects/{pid}/editor';pack=client.get(base+'/manual/package').json()
    payload=deepcopy(pack['output_template']);scene=pack['narration'][0]
    payload['katmanlar']=[{'scene_id':scene['scene_id'],'start':scene['start']+i*.001,
        'end':scene['start']+i*.001+.04,'text':'Roma','effect':'none','object_id':str(i)} for i in range(count)]
    # Whitespace is valid external JSON and must not trigger the old 200k cap.
    text=json.dumps(payload,ensure_ascii=False,indent=100)
    assert 200000<len(text)<MAX_RESPONSE_CHARS
    return base,text


def test_large_json_is_reviewed_once_and_only_explicit_selection_is_applied(workflow,monkeypatch):
    client,pid=workflow;base,text=payload_for(client,pid);ed=AdvancedEditor(client.app.state.editor);before=ed.get(pid)
    calls=[];original=Editorial._import_draft
    def counted(self,*args,**kwargs):calls.append(1);return original(self,*args,**kwargs)
    monkeypatch.setattr(Editorial,'_import_draft',counted)
    started=client.post(base+'/manual/response-jobs',json={'text':text});assert started.status_code==202,started.text
    job=wait(client,started.json()['status_url']);assert job['status']=='completed',job
    draft=job['draft'];assert len(draft['clips'])==150 and draft['import_issues']==[]
    assert calls==[1]  # no O(N) recompiles of growing prefixes
    assert ed.get(pid)==before
    approve=base+f'/editorial/drafts/{draft["id"]}/approve'
    assert client.post(approve,json={'confirmed':False,'clip_ids':[draft['clips'][0]['id']]}).status_code==422
    assert ed.get(pid)==before
    assert client.post(approve,json={'confirmed':True,'clip_ids':[draft['clips'][0]['id']]}).status_code==200
    assert len(ed.get(pid)['document']['clips'])==1


def test_slow_validation_keeps_submission_polling_and_health_responsive(workflow,monkeypatch):
    client,pid=workflow;base,text=payload_for(client,pid);gate=Event();entered=Event();original=Editorial._import_draft
    def slow(self,*a,**kw):
        entered.set();assert gate.wait(10);return original(self,*a,**kw)
    monkeypatch.setattr(Editorial,'_import_draft',slow)
    started=time.monotonic();response=client.post(base+'/manual/response-jobs',json={'text':text})
    assert response.status_code==202 and time.monotonic()-started<2
    try:
        assert entered.wait(3)
        started=time.monotonic();state=client.get(response.json()['status_url']);assert state.json()['status']=='running'
        assert time.monotonic()-started<2
        assert client.get('/api/health').status_code==200
        duplicate=client.post(base+'/manual/response-jobs',json={'text':text});assert duplicate.json()['id']==response.json()['id']
        different=client.post(base+'/manual/response-jobs',json={'text':text+' '});assert different.status_code==409
    finally:gate.set()
    assert wait(client,response.json()['status_url'])['status']=='completed'


def test_invalid_json_job_reports_error_and_does_not_change_timeline(workflow):
    client,pid=workflow;base=f'/api/projects/{pid}/editor';ed=AdvancedEditor(client.app.state.editor);before=ed.get(pid)
    r=client.post(base+'/manual/response-jobs',json={'text':'{"sahneler":[NaN]}'})
    job=wait(client,r.json()['status_url']);assert job['status']=='failed' and job['category']=='invalid_response'
    assert ed.get(pid)==before and not Editorial(ed.editor).drafts(pid)['drafts']
    assert client.post(base+'/manual/response-jobs',json={'text':'x'*(MAX_RESPONSE_CHARS+1)}).status_code==422
    assert client.get(base+'/manual/response-jobs/'+'a'*32).status_code==404
    assert client.get('/api/projects/'+'f'*32+'/editor/manual/response-jobs/'+job['id']).status_code==404


def test_mixed_job_preserves_valid_operations_and_persisted_job_can_be_read(workflow,monkeypatch):
    client,pid=workflow;base,text=payload_for(client,pid);payload=json.loads(text)
    payload['katmanlar']=payload['katmanlar'][:1]+[{'scene_id':[], 'text':'bad'}]
    r=client.post(base+'/manual/response-jobs',json={'text':json.dumps(payload)})
    job=wait(client,r.json()['status_url']);assert job['status']=='completed',job
    assert len(job['draft']['clips'])==1 and len(job['draft']['import_issues'])==1
    import app.editor.manual_jobs as jobs
    # Completed task persistence must not depend on an in-process Future.
    with jobs._lock:
        keys=[k for k in jobs._jobs if k[1:]==(pid,job['id'])]
        for k in keys:future=jobs._jobs[k]['future']
    for k in keys:future.result(timeout=5)
    with jobs._lock:
        for k in keys:jobs._jobs.pop(k,None)
    saved=client.get(r.json()['status_url']);assert saved.status_code==200 and saved.json()['draft']['id']==job['draft']['id']
