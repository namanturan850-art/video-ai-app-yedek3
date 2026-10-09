"""Decode real moving renders: timestamps, crop continuity and held crossfades."""
from copy import deepcopy
import hashlib
import json
import shutil
import subprocess

import pytest

from app.rendering import smart_edit,timeline
from app.rendering.smart_graph import slot_graph
from test_rendering import synthetic,contract
from test_smart_edit import handoffs,run_render

W,H=192,108


def moving(folder,name,seconds,offset=0):
    # A white moving marker plus animated, nonblack background. Each source
    # frame is distinct; camera jumps can be measured separately from motion.
    expression=(f"nullsrc=s=640x360:r=30:d={seconds},geq="
                f"r='if(between(X,180+N/10,200+N/10),240,70+30*sin(N/4+Y/11)+{offset})':"
                "g='if(between(X,180+N/10,200+N/10),240,80+20*sin(N/5+X/13))':"
                "b='if(between(X,180+N/10,200+N/10),240,90+20*sin(N/7+Y/17))'")
    return synthetic(folder,name,['-f','lavfi','-i',expression,'-c:v','libx264'])


def frames(path):
    output=subprocess.run([shutil.which('ffmpeg'),'-v','error','-i',str(path),
        '-vf',f'scale={W}:{H}','-fps_mode','passthrough','-pix_fmt','rgb24','-f','rawvideo','-'],
        capture_output=True,check=True,shell=False).stdout
    size=W*H*3
    assert len(output)%size==0
    return [output[i:i+size] for i in range(0,len(output),size)]


def center(raw):
    weights=[sum(raw[(y*W+x)*3] for y in range(H)
                 if min(raw[(y*W+x)*3:(y*W+x)*3+3])>185) for x in range(W)]
    assert sum(weights)>0
    return sum(x*w for x,w in enumerate(weights))/sum(weights)


def check_clock(path,count):
    if not shutil.which('ffprobe'):pytest.skip('Optional ffprobe absent: per-frame clock not measured')
    result=subprocess.run([shutil.which('ffprobe'),'-v','error','-select_streams','v:0',
        '-show_frames','-show_streams','-show_entries',
        'stream=avg_frame_rate,r_frame_rate,width,height:frame=best_effort_timestamp_time,width,height',
        '-of','json',str(path)],capture_output=True,check=True,shell=False)
    data=json.loads(result.stdout);stream=data['streams'][0];decoded=data['frames']
    assert stream['avg_frame_rate']==stream['r_frame_rate']=='30/1'
    assert (stream['width'],stream['height'])==(1920,1080)
    assert len(decoded)==count
    times=[float(f['best_effort_timestamp_time']) for f in decoded]
    assert times[0]==0
    assert all(abs(t-i/30)<.000002 for i,t in enumerate(times))
    assert all((f['width'],f['height'])==(1920,1080) for f in decoded)


