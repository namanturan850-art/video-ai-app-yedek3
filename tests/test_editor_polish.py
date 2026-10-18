from copy import deepcopy
import json
import subprocess

import pytest
from test_advanced_editing import advanced,change
from app.editor.operations import operate
from app.editor.advanced import Document,AdvancedEditor
from app.editor.models import EditorError
from app.editor.compositor import value_at,expression,compile_graph
from app.editor.curves import progress


def seed(advanced):
    ed,pid,view,digest=advanced
    for i,start in enumerate([0.,1.,2.]):
        change(ed,pid,lambda d:d['clips'].append({'id':str(i+1)*32,'kind':'text','track':'layers','start':start,'end':start+3.,'text':'Not'}))
    return ed,pid,view


def operation(ed,pid,action,**kw):
    state=ed.get(pid)
    return operate(ed,pid,{'plan_id':state['plan_id'],'revision':state['revision'],'ids':[c['id'] for c in state['document']['clips']], 'action':action,**kw})


def test_group_atomic_history_reopen_and_rejection(advanced):
    ed,pid,view=seed(advanced);original=deepcopy(view)
    saved=operation(ed,pid,'move',delta=2.)
    assert [c['start'] for c in saved['document']['clips']]==[2,3,4]
    assert saved['revision']==4 and view==original
    assert AdvancedEditor(ed.editor).get(pid)['document']==saved['document']
    undone=ed.history(pid,'undo',{'plan_id':'p','revision':4})
    assert [c['start'] for c in undone['document']['clips']]==[0,1,2]
    before=ed.get(pid)
    for kw in ({'delta':7.},{'delta':-1.},{'track':'audio'},{'delta':float('nan')}):
        with pytest.raises(EditorError):operation(ed,pid,'move',**kw)
        assert ed.get(pid)==before
    operation(ed,pid,'lock',value=True)
    before=ed.get(pid)
    with pytest.raises(EditorError,match='kilitli'):operation(ed,pid,'move',delta=1.)
    assert ed.get(pid)==before
    operation(ed,pid,'lock',value=False)
    operation(ed,pid,'visibility',value=False)
    assert all(not c['visible'] for c in ed.get(pid)['document']['clips'])
    operation(ed,pid,'duplicate',delta=0.)
    assert len(ed.get(pid)['document']['clips'])==6
    operation(ed,pid,'delete')
    assert not ed.get(pid)['document']['clips']


@pytest.mark.parametrize('kind',['linear','ease_in','ease_out','ease_in_out','hold','bezier'])
def test_split_curve_domain_and_source_are_continuous(advanced,kind):
    ed,pid,view,digest=advanced
    saved=change(ed,pid,lambda d:d['clips'].append({'id':'a'*32,'kind':'text','track':'layers','start':0.,'end':6.,'text':'Curve','fade_in':2.,'fade_out':2.,'keyframes':[{'property':'x','time':0.,'value':-100.},{'property':'x','time':6.,'value':100.,'interpolation':kind,'bezier':[.1,.8,.7,.9]}]}))
    original=saved['document']['clips'][0]
    operation(ed,pid,'split',time=1.)
    clips=ed.get(pid)['document']['clips'];left,right=clips
    assert right['animation_offset']==1 and right['source_start']==1
    for t in [0.,.1,.5,.999,1.,1.001,3.,5.9]:
        c=left if t<1 else right
        assert value_at(c,'x',t-c['start']+c['animation_offset'])==pytest.approx(value_at(original,'x',t),abs=1e-6)
        length=c['animation_duration'];local=t-c['start']+c['animation_offset']
        assert min(1,local/c['fade_in'],(length-local)/c['fade_out'])==pytest.approx(min(1,t/2,(6-t)/2))
    # A second split retains the original clock rather than re-fitting an ease.
    state=ed.get(pid)
    operate(ed,pid,{'plan_id':'p','revision':state['revision'],'ids':[right['id']],'action':'split','time':4.})
    assert sorted(c['animation_offset'] for c in ed.get(pid)['document']['clips'])==[0,1,4]


@pytest.mark.parametrize('handles',[[.8,0.,.2,1.],[-.1,0.,.5,1.],[.1,2.,.5,1.],[0.,0.,1.]])
def test_invalid_bezier_is_rejected(handles):
    with pytest.raises(ValueError):Document.model_validate({'clips':[{'id':'a'*32,'kind':'text','track':'layers','start':0.,'end':2.,'text':'x','keyframes':[{'property':'opacity','time':0.,'value':1.,'interpolation':'bezier','bezier':handles}]}]})


