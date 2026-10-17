from copy import deepcopy
from contextlib import closing
import hashlib
import json
from types import SimpleNamespace

import pytest

from app.database import initialize_database,SCHEMA_VERSION
from app.projects import ProjectService
from app.editor.advanced import AdvancedEditor,Document
from app.editor.models import EditorError


@pytest.fixture
def advanced(tmp_path):
    initialize_database(tmp_path);projects=ProjectService(tmp_path)
    pid=projects.create({'name':'Ek kurgu','topic':'Yerel test'})['id']
    path=tmp_path/'test.png';path.write_bytes(b'local-test-bytes')
    asset={'media_type':'image','duration':None};digest=hashlib.sha256(path.read_bytes()).hexdigest()
    view={'duration':8.,'scenes':[{'scene_id':'s','start':0.,'end':8.,'locked':False,'narration':'Rota 40 km.'}],
          'tracks':{'visuals':[{'slot_id':'base','start':0.,'end':8.,'locked':False,'media':{'media_type':'image'}}]}}
    editor=SimpleNamespace(projects=projects,_active=lambda _: {'plan_id':'p'},view=lambda _:deepcopy(view),
                           archive_file=lambda *args:(path,asset),stock=SimpleNamespace(_idle=lambda *args:None))
    return AdvancedEditor(editor),pid,view,digest


def change(editor,pid,fn):
    current=editor.get(pid);fn(current['document']);return editor.save(pid,current)


def test_documents_scope_history_reopen_and_clock(advanced):
    editor,pid,view,digest=advanced
    before=deepcopy(view)
    saved=change(editor,pid,lambda d:d['clips'].append({'id':'a'*32,'kind':'media','track':'layers','start':1.,'end':3.,
        'media':{'provider':'local','media_id':'m','sha256':digest},'keyframes':[{'property':'scale','time':0.,'value':1.},{'property':'scale','time':2.,'value':1.5}]}))
    assert saved['revision']==1 and view==before
    undone=editor.history(pid,'undo',{'plan_id':'p','revision':1});assert undone['document']['clips']==[]
    redone=editor.history(pid,'redo',{'plan_id':'p','revision':2});assert len(redone['document']['clips'])==1
    assert AdvancedEditor(editor.editor).get(pid)==redone
    with pytest.raises(EditorError,match='revizyon'):editor.save(pid,saved)
    editor.editor._active=lambda _: {'plan_id':'other'}
    assert editor.get(pid)['revision']==0 and editor.get(pid)['document']['clips']==[]


@pytest.mark.parametrize('update',[
    {'transform':{'scale':9.}}, {'transform':{'x':float('nan')}}, {'effects':{'unknown':1}},
    {'keyframes':[{'property':'scale','time':9.,'value':1.}]}, {'keyframes':[{'property':'x','time':0.,'value':99999.}]},
    {'start':7.,'end':9.}, {'kind':'media','media':None}, {'kind':'text','track':'audio'},
])
def test_invalid_edits_never_change_revision(advanced,update):
    editor,pid,view,digest=advanced
    with pytest.raises(EditorError):
        change(editor,pid,lambda d:d['clips'].append({'id':'a'*32,'kind':'text','track':'layers','start':0.,'end':2.,'text':'Not',**update}))
    assert editor.get(pid)['revision']==0


def test_lock_marker_and_invalid_transition(advanced):
    editor,pid,view,digest=advanced
    view['scenes'][0]['locked']=True
    saved=change(editor,pid,lambda d:d['markers'].append({'id':'a'*32,'time':2.,'name':'Kontrol','note':'Not'}))
    assert saved['document']['markers'][0]['time']==2.
    with pytest.raises(EditorError,match='Kilitli'):
        change(editor,pid,lambda d:d['clips'].append({'id':'a'*32,'kind':'text','track':'layers','start':0.,'end':2.,'text':'Not'}))
    with pytest.raises(EditorError,match='bitişik'):
        change(editor,pid,lambda d:d['transitions'].append({'slot_id':'base','next_slot_id':'missing','kind':'cross_dissolve','duration':.2}))


def test_schema14_upgrade_preserves_project(tmp_path):
    db=initialize_database(tmp_path);projects=ProjectService(tmp_path)
    pid=projects.create({'name':'Eski proje','topic':'Korunacak'})['id']
    with closing(projects._connection()) as c,c:
        c.execute('DROP TABLE editor_document_events');c.execute('DROP TABLE editor_documents')
        c.execute("UPDATE app_metadata SET value='14' WHERE key='schema_version'")
    initialize_database(tmp_path)
    assert projects.get(pid)['name']=='Eski proje'
    with closing(projects._connection()) as c:
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]==SCHEMA_VERSION


