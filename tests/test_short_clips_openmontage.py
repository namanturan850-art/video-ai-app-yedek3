"""Part 9.7 contracts; external tools mocked here, real smoke is separate.

Live provider/OpenMontage test must be run by owner on Windows.
"""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.rendering import smart_edit,timeline
from app.rendering.models import options,RenderError
from app.rendering.windows import source_window
from app.stock.models import make_slots,rejection_reason,StockError
from app.stock.pacing import rebuild
from app.stock import relevance
from app.integrations.openmontage.bridge import Bridge,PIN,OFFICIAL,trusted_root,child_env
from app.integrations.openmontage import media as external_media
from test_stock_media import media,stock_studio,view,start,production_studio,studio
from test_rendering import ready,url
from test_smart_edit import owner_shape


def scene(duration=193):
    return {'scene_id':'a','start_estimate':0,'end_estimate':duration,'importance':50,
        'narration_text':'Ein wichtiger Punkt. Noch eine genaue Erklärung. Ein ruhiger Abschluss.',
        'visual_intent':'electric cars','primary_stock_query':'electric cars road',
        'alternative_stock_queries':['electric cars charging','electric car connector'],
        'preferred_media_type':'stock_video','composition':'wide'}


def test_193_seconds_short_varied_beats_are_contiguous_read_only():
    s=scene();old=deepcopy(s);slots=make_slots(s)
    assert 45<=len(slots)<=65 and len(slots)>37 and s==old
    assert 3<=193/len(slots)<=4.2
    assert len({v['duration'] for v in slots})>3
    assert all(2.5<=v['duration']<=5.5 for v in slots)
    assert slots[0]['estimated_start']==0 and slots[-1]['estimated_end']==193
    assert all(a['estimated_end']==b['estimated_start'] for a,b in zip(slots,slots[1:]))
    assert sum(s['duration'] for s in slots)==pytest.approx(193,abs=.02)


def test_owner_37_slot_shape_subdivides_without_rewriting_master_or_reusing_assets():
    h,p=owner_shape();before=deepcopy((h,p));scenes=[];slots=[]
    for source in h['scenes']:
        scenes.append({**scene(source['end']-source['start']),**p['scenes'][len(scenes)],
            'start_estimate':source['start'],'end_estimate':source['end']})
    for old in h['stock_slots']:
        slot=make_slots({**scenes[next(i for i,s in enumerate(scenes) if s['scene_id']==old['scene_id'])],
            'start_estimate':old['start'],'end_estimate':old['end']})[0]
        slot.update(slot_id=old['slot_id'],estimated_start=old['start'],estimated_end=old['end'],duration=old['duration'],
            selected_media={'provider':'pixabay','media_id':old['slot_id'],'media_type':'video'},status='complete')
        slots.append(slot)
    state={'slots':slots};rebuild(state,{'scenes':scenes},h)
    assert len(state['slots'])==48
    assert sum(s['duration'] for s in state['slots'])==pytest.approx(193,abs=.02)
    assert max(s['duration'] for s in state['slots'])<=5.5
    selected=[s['selected_media']['media_id'] for s in state['slots'] if s['selected_media']]
    assert len(selected)==len(set(selected))==37
    assert (h,p)==before
    saved=deepcopy(state);rebuild(state,{'scenes':scenes},h);assert state==saved


def test_explicit_repace_preserves_locked_slot_and_old_selection_once():
    s=scene(22);a=make_slots(s)[0];a.update(estimated_end=22,duration=22,selected_media={'media_id':'old'},locked=True)
    state={'slots':[a]};old=deepcopy(a);rebuild(state,{'scenes':[s]})
    assert state['slots']==[old]
    state['slots'][0]['locked']=False;state.pop('short_pacing_version');rebuild(state,{'scenes':[s]})
    assert len(state['slots'])>1 and sum(bool(x['selected_media']) for x in state['slots'])==1


@pytest.mark.parametrize('width,height,reason',[(1080,1920,'orientation'),(1080,1080,'orientation'),(1279,720,'resolution'),(1920,1080,None)])
def test_landscape_gate(width,height,reason):
    assert rejection_reason(media(width=width,height=height),{'duration':3.7,'pacing_version':1},technical_only=True)==reason


