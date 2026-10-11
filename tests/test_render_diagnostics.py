"""Safe local diagnostics: real decoder checks and synthetic process failures."""
from contextlib import closing
from io import StringIO
import json
from pathlib import Path
import subprocess

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.rendering.diagnostics import classify,diagnostic,safe_diagnostic
from app.rendering.models import RenderError,options
from app.rendering.runner import ProcessRunner
from app.rendering.engine import FFmpegRenderProvider
from app.rendering import probe,timeline,tools
from test_rendering import ready,url,await_job,contract
from test_subtitles import HEADERS

PRIVATE='C:\\Users\\Owner\\private\\secret.mp4 Authorization: sk-private-key-1234 https://private.invalid/audio?signature=PRIVATE environment=PRIVATE'


def failing_process(monkeypatch,text,returncode=1):
    class Child:
        def __init__(self):self.stdout=StringIO('progress=end\n');self.returncode=returncode
        def wait(self,timeout=None):return self.returncode
        def poll(self):return self.returncode
    def popen(args,**kw):
        assert kw['shell'] is False
        kw['stderr'].write((text+'\n'+PRIVATE).encode());kw['stderr'].flush();return Child()
    monkeypatch.setattr('app.rendering.runner.subprocess.Popen',popen)


@pytest.mark.parametrize('text,phase,encoder,code',[
 ('No such file or directory','slot_render','libx264','input_decode_failed'),
 ('Invalid data found when processing input','slot_render','libx264','input_decode_failed'),
 ('Error while filtering','slot_render','libx264','filter_graph_failed'),
 ('Error reinitializing filters','slot_render','libx264','filter_graph_failed'),
 ('Failed to configure output pad','slot_render','libx264','filter_graph_failed'),
 ('No such filter: nonexistent','slot_render','libx264','filter_graph_failed'),
 ('Error parsing filter','slot_render','libx264','filter_graph_failed'),
 ('[Parsed_scale_0] Failed to configure output pad','slot_render','libx264','scale_filter_failed'),
 ('[Parsed_ass_0] Could not create a libass track','final_assembly','libx264','subtitle_filter_failed'),
 ('Error while filtering','subtitle_preflight','','subtitle_filter_failed'),
 ('[concat @ 0] Impossible to open segment','final_assembly','libx264','concat_failed'),
 ('[Parsed_amix_2] Failed to configure output pad','final_assembly','libx264','audio_mix_failed'),
 ('Error opening encoder','slot_render','libx264','encoder_failed'),
 ('Error opening encoder','slot_render','h264_nvenc','encoder_failed'),
 ('Cannot load nvcuda.dll','slot_render','h264_nvenc','nvenc_failed'),
 ('Could not write header','final_assembly','libx264','output_mux_failed'),
 ('Error writing trailer','final_assembly','libx264','output_mux_failed'),
 ('Unrecognized option filter_complex_script. Option not found','slot_render','libx264','filter_option_unsupported'),
 ('Some unknown private error','slot_render','libx264','unknown_ffmpeg_error'),
])
def test_classified_stderr_never_escapes(tmp_path,monkeypatch,text,phase,encoder,code):
    assert classify(text,phase=phase,encoder=encoder)==code
    failing_process(monkeypatch,text);reported=[];runner=ProcessRunner(diagnostic_callback=reported.append)
    with pytest.raises(RenderError) as error:
        runner.run(['trusted-ffmpeg',PRIVATE],tmp_path,phase=phase,encoder=encoder,slot_index=4,slot_id='a'*32,slot_count=37,media_type='video')
    safe=error.value.diagnostic
    assert safe['safe_error_code']==code and safe['phase']==phase and safe['slot_index']==4
    assert safe['return_code']==1 and safe['slot_id']=='a'*32 and 'Medya 5/37' in safe['phase_label']
    assert reported==[safe] and not (tmp_path/'stderr.tmp').exists()
    assert error.value.category==('nvenc_failed' if code=='nvenc_failed' else 'render_failed')
    serialized=json.dumps(safe)+str(error.value)
    for secret in ('Owner','Authorization','sk-private','private.invalid','signature','environment=','Some unknown'):
        assert secret not in serialized


def test_context_is_allowlisted_not_scrubbed():
    safe=diagnostic('unknown_ffmpeg_error',phase=PRIVATE,slot_id=PRIVATE,encoder=PRIVATE,media_type=PRIVATE,slot_index=PRIVATE,operation=PRIVATE,raw_stderr=PRIVATE,command=PRIVATE)
    assert safe['phase']=='ffmpeg' and safe['encoder']==''
    assert set(safe)=={'phase','operation','encoder','safe_error_code','safe_error_summary','phase_label'}
    assert 'PRIVATE' not in json.dumps(safe)
    assert safe_diagnostic({'phase':[], 'safe_error_code':[]}) is None
    assert safe_diagnostic({'phase':'slot_render','safe_error_code':PRIVATE}) is None
    assert classify('libass version banner')=='unknown_ffmpeg_error'
    assert classify('Unknown problem '+PRIVATE,phase='final_assembly')=='unknown_ffmpeg_error'


