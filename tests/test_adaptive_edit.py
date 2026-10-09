"""Exact source plans plus real local FFmpeg layouts, not command-only tests."""
from copy import deepcopy
import json
import pytest
from app.rendering import smart_edit,timeline,adaptive
from app.rendering.models import options,RenderError
from test_smart_edit import handoffs,owner_shape,run_render,pixels,difference
from test_rendering import synthetic,ready,url,await_job


def content(text,**meta):
    h,p=handoffs(12,text);h['subtitles']=[{'index':1,'start':2,'end':4.5,'text':text}];p['scenes'][0].update(importance=80,**meta)
    return h,p

@pytest.mark.parametrize('text,meta,expected',[
 ('Das Bermuda Triangle liegt im Atlantik.',{'location':'Bermuda Triangle'},'location_card'),
 ('Das Flugzeug nutzt 70 Prozent weniger Energie.',{},'big_number'),
 ('1930 begann die Reise. 1940 endete die Reise.',{},'timeline_card'),
 ('Der Pilot prüft Instrumente. Die Crew kontrolliert Anzeigen.',{},'fact_card'),
])
def test_content_signals_not_topic_templates(text,meta,expected):
    h,p=content(text,**meta);before=deepcopy((h,p));t=timeline.build(h,p)
    plan=smart_edit.build(t,h,'adaptive','fixed',media_details={'a'*32:{'description':'Bermuda Triangle map'}})
    assert plan['slots'][0]['layout']==expected
    assert (h,p)==before
    assert all(value in text for item in plan['slots'] for value in item['texts'])
    assert plan['summary']['graphic_seconds']<=h['audio_duration']*.3
    assert plan==smart_edit.build(t,h,'adaptive','fixed',media_details={'a'*32:{'description':'Bermuda Triangle map'}})


def test_seed_changes_only_compatible_treatment_not_words_or_timing():
    h,p=content('Eine wichtige Aussage über das Flugzeug.');t=timeline.build(h,p)
    plans=[smart_edit.build(t,h,'adaptive','fixed',seed=str(i)) for i in range(8)]
    assert len({p['slots'][0]['layout'] for p in plans})>=2
    assert plans[1]['slots'][0]['layout']!=plans[2]['slots'][0]['layout']
    assert len({json.dumps([(s['texts'],s['layout_window'],s['start'],s['end']) for s in p['slots']]) for p in plans})==1
    assert plans[1]==smart_edit.build(t,h,'adaptive','fixed',seed='1')


def test_no_suitable_short_cues_falls_back_to_broll():
    h,p=content(' '.join(['Langes']*100));plan=smart_edit.build(timeline.build(h,p),h,'adaptive','s')
    assert plan['slots'][0]['layout']=='full_broll'

@pytest.mark.parametrize('value',[{'edit_variation_seed':'../bad'},{'edit_variation_seed':''},{'subtitle_display':'other'}])
def test_options_safe(value):
    with pytest.raises(RenderError):options(value)


def test_adaptive_default_and_legacy_explicit_subtitle_choice():
    assert options({})['editing_style']=='adaptive'
    assert options({'editing_style':'balanced','subtitle_burned':True})['subtitle_display']=='full'
    assert options({'subtitle_burned':False})['subtitle_display']=='emphasis'  # Legacy bottom-caption checkbox keeps existing overlays.


@pytest.mark.parametrize('mode,burned',[('full',True),('emphasis',False),('none',False)])
def test_explicit_subtitle_mode_canonicalizes_legacy_checkbox(mode,burned):
    assert options({'subtitle_display':mode})['subtitle_burned'] is burned
    assert options({'subtitle_display':mode,'subtitle_burned':not burned})['subtitle_burned'] is burned


def test_default_preview_matches_render_and_encoder_does_not_change_editorial_seed(ready):
    c=ready['client'];service=c.app.state.rendering
    preview=c.get(url(ready),params={'editing_style':'adaptive','subtitle_display':'emphasis'}).json()['smart_edit_plan']
    payload={'editing_style':'adaptive','encoder':'auto','edit_variation_seed':None,'subtitle_display':'emphasis','subtitle_burned':False}
    actual=service._inputs(ready['pid'],options(payload))['smart_edit_plan']
    assert preview==actual
    cpu=service._inputs(ready['pid'],options({**payload,'encoder':'cpu'}))['smart_edit_plan']
    assert cpu['edit_variation_seed']==actual['edit_variation_seed']
    assert {k:v for k,v in cpu.items() if k not in ('fingerprint','source_fingerprint')}=={k:v for k,v in actual.items() if k not in ('fingerprint','source_fingerprint')}

