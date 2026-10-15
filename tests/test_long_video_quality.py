"""Offline 15-minute native export with real FFmpeg and stream validation.

Synthetic footage/silence only. This proves duration/decoding, not stock API
availability, speech alignment or the artistic quality of a real project.
"""
import shutil
import subprocess

import pytest

from app.rendering import probe, tools
from test_smart_edit import handoffs, run_render, pixels
from test_rendering import synthetic


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='FFmpeg/ffprobe required')
def test_real_fifteen_minute_export_has_both_streams_and_no_truncated_tail(tmp_path):
    seconds=900.
    h,p=handoffs(seconds)
    h['subtitles']=[]
    scenes=[];slots=[];editing=[];media={}
    for i,colour in enumerate(('blue','green','red')):
        source=synthetic(tmp_path,f'source-{i}.mp4',['-f','lavfi','-i',f'color=c={colour}:s=1280x720:r=30:d=1',
                                               '-c:v','libx264','-threads','2','-pix_fmt','yuv420p'])
        sid=f'scene-{i}';slot=f'{i+1:032x}';a=i*300.;b=(i+1)*300.
        scenes.append({'scene_id':sid,'start':a,'end':b,'narration_text':f'Synthetic scene {i}.'})
        slots.append({'slot_id':slot,'scene_id':sid,'order':1,'start':a,'end':b,'duration':b-a,
                      'status':'complete','selected_media_local_identity':{'media_type':'video'}})
        editing.append({'scene_id':sid,'transition':'none','motion':'none','overlay_text':'','composition':'wide','importance':30})
        media[slot]={'type':'video','path':source,'duration':1.,'width':1280,'height':720}
    h.update(scenes=scenes,stock_slots=slots);p['scenes']=editing
    result,plan,runner=run_render(tmp_path/'film',h,p,media,'basic')
    metadata=probe.validate(tools.discover()['ffprobe'],result['path'],seconds)
    assert metadata['duration']==seconds
    assert probe.decode(runner,shutil.which('ffmpeg'),result['path'],seconds,tmp_path/'film')
    # The last shot reaches the actual tail, not merely a 900-second container header.
    frame=pixels(result['path'],899.5)
    assert sum(frame[0::3])>sum(frame[2::3])*3
