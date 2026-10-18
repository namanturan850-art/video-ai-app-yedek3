"""Atomic clip operations; only AdvancedEditor.save can persist a result."""
from copy import deepcopy
from uuid import uuid4

from app.editor.advanced import Document,Strict
from app.editor.models import EditorError
from pydantic import Field
from typing import Literal


class GroupOperation(Strict):
    plan_id: str
    revision: int=Field(ge=0)
    ids: list[str]=Field(min_length=1,max_length=200)
    action: Literal['move','duplicate','delete','visibility','lock','split']
    delta: float=0
    track: str|None=None
    track_delta: int=Field(default=0,ge=-4,le=4)
    value: bool|None=None
    time: float|None=None


def operate(advanced,pid,payload):
    from pydantic import ValidationError
    try:op=GroupOperation.model_validate(payload)
    except ValidationError:raise EditorError('invalid_group','Grup işlemi, zaman farkı ve seçili klipleri kontrol edin.') from None
    with advanced.projects.lock:
        current=advanced.get(pid)
        if (op.plan_id,op.revision)!=(current['plan_id'],current['revision']):raise EditorError('stale_revision','Kurgu revizyonu değişti; yenileyin.',409)
        doc=Document.model_validate(current['document']).model_dump()
        selected=[c for c in doc['clips'] if c['id'] in op.ids]
        if len(selected)!=len(set(op.ids)) or len(set(op.ids))!=len(op.ids):raise EditorError('invalid_group','Seçim eski veya yinelenmiş; klipleri yeniden seçin.')
        if op.action!='lock' and any(c['locked'] for c in selected):raise EditorError('locked','Grupta kilitli klip var; önce kilidi açın.',409)
        result_ids=[]
        for clip in selected:
            if op.action in ('move','duplicate'):
                target=clip
                if op.action=='duplicate':
                    target=deepcopy(clip);target['id']=uuid4().hex;target['legacy_key']=None;target['source_key']=None;doc['clips'].append(target)
                if op.track_delta:
                    tracks=['emphasis','layers','maps','infographics','visuals']
                    if clip['track'] not in tracks or op.track:raise EditorError('invalid_track','Ses izi kaydırılamaz; iz hedefi ile iz farkını birlikte seçmeyin.')
                    index=tracks.index(clip['track'])+op.track_delta
                    if not 0<=index<len(tracks):raise EditorError('invalid_track','Grup görsel iz sınırlarının dışına çıkamaz.')
                    target['track']=tracks[index]
                if op.track:
                    if (op.track=='audio')!=(clip['track']=='audio'):raise EditorError('invalid_track','Ses ve görsel izler birbirine taşınamaz.')
                    target['track']=op.track
                target['start']+=op.delta;target['end']+=op.delta;result_ids.append(target['id'])
            elif op.action=='delete':doc['clips'].remove(clip)
            elif op.action in ('lock','visibility'):
                if op.value is None:raise EditorError('invalid_group','İşlemin açık/kapalı değerini seçin.')
                clip['locked' if op.action=='lock' else 'visible']=op.value
            elif op.action=='split':
                if op.time is None or min(op.time-clip['start'],clip['end']-op.time)<1/30-1e-9:raise EditorError('invalid_split','Bölme noktası her seçili klibin içinde olmalıdır.')
                right=deepcopy(clip);offset=op.time-clip['start'];right['id']=uuid4().hex
                # Restrict the original parametric curve domain, without fitting
                # new handles: identical values AND derivatives on both sides,
                # including repeated splits, fades, hold and arbitrary Bezier.
                clip['animation_duration']=right['animation_duration']=clip['animation_duration'] or clip['end']-clip['start']
                right['animation_offset']+=offset;right['start']=op.time
                right['source_start']+=offset*clip['transform']['speed'];clip['end']=op.time
                right['legacy_key']=None;right['source_key']=None;doc['clips'].append(right);result_ids.extend([clip['id'],right['id']])
        saved=advanced.save(pid,{'plan_id':op.plan_id,'revision':op.revision,'document':doc})
        return {**saved,'selected_ids':result_ids or [c['id'] for c in selected if op.action!='delete']}
