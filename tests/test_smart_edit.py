"""Part 9.5: immutable plans + actual FFmpeg pixels, not command-only proof."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.rendering import smart_edit,timeline,ass,tools,probe
from app.rendering.models import options,RenderError
from app.rendering.engine import FFmpegRenderProvider
from app.rendering.runner import ProcessRunner
from test_rendering import synthetic,contract,ready,url,await_job
from test_subtitles import wav,HEADERS


def handoffs(seconds=4,text='Im Jahr 2026 beginnt eine neue Geschichte.'):
    h,p=contract(seconds)
    h['scenes']=[{'scene_id':'a','start':0,'end':seconds,'narration_text':text}]
    h['stock_slots']=[{'slot_id':'a'*32,'scene_id':'a','order':1,'start':0,'end':seconds,'duration':seconds,'status':'complete','selected_media_local_identity':{'media_type':'video','provider':'pixabay','media_id':'1','local_path':'stock/local.mp4'}}]
    h['subtitles']=[{'index':1,'start':.5,'end':min(3.5,seconds),'text':text}]
    p['scenes']=[{'scene_id':'a','transition':'hard_cut','motion':'none','overlay_text':'','composition':'wide','importance':50,'narration_text':text}]
    return h,p


def owner_shape():
    seconds=193;h,p=handoffs(seconds);scenes=[];metadata=[];slots=[]
    for i in range(24):
        a=i*seconds/24;b=(i+1)*seconds/24;sid=f'scene-{i}'
        text='Im Jahr 2026 beginnt eine neue Geschichte.'
        scenes.append({'scene_id':sid,'start':a,'end':b,'narration_text':text})
        metadata.append({'scene_id':sid,'narration_text':text,'importance':80 if i%5==0 else 50,'composition':'wide' if i%2 else 'medium','motion':'none','transition':'none','overlay_text':''})
        count=2 if i<13 else 1
        for j in range(count):
            start=a+(b-a)*j/count;end=a+(b-a)*(j+1)/count
            slots.append({'slot_id':f'{len(slots)+1:032x}','scene_id':sid,'order':j+1,'start':start,'end':end,'duration':end-start,'status':'complete','selected_media_local_identity':{'media_type':'video','provider':'pixabay','media_id':str(len(slots)+1),'local_path':'stock/local.mp4'}})
    h.update(scenes=scenes,stock_slots=slots,subtitles=[{'index':i+1,'start':i*seconds/49,'end':(i+1)*seconds/49,'text':'Im Jahr 2026 beginnt eine neue Geschichte.'} for i in range(49)])
    p['scenes']=metadata
    return h,p


@pytest.mark.parametrize('style',['basic','balanced','dynamic'])
def test_plan_deterministic_readonly(style):
    h,p=owner_shape();t=timeline.build(h,p);before=deepcopy((h,p,t))
    plan=smart_edit.build(t,h,style,'fixed-source')
    assert plan==smart_edit.build(deepcopy(t),deepcopy(h),style,'fixed-source')
    assert (h,p,t)==before
    assert plan['fingerprint']!=smart_edit.build(t,h,style,'changed-source')['fingerprint']
    assert plan['editing_style']==style


def test_owner_video_only_shape_has_meaningful_visible_edits():
    h,p=owner_shape();t=timeline.build(h,p);plan=smart_edit.build(t,h,'balanced','source');s=plan['summary']
    assert s['slots']==37 and s['scenes']==24 and len(h['subtitles'])==49
    assert all(item['media_type']=='video' for item in plan['slots'])
    assert 18<=s['motion_effects']<=37 and 6<=s['scene_transitions']<=12 and 5<=s['emphasis_texts']<=8 and s['internal_edits']>=6
    assert all(e['text'] in ' '.join(s['narration_text'] for s in p['scenes']) for e in plan['emphasis'])
    assert all(1.5<=e['end']-e['start'] for e in plan['emphasis'])  # the card lasts until the sentence ends (+0.4 s)
    assert plan['emphasis'][0]['start']<15
    for old,new in zip(t['slots'],plan['slots']):
        assert old['slot_id']==new['slot_id'] and old['start']==new['start'] and old['end']==new['end']
        segments=new['segments'];assert segments[0]['start_frame']==0 and segments[-1]['end_frame']==old['frames']
        assert sum(s['frames'] for s in segments)==old['frames']
        assert all(a['end_frame']==b['start_frame'] for a,b in zip(segments,segments[1:]))
        assert all(0<=s['motion_strength']<=.07 for s in segments)
    within=[i for i in range(36) if plan['slots'][i]['scene_id']==plan['slots'][i+1]['scene_id']]
    assert all(plan['slots'][i]['transition_out']=='hard_cut' for i in within)


@pytest.mark.parametrize('text,expected',[
 ('Im Jahr 2026.', 'Im Jahr 2026.'),
 ('70 Prozent der Menschen.', '70 Prozent der Menschen.'),
 ('Eine kurze Aussage, gefolgt von einer sehr sehr sehr sehr langen weiteren Erklärung.', 'Eine kurze Aussage,'),
 ('Unvollständig',None),
 ('Dies ist ein viel zu langer Satz ohne eine natürliche kurze Grenze für eine sinnvolle Hervorhebung.',None),
])
def test_exact_phrase_extraction(text,expected):
    result=smart_edit.phrase(text);assert result==expected
    if result:assert result in smart_edit.clean(text)


def test_emphasis_only_exact_source_and_no_interior_timing_guess():
    h,p=handoffs(8,'Im Jahr 2026 beginnt eine neue Geschichte.')
    h['subtitles']=[{'index':1,'start':0,'end':3,'text':'Eine erfundene neue Behauptung.'},{'index':2,'start':3,'end':7,'text':'Im Jahr 2026'}]
    plan=smart_edit.build(timeline.build(h,p),h,'balanced','s')
    assert [e['text'] for e in plan['emphasis']]==['Im Jahr 2026']
    assert plan['emphasis'][0]['start']==3 and plan['emphasis'][0]['end']<=7.8
    h['subtitles'][1]['text']='Viele zusätzliche Wörter liegen vor Im Jahr 2026 aber kein eigener kurzer Satz ist hier.'
    assert not smart_edit.build(timeline.build(h,p),h,'balanced','s')['emphasis']


def test_existing_overlay_kept_exactly_even_not_in_narration():
    h,p=handoffs();p['scenes'][0]['overlay_text']='Bereits genehmigte Betonung.'
    for style in ('basic','balanced','dynamic'):
        assert smart_edit.build(timeline.build(h,p),h,style,'s')['emphasis'][0]['text']=='Bereits genehmigte Betonung.'


@pytest.mark.parametrize('composition',['close','detail','person','graphic','movement'])
def test_tight_or_high_motion_scene_has_restrained_camera(composition):
    h,p=handoffs(12);p['scenes'][0]['composition']=composition
    plan=smart_edit.build(timeline.build(h,p),h,'dynamic','s')
    assert all(seg['motion_effect'] in ('none','subtle_reframe') and seg['motion_strength']<=.012 for seg in plan['slots'][0]['segments'])


@pytest.mark.parametrize('hint,effect',[('slow_zoom','push_in'),('ken_burns','push_in'),('pan','pan_left')])
def test_explicit_scene_motion_matters(hint,effect):
    h,p=handoffs();p['scenes'][0]['motion']=hint
    assert smart_edit.build(timeline.build(h,p),h,'balanced','s')['slots'][0]['segments'][0]['motion_effect']==effect


@pytest.mark.parametrize('style',['balanced','dynamic'])
def test_smart_ass_exact_words_timing_safe_area_and_no_karaoke(style):
    h,p=handoffs();t=timeline.build(h,p);plan=smart_edit.build(t,h,style,'s')
    text,_,_=ass.create(h['subtitles'],t['scenes'],4,editing_style=style,emphasis=plan['emphasis'])
    assert h['subtitles'][0]['text'] in text
    assert '0:00:00.50,0:00:03.50,Subtitle' in text
    assert 'EmphasisCenter' in text and r'\fad(180,100)' in text and r'\t(0,180' in text
    assert r'\k' not in text and ',2,100,100,72,1' in text


def pixels(path,when,crop=None):
    vf=(crop+',' if crop else '')+'scale=192:108'
    r=subprocess.run([shutil.which('ffmpeg'),'-v','error','-ss',str(when),'-i',str(path),'-frames:v','1','-vf',vf,'-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True,shell=False)
    assert len(r.stdout)==192*108*3;return r.stdout


def difference(a,b):return sum(abs(x-y) for x,y in zip(a,b))/len(a)


def run_render(folder,h,p,media,style,*,burn=False,change=None):
    folder.mkdir();voice=folder.parent/'voice.wav'
    if not voice.exists():voice.write_bytes(wav(h['audio_duration']))
    t=timeline.build(h,p);plan=smart_edit.build(t,h,style,'source')
    if change:change(plan)
    runner=ProcessRunner();engine=FFmpegRenderProvider(tools.discover(),runner)
    result=engine.render({'temporary':folder,'timeline':t,'handoff':h,'options':options({'encoder':'cpu','editing_style':style,'subtitle_burned':burn}),
                          'smart_edit_plan':plan,'media':media,'audio':voice,'music':None})
    assert abs(result['metadata']['duration']-h['audio_duration'])<=.04
    assert result['metadata']['width']==1920 and result['metadata']['height']==1080
    assert not result['metadata']['warnings'],result['metadata']['warnings']
    return result,plan,runner


def test_real_stock_video_basic_vs_balanced_pixels_multiple_timestamps(tmp_path):
    clip=synthetic(tmp_path,'moving.mp4',['-f','lavfi','-i','testsrc2=s=640x360:r=30:d=4','-c:v','libx264'])
    before=clip.read_bytes();h,p=handoffs();h['subtitles']=[];media={'a'*32:{'path':clip,'type':'video'}}
    basic,_,_=run_render(tmp_path/'basic',h,p,media,'basic')
    smart,plan,_=run_render(tmp_path/'balanced',h,p,media,'balanced')
    for when in (.6,1.6,2.9):assert difference(pixels(basic['path'],when),pixels(smart['path'],when))>.8
    assert pixels(smart['path'],.6)!=pixels(smart['path'],1.6)  # moving video remains moving
    assert smart['metadata']['smart_edit_applied_summary']['motion_effects']==1 and clip.read_bytes()==before


def test_real_crossfade_has_blended_pixels_basic_is_clean_cut(tmp_path):
    red=synthetic(tmp_path,'red.mp4',['-f','lavfi','-i','color=c=red:s=320x240:r=30:d=4','-c:v','libx264'])
    blue=synthetic(tmp_path,'blue.mp4',['-f','lavfi','-i','color=c=blue:s=320x240:r=30:d=4','-c:v','libx264'])
    h,p=contract(4);h['subtitles']=[]
    for s in p['scenes']:s.update(transition='hard_cut',motion='none',overlay_text='',composition='wide',importance=50)
    media={'1':{'path':red,'type':'video'},'2':{'path':blue,'type':'video'}}
    basic,_,_=run_render(tmp_path/'basic',h,p,media,'basic')
    smart,_,_=run_render(tmp_path/'balanced',h,p,media,'balanced')
    a=pixels(basic['path'],1.65);b=pixels(smart['path'],1.65)
    assert sum(a[0::3])/len(a[0::3])<10 and sum(a[2::3])/len(a[2::3])>150
    assert 20<sum(b[0::3])/len(b[0::3])<220 and 20<sum(b[2::3])/len(b[2::3])<220
    assert smart['metadata']['smart_edit_applied_summary']['scene_transitions']==1


def test_real_emphasis_visible_exact_and_disappears(tmp_path):
    clip=synthetic(tmp_path,'blue.mp4',['-f','lavfi','-i','color=c=blue:s=320x240:r=30:d=4','-c:v','libx264'])
    h,p=handoffs();h['subtitles'][0].update(text='Im Jahr 2026',start=.5,end=2.5);media={'a'*32:{'path':clip,'type':'video'}}
    with_text,plan,_=run_render(tmp_path/'text',h,p,media,'balanced')
    def omit(plan):plan['emphasis']=[]
    without,_,_=run_render(tmp_path/'without',h,p,media,'balanced',change=omit)
    content='\n'.join(f.read_text() for f in (tmp_path/'text').glob('captions-*.ass'))
    assert plan['emphasis'][0]['text']=='Im Jahr 2026' and 'Im Jahr 2026' in content
    assert difference(pixels(with_text['path'],1.3,'crop=1920:540:0:0'),pixels(without['path'],1.3,'crop=1920:540:0:0'))>1
    assert difference(pixels(with_text['path'],3.1,'crop=1920:540:0:0'),pixels(without['path'],3.1,'crop=1920:540:0:0'))<.2
    assert with_text['metadata']['smart_edit_applied_summary']['emphasis_texts']==1


def test_real_long_video_internal_treatments_same_media_master_and_no_gaps(tmp_path):
    clip=synthetic(tmp_path,'long.mp4',['-f','lavfi','-i','nullsrc=s=640x360:r=30:d=12,geq=r=60+X/W*140:g=40+Y/H*150:b=90','-c:v','libx264'])
    before=clip.read_bytes();h,p=handoffs(12);h['subtitles']=[]
    result,plan,runner=run_render(tmp_path/'smart',h,p,{'a'*32:{'path':clip,'type':'video'}},'balanced')
    assert len(plan['slots'][0]['segments'])==3 and result['metadata']['smart_edit_applied_summary']['internal_edits']==2
    assert clip.read_bytes()==before and len(list((tmp_path/'smart').glob('core-*.mp4')))==1
    assert len([cmd for cmd in runner.commands if '-i' in cmd and str(clip) in cmd])==1
    for when in (.1,3.9,4.1,7.9,8.1,11.8):assert min(pixels(result['path'],when))>15
    assert difference(pixels(result['path'],3.9),pixels(result['path'],4.1))<.3
    assert difference(pixels(result['path'],.1),pixels(result['path'],2.4))>.3


def test_preview_styles_new_versions_and_legacy_fingerprint_survive(ready):
    st=ready;c=st['client'];service=c.app.state.rendering
    views=[c.get(url(st),params={'editing_style':style}).json()['smart_edit_plan'] for style in smart_edit.STYLES]
    assert len({v['fingerprint'] for v in views})==len(smart_edit.STYLES)
    assert c.get(url(st),params={'editing_style':'invalid'}).status_code==422
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu','editing_style':'basic'}).status_code==202
    first=await_job(st)['active'];old_path=st['root']/first['metadata']['output_local_path'];original=old_path.read_bytes()
    # Simulate an actual pre-9.5 record, preserving the old options/hash algorithm.
    legacy_options=dict(first['metadata']['options']);legacy_options.pop('editing_style')
    legacy_fingerprint=service._inputs(st['pid'],legacy_options)['fingerprint']
    with closing(service.projects._connection()) as db,db:
        meta=deepcopy(first['metadata']);meta['options']=legacy_options
        for k in ('editing_style','smart_edit_plan','smart_edit_summary','smart_edit_applied_summary'):meta.pop(k,None)
        preserved_path=old_path.with_name('video-v3.mp4');old_path.rename(preserved_path);old_path=preserved_path
        meta['output_local_path']='renders/video-v3.mp4'
        db.execute('UPDATE render_versions SET version=3,metadata_json=?,source_fingerprint=? WHERE id=?',(json.dumps(meta),legacy_fingerprint,first['id']))
    assert not c.get(url(st)).json()['active']['stale'] and c.get(url(st)+'/handoff').json()['ready']
    assert c.post(url(st)+f'/versions/{first["id"]}/activate').status_code==200
    assert c.post(url(st)+'/jobs',json={'encoder':'cpu','editing_style':'balanced'}).status_code==202
    state=await_job(st);assert state['job']['status']=='completed',state
    assert state['active']['version']==4 and state['active']['metadata']['editing_style']=='balanced'
    assert state['active']['metadata']['smart_edit_summary']['motion_effects']>0
    assert 'smart_edit_applied_summary' in state['active']['metadata'] and old_path.read_bytes()==original
    assert not next(v for v in state['versions'] if v['id']==first['id'])['stale']
    assert next(v for v in state['versions'] if v['id']==first['id'])['version']==3
    assert c.get(url(st)+f'/versions/{first["id"]}/video').content==original
    for name,data in st['originals'].items():assert (st['root']/name).read_bytes()==data
    with TestClient(create_app(st['storage']),headers=HEADERS) as other:
        assert other.get(url(st)).json()['active']['metadata']['editing_style']=='balanced'
    with closing(service.projects._connection()) as db:
        assert db.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='12'


@pytest.mark.parametrize('effect',list(smart_edit.MOTIONS.keys())[1:])
def test_every_camera_motion_has_real_pixels_and_stops_on_target_frame(tmp_path,effect):
    clip=synthetic(tmp_path,'grid.mp4',['-f','lavfi','-i','nullsrc=s=640x360:r=30:d=3,geq=r=80+60*sin(X/11):g=100+40*sin(Y/7):b=90','-c:v','libx264'])
    segment={'frames':60,'motion_effect':effect,'motion_strength':.012 if effect=='subtle_reframe' else .04}
    vf='scale=1920:1080'+smart_edit.camera(segment)+r',select=eq(n\,0)+eq(n\,59)+eq(n\,70)'
    result=subprocess.run([shutil.which('ffmpeg'),'-v','error','-i',str(clip),'-vf',vf,'-fps_mode','passthrough','-frames:v','3','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True,shell=False)
    size=1920*1080*3;assert len(result.stdout)==size*3
    a,b,c=(result.stdout[i*size:(i+1)*size] for i in range(3))
    assert difference(a,b)>.15
    assert difference(b,c)<.15
    assert min(b)>5  # positive source colors cover every edge


@pytest.mark.parametrize('stage,burn,code',[
 ('slot_render',False,'smart_motion_failed'),('crossfade',False,'smart_transition_failed'),
 ('subtitle_preflight',True,'emphasis_render_failed'),('final_assembly',True,'emphasis_render_failed'),('final_assembly',False,'emphasis_render_failed'),
])
def test_real_decorative_failure_falls_back_with_applied_counts(tmp_path,stage,burn,code):
    clip=synthetic(tmp_path,'clip.mp4',['-f','lavfi','-i','testsrc2=s=640x360:r=30:d=4','-c:v','libx264']);before=clip.read_bytes()
    h,p=handoffs();h['subtitles'][0]['text']='Im Jahr 2026'
    if stage=='crossfade':
        h,p=contract(4)
        for s in p['scenes']:s.update(overlay_text='',motion='none',transition='hard_cut',composition='wide',importance=50)
        h['subtitles']=[]
    t=timeline.build(h,p);edit=smart_edit.build(t,h,'balanced','source');folder=tmp_path/'job';folder.mkdir();voice=tmp_path/'voice.wav';voice.write_bytes(wav(4));diagnostics=[]
    class FailOnce(ProcessRunner):
        def __init__(self):super().__init__(diagnostic_callback=diagnostics.append);self.failed=False
        def run(self,args,cwd,*a,**context):
            if context.get('phase')==stage and not self.failed:
                self.failed=True
                if stage in ('subtitle_preflight','final_assembly'):
                    for file in Path(cwd).glob('captions-*.ass'):file.write_text('invalid local ASS fixture')
                else:
                    file=Path(cwd)/args[args.index('-/filter_complex')+1]
                    file.write_text(file.read_text().replace('perspective','nonexistent_motion') if stage=='slot_render' else file.read_text().replace('xfade','nonexistent_transition'))
            return super().run(args,cwd,*a,**context)
    runner=FailOnce();engine=FFmpegRenderProvider(tools.discover(),runner)
    result=engine.render({'temporary':folder,'timeline':t,'handoff':h,'smart_edit_plan':edit,'options':options({'encoder':'cpu','subtitle_burned':burn}),
        'media':{s['slot_id']:{'path':clip,'type':'video'} for s in t['slots']},'audio':voice,'music':None})
    assert runner.failed and code in [d['safe_error_code'] for d in diagnostics]
    applied=result['metadata']['smart_edit_applied_summary']
    if stage=='slot_render':assert applied['motion_effects']==0
    elif stage=='crossfade':assert applied['scene_transitions']==0
    else:assert applied['emphasis_texts']==0
    assert result['metadata']['warnings'] and result['metadata']['encoder_used']=='libx264' and clip.read_bytes()==before
    assert abs(result['metadata']['duration']-4)<=.04 and not (folder/'stderr.tmp').exists()


def test_smart_render_preserves_nvenc_encoder_selection_and_options():
    engine=FFmpegRenderProvider({'encoders':['h264_nvenc','libx264']},None)
    assert tools.select_encoder('auto',engine.tools)=='h264_nvenc'
    assert engine.codec('h264_nvenc')[:2]==['-c:v','h264_nvenc']
    h,p=owner_shape();edit=smart_edit.build(timeline.build(h,p),h,'dynamic','s')
    assert edit['summary']['motion_effects']>0 and options({})['encoder']=='auto'


def test_original_srt_vtt_and_subtitle_words_unchanged_in_profiles():
    h,p=handoffs();before=deepcopy(h)
    for style in ('balanced','dynamic'):
        edit=smart_edit.build(timeline.build(h,p),h,style,'s')
        content,_,_=ass.create(h['subtitles'],h['scenes'],4,editing_style=style,emphasis=edit['emphasis'])
        assert h==before and h['subtitles'][0]['text'] in content


def test_invalid_profile_and_extra_filter_fields_rejected():
    for value in ({'editing_style':'custom'},{'editing_style':123},{'filter_graph':'raw'}):
        with pytest.raises(RenderError):options(value)


def test_real_smart_video_stock_audio_never_reaches_narration(tmp_path):
    import array
    clip=synthetic(tmp_path,'noisy-stock.mp4',['-f','lavfi','-i','testsrc2=s=320x240:r=30:d=4',
        '-f','lavfi','-i','sine=frequency=1000:duration=4','-c:v','libx264','-c:a','aac','-shortest'])
    h,p=handoffs();h['subtitles']=[]
    result,_,_=run_render(tmp_path/'smart',h,p,{'a'*32:{'path':clip,'type':'video'}},'balanced')
    raw=subprocess.run([shutil.which('ffmpeg'),'-v','error','-i',str(result['path']),'-vn','-ac','1','-f','f32le','-'],capture_output=True,check=True,shell=False)
    samples=array.array('f',raw.stdout)
    assert len(samples)>=4*47000 and max(abs(v) for v in samples)<.00001
    assert result['metadata']['audio_codec']=='aac'


def test_decorative_diagnostics_only_controlled_fields_and_no_text_or_secrets():
    from app.rendering.diagnostics import diagnostic,safe_diagnostic
    sentinel='secret-owned-key-and-private-url'
    for code,phase in [('smart_motion_failed','smart_motion'),('smart_transition_failed','smart_transition'),('emphasis_render_failed','emphasis_render')]:
        d=diagnostic(code,phase=phase,encoder='h264_nvenc',slot_index=2,slot_count=37,slot_id='a'*32)
        assert d['safe_error_code']==code and d['phase']==phase
        assert safe_diagnostic({**d,'raw_stderr':sentinel,'script_text':sentinel,'Authorization':sentinel})==d
        assert sentinel not in json.dumps(d) and 'Medya 3/37' in d['phase_label']
