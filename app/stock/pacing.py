"""Explicit visual replanning only. Archives/locks and narration remain intact."""
from copy import deepcopy
from app.stock.models import make_slots


def rebuild(state,handoff,timing=None):
    if state.get('short_pacing_version')==1:return
    timing=timing or {};actual={s['scene_id']:s for s in timing.get('scenes',[])}
    projected={s['slot_id']:s for s in timing.get('stock_slots',[])}
    new=[]
    for scene in handoff['scenes']:
        old=[s for s in state['slots'] if s['scene_id']==scene['scene_id']]
        a=actual.get(scene['scene_id'],{}).get('start',scene['start_estimate'])
        b=actual.get(scene['scene_id'],{}).get('end',scene['end_estimate'])
        span=scene['end_estimate']-scene['start_estimate']
        for s in old:
            mapped=projected.get(s['slot_id'])
            start=mapped['start'] if mapped else a+(s['estimated_start']-scene['start_estimate'])/span*(b-a)
            end=mapped['end'] if mapped else a+(s['estimated_end']-scene['start_estimate'])/span*(b-a)
            if s['locked']:
                new.append(deepcopy(s));continue
            if end-start<=4.5:
                item=deepcopy(s);item.update(pacing_version=1,actual_duration_hint=end-start);new.append(item);continue
            parts=make_slots({**scene,'start_estimate':start,'end_estimate':end,
                '_visual_boundaries':[c['end'] for c in timing.get('subtitles',[]) if start<c['end']<end]})
            # Part 8 projects duration weights, so retain their original scale.
            # Storing audio seconds as weights would move locked neighbours.
            for part in parts:
                part['actual_duration_hint']=part['duration']
                x=s['estimated_start']+(part['estimated_start']-start)/(end-start)*(s['estimated_end']-s['estimated_start'])
                y=s['estimated_start']+(part['estimated_end']-start)/(end-start)*(s['estimated_end']-s['estimated_start'])
                part.update(estimated_start=round(x,6),estimated_end=round(y,6),duration=round(y-x,6))
            # One existing asset may remain attached once. Additional beats are
            # unresolved until a different relevant identity has been selected.
            parts[0].update({k:deepcopy(s[k]) for k in ('selected_media','status','candidates','warnings','message')})
            parts[0]['slot_id']=s['slot_id'];new.extend(parts)
        ordered=[s for s in new if s['scene_id']==scene['scene_id']]
        for i,s in enumerate(ordered):s['order']=i+1
    state['slots']=new;state['short_pacing_version']=1