def test_marker_keyframe_move_delete_history_and_locked_clips(advanced):
    editor,pid,view,digest=advanced;original=deepcopy(view)
    saved=change(editor,pid,lambda d:d['clips'].append({'id':'b'*32,'kind':'text','track':'layers','start':1.,'end':3.,'text':'Not'}))
    def edited(d):
        clip=d['clips'][0];clip.update(start=2.,end=4.);clip['keyframes']=[{'property':'opacity','time':0.,'value':0.},{'property':'opacity','time':2.,'value':1.}]
        d['markers'].append({'id':'c'*32,'time':3.,'name':'Kontrol','note':'Kalıcılık'})
    changed=change(editor,pid,edited)
    assert changed['document']['clips'][0]['start']==2 and view==original
    changed=change(editor,pid,lambda d:d['clips'][0]['keyframes'].pop())
    assert len(changed['document']['clips'][0]['keyframes'])==1
    deleted=change(editor,pid,lambda d:(d['clips'].clear(),d['markers'].clear()))
    assert deleted['document']['clips']==[]
    restored=editor.history(pid,'undo',{'plan_id':'p','revision':deleted['revision']})
    assert restored['document']['markers'][0]['note']=='Kalıcılık'
    assert restored['document']['clips'][0]['keyframes'][0]['value']==0
    locked=change(editor,pid,lambda d:d['clips'][0].update(locked=True))
    with pytest.raises(EditorError,match='[Kk]ilitli'):change(editor,pid,lambda d:d['clips'].clear())
    with pytest.raises(EditorError,match='kilitli'):change(editor,pid,lambda d:d['clips'][0].update(text='Değişti'))
    another=editor.projects.create({'name':'Başka proje','topic':'Kapsam'})['id']
    assert editor.get(another)['document']['clips']==[]


def test_audio_has_only_supported_controls(advanced):
    editor,pid,view,digest=advanced
    path,_=editor.editor.archive_file(pid,'local','m');asset={'media_type':'audio','duration':4.,'has_audio':True}
    editor.editor.archive_file=lambda *args:(path,asset)
    saved=change(editor,pid,lambda d:d['clips'].append({'id':'d'*32,'kind':'media','track':'audio','start':0.,'end':2.,'media':{'provider':'local','media_id':'m','sha256':digest},'transform':{'volume':1.,'speed':2.}}))
    with pytest.raises(EditorError,match='Ses klibinde'):change(editor,pid,lambda d:d['clips'][0]['transform'].update(rotation=30.))
    with pytest.raises(EditorError,match='yetersiz'):change(editor,pid,lambda d:d['clips'][0].update(end=3.))


def test_locked_transition_allows_notes_but_rejects_removal(advanced):
    editor,pid,view,digest=advanced
    view['tracks']['visuals'][0]['end']=4.
    view['tracks']['visuals'].append({'slot_id':'next','start':4.,'end':8.,'locked':False,'media':{'media_type':'image'}})
    change(editor,pid,lambda d:d['transitions'].append({'slot_id':'base','next_slot_id':'next','kind':'wipe','duration':.2}))
    view['tracks']['visuals'][0]['locked']=True
    change(editor,pid,lambda d:d['markers'].append({'id':'f'*32,'time':1.,'name':'Not'}))
    with pytest.raises(EditorError,match='Kilitli'):change(editor,pid,lambda d:d['transitions'].clear())


def test_clip_cannot_escape_a_locked_scene(advanced):
    editor,pid,view,digest=advanced
    view['scenes'][0]['end']=4.
    view['scenes'].append({'scene_id':'other','start':4.,'end':8.,'locked':False})
    change(editor,pid,lambda d:d['clips'].append({'id':'e'*32,'kind':'text','track':'layers','start':0.,'end':2.,'text':'Başlık'}))
    view['scenes'][0]['locked']=True
    with pytest.raises(EditorError,match='Kilitli'):change(editor,pid,lambda d:d['clips'][0].update(start=5.,end=7.))


def test_real_thumbnail_cache_and_changed_hash_rejection(advanced):
    import subprocess,shutil
    from PIL import Image
    from app.editor.previews import thumbnail
    editor,pid,view,digest=advanced
    path=editor.projects._path(pid)/'stock'/'thumbnail-test.mp4'
    subprocess.run([shutil.which('ffmpeg'),'-v','error','-y','-f','lavfi','-i','color=c=red:s=240x320:r=30:d=0.4','-c:v','libx264','-threads','1',str(path)],check=True,capture_output=True)
    original=path.read_bytes();asset={'media_type':'video','duration':.4,'sha256':hashlib.sha256(original).hexdigest()}
    editor.editor.archive_file=lambda *args:(path,asset)
    first=thumbnail(editor.editor,pid,'local','thumbnail')
    assert Image.open(first).size==(240,135)
    mtime=first.stat().st_mtime_ns
    assert thumbnail(editor.editor,pid,'local','thumbnail')==first and first.stat().st_mtime_ns==mtime
    path.write_bytes(original[:-1]+bytes([original[-1]^1]))
    with pytest.raises(EditorError,match='değişmiş'):thumbnail(editor.editor,pid,'local','thumbnail')