@pytest.mark.parametrize('change',['no_video','zero_width','negative_height','nan','infinite','zero_duration','missing_duration','bad_stream','bad_format'])
def test_stock_preflight_validates_real_stream_contract(monkeypatch,change):
    data={'streams':[{'codec_type':'video','width':1920,'height':1080}], 'format':{'duration':'3'}}
    if change=='no_video':data['streams'][0]['codec_type']='audio'
    elif change=='zero_width':data['streams'][0]['width']=0
    elif change=='negative_height':data['streams'][0]['height']=-1
    elif change=='missing_duration':data['format']={}
    elif change=='bad_stream':data['streams']=['invalid']
    elif change=='bad_format':data['format']='invalid'
    else:data['format']['duration']={'nan':'nan','infinite':'inf','zero_duration':'0'}[change]
    monkeypatch.setattr(probe,'metadata',lambda *a:data)
    with pytest.raises(RenderError) as error:probe.stock('ffprobe',Path(PRIVATE),'video',slot_index=2,slot_id='b'*32,slot_count=3)
    assert str(error.value)=='Stok medya dosyalarından biri FFmpeg tarafından okunamadı.'
    assert error.value.diagnostic['safe_error_code']=='input_decode_failed' and error.value.diagnostic['slot_index']==2
    assert PRIVATE not in json.dumps(error.value.diagnostic)


def test_image_preflight_accepts_no_duration(monkeypatch):
    monkeypatch.setattr(probe,'metadata',lambda *a:{'streams':[{'codec_type':'video','width':24,'height':24}]})
    assert probe.stock('ffprobe',Path('local.png'),'image')['streams'][0]['width']==24


def test_corrupt_real_slot_has_safe_persistent_diagnostic(ready):
    st=ready;c=st['client'];h=c.app.state.subtitles.handoff(st['pid'])
    path=st['root']/h['stock_slots'][0]['selected_media_local_identity']['local_path']
    path.write_bytes(b'x'*path.stat().st_size)
    assert c.post(url(st)+'/jobs',json={'encoder':'auto'}).status_code==202
    state=await_job(st);safe=state['job']['progress']['diagnostic']
    assert state['job']['status']=='error' and safe['phase']=='input_preflight' and safe['slot_index']==0 and safe['media_type']=='video'
    assert safe['slot_id']==h['stock_slots'][0]['slot_id']
    log=(st['root']/'renders/render-v1.log').read_text()
    assert 'input_decode_failed' in log and 'input_preflight' in log
    assert str(path) not in log and not list((st['root']/'renders').glob('.job-*'))
    with TestClient(create_app(st['storage']),headers=HEADERS) as other:
        assert other.get(url(st)).json()['job']['progress']['diagnostic']==safe
    with closing(c.app.state.projects._connection()) as db:
        assert db.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='12'


@pytest.mark.parametrize('phase,text,code',[
 ('slot_render','Error reinitializing filters','filter_graph_failed'),
 ('subtitle_preflight','Could not create libass track','subtitle_filter_failed'),
 ('final_assembly','[concat @ 0] Impossible to open segment','concat_failed'),
 ('final_assembly','Error writing trailer','output_mux_failed'),
])
def test_safe_diagnostic_reaches_job_api_and_log(ready,monkeypatch,caplog,phase,text,code):
    st=ready;c=st['client'];c.app.state.settings.save('openai',{'api_key':'sk-private-key-1234'})
    class Failed:
        def __init__(self,tool,runner,*args):self.runner=runner
        def render(self,plan):
            failing_process(monkeypatch,text)
            self.runner.run(['trusted-ffmpeg',PRIVATE],plan['temporary'],phase=phase,encoder='libx264',slot_index=0,slot_id=plan['timeline']['slots'][0]['slot_id'],slot_count=len(plan['timeline']['slots']),media_type='video')
    c.app.state.rendering.factory=Failed
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu'}).status_code==202
    state=await_job(st);assert state['job']['progress']['diagnostic']['safe_error_code']==code
    log=(st['root']/'renders/render-v1.log').read_text()
    with closing(c.app.state.projects._connection()) as db:
        persisted=dict(db.execute('SELECT * FROM render_jobs').fetchone())
    combined=json.dumps(state)+json.dumps(persisted)+log+caplog.text
    for secret in ('sk-private-key-1234','Authorization','private.invalid','Owner','signature=','stderr.tmp','trusted-ffmpeg'):assert secret not in combined
    assert not list((st['root']/'renders').glob('.job-*'))
    for name,content in st['originals'].items():assert (st['root']/name).read_bytes()==content


