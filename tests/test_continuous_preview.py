"""Continuous packet timestamps and native-size drawing; no paid providers."""
from copy import deepcopy
import json
import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from PIL import Image,ImageChops,ImageStat
from app.main import create_app
from app.animation.examples import examples
from app.channels import DEFAULT_STYLE
from app.motion.templates import build
from app.motion.raster import draw_frame
from test_manual_first import install_manual_example


@pytest.mark.parametrize('kind',['science','chart','diagram'])
def test_native_720p_actors_preserve_geometry_camera_labels_and_alpha(kind):
    scene=build({'template':'documentary','data':examples()[kind]},DEFAULT_STYLE,4.,0,'tr')
    full=draw_frame(scene,1.,Image.new('RGBA',(1920,1080),(0,0,0,0)),{})
    scene['_render_size']=[1280,720]
    native=draw_frame(scene,1.,Image.new('RGBA',(1280,720),(0,0,0,0)),{})
    # The same coordinate system, not a smaller crop of the upper-left corner.
    reference=full.resize(native.size,Image.Resampling.LANCZOS)
    diff=ImageStat.Stat(ImageChops.difference(reference,native))
    assert max(diff.mean)<3,diff.mean
    assert native.getbbox() and native.getpixel((10,10))[3]==0
    assert native.crop((400,20,900,70)).getbbox()  # required DEMO notice remains visible


def test_stream_remux_preserves_uniform_frames_audio_clock_and_source_identity(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app,headers={'X-AI-Video-Studio':'projects'}) as client:
        st=install_manual_example(app);pid=st['pid'];base=f'/api/projects/{pid}/editor/advanced'
        before=client.get(base).json();response=client.post(base+'/program-proxy',json={'time':0.,'quality':'high'})
        assert response.status_code==200,response.text
        meta=response.json();deadline=time.monotonic()+60
        while meta['status']!='ready':
            assert time.monotonic()<deadline
            time.sleep(.1);meta=client.get(meta['status_url']).json()
        result=client.get(meta['stream_info_url']);assert result.status_code==200,result.text
        info=result.json();assert info['mime'].startswith('video/mp4; codecs="avc1.') and info['origin']==0.
        response=client.get(info['url']);assert response.status_code==200
        target=tmp_path/'fragmented.mp4';target.write_bytes(response.content)
        assert b'moof' in target.read_bytes() and b'mvex' in target.read_bytes()
        data=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v','-show_entries','packet=pts_time,duration_time','-of','json',str(target)]))
        stamps=[float(p['pts_time']) for p in data['packets']]
        assert len(stamps)==120 and stamps[0]==0.
        assert all(abs(b-a-1/30)<.00001 for a,b in zip(stamps,stamps[1:]))
        # The original AAC priming edit is preserved, not repeated as an extra
        # 21ms delay on each video segment as with empty_moov remuxing.
        audio=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','a','-show_entries','packet=pts_time','-of','json',str(target)]))['packets']
        assert abs(float(audio[0]['pts_time'])+1024/48000)<.00001
        assert float(audio[1]['pts_time'])==0.
        assert client.get(meta['stream_info_url']).json()==info
        assert client.get(base).json()==before
        assert client.get(base+'/program-stream/'+'a'*64).status_code==404


def test_static_text_flattening_preserves_order_pixels_and_original_document(tmp_path):
    from app.editor.advanced import Document
    from app.editor.proxy_layers import flatten
    from app.editor.compositor import compile_graph
    doc=Document.model_validate({'clips':[
        {'id':'1'*32,'kind':'text','track':'layers','start':0.,'end':1.,'text':'İstanbul','transform':{'x':120,'y':-81}},
        {'id':'2'*32,'kind':'text','track':'layers','start':0.,'end':1.,'text':'Belgesel','transform':{'x':-80,'y':81}},
        {'id':'3'*32,'kind':'text','track':'layers','start':0.,'end':1.,'text':'Hareketli','keyframes':[{'property':'x','time':0.,'value':-100},{'property':'x','time':1.,'value':100}]},
    ]}).model_dump();before=deepcopy(doc);assets={}
    flat,resolved=flatten(doc,assets,tmp_path,1280,720)
    assert doc==before and not assets and len(flat['clips'])==2
    assert flat['clips'][-1]==doc['clips'][-1] and flat['clips'][0]['id']==doc['clips'][0]['id']
    def render(document,media,name):
        args=['ffmpeg','-v','error','-y','-filter_complex_threads','1','-threads','1','-f','lavfi','-i','color=c=blue:s=1280x720:r=30:d=1']
        graph,label,_=compile_graph(args,document,media,base='0:v',folder=tmp_path,duration=1.,width=1280,height=720)
        path=tmp_path/(name+'.mp4')
        subprocess.run(args+['-filter_complex',graph,'-map',f'[{label}]','-c:v','libx264','-preset','ultrafast','-crf','18','-threads','1','-t','1',str(path)],check=True)
        raw=subprocess.check_output(['ffmpeg','-v','error','-ss','0.5','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        return Image.frombytes('RGB',(1280,720),raw)
    original=render(doc,{},'original');optimized=render(flat,resolved,'flattened')
    stats=ImageStat.Stat(ImageChops.difference(original,optimized))
    assert max(stats.mean)<.5,stats.mean
    assert doc==before
