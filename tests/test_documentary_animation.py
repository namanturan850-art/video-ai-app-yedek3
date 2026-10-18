"""Bounded declarative scenes and the real manual approval/render pipeline."""
from copy import deepcopy
import io
import json
import subprocess

import pytest
from PIL import Image,ImageChops
from app.animation.schema import validate
from app.animation.examples import examples
from app.animation.scene import at
from app.channels import DEFAULT_STYLE
from app.motion.templates import build
from app.motion.raster import draw_frame
from app.motion.clips import render_clip
from app.editor.advanced import AdvancedEditor
from test_simple_workflow import workflow
from test_plan_intervals import selected


@pytest.mark.parametrize('name',['science','chart','diagram'])
def test_examples_have_deterministic_moving_composed_objects_and_notice(name):
    data=validate(examples()[name],'',1.)
    scene=build({'template':'documentary','data':data},DEFAULT_STYLE,1.,0,'tr')
    def frame(t):return draw_frame(scene,t,Image.new('RGBA',(1920,1080),(0,0,0,0)),{})
    assert frame(.5).tobytes()==frame(.5).tobytes()
    assert frame(.2).tobytes()!=frame(.7).tobytes()
    assert scene['fps']==30 and scene['width']==1920 and scene['alpha'] and scene['sfx']==[]
    assert scene['elements'][-1]['props']['required_notice'] and 'DEMO' in scene['elements'][-1]['props']['text']


@pytest.mark.parametrize('change',[
    lambda d:d.update(code='import os'),
    lambda d:d['objects'][0].update(kind='eval'),
    lambda d:d['objects'][0].update(data={'url':'https://example.com'}),
    lambda d:d['objects'].append(deepcopy(d['objects'][0])),
    lambda d:d['objects'][0].update(x=float('inf')),
    lambda d:d['objects'][0].update(keyframes=[{'time':2.,'property':'x','value':0.}]),
    lambda d:d['objects'][0].update(keyframes=[{'time':0.,'property':'scale','value':100.}]),
    lambda d:d['camera'].update(keyframes=[{'time':0.,'property':'rotation','value':90.}]),
])
def test_unsafe_or_outside_features_are_rejected(change):
    data=examples()['diagram'];change(data)
    with pytest.raises(ValueError):validate(data,'',1.)


def test_facts_are_verified_against_narration_not_ai_claims():
    data={'schema':'naman.animation.v1','basis':'narration','objects':[{'id':'count','kind':'counter','data':{'value':40.,'unit':'kilómetros'}}]}
    assert validate(data,'Recorremos 40 kilómetros en Roma.',1.)
    data['objects'][0]['data']['value']=41.
    with pytest.raises(ValueError,match='doğrulanamadı'):validate(data,'Recorremos 40 kilómetros en Roma.',1.)
    data['basis']='schematic'
    with pytest.raises(ValueError):validate(data,'Recorremos 40 kilómetros en Roma.',1.)
    data['basis']='demo';assert validate(data,'',1.)


def test_easing_and_camera_are_evaluated_from_seconds():
    state={'x':0.,'keyframes':[{'time':0.,'property':'x','value':0.,'easing':'linear'},
                             {'time':1.,'property':'x','value':100.,'easing':'linear'}]}
    assert at(state,.25)['x']==25. and at(state,.75)['x']==75.
    state['keyframes'][1]['easing']='hold';assert at(state,.99)['x']==0. and at(state,1.)['x']==100.


def test_alpha_sample_and_full_render_use_the_same_frame(tmp_path):
    from app.rendering.tools import discover
    data=validate(examples()['science'],'',1.)
    spec={'template':'documentary','data':data}
    full,scene,_=render_clip(tmp_path,spec,DEFAULT_STYLE,1.,0,prefer_openmontage=False)
    sample,_,_=render_clip(tmp_path,spec,DEFAULT_STYLE,1.,0,prefer_openmontage=False,sample_time=.5)
    assert full.suffix==sample.suffix=='.mov'
    def rgba(path,t):
        raw=subprocess.run([discover()['ffmpeg'],'-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-threads','1','-'],capture_output=True,check=True).stdout
        return Image.frombytes('RGBA',(1920,1080),raw)
    a,b=rgba(full,.5),rgba(sample,0)
    assert a.tobytes()==b.tobytes() and a.getpixel((40,40))[3]==0 and a.getchannel('A').getextrema()[1]==255
    assert rgba(full,.2).tobytes()!=rgba(full,.7).tobytes()  # no settled-frame freeze


