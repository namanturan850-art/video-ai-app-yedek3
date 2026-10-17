"""Project editing policy and reviewable drafts; legacy reads never migrate content."""
from contextlib import closing
from copy import deepcopy
import json
from uuid import uuid4

from pydantic import Field
from typing import Literal
from app.editor.advanced import Strict, AdvancedEditor
from app.editor.models import EditorError
from app.projects import now

STATEMENTS=(
    '''CREATE TABLE IF NOT EXISTS editorial_state(project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
       revision INTEGER NOT NULL,payload_json TEXT NOT NULL,updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS editorial_events(id INTEGER PRIMARY KEY AUTOINCREMENT,
       project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,plan_id TEXT NOT NULL,
       kind TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL)''',
)


class Preferences(Strict):
    editing_mode: Literal['legacy','manual','approved_auto']='legacy'
    media_preparation_mode: Literal['legacy','sources_only']='legacy'
    subtitle_display: Literal['full','emphasis','none']='full'
    important_cues: list[int]=Field(default_factory=list,max_length=2000)
    word_highlight: bool=False
    legacy_decorations: bool=True
    approved_editorial_revision: str|None=None


def read(projects,pid):
    # Read-only projection adapters have no persistence; preserve legacy behavior.
    if not hasattr(projects,'_connection') or not hasattr(projects,'_row'):return {'revision':0,'preferences':Preferences().model_dump()}
    with closing(projects._connection()) as c:
        projects._row(c,pid)
        row=c.execute('SELECT * FROM editorial_state WHERE project_id=?',(pid,)).fetchone()
    return {'revision':row['revision'] if row else 0,'preferences':json.loads(row['payload_json']) if row else Preferences().model_dump()}


def manual(projects,pid):return read(projects,pid)['preferences']['editing_mode']!='legacy'


def initialize_project(c,pid):
    prefs=Preferences(editing_mode='manual',media_preparation_mode='sources_only',legacy_decorations=False).model_dump()
    c.execute('INSERT INTO editorial_state VALUES (?,?,?,?)',(pid,0,json.dumps(prefs),now()))


