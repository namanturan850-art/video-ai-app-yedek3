"""A new render projection; never alter the Part 8 master timing contract."""
from copy import deepcopy
import math
from app.rendering.models import RenderError,SOURCE_MESSAGE

FPS=30
EPSILON=.0011


def number(value):return type(value) in (int,float) and math.isfinite(value)


def build(handoff,production):
    if handoff.get('ready') is not True or handoff.get('contract_version')!=1:
        raise RenderError('source_stale',SOURCE_MESSAGE)
    if (handoff.get('source_script_version_id')!=production.get('source_script_version_id')
            or handoff.get('scene_plan_id')!=production.get('plan_id')):
        raise RenderError('source_stale',SOURCE_MESSAGE)
    duration=handoff.get('audio_duration')
    if not number(duration) or not 0<duration<86400:raise RenderError('timeline_invalid','Ses süresi geçersiz. Altyazı ve Zamanlama ekranını kontrol edin.')
    metadata={s['scene_id']:s for s in production['scenes']}
    scenes=handoff['scenes'];scene_ids=[s['scene_id'] for s in scenes]
    if len(metadata)!=len(production['scenes']) or set(scene_ids)!=set(metadata) or len(set(scene_ids))!=len(scene_ids):
        raise RenderError('source_stale',SOURCE_MESSAGE)
    if scene_ids!=[s['scene_id'] for s in production['scenes']]:raise RenderError('source_stale',SOURCE_MESSAGE)
    scene_cursor=0.
    for scene in scenes:
        a,b=scene.get('start'),scene.get('end')
        if not number(a) or not number(b) or b<=a or abs(a-scene_cursor)>EPSILON:
            raise RenderError('timeline_invalid','Sahne zamanları ses süresini sırayla ve boşluksuz kapsamalı.')
        scene_cursor=b
    if abs(scene_cursor-duration)>EPSILON:
        raise RenderError('timeline_invalid','Son sahne sesin sonunda bitmeli.')
    slots=deepcopy(handoff['stock_slots'])
    if not slots:raise RenderError('timeline_invalid','Video için hazır medya yuvası gerekli.')
    cursor=0.;last_scene=-1;last_order=0;seen=set()
    for slot in slots:
        sid=slot['scene_id'];start,end=slot['start'],slot['end']
        if sid not in metadata:raise RenderError('source_stale',SOURCE_MESSAGE)
        index=scene_ids.index(sid)
        if type(slot.get('order')) is not int or slot['order']<1:
            raise RenderError('timeline_invalid','Medya yuvasının sıra numarası geçersiz.')
        if (index<last_scene or (index==last_scene and slot['order']<=last_order)
                or slot['slot_id'] in seen):raise RenderError('timeline_invalid','Medya yuvaları sahne sırasıyla aynı olmalı.')
        if not number(start) or not number(end) or end<=start or start<-.001 or abs(start-cursor)>EPSILON:
            raise RenderError('timeline_invalid','Görsel zaman çizelgesinde boşluk, örtüşme veya geçersiz süre var. Altyazı ve medya planını kontrol edin.')
        if not number(slot['duration']) or abs(slot['duration']-(end-start))>EPSILON:
            raise RenderError('timeline_invalid','Medya yuvasının süresi başlangıç/bitiş ile eşleşmiyor.')
        scene=scenes[index]
        if start<scene['start']-EPSILON or end>scene['end']+EPSILON:raise RenderError('timeline_invalid','Medya yuvası kendi sahne süresini aşıyor.')
        if slot['status']!='complete' or not slot.get('selected_media_local_identity'):
            raise RenderError('input_missing','Bazı yerel medya dosyaları hazır değil.')
        slot['start']=cursor;slot['end']=end;slot['duration']=end-cursor
        slot['start_frame']=round(cursor*FPS);slot['end_frame']=round(end*FPS)
        slot['frames']=slot['end_frame']-slot['start_frame']
        if slot['frames']<1:raise RenderError('timeline_invalid','Bir medya yuvası bir video karesinden kısa. Zamanlamayı kontrol edin.')
        slot['editing']={k:metadata[sid].get(k,'') for k in ('transition','motion','overlay_text','composition')}
        cursor=end;last_scene=index;last_order=slot['order'];seen.add(slot['slot_id'])
    if abs(cursor-duration)>EPSILON or {s['scene_id'] for s in slots}!=set(scene_ids):
        raise RenderError('timeline_invalid','Görsel zaman çizelgesi ses süresinin tamamını kapsamıyor.')
    slots[-1].update(end=duration,duration=duration-slots[-1]['start'],end_frame=round(duration*FPS))
    slots[-1]['frames']=slots[-1]['end_frame']-slots[-1]['start_frame']
    return {'duration':duration,'frames':round(duration*FPS),'fps':FPS,'width':1920,'height':1080,'slots':slots,'scenes':deepcopy(scenes),'editing_scenes':deepcopy(production['scenes'])}
