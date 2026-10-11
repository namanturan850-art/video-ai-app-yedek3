"""Versioned render-only coverage, never rewrite Part 8 or raw stock slots."""
from copy import deepcopy
import hashlib
import json
import re
from uuid import uuid4
from app.stock import relevance
from app.stock.download import asset_path
from app.stock.identities import identity_keys
from app.scripts.models import ScriptError


def binding(h,state):
    value={'script':h.get('source_script_version_id'),'voice':h.get('narration_version_id'),
           'subtitle':h.get('subtitle_version_id'),'scenes':h.get('scenes'),'cues':h.get('subtitles'),
           'slots':state['slots'],'duration':h.get('audio_duration')}
    # Diagnostic/job/recovery state is not source identity.
    value['slots']=[{k:s.get(k) for k in ('slot_id','scene_id','duration','estimated_start','estimated_end','locked','status','selected_media','visual_check','local_validation')} for s in state['slots']]
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


# A long single framing is no longer static: the renderer splits it with a
# punch-in reframe and moves the camera, so a merged shot may run longer.
VIDEO_MERGE_MAX=10.
IMAGE_MERGE_MAX=9.
CONTINUATION_MAX=6.
CHAIN_MAX=14.


def merge_limit(m):
    return min(VIDEO_MERGE_MAX,float(m.get('duration') or 7)) if m['media_type']=='video' else IMAGE_MERGE_MAX