def setup(workflow,name='science'):
    client,pid=workflow;base=f'/api/projects/{pid}/editor';ed=AdvancedEditor(client.app.state.editor)
    pack=client.get(base+'/manual/package').json();plan=deepcopy(pack['output_template']);scene=pack['narration'][0]
    record={'scene_id':scene['scene_id'],'start':scene['start'],'end':min(scene['end'],scene['start']+1.),'object_id':'animation-'+name,
            'data':examples()[name]}
    plan['animasyon_sahneleri']=[record]
    return client,pid,base,ed,pack,plan,record


@pytest.mark.parametrize('name',['science','chart','diagram'])
def test_json_validation_draft_preview_selection_approval_real_mp4(workflow,name):
    from test_rendering import await_job
    from test_advanced_render import decoded_frame
    client,pid,base,ed,pack,plan,record=setup(workflow,name);before=ed.get(pid);view=ed.editor.view(pid)
    preflight=client.post(base+'/manual/validate',json=plan)
    assert preflight.status_code==200 and preflight.json()['valid'],preflight.text
    response=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)})
    assert response.status_code==201,response.text
    draft=response.json();assert not draft['import_issues'] and len(draft['clips'])==1 and ed.get(pid)==before
    preview=client.get(base+f'/editorial/drafts/{draft["id"]}/preview?time={record["start"]+.5}')
    assert preview.status_code==200,preview.text if preview.status_code!=200 else ''
    picture=Image.open(io.BytesIO(preview.content))
    # The underlying actual blue video remains visible through alpha corners.
    pixel=picture.getpixel((20,20));assert pixel[2]>150 and pixel[0]<30,pixel
    endpoint=base+f'/editorial/drafts/{draft["id"]}/approve'
    assert client.post(endpoint,json={'confirmed':False,'clip_ids':selected(draft)}).status_code==422 and ed.get(pid)==before
    assert client.post(endpoint,json={'confirmed':True,'clip_ids':selected(draft)}).status_code==200
    assert ed.editor.view(pid)['tracks']==view['tracks'] and ed.editor.task_package(pid)['voice']==pack['voice']
    result=client.post(f'/api/projects/{pid}/render/jobs',json={'encoder':'cpu'})
    assert result.status_code==202,result.text
    result=await_job({'client':client,'pid':pid});assert result['job']['status']=='completed',result
    path=client.app.state.rendering.export(pid,result['active']['id'])
    streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))['streams']
    video=next(s for s in streams if s['codec_type']=='video');audio=next(s for s in streams if s['codec_type']=='audio')
    assert (video['width'],video['height'],video['avg_frame_rate'])==(1920,1080,'30/1')
    assert abs(float(video['duration'])-float(audio['duration']))<1/30
    frame=decoded_frame(path,record['start']+.5)
    assert frame.size==(1920,1080) and frame.getpixel((20,20))[2]>150
    assert client.app.state.rendering._inputs(pid,__import__('app.rendering.models',fromlist=['options']).options({'encoder':'cpu'}))['advanced_document']['clips'][0]['motion']['data']['basis']=='demo'


def test_bad_animation_does_not_discard_valid_text_or_valid_animation(workflow):
    client,pid,base,ed,pack,plan,record=setup(workflow);before=ed.get(pid)
    plan['katmanlar']=[{'scene_id':record['scene_id'],'text':'Roma'}]
    bad=deepcopy(record);bad['object_id']='bad';bad['data']['objects'][0]['kind']='javascript'
    plan['animasyon_sahneleri'].append(bad)
    response=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)})
    assert response.status_code==201,response.text
    draft=response.json();assert len(draft['clips'])==2 and len(draft['import_issues'])==1
    issue=draft['import_issues'][0];assert issue['scene_id']==record['scene_id'] and issue['start']==record['start'] and 'kind' in issue['message']
    assert ed.get(pid)==before


@pytest.mark.parametrize('kind,data',[
    ('cloud',{}),('flow',{'points':[{'x':-80.,'y':0.},{'x':80.,'y':0.}]}),
    ('arrow',{'points':[{'x':-80.,'y':0.},{'x':80.,'y':0.}]}),
    ('line',{'points':[{'x':-80.,'y':0.},{'x':80.,'y':0.}]}),('lightning',{}),
    ('bar_chart',{'items':[{'label':'A','value':0.},{'label':'B','value':40.}]}),
    ('line_chart',{'items':[{'label':'A','value':0.},{'label':'B','value':40.}]}),
    ('label',{'text':'Demo'}),('node',{'text':'Demo'}),('counter',{'value':40.}),
    ('wave',{}),('particles',{}),('box',{}),('circle',{}),('isometric_box',{})])