def test_bezier_ffmpeg_matches_python_samples(tmp_path):
    import shutil
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:pytest.skip('FFmpeg yok')
    edit={'keyframes':[{'property':'volume','time':0.,'value':0.},{'property':'volume','time':1.,'value':1.,'interpolation':'bezier','bezier':[.05,.8,.6,.9]}]}
    # FFmpeg evaluates the actual generated expression, not an implementation mirror.
    for t in [0.,.1,.5,.9,1.]:
        expr=expression(edit,'volume',str(t));out=tmp_path/f'{t}.f32'
        graph=tmp_path/'curve.txt';graph.write_text(f"[0:a]aeval=exprs='{expr}':c=same[a]")
        subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=mono','-filter_complex_script',str(graph),'-map','[a]','-t','0.01','-f','f32le',str(out)],check=True,capture_output=True)
        import struct
        samples=struct.unpack('<'+'f'*(out.stat().st_size//4),out.read_bytes())
        assert samples[0]==pytest.approx(value_at(edit,'volume',t),abs=2e-6)


def test_real_proxy_api_cache_audio_and_interval_invalidation(tmp_path):
    import time
    from app.main import create_app
    from fastapi.testclient import TestClient
    from test_manual_first import install_manual_example
    app=create_app(tmp_path)
    with TestClient(app,headers={'X-AI-Video-Studio':'projects'}) as client:
        st=install_manual_example(app);pid=st['pid'];url=f'/api/projects/{pid}/editor'
        state=client.get(url+'/advanced').json()
        state['document']['clips']=[{'id':'a'*32,'kind':'text','track':'layers','start':0.,'end':3.,'text':'Proxy Bezier','keyframes':[{'property':'opacity','time':0.,'value':0.},{'property':'opacity','time':3.,'value':1.,'interpolation':'bezier','bezier':[.1,.7,.6,.9]}]}]
        saved=client.put(url+'/advanced',json=state);assert saved.status_code==200,saved.text
        start=time.monotonic()
        result=client.post(url+'/advanced/program-proxy',json={'time':0.,'quality':'low'});assert result.status_code==200,result.text
        while result.json()['status']!='ready' and time.monotonic()-start<30:
            time.sleep(.1);result=client.post(url+'/advanced/program-proxy',json={'time':0.,'quality':'low'});assert result.status_code==200,result.text
        meta=result.json();assert meta['status']=='ready',meta
        response=client.get(meta['url']);assert response.status_code==200
        output=tmp_path/'preview.mp4';output.write_bytes(response.content)
        data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
        video=next(s for s in data['streams'] if s['codec_type']=='video');audio=next(s for s in data['streams'] if s['codec_type']=='audio')
        assert video['width']==320 and video['height']==180 and video['r_frame_rate']=='30/1'
        assert audio['sample_rate']=='48000' and float(data['format']['duration'])==pytest.approx(4.,abs=.04)
        assert client.post(url+'/advanced/program-proxy',json={'time':1.,'quality':'low'}).json()['key']==meta['key']
        # Identical active content with a new revision keeps the local identity.
        state=client.get(url+'/advanced').json();state['document']['markers'].append({'id':'b'*32,'time':3.,'name':'Not'})
        assert client.put(url+'/advanced',json=state).status_code==200
        assert client.post(url+'/advanced/program-proxy',json={'time':1.,'quality':'low'}).json()['key']==meta['key']
        state=client.get(url+'/advanced').json();state['document']['clips'][0]['text']='Changed'
        assert client.put(url+'/advanced',json=state).status_code==200
        changed=client.post(url+'/advanced/program-proxy',json={'time':1.,'quality':'low'});assert changed.status_code==200,changed.text
        assert changed.json()['key']!=meta['key']


def test_motion_objects_are_saved_reopened_and_rasterized(advanced,tmp_path):
    from app.editor.motion_objects import scene_for
    from app.motion.templates import build
    from app.motion.raster import draw_frame
    from app.channels import DEFAULT_STYLE
    from PIL import Image
    ed,pid,view,digest=advanced
    state=change(ed,pid,lambda d:d['clips'].append({'id':'c'*32,'kind':'motion','track':'infographics','start':0.,'end':2.,'motion':{'template':'stat','data':{'value':'40 km','label':'Rota'}}}))
    objects=scene_for(ed,pid,'c'*32);assert objects['source_type']=='editable_naman'
    index=next(e['index'] for e in objects['elements'] if e['type']=='counter')
    state=change(ed,pid,lambda d:d['clips'][0].update(motion_elements=[{'index':index,'visible':False}]))
    clip=AdvancedEditor(ed.editor).get(pid)['document']['clips'][0]
    scene=build(clip['motion'],DEFAULT_STYLE,2.,0.)
    before=draw_frame(scene,1.,Image.new('RGB',(1920,1080),scene['background']),{})
    scene['_editor_elements']=clip['motion_elements']
    after=draw_frame(scene,1.,Image.new('RGB',(1920,1080),scene['background']),{})
    assert before.tobytes()!=after.tobytes()
    with pytest.raises(EditorError):change(ed,pid,lambda d:d['clips'][0].update(motion_elements=[{'index':999}]))
    # A flat archive source never acquires guessed editable labels.
    state=change(ed,pid,lambda d:d['clips'].append({'id':'d'*32,'kind':'media','track':'layers','start':0.,'end':2.,'media':{'provider':'local','media_id':'m','sha256':digest}}))
    with pytest.raises(EditorError,match='düz MP4'):scene_for(ed,pid,'d'*32)


def test_local_quality_no_network_persistence_and_cache(tmp_path,monkeypatch):
    from app.main import create_app
    from fastapi.testclient import TestClient
    from test_manual_first import install_manual_example
    from app.editor.reviews import Reviews
    with TestClient(create_app(tmp_path),headers={'X-AI-Video-Studio':'projects'}) as client:
        st=install_manual_example(client.app);pid=st['pid'];editor=client.app.state.editor
        monkeypatch.setattr(editor,'video_review',lambda *a,**kw:pytest.fail('Yerel denetim harici servis çağırdı'))
        response=client.post(f'/api/projects/{pid}/editor/quality/local');assert response.status_code==200,response.text
        report=response.json();assert report['external_calls']==0 and report['analysis_scope']=='local_metadata'
        again=client.post(f'/api/projects/{pid}/editor/quality/local').json();assert again['cached'] and again['source_sha256']==report['source_sha256']
        assert any(r['render_version_id']==report['render_version_id'] for r in Reviews(editor).get(pid)['reports'])


def test_comprehensive_permissions_cache_partial_and_cancel(tmp_path,monkeypatch):
    from app.main import create_app
    from fastapi.testclient import TestClient
    from test_manual_first import install_manual_example
    from app.editor.comprehensive import start,status
    from types import SimpleNamespace
    from threading import Event
    import time
    with TestClient(create_app(tmp_path)) as client:
        st=install_manual_example(client.app);editor=client.app.state.editor;pid=st['pid']
        path=tmp_path/'fake-finished.mp4';path.write_bytes(b'synthetic-scope-hash')
        editor.rendering=SimpleNamespace(view=lambda _: {'active':{'id':'video1','status':'completed','metadata':{'duration':40.}}},export=lambda *a:path)
        editor.settings=SimpleNamespace(ai_visual_check=lambda:True,gemini_config=lambda:{'model':'synthetic-mock-model'})
        entered=Event();release=Event();calls=[]
        def analyze(*a,**kw):
            calls.append(kw);entered.set();assert release.wait(5)
            return {'summary':'Mock: gerçek video görülmedi','sample_timecodes':kw['sample_times'],'issues':[{'timecode':kw['sample_times'][0],'category':'test','message':'Sentetik','severity':'info'}]}
        monkeypatch.setattr(editor,'video_review',analyze)
        request={'confirmed':True,'data_sharing_confirmed':True,'cost_confirmed':True,'start':2.,'end':38.,'frames':24}
        for key in ['confirmed','data_sharing_confirmed','cost_confirmed']:
            with pytest.raises(EditorError):start(editor,pid,{**request,key:False})
        assert not calls
        report=start(editor,pid,request);assert entered.wait(3)
        status(editor,pid,report['review_id'],cancel=True);release.set()
        for _ in range(100):
            report=status(editor,pid,report['review_id'])
            if report['status']=='cancelled':break
            time.sleep(.02)
        assert report['status']=='cancelled' and len(calls)==1 and len(report['sample_timecodes'])==8
        # Retry keeps cached batch evidence via the existing video review cache;
        # mocked provider below verifies aggregate persistence and completed reuse.
        monkeypatch.setattr(editor,'video_review',lambda *a,**kw:{'summary':'Mock','sample_timecodes':kw['sample_times'],'issues':[]})
        report=start(editor,pid,{**request,'frames':8})
        for _ in range(100):
            report=status(editor,pid,report['review_id'])
            if report['status']=='completed':break
            time.sleep(.02)
        assert report['status']=='completed'
        cached=start(editor,pid,{**request,'frames':8});assert cached['cached'] and cached['sample_timecodes']==report['sample_timecodes']