def build(h,p,state,projects,hash_file):
    result=deepcopy(h);segments=deepcopy(h.get('stock_slots',[]));selected={s['slot_id']:s for s in state['slots']}
    meta={s['scene_id']:s for s in p['scenes']};used=set();assets={};invalid=[]
    for s in segments:
        raw=selected.get(s['slot_id'],{});m=deepcopy(raw.get('selected_media'));s['raw_slot_ids']=[s['slot_id']]
        if m and raw.get('visual_check'):m.setdefault('source_metadata',{})['visual_analysis']=raw['visual_check']
        valid=False
        if m and raw.get('status')=='complete':
            try:
                path=asset_path(projects,h['project_id'],m);digest=hash_file(path)
                profile=relevance.profile(meta[s['scene_id']],raw)
                proof=raw.get('local_validation',{})
                valid=(not m.get('sha256') or digest==m['sha256']) and proof.get('sha256')==digest and not proof.get('error') and proof.get('media_type')==m['media_type']
                valid=valid and raw.get('visual_check',{}).get('verdict')!='mismatch'
                if valid:
                    m.update(width=proof['width'],height=proof['height'])
                    if m['media_type']=='video':m['duration']=proof['duration']
                if not raw.get('locked'):
                    valid=valid and relevance.acceptable(relevance.evaluate(m,profile),profile) and not (identity_keys(m)&used)
                    if m['media_type']=='video':valid=valid and m['width']>m['height'] and m['width']>=1280 and m['height']>=720 and float(m['duration'])+1/30>=s['duration']
                if valid:assets[s['slot_id']]=m;used.update(identity_keys(m))
            except (ScriptError,OSError,KeyError,TypeError,ValueError):valid=False
        s['status']='complete' if valid else 'pending'
        if not valid:s['selected_media_local_identity']=None;invalid.append(s['slot_id'])
    # Merge only adjacent artificial gaps within the SAME semantic scene.
    changed=True
    while changed:
        changed=False
        for i,gap in enumerate(segments):
            if gap['status']=='complete' or gap.get('locked'):continue
            neighbours=[j for j in (i-1,i+1) if 0<=j<len(segments)]
            for j in neighbours:
                anchor=segments[j];m=assets.get(anchor['slot_id'])
                if not m or anchor.get('locked') or anchor['scene_id']!=gap['scene_id']:continue
                length=anchor['duration']+gap['duration']
                limit=merge_limit(m)
                if length>limit+.001:continue
                anchor.update(start=min(anchor['start'],gap['start']),end=max(anchor['end'],gap['end']),duration=length,
                              raw_slot_ids=sorted(anchor['raw_slot_ids']+gap['raw_slot_ids']))
                segments.pop(i);changed=True;break
            if changed:break
    # A gap that no single neighbour can absorb is shared by BOTH same-scene
    # neighbours (left grows forward, right grows backward), each within limit.
    for i,gap in list(enumerate(segments)):
        if gap['status']=='complete' or gap.get('locked') or not 0<i<len(segments)-1:continue
        left,right=segments[i-1],segments[i+1]
        ml,mr=assets.get(left['slot_id']),assets.get(right['slot_id'])
        if not ml or not mr or left.get('locked') or right.get('locked') or left['scene_id']!=gap['scene_id'] or right['scene_id']!=gap['scene_id']:continue
        room_l=merge_limit(ml)-left['duration'];room_r=merge_limit(mr)-right['duration']
        if room_l<.5 or room_r<.5 or room_l+room_r+.001<gap['duration']:continue
        share=min(room_l,max(gap['duration']-room_r,gap['duration']/2));cut=gap['start']+share
        left.update(end=cut,duration=cut-left['start'],raw_slot_ids=sorted(left['raw_slot_ids']+gap['raw_slot_ids']))
        right.update(start=cut,duration=right['end']-cut)
        gap['status']='merged'
    segments=[s for s in segments if s['status']!='merged']
    # Exact existing numerical/factual cue; restrained, never arbitrary filler.
    graphic_seconds=0.
    for s in segments:
        if s['status']=='complete' or s.get('locked') or not 2<=s['duration']<=7:continue
        source=' '.join(meta[s['scene_id']].get('narration_text','').split())
        cue=next((c for c in h.get('subtitles',[]) if c['start']>=s['start']-.001 and c['end']<=s['end']+.001
                  and 2<=len(c['text'].split())<=22 and len(c['text'])<=150
                  and re.search(r'\b\d+(?:[.,]\d+)?\b',c['text']) and ' '.join(c['text'].split()) in source),None)
        if cue and graphic_seconds+s['duration']<=h['audio_duration']*.20:
            s.update(status='complete',graphic_text=cue['text'],selected_media_local_identity={'media_type':'image','graphic':True})
            graphic_seconds+=s['duration']
    # Last resort for short gaps (e.g. a whole scene left empty): the adjacent
    # shot simply keeps running across the boundary from where it stopped — one
    # continuous take, never a second copy of another part of the clip. The
    # renderer reframes it (clear punch-in) so it reads as a deliberate cut.
    continued_seconds=0.
    for i,gap in enumerate(segments):
        if gap['status']=='complete' or gap.get('locked') or gap['duration']>CONTINUATION_MAX:continue
        for j in (i-1,i+1):
            if not 0<=j<len(segments):continue
            anchor=segments[j];root=anchor.get('continuation_of') or anchor['slot_id'];m=assets.get(root)
            if not m or anchor['status']!='complete' or anchor.get('graphic_text') or anchor.get('locked'):continue
            chain=sum(x['duration'] for x in segments if x['slot_id']==root or x.get('continuation_of')==root)+gap['duration']
            if m['media_type']=='video' and chain>float(m.get('duration') or 0)-.6:continue
            if chain>CHAIN_MAX:continue
            gap.update(status='complete',continuation_of=root,selected_media_local_identity=deepcopy(anchor['selected_media_local_identity']))
            continued_seconds+=gap['duration'];break
    uncovered=sum(s['duration'] for s in segments if s['status']!='complete')
    for scene in h.get('scenes',[]):
        for order,s in enumerate((s for s in segments if s['scene_id']==scene['scene_id']),1):s['order']=order
    result['stock_slots']=segments
    # Existing source checks require real scenes/IDs; absent/stale timing cannot
    # become ready merely because the empty set sums to zero.
    complete=bool(segments and h.get('scene_plan_id')==p['plan_id'] and h.get('source_script_version_id')==p['source_script_version_id'])
    result['ready']=complete and uncovered<.001
    if result['ready']:
        # This raw-slot warning is obsolete only after verified effective coverage.
        result['warnings']=[w for w in result.get('warnings',[]) if w!='Bazı stok medya yuvaları veya yerel dosyaları henüz hazır değil.']
    if not invalid:
        # Merely validating an already complete plan is not an editorial change:
        # retain its original contract/fingerprint so existing versions stay current.
        result=deepcopy(h)
    report={'raw_stock_slots':len(state['slots']),'selected_stock_assets':len(assets),
            'unresolved_raw_slots':len(invalid),'effective_render_segments':len(segments),
            'effective_covered_duration':round(h.get('audio_duration',0)-uncovered,3),
            'effective_uncovered_duration':round(uncovered,3),'render_ready':result['ready'],
            'merged_intervals':sum(len(s['raw_slot_ids'])-1 for s in segments),
            'graphic_seconds':round(graphic_seconds,3),'continued_seconds':round(continued_seconds,3)}
    return result,report


