import subprocess
import shutil

from PIL import Image
import pytest

from app.editor.advanced import Document
from app.editor.compositor import compile_graph,value_at


def decoded_frame(path,time):
    done=subprocess.run([shutil.which('ffmpeg'),'-v','error','-ss',str(time),'-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True,check=True)
    import io
    return Image.open(io.BytesIO(done.stdout)).convert('RGB')


def test_real_keyframe_effect_overlay_and_duration(tmp_path):
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:pytest.skip('FFmpeg gerekli')
    source=tmp_path/'source.png';Image.new('RGB',(100,100),'red').save(source)
    document=Document.model_validate({'clips':[{'id':'a'*32,'track':'layers','kind':'media','start':0.,'end':.6,
        'media':{'provider':'local','media_id':'a','sha256':'a'*64},'transform':{'scale':.3},
        'effects':{'monochrome':True},'keyframes':[{'property':'x','time':0.,'value':-480.},
          {'property':'x','time':.6,'value':480.},{'property':'opacity','time':0.,'value':.3},
          {'property':'opacity','time':.6,'value':1.,'interpolation':'ease_in_out'},
          {'property':'scale','time':0.,'value':.2},{'property':'scale','time':.6,'value':.4},
          {'property':'rotation','time':0.,'value':0.},{'property':'rotation','time':.6,'value':20.}]}]}).model_dump()
    args=[ffmpeg,'-v','error','-y','-filter_complex_threads','1','-threads','1','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=0.6']
    graph,label,_=compile_graph(args,document,{'a'*32:{'path':source,'type':'image'}},folder=tmp_path,duration=.6,width=320,height=180)
    out=tmp_path/'out.mp4'
    subprocess.run(args+['-filter_complex',graph,'-map',f'[{label}]','-t','0.6','-an','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(out)],check=True,capture_output=True)
    first,last=decoded_frame(out,.05),decoded_frame(out,.5)
    def points(image):
        return [(x,y) for y in range(180) for x in range(320) if image.getpixel((x,y))[0]>20]
    a,b=points(first),points(last)
    assert a and b
    assert sum(x for x,y in b)/len(b)>sum(x for x,y in a)/len(a)+70
    # Desaturation is actually present in the encoded foreground.
    red,green,blue=last.getpixel((215,90));assert abs(red-green)<8
    assert value_at(document['clips'][0],'x',.3)==0
    assert .3<value_at(document['clips'][0],'opacity',.3)<1
    # Still preview and encoded final use the same graph at first/middle/last points.
    from PIL import ImageChops,ImageStat
    for time in (0.,.3,.5):
        still_args=[ffmpeg,'-v','error','-y','-filter_complex_threads','1','-threads','1','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=0.04']
        still_graph,still_label,_=compile_graph(still_args,document,{'a'*32:{'path':source,'type':'image'}},folder=tmp_path,duration=.04,width=320,height=180,frame_time=time)
        still=tmp_path/f'frame-{time}.png'
        subprocess.run(still_args+['-filter_complex',still_graph,'-map',f'[{still_label}]','-frames:v','1','-threads','1',str(still)],check=True,capture_output=True)
        difference=ImageStat.Stat(ImageChops.difference(Image.open(still).convert('RGB'),decoded_frame(out,time)))
        assert max(difference.mean)<5,(time,difference.mean)


def test_real_text_fade_and_black_background_adjustment(tmp_path):
    ffmpeg=shutil.which('ffmpeg')
    doc=Document.model_validate({'clips':[{'id':'b'*32,'kind':'text','track':'emphasis','start':0.,'end':.5,'text':'NAMAN','font_size':100,'color':'#FF0000','fade_in':.2}]}).model_dump()
    args=[ffmpeg,'-v','error','-y','-filter_complex_threads','1','-threads','1','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=0.5']
    graph,label,_=compile_graph(args,doc,{},folder=tmp_path,duration=.5,width=320,height=180)
    out=tmp_path/'text.mp4'
    subprocess.run(args+['-filter_complex',graph,'-map',f'[{label}]','-t','0.5','-an','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(out)],capture_output=True,check=True)
    assert max(p[0] for p in decoded_frame(out,.3).getdata())>150
    assert decoded_frame(out,.3).getpixel((0,0))[2]>200


def test_native_engine_delivers_edits_transition_and_unchanged_clock(tmp_path,monkeypatch):
    from test_rendering import contract,synthetic
    from test_subtitles import wav
    from app.rendering.engine import FFmpegRenderProvider
    from app.rendering.runner import ProcessRunner
    from app.rendering.tools import discover
    from app.rendering.models import options
    from app.rendering.timeline import build
    h,p=contract(2.);source=synthetic(tmp_path,'source.mp4',['-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=3','-c:v','libx264','-threads','1'])
    second=synthetic(tmp_path,'second.mp4',['-f','lavfi','-i','color=c=red:s=320x180:r=30:d=3','-c:v','libx264','-threads','1'])
    voice=tmp_path/'voice.wav';voice.write_bytes(wav(2))
    document=Document.model_validate({'adjustments':[{'slot_id':'1','effects':{'brightness':.15}}],
        'clips':[{'id':'c'*32,'kind':'text','track':'emphasis','start':.1,'end':1.8,'text':'NAMAN','color':'#FF0000','font_size':100}],
        'transitions':[{'slot_id':'1','next_slot_id':'2','kind':'wipe','duration':.1}]}).model_dump()
    timeline=build(h,p)
    plan={'temporary':tmp_path,'timeline':timeline,'handoff':h,'options':options({'encoder':'cpu','subtitle_display':'none'}),
          'audio':voice,'music':None,'media':{'1':{'path':source,'type':'video'},'2':{'path':second,'type':'video'}},
          'advanced_document':document,'advanced_assets':{},'advanced_slots':{x['slot_id']:x for x in timeline['slots']}}
    result=FFmpegRenderProvider(discover(),ProcessRunner(),workers=1).render(plan)
    assert abs(result['metadata']['duration']-2)<.04
    image=decoded_frame(result['path'],.8)
    assert max(pixel[0] for pixel in image.getdata())>160
    graphs='\n'.join(p.read_text() for p in tmp_path.glob('filter-*.txt'))
    assert 'wipeleft' in graphs and 'brightness=0.15' in graphs
    assert result['metadata']['smart_edit_applied_summary']['scene_transitions']==1
    # Visible, different sources prove the saved Wipe actually reaches encoded frames.
    from types import SimpleNamespace
    from hashlib import sha256
    from app.editor.previews import program_frame
    from PIL import ImageChops,ImageStat
    (tmp_path/'stock').mkdir()
    media=[]
    for slot,path in zip(timeline['slots'],(source,second)):
        media.append({**slot,'clip_start':0,'media':{'media_type':'video','duration':3.,'sha256':sha256(path.read_bytes()).hexdigest(),'_test_path':path}})
    monkeypatch.setattr('app.stock.download.asset_path',lambda projects,pid,item:item['_test_path'])
    editor=SimpleNamespace(projects=SimpleNamespace(_path=lambda pid:tmp_path),stock=None,archive_file=lambda *args:None,
        view=lambda pid:{'duration':2.,'stock_revision':1,'tracks':{'visuals':media}})
    advanced=SimpleNamespace(get=lambda pid:{'document':document})
    for time in (1.5,1.5+1/30,1.5+2/30):
        preview=Image.open(program_frame(editor,advanced,'test',time)).convert('RGB')
        final=decoded_frame(result['path'],time).resize((640,360))
        # Corners exclude the independently rasterized caption glyphs.
        for box in ((10,20,100,80),(540,20,630,80)):
            assert max(ImageStat.Stat(ImageChops.difference(preview.crop(box),final.crop(box))).mean)<12
    mid=decoded_frame(result['path'],1.5+1/30)
    assert mid.getpixel((100,100))[2]>150 and mid.getpixel((1820,100))[0]>150


@pytest.mark.parametrize('speed',[.5,1.,2.])
def test_audio_layer_delay_fade_and_volume_keyframes(tmp_path,speed):
    import wave,array,math
    ffmpeg=shutil.which('ffmpeg');sound=tmp_path/'sine.wav'
    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=0.8',str(sound)],check=True,capture_output=True)
    doc=Document.model_validate({'clips':[{'id':'d'*32,'kind':'media','track':'audio','start':.2,'end':.6,
       'media':{'provider':'local','media_id':'sound','sha256':'d'*64},'transform':{'volume':.5,'speed':speed},'fade_in':.1,
       'keyframes':[{'property':'volume','time':0.,'value':.1},{'property':'volume','time':.4,'value':.5}]}]}).model_dump()
    args=[ffmpeg,'-v','error','-y','-filter_complex_threads','1','-f','lavfi','-i','color=c=black:s=32x32:r=30:d=1']
    graph,_,labels=compile_graph(args,doc,{'d'*32:{'path':sound,'type':'audio'}},folder=tmp_path,duration=1,width=32,height=32)
    out=tmp_path/'mix.wav';subprocess.run(args+['-filter_complex',graph,'-map',f'[{labels[0]}]','-ar','48000','-ac','1','-c:a','pcm_s16le',str(out)],check=True,capture_output=True)
    with wave.open(str(out)) as f:
        samples=array.array('h');samples.frombytes(f.readframes(f.getnframes()))
    rms=lambda a,b:math.sqrt(sum(x*x for x in samples[round(a*48000):round(b*48000)])/round((b-a)*48000))
    assert len(samples)==48000 and rms(0,.15)<1 and rms(.4,.5)>100 and rms(.8,.9)<1