def test_each_supported_component_draws_with_zero_values_and_safe_defaults(kind,data):
    value=validate({'schema':'naman.animation.v1','basis':'demo','objects':[{'id':'one','kind':kind,'data':data}]},'',1.)
    scene=build({'template':'documentary','data':value},DEFAULT_STYLE,1.,0)
    frame=draw_frame(scene,.5,Image.new('RGBA',(1920,1080),(0,0,0,0)),{})
    # Exclude the notice: the actor itself must produce pixels in its region.
    assert frame.crop((0,120,1920,900)).getbbox() is not None


def test_layer_order_keyframes_camera_and_visibility_are_real_pixels():
    data={'schema':'naman.animation.v1','basis':'demo','camera':{'x':100.},'objects':[
        {'id':'back','kind':'box','x':300.,'y':300.,'width':100.,'height':100.,'color':'#0000FF'},
        {'id':'front','kind':'circle','x':200.,'y':300.,'width':60.,'height':60.,'color':'#FF0000','layer':2,'start':.2,'end':.8,
         'keyframes':[{'property':'x','time':0.,'value':200.},{'property':'x','time':1.,'value':400.}]}]}
    scene=build({'template':'documentary','data':validate(data,'',1.)},DEFAULT_STYLE,1.,0)
    def frame(t):return draw_frame(scene,t,Image.new('RGBA',(1920,1080),(0,0,0,0)),{})
    assert frame(.5).getpixel((200,300))[:3]==(255,0,0)
    assert frame(.9).getpixel((200,300))[:3]==(0,0,255)
    assert frame(.1).getpixel((100,300))[3]==0


def test_new_optional_section_does_not_change_old_response_grammar(workflow):
    client,pid,base,ed,pack,plan,record=setup(workflow)
    plan.pop('animasyon_sahneleri');plan['katmanlar']=[{'scene_id':record['scene_id'],'text':'Roma'}]
    result=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)})
    assert result.status_code==201 and len(result.json()['clips'])==1 and not result.json()['import_issues']
    assert 'animation_subtitle_version' not in result.json()
    assert ed.get(pid)['revision']==0


def test_package_has_actual_schema_examples_and_gemini_needs_confirmation(workflow,monkeypatch):
    from types import SimpleNamespace
    client,pid,base,ed,pack,plan,record=setup(workflow);before=ed.get(pid);calls=[]
    def prepare(purpose,prompt,*a,**kw):
        calls.append(prompt);return {'instructions':['Yalnız desteklenen animasyon bileşenlerini kullan; önce taslak ve onay.']}
    monkeypatch.setattr('app.providers.factory.make_script_provider',lambda *a,**kw:SimpleNamespace(complete_json=prepare))
    assert client.post(base+'/manual/package/prepare',json={}).status_code==409 and not calls
    response=client.post(base+'/manual/package/prepare',json={'cost_confirmed':True})
    assert response.status_code==200,response.text
    caps=response.json()['animation_capabilities']
    assert 'animasyon_sahneleri' in response.json()['output_template'] and len(caps['examples'])==3
    assert caps['canvas']=={'width':1920,'height':1080,'fps':30}
    assert caps['record_contract']['data_schema']['additionalProperties'] is False
    assert 'animation_capabilities' in calls[0] and 'animasyon_sahneleri' in calls[0] and ed.get(pid)==before
    assert 'animation_reference_selection' in calls[0] and response.json()['animation_reference_selection']['catalog_count']==300


def test_locked_slot_and_scene_preserve_valid_proposals(workflow):
    from contextlib import closing
    client,pid,base,ed,pack,plan,record=setup(workflow);stock=client.app.state.stock;view=ed.editor.view(pid)
    with closing(ed.projects._connection()) as c,c:
        state=stock._load(c,pid,view['stock_plan_id']);state['slots'][0]['locked']=True;stock._save(c,state)
    before=ed.get(pid);response=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)})
    assert response.status_code==201,response.text
    assert not response.json()['clips'] and len(response.json()['import_issues'])==1 and ed.get(pid)==before


def test_background_media_is_only_real_archive_and_can_be_approved_separately(workflow):
    client,pid,base,ed,pack,plan,record=setup(workflow)
    asset=next(a for a in pack['archive'] if a['media_type']=='image')
    record['background_media']={k:asset[k] for k in ('provider','media_id','sha256')}
    before=ed.get(pid);draft=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)}).json()
    assert len(draft['clips'])==2 and not draft['import_issues'] and ed.get(pid)==before
    layer=next(c for c in draft['clips'] if c['kind']=='motion')
    assert client.post(base+f'/editorial/drafts/{draft["id"]}/approve',json={'confirmed':True,'clip_ids':[layer['id']]}).status_code==200
    assert len(ed.get(pid)['document']['clips'])==1 and ed.get(pid)['document']['clips'][0]['kind']=='motion'
    plan['animasyon_sahneleri'][0]['background_media']['sha256']='0'*64
    failed=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)}).json()
    assert failed['import_issues'] and not failed['clips']