def test_short_source_coverage_strict_new_slots_long_relevant_source_allowed():
    slot={'duration':3.7,'pacing_version':1}
    assert rejection_reason(media(duration=3),slot,technical_only=True)=='duration'
    assert rejection_reason(media(duration=22),slot,technical_only=True) is None
    assert rejection_reason(media(duration=3),{'duration':3.7},technical_only=True) is None  # legacy tolerance


def test_16_9_short_source_preferred_among_equally_relevant_candidates():
    s=make_slots(scene(4))[0];profile=relevance.profile(scene(4),s)
    candidates=[relevance.annotate(m,profile,1,'electric cars road') for m in [media('long',duration=22),media('short',duration=7)]]
    assert relevance.choose(candidates,set(),s)['media_id']=='short'
    candidates=[relevance.annotate(m,profile,1,'electric cars road') for m in [media('wide',width=1920,height=800),media('normal')]]
    assert relevance.choose(candidates,set(),s)['media_id']=='normal'


@pytest.mark.parametrize('duration',[4,7,12,22,30])
def test_source_windows_repeatable_bounded_and_no_source_mutation(duration):
    x=source_window(duration,3.7,'media-slot');assert x==source_window(duration,3.7,'media-slot')
    assert 0<=x['source_in']<x['source_out']<=duration
    assert x['source_out']-x['source_in']==pytest.approx(3.7,abs=.000001)
    assert x['used_duration']==3.7 and x['source_duration']==duration
    if duration>=7:assert x['source_in']>.35 and x!=source_window(duration,3.7,'other-slot')


def test_complete_native_defaults_and_missing_optional_engine(ready):
    c=ready['client'];state=c.get(url(ready)).json()
    assert state['ready'] and all(state['readiness'][k] for k in ('narration_ready','subtitles_ready','stock_ready','ffmpeg_ready'))
    assert state['readiness']['blockers']==[] and not state['openmontage']['ready']
    for style,seed,mode in [('adaptive','1','emphasis'),('dynamic','2','none'),('basic','3','full')]:
        changed=c.get(url(ready),params={'editing_style':style,'edit_variation_seed':seed,'subtitle_display':mode}).json()
        assert changed['ready'] and changed['readiness']['blockers']==[]
    external=c.get(url(ready),params={'montage_engine':'openmontage'}).json()
    assert not external['ready'] and external['readiness']['blockers'][0]['code']=='openmontage_missing'
    r=c.post(url(ready)+'/jobs',json={'montage_engine':'openmontage'})
    assert r.status_code==409 and r.json()['category']=='openmontage_unavailable'
    assert not c.get(url(ready)).json()['versions']  # never silently fall back


def test_unresolved_readiness_partial_preview_then_ready_after_completion(ready):
    c=ready['client'];p=c.app.state.projects
    with closing(p._connection()) as db,db:
        row=db.execute('SELECT plan_id,state_json FROM stock_plans WHERE project_id=?',(ready['pid'],)).fetchone()
        state=json.loads(row['state_json']);original=deepcopy(state);state['slots'][0].update(status='ai_needed',selected_media=None)
        db.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(state),ready['pid']))
    result=c.get(url(ready)).json();assert not result['ready']
    assert result['readiness']['unresolved_stock_slots']==1
    assert result['readiness']['narration_ready'] and result['readiness']['subtitles_ready']
    assert result['smart_edit_plan']['estimated']
    assert any(b['code']=='stock_unresolved' for b in result['readiness']['blockers'])
    changed=c.get(url(ready),params={'edit_variation_seed':'new'}).json()
    assert changed['smart_edit_plan']['estimated'] and changed['smart_edit_plan']['fingerprint']!=result['smart_edit_plan']['fingerprint']
    assert c.post(url(ready)+'/jobs',json={}).status_code==409
    with closing(p._connection()) as db,db:db.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?',(json.dumps(original),ready['pid']))
    assert c.get(url(ready)).json()['ready']
    assert all((ready['root']/name).read_bytes()==data for name,data in ready['originals'].items())


def test_missing_file_precise_blocker(ready):
    c=ready['client'];h=c.app.state.subtitles.handoff(ready['pid']);path=ready['root']/h['stock_slots'][0]['selected_media_local_identity']['local_path']
    original=path.read_bytes();path.unlink()
    state=c.get(url(ready)).json();assert not state['ready'] and state['readiness']['missing_files']==1
    assert 'media_file_missing' in {b['code'] for b in state['readiness']['blockers']}
    assert str(ready['root']) not in json.dumps(state['readiness'])
    path.write_bytes(original);assert c.get(url(ready)).json()['ready']


