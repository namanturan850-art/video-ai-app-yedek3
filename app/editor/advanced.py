"""Versioned supplementary editing over an immutable narration clock.

Documents are scoped to a project AND active production plan. No media file,
base slot, subtitle or narration is deleted when a supplementary clip is removed.
"""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.editor.models import EditorError
from app.projects import now

STATEMENTS = (
    '''CREATE TABLE IF NOT EXISTS editor_documents (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plan_id TEXT NOT NULL, revision INTEGER NOT NULL, payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL, PRIMARY KEY(project_id,plan_id))''',
    '''CREATE TABLE IF NOT EXISTS editor_document_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        plan_id TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS editor_document_events_scope ON editor_document_events(project_id,plan_id,id)',
)


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)


class Transform(Strict):
    x: float=Field(default=0,ge=-1920,le=1920)
    y: float=Field(default=0,ge=-1080,le=1080)
    scale: float=Field(default=1,ge=.1,le=2)
    rotation: float=Field(default=0,ge=-180,le=180)
    opacity: float=Field(default=1,ge=0,le=1)
    volume: float=Field(default=0,ge=0,le=2)
    speed: float=Field(default=1,ge=.25,le=4)
    flip_x: bool=False
    flip_y: bool=False
    crop_left: float=Field(default=0,ge=0,le=.45)
    crop_right: float=Field(default=0,ge=0,le=.45)
    crop_top: float=Field(default=0,ge=0,le=.45)
    crop_bottom: float=Field(default=0,ge=0,le=.45)


class Effects(Strict):
    brightness: float=Field(default=0,ge=-.5,le=.5)
    contrast: float=Field(default=1,ge=.2,le=3)
    saturation: float=Field(default=1,ge=0,le=3)
    blur: float=Field(default=0,ge=0,le=10)
    sharpen: float=Field(default=0,ge=0,le=2)
    monochrome: bool=False
    vignette: bool=False
    enabled: bool=True


class Keyframe(Strict):
    curve_version: Literal[1]=1
    property: Literal['x','y','scale','rotation','opacity','volume']
    time: float=Field(ge=0)
    value: float
    interpolation: Literal['linear','ease_in','ease_out','ease_in_out','hold','bezier']='linear'
    bezier: list[float]=Field(default_factory=lambda:[1/3,0.,2/3,1.],min_length=4,max_length=4)

    @model_validator(mode='after')
    def valid(self):
        Transform.model_validate({self.property:self.value})
        x1,y1,x2,y2=self.bezier
        if not (0<=x1<=x2<=1 and 0<=y1<=1 and 0<=y2<=1):raise ValueError("Bezier kolları 0–1 aralığında, zaman kolları sıralı olmalıdır.")
        return self


class MotionElementEdit(Strict):
    source_signature: str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    index: int=Field(ge=0,le=2000)
    visible: bool=True
    x: float=Field(default=0,ge=-1920,le=1920)
    y: float=Field(default=0,ge=-1080,le=1080)
    opacity: float=Field(default=1,ge=0,le=1)
    color: str|None=Field(default=None,pattern=r'^#[0-9A-Fa-f]{6}$')
    text: str|None=Field(default=None,max_length=400)
    start: float=Field(default=0,ge=0)
    end: float|None=Field(default=None,gt=0)
    keyframes: list[Keyframe]=Field(default_factory=list,max_length=128)

    @model_validator(mode='after')
    def valid(self):
        if self.end is not None and self.end<=self.start:raise ValueError('Nesne zaman aralığı geçersiz.')
        if any(k.property not in ('x','y','opacity') for k in self.keyframes):raise ValueError('Nesnede yalnız X/Y ve saydamlık keyframe desteklenir.')
        if len({(k.property,k.time) for k in self.keyframes})!=len(self.keyframes):raise ValueError('Yinelenen nesne keyframe.')
        return self


class Media(Strict):
    provider: str=Field(min_length=1,max_length=32,pattern=r'^[a-z0-9_-]+$')
    media_id: str=Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9_-]+$')
    sha256: str=Field(pattern=r'^[a-f0-9]{64}$')


class Editable(Strict):
    animation_offset: float=Field(default=0,ge=0)
    animation_duration: float|None=Field(default=None,gt=0)
    transform: Transform=Field(default_factory=Transform)
    effects: Effects=Field(default_factory=Effects)
    keyframes: list[Keyframe]=Field(default_factory=list,max_length=128)
    fade_in: float=Field(default=0,ge=0,le=3)
    fade_out: float=Field(default=0,ge=0,le=3)

    @model_validator(mode='after')
    def unique_points(self):
        if len({(k.property,k.time) for k in self.keyframes})!=len(self.keyframes):raise ValueError('Aynı özellik/zamanda iki keyframe olamaz.')
        return self


class Clip(Editable):
    id: str=Field(pattern=r'^[a-f0-9]{32}$')
    track: Literal['emphasis','layers','maps','infographics','visuals','audio']
    kind: Literal['media','text','motion','shape']='media'
    start: float=Field(ge=0)
    end: float=Field(gt=0)
    source_start: float=Field(default=0,ge=0)
    media: Media | None=None
    text: str=Field(default='',max_length=400)
    color: str=Field(default='#FFFFFF',pattern=r'^#[0-9A-Fa-f]{6}$')
    font_size: int=Field(default=64,ge=18,le=160)
    font: Literal['inter','montserrat','oswald','bebas','lora']='inter'
    font_weight: Literal['normal','bold']='normal'
    text_align: Literal['left','center','right']='center'
    text_width: float=Field(default=.84,ge=.1,le=.9)
    text_background: str|None=Field(default=None,pattern=r'^#[0-9A-Fa-f]{6}$')
    background_opacity: float=Field(default=.65,ge=0,le=1)
    clean_map: bool=False
    motion_color: str|None=Field(default=None,pattern=r'^#[0-9A-Fa-f]{6}$')
    shape: Literal['pin','arrow','rectangle']='pin'
    shape_size: float=Field(default=.1,ge=.02,le=.5)
    audio_role: Literal['source','music','sfx']='source'
    ducking: bool=False
    origin: Literal['manual','automatic','json']='manual'
    source_key: str|None=Field(default=None,max_length=64)
    motion_elements: list[MotionElementEdit]=Field(default_factory=list,max_length=2000)
    motion: dict | None=None
    motion_sources: list[Media]=Field(default_factory=list,max_length=2)
    visible: bool=True
    locked: bool=False
    order: int=Field(default=0,ge=0,le=1000)
    legacy_key: str|None=Field(default=None,max_length=160)

    @model_validator(mode='after')
    def valid(self):
        if self.end-self.start<1/30: raise ValueError('Klip en az bir kare olmalı.')
        if self.motion_elements and self.kind!='motion':raise ValueError('Düz kaynakta bağımsız motion nesnesi bulunmaz.')
        if len({e.index for e in self.motion_elements})!=len(self.motion_elements):raise ValueError('Yinelenen motion nesnesi.')
        if self.kind=='media' and self.media is None:raise ValueError('Medya kimliği eksik.')
        if self.kind=='text' and (not self.text.strip() or self.track=='audio'):raise ValueError('Metin ve iz geçersiz.')
        if self.kind=='motion' and (not self.motion or self.track=='audio'):raise ValueError('Motion ve iz geçersiz.')
        if self.kind=='shape' and self.track=='audio':raise ValueError('Görsel işaret Ses izine eklenemez.')
        if self.ducking and self.track!='audio':raise ValueError('Ducking yalnız ek ses klibinde desteklenir.')
        if self.clean_map and (self.kind!='motion' or self.motion.get('template')!='map'):raise ValueError('Temiz kaynak modu yalnız yerel map şablonunda desteklenir.')
        if self.animation_duration is not None and self.animation_offset+self.end-self.start>self.animation_duration+.001:raise ValueError('Animasyon kesiti kaynak zamanını aşıyor.')
        if self.animation_offset and self.animation_duration is None:raise ValueError('Animasyon kaynak süresi eksik.')
        if any(k.time>(self.animation_duration or self.end-self.start)+.001 for k in self.keyframes):raise ValueError('Keyframe klip süresini aşıyor.')
        if len({(k.property,k.time) for k in self.keyframes})!=len(self.keyframes):raise ValueError('Aynı özellik/zamanda iki keyframe olamaz.')
        if self.fade_in+self.fade_out>(self.animation_duration or self.end-self.start):raise ValueError('Fade süreleri klibi aşıyor.')
        return self


class Adjustment(Editable):
    slot_id: str=Field(min_length=1,max_length=128)


class Marker(Strict):
    id: str=Field(pattern=r'^[a-f0-9]{32}$')
    time: float=Field(ge=0)
    name: str=Field(min_length=1,max_length=120)
    note: str=Field(default='',max_length=2000)
    color: str=Field(default='#8065E8',pattern=r'^#[0-9A-Fa-f]{6}$')


class Transition(Strict):
    slot_id: str
    next_slot_id: str
    kind: Literal['cut','cross_dissolve','dip_black','wipe']='cut'
    duration: float=Field(default=.3,ge=0,le=2)


class Document(Strict):
    schema_version: Literal[1]=1
    clips: list[Clip]=Field(default_factory=list,max_length=200)
    adjustments: list[Adjustment]=Field(default_factory=list,max_length=500)
    markers: list[Marker]=Field(default_factory=list,max_length=500)
    transitions: list[Transition]=Field(default_factory=list,max_length=500)
    suppressed_scenes: list[str]=Field(default_factory=list,max_length=500)
    suppressed_layers: list[str]=Field(default_factory=list,max_length=500)
    empty_slots: list[str]=Field(default_factory=list,max_length=500)
    disabled_slots: list[str]=Field(default_factory=list,max_length=500)

    @model_validator(mode='after')
    def unique(self):
        for values,key in ((self.clips,'id'),(self.adjustments,'slot_id'),(self.markers,'id'),(self.transitions,'slot_id')):
            ids=[getattr(v,key) for v in values]
            if len(ids)!=len(set(ids)):raise ValueError('Yinelenen kayıt kimliği.')
        return self


def read_document(projects,pid,plan_id):
    if not hasattr(projects,'_connection') or not hasattr(projects,'_row'):return {'plan_id':plan_id,'revision':0,'document':Document().model_dump()}
    with closing(projects._connection()) as c:
        row=c.execute('SELECT * FROM editor_documents WHERE project_id=? AND plan_id=?',(pid,plan_id)).fetchone()
    return {'plan_id':plan_id,'revision':row['revision'] if row else 0,
            'document':json.loads(row['payload_json']) if row else Document().model_dump()}


class AdvancedEditor:
    def __init__(self,editor):self.editor=editor;self.projects=editor.projects

    def get(self,pid):
        with self.projects.lock:
            plan=self.editor._active(pid)
            return read_document(self.projects,pid,plan['plan_id'])

    def validate(self,pid,document,old):
        old=Document.model_validate(old).model_dump()
        try: validated=Document.model_validate(document).model_dump()
        except ValidationError as error:
            detail='; '.join('.'.join(map(str,e['loc']))+': '+e['msg'] for e in error.errors(include_input=False)[:6])
            raise EditorError('invalid_document','Kurgu verisi geçersiz: '+detail) from None
        view=self.editor.view(pid);duration=view['duration']
        for scene_id in set(old.get('suppressed_scenes',[]))^set(validated['suppressed_scenes']):
            scene=next((s for s in view['scenes'] if s['scene_id']==scene_id),None)
            if not scene or scene['locked']:raise EditorError('locked','Plan katmanı eksik veya sahne kilitli.',409)
        legacy={x['legacy_key']:x for items in view['tracks'].values() for x in items if x.get('legacy_key')}
        for key in set(old.get('suppressed_layers',[]))^set(validated['suppressed_layers']):
            item=legacy.get(key);scene=next((s for s in view['scenes'] if item and s['scene_id']==item['scene_id']),None)
            if not scene or scene['locked']:raise EditorError('locked','Kaynak plan katmanı eksik veya kilitli.',409)
        slots={x['slot_id']:x for track in view['tracks'].values() for x in track if x.get('slot_id')}
        for field in ('empty_slots','disabled_slots'):
            for sid in set(old.get(field,[]))^set(validated[field]):
                slot=slots.get(sid)
                if not slot or slot['locked']:raise EditorError('locked','Bu yuva eksik veya kilitli. Önce kilidini açın.',409)
        old_clips={c['id']:c for c in old['clips']}
        for clip in validated['clips']:
            if clip.get('animation_duration') and clip['animation_duration']>duration+.001:raise EditorError('invalid_animation','Animasyon kaynak süresi ana anlatımı aşamaz.')
            if clip['end']>duration+.001:raise EditorError('clip_outside','Ek klip anlatım süresinin dışına çıkamaz.')
            previous=old_clips.get(clip['id'])
            changed=previous!=clip
            if previous and previous['locked'] and {**previous,'locked':clip['locked']}!=clip:
                raise EditorError('locked','Bu ek klip kilitli. Önce kilidini açın.',409)
            if changed and any(s['locked'] and (clip['start']<s['end'] and clip['end']>s['start'] or previous and previous['start']<s['end'] and previous['end']>s['start']) for s in view['scenes']):
                raise EditorError('locked','Kilitli sahnenin üzerine ek klip düzenlenemez.',409)
            if clip['kind']!='media' and (clip['transform']['speed']!=1 or clip['transform']['volume'] or any(k['property']=='volume' for k in clip['keyframes'])):
                raise EditorError('silent_layer','Metin ve ek motion katmanında kaynak sesi/hız değişikliği desteklenmiyor.')
            if clip['kind']=='media':
                from app.editor.service import sha256_file
                path,asset=self.editor.archive_file(pid,clip['media']['provider'],clip['media']['media_id'])
                verifier=getattr(getattr(self.editor.stock,'downloader',None),'verified_hash',None)
                actual=verifier(path,clip['media']['sha256']) if verifier else sha256_file(path)
                if actual!=clip['media']['sha256']:raise EditorError('stale_media','Kaynak dosya değişmiş; arşivi yenileyin.',409)
                if (asset['media_type']=='audio')!=(clip['track']=='audio'):raise EditorError('invalid_media_type','Ses dosyası Ses izine; video/görsel görsel izlere eklenir.')
                if asset['media_type']=='image' and clip['transform']['speed']!=1:raise EditorError('still_speed','Durağan görselin oynatma hızı değiştirilemez.')
                if clip['track']=='audio':
                    visual_values={k:v for k,v in clip['transform'].items() if k not in ('volume','speed')}
                    defaults={k:v for k,v in Transform().model_dump().items() if k not in ('volume','speed')}
                    if visual_values!=defaults or clip['effects']!=Effects().model_dump() or any(k['property']!='volume' for k in clip['keyframes']):
                        raise EditorError('audio_controls','Ses klibinde yalnız ses seviyesi/keyframe, hız, kesit ve fade düzenlenir.')
                if (clip['transform']['volume'] or any(k['property']=='volume' for k in clip['keyframes'])) and not (asset.get('has_audio') or asset['media_type']=='audio'):
                    raise EditorError('no_source_audio','Kaynakta doğrulanmış ses akışı yok. Kaynak ses seviyesi sıfır kalmalıdır.')
                if asset['media_type']=='video':
                    from app.rendering.source_timing import editor_coverage
                    from app.rendering.tools import discover
                    editor_coverage(path,discover().get('ffprobe'),clip['source_start'],None,clip['transform']['speed'],clip['end']-clip['start'],f"Ek görüntü {clip['id']}, {clip['start']:.3f} sn")
                elif asset['media_type']=='audio':
                    needed=clip['source_start']+(clip['end']-clip['start'])*clip['transform']['speed']
                    if not asset.get('duration') or needed>asset['duration']+.04:raise EditorError('short_source','Kaynak süresi, kesit ve hız için yetersiz.')
            if clip['kind']=='motion':
                from app.motion.templates import validate
                scene=next((s for s in view['scenes'] if s['start']<=clip['start']<s['end']),None)
                try:clip['motion']=validate({**clip['motion'],'local_only':True},scene['narration'] if scene else '')
                except (ValueError,RuntimeError) as e:raise EditorError('invalid_motion','Animasyon şeması/anlatımı geçersiz: '+str(e)) from None
                if clip['motion']['template'] in ('mark','archive','beforeafter'):
                    from pathlib import Path
                    from app.editor.service import sha256_file
                    data=clip['motion']['data'];names=data.get('images',[]) if clip['motion']['template']=='beforeafter' else [data.get('image')]
                    archive=self.editor.archive(pid)['items'];refs=[]
                    for name in names:
                        asset=next((a for a in archive if a['media_type']=='image' and a['file_name']==name),None)
                        if not asset or Path(str(name)).name!=name:raise EditorError('invalid_motion_image','Animasyon için bu projenin arşivindeki görsel dosya adını seçin.')
                        path,_=self.editor.archive_file(pid,asset['provider'],asset['media_id'])
                        ref={k:asset[k] for k in ('provider','media_id','sha256')}
                        if sha256_file(path)!=ref['sha256']:raise EditorError('stale_media','Animasyonun görsel kaynağı değişmiş.',409)
                        refs.append(ref)
                    clip['motion_sources']=refs
                # Catch incomplete extended-template fields before any save/job.
                # Building a local scene does not render frames or contact providers.
                from app.channels import DEFAULT_STYLE
                from app.motion.templates import build
                from app.motion.clips import with_pictures
                from app.motion.places import offline
                try:
                    with offline():
                        spec=with_pictures({**clip['motion'],'local_only':True},self.projects._path(pid)/'stock')
                        channels=getattr(getattr(self.editor,'rendering',None),'channels',None)
                        kit=deepcopy(channels.for_project(pid)['style'] if channels else DEFAULT_STYLE)
                        if clip.get('motion_color'):kit['palette']['accent']=clip['motion_color']
                        spec={**spec,'clean_source':clip.get('clean_map',False)}
                        scene=build(spec,kit,clip.get('animation_duration') or clip['end']-clip['start'],0,self.projects.get(pid)['language'])
                        from app.editor.motion_objects import validate_edits
                        validate_edits(scene,clip['motion_elements'])
                except (ValueError,RuntimeError,KeyError,TypeError,IndexError):raise EditorError('invalid_motion','Animasyon verisi, görseli veya nesne kaynağı değişmiş/geçersiz. Şablonu/arşivi kontrol edin; kaynak değiştiyse nesne düzenlemelerini sıfırlayın.') from None
        for previous in old['clips']:
            if previous['id'] not in {c['id'] for c in validated['clips']} and (previous['locked'] or any(s['locked'] and previous['start']<s['end'] and previous['end']>s['start'] for s in view['scenes'])):
                raise EditorError('locked','Kilitli ek klip silinemez.',409)
        before={a['slot_id']:a for a in old['adjustments']}
        after={a['slot_id']:a for a in validated['adjustments']}
        for sid in set(before)|set(after):
            slot=slots.get(sid)
            if not slot:raise EditorError('stale_slot','Ana klip değişti. Editörü yenileyin.',409)
            if before.get(sid)!=after.get(sid) and slot['locked']:raise EditorError('locked','Kilitli ana klip değiştirilemez.',409)
            item=after.get(sid)
            if item:
                duration=slot['end']-slot['start']
                animation_length=item.get('animation_duration') or duration
                if item.get('animation_offset',0)+duration>animation_length+.001 or animation_length>view['duration']+.001:raise EditorError('invalid_animation','Ana klibin animasyon kaynak saati geçersiz.')
                if item['fade_in']+item['fade_out']>animation_length:raise EditorError('invalid_fade','Fade süreleri ana klibi aşıyor.')
                if any(k['time']>animation_length+.001 for k in item['keyframes']):raise EditorError('invalid_keyframe','Keyframe ana klip süresini aşıyor.')
                # Main-clock speed is applied only with enough actual source coverage.
                asset=slot.get('media') or {}
                if asset.get('media_type')!='video' and item['transform']['speed']!=1:raise EditorError('still_speed','Yalnız kaynak videonun oynatma hızı değiştirilebilir.')
                if (item['transform']['volume'] or any(k['property']=='volume' for k in item['keyframes'])) and not asset.get('has_audio'):
                    raise EditorError('no_source_audio','Kaynakta doğrulanmış ses akışı yok. Kaynak ses seviyesi sıfır kalmalıdır.')
                if asset.get('media_type')=='video' and item['transform']['speed']!=1:
                    from app.stock.download import asset_path
                    from app.rendering.source_timing import editor_coverage
                    from app.rendering.tools import discover
                    editor_coverage(asset_path(self.projects,pid,asset),discover().get('ffprobe'),slot.get('clip_start') or 0,slot.get('clip_end'),item['transform']['speed'],duration,f"Sahne {slot['scene_id']}, {slot['start']:.3f} sn")
        for marker in validated['markers']:
            if marker['time']>view['duration']:
                raise EditorError('invalid_marker','İşaretleyici anlatım süresini aşıyor.')
        previous_transitions={t['slot_id']:t for t in old['transitions']}
        next_transitions={t['slot_id']:t for t in validated['transitions']}
        for sid in set(previous_transitions)|set(next_transitions):
            previous=previous_transitions.get(sid);current=next_transitions.get(sid)
            if previous!=current and any(slots.get(t.get(key),{}).get('locked') for t in (previous or {},current or {}) for key in ('slot_id','next_slot_id')):
                raise EditorError('locked','Kilitli klibin geçişi değiştirilemez.',409)
        for transition in validated['transitions']:
            first=slots.get(transition['slot_id']);second=slots.get(transition['next_slot_id'])
            if not first or not second or abs(first['end']-second['start'])>.04:raise EditorError('invalid_transition','Geçiş bitişik iki ana klip arasında olmalıdır.')
            from app.rendering.source_timing import verified_slot
            if previous_transitions.get(transition['slot_id'])!=transition:first=verified_slot(self.editor,pid,first)
            from app.editor.transition_handles import problem
            failure=problem(first,second,transition,validated['adjustments'])
            if failure:
                raise EditorError(failure['category'],failure['message'],details=[failure['limits']])
        return validated

    def save(self,pid,payload,kind='edit'):
        if not isinstance(payload,dict) or set(payload)!={'plan_id','revision','document'} or type(payload['revision'])is not int:
            raise EditorError('invalid_document','Plan, revizyon ve düzenleme belgesini kontrol edin.')
        with self.projects.lock:
            current=self.get(pid)
            if (payload['plan_id'],payload['revision'])!=(current['plan_id'],current['revision']):raise EditorError('stale_revision','Kurgu revizyonu değişti. Yenileyin.',409)
            # Do not change advanced state while a render/stock process owns the project.
            with closing(self.projects._connection()) as c:self.editor.stock._idle(c,pid)
            with closing(self.projects._connection()) as c:
                if c.execute("SELECT 1 FROM render_jobs WHERE project_id=? AND status IN ('queued','preparing','rendering','validating')",(pid,)).fetchone():
                    raise EditorError('render_busy','Render sürüyor. Kurgu değişikliğinden önce tamamlanmasını bekleyin veya iptal edin.',409)
            document=self.validate(pid,payload['document'],current['document'])
            with closing(self.projects._connection()) as c,c:
                c.execute('INSERT INTO editor_documents VALUES (?,?,?,?,?) ON CONFLICT(project_id,plan_id) DO UPDATE SET revision=excluded.revision,payload_json=excluded.payload_json,updated_at=excluded.updated_at',
                          (pid,current['plan_id'],current['revision']+1,json.dumps(document,ensure_ascii=False),now()))
                c.execute('INSERT INTO editor_document_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',
                          (pid,current['plan_id'],kind,json.dumps({'before':current['document'],'after':document},ensure_ascii=False),now()))
            return self.get(pid)

    def history(self,pid,direction,payload):
        if direction not in ('undo','redo'):raise EditorError('invalid_history','Geçmiş yönü geçersiz.')
        with self.projects.lock:
            current=self.get(pid)
            if payload!={'plan_id':current['plan_id'],'revision':current['revision']}:raise EditorError('stale_revision','Kurgu revizyonu değişti.',409)
            with closing(self.projects._connection()) as c:
                rows=c.execute('SELECT * FROM editor_document_events WHERE project_id=? AND plan_id=? ORDER BY id',(pid,current['plan_id'])).fetchall()
            done=[];undone=[];records={}
            for row in rows:
                record=json.loads(row['payload_json'])
                if row['kind']=='edit':done.append(row['id']);records[row['id']]=record;undone=[]
                elif row['kind']=='undo' and done:undone.append(done.pop())
                elif row['kind']=='redo' and undone:done.append(undone.pop())
            stack=done if direction=='undo' else undone
            if not stack:raise EditorError('empty_history','Bu yönde geri alınabilecek ek kurgu işlemi yok.',409)
            record=records[stack[-1]];target=record['before' if direction=='undo' else 'after']
            expected=record['after' if direction=='undo' else 'before']
            if Document.model_validate(current['document']).model_dump()!=Document.model_validate(expected).model_dump():
                raise EditorError('stale_history','Kurgu başka işlemde değişmiş. Önce ilgili yuva/altyazı işlemini geri alın.',409)
            return self.save(pid,{**payload,'document':target},kind=direction)


def identity(document):
    return hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()