def project(h,p,state,projects,hash_file):
    recovery=state.get('recovery_plan')
    if not recovery:return h,None
    if recovery.get('binding')!=binding(h,state):
        return h,{'render_ready':False,'stale':True,'message':'Akıllı kurgu kaynakları değişti. Eksik Medyaları Akıllı Tamamla ile güncelleyin.'}
    effective,report=build(h,p,state,projects,hash_file)
    report['version_id']=recovery['version_id'];return effective,report


def save(service,pid,state,h,p):
    from app.rendering.files import sha256
    from app.stock.download import directory
    from app.projects import now
    h,report=build(h,p,state,service.projects,sha256)
    version=uuid4().hex;value={'version_id':version,'binding':binding(h,state),'created_at':now(),
                            'report':report,'segments':h['stock_slots']}
    # Binding uses the unchanged raw handoff, not reflowed intervals.
    raw=service.timing_handoff(pid);value['binding']=binding(raw,state)
    service._guard(value)
    folder=directory(service.projects,pid)
    import os
    with (folder/('recovery-'+version+'.json')).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
    state['recovery_plan']={k:value[k] for k in ('version_id','binding','created_at','report')}
    return report


def apply_graphics(plan):
    if not plan.get('smart_edit_plan') or not any(s.get('graphic_text') for s in plan['handoff']['stock_slots']):return
    by_id={s['slot_id']:s for s in plan['handoff']['stock_slots']}
    for item in plan['smart_edit_plan']['slots']:
        source=by_id[item['slot_id']]
        if source.get('graphic_text'):
            item.update(layout='fact_card',layout_label='Bilgi kartı',texts=[source['graphic_text']],
                        layout_window={'start':item['start'],'end':item['end']},motion_effect='none',secondary_slot_id=None)
    from app.rendering.smart_edit import digest
    from collections import Counter
    items=plan['smart_edit_plan']['slots'];counts=Counter(s.get('layout','full_broll') for s in items)
    summary=plan['smart_edit_plan']['summary']
    if 'layouts' in summary:summary['layouts']={k:counts[k] for k in summary['layouts']}
    seconds=sum(s['layout_window']['end']-s['layout_window']['start'] for s in items if s.get('layout_window') and s.get('layout')!='full_broll')
    summary.update(graphic_seconds=round(seconds,3),broll_seconds=round(plan['timeline']['duration']-seconds,3),emphasis_texts=sum(len(s.get('texts',[])) for s in items))
    plan['smart_edit_plan']['fingerprint']=digest({k:v for k,v in plan['smart_edit_plan'].items() if k!='fingerprint'})


def materialize(plan,tools,runner):
    for sid,m in plan['media'].items():
        if m['type']!='graphic':continue
        path=plan['temporary']/('graphic-'+hashlib.sha256(sid.encode()).hexdigest()[:20]+'.png')
        runner.run([tools['ffmpeg'],'-v','error','-y','-f','lavfi','-i','color=c=0x101823:s=1920x1080',
                    '-frames:v','1',str(path)],plan['temporary'],phase='input_preflight')
        m.update(path=path,type='image',width=1920,height=1080,was_graphic=True)
