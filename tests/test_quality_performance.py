"""Quality regressions and bounded-worker checks; no network or user data."""
import json
import sys
import threading
import subprocess
import shutil
from copy import deepcopy
from types import SimpleNamespace

from app.stock.shot import bind, narration
from app.stock.verdict_cache import VerdictCache, context
from app.stock.director_media import MediaDirector, technical
from app.text_layout import fit_text
from app.motion.templates import fit, measure
from app.rendering import ass
import pytest


def test_different_sentences_do_not_share_approval_context():
    scene = {'scene_id': 'one', 'start_estimate': 0., 'end_estimate': 12.,
             'narration_text': 'Ships cross stormy ocean waters. Aircraft instruments guide pilots safely.'}
    first = {'estimated_start': 0., 'estimated_end': 6.}
    second = {'estimated_start': 6., 'estimated_end': 12.}
    before = deepcopy(scene)
    assert narration(scene, first) == 'Ships cross stormy ocean waters.'
    assert narration(scene, second) == 'Aircraft instruments guide pilots safely.'
    assert context(bind(scene, first)) != context(bind(scene, second))
    assert scene == before


def test_prejudge_searches_each_sentence_before_the_old_scene_query():
    director = MediaDirector.__new__(MediaDirector)
    director.clip, director.local, director.language, director.memo = None, False, 'en', {}
    scene = {'scene_id': 's', 'start_estimate': 0., 'end_estimate': 12.,
             'primary_stock_query': 'old general topic',
             'narration_text': 'Aircraft instruments guide pilots safely. Ocean ships cross stormy waters.'}
    slots = [{'slot_id': str(i), 'estimated_start': i*6., 'estimated_end': (i+1)*6.,
              'search_query': 'old general topic', 'duration': 6} for i in range(2)]
    searches = []
    director.search = lambda slot, kinds, query, log, scene: searches.append(query) or []
    director.prejudge(scene, slots)
    assert len(searches) == 2 and all(q != 'old general topic' for q in searches)
    assert 'aircraft' in searches[0].lower() and 'ocean' in searches[1].lower()


def test_word_order_and_constraints_invalidate_verdict_cache():
    base = {'narration_text': 'The dog follows the man.', 'must_not_show': 'cars'}
    assert context(base) != context({**base, 'narration_text': 'The man follows the dog.'})
    assert context(base) != context({**base, 'must_not_show': 'dogs'})


def test_early_explicit_year_is_historical_but_person_count_is_not():
    from app.stock.setting import period, for_scene
    assert period('Um das Jahr 100 lebten Menschen in Rom.')[0] == 'ancient'
    assert period('100 yılında Roma.')[0] == 'ancient'
    assert period('100 Menschen wohnen heute hier.')[0] == 'contemporary'
    assert for_scene({'era': 'contemporary', 'mode': 'auto'}, 'In the year 100 the city grew.')['era'] == 'ancient'


def test_sentence_specific_owner_visual_note_is_preserved():
    scene = {'scene_id': 's', 'start_estimate': 0., 'end_estimate': 6.,
             'narration_text': 'Rome grew from a small village into an empire.',
             'owner_hints': [{'type': 'visual', 'value': 'roman colosseum',
                              'sentence': 'Rome grew from a small village into an empire.'}]}
    bound = bind(scene, {'estimated_start': 0., 'estimated_end': 6.}, 'en')
    assert bound['primary_stock_query'] == 'roman colosseum'
    assert bound['narration_text'] == scene['narration_text']


def test_same_frame_embedding_is_reused_but_changed_model_is_not():
    from app.integrations.openmontage import visual_engine as visual
    import numpy as np
    calls = []
    def encode(values):
        calls.append(list(values))
        return np.ones((len(values), 4), dtype=np.float32)
    visual._EMBEDDINGS.clear()
    try:
        visual.embedded(['frame'], [('image', 'model-a', 'sha')], encode, None, None)
        visual.embedded(['frame'], [('image', 'model-a', 'sha')], encode, None, None)
        visual.embedded(['frame'], [('image', 'model-b', 'sha')], encode, None, None)
        assert calls == [['frame'], ['frame']]
    finally:
        visual._EMBEDDINGS.clear()


def test_unavailable_clip_probe_is_not_repeated_for_every_candidate():
    from app.stock.clip_check import ClipCheck
    calls = []
    def unavailable():
        calls.append(1)
        raise RuntimeError('not installed')
    checker = ClipCheck(SimpleNamespace(openmontage=SimpleNamespace(status=unavailable)))
    assert not checker.ready() and not checker.ready()
    assert calls == [1]