@pytest.mark.parametrize('style',['balanced','dynamic'])
def test_real_moving_crossfade_has_continuous_clock_stable_crop_and_exact_endpoints(tmp_path,style):
    first=moving(tmp_path,'first.mp4',4);second=moving(tmp_path,'second.mp4',4,45)
    originals=[f.read_bytes() for f in (first,second)]
    h,p=contract(6);h['subtitles']=[]
    h['scenes'][0]['end']=h['scenes'][1]['start']=3
    h['stock_slots'][0].update(end=3,duration=3)
    h['stock_slots'][1].update(start=3,duration=3,selected_media_local_identity={'media_type':'video'})
    for s in p['scenes']:s.update(transition='crossfade',motion='none',overlay_text='',composition='wide',importance=50)
    before=deepcopy((h,p))
    result,plan,_=run_render(tmp_path/'render',h,p,{'1':{'path':first,'type':'video'},'2':{'path':second,'type':'video'}},style)
    assert result['metadata']['smart_edit_applied_summary']['scene_transitions']==1
    assert result['metadata']['smart_edit_applied_summary']['motion_effects']==2
    check_clock(result['path'],180);output=frames(result['path'])
    assert len(output)==180 and min(map(min,output))>10
    n=round(plan['slots'][0]['transition_duration']*30)
    window=output[87:90+n+4]
    assert len({hashlib.sha256(f).digest() for f in window})==len(window)
    centers=[center(f) for f in window]
    # Source movement/ghosting is allowed; the old camera reset (~5px at this
    # scale) is not. No sudden alternating crop directions in the handles.
    deltas=[b-a for a,b in zip(centers,centers[1:])]
    assert max(map(abs,deltas))<.9
    assert not any(a*b<0 and min(abs(a),abs(b))>.45 for a,b in zip(deltas,deltas[1:]))
    transition=frames(tmp_path/'render'/'transition-1.mp4')
    tail=frames(tmp_path/'render'/'tail-0.mp4');head=frames(tmp_path/'render'/'head-1.mp4')
    mean_difference=lambda a,b:sum(abs(x-y) for x,y in zip(a,b))/len(a)
    assert len(transition)==len(tail)==len(head)==n
    assert mean_difference(transition[0],tail[0])<1.2
    assert mean_difference(transition[-1],head[-1])<1.2
    assert [f.read_bytes() for f in (first,second)]==originals and (h,p)==before


def test_real_twelve_second_internal_motion_no_reset_or_clock_gap(tmp_path):
    clip=moving(tmp_path,'long.mp4',12);original=clip.read_bytes()
    h,p=handoffs(12);h['subtitles']=[]
    result,plan,_=run_render(tmp_path/'render',h,p,{'a'*32:{'path':clip,'type':'video'}},'balanced')
    assert len(plan['slots'][0]['segments'])==3
    assert result['metadata']['smart_edit_applied_summary']['internal_edits']==2
    check_clock(result['path'],360);output=frames(result['path'])
    assert len(output)==360 and clip.read_bytes()==original
    for boundary in (120,240):
        window=output[boundary-3:boundary+4]
        assert min(map(min,window))>10
        assert len({hashlib.sha256(f).digest() for f in window})==len(window)
        centers=[center(f) for f in window]
        assert max(abs(b-a) for a,b in zip(centers,centers[1:]))<.5


@pytest.mark.parametrize('style',['balanced','dynamic'])
def test_transition_suppresses_only_overlapping_punch_without_changing_exact_text_or_times(style):
    h,p=contract(8)
    h['scenes'][0]['end']=h['scenes'][1]['start']=4
    h['stock_slots'][0].update(end=4,duration=4)
    h['stock_slots'][1].update(start=4,duration=4)
    for s in p['scenes']:s.update(transition='crossfade',motion='none',composition='wide',importance=80,overlay_text='')
    p['scenes'][1]['narration_text']='Im Jahr 2026.'
    h['subtitles']=[{'index':1,'start':4,'end':6,'text':'Im Jahr 2026.'}]
    t=timeline.build(h,p);unadjusted=smart_edit.emphasis(t,h,style)
    plan=smart_edit.build(t,h,style,'source');adjusted=plan['emphasis']
    assert len(unadjusted)==len(adjusted)==1 and unadjusted[0]['punch_in']
    assert not adjusted[0]['punch_in'] and adjusted[0]['punch_suppressed']=='transition'
    assert {k:v for k,v in adjusted[0].items() if k not in ('punch_in','punch_suppressed')}=={k:v for k,v in unadjusted[0].items() if k!='punch_in'}
    # Graph guard also protects a legacy/manually restored overlapping punch.
    n=round(plan['slots'][0]['transition_duration']*30)
    graph=slot_graph('fps=30',[('core',n,120),('head',0,n)],1,[0,n],[n,0],[0,0],plan['slots'][1],unadjusted)
    assert '+0.01*' not in graph