@pytest.mark.parametrize('layout',['full_broll','split_media_text','fact_card','big_number','timeline_card','dual_media','minimal_title','quote_emphasis','location_card'])
def test_real_ffmpeg_layout_pixels_timing_format_and_source_safety(tmp_path,layout):
    # Exercise each renderer independently from planner selection.
    text='1930 begann die Reise. 1940 endete die Reise.'
    h,p=content(text);clip=synthetic(tmp_path,'source.mp4',['-f','lavfi','-i','color=c=blue:s=640x360:r=30:d=12','-c:v','libx264'])
    second=synthetic(tmp_path,'second.mp4',['-f','lavfi','-i','color=c=red:s=640x360:r=30:d=12','-c:v','libx264'])
    originals=[clip.read_bytes(),second.read_bytes()]
    media={'a'*32:{'path':clip,'type':'video'},'second':{'path':second,'type':'video'}}
    def select(plan):
        item=plan['slots'][0];item.update(layout=layout,texts=[text] if layout!='fact_card' else ['1930 begann die Reise.','1940 endete die Reise.'],number='1930',layout_window={'start':2,'end':4.5},secondary_slot_id='second' if layout=='dual_media' else None)
    result,plan,_=run_render(tmp_path/'job',h,p,media,'adaptive',change=select)
    md=result['metadata'];assert md['fps']==30 and abs(md['duration']-12)<.04
    assert md['smart_edit_applied_summary']['layouts'][layout]==1
    assert md['smart_edit_applied_summary']['layout_failures']==0
    before=pixels(result['path'],1);during=pixels(result['path'],3);after=pixels(result['path'],6)
    assert sum(before)/len(before)>30 and sum(during)/len(during)>10 and sum(after)/len(after)>30
    assert difference(before,after)<.5
    if layout!='full_broll':assert difference(before,during)>5
    assert [clip.read_bytes(),second.read_bytes()]==originals
    if layout!='full_broll':
        content_file=(tmp_path/'job'/'layout-0.ass').read_text()
        assert '0:00:02.00,0:00:04.50' in content_file and '\\fad(150,150)' in content_file


def test_local_preview_variation_does_not_call_providers_and_persists_in_version(ready):
    st=ready;c=st['client']
    views=[c.get(url(st),params={'editing_style':'adaptive','edit_variation_seed':str(i),'subtitle_display':'emphasis'}).json() for i in (1,2)]
    assert views[0]['smart_edit_plan']['edit_variation_seed']=='1'
    assert views[1]['smart_edit_plan']['edit_variation_seed']=='2'
    assert c.post(url(st)+'/jobs',json={'editing_style':'adaptive','encoder':'cpu','edit_variation_seed':'2','subtitle_display':'emphasis'}).status_code==202
    state=await_job(st);assert state['job']['status']=='completed'
    assert state['active']['metadata']['options']['edit_variation_seed']=='2'


def test_approved_overlay_and_no_subtitle_mode():
    h,p=content('Eine kurze neutrale Aussage.');h['subtitles']=[];p['scenes'][0]['overlay_text']='Bereits genehmigte Betonung.'
    plan=smart_edit.build(timeline.build(h,p),h,'adaptive','fixed')
    assert plan['slots'][0]['texts']==['Bereits genehmigte Betonung.']
    assert plan['slots'][0]['text_provenance']['source']=='scene_overlay'
    without=smart_edit.build(timeline.build(h,p),h,'adaptive','fixed',subtitle_mode='none')
    assert not without['emphasis'] and all(not s['texts'] for s in without['slots'])