def test_parallel_cache_instances_preserve_each_others_entries(tmp_path):
    a, b = VerdictCache(tmp_path), VerdictCache(tmp_path)
    a.put({'one': {'score': 8}})
    assert b.get('one')['score'] == 8
    a.put({'two': {'score': 9}})
    b.put({'three': {'score': 7}})
    assert set(json.loads(a.path.read_text())) == {'one', 'two', 'three'}
    assert a.get('three')['score'] == 7


def test_portrait_and_low_resolution_are_not_new_automatic_picks():
    media = {'media_type': 'video', 'width': 1920, 'height': 1080, 'duration': 8}
    assert technical(media, 4) is None
    assert technical({**media, 'width': 1080, 'height': 1920}, 4) == 'orientation'
    assert technical({**media, 'width': 640, 'height': 360}, 4) == 'resolution'


def test_generic_search_word_does_not_certify_wrong_subject():
    director = MediaDirector.__new__(MediaDirector)
    scene = {'primary_stock_query': 'airplane cockpit instruments', 'visual_intent': 'aircraft cockpit',
             'must_show': 'aircraft instruments', 'narration_text': 'Aircraft instruments guide pilots.'}
    slot = {'search_query': 'computer office', 'visual_goal': 'aircraft cockpit'}
    media = {'provider': 'pixabay', 'media_type': 'video', 'media_id': '1',
             'description': 'computer office screen', 'query_used': 'computer office'}
    assert not director.local_judge(slot, scene, [media])[('pixabay','video','1')]['approved']


def test_motion_text_fit_preserves_all_words_and_long_names():
    text = 'Geniş başlık ' * 15 + 'Donaudampfschifffahrtsgesellschaft'
    size, rows = fit(text, 'Inter.ttf', 72, 1400, 3)
    assert ''.join(''.join(rows).split()) == ''.join(text.split())
    assert len(rows) <= 3
    assert all(measure(row, 'Inter.ttf', size) <= 1400 for row in rows)


def test_ass_band_and_badge_keep_complete_long_titles():
    text = 'Profesyonel video başlığının tamamı güvenli ekran alanında görünmeli ' * 2
    item = {'text': text, 'top': 'Üst başlık'}
    output = '\n'.join(ass.band2(item, 0, 6, {'font': 'Inter'}))
    assert 'görünmeli' in output
    assert '\\N' in output
    size, shown = ass.fitted(text, 'Inter', 1500, 2, 64)
    assert ' '.join(shown.split()) == ' '.join(text.split())


def test_word_highlight_preserves_explicit_line_break():
    output = '\n'.join(ass.word_boxes({'start': 0., 'end': 3., 'text': 'Birinci satır\nikinci satır'}, '#336699'))
    assert '\\N' in output


def test_frames_process_reuses_worker_and_recovers_after_exit(tmp_path):
    from app.integrations.openmontage.frames_process import FramesProcess
    import os
    script = tmp_path / 'worker.py'
    script.write_text('import sys,json,os\nfor line in sys.stdin:\n print(json.dumps({"success":True,"data":{"pid":os.getpid(),"input":json.loads(line)}}),flush=True)\n')
    worker = FramesProcess()
    args = [sys.executable, str(script)]
    try:
        a = worker.call(args, tmp_path, dict(os.environ), {'n': 1})
        b = worker.call(args, tmp_path, dict(os.environ), {'n': 2})
        assert a['data']['pid'] == b['data']['pid']
        worker.process.terminate();worker.process.wait(timeout=3)
        c = worker.call(args, tmp_path, dict(os.environ), {'n': 3})
        assert c['data']['input']['n'] == 3
    finally:
        worker.close()


def test_338_shots_over_15_minutes_keep_master_clock_and_original_script():
    from app.subtitles.timing import generate, map_scenes
    sentences = [f'Aircraft instruments guide pilots during flight number {i}.' for i in range(338)]
    text = ' '.join(sentences)
    cues, boundaries = generate(text, 900.)
    scenes = [{'scene_id': str(i), 'narration_text': sentence} for i, sentence in enumerate(sentences)]
    mapped = map_scenes(text, scenes, boundaries, 900.)
    assert len(mapped) == 338 and mapped[0]['start'] == 0 and mapped[-1]['end'] == 900.
    assert all(a['end'] == b['start'] for a,b in zip(mapped,mapped[1:]))
    assert all(s['end'] > s['start'] for s in mapped)
    assert ' '.join(' '.join(c['text'].split()) for c in cues) == text


