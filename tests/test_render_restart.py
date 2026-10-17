from test_rendering import ready,await_job,url
from app.rendering.models import RenderError


def test_verified_restart_checks_identity_and_preserves_failed_job(ready,monkeypatch):
    st=ready;client=st['client'];service=client.app.state.rendering
    actual_factory=service.factory
    class Failed:
        def __init__(self,*args):pass
        def render(self,*args):raise RenderError('render_failed','Sentetik kesinti')
    service.factory=Failed
    created=client.post(url(st)+'/jobs',json={'encoder':'cpu','editing_style':'basic','subtitle_display':'none'})
    assert created.status_code==202
    previous=created.json()['job_id'];failed=await_job(st)
    assert failed['job']['status']=='error'
    restart=url(st)+f'/jobs/{previous}/restart'
    assert client.post(restart,json={}).status_code==422
    actual_inputs=service._inputs
    def changed(*args,**kwargs):return {**actual_inputs(*args,**kwargs),'fingerprint':'changed'}
    monkeypatch.setattr(service,'_inputs',changed)
    assert client.post(restart,json={'confirmed':True}).status_code==409
    monkeypatch.setattr(service,'_inputs',actual_inputs);service.factory=actual_factory
    restarted=client.post(restart,json={'confirmed':True})
    assert restarted.status_code==202,restarted.text
    assert restarted.json()['resume_mode']=='verified_restart' and restarted.json()['job_id']!=previous
    finished=await_job(st)
    assert finished['job']['status']=='completed',finished
    assert finished['active']['version']==2
