"""Local Part 9: real files/SQLite/FFmpeg plus focused failure-path tests. No APIs."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
from threading import Event
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.database import initialize_database
from app.production import narration_units,visual_blocks
from app.stock.models import make_slots
from app.rendering.models import RenderError,options
from app.rendering import timeline,ass,tools,files,probe
from app.rendering.engine import FFmpegRenderProvider
from app.rendering.runner import ProcessRunner
from test_subtitles import seed,HEADERS,no_network,wav
from test_production import scene


class NativeRenderClient(TestClient):
    """Existing native-engine regressions explicitly select the alternative.

    Part 9.8 default behavior is covered independently with ordinary TestClient.
    """
    def request(self,method,url,**kwargs):
        if str(url).endswith('/render'):
            kwargs['params']={'montage_engine':'native',**dict(kwargs.get('params') or {})}
        if method.upper()=='POST' and str(url).endswith('/render/jobs'):
            kwargs['json']={'montage_engine':'native',**(kwargs.get('json') or {})}
        return super().request(method,url,**kwargs)


def contract(duration=3.14):
    h={'ready':True,'contract_version':1,'source_script_version_id':'s','scene_plan_id':'p','audio_duration':duration,
       'scenes':[{'scene_id':'a','start':0,'end':1.5},{'scene_id':'b','start':1.5,'end':duration}],
       'subtitles':[{'index':1,'start':0,'end':duration,'text':'Grüße ş ğ ß ¿é!'}],
       'stock_slots':[{'slot_id':'1','scene_id':'a','order':1,'start':0,'end':1.5,'duration':1.5,'status':'complete','selected_media_local_identity':{'media_type':'video'}},
                      {'slot_id':'2','scene_id':'b','order':1,'start':1.5,'end':duration,'duration':duration-1.5,'status':'complete','selected_media_local_identity':{'media_type':'image'}}]}
    p={'source_script_version_id':'s','plan_id':'p','scenes':[{'scene_id':'a','transition':'crossfade','motion':'none','overlay_text':'Merhaba şü'}, {'scene_id':'b','transition':'none','motion':'slow_zoom'}]}
    return h,p


def synthetic(folder,name,args):
    exe=shutil.which('ffmpeg')
    if not exe:pytest.skip('Optional FFmpeg absent: real rendering cannot be verified')
    path=folder/name
    subprocess.run([exe,'-v','error','-y',*args,str(path)],shell=False,capture_output=True,check=True)
    return path


def install_ready(app,seconds=3.14):
    st=seed(app,text='Ein kurzer Anfang. Eine genaue Erklärung. Ein ruhiger Abschluss.',seconds=seconds);pid=st['pid']
    units=narration_units(st['source']);ids=[u['unit_id'] for u in units]
    blocks=visual_blocks({'scenes':[scene(ids[:1]),scene(ids[1:])]},st['source'],'de',135,units=units)
    plan=app.state.production.save_generated(pid,st['sid'],'de',blocks)
    p=app.state.production.handoff(pid);root=app.state.projects._path(pid)
    clip=synthetic(root/'stock',uuid4().hex+'.mp4',['-f','lavfi','-i','color=c=blue:s=320x240:d=0.4','-f','lavfi','-i','sine=frequency=1000:duration=0.4','-c:v','libx264','-c:a','aac','-shortest'])
    image=synthetic(root/'stock',uuid4().hex+'.png',['-f','lavfi','-i','color=c=green:s=240x320','-frames:v','1'])
    slots=[]
    for i,s in enumerate(p['scenes']):
        for slot in make_slots(s):
            path=clip if i==0 else image
            m={'provider':'pixabay','media_id':str(i+1),'media_type':'video' if i==0 else 'image','local_path':'stock/'+path.name,'file_size':path.stat().st_size,'duration':.4 if i==0 else None}
            slot.update(selected_media=m,locked=True,status='complete');slots.append(slot)
    state={'project_id':pid,'plan_id':plan['plan_id'],'source_version_id':st['sid'],'slots':slots,'revision':1}
    with closing(app.state.projects._connection()) as c,c:
        c.execute('INSERT INTO stock_plans VALUES (?,?,?,?,?)',(pid,plan['plan_id'],st['sid'],json.dumps(state),st['project']['created_at']))
    app.state.subtitles.create(pid,{'regenerate_confirmed':False})
    for owner,attribute in [(app.state.narration,'factory'),(app.state.stock,'factory'),(app.state.scripts,'provider_factory')]:setattr(owner,attribute,no_network)
    app.state.narration.downloader.download=no_network;app.state.stock.downloader.download=no_network
    st['root']=root;st['originals']={str(f.relative_to(root)):f.read_bytes() for d in ('stock','voice','subtitles','scenes','script') for f in (root/d).rglob('*') if f.is_file()}
    return st


@pytest.fixture
def ready(tmp_path):
    storage=tmp_path/'data (şü)'
    with NativeRenderClient(create_app(storage),headers=HEADERS) as client:
        st=install_ready(client.app);st.update(client=client,storage=storage);yield st


def url(st):return f'/api/projects/{st["pid"]}/render'
def await_job(st):
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        state=st['client'].get(url(st)).json()
        if state['job']['status'] not in ('queued','preparing','rendering','validating'):return state
        time.sleep(.03)
    raise AssertionError('Render did not finish')


def test_master_timeline_readonly_exact():
    h,p=contract();before=deepcopy(h);t=timeline.build(h,p)
    assert t['duration']==3.14 and t['slots'][0]['start']==0 and t['slots'][-1]['end']==3.14
    assert sum(s['frames'] for s in t['slots'])==round(3.14*30) and h==before


@pytest.mark.parametrize('change',['gap','overlap','negative','empty','outorder','duplicate','source','plan','unready','bad_duration','bad_slot_duration','missing','scene_boundary'])
def test_invalid_contract_blocked(change):
    h,p=contract();s=h['stock_slots']
    if change=='gap':s[1]['start']+=.1
    elif change=='overlap':s[1]['start']-=.1
    elif change=='negative':s[0]['start']=-1
    elif change=='empty':h['stock_slots']=[]
    elif change=='outorder':s.reverse()
    elif change=='duplicate':s[1]['slot_id']=s[0]['slot_id']
    elif change=='source':p['source_script_version_id']='other'
    elif change=='plan':p['plan_id']='other'
    elif change=='unready':h['ready']=False
    elif change=='bad_duration':h['audio_duration']=float('nan')
    elif change=='bad_slot_duration':s[1]['duration']=9
    elif change=='missing':s[1]['status']='pending'
    elif change=='scene_boundary':h['scenes'][0]['end']=.5
    with pytest.raises(RenderError):timeline.build(h,p)


def test_tiny_float_clamped():
    h,p=contract();h['stock_slots'][1]['start']+=.0001;h['stock_slots'][1]['duration']-=.0001
    t=timeline.build(h,p);assert t['slots'][1]['start']==t['slots'][0]['end']


@pytest.mark.parametrize('payload',[{'encoder':'else'},{'executable':'cmd.exe'},{'music_volume':float('inf')},{'music_volume':2},{'subtitle_burned':'false'},{'music_fade_in':-1}])
def test_invalid_settings(payload):
    with pytest.raises(RenderError):options(payload)


def test_defaults():
    o=options({});assert o['encoder']=='auto' and o['subtitle_burned'] and not o['music_enabled']


@pytest.mark.parametrize('requested,encoders,expected',[('auto',['h264_nvenc','libx264'],'h264_nvenc'),('auto',['libx264'],'libx264'),('cpu',['h264_nvenc','libx264'],'libx264'),('nvenc',['h264_nvenc'],'h264_nvenc')])
def test_encoder_choice(requested,encoders,expected):assert tools.select_encoder(requested,{'encoders':encoders})==expected


@pytest.mark.parametrize('mode,encoders',[('cpu',[]),('nvenc',['libx264']),('auto',[])])
def test_encoder_unavailable(mode,encoders):
    with pytest.raises(RenderError,match='encoder|Encoder|NVENC'):tools.select_encoder(mode,{'encoders':encoders})


@pytest.mark.parametrize('mode,category,retry',[('auto','nvenc_failed',True),('nvenc','nvenc_failed',False),('auto','render_failed',False),('auto','input_invalid',False),('cpu','render_failed',False)])
def test_retry_only_nvenc_init(mode,category,retry,monkeypatch):
    e=FFmpegRenderProvider({'encoders':['libx264','h264_nvenc']},None);calls=[]
    def attempt(plan,encoder):
        calls.append(encoder)
        if len(calls)==1:raise RenderError(category,'Güvenli hata')
        return {'ok':True}
    monkeypatch.setattr(e,'attempt',attempt)
    if retry:assert e.render({'options':{'encoder':mode}})=={'ok':True} and calls==['h264_nvenc','libx264']
    else:
        with pytest.raises(RenderError):e.render({'options':{'encoder':mode}})
        assert len(calls)==1


def test_retry_only_once(monkeypatch):
    e=FFmpegRenderProvider({'encoders':['libx264','h264_nvenc']},None);calls=[]
    def fail(p,enc):calls.append(enc);raise RenderError('nvenc_failed','Güvenli hata')
    monkeypatch.setattr(e,'attempt',fail)
    with pytest.raises(RenderError):e.render({'options':{'encoder':'auto'}})
    assert calls==['h264_nvenc','libx264']


@pytest.mark.parametrize('text,expected',[('Cannot load libcuda.so.1',True),('No capable devices found',True),('Error opening input file',False),('Invalid argument',False)])
def test_nvenc_category(text,expected):assert tools.nvenc_initialization_failure(text)==expected


@pytest.mark.parametrize('burn',[True,False])
def test_ass_timing_unicode_escape(burn):
    h,p=contract(6);h['subtitles'][0]['text']='ä ö ü ß á ñ ¿ é ç ş ğ ı İ {\\pos(1,2)}\nSecond line'
    scenes=[{'start':1,'end':6,'overlay_text':'Wörter ä ş'}]
    text,warnings,lines=ass.create(h['subtitles'],scenes,6,subtitles=burn)
    assert '0:00:01.00,0:00:04.00,Overlay' in text and 'Wörter ä ş' in text
    assert ('0:00:00.00,0:00:06.00,Subtitle' in text)==burn
    assert '{\\pos(1,2)}' not in text and not warnings


def test_invalid_overlay_skipped():
    text,warnings,_=ass.create([], [{'start':0,'end':4,'overlay_text':'unsafe\x00'}],4,subtitles=False)
    assert warnings and 'unsafe' not in text


def test_discovery_missing(monkeypatch,tmp_path):
    monkeypatch.setattr(tools.shutil,'which',lambda _:None)
    result=tools.discover(root=tmp_path);assert not result['found'] and result['ffmpeg'] is None


def test_real_discovery():
    if not shutil.which('ffmpeg'):pytest.skip('Optional FFmpeg absent')
    result=tools.discover();assert result['found'] and 'libx264' in result['encoders'] and result['ffprobe']


@pytest.mark.parametrize('value',['../other.mp4','/tmp/video.mp4','renders/../video-v1.mp4','renders/video-v0.mp4','https://evil/video.mp4'])
def test_video_traversal(ready,value):
    with pytest.raises(RenderError):files.video_path(ready['client'].app.state.projects,ready['pid'],{'output_local_path':value})


def test_temp_cleanup_scoped(ready,tmp_path):
    p=ready['client'].app.state.projects;jid=uuid4().hex;owned=files.job_directory(p,ready['pid'],jid);(owned/'partial').write_bytes(b'test')
    files.cleanup(p,ready['pid'],jid);assert not owned.exists()
    for name,data in ready['originals'].items():assert (ready['root']/name).read_bytes()==data
    files.cleanup(p,ready['pid'],'../stock')


def test_symlink_cleanup_refused(ready,tmp_path):
    jid=uuid4().hex;p=ready['client'].app.state.projects;owned=files.job_directory(p,ready['pid'],jid)
    outside=tmp_path/'keep';outside.write_text('keep');(owned/'link').symlink_to(outside)
    with pytest.raises(RenderError):files.cleanup(p,ready['pid'],jid)
    assert outside.read_text()=='keep'
    (owned/'link').unlink();files.cleanup(p,ready['pid'],jid)


def test_real_render_version_range_restart_and_readonly(ready):
    st=ready;c=st['client'];before=deepcopy(st['originals']);r=c.post(url(st)+'/jobs',json={'encoder':'cpu'});assert r.status_code==202,r.text
    state=await_job(st);assert state['job']['status']=='completed',state
    v=state['active'];m=v['metadata'];assert v['version']==1 and not v['stale'] and m['encoder_used']=='libx264'
    assert abs(m['duration']-3.14)<=.04 and m['width']==1920 and m['height']==1080 and m['video_codec']=='h264' and m['audio_codec']=='aac'
    path=st['root']/m['output_local_path'];assert path.exists() and not list((st['root']/'renders').glob('.job-*'))
    route=url(st)+f'/versions/{v["id"]}/video';response=c.get(route,headers={'Range':'bytes=0-1023'});assert response.status_code==206 and len(response.content)==1024
    assert c.get(route+'?download=true').headers['content-disposition'].startswith('attachment')
    h=c.get(url(st)+'/handoff').json();assert h['ready'] and h['duration']==m['duration']
    assert 'https://' not in json.dumps(state) and '/workspace/' not in json.dumps(state)
    for name,data in before.items():assert (st['root']/name).read_bytes()==data
    with NativeRenderClient(create_app(st['storage']),headers=HEADERS) as other:
        assert other.get(url(st)).json()['active']['id']==v['id']
        assert other.get(route).status_code==200
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu','subtitle_burned':False}).status_code==202
    state=await_job(st);assert state['job']['status']=='completed' and state['active']['version']==2
    assert path.exists() and c.post(url(st)+f'/versions/{v["id"]}/activate').status_code==200
    assert c.get(url(st)).json()['active']['id']==v['id']
    # Failed attempt leaves the older active video untouched.
    def failed(*a,**kw):raise RenderError('render_failed','Yerel test hatası')
    c.app.state.rendering.factory=failed
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu'}).status_code==202
    state=await_job(st);assert state['job']['status']=='error' and state['active']['id']==v['id'] and path.exists()
    # Changed active subtitles make the output stale without re-render or removal.
    active=c.app.state.subtitles.view(st['pid'])['active'];cues=[{k:q[k] for k in ('start','end','text')} for q in active['cues']];cues[0]['text']='Geänderte Untertitel.'
    c.app.state.subtitles.edit(st['pid'],active['id'],{'cues':cues})
    state=c.get(url(st)).json();assert state['active']['stale'] and path.exists() and not c.get(url(st)+'/handoff').json()['ready']
    assert c.post(url(st)+f'/versions/{v["id"]}/activate').status_code==409


def test_duplicate_cancel_and_delete_protection(ready):
    st=ready;entered=Event()
    class Wait:
        def __init__(self,tool,runner,*a):self.runner=runner
        def render(self,plan):
            entered.set();self.runner.event.wait(20);raise RenderError('render_cancelled','Render iptal edildi.')
    st['client'].app.state.rendering.factory=Wait
    r=st['client'].post(url(st)+'/jobs',json={'encoder':'cpu'});assert r.status_code==202 and entered.wait(2)
    assert st['client'].post(url(st)+'/jobs',json={'encoder':'cpu'}).status_code==409
    assert st['client'].request('DELETE',f'/api/projects/{st["pid"]}',json={'confirm':True}).status_code==409
    assert st['client'].post(url(st)+f'/jobs/{r.json()["job_id"]}/cancel').status_code==200
    state=await_job(st);assert state['job']['status']=='cancelled' and state['active'] is None
    for name,data in st['originals'].items():assert (st['root']/name).read_bytes()==data


def test_recovery_queued_keeps_sources(ready):
    p=ready['client'].app.state.projects;jid,vid=uuid4().hex,uuid4().hex;h=ready['client'].app.state.subtitles.handoff(ready['pid']);stamp=ready['project']['created_at']
    with closing(p._connection()) as c,c:
        c.execute('INSERT INTO render_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(vid,ready['pid'],1,h['source_script_version_id'],h['narration_version_id'],h['subtitle_version_id'],h['scene_plan_id'],'fingerprint',json.dumps({'options':options({})}),'rendering',stamp,stamp))
        c.execute('INSERT INTO render_jobs VALUES (?,?,?,?,?,?,?,?,?)',(jid,ready['pid'],vid,'rendering',json.dumps({'percent':34,'encoder_used':'libx264','elapsed_seconds':1}),'','',stamp,stamp))
    tmp=files.job_directory(p,ready['pid'],jid);(tmp/'partial.mp4').write_bytes(b'partial')
    ready['client'].app.state.rendering.recover();state=ready['client'].get(url(ready)).json()
    assert state['job']['status']=='error' and state['job']['error_category']=='render_interrupted' and not tmp.exists()
    for name,data in ready['originals'].items():assert (ready['root']/name).read_bytes()==data


@pytest.mark.parametrize('bad',[{}, {'executable':'C:/evil.exe'},{'encoder':'cmd.exe'}])
def test_endpoint_unknown_executable_and_no_sources(tmp_path,bad):
    with TestClient(create_app(tmp_path),headers=HEADERS) as c:
        pid=c.app.state.projects.create({'name':'Local','topic':'No keys'})['id'];r=c.post(f'/api/projects/{pid}/render/jobs',json=bad)
        assert r.status_code in (409,422) and c.get('/api/health').status_code==200


def test_music_upload_and_license(ready):
    c=ready['client'];data=wav(1);route=url(ready)+'/music';headers={**HEADERS,'X-Music-Format':'wav'}
    assert c.post(route,content=data,headers=headers).status_code==422
    headers['X-Music-License']='confirmed';r=c.post(route,content=data,headers=headers);assert r.status_code==201,r.text
    assert c.get(url(ready)).json()['music']['license_confirmed']
    assert c.post(route,content=b'not audio',headers=headers).status_code==422
    assert c.post(url(ready)+'/jobs',json={'encoder':'cpu','music_enabled':True}).status_code==202
    state=await_job(ready);assert state['job']['status']=='completed',state
    assert state['active']['metadata']['music_enabled']


def test_missing_ffmpeg_disabled(ready,monkeypatch):
    missing={'found':False,'status':'Bulunamadı','message':'Video oluşturmak için FFmpeg gerekli.','encoders':[]}
    monkeypatch.setattr(ready['client'].app.state.rendering,'_tools',lambda *a:missing)
    state=ready['client'].get(url(ready)).json();assert not state['ready'] and state['source_ready']
    r=ready['client'].post(url(ready)+'/jobs',json={});assert r.status_code==409 and r.json()['category']=='ffmpeg_missing'

@pytest.mark.parametrize('kind,motion,transition,clip_duration,with_probe',[
    ('jpg','none','hard_cut',.3,True),('png','slow_zoom','crossfade',3,True),
    ('webp','pan','fade',1.5,True),('png','ken_burns','none',.2,True),
    ('jpg','none','crossfade',.4,False),
])
def test_real_media_normalization_loop_trim_transitions(tmp_path,kind,motion,transition,clip_duration,with_probe):
    folder=tmp_path/'Türkçe (spaces)';folder.mkdir()
    clip=synthetic(folder,'clip.mp4',['-f','lavfi','-i',f'color=c=blue:s=240x320:d={clip_duration}','-f','lavfi','-i',f'sine=frequency=1000:duration={clip_duration}','-c:v','libx264','-c:a','aac','-shortest'])
    image=synthetic(folder,'image.'+kind,['-f','lavfi','-i','color=c=green:s=480x240','-frames:v','1'])
    voice=folder/'voice.wav';voice.write_bytes(wav(3.14));before=[f.read_bytes() for f in (clip,image,voice)]
    h,p=contract();p['scenes'][0]['transition']=transition;p['scenes'][1]['motion']=motion
    folder_job=folder/'job';folder_job.mkdir();tool=tools.discover();tool['ffprobe']=tool['ffprobe'] if with_probe else None
    runner=ProcessRunner();progress=[]
    engine=FFmpegRenderProvider(tool,runner,lambda *a:progress.append(a))
    result=engine.render({'temporary':folder_job,'timeline':timeline.build(h,p),'handoff':h,'options':options({'encoder':'cpu','subtitle_burned':False}),'media':{'1':{'path':clip,'type':'video','duration':clip_duration},'2':{'path':image,'type':'image'}},'audio':voice,'music':None})
    metadata=probe.validate(shutil.which('ffprobe'),result['path'],3.14)
    assert metadata['width']==1920 and abs(metadata['duration']-3.14)<=.04
    if with_probe:
        output_data=probe.metadata(tool['ffprobe'],result['path'])
        assert int(next(s for s in output_data['streams'] if s['codec_type']=='video')['nb_frames'])==round(3.14*30)
    assert [f.read_bytes() for f in (clip,image,voice)]==before
    assert len(runner.commands)>=3 and max(sum(len(a) for a in cmd) for cmd in runner.commands)<4000
    assert progress and progress[-1][0]=='validating'
    if transition=='crossfade' and with_probe:assert not any('crossfade uygulanamadı' in w for w in result['metadata']['warnings'])
    # Narration is silence, stock audio is a tone. Output must remain silent.
    import array
    raw=subprocess.run([shutil.which('ffmpeg'),'-v','error','-i',str(result['path']),'-map','0:a:0','-f','f32le','-'],shell=False,capture_output=True,check=True).stdout
    samples=array.array('f');samples.frombytes(raw);assert samples and max(abs(s) for s in samples)<1e-5
    # Extract beginning/middle/end pixels: neither blue nor green may become a black gap.
    for when in (.1,1.4,2.8):
        raw=subprocess.run([shutil.which('ffmpeg'),'-v','error','-ss',str(when),'-i',str(result['path']),'-frames:v','1','-vf','scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'],shell=False,capture_output=True,check=True).stdout
        assert len(raw)==3 and max(raw)>70


def test_real_subtitle_on_off_pixels(tmp_path):
    clip=synthetic(tmp_path,'clip.mp4',['-f','lavfi','-i','color=c=blue:s=320x240:d=2','-c:v','libx264'])
    voice=tmp_path/'voice.wav';voice.write_bytes(wav(3.14));h,p=contract()
    p['scenes'][0].update(overlay_text='',transition='hard_cut');p['scenes'][1].update(overlay_text='',motion='none')
    frames=[]
    for burn in (False,True):
        folder=tmp_path/str(burn);folder.mkdir();engine=FFmpegRenderProvider(tools.discover(),ProcessRunner())
        result=engine.render({'temporary':folder,'timeline':timeline.build(h,p),'handoff':h,'options':options({'encoder':'cpu','subtitle_burned':burn}),'media':{key:{'path':clip,'type':'video'} for key in ('1','2')},'audio':voice,'music':None})
        graph='\n'.join(f.read_text() for f in folder.glob('filter-*.txt'))
        assert ('ass=filename=' in graph)==burn
        frames.append(subprocess.run([shutil.which('ffmpeg'),'-v','error','-ss','0.5','-i',str(result['path']),'-frames:v','1','-vf','crop=1920:200:0:880','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout)
    assert frames[0]!=frames[1]


def test_runner_shell_false_progress_safe_error(tmp_path,monkeypatch):
    from io import StringIO
    calls=[]
    class Child:
        stdout=StringIO('out_time_us=1500000\nout_time_ms=1500000\nprogress=end\n');returncode=0
        def wait(self,timeout=None):return 0
        def poll(self):return 0
    def popen(args,**kw):calls.append((args,kw));return Child()
    monkeypatch.setattr('app.rendering.runner.subprocess.Popen',popen)
    progress=[];runner=ProcessRunner();assert runner.run(['trusted-ffmpeg','path (ş).mp4'],tmp_path,progress.append)==1.5
    assert calls[0][1]['shell'] is False and calls[0][0][1]=='path (ş).mp4' and progress==[1.5,1.5]
    assert not (tmp_path/'stderr.tmp').exists()


def test_real_process_cancel_scoped(tmp_path):
    unrelated=subprocess.Popen([shutil.which('ffmpeg'),'-v','error','-re','-f','lavfi','-i','color=d=20:s=16x16','-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    runner=ProcessRunner();from threading import Thread
    result=[]
    def run():
        try:runner.run([shutil.which('ffmpeg'),'-v','error','-re','-f','lavfi','-i','color=d=20:s=16x16','-progress','pipe:1','-nostats','-f','null','-'],tmp_path)
        except RenderError as error:result.append(error.category)
    worker=Thread(target=run);worker.start()
    try:
        deadline=time.monotonic()+5
        while runner.process is None and time.monotonic()<deadline:time.sleep(.01)
        assert runner.process is not None;runner.cancel();worker.join(5)
        assert not worker.is_alive() and result==['render_cancelled'] and unrelated.poll() is None
    finally:unrelated.terminate();unrelated.wait(5)


def test_output_invalid_not_activated(tmp_path):
    path=tmp_path/'bad.mp4';path.write_bytes(b'not an MP4'*100)
    with pytest.raises(RenderError) as e:probe.validate(shutil.which('ffprobe'),path,3)
    assert e.value.category=='output_invalid'


def test_render_route_project_scoped_and_secrets(ready,monkeypatch):
    c=ready['client'];c.app.state.settings.save('openai',{'api_key':'test-local-secret-329871'})
    state=c.get(url(ready)).json();assert 'test-local-secret-329871' not in json.dumps(state)
    pid=c.app.state.projects.create({'name':'Other','topic':'Isolated'})['id']
    r=c.get(f'/api/projects/{pid}/render/versions/{uuid4().hex}/video');assert r.status_code==404
    def unexpected(*a):raise RuntimeError('Authorization: test-local-secret-329871 https://private.invalid?signed=true')
    monkeypatch.setattr(c.app.state.rendering,'view',unexpected)
    r=c.get(url(ready));assert r.status_code==500 and r.json()['category']=='unexpected_backend'
    assert 'secret-329871' not in r.text and 'signed=true' not in r.text and 'RuntimeError' not in r.text


def test_schema9_upgrade_preserves_sources(ready):
    p=ready['client'].app.state.projects
    with closing(p._connection()) as c,c:
        for table in ('render_jobs','render_state','render_music','render_versions'):c.execute('DROP TABLE '+table)
        c.execute("UPDATE app_metadata SET value='9' WHERE key='schema_version'")
    initialize_database(ready['storage'])
    with closing(p._connection()) as c:
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='12'
        assert c.execute('SELECT COUNT(*) FROM narration_versions').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM subtitle_versions').fetchone()[0]>=1
    for name,data in ready['originals'].items():assert (ready['root']/name).read_bytes()==data


def test_source_mismatch_and_stale_subtitles(ready,monkeypatch):
    service=ready['client'].app.state.rendering;p=service.production.handoff(ready['pid']);p['plan_id']='other'
    monkeypatch.setattr(service.production,'handoff',lambda pid:p)
    r=ready['client'].post(url(ready)+'/jobs',json={});assert r.status_code==409 and r.json()['message']== 'Video kaynakları birbiriyle eşleşmiyor. Güncel seslendirme, altyazı ve medya planını kontrol edin.'


def test_corrupt_local_stock_preserves_active_sources(ready):
    h=ready['client'].app.state.subtitles.handoff(ready['pid']);path=ready['root']/h['stock_slots'][0]['selected_media_local_identity']['local_path'];size=path.stat().st_size;path.write_bytes(b'x'*size)
    # Identity still resolves, but actual decoder validation must reject it safely.
    r=ready['client'].post(url(ready)+'/jobs',json={'encoder':'cpu'});assert r.status_code==202
    state=await_job(ready);assert state['job']['status']=='error' and state['job']['error_category']=='input_invalid' and state['active'] is None
    assert path.read_bytes()==b'x'*size

@pytest.mark.parametrize('text',[r'{\pos(0,0)}INJECTION',r'{\an7\move(0,0,0,0)}INJECTION',r'{\p1}m 0 0 l 1920 0 1920 1080 0 1080{\p0}',r'Backslash \N ä ö ş İ'])
def test_real_ass_control_text_cannot_move_or_draw(tmp_path,text):
    # Inspect actual libass pixels, not just the escaped string.
    content,_,_=ass.create([{'start':0,'end':1,'text':text}],[],1)
    path=tmp_path/'safe.ass';path.write_text(content,encoding='utf-8')
    raw=subprocess.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=blue:s=1920x1080:d=1','-vf','ass=filename=safe.ass','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'],cwd=tmp_path,capture_output=True,check=True,shell=False).stdout
    rows=[]
    for y in range(1080):
        row=raw[y*1920*3:(y+1)*1920*3]
        if any(row[i]>180 and row[i+1]>180 and row[i+2]>180 for i in range(0,len(row),3)):rows.append(y)
    assert rows and min(rows)>800  # all white text must stay in the intended subtitle area


def test_real_auto_encoder_fallback_if_needed(ready):
    r=ready['client'].post(url(ready)+'/jobs',json={'encoder':'auto'});assert r.status_code==202
    state=await_job(ready);assert state['job']['status']=='completed',state
    assert len(state['versions'])==1 and state['versions'][0]['version']==1
    assert state['active']['metadata']['encoder_used'] in ('h264_nvenc','libx264')
    # Availability on this particular host is recorded, never interpreted as RTX success.
    if state['active']['metadata']['encoder_used']=='libx264' and 'h264_nvenc' in state['ffmpeg']['encoders']:
        assert any('NVENC başlatılamadı' in w for w in state['active']['metadata']['warnings'])


def test_source_change_during_job_preserves_previous_video(ready):
    st=ready;c=st['client'];assert c.post(url(st)+'/jobs',json={'encoder':'cpu'}).status_code==202
    previous=await_job(st)['active'];oldpath=st['root']/previous['metadata']['output_local_path'];gate=Event();entered=Event()
    class Changed:
        def __init__(self,tool,runner,progress,log):self.engine=FFmpegRenderProvider(tool,runner,progress,log)
        def render(self,plan):
            result=self.engine.render(plan);entered.set();gate.wait(5);return result
    c.app.state.rendering.factory=Changed
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu'}).status_code==202 and entered.wait(15)
    active=c.app.state.subtitles.view(st['pid'])['active'];cues=[{k:q[k] for k in ('start','end','text')} for q in active['cues']];cues[0]['text']='Neue Anzeige.'
    c.app.state.subtitles.edit(st['pid'],active['id'],{'cues':cues});gate.set()
    state=await_job(st);assert state['job']['status']=='error' and state['job']['error_category']=='source_stale' and state['active']['id']==previous['id'] and oldpath.exists()
    assert not (st['root']/'renders'/'video-v2.mp4').exists()

@pytest.mark.parametrize('change',['scene_gap','scene_overlap','scene_end','scene_nan','order_string','order_zero'])
def test_invalid_scene_clock_and_slot_order(change):
    h,p=contract()
    if change=='scene_gap':h['scenes'][1]['start']+=.1
    elif change=='scene_overlap':h['scenes'][1]['start']-=.1
    elif change=='scene_end':h['scenes'][1]['end']-=.1
    elif change=='scene_nan':h['scenes'][0]['end']=float('nan')
    elif change=='order_string':h['stock_slots'][0]['order']='1'
    elif change=='order_zero':h['stock_slots'][0]['order']=0
    with pytest.raises(RenderError):timeline.build(h,p)
