"""Project editing policy and reviewable drafts; legacy reads never migrate content."""
from contextlib import closing
from copy import deepcopy
import json
import math
from uuid import uuid4

from pydantic import Field
from typing import Literal
from app.editor.advanced import Strict, AdvancedEditor
from app.editor.models import EditorError
from app.projects import now
from app.editor.plan_intervals import SceneIntervals, upsert_slots, import_scope

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

    def save(self,pid,payload,kind='preferences'):
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
                if not any(json.loads(r[0])['draft_id']==prefs['approved_editorial_revision'] and json.loads(r[0]).get('source','automatic')=='automatic' for r in approved):raise EditorError('unapproved','Bu projeye ait onaylı otomatik taslak bulunamadı.')
            if prefs['editing_mode']!='legacy':prefs['media_preparation_mode']='sources_only'
            else:prefs.update(media_preparation_mode='legacy',legacy_decorations=True)
            with closing(self.projects._connection()) as c,c:
                c.execute('INSERT INTO editorial_state VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET revision=excluded.revision,payload_json=excluded.payload_json,updated_at=excluded.updated_at',(pid,old['revision']+1,json.dumps(prefs),now()))
                c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,old['plan_id'],kind,json.dumps({'before':old['preferences'],'after':prefs}),now()))
            return self.get(pid)

    def draft(self,pid,clips,source='automatic',adjustments=None,transitions=None,details=None,*,persist=True):
        state=self.advanced.get(pid);doc=deepcopy(state['document'])
        for i,clip in enumerate(clips):clip.setdefault('order',len(doc['clips'])+i)
        doc['clips']+=clips
        doc['adjustments']=upsert_slots(doc['adjustments'],adjustments or []) if source=='json' else doc['adjustments']+(adjustments or [])
        doc['transitions']+=transitions or []
        # Validate without committing: no plan, source, or user edit changes here.
        normalized=self.advanced.validate(pid,doc,state['document'])
        draft={'id':uuid4().hex,'source':source,'base_revision':state['revision'],'clips':normalized['clips'][len(state['document']['clips']):],
               'adjustments':[x for x in normalized['adjustments'] if x['slot_id'] in {a['slot_id'] for a in (adjustments or [])}],
               'transitions':normalized['transitions'][len(state['document']['transitions']):],
               'plan_id':state['plan_id'],'created_at':now(),**(details or {})}
        if persist:
            with closing(self.projects._connection()) as c,c:
                c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,state['plan_id'],'draft',json.dumps(draft),now()))
        return draft

    def automatic(self,pid):
        from hashlib import sha256
        view=self.editor.view(pid);clips=[];document=self.advanced.get(pid)['document'];current=document['clips'];transitions=[];warnings=[]
        slots=sorted((x for values in view['tracks'].values() for x in values if x.get('slot_id')),key=lambda x:x['start'])
        for scene in view['scenes']:
            if scene['locked']:continue
            # Extract only actual narration words; no inferred names, dates or numbers.
            text=' '.join(scene['narration'].split()[:7])
            key=sha256(json.dumps([scene['scene_id'],text]).encode()).hexdigest()
            repeated=any(c.get('source_key')==key or c.get('text')==text and c['start']==scene['start'] for c in current)
            if not repeated and text and scene['end']-scene['start']>=1/30 and not (view['editorial']['legacy_decorations'] and scene.get('overlay_text')==text):
                clips.append({'id':uuid4().hex,'kind':'text','track':'emphasis','start':scene['start'],'end':min(scene['end'],scene['start']+3),
                              'text':text,'color':'#FFFFFF','order':100,'origin':'automatic','source_key':key})
            for overlay in scene['naman_overlays']:
                if overlay.get('kind') not in ('map','infographic') or not overlay.get('template'):continue
                key=sha256(json.dumps([scene['scene_id'],overlay],sort_keys=True).encode()).hexdigest()
                if any(c.get('source_key')==key for c in current):continue
                if any(s['scene_id']==scene['scene_id'] and s.get('motion_spec',{}).get('template')==overlay['template'] and s['motion_spec']['data']==overlay.get('data') for s in slots):continue
                clip={'id':uuid4().hex,'kind':'motion','track':'maps' if overlay['kind']=='map' else 'infographics',
                      'start':scene['start'],'end':scene['end'],'motion':{k:overlay[k] for k in ('template','data','emphasis') if k in overlay},
                      'origin':'automatic','source_key':key,'order':10,'clean_map':overlay['template']=='map'}
                try:self.advanced.validate(pid,{**deepcopy(document),'clips':document['clips']+[clip]},document)
                except EditorError as e:warnings.append(f"{scene['scene_id']}: öneri atlandı — {e}");continue
                clips.append(clip)
            last=next((s for s in slots if s['scene_id']==scene['scene_id'] and abs(s['end']-scene['end'])<.04),None)
            nxt=next((s for s in slots if last and abs(s['start']-last['end'])<.04),None)
            transition={'crossfade':'cross_dissolve','fade':'dip_black'}.get(scene.get('transition'))
            if transition and last and nxt and not last['locked'] and not nxt['locked'] and not any(t['slot_id']==last['slot_id'] for t in document['transitions']):
                transitions.append({'slot_id':last['slot_id'],'next_slot_id':nxt['slot_id'],'kind':transition,'duration':min(.2,(last['end']-last['start'])/4,(nxt['end']-nxt['start'])/4)})
        return self.draft(pid,clips,transitions=transitions,details={'changes':[f'{len(clips)} bağımsız katman, {len(transitions)} geçiş önerisi. Yerel deterministik analiz; yeni olgu veya medya üretilmedi.',*warnings]})

    def import_draft(self,pid,payload):
        with self.projects.lock:
            return self._import_draft(pid,payload)

    def validate_response(self,pid,payload):
        with self.projects.lock:
            try:
                draft=self._import_draft(pid,payload,persist=False)
                plan=self.editor._active(pid)
                return {'valid':True,'errors':[],'correction_message':'','changes':draft['changes'],'transition_issues':draft.get('transition_issues',[]),'requires_transition_resolution':any(i['status']=='pending' for i in draft.get('transition_issues',[])),'base_plan_id':plan['plan_id'],'base_revision':plan.get('revision')}
            except EditorError as error:
                return {'valid':False,'errors':[str(error)],'correction_message':str(error),'changes':[]}

    def _import_draft(self,pid,payload,*,persist=True):
        from hashlib import sha256
        plain=deepcopy(payload)
        sections=('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar','animasyon_sahneleri')
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
        intervals=SceneIntervals(slots,current,view.get('fps',30))
        for section in sections:
            for item in payload.get(section,[]):
                scene=scenes[item['scene_id']];start=item.get('start',scene['start']);end=item.get('end',scene['end'])
                if type(start) not in (int,float) or type(end) not in (int,float) or not math.isfinite(start) or not math.isfinite(end) or not scene['start']<=start<end<=scene['end']:
                    raise EditorError('invalid_time',f'{section}: zamanlar kendi sahne aralığında olmalıdır.')
                if 'object_id' in item and (not isinstance(item['object_id'],str) or not 1<=len(item['object_id'])<=160):
                    raise EditorError('invalid_object_id',f'{section}: object_id 1–160 karakterlik metin olmalıdır.')
                identity={**item,'start':float(start),'end':float(end)};identity.pop('object_id',None)
                source_key=sha256(json.dumps([section,identity],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                key=item.get('object_id') or source_key
                if key in seen or source_key in existing:raise EditorError('duplicate','Tekrarlanan JSON nesnesi bulundu. Var olan öğe korunuyor.')
                seen.add(key)
                if section=='animasyon_sahneleri':
                    from app.animation.importing import clips_for
                    clips+=clips_for(item,scene,start,end,slots,source_key,self.editor,pid)
                    continue
                if section=='sahneler':
                    if item.get('composition') not in (None,'wide') or item.get('motion') in ('overlay','emphasis_text') and not item.get('overlay_text'):
                        raise EditorError('unsupported_scene','Bu manuel JSON sahnesinin composition/motion alanı desteklenmiyor. Gerçek X/Y, ölçek veya bağımsız metin katmanı kullanın.')
                    text=item.get('overlay_text')
                    if text:clips.append({'id':uuid4().hex,'kind':'text','track':'layers','start':start,'end':end,'text':text,'origin':'json','source_key':source_key})
                    if 'media' in item:
                        # An imported file choice uses existing supplementary
                        # clips. Never replace/delete the underlying source.
                        if any(s.get('locked') and start<s['end'] and end>s['start'] for s in slots):
                            raise EditorError('locked','Bu aralıkta kilitli görüntü yuvası var; arşiv kesiti üzerine eklenmedi.',409)
                        media_clip={'id':uuid4().hex,'kind':'media','track':'visuals','start':start,'end':end,
                                    'media':item['media'],'source_start':item.get('source_start',0.),'origin':'json','source_key':source_key}
                        motion=item.get('motion','none')
                        if motion in ('pan','slow_zoom','ken_burns'):
                            prop='x' if motion=='pan' else 'scale';low,high=(-100.,100.) if prop=='x' else (1.,1.12)
                            media_clip['keyframes']=[{'property':prop,'time':0.,'value':low},
                                {'property':prop,'time':max(0.,end-start-1/30),'value':high}]
                            if end-start<=1/30+1e-6:media_clip['keyframes']=media_clip['keyframes'][:1]
                        clips.append(media_clip)
                    else:intervals.add(scene,item,start,end)
                    continue
                track={'infografikler':'infographics','harita_sahneleri':'maps','vurgular':'emphasis','katmanlar':'layers'}[section]
                clip={'id':uuid4().hex,'kind':'motion' if section in ('infografikler','harita_sahneleri') else 'text',
                      'track':track,'start':start,'end':end,'origin':'json','source_key':source_key}
                if clip['kind']=='motion':
                    clip['motion']={k:item[k] for k in ('template','data','emphasis') if k in item}
                    if any(s['scene_id']==scene['scene_id'] and s.get('motion_spec',{}).get('template')==item['template'] and s['motion_spec']['data']==item['data'] for s in slots):
                        raise EditorError('duplicate_motion','Bu animasyon zaten temel medya yuvasında. Aynı öğe ikinci kez eklenmedi.')
                else:
                    clip['text']=item['text'];duration=end-start
                    if item.get('effect')=='pulse':clip['keyframes']=[{'property':'scale','time':0.,'value':1.},{'property':'scale','time':duration*.2,'value':1.08},{'property':'scale','time':duration*.5,'value':1.}]
                    if item.get('effect')=='glitch':clip['keyframes']=[{'property':'x','time':0.,'value':0.},{'property':'x','time':duration*.1,'value':8.},{'property':'x','time':duration*.2,'value':-6.},{'property':'x','time':duration*.3,'value':0.}]
                clips.append(clip)
        adjustments,transitions,interval_changes=intervals.compile()
        details={'transition_issues':intervals.transition_issues,'import_scope':import_scope(view),'changes':checked['changes']+interval_changes,'overlapping_manual_ids':[c['id'] for c in current['clips'] if any(c['start']<x['end'] and c['end']>x['start'] for x in clips)]}
        if payload.get('animasyon_sahneleri'):
            details['animation_subtitle_version']=view.get('subtitle_version_id')
        return self.draft(pid,clips,'json',adjustments,transitions,details,persist=persist)

    def drafts(self,pid,limit=100):
        state=self.advanced.get(pid)
        with closing(self.projects._connection()) as c:
            rows=c.execute("SELECT kind,payload_json FROM editorial_events WHERE project_id=? AND plan_id=? AND kind IN ('draft','approved','transition_resolution') ORDER BY id",(pid,state['plan_id'])).fetchall()
        drafts={}
        for row in rows:
            value=json.loads(row['payload_json'])
            if row['kind']=='draft':drafts[value['id']]={**value,'applied_ids':[],'expected_revision':value['base_revision']}
            elif value['draft_id'] in drafts:
                d=drafts[value['draft_id']]
                if row['kind']=='transition_resolution':
                    for issue in d.get('transition_issues',[]):
                        if issue['id']==value['issue_id']:
                            issue.update(status='resolved',resolution=value['option_id'])
                    d['transitions'].append(value['transition'])
                    d['changes'].append(value['message'])
                else:
                    d['applied_ids']+=value.get('clip_ids',[]);d['expected_revision']=value['revision']
        scope=import_scope(self.editor.view(pid)) if any(d.get('import_scope') for d in drafts.values()) else None
        subtitle_version=self.editor.view(pid).get('subtitle_version_id') if any('animation_subtitle_version' in d for d in drafts.values()) else None
        for d in drafts.values():d['stale']=('animation_subtitle_version' in d and d['animation_subtitle_version']!=subtitle_version) or d['expected_revision']!=state['revision'] or bool(d.get('import_scope') and d['import_scope']!=scope)
        values=list(reversed(list(drafts.values())))
        return {'drafts':values if limit is None else values[:limit]}

    def resolve_transition(self,pid,did,payload):
        if set(payload)!={'confirmed','issue_id','option_id'} or payload['confirmed'] is not True:
            raise EditorError('confirmation_required','Yalnız seçtiğiniz geçiş düzeltmesini açıkça onaylayın.')
        with self.projects.lock:
            self._idle(pid)
            draft=next((d for d in self.drafts(pid,limit=None)['drafts'] if d['id']==did),None)
            if not draft or draft['stale']:raise EditorError('stale_draft','Görüntüler veya kurgu değişti; güncel paketle yeni taslak oluşturun.',409)
            issue=next((i for i in draft.get('transition_issues',[]) if i['id']==payload['issue_id']),None)
            if not issue or issue['status']!='pending':raise EditorError('invalid_resolution','Bekleyen bir geçiş sorunu seçin.')
            option=next((o for o in issue['options'] if o['id']==payload['option_id']),None)
            if not option:raise EditorError('invalid_resolution','Sunulan geçiş düzeltmelerinden birini seçin.')
            state=self.advanced.get(pid);doc=deepcopy(state['document']);used=set(draft['applied_ids'])
            doc['clips'] += [x for x in draft['clips'] if x['id'] not in used]
            doc['adjustments']=upsert_slots(doc['adjustments'],[x for x in draft.get('adjustments',[]) if 'adjustment:'+x['slot_id'] not in used])
            doc['transitions'] += [x for x in draft['transitions'] if 'transition:'+x['slot_id'] not in used]+[option['transition']]
            self.advanced.validate(pid,doc,state['document'])
            message=f"Sahne {issue['scene_id']}, {issue['time']:.3f} sn: kullanıcı {option['label']} seçeneğini onayladı; yalnız bu geçiş taslakta değiştirildi."
            event={'draft_id':did,'issue_id':issue['id'],'option_id':option['id'],'transition':option['transition'],'message':message}
            with closing(self.projects._connection()) as c,c:
                c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,state['plan_id'],'transition_resolution',json.dumps(event),now()))
            return next(d for d in self.drafts(pid,limit=None)['drafts'] if d['id']==did)

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
                    content=lambda q:(q['start'],q['end'],q['text'])
                    if [content(q) for q in old_cues if inside(q)]!=[content(q) for q in cues if inside(q)]:raise EditorError('locked','Kilitli sahnenin altyazısı değiştirilemez.',409)
            result=self.editor.subtitles.edit(pid,current['id'],{'cues':payload['cues']},allow_empty=True,preserve_clock=True)
            before=self.get(pid);after=deepcopy(before['preferences']);after['important_cues']=important
            self.save(pid,{**before,'preferences':after},kind='subtitle_preferences')
            with closing(self.projects._connection()) as c,c:
                c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,before['plan_id'],'subtitle_edit',json.dumps({'before':current['id'],'after':result['active']['id'],'preferences_before':before['preferences'],'preferences_after':after}),now()))
            return result

    def preview(self,pid,did,time):
        from types import SimpleNamespace
        from app.editor.previews import program_frame
        with self.projects.lock:
            draft=next((d for d in self.drafts(pid,limit=None)['drafts'] if d['id']==did),None)
            if not draft or draft['stale']:raise EditorError('stale_draft','Güncel bir taslak seçin; eski taslak uygulanmaz.',409)
            state=self.advanced.get(pid);doc=deepcopy(state['document']);used=set(draft['applied_ids'])
            doc['clips'] += [x for x in draft['clips'] if x['id'] not in used]
            doc['adjustments']=upsert_slots(doc['adjustments'],[x for x in draft.get('adjustments',[]) if 'adjustment:'+x['slot_id'] not in used])
            doc['transitions'] += [x for x in draft.get('transitions',[]) if 'transition:'+x['slot_id'] not in used]
            doc=self.advanced.validate(pid,doc,state['document'])
        # The shared compositor draws a sampled frame; no project save or full render.
        return program_frame(self.editor,SimpleNamespace(get=lambda pid:{**state,'document':doc}),pid,time)

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
            self.save(pid,{**scope,'preferences':event['preferences_before' if direction=='undo' else 'preferences_after']},kind='subtitle_preferences')
            with closing(self.projects._connection()) as c,c:c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,scope['plan_id'],'subtitle_'+direction,json.dumps({'before':current['id'],'after':target}),now()))
            return result

    def approve(self,pid,did,payload):
        if set(payload)!={'confirmed','clip_ids'} or payload['confirmed'] is not True or not isinstance(payload['clip_ids'],list) or any(not isinstance(x,str) for x in payload['clip_ids']):raise EditorError('confirmation_required','Uygulanacak taslak öğelerini seçip onaylayın.')
        with self.projects.lock:
            state=self.advanced.get(pid)
            draft=next((d for d in self.drafts(pid,limit=None)['drafts'] if d['id']==did),None)
            expected=(draft or {}).get('expected_revision')
            if draft and 'animation_subtitle_version' in draft and draft['animation_subtitle_version']!=self.editor.view(pid).get('subtitle_version_id'):
                raise EditorError('stale_draft','Animasyonun altyazı cümleleri değişmiş; güncel paketle yeni taslak oluşturun.',409)
            if draft and draft.get('import_scope') and draft['import_scope']!=import_scope(self.editor.view(pid)):
                raise EditorError('stale_draft','Taslak hazırlanırken görüntü yuvaları, kaynaklar veya kilitler değişti. Güncel paketle yeni taslak oluşturun.',409)
            if not draft or expected!=state['revision']:raise EditorError('stale_draft','Taslak başka düzenlemelerden önce oluşturulmuş. Güncel kurgu üzerinden yeni taslak oluşturun.',409)
            used=set((draft or {}).get('applied_ids',[]))
            selected=set(payload['clip_ids']);available={x['id'] for x in draft['clips']}|{'adjustment:'+x['slot_id'] for x in draft.get('adjustments',[])}|{'transition:'+x['slot_id'] for x in draft.get('transitions',[])}
            if not selected or not selected<=available or selected&used:raise EditorError('invalid_draft','Henüz uygulanmamış geçerli taslak öğelerini seçin.')
            doc=deepcopy(state['document']);doc['clips'] += [x for x in draft['clips'] if x['id'] in selected]
            doc['adjustments']=upsert_slots(doc['adjustments'],[x for x in draft.get('adjustments',[]) if 'adjustment:'+x['slot_id'] in selected])
            doc['transitions'] += [x for x in draft.get('transitions',[]) if 'transition:'+x['slot_id'] in selected]
            prefs_before=self.get(pid)['preferences']
            result=self.advanced.save(pid,{**state,'document':doc})
            prefs_after={**prefs_before,'approved_editorial_revision':did,'media_preparation_mode':'sources_only'}
            if draft['source']=='automatic':prefs_after['editing_mode']='approved_auto'
            with closing(self.projects._connection()) as c,c:
                event_id=c.execute('SELECT MAX(id) FROM editor_document_events WHERE project_id=? AND plan_id=?',(pid,state['plan_id'])).fetchone()[0]
                c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,state['plan_id'],'approved',json.dumps({'draft_id':did,'source':draft['source'],'clip_ids':sorted(selected),'revision':result['revision'],'advanced_event_id':event_id,'preferences_before':prefs_before,'preferences_after':prefs_after}),now()))
            prefs=self.get(pid);prefs['preferences']=prefs_after;self.save(pid,prefs,kind='approval_preferences')
            return result
