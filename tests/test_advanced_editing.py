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