def test_cue_ids_and_changed_subtitles_invalidate_animation_draft(workflow):
    client,pid,base,ed,pack,plan,record=setup(workflow)
    indices=[i for i,c in enumerate(pack['subtitles']['cues']) if record['start']<=c['start']<record['end']]
    record['sentence_indices']=[indices[0]]
    draft=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)}).json()
    assert not draft['import_issues']
    # New subtitle version, same narration clock: old animation cue references
    # must not be approved against different subtitle content.
    subs=client.app.state.subtitles.view(pid)['active'];cues=[{k:c[k] for k in ('start','end','text')} for c in subs['cues']];cues[0]['text']='Altyazı düzeltmesi'
    client.app.state.subtitles.edit(pid,subs['id'],{'cues':cues},preserve_clock=True)
    response=client.post(base+f'/editorial/drafts/{draft["id"]}/approve',json={'confirmed':True,'clip_ids':selected(draft)})
    assert response.status_code==409 and ed.get(pid)['revision']==0
    record['sentence_indices']=[99999]
    bad=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)}).json()
    assert bad['import_issues'] and not bad['clips']


def test_demo_notice_cannot_be_removed_by_motion_object_edits(workflow):
    client,pid,base,ed,pack,plan,record=setup(workflow)
    draft=client.post(base+'/manual/response-draft',json={'text':json.dumps(plan)}).json()
    assert client.post(base+f'/editorial/drafts/{draft["id"]}/approve',json={'confirmed':True,'clip_ids':selected(draft)}).status_code==200
    state=ed.get(pid);clip=state['document']['clips'][0]
    response=client.get(base+'/advanced/motion-elements/'+clip['id'])
    assert response.status_code==200,response.text
    assert all('DEMO' not in a['label'] for a in response.json()['elements'])
    clip['motion_elements']=[{'index':len(record['data']['objects']),'visible':False}]
    result=client.put(base+'/advanced',json=state)
    assert result.status_code==422 and 'gizlenemez' in result.text


def test_short_charts_reach_their_true_values_in_the_last_frame():
    data={'schema':'naman.animation.v1','basis':'demo','objects':[{'id':'bars','kind':'bar_chart','x':960.,'y':500.,'width':900.,'height':300.,'color':'#FF0000',
          'data':{'items':[{'label':str(i),'value':40.} for i in range(8)]}}]}
    scene=build({'template':'documentary','data':validate(data,'',.3)},DEFAULT_STYLE,.3,0)
    frame=draw_frame(scene,8/30,Image.new('RGBA',(1920,1080),(0,0,0,0)),{})
    for i in range(8):
        x=round(960.-450.+900./8*(i+.5))
        assert frame.getpixel((x,360))[:3]==(255,0,0)


def test_render_failure_is_actionable_without_silent_fallback_or_lost_cancellation(tmp_path,monkeypatch):
    from app.editor.compositor import motion_asset
    from app.rendering.models import RenderError
    from app.motion.control import MotionCancelled
    clip={'motion':{'template':'documentary','data':examples()['science']},'start':0.,'end':1.}
    def fail(*a,**k):raise OSError('synthetic encoder problem')
    monkeypatch.setattr('app.motion.clips.render_clip',fail)
    with pytest.raises(RenderError,match='FFmpeg') as error:motion_asset(clip,tmp_path)
    assert error.value.category=='animation_render_failed'
    def cancel(*a,**k):raise MotionCancelled('Durduruldu')
    monkeypatch.setattr('app.motion.clips.render_clip',cancel)
    with pytest.raises(MotionCancelled):motion_asset(clip,tmp_path)


def test_text_rotation_is_rendered_instead_of_ignored():
    data={'schema':'naman.animation.v1','basis':'demo','objects':[{'id':'word','kind':'label','x':700.,'y':500.,'width':800.,'data':{'text':'Documentary'}}]}
    def bounds(angle):
        data['objects'][0]['rotation']=angle
        scene=build({'template':'documentary','data':validate(data,'',1.)},DEFAULT_STYLE,1.,0)
        box=draw_frame(scene,.5,Image.new('RGBA',(1920,1080),(0,0,0,0)),{}).crop((100,200,1800,900)).getbbox()
        return box[2]-box[0],box[3]-box[1]
    w,h=bounds(0.);rw,rh=bounds(90.)
    assert w>h*2 and rh>rw*2