def test_native_filter_file_option_is_short_and_real(tmp_path):
    engine=FFmpegRenderProvider(tools.discover(),ProcessRunner())
    option=engine.graph(tmp_path,'[0:v]scale=16:16,setparams=range=limited,split=1[v]')
    assert option==['-/filter_complex','filter-1.txt']
    result=subprocess.run([engine.tools['ffmpeg'],'-v','error','-f','lavfi','-i','color=s=16x16:d=0.04',*option,'-map','[v]','-frames:v','1','-f','null','-'],cwd=tmp_path,capture_output=True,shell=False)
    assert result.returncode==0


def test_subtitle_preflight_happens_before_slot_encode(tmp_path,monkeypatch):
    h,p=contract();calls=[];runner=ProcessRunner()
    def fail(args,cwd,*a,**context):
        calls.append(context)
        raise RenderError('render_failed','Altyazı filtresi başarısız oldu.',diagnostic=diagnostic('subtitle_filter_failed',**context))
    monkeypatch.setattr(runner,'run',fail)
    plan={'temporary':tmp_path,'timeline':timeline.build(h,p),'handoff':h,'options':options({'encoder':'cpu'}),'media':{},'audio':Path('voice.wav')}
    with pytest.raises(RenderError) as error:FFmpegRenderProvider(tools.discover(),runner).render(plan)
    assert len(calls)==1 and calls[0]['phase']=='subtitle_preflight'
    assert error.value.diagnostic['safe_error_code']=='subtitle_filter_failed'


def test_failed_diagnostic_preserves_old_active_video(ready,monkeypatch):
    st=ready;c=st['client']
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu'}).status_code==202
    old=await_job(st)['active'];output=st['root']/old['metadata']['output_local_path'];before=output.read_bytes()
    class Failed:
        def __init__(self,tool,runner,*a):self.runner=runner
        def render(self,plan):
            failing_process(monkeypatch,'Unknown failure '+PRIVATE)
            self.runner.run(['trusted-ffmpeg'],plan['temporary'],phase='slot_render',encoder='libx264',slot_index=0,slot_count=len(plan['timeline']['slots']))
    c.app.state.rendering.factory=Failed
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu'}).status_code==202
    state=await_job(st)
    assert state['job']['progress']['diagnostic']['safe_error_code']=='unknown_ffmpeg_error'
    assert state['active']['id']==old['id'] and output.read_bytes()==before


def test_real_auto_fallback_keeps_sanitized_nvenc_diagnostic(ready):
    st=ready;c=st['client']
    assert c.post(url(st)+'/jobs',json={'encoder':'auto'}).status_code==202
    state=await_job(st);assert state['job']['status']=='completed'
    if state['active']['metadata']['encoder_used']=='libx264' and 'h264_nvenc' in state['ffmpeg']['encoders']:
        log=(st['root']/'renders/render-v1.log').read_text()
        assert 'nvenc_failed' in log and 'slot_render' in log and 'nvenc_initialization_failed_cpu_retry' in log
        assert 'diagnostic' not in state['job']['progress']


@pytest.mark.parametrize('code',['filter_graph_failed','encoder_failed','input_decode_failed'])
def test_non_nvenc_diagnostic_never_triggers_cpu_retry(monkeypatch,code):
    engine=FFmpegRenderProvider({'encoders':['libx264','h264_nvenc']},None);calls=[]
    def fail(plan,encoder):
        calls.append(encoder)
        raise RenderError('render_failed','Güvenli hata',diagnostic=diagnostic(code,phase='slot_render',encoder=encoder))
    monkeypatch.setattr(engine,'attempt',fail)
    with pytest.raises(RenderError):engine.render({'options':{'encoder':'auto'}})
    assert calls==['h264_nvenc']


def test_output_validation_failure_has_phase(tmp_path,monkeypatch):
    h,p=contract();runner=ProcessRunner();monkeypatch.setattr(runner,'run',lambda *a,**kw:0)
    monkeypatch.setattr(probe,'stock',lambda *a,**kw:{'stock_duration':2})
    def invalid(*a):raise RenderError('output_invalid','Oluşan video doğrulanamadı.')
    monkeypatch.setattr(probe,'validate',invalid)
    plan={'temporary':tmp_path,'timeline':timeline.build(h,p),'handoff':h,'options':options({'encoder':'cpu'}),
          'media':{'1':{'path':Path('a.mp4'),'type':'video'},'2':{'path':Path('b.png'),'type':'image'}},'audio':Path('voice.wav')}
    with pytest.raises(RenderError) as error:FFmpegRenderProvider(tools.discover(),runner).render(plan)
    assert error.value.diagnostic['phase']=='output_validation' and error.value.diagnostic['safe_error_code']=='output_validation_failed'
