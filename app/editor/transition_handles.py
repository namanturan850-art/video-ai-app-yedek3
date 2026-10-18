"""One source-handle calculation for imported proposals and document validation."""
import math

FPS=30  # Native render and editor transition duration contract.
MIN_DURATION=2/FPS


def frame_floor(seconds):
    return max(0,math.floor(seconds*FPS+1e-8))/FPS


def capacity(first, second, adjustments):
    lengths=[s['end']-s['start'] for s in (first,second)]
    frame_lengths=[(round(s['end']*FPS)-round(s['start']*FPS))/FPS for s in (first,second)]
    clip_limit=min(*lengths,*frame_lengths)/4
    source_length=max(lengths[0],frame_lengths[0])
    source=first.get('media') or {}
    speed=next((a.get('transform',{}).get('speed',1.) for a in adjustments if a['slot_id']==first['slot_id']),1.)
    tail=None;duration_known=True
    if source.get('media_type')=='video':
        duration=source.get('duration')
        if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:
            tail=0.;duration_known=False
        else:tail=max(0.,(duration-(first.get('clip_start') or 0))/speed-source_length)
    return {'clip_limit':clip_limit,'tail':tail,'speed':speed,'duration_known':duration_known,
            'blend_max':frame_floor(min(clip_limit,tail)) if tail is not None else frame_floor(clip_limit),
            'dip_max':frame_floor(clip_limit)}


def problem(first, second, record, adjustments):
    if record['kind']=='cut':return None
    limits=capacity(first,second,adjustments)
    where=f"Sahne {first.get('scene_id','?')}, {first['end']:.3f} sn ({first['slot_id']} → {second['slot_id']})"
    if record['duration']<MIN_DURATION-1e-8 or record['duration']>limits['clip_limit']+1e-8:
        return {'category':'invalid_transition','message':where+': geçiş süresi komşu klipler için uygun değil. Daha kısa geçiş veya hard_cut seçin.','limits':limits}
    if record['kind'] in ('cross_dissolve','wipe') and limits['tail'] is not None and record['duration']>limits['tail']+.001/limits['speed']:
        reason=f"ilk kaynak videonun ek süresi yetersiz (gereken {record['duration']:.3f} sn, kullanılabilir {limits['tail']:.3f} sn)" if limits['duration_known'] else 'ilk kaynak videonun süresi doğrulanamadı; kullanılabilir ek süre bilinmiyor'
        return {'category':'short_transition','message':where+': '+reason+'. Daha kısa geçiş, siyaha geçiş veya hard_cut seçin.','limits':limits}
    return None


def issue(first, second, record, adjustments):
    failure=problem(first,second,record,adjustments)
    if not failure:return None
    limits=failure['limits'];options=[]
    if record['kind'] in ('cross_dissolve','wipe') and limits['blend_max']>=MIN_DURATION:
        duration=min(record['duration'],limits['blend_max'])
        options.append({'id':'shorter','label':f'Aynı geçişi {duration:.3f} sn olarak kullan',
                        'transition':{**record,'duration':duration}})
    if limits['dip_max']>=MIN_DURATION:
        duration=min(.2,limits['dip_max'])
        options.append({'id':'dip_black','label':f'Siyaha geçiş kullan ({duration:.3f} sn; ek kaynak süresi gerektirmez)',
                        'transition':{**record,'kind':'dip_black','duration':duration}})
    options.append({'id':'hard_cut','label':'Hard cut / doğrudan kesme kullan',
                    'transition':{**record,'kind':'cut','duration':0.}})
    return {'id':'transition:'+record['slot_id'],'slot_id':record['slot_id'],
            'scene_id':first.get('scene_id'),'time':first['end'],'category':failure['category'],
            'message':failure['message'],'requested':record,'options':options,'status':'pending'}
