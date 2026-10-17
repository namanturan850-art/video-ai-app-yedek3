"""One toolbar undo/redo across scoped documents, slots, preferences and subtitles."""
from contextlib import closing
import hashlib
import json

from app.editor.advanced import AdvancedEditor,Document
from app.editor.editorial import Editorial
from app.editor.models import EditorError


def top(rows,edit,undo,redo,direction):
    done=[];undone=[];records={}
    for row in rows:
        record=json.loads(row['payload_json'])
        if row['kind']==edit:
            key=str(row['id']);item={'id':key,'record':record,'time':row['created_at']};records[key]=item;done.append(item);undone=[]
        elif row['kind']==undo and done:
            target=record.get('target');item=next((x for x in done if x['id']==str(target)),None) if target else done[-1]
            if item in done:done.remove(item);item={**item,'time':row['created_at']};undone.append(item)
        elif row['kind']==redo and undone:
            item=undone.pop();done.append({**item,'time':row['created_at']})
    stack=done if direction=='undo' else undone
    return stack[-1] if stack else None


class History:
    def __init__(self,editor):self.editor=editor;self.projects=editor.projects;self.editorial=Editorial(editor);self.advanced=AdvancedEditor(editor)

    def snapshot(self,pid):
        mode=self.editorial.get(pid);advanced=self.advanced.get(pid)
        with closing(self.projects._connection()) as c:
            row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=? AND plan_id=?',(pid,mode['plan_id'])).fetchone()
            stock=json.loads(row[0]) if row else {}
            active=c.execute('SELECT active_version_id FROM subtitle_state WHERE project_id=?',(pid,)).fetchone()
        audio=self.editor.audio_settings(pid)
        return {'plan_id':mode['plan_id'],'editorial_revision':mode['revision'],'advanced_revision':advanced['revision'],
                'stock_revision':stock.get('revision',0),'subtitle_version_id':active[0] if active else None,
                'audio_identity':hashlib.sha256(json.dumps(audio,sort_keys=True).encode()).hexdigest()}

    def apply(self,pid,direction,payload):
        if direction not in ('undo','redo'):raise EditorError('invalid_history','Geçmiş yönü geçersiz.')
        with self.projects.lock:
            current=self.snapshot(pid)
            if payload!=current:raise EditorError('stale_history','Proje başka işlemde değişmiş. Güncel geçmişi yeniden yükleyin.',409)
            self.editorial._idle(pid);plan=current['plan_id']
            with closing(self.projects._connection()) as c:
                advanced=c.execute('SELECT * FROM editor_document_events WHERE project_id=? AND plan_id=? ORDER BY id',(pid,plan)).fetchall()
                slots=c.execute('SELECT * FROM editor_revisions WHERE project_id=? AND plan_id=? ORDER BY created_at,rowid',(pid,plan)).fetchall()
                editorial=c.execute('SELECT * FROM editorial_events WHERE project_id=? AND plan_id=? ORDER BY id',(pid,plan)).fetchall()
            candidates=[]
            if direction=='redo':
                edits=[r['created_at'] for r in [*advanced,*slots,*editorial] if r['kind'] in ('edit','timeline_edit','preferences','subtitle_edit','audio_mix')]
                undos=[r['created_at'] for r in [*advanced,*slots,*editorial] if r['kind'] in ('undo','timeline_undo','preferences_undo','subtitle_undo','audio_mix_undo')]
                if not undos or edits and max(edits)>max(undos):raise EditorError('empty_history','Yeni düzenleme sonrasında önceki yineleme dalı kapandı.',409)
            for domain,rows,kinds in [('advanced',advanced,('edit','undo','redo')),('slots',slots,('timeline_edit','timeline_undo','timeline_redo')),
                                      ('preferences',editorial,('preferences','preferences_undo','preferences_redo')),
                                      ('subtitles',editorial,('subtitle_edit','subtitle_undo','subtitle_redo')),
                                      ('audio',editorial,('audio_mix','audio_mix_undo','audio_mix_redo'))]:
                candidate=top(rows,*kinds,direction)
                if candidate:candidates.append({**candidate,'domain':domain})
            if not candidates:raise EditorError('empty_history','Bu yönde geri alınabilecek düzenleme yok.',409)
            selected=max(candidates,key=lambda x:x['time']);domain=selected['domain'];record=selected['record']
            if domain=='advanced':
                self.advanced.history(pid,direction,{'plan_id':plan,'revision':current['advanced_revision']})
                approval=next((json.loads(r['payload_json']) for r in editorial if r['kind']=='approved' and str(json.loads(r['payload_json']).get('advanced_event_id'))==selected['id']),None)
                if approval:
                    state=self.editorial.get(pid);state['preferences']=approval['preferences_before' if direction=='undo' else 'preferences_after']
                    self.editorial.save(pid,state,kind='approval_preferences')
            elif domain=='slots':self.editor.timeline_history(pid,direction,{'plan_id':plan,'revision':current['stock_revision']})
            elif domain=='subtitles':self.editorial.subtitle_history(pid,direction,{'version_id':current['subtitle_version_id']})
            elif domain=='preferences':
                state=self.editorial.get(pid);expected=record['after' if direction=='undo' else 'before']
                if state['preferences']!=expected:raise EditorError('stale_history','Kurgu ayarları başka işlemde değişmiş.',409)
                state['preferences']=record['before' if direction=='undo' else 'after'];self.editorial.save(pid,state,kind='preferences_'+direction)
            elif domain=='audio':
                actual=self.editor.audio_settings(pid);actual.pop('project_id',None)
                if actual!=record['after' if direction=='undo' else 'before']:raise EditorError('stale_history','Ses ayarı değişmiş.',409)
                self.editor.save_audio_settings(pid,record['before' if direction=='undo' else 'after'],history_kind='audio_mix_'+direction)
            return {'domain':domain,'snapshot':self.snapshot(pid)}