@pytest.mark.parametrize('bad',['../tool','https://host/tool','//host/share','\\\\host\\share'])
def test_external_root_rejects_remote_relative_and_shell_injection(bad):
    with pytest.raises(RenderError):trusted_root(bad)


def test_external_symlink_rejected(tmp_path):
    (tmp_path/'alias').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(RenderError):trusted_root(str(tmp_path/'alias'))


def test_config_persistence_safe_types_and_no_keys(studio):
    c=studio[0];bridge=c.app.state.rendering.openmontage
    key='test-external-secret-9912';c.app.state.settings.save('pexels',{'api_key':key})
    payload={'media_search':True,'reuse_stock_keys':False,'matching':'fast'}
    r=c.post('/api/settings/openmontage',headers={'X-AI-Video-Studio':'settings'},json=payload)
    assert r.status_code==200 and r.json()['media_search']
    assert Bridge(c.app.state.projects,c.app.state.settings).config()=={**payload,'root':''}
    assert key not in bridge.config_file.read_text() and key not in r.text
    for payload in ({'root':'https://bad/tool'},{'media_search':'yes'},{'matching':'shell'},{'api_key':key}):
        assert c.post('/api/settings/openmontage',headers={'X-AI-Video-Studio':'settings'},json=payload).status_code==422