def test_real_decorative_failure_uses_same_broll_and_duration(tmp_path):
    from app.rendering import tools
    from app.rendering.engine import FFmpegRenderProvider
    from app.rendering.runner import ProcessRunner
    from test_subtitles import wav
    h,p=content('Das Flugzeug nutzt 70 Prozent weniger Energie.');t=timeline.build(h,p);edit=smart_edit.build(t,h,'adaptive','s')
    clip=synthetic(tmp_path,'clip.mp4',['-f','lavfi','-i','color=c=blue:s=640x360:r=30:d=12','-c:v','libx264'])
    folder=tmp_path/'fallback';folder.mkdir();voice=tmp_path/'voice.wav';voice.write_bytes(wav(12))
    class FailLayout(ProcessRunner):
        failed=False
        def run(self,args,cwd,*pos,**kw):
            if kw.get('phase')=='slot_render' and not self.failed:
                self.failed=True;raise RenderError('render_failed','Güvenli sentetik dekoratif hata.')
            return super().run(args,cwd,*pos,**kw)
    runner=FailLayout();result=FFmpegRenderProvider(tools.discover(),runner).render({'temporary':folder,'timeline':t,'handoff':h,'smart_edit_plan':edit,'options':options({'encoder':'cpu','editing_style':'adaptive','subtitle_display':'emphasis'}),'media':{'a'*32:{'path':clip,'type':'video'}},'audio':voice,'music':None})
    applied=result['metadata']['smart_edit_applied_summary'];assert runner.failed and applied['layout_failures']==1
    assert applied['layouts']['full_broll']==1 and applied['layouts']['big_number']==0
    assert applied['emphasis_texts']==0 and abs(result['metadata']['duration']-12)<.04
    assert difference(pixels(result['path'],1),pixels(result['path'],3))<.5


def test_real_1080p_frame_continuity_and_subtitle_modes(tmp_path):
    import subprocess,shutil
    from app.rendering import tools
    from app.rendering.engine import FFmpegRenderProvider
    from app.rendering.runner import ProcessRunner
    from test_subtitles import wav
    text='Das Flugzeug nutzt 70 Prozent weniger Energie.';h,p=content(text);t=timeline.build(h,p)
    clip=synthetic(tmp_path,'clip.mp4',['-f','lavfi','-i','color=c=blue:s=640x360:r=30:d=12','-c:v','libx264']);voice=tmp_path/'voice.wav';voice.write_bytes(wav(12));outputs={}
    for mode in ('full','emphasis','none'):
        folder=tmp_path/mode;folder.mkdir();edit=smart_edit.build(t,h,'adaptive','s',subtitle_mode=mode)
        outputs[mode]=FFmpegRenderProvider(tools.discover(),ProcessRunner()).render({'temporary':folder,'timeline':t,'handoff':h,'smart_edit_plan':edit,'options':options({'encoder':'cpu','editing_style':'adaptive','subtitle_display':mode}),'media':{'a'*32:{'path':clip,'type':'video'}},'audio':voice,'music':None})
        data=subprocess.run([shutil.which('ffprobe'),'-v','error','-select_streams','v','-show_entries','frame=best_effort_timestamp_time','-of','json',str(outputs[mode]['path'])],capture_output=True,check=True).stdout
        frames=[float(f['best_effort_timestamp_time']) for f in json.loads(data)['frames']]
        assert len(frames)==360 and all(abs(b-a-1/30)<.000002 for a,b in zip(frames,frames[1:]))
    crop='crop=1920:180:0:900'
    assert difference(pixels(outputs['full']['path'],3,crop),pixels(outputs['emphasis']['path'],3,crop))>1
    assert difference(pixels(outputs['emphasis']['path'],3,crop),pixels(outputs['none']['path'],3,crop))<.5
    assert difference(pixels(outputs['emphasis']['path'],3),pixels(outputs['none']['path'],3))>5
    assert difference(pixels(outputs['emphasis']['path'],6),pixels(outputs['none']['path'],6))<.5


def test_cue_crossing_stock_boundary_keeps_exact_clause_and_master_timing():
    h,p=content('Der Pilot prüft Instrumente.');h['subtitles']=[{'index':7,'start':0,'end':7,'text':'Der Pilot prüft Instrumente. Die Crew bleibt ruhig.'}]
    # Visual beat lies inside a longer existing cue. No word timestamps guessed.
    t=timeline.build(h,p);plan=smart_edit.build(t,h,'adaptive','fixed')
    item=plan['slots'][0];assert item['texts']==['Der Pilot prüft Instrumente.']
    assert item['text_provenance']['source']=='subtitle_clause'
    assert item['text_provenance']['cue_index']==7
    assert 0<=item['layout_window']['start']<item['layout_window']['end']<=7
    assert item['start']==0 and item['end']==12