class Editorial:
    def __init__(self,editor):self.editor=editor;self.projects=editor.projects;self.advanced=AdvancedEditor(editor)

    def get(self,pid):
        state=read(self.projects,pid);state['plan_id']=self.editor._active(pid)['plan_id'];return state

    def save(self,pid,payload):
        from pydantic import ValidationError
        if set(payload)!={'plan_id','revision','preferences'}:raise EditorError('invalid_preferences','Kurgu modu, plan ve revizyon bilgilerini kontrol edin.')
        try:prefs=Preferences.model_validate(payload['preferences']).model_dump()
        except ValidationError:raise EditorError('invalid_preferences','Kurgu veya altyazı seçimi geçersiz.') from None
        with self.projects.lock:
            old=self.get(pid)
            if type(payload['revision']) is not int or (payload['plan_id'],payload['revision'])!=(old['plan_id'],old['revision']):raise EditorError('stale_revision','Kurgu modu değişmiş. Sayfayı yenileyin.',409)
            with closing(self.projects._connection()) as c:
                self.editor.stock._idle(c,pid)
                if c.execute("SELECT 1 FROM render_jobs WHERE project_id=? AND status IN ('queued','preparing','rendering','validating')",(pid,)).fetchone():raise EditorError('render_busy','Render sırasında kurgu modu değiştirilemez.',409)
            if prefs['editing_mode']=='approved_auto' and not prefs['approved_editorial_revision']:
                raise EditorError('unapproved','Önce bir otomatik kurgu taslağını inceleyip onaylayın.')
            if prefs['editing_mode']=='approved_auto':
                with closing(self.projects._connection()) as c:approved=c.execute("SELECT payload_json FROM editorial_events WHERE project_id=? AND plan_id=? AND kind='approved'",(pid,old['plan_id'])).fetchall()
                if not any(json.loads(r[0])['draft_id']==prefs['approved_editorial_revision'] for r in approved):raise EditorError('unapproved','Bu projeye ait onaylı taslak bulunamadı.')
            if prefs['editing_mode']!='legacy':prefs['media_preparation_mode']='sources_only'
            else:prefs.update(media_preparation_mode='legacy',legacy_decorations=True)
            with closing(self.projects._connection()) as c,c:
                c.execute('INSERT INTO editorial_state VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET revision=excluded.revision,payload_json=excluded.payload_json,updated_at=excluded.updated_at',(pid,old['revision']+1,json.dumps(prefs),now()))
                c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,old['plan_id'],'preferences',json.dumps({'before':old['preferences'],'after':prefs}),now()))
            return self.get(pid)

    def draft(self,pid,clips,source='automatic',adjustments=None,transitions=None):
        state=self.advanced.get(pid);doc=deepcopy(state['document']);doc['clips']+=clips
        doc['adjustments']+=adjustments or [];doc['transitions']+=transitions or []
        # Validate without committing: no plan, source, or user edit changes here.
        normalized=self.advanced.validate(pid,doc,state['document'])
        draft={'id':uuid4().hex,'source':source,'base_revision':state['revision'],'clips':normalized['clips'][len(state['document']['clips']):],
               'adjustments':normalized['adjustments'][len(state['document']['adjustments']):],
               'transitions':normalized['transitions'][len(state['document']['transitions']):],
               'plan_id':state['plan_id'],'created_at':now()}
        with closing(self.projects._connection()) as c,c:
            c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,state['plan_id'],'draft',json.dumps(draft),now()))
        return draft

    def automatic(self,pid):
        from hashlib import sha256
        view=self.editor.view(pid);clips=[];current=self.advanced.get(pid)['document']['clips']
        for scene in view['scenes']:
            if scene['locked']:continue
            # Extract only actual narration words; no inferred names, dates or numbers.
            text=' '.join(scene['narration'].split()[:7])
            key=sha256(json.dumps([scene['scene_id'],text]).encode()).hexdigest()
            if any(c.get('source_key')==key or c.get('text')==text and c['start']==scene['start'] for c in current):continue
            if text and scene['end']-scene['start']>=1/30:
                clips.append({'id':uuid4().hex,'kind':'text','track':'emphasis','start':scene['start'],'end':min(scene['end'],scene['start']+3),
                              'text':text,'color':'#FFFFFF','order':100,'origin':'automatic','source_key':key})
        return self.draft(pid,clips)

    def import_draft(self,pid,payload):
        from hashlib import sha256
        plain=deepcopy(payload)
        sections=('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar')
        if not isinstance(payload,dict):raise EditorError('invalid_json','JSON kökü nesne olmalıdır.')
        for section in sections:
            if isinstance(plain.get(section),list):
                for item in plain[section]:
                    if isinstance(item,dict):
                        for key in ('start','end','object_id'):item.pop(key,None)
        checked=self.editor.validate_import(pid,plain)
        if not checked['valid']:raise EditorError('invalid_json',checked['correction_message'])
        view=self.editor.view(pid);scenes={s['scene_id']:s for s in view['scenes']};clips=[];adjustments=[];transitions=[];seen=set()
        current=self.advanced.get(pid)['document'];existing={c.get('source_key') for c in current['clips'] if c.get('source_key')}
        slots=sorted([x for values in view['tracks'].values() for x in values if x.get('slot_id')],key=lambda x:x['start'])
        for section in sections:
            for item in payload[section]:
                scene=scenes[item['scene_id']];start=item.get('start',scene['start']);end=item.get('end',scene['end'])
                if type(start) not in (int,float) or type(end) not in (int,float) or not scene['start']<=start<end<=scene['end']:
                    raise EditorError('invalid_time',f'{section}: zamanlar kendi sahne aralığında olmalıdır.')
                source_key=sha256(json.dumps([section,item],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                key=item.get('object_id') or source_key
                if key in seen or source_key in existing:raise EditorError('duplicate','Tekrarlanan JSON nesnesi bulundu. Var olan öğe korunuyor.')
                seen.add(key)
                if section=='sahneler':
                    if item.get('composition') not in (None,'wide') or item.get('motion') in ('overlay','emphasis_text') and not item.get('overlay_text'):
                        raise EditorError('unsupported_scene','Bu manuel JSON sahnesinin composition/motion alanı desteklenmiyor. Gerçek X/Y, ölçek veya bağımsız metin katmanı kullanın.')
                    text=item.get('overlay_text')
                    if text:clips.append({'id':uuid4().hex,'kind':'text','track':'layers','start':start,'end':end,'text':text,'origin':'json','source_key':source_key})
                    for slot in (s for s in slots if s['scene_id']==scene['scene_id']):
                        motion=item.get('motion','none');duration=slot['end']-slot['start']
                        if motion in ('pan','slow_zoom','ken_burns'):
                            prop='x' if motion=='pan' else 'scale';a,z=(-100.,100.) if prop=='x' else (1.,1.12)
                            adjustments.append({'slot_id':slot['slot_id'],'keyframes':[{'property':prop,'time':0.,'value':a},{'property':prop,'time':duration,'value':z}]})
                    transition=item.get('transition','none')
                    last=next((s for s in slots if s['scene_id']==scene['scene_id'] and abs(s['end']-scene['end'])<.04),None)
                    nxt=next((s for s in slots if last and abs(s['start']-last['end'])<.04),None)
                    if last and nxt and transition!='none':
                        length=min(.2,(last['end']-last['start'])/4,(nxt['end']-nxt['start'])/4)
                        transitions.append({'slot_id':last['slot_id'],'next_slot_id':nxt['slot_id'],'kind':{'hard_cut':'cut','crossfade':'cross_dissolve','fade':'dip_black'}[transition],'duration':length})
                    continue
                track={'infografikler':'infographics','harita_sahneleri':'maps','vurgular':'emphasis','katmanlar':'layers'}[section]
                clip={'id':uuid4().hex,'kind':'motion' if section in ('infografikler','harita_sahneleri') else 'text',
                      'track':track,'start':start,'end':end,'origin':'json','source_key':source_key}
                if clip['kind']=='motion':
                    clip['motion']={k:item[k] for k in ('template','data','emphasis') if k in item}
                    if any(s['scene_id']==scene['scene_id'] and s.get('motion_spec',{}).get('template')==item['template'] and s['motion_spec']['data']==item['data'] for s in slots):
                        raise EditorError('duplicate_motion','Bu animasyon zaten temel medya yuvasında. Aynı öğe ikinci kez eklenmedi.')
                else:clip['text']=item['text']
                clips.append(clip)
        draft=self.draft(pid,clips,'json',adjustments,transitions)
        draft['changes']=checked['changes'];draft['overlapping_manual_ids']=[c['id'] for c in current['clips'] if any(c['start']<x['end'] and c['end']>x['start'] for x in clips)]
        return draft

    def subtitles_edit(self,pid,payload):
        if set(payload)!={'version_id','cues','important_cues'}:raise EditorError('invalid_subtitles','Altyazı sürümü, metin/zamanlar ve önemli öğe seçimini kontrol edin.')
        with self.projects.lock:
            current=self.editor.subtitles.view(pid).get('active')
            if not current or current['id']!=payload['version_id']:raise EditorError('stale_subtitle','Altyazı sürümü değişmiş. Güncel sürümü yeniden açın.',409)
            self._idle(pid)
            from app.subtitles.models import validate_cues
            cues=validate_cues(payload['cues'],current['metadata']['audio_duration'],allow_empty=True)
            important=payload['important_cues']
            if not isinstance(important,list) or any(type(i)is not int or i<1 or i>len(cues) for i in important):raise EditorError('invalid_cues','Önemli altyazı seçimi geçersiz.')
            old_cues=current['cues'];scenes=self.editor.view(pid)['scenes']
            for scene in scenes:
                if scene['locked']:
                    inside=lambda q:q['start']<scene['end'] and q['end']>scene['start']
                    if [q for q in old_cues if inside(q)]!=[q for q in cues if inside(q)]:raise EditorError('locked','Kilitli sahnenin altyazısı değiştirilemez.',409)
            result=self.editor.subtitles.edit(pid,current['id'],{'cues':payload['cues']},allow_empty=True,preserve_clock=True)
            before=self.get(pid);after=deepcopy(before['preferences']);after['important_cues']=important
            self.save(pid,{**before,'preferences':after})
            with closing(self.projects._connection()) as c,c:
                c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,before['plan_id'],'subtitle_edit',json.dumps({'before':current['id'],'after':result['active']['id'],'preferences_before':before['preferences'],'preferences_after':after}),now()))
            return result

    def _idle(self,pid):
        with closing(self.projects._connection()) as c:
            self.editor.stock._idle(c,pid)
            if c.execute("SELECT 1 FROM render_jobs WHERE project_id=? AND status IN ('queued','preparing','rendering','validating')",(pid,)).fetchone():raise EditorError('render_busy','Render sırasında düzenleme yapılamaz.',409)

    def subtitle_history(self,pid,direction,payload):
        if direction not in ('undo','redo') or set(payload)!={'version_id'}:raise EditorError('invalid_history','Altyazı geçmişi isteği geçersiz.')
        with self.projects.lock:
            self._idle(pid);scope=self.get(pid)
            current=self.editor.subtitles.view(pid)['active']
            if not current or current['id']!=payload['version_id']:raise EditorError('stale_subtitle','Aktif altyazı değişmiş.',409)
            with closing(self.projects._connection()) as c:rows=c.execute("SELECT kind,payload_json FROM editorial_events WHERE project_id=? AND plan_id=? AND kind IN ('subtitle_edit','subtitle_undo','subtitle_redo') ORDER BY id",(pid,scope['plan_id'])).fetchall()
            done=[];undone=[]
            for row in rows:
                event=json.loads(row['payload_json'])
                if row['kind']=='subtitle_edit':done.append(event);undone=[]
                elif row['kind']=='subtitle_undo' and done:undone.append(done.pop())
                elif row['kind']=='subtitle_redo' and undone:done.append(undone.pop())
            stack=done if direction=='undo' else undone
            if not stack:raise EditorError('empty_history','Bu yönde altyazı işlemi yok.',409)
            event=stack[-1];expected=event['after' if direction=='undo' else 'before']
            if current['id']!=expected:raise EditorError('stale_subtitle','Altyazı başka işlemde değiştirilmiş. Sürümlerden seçin.',409)
            target=event['before' if direction=='undo' else 'after']
            result=self.editor.subtitles.activate(pid,target,{'confirm':True})
            self.save(pid,{**scope,'preferences':event['preferences_before' if direction=='undo' else 'preferences_after']})
            with closing(self.projects._connection()) as c,c:c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,scope['plan_id'],'subtitle_'+direction,json.dumps({'before':current['id'],'after':target}),now()))
            return result

    def approve(self,pid,did,payload):
        if set(payload)!={'confirmed','clip_ids'} or payload['confirmed'] is not True or not isinstance(payload['clip_ids'],list):raise EditorError('confirmation_required','Uygulanacak taslak öğelerini seçip onaylayın.')
        with self.projects.lock:
            state=self.advanced.get(pid)
            with closing(self.projects._connection()) as c:
                rows=c.execute("SELECT payload_json FROM editorial_events WHERE project_id=? AND plan_id=? AND kind='draft'",(pid,state['plan_id'])).fetchall()
                applied=c.execute("SELECT payload_json FROM editorial_events WHERE project_id=? AND plan_id=? AND kind='approved'",(pid,state['plan_id'])).fetchall()
            draft=next((json.loads(r[0]) for r in rows if json.loads(r[0])['id']==did),None)
            if not draft or draft['base_revision']!=state['revision'] or any(json.loads(r[0])['draft_id']==did for r in applied):raise EditorError('stale_draft','Taslak eski veya daha önce uygulanmış. Güncel kurgu üzerinden yeni taslak oluşturun.',409)
            selected=set(payload['clip_ids']);available={x['id'] for x in draft['clips']}|{'adjustment:'+x['slot_id'] for x in draft.get('adjustments',[])}|{'transition:'+x['slot_id'] for x in draft.get('transitions',[])}
            if not selected or not selected<=available:raise EditorError('invalid_draft','Geçerli taslak öğelerini seçin.')
            doc=deepcopy(state['document']);doc['clips'] += [x for x in draft['clips'] if x['id'] in selected]
            doc['adjustments'] += [x for x in draft.get('adjustments',[]) if 'adjustment:'+x['slot_id'] in selected]
            doc['transitions'] += [x for x in draft.get('transitions',[]) if 'transition:'+x['slot_id'] in selected]
            result=self.advanced.save(pid,{**state,'document':doc})
            with closing(self.projects._connection()) as c,c:
                c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,state['plan_id'],'approved',json.dumps({'draft_id':did,'revision':result['revision']}),now()))
            prefs=self.get(pid);prefs['preferences'].update(approved_editorial_revision=did,media_preparation_mode='sources_only')
            if draft['source']=='automatic':prefs['preferences']['editing_mode']='approved_auto'
            self.save(pid,prefs)
            return result