def test_child_env_excludes_ambient_provider_keys(monkeypatch,tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY','ambient-secret');monkeypatch.setenv('PEXELS_API_KEY','ambient-stock-secret')
    assert 'OPENAI_API_KEY' not in child_env(tmp_path) and 'PEXELS_API_KEY' not in child_env(tmp_path)
    assert child_env(tmp_path,{'PEXELS_API_KEY':'explicit'})['PEXELS_API_KEY']=='explicit'


def test_external_process_contract_runtime_key_only_no_disk_or_argv(studio,monkeypatch,tmp_path):
    bridge=studio[0].app.state.rendering.openmontage;bridge.save({'root':str(tmp_path/'engine'),'reuse_stock_keys':True})
    key='runtime-only-key-1239';bridge.settings.save('pexels',{'api_key':key})
    monkeypatch.setattr(bridge,'status',lambda *a:{'ready':True})
    calls=[]
    class Runner:
        def run(self,args,cwd,**kw):
            calls.append((args,kw));payload=json.loads(Path(args[-1]).read_text());assert key not in json.dumps(payload)
            Path(payload['result_path']).write_text(json.dumps({'success':True,'data':{'clips':[]}}))
    assert bridge.call('search',{'queries':[{'query':'electric cars'}]},tmp_path,Runner())=={'clips':[]}
    assert calls[0][1]['env']['PEXELS_API_KEY']==key and key not in json.dumps(calls[0][0])
    assert not list(tmp_path.glob('om-*.json'))
    bridge.call('trim',{'input_path':'local'},tmp_path,Runner())
    assert 'PEXELS_API_KEY' not in calls[-1][1]['env']
    assert key not in bridge.config_file.read_text()


def test_external_failure_returns_safe_message_no_fallback(studio,monkeypatch,tmp_path):
    b=studio[0].app.state.rendering.openmontage;monkeypatch.setattr(b,'status',lambda *a:{'ready':True})
    class Broken:
        def run(self,args,cwd,**kw):raise RenderError('unexpected','Authorization secret signed URL')
    with pytest.raises(RenderError) as e:b.call('trim',{},tmp_path,Broken())
    assert e.value.category=='openmontage_failed' and 'Authorization' not in str(e.value)


def test_direct_search_filters_verified_external_contract(studio,monkeypatch):
    b=studio[0].app.state.rendering.openmontage;b.save({'media_search':True})
    monkeypatch.setattr(b,'status',lambda *a:{'ready':True,'semantic_ready':False})
    monkeypatch.setattr(external_media,'discover',lambda:{'ffprobe':'trusted-probe'})
    calls=[]
    def call(operation,inputs,folder):calls.append((operation,inputs));return {'clips':[]}
    monkeypatch.setattr(b,'call',call)
    assert external_media.search(b,studio[1]['id'],'electric cars')==[]
    op,inputs=calls[0];assert op=='search' and inputs['clips_per_query']==4
    assert inputs['filters']=={'orientation':'landscape','min_duration':3,'max_duration':12,'min_width':1280}
    assert not list((b.projects._path(studio[1]['id'])/'stock').glob('.om-search-*'))


def test_semantic_missing_is_explicit_and_no_heavy_auto_install(studio,monkeypatch):
    b=studio[0].app.state.rendering.openmontage;b.save({'media_search':True,'matching':'semantic'})
    monkeypatch.setattr(b,'status',lambda *a:{'ready':True,'semantic_ready':False})
    with pytest.raises(StockError,match='CLIP'):external_media.search(b,studio[1]['id'],'cars')


def test_real_local_import_and_cache_have_no_external_paths_or_credentials(studio,monkeypatch):
    from test_rendering import synthetic
    from app.stock.download import Downloader,asset_path
    b=studio[0].app.state.rendering.openmontage;b.save({'media_search':True})
    monkeypatch.setattr(b,'status',lambda *a:{'ready':True,'semantic_ready':False})
    def search(operation,inputs,folder):
        path=synthetic(folder,'download.mp4',['-f','lavfi','-i','color=c=blue:s=1280x720:r=30:d=4','-c:v','libx264'])
        return {'clips':[{'path':str(path),'source':'archive_org','source_id':'free-film','source_url':'https://archive.org/details/free-film',
                         'creator':'Archive creator','license':'Verify source license','source_tags':'electric cars road','kind':'video'}]}
    monkeypatch.setattr(b,'call',search)
    candidates=external_media.search(b,studio[1]['id'],'electric cars road')
    assert len(candidates)==1
    candidate=candidates[0];assert candidate['provider']=='openmontage' and candidate['width']==1280 and candidate['duration']==4
    assert candidate['source_metadata']['source']=='archive_org'
    assert candidate['description']=='electric cars road'
    assert not any(k in candidate for k in ('path','headers','api_key','Authorization'))
    assert str(b.projects.storage) not in json.dumps(candidate)
    saved=Downloader(b.projects).download(studio[1]['id'],candidate)
    assert asset_path(b.projects,studio[1]['id'],saved).is_file() and saved['sha256']==candidate['sha256']
    assert not list((b.projects._path(studio[1]['id'])/'stock').glob('.om-search-*'))


def test_explicit_external_search_repairs_missing_or_corrupt_import_without_deleting_old_files(studio,monkeypatch,tmp_path):
    from test_rendering import synthetic
    from app.stock.download import Downloader,asset_path
    client,project=studio[:2];stock=client.app.state.stock;b=stock.openmontage;pid=project['id']
    b.save({'media_search':True});monkeypatch.setattr(b,'status',lambda *a:{'ready':True,'semantic_ready':False})
    source=synthetic(tmp_path,'source.mp4',['-f','lavfi','-i','color=c=blue:s=1280x720:r=30:d=4','-c:v','libx264'])
    calls=[]
    def search(operation,inputs,folder):
        import shutil
        calls.append(operation);path=folder/'download.mp4';shutil.copyfile(source,path)
        return {'clips':[{'path':str(path),'source':'archive_org','source_id':'free-film',
                         'source_url':'https://archive.org/details/free-film','source_tags':'electric cars road'}]}
    monkeypatch.setattr(b,'call',search)
    results,_,cached=stock._cache_search(pid,'openmontage','video','electric cars road')
    assert not cached and calls==['search']
    assert stock._cache_search(pid,'openmontage','video','electric cars road')[2]
    saved=Downloader(b.projects).download(pid,results[0]);old=asset_path(b.projects,pid,saved)
    # Same-sized corruption is detected by SHA, not merely existence/size.
    original=old.read_bytes();old.write_bytes(b'X'*len(original))
    results,_,cached=stock._cache_search(pid,'openmontage','video','electric cars road')
    assert not cached and len(calls)==2 and old.read_bytes()==b'X'*len(original)
    restored=asset_path(b.projects,pid,Downloader(b.projects).download(pid,results[0]))
    assert restored!=old and restored.read_bytes()==original
    restored.unlink()
    results,_,cached=stock._cache_search(pid,'openmontage','video','electric cars road')
    assert not cached and len(calls)==3 and old.is_file()
    assert asset_path(b.projects,pid,Downloader(b.projects).download(pid,results[0])).read_bytes()==original
    assert stock._cache_search(pid,'openmontage','video','electric cars road')[2] and len(calls)==3


def test_paid_or_private_source_urls_rejected():
    for value,source in [('https://example.com/a','paid'),('https://archive.org/a?token=secret','archive_org'),('https://user:pw@archive.org/a','archive_org')]:
        with pytest.raises(StockError):external_media.source_page(value,source)
    assert external_media.source_page('https://archive.org/details/public-film','archive_org')


def test_new_subslots_automatically_get_distinct_videos(stock_studio):
    state=start(stock_studio);selected=[s['selected_media'] for s in state['slots']]
    assert all(m and m['media_type']=='video' and m['width']>m['height'] for m in selected)
    assert len({m['sha256'] for m in selected})==len(selected)
    assert all(a['media_id']!=b['media_id'] for a,b in zip(selected,selected[1:]))
    assert state['media_mix']['video_ratio_percent']==100  # soft target, never force irrelevant images
    assert state['media_mix']['portrait_videos']==0
    assert state['media_mix']['average_used_duration']<4.5


def test_trusted_pinned_status_and_shell_false(studio,monkeypatch,tmp_path):
    b=studio[0].app.state.rendering.openmontage;root=tmp_path/'separate';root.mkdir()
    python=root/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python');python.parent.mkdir(parents=True);python.write_text('test')
    cli=root/'remotion-composer/node_modules/@remotion/cli/remotion-cli.js';cli.parent.mkdir(parents=True);cli.write_text('test')
    b.save({'root':str(root)})
    calls=[]
    def execute(args,**kw):
        calls.append((args,kw));assert kw['shell'] is False
        output=PIN if 'rev-parse' in args else OFFICIAL if 'get-url' in args else json.dumps({'success':True,'semantic_ready':False,'sources':['archive_org']}) if 'worker.py' in ' '.join(args) else ''
        return SimpleNamespace(returncode=0,stdout=output)
    monkeypatch.setattr('app.integrations.openmontage.bridge.subprocess.run',execute)
    state=b.status(True);assert state['ready'] and state['commit']==PIN[:7] and len(calls)==4
    assert all('shell' in kw and kw['shell'] is False for args,kw in calls)
    monkeypatch.setattr(b,'_run',lambda *a:SimpleNamespace(returncode=0,stdout='other-commit'))
    assert not b.status(True)['ready']


def test_mock_trim_compose_projection_preserves_timing_without_cycles(tmp_path,monkeypatch):
    from app.integrations.openmontage import provider
    from test_rendering import contract
    h,p=contract(6);h['project_id']='local';h['subtitles']=[]
    for s in p['scenes']:s.update(narration_text='Genehmigter Text.',importance=50)
    t=timeline.build(h,p);source=tmp_path/'source.mp4';source.write_bytes(b'unchanged');voice=tmp_path/'voice.wav';voice.write_bytes(b'voice')
    details={s['slot_id']:{'path':source,'type':'video','duration':22,'sha256':'fixture'} for s in t['slots']}
    edit=smart_edit.build(t,h,'adaptive','source',media_details=details)
    for i,s in enumerate(edit['slots']):s.update(layout='dual_media',secondary_slot_id=edit['slots'][1-i]['slot_id'])
    external=tmp_path/'external';(external/'remotion-composer').mkdir(parents=True);job=tmp_path/'job';job.mkdir();calls=[]
    class FakeBridge:
        def status(self,*a):return {'ready':True,'commit':PIN[:7]}
        def root(self):return external
        def settings_guard(self,v):pass
        def call(self,op,inputs,folder,runner,progress=None):
            calls.append((op,deepcopy(inputs)))
            if op=='trim':Path(inputs['output_path']).write_bytes(b'trim')
            else:
                props=json.loads(Path(inputs['edit_decisions']['bespoke']['props_path']).read_text())
                assert props['narration_audio']==str(voice) and props['duration']==6
                assert props['frames']==180 and props['subtitle_display']=='none'
                assert all(c['source_in']==0 and 'secondary' in c for c in props['clips'])
                assert inputs['edit_decisions']['render_runtime']=='remotion'
                Path(inputs['output_path']).write_bytes(b'output')
    class Delivery:
        def __init__(self,*args):pass
        def render(self,plan):
            assert plan['audio']==voice and plan['timeline']['duration']==6
            return {'path':job/'output.mp4','metadata':{}}
    monkeypatch.setattr(provider,'FFmpegRenderProvider',Delivery)
    result=provider.OpenMontageProvider(FakeBridge(),{},None).render({'temporary':job,'handoff':h,'timeline':t,'smart_edit_plan':edit,
        'options':options({'montage_engine':'openmontage','subtitle_display':'none'}),'media':details,'audio':voice,'music':None})
    assert [c[0] for c in calls]==['trim','trim','compose']
    for (_,request),item,slot in zip(calls,edit['slots'],t['slots']):
        assert request['start_seconds']==item['source_in']
        # Only a crossfade adds its blend handle; never loops or speed changes.
        handle=round(item['transition_duration']*30) if item['transition_out']=='crossfade' else 0
        assert request['end_seconds']-request['start_seconds']==pytest.approx((slot['frames']+handle)/30)
        assert 'speed' not in request and request['codec']=='libx264'
    assert source.read_bytes()==b'unchanged' and voice.read_bytes()==b'voice'
    assert result['metadata']['montage_engine']=='openmontage'
    assert not list((external/'remotion-composer/projects').iterdir())


def test_real_external_remotion_trim_delivery_and_source_hashes(tmp_path):
    """Real installed tools when explicitly supplied by the development environment."""
    root=os.environ.get('OPENMONTAGE_TEST_ROOT')
    if not root:pytest.skip('Optional external OpenMontage smoke requires its separate installed checkout.')
    from app.integrations.openmontage.provider import OpenMontageProvider
    from app.rendering import tools,probe
    from app.rendering.runner import ProcessRunner
    from test_rendering import contract,synthetic
    from test_subtitles import wav
    from test_smart_edit import pixels,difference
    b=Bridge(SimpleNamespace(storage=tmp_path),SimpleNamespace(secret_values=lambda:[],stock_config=lambda n:{}));b.save({'root':root})
    assert b.status(True)['ready'],b.status()
    h,p=contract(4);h['project_id']='smoke';h['subtitles']=[{'index':1,'start':1.2,'end':2.8,'text':'Genehmigter deutscher Text.'}]
    for s in p['scenes']:s.update(narration_text='Genehmigter deutscher Text.',importance=80)
    clip=synthetic(tmp_path,'long.mp4',['-f','lavfi','-i','color=c=blue:s=1280x720:r=30:d=22','-c:v','libx264'])
    picture=synthetic(tmp_path,'portrait.png',['-f','lavfi','-i','color=c=green:s=300x600','-frames:v','1'])
    voice=tmp_path/'voice.wav';voice.write_bytes(wav(4));originals={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in (clip,picture,voice)}
    media={'1':{'path':clip,'type':'video','duration':22,'width':1280,'height':720,'sha256':originals[clip]},
           '2':{'path':picture,'type':'image','duration':None,'width':300,'height':600,'sha256':originals[picture]}}
    t=timeline.build(h,p);edit=smart_edit.build(t,h,'adaptive','source',media_details=media)
    job=tmp_path/'job';job.mkdir();runner=ProcessRunner();result=OpenMontageProvider(b,tools.discover(),runner).render({
        'temporary':job,'handoff':h,'timeline':t,'smart_edit_plan':edit,'options':options({'montage_engine':'openmontage','encoder':'cpu','subtitle_display':'full'}),
        'audio':voice,'music':None,'media':media})
    measured=probe.validate(tools.discover()['ffprobe'],result['path'],4)
    assert measured['video_codec']=='h264' and measured['audio_codec']=='aac'
    assert result['metadata']['subtitle_burned'] and result['metadata']['montage_engine']=='openmontage'
    assert all(hashlib.sha256(f.read_bytes()).hexdigest()==v for f,v in originals.items())
    assert edit['slots'][0]['source_in']>1 and edit['slots'][1]['fit']=='contain'
    assert difference(pixels(result['path'],.4),pixels(result['path'],1.8))>5