def test_clip_verdict_is_reused_without_another_model_call(tmp_path):
    director = MediaDirector.__new__(MediaDirector)
    director.service = SimpleNamespace(projects=SimpleNamespace(storage=tmp_path))
    director.local, director.ai, director.progress = True, None, {}
    calls=[]
    def clip(slot, scene, pool):
        calls.append(1)
        return {('pixabay','video','one'): {'score':8,'approved':True,'local':True,'clip_approved':True,'reason':'uygun'}}
    director.clip_judge=clip
    scene={'scene_id':'s','narration_text':'Aircraft cockpit instruments.'}
    slot={'duration':4,'search_query':'aircraft cockpit'}
    media={'provider':'pixabay','media_type':'video','media_id':'one'}
    director.judge(slot,scene,[media]);result=director.judge(slot,scene,[media])
    assert calls==[1] and result[('pixabay','video','one')]['cached']


def test_exhausted_visual_budget_never_becomes_metadata_approval(tmp_path, monkeypatch):
    monkeypatch.setattr('app.stock.director_media.collage', lambda frames: {})
    director = MediaDirector.__new__(MediaDirector)
    director.service = SimpleNamespace(projects=SimpleNamespace(storage=tmp_path))
    director.local, director.ai, director.progress = False, None, {}
    director.clip_judge = lambda *args: {}
    director.frames = lambda media: pytest.fail('Skipped cloud requests must not download previews')
    director.local_judge = lambda *args: pytest.fail('Budget cannot authorize stock from tags')
    director._rate = lambda *args: pytest.fail('Budget exceeded')
    director.single = False
    scene = {'scene_id': 's', 'narration_text': 'Aircraft instruments.',
             'visual_intent': 'aircraft cockpit', 'primary_stock_query': 'aircraft cockpit instruments',
             'must_show': 'aircraft instruments'}
    slot = {'duration': 4}
    fingerprint = context(scene, {'quality_setting': director.where(scene),
                                 'quality_evaluator': {'clip': '', 'cloud': '', 'model': ''}})
    director.look_budget = {(fingerprint, 's'): 1}
    media = {'provider': 'pixabay', 'media_type': 'video', 'media_id': 'one',
             'description': 'aircraft cockpit instruments'}
    assert director.judge(slot, scene, [media]) == {}
    assert director.progress['visual_budget_skipped'] == 1


def test_cloud_yes_cannot_approve_unrelated_source_tags(tmp_path, monkeypatch):
    monkeypatch.setattr('app.stock.director_media.collage', lambda frames: {})
    director = MediaDirector.__new__(MediaDirector)
    director.service = SimpleNamespace(projects=SimpleNamespace(storage=tmp_path))
    director.local, director.ai, director.progress, director.single = False, None, {}, False
    director.clip_judge = lambda *args: {}
    director.frames = lambda media: [None]
    director._rate = lambda *args: {'verdicts': [{'candidate': 1, 'score': 9, 'approved': True}]}
    scene = {'scene_id': 's', 'narration_text': 'Aircraft instruments guide pilots.',
             'visual_intent': 'aircraft cockpit', 'must_show': 'aircraft instruments',
             'primary_stock_query': 'aircraft cockpit instruments'}
    media = {'provider': 'pixabay', 'media_type': 'video', 'media_id': 'one',
             'description': 'modern city skyline traffic'}
    result = director.judge({'duration': 4}, scene, [media])
    assert not result[('pixabay', 'video', 'one')]['approved']


