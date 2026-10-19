"""Real FFmpeg proxy conformance, bounded animation windows and reference selection."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.editor.advanced import AdvancedEditor
from app.editor.proxies import snapshot,build
from app.animation.examples import examples
from app.animation.references import select_techniques
from test_manual_first import install_manual_example


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(path)]))['streams']


def test_300_reference_selection_matches_scenes_without_copying_sources():
    scenes=[{'scene_id':'science','text':'Fırtına bulut ve şimşek.','start':0,'end':4},
            {'scene_id':'data','text':'Nüfus yüzde artış oranı.','start':4,'end':8},
            {'scene_id':'geo','text':'Roma nehir rota harita.','start':8,'end':12}]
    result=select_techniques(scenes)
    assert result==select_techniques(scenes) and result['catalog_count']==300
    assert [next(iter(s['reason'])) for s in result['scenes']]==['Bilimsel/doğa','İnfografik','Coğrafya']
    from app.animation.references import PER_SCENE
    assert all(1<=len(s['references'])<=PER_SCENE for s in result['scenes'])
    encoded=json.dumps(result)
    assert 'https://' not in encoded and 'prompt_sha256' not in encoded
    assert len({s['references'][0]['reference_id'] for s in result['scenes']})>=2


@pytest.mark.parametrize('kind',['cross_dissolve','wipe','dip_black'])
def test_720p_transition_proxy_has_30fps_no_missing_frames_and_matches_program(tmp_path,kind):
    from PIL import Image,ImageChops,ImageStat
    from app.editor.previews import program_frame
    app=create_app(tmp_path)
    with TestClient(app) as client:
        st=install_manual_example(app,seconds=4);pid=st['pid'];ed=app.state.editor;advanced=AdvancedEditor(ed)
        slots=[x for values in ed.view(pid)['tracks'].values() for x in values if x.get('slot_id')]
        a,b=next((a,b) for a,b in zip(slots,slots[1:]) if a['end']==b['start'])
        state=advanced.get(pid);state['document']['transitions']=[{'slot_id':a['slot_id'],'next_slot_id':b['slot_id'],'kind':kind,'duration':.2}]
        advanced.save(pid,state);before=advanced.get(pid)
        key,data,_=snapshot(ed,advanced,pid,b['start']+.1,'high')
        folder=tmp_path/'proxy';folder.mkdir();target=folder/'720.mp4';build(folder,target,data)
        streams=probe(target);v=next(s for s in streams if s['codec_type']=='video');audio=next(s for s in streams if s['codec_type']=='audio')
        assert (v['width'],v['height'],v['r_frame_rate'],int(v['nb_read_frames']))==(1280,720,'30/1',round(data['duration']*30))
        assert audio['sample_rate']=='48000' and abs(float(v['duration'])-float(audio['duration']))<.04
        assert advanced.get(pid)==before
        # Existing scalar compositor is an independent reference for the transition.
        t=b['start']+2/30
        still=Image.open(program_frame(ed,advanced,pid,t)).convert('RGB')
        raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t-data['start']),'-i',str(target),'-vf','scale=640:360','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        actual=Image.frombytes('RGB',(640,360),raw)
        # Avoid burned subtitles; compare the plain source corner.
        delta=ImageStat.Stat(ImageChops.difference(still.crop((5,5,100,90)),actual.crop((5,5,100,90))))
        assert max(delta.mean)<8,delta.mean


def test_720p_multilayer_motion_windows_are_bounded_continuous_and_cached(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app):
        st=install_manual_example(app,seconds=12);pid=st['pid'];ed=app.state.editor;advanced=AdvancedEditor(ed)
        state=advanced.get(pid)
        state['document']['clips']=[{'id':'a'*32,'kind':'motion','track':'infographics','start':0.,'end':12.,'motion':{'template':'documentary','data':examples()['science'],'emphasis':''}}]
        for i in range(4):
            state['document']['clips'].append({'id':str(i+1)*32,'kind':'text','track':'layers','start':0.,'end':12.,'text':'Katman '+str(i),'transform':{'y':i*100.-200.},'keyframes':[{'property':'x','time':0.,'value':-150.},{'property':'x','time':12.,'value':150.}]})
        advanced.save(pid,state);before=advanced.get(pid);folder=tmp_path/'proxies';folder.mkdir()
        keys=[];times=[]
        for t in (0.,4.,8.):
            key,data,_=snapshot(ed,advanced,pid,t,'high');keys.append(key);target=folder/f'{key}.mp4'
            started=time.monotonic();build(folder,target,data);times.append(time.monotonic()-started)
            v=next(s for s in probe(target) if s['codec_type']=='video')
            assert (v['width'],v['height'],v['r_frame_rate'],int(v['nb_read_frames']))==(1280,720,'30/1',120)
            # Every encoded frame has a monotonic 1/30s timestamp, including edges.
            frames=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v','-show_entries','frame=best_effort_timestamp_time','-of','json',str(target)]))['frames']
            stamps=[float(f['best_effort_timestamp_time']) for f in frames]
            assert all(abs(b-a-1/30)<.00001 for a,b in zip(stamps,stamps[1:]))
        # The animation cache holds only 120-frame windows, not a 360-frame scene.
        motion=list((st['root']/'stock/editor-cache').glob('motion-window-*.mov'))
        assert len(motion)==3
        assert all(int(probe(p)[0]['nb_read_frames'])==120 for p in motion)
        from PIL import Image
        from app.motion.templates import build as scene_build
        from app.motion.raster import draw_frame
        from app.channels import DEFAULT_STYLE
        scene=scene_build({'template':'documentary','data':examples()['science']},data.get('kit') or DEFAULT_STYLE,12.,0,'es')
        for t,path in zip((0.,4.,8.),sorted(motion,key=lambda p:p.stat().st_mtime)):
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'])
            scene['_render_size']=[1280,720]
            expected=draw_frame(scene,t,Image.new('RGBA',(1280,720),(0,0,0,0)),{})
            assert raw==expected.tobytes()  # exact alpha and analytical time, not a restarted scene
        assert advanced.get(pid)==before and len(set(keys))==3
        assert snapshot(ed,advanced,pid,4.2,'high')[0]==keys[1]
        print('12s / five layers / 720p preparation seconds:',times)


def test_1080p_proxy_is_real_1080p_30fps(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app):
        st=install_manual_example(app);ed=app.state.editor;pid=st['pid'];advanced=AdvancedEditor(ed)
        _,data,_=snapshot(ed,advanced,pid,0.,'full');folder=tmp_path/'full';folder.mkdir();target=folder/'full.mp4'
        moving=folder/'moving-source.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=1920x1080:r=30:d=4','-c:v','libx264','-preset','ultrafast','-threads','1',str(moving)],check=True)
        for part in data['bases']:part.update(path=moving,type='video')
        build(folder,target,data);v=next(s for s in probe(target) if s['codec_type']=='video')
        assert (v['width'],v['height'],v['r_frame_rate'],int(v['nb_read_frames']))==(1920,1080,'30/1',120)
        def frame(t):return subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(target),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        assert frame(0)!=frame(1)  # actual moving video, not a repeated still


def test_word_highlight_crossing_proxy_edge_keeps_original_subtitle_clock(tmp_path,monkeypatch):
    from app.rendering import ass
    from app.editor.editorial import Editorial
    app=create_app(tmp_path)
    with TestClient(app):
        st=install_manual_example(app,seconds=12);ed=app.state.editor;pid=st['pid'];advanced=AdvancedEditor(ed)
        editorial=Editorial(ed);preferences=editorial.get(pid);preferences['preferences']['word_highlight']=True;editorial.save(pid,preferences)
        original=ed.subtitles.view(pid)['active']['cues']
        _,data,_=snapshot(ed,advanced,pid,4.,'high')
        assert any(q['start']<4<q['end'] for q in data['cues'])
        assert all(q in original for q in data['cues'])  # no cropped duration / restarted word weights
        calls=[];create=ass.create
        def record(cues,scenes,duration,**options):
            result=create(cues,scenes,duration,**options);calls.append((cues,duration,result[0]));return result
        monkeypatch.setattr(ass,'create',record)
        folder=tmp_path/'words';folder.mkdir();target=folder/'words.mp4';build(folder,target,data)
        assert calls[0][0]==data['cues'] and calls[0][1]==12.
        assert '\\bord10' in calls[0][2]
        v=next(s for s in probe(target) if s['codec_type']=='video')
        assert v['r_frame_rate']=='30/1' and int(v['nb_read_frames'])==120
        assert ed.subtitles.view(pid)['active']['cues']==original


def test_static_actor_cache_preserves_pixels_with_camera_visibility_and_procedural_flow():
    from PIL import Image
    from app.motion.templates import build as scene_build
    from app.motion.raster import draw_frame
    from app.channels import DEFAULT_STYLE
    data=examples()['diagram'];data['objects'][0]['end']=1.
    scene=scene_build({'template':'documentary','data':data},DEFAULT_STYLE,4.,0,'tr')
    base=Image.new('RGBA',(1920,1080),(0,0,0,0));cache={}
    for t in (0.,.5,.8,1.,1.5,2.,2.5,3.9,.5):
        expected=draw_frame(scene,t,base,{})
        actual=draw_frame(scene,t,base,{},actor_cache=cache)
        assert actual.tobytes()==expected.tobytes()
        assert len(cache)<=3  # bounded per actor; never grows with time
