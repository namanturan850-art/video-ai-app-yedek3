"""Real source bounds, delayed video PTS and Program/final frame agreement."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
from fastapi.testclient import TestClient
from PIL import Image,ImageChops,ImageStat
from app.main import create_app
from app.editor.advanced import AdvancedEditor,Document
from app.editor.proxies import snapshot,build as proxy_build
from app.editor.previews import program_frame
from app.editor.models import EditorError
from app.rendering.source_timing import coverage,duration,input_time
from app.rendering.models import RenderError,options
from app.rendering.tools import discover
from app.rendering.engine import FFmpegRenderProvider
from app.rendering.runner import ProcessRunner
from app.rendering.timeline import build as timeline_build
from test_manual_first import install_manual_example
from test_rendering import synthetic,contract
from test_subtitles import wav


def install_videos(app,seconds=12):
    st=install_manual_example(app,seconds=seconds);pid=st['pid'];root=st['root']
    # First video has 5 seconds of video starting at container t=2, alongside
    # 9 seconds of audio. Container duration is NOT its usable video duration.
    first=synthetic(root/'stock','1'*32+'.mp4',['-f','lavfi','-i','testsrc2=s=320x180:r=25:d=5',
        '-f','lavfi','-i','sine=frequency=400:duration=9','-filter:v','setpts=PTS+2/TB',
        '-fps_mode','passthrough','-c:v','libx264','-threads','1','-c:a','aac'])
    second=synthetic(root/'stock','2'*32+'.mp4',['-f','lavfi','-i','testsrc2=s=320x180:r=30:d=10',
        '-vf','hue=h=90','-c:v','libx264','-threads','1'])
    with closing(app.state.projects._connection()) as c,c:
        row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone();stock=json.loads(row[0])
        for i,(slot,path) in enumerate(zip(stock['slots'],(first,second))):
            media={'provider':'local','media_id':str(i+1)*32,'media_type':'video','title':'Gerçek hareketli test',
                'local_path':'stock/'+path.name,'file_size':path.stat().st_size,'sha256':sha256(path.read_bytes()).hexdigest(),
                'duration':9. if i==0 else 10.,'width':320,'height':180,'has_audio':False}
            c.execute('INSERT INTO stock_assets VALUES (?,?,?,?,?)',(pid,'local',media['media_id'],'video',json.dumps(media)))
            slot.update(selected_media=media,segment_start=.2 if i==0 else 1.,segment_end=4.9 if i==0 else 9.9)
        c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(stock),pid))
    return st


def pixels(path,width=160,height=90):
    raw=subprocess.check_output(['ffmpeg','-v','error','-threads','1','-i',str(path),'-vf',f'scale={width}:{height}',
        '-pix_fmt','rgb24','-f','rawvideo','-'])
    size=width*height*3
    return [Image.frombytes('RGB',(width,height),raw[i:i+size]) for i in range(0,len(raw),size)]


def test_actual_video_duration_excludes_long_audio_and_delayed_start(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        st=install_videos(client.app)
        path=st['root']/'stock'/('1'*32+'.mp4')
        assert duration(path,discover()['ffprobe'])==pytest.approx(5.,abs=.001)
        assert input_time(path,discover()['ffprobe'],.2)==pytest.approx(2.2,abs=.04)
        uploaded=client.post(f'/api/projects/{st["pid"]}/editor/archive/upload',content=path.read_bytes(),
                             headers={'X-AI-Video-Studio':'projects','X-File-Name':'source.mp4','Content-Type':'video/mp4'})
        assert uploaded.status_code==201,uploaded.text
        assert uploaded.json()['item']['duration']==duration(path,discover()['ffprobe'])
        with pytest.raises(RenderError,match=f'kaynak {duration(path,discover()["ffprobe"]):.3f}'):
            coverage(duration(path,discover()['ffprobe']),.2,None,1.,6.,where='Sahne 1, 0 sn')


@pytest.mark.parametrize('start,end,speed,length',[(0.,None,1.,6.),(2.,None,1.,2.),(0.,2.,1.,3.),(0.,None,2.,2.)])
def test_three_second_source_is_not_looped_or_filled(start,end,speed,length):
    with pytest.raises(RenderError):coverage(3.,start,end,speed,length,where='Sahne Roma, 4 sn')


@pytest.mark.parametrize('quality',['high','full'])
def test_real_consecutive_videos_match_final_without_black_heads_or_tails(tmp_path,quality):
    app=create_app(tmp_path/'app')
    with TestClient(app) as client:
        st=install_videos(app);pid=st['pid'];ed=app.state.editor;advanced=AdvancedEditor(ed)
        before=advanced.get(pid);view=ed.view(pid)
        # Different saved transforms on either side of a subframe cut must take
        # effect on the same first/last output frame in proxy and export.
        edits=advanced.get(pid)
        ordered=sorted([s for xs in view['tracks'].values() for s in xs if s.get('slot_id')],key=lambda s:s['start'])
        edits['document']['adjustments']=[{'slot_id':s['slot_id'],'transform':{'x':70 if i==0 else -70}} for i,s in enumerate(ordered)]
        advanced.save(pid,edits);before=advanced.get(pid)
        # Draw no captions in either output, so every edge frame is comparable.
        from app.editor.editorial import Editorial
        prefs=Editorial(ed).get(pid);prefs['preferences']['subtitle_display']='none';Editorial(ed).save(pid,prefs)
        folder=tmp_path/'proxy';folder.mkdir();preview=[]
        for time in (0.,4.,8.):
            key,data,_=snapshot(ed,advanced,pid,time,quality);target=folder/f'{key}.mp4';proxy_build(folder,target,data)
            frames=pixels(target);assert len(frames)==120
            assert all(max(ImageStat.Stat(frame).mean)>30 for frame in frames)
            preview+=frames
        inputs=app.state.rendering._inputs(pid,options({'encoder':'cpu','subtitle_display':'none'}),True)
        inputs['temporary']=tmp_path/'render';inputs['temporary'].mkdir()
        result=FFmpegRenderProvider(discover(),ProcessRunner(),workers=1).render(inputs)
        final=pixels(result['path']);assert len(final)==360 and len(preview)==360
        assert all(max(ImageStat.Stat(frame).mean)>30 for frame in final)
        boundary=round(view['scenes'][0]['end']*30)
        for index in sorted({0,1,118,119,120,121,boundary-1,boundary,boundary+1,238,239,240,358,359}):
            delta=ImageStat.Stat(ImageChops.difference(final[index],preview[index]))
            assert max(delta.mean)<14,(index,delta.mean)
            assert max(ImageStat.Stat(final[index]).mean)>30
        assert advanced.get(pid)==before


def test_three_second_source_six_second_timeline_rejected_in_frame_proxy_and_final(tmp_path):
    app=create_app(tmp_path/'app')
    with TestClient(app) as client:
        st=install_manual_example(app,seconds=18);pid=st['pid'];ed=app.state.editor;advanced=AdvancedEditor(ed)
        short=synthetic(st['root']/'stock','3'*32+'.mp4',['-f','lavfi','-i','color=c=red:s=320x180:r=30:d=3','-c:v','libx264','-threads','1'])
        with closing(app.state.projects._connection()) as c,c:
            row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone();stock=json.loads(row[0])
            m={**stock['slots'][0]['selected_media'],'local_path':'stock/'+short.name,'sha256':sha256(short.read_bytes()).hexdigest(),'file_size':short.stat().st_size,'duration':99.,'media_type':'video'}
            stock['slots'][0]['selected_media']=m
            c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(stock),pid))
        before=advanced.get(pid)
        with pytest.raises(RenderError,match='kaynak 3.000'):
            coverage(duration(short,discover()['ffprobe']),0.,None,1.,6.,where='3 sn kaynak / 6 sn timeline')
        with pytest.raises(EditorError,match='kaynak 3.000'):snapshot(ed,advanced,pid,0.,'high')
        with pytest.raises(EditorError,match='kaynak 3.000'):program_frame(ed,advanced,pid,.1)
        inputs=app.state.rendering._inputs(pid,options({'encoder':'cpu'}),True);inputs['temporary']=tmp_path/'render';inputs['temporary'].mkdir()
        with pytest.raises(RenderError,match='kaynak 3.000'):FFmpegRenderProvider(discover(),ProcessRunner(),workers=1).render(inputs)
        assert advanced.get(pid)==before


@pytest.mark.parametrize('kind',['cross_dissolve','wipe','dip_black'])
def test_selected_transitions_match_program_frames_and_final_video(tmp_path,kind):
    app=create_app(tmp_path/'app')
    with TestClient(app) as client:
        st=install_videos(app,seconds=4);pid=st['pid'];ed=app.state.editor;advanced=AdvancedEditor(ed)
        from app.editor.editorial import Editorial
        prefs=Editorial(ed).get(pid);prefs['preferences']['subtitle_display']='none';Editorial(ed).save(pid,prefs)
        view=ed.view(pid);slots=sorted([s for xs in view['tracks'].values() for s in xs if s.get('slot_id')],key=lambda s:s['start'])
        state=advanced.get(pid);state['document']['transitions']=[{'slot_id':slots[0]['slot_id'],'next_slot_id':slots[1]['slot_id'],'kind':kind,'duration':.2}]
        advanced.save(pid,state);before=advanced.get(pid)
        key,data,_=snapshot(ed,advanced,pid,0.,'high');path=tmp_path/'proxy.mp4';proxy_build(tmp_path,path,data)
        proxy=pixels(path)
        inputs=app.state.rendering._inputs(pid,options({'encoder':'cpu','subtitle_display':'none'}),True)
        inputs['temporary']=tmp_path/'render';inputs['temporary'].mkdir()
        result=FFmpegRenderProvider(discover(),ProcessRunner(),workers=1).render(inputs);final=pixels(result['path'])
        boundary=round(slots[0]['end']*30)
        assert len(proxy)==len(final)==120
        for index in range(boundary-3,boundary+7):
            diff=ImageStat.Stat(ImageChops.difference(proxy[index],final[index]))
            assert max(diff.mean)<14,(kind,index,diff.mean)
            still=Image.open(program_frame(ed,advanced,pid,index/30)).convert('RGB').resize((160,90))
            assert max(ImageStat.Stat(ImageChops.difference(still,final[index])).mean)<16,(kind,index)
        assert advanced.get(pid)==before


def test_draft_transition_uses_real_video_handle_not_long_audio_metadata(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app,headers={'X-AI-Video-Studio':'projects'}) as client:
        st=install_videos(app);pid=st['pid'];ed=app.state.editor
        from app.editor.editorial import Editorial
        with closing(app.state.projects._connection()) as c,c:
            stock=json.loads(c.execute('SELECT state_json FROM stock_plans WHERE project_id=?',(pid,)).fetchone()[0])
            # 125 frames at 25 fps cover 5s; saved container metadata says 9s.
            stock['slots'][0].update(segment_start=.68,segment_end=None)
            c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(stock),pid))
        base=f'/api/projects/{pid}/editor';package=client.get(base+'/manual/package').json();plan=deepcopy(package['output_template']);scene=package['narration'][0]
        plan['sahneler']=[{'scene_id':scene['scene_id'],'start':scene['start'],'end':scene['end'],'transition':'crossfade'}]
        plan['katmanlar']=[{'scene_id':scene['scene_id'],'text':'Roma','start':0.,'end':.2}]
        before=AdvancedEditor(ed).get(pid)
        draft=Editorial(ed).import_draft(pid,plan)
        assert not draft['transitions'] and len(draft['clips'])==1
        assert draft['transition_issues'][0]['category']=='short_transition'
        assert AdvancedEditor(ed).get(pid)==before
        issue=draft['transition_issues'][0]
        assert issue['scene_id']==scene['scene_id'] and issue['time']==scene['end']
        assert {o['id'] for o in issue['options']}=={'hard_cut','dip_black'}


@pytest.mark.parametrize('speed',[.5,2.])
def test_explicit_source_speed_has_the_same_frames_in_proxy_and_final(tmp_path,speed):
    app=create_app(tmp_path)
    with TestClient(app) as client:
        st=install_videos(app,seconds=4);pid=st['pid'];ed=app.state.editor;advanced=AdvancedEditor(ed)
        from app.editor.editorial import Editorial
        prefs=Editorial(ed).get(pid);prefs['preferences']['subtitle_display']='none';Editorial(ed).save(pid,prefs)
        slots=[s for xs in ed.view(pid)['tracks'].values() for s in xs if s.get('slot_id')]
        state=advanced.get(pid);state['document']['adjustments']=[{'slot_id':s['slot_id'],'transform':{'speed':speed}} for s in slots]
        advanced.save(pid,state);before=advanced.get(pid)
        key,data,_=snapshot(ed,advanced,pid,0.,'high');proxy=tmp_path/'proxy.mp4';proxy_build(tmp_path,proxy,data)
        plan=app.state.rendering._inputs(pid,options({'encoder':'cpu','subtitle_display':'none'}),True);plan['temporary']=tmp_path/'render';plan['temporary'].mkdir()
        result=FFmpegRenderProvider(discover(),ProcessRunner(),workers=1).render(plan)
        frames,reference=pixels(proxy),pixels(result['path'])
        assert len(frames)==len(reference)==120
        assert all(max(ImageStat.Stat(frame).mean)>30 for frame in reference)
        for a,b in zip(frames,reference):assert max(ImageStat.Stat(ImageChops.difference(a,b)).mean)<14
        assert advanced.get(pid)==before