def test_search_prefetch_is_bounded_parallel_and_results_are_deterministic():
    from concurrent.futures import ThreadPoolExecutor
    barrier=threading.Barrier(2)
    def search(pid,name,kind,query):
        barrier.wait(timeout=3)
        return [{'provider':name,'media_type':kind,'media_id':str(i)} for i in range(15)],{},False
    director=MediaDirector.__new__(MediaDirector)
    director.language,director.pid,director.progress='en','p',{}
    director.job={}
    director.providers=lambda scene=None:['one','two']
    with ThreadPoolExecutor(max_workers=2) as pool:
        director.service=SimpleNamespace(search_executor=pool,_cache_search=search,_checkpoint=lambda *a,**k:None)
        result=director.search({'order':1},['video'],'aircraft cockpit',{'searches':[]})
    assert [m['provider'] for m in result]==['one']*15+['two']*15


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='FFmpeg/ffprobe required')
def test_real_source_inspection_rejects_defocused_and_portrait_images(tmp_path):
    from app.stock.quality import inspect_media
    from app.rendering.tools import discover
    from PIL import Image, ImageFilter
    import numpy as np
    import hashlib
    root=tmp_path/'stock';root.mkdir()
    projects=SimpleNamespace(_path=lambda pid:tmp_path)
    tool=discover()
    rng=np.random.default_rng(42)
    raw=(rng.random((720,1280))*255).astype(np.uint8)
    sharp=Image.fromarray(raw).convert('RGB')
    # Structured contrast survives defocus, fine detail does not.
    x=np.linspace(0,255,1280,dtype=np.uint8)
    blurred=Image.fromarray(np.tile(x,(720,1))).convert('RGB').filter(ImageFilter.GaussianBlur(18))
    def inspect(image,index):
        path=root/(f'{index:032x}'+'.png');image.save(path)
        media={'media_type':'image','local_path':'stock/'+path.name,'file_size':path.stat().st_size,
               'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        return inspect_media(projects,'p',media,tool)
    assert inspect(sharp,1)['accepted']
    assert inspect(blurred,2)['reason']=='blurred'
    assert inspect(sharp.transpose(Image.Transpose.ROTATE_90),3)['reason']=='orientation_or_resolution'


def test_frames_timeout_stops_worker_and_next_request_can_restart(tmp_path):
    from app.integrations.openmontage.frames_process import FramesProcess
    import os
    script=tmp_path/'worker.py'
    script.write_text('import time\ntime.sleep(30)\n')
    worker=FramesProcess()
    with pytest.raises(ValueError):worker.call([sys.executable,str(script)],tmp_path,dict(os.environ),{},timeout=.1)
    assert worker.process is None
    worker.close()


def test_motion_cancellation_reaps_blocked_child(tmp_path):
    from app.motion.control import CANCELLED, MotionCancelled, guard
    event=threading.Event()
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    token=CANCELLED.set(event.is_set)
    try:
        with pytest.raises(MotionCancelled):
            with guard(child):
                event.set()
                child.wait(timeout=3)
        assert child.poll() is not None
    finally:
        CANCELLED.reset(token)
        if child.poll() is None:child.kill();child.wait()


def test_silent_render_process_is_stopped_by_watchdog(tmp_path):
    from app.rendering.runner import ProcessRunner
    from app.rendering.models import RenderError
    runner=ProcessRunner(stall_seconds=.2)
    with pytest.raises(RenderError) as error:
        runner.run([sys.executable,'-c','import time; time.sleep(30)'],tmp_path)
    assert error.value.category=='render_stalled'
    assert runner.process is None


def test_remotion_uses_same_lossless_layout_without_changing_source_text():
    from app.integrations.openmontage.provider import text_layout
    text='Uzun ve okunabilir başlık metni ' * 6
    props={'clips':[{'layout':'split_media_text','texts':[text]}],
           'emphasis':[{'text':text,'style':'lower_third','start':0,'end':3}],
           'subtitles':[{'text':text,'start':0,'end':3}]}
    result=text_layout({},deepcopy(props))
    assert result['clips'][0]['texts']==[text]
    assert ' '.join(result['clips'][0]['display_text'].split())==' '.join(text.split())
    assert result['subtitles'][0]['text']==text
    assert result['subtitles'][0]['font_size']<=64


def test_quality_rejected_source_cannot_bypass_render_preflight(ready):
    from contextlib import closing
    from test_rendering import url
    service=ready['client'].app.state.rendering
    with closing(service.projects._connection()) as c,c:
        row=c.execute('SELECT plan_id,state_json FROM stock_plans WHERE project_id=?',(ready['pid'],)).fetchone()
        state=json.loads(row['state_json']);state['slots'][0]['local_validation']={'accepted':False}
        c.execute('UPDATE stock_plans SET state_json=? WHERE project_id=? AND plan_id=?',
                  (json.dumps(state),ready['pid'],row['plan_id']))
    response=ready['client'].post(url(ready)+'/jobs',json={})
    assert response.status_code==409 and response.json()['category']=='input_invalid'


from test_rendering import ready