def test_multiple_semantic_scenes_have_content_driven_variety_and_broll_majority():
    h,p=owner_shape()
    for i,(scene,meta) in enumerate(zip(h['scenes'],p['scenes'])):
        texts=['Ein Pilot prüft die Instrumente.','Das Flugzeug nutzt 70 Prozent weniger Energie.','1930 begann die Reise. 1940 endete die Reise.']
        text=texts[i%3];scene['narration_text']=meta['narration_text']=text;meta['importance']=80
    h['subtitles']=[{'index':i+1,'start':s['start']+.3,'end':s['end']-.3,'text':s['narration_text']} for i,s in enumerate(h['scenes'])]
    plan=smart_edit.build(timeline.build(h,p),h,'adaptive','fixed')
    kinds=[s['layout'] for s in plan['slots']];assert len(set(kinds))>=4
    assert .1<=plan['summary']['graphic_seconds']/193<=.3
    assert all(not (a==b==c!='full_broll') for a,b,c in zip(kinds,kinds[1:],kinds[2:]))
    assert all(text in p['scenes'][next(i for i,m in enumerate(p['scenes']) if m['scene_id']==s['scene_id'])]['narration_text'] for s in plan['slots'] for text in s['texts'])


@pytest.mark.parametrize('text',['1930 und 1940 sind Jahreszahlen.','1940 endete die Reise. 1930 begann die Reise.','1930 begann die Reise. 1930 begann die Reise.'])
def test_years_without_distinct_ordered_facts_do_not_create_timeline(text):
    h,p=content(text);plan=smart_edit.build(timeline.build(h,p),h,'adaptive','s')
    assert plan['slots'][0]['layout']!='timeline_card'


def test_split_orientation_alternates_and_broll_resets_layout_repetition():
    h,p=owner_shape();text='Der erfahrene Pilot kontrolliert alle Instrumente und die Crew beobachtet wichtige Anzeigen.'
    for scene,meta in zip(h['scenes'],p['scenes']):scene['narration_text']=meta['narration_text']=text;meta['importance']=80
    h['subtitles']=[{'index':i+1,'start':s['start']+.3,'end':s['end']-.3,'text':text} for i,s in enumerate(h['scenes'])]
    plan=smart_edit.build(timeline.build(h,p),h,'adaptive','source',seed='1')
    splits=[s for s in plan['slots'] if s['layout']=='split_media_text']
    assert len(splits)>=4  # A later B-roll beat must unblock the same valid layout.
    assert all(a['orientation']!=b['orientation'] for a,b in zip(splits,splits[1:]))


def test_adaptive_broll_transitions_vary_without_changing_master_clock():
    h,p=owner_shape();h['subtitles']=[]
    for m in p['scenes']:m['transition']='crossfade'
    t=timeline.build(h,p);plan=smart_edit.build(t,h,'adaptive','s',seed='1')
    transitions=[s['transition_out'] for s in plan['slots'] if s['transition_out']!='hard_cut']
    assert len(set(transitions))>=2
    assert all(a!=b for a,b in zip(transitions,transitions[1:]))
    assert [(s['start'],s['end']) for s in t['slots']]==[(s['start'],s['end']) for s in plan['slots']]


@pytest.mark.parametrize('style',['basic','balanced','dynamic'])
def test_no_subtitle_mode_has_truthful_zero_emphasis_plan(style):
    h,p=content('Eine kurze Aussage.');p['scenes'][0]['overlay_text']='Genehmigte Betonung.'
    plan=smart_edit.build(timeline.build(h,p),h,style,'s',subtitle_mode='none')
    assert not plan['emphasis'] and plan['summary']['emphasis_texts']==0
    assert plan['fingerprint']==smart_edit.digest({k:v for k,v in plan.items() if k!='fingerprint'})


def test_real_basic_no_subtitle_mode_mutes_existing_overlay(tmp_path):
    from app.rendering import tools
    from app.rendering.engine import FFmpegRenderProvider
    from app.rendering.runner import ProcessRunner
    from test_subtitles import wav
    h,p=content('Eine kurze Aussage.');p['scenes'][0]['overlay_text']='Genehmigte Betonung.';t=timeline.build(h,p)
    clip=synthetic(tmp_path,'clip.mp4',['-f','lavfi','-i','color=c=blue:s=640x360:r=30:d=12','-c:v','libx264']);voice=tmp_path/'voice.wav';voice.write_bytes(wav(12));folder=tmp_path/'job';folder.mkdir()
    result=FFmpegRenderProvider(tools.discover(),ProcessRunner()).render({'temporary':folder,'timeline':t,'handoff':h,'smart_edit_plan':smart_edit.build(t,h,'basic','s',subtitle_mode='none'),'options':options({'encoder':'cpu','editing_style':'basic','subtitle_display':'none'}),'media':{'a'*32:{'path':clip,'type':'video'}},'audio':voice,'music':None})
    assert not list(folder.glob('captions-*.ass'))
    assert result['metadata']['smart_edit_applied_summary']['emphasis_texts']==0
    assert difference(pixels(result['path'],1),pixels(result['path'],4))<.5
