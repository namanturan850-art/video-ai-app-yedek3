"""Pure local render projection. No provider, filesystem or source mutation."""
import hashlib
import json
import re

STYLES={'adaptive':'Uyarlanabilir YouTube','basic':'Temel','balanced':'Dengeli YouTube','dynamic':'Dinamik YouTube'}
MOTIONS={'none':'Yok','push_in':'Yakınlaşma','push_out':'Uzaklaşma','pan_left':'Sola kayma',
         'pan_right':'Sağa kayma','pan_up':'Yukarı kayma','pan_down':'Aşağı kayma','subtle_reframe':'Hafif kadraj değişimi'}
TRANSITIONS={'hard_cut':'Temiz kesme','crossfade':'Yumuşak geçiş','fade_dark':'Koyu geçiş','dip_black':'Kısa kararma','none':'Yok','fade':'Koyu geçiş'}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def clean(text):return ' '.join(text.split()) if isinstance(text,str) else ''


def phrase(text):
    """Only a whole cue or leading clause. Never guess interior word timestamps."""
    text=clean(text)
    if not text or any(ord(c)<32 for c in text) or any(c in text for c in '{}\\'):return None
    candidates=[text]
    match=re.search(r'[,;:!?]|\.(?:\s|$)',text)
    if match:candidates.append(text[:match.start()+1])
    for item in candidates:
        if 2<=len(item.split())<=10 and len(item)<=100 and re.search(r'\w',item):return item
    return None


def emphasis(t,h,style):
    result=[];last=-100.;spacing=28 if style=='balanced' else 18
    meta={s['scene_id']:s for s in t['editing_scenes']}
    for order,scene in enumerate(t['scenes']):
        original=meta[scene['scene_id']];existing=original.get('overlay_text','');importance=original.get('importance',50)
        if existing and isinstance(existing,str) and len(existing)<=500 and not any(ord(c)<32 and c not in '\n\r\t' for c in existing):
            start=scene['start'];end=min(start+3,scene['end']);text=existing;source='scene_overlay';cue_index=None
        else:
            if style=='basic':continue
            if importance<40 and order and scene['start']>=15:continue
            source_text=clean(original.get('narration_text',scene.get('narration_text','')))
            candidates=[]
            for cue in h['subtitles']:
                if cue['start']<scene['start']-.001 or cue['end']>scene['end']+.001:continue
                if cue['start']-last<(spacing-4 if importance>=75 else spacing):continue
                text=phrase(cue['text'])
                if not text or text not in source_text:continue
                start=max(cue['start'],scene['start']);end=min(cue['end'],scene['end'],start+3)
                if end-start<1.5:continue
                # Prefer an exact number/date phrase; otherwise a scene-opening cue.
                candidates.append((int(bool(re.search(r'\d',text))),-cue['start'],text,start,end,cue.get('index')))
            if not candidates:continue
            _,_,text,start,end,cue_index=max(candidates)
            source='subtitle_cue'
        if end-start<.1:continue
        slot=next((s for s in t['slots'] if s['scene_id']==scene['scene_id'] and s['start']<=start<s['end']),None)
        if not slot:continue
        result.append({'scene_id':scene['scene_id'],'slot_id':slot['slot_id'],'text':text,'start':start,'end':end,
                       'style':'upper_left' if original.get('composition') in ('person','close','detail') else 'upper_center',
                       'source':source,'cue_index':cue_index,'punch_in':style!='basic' and (importance>=75 or start<15)})
        last=start
    return result


def motion(scene,index,style,opening):
    explicit=scene.get('motion','none');composition=scene.get('composition','medium');importance=scene.get('importance',50)
    high=composition=='movement' or bool(re.search(r'\b(?:running|driving|flying|racing|laufen|fahren|koşu|hareket)\b',str(scene.get('action','')).casefold()))
    strength=.045 if style=='balanced' else .07
    if opening or composition in ('wide','environment'):strength=min(.05 if style=='balanced' else .08,strength+.005)
    if importance<40:strength*=.65
    if high:
        return ('subtle_reframe',.008,'Hareketli sahnede sakin kadraj') if explicit in ('pan','slow_zoom','ken_burns') else ('none',0.,'Hareketli sahne korunur')
    if composition in ('close','detail','graphic','person'):
        return ('subtle_reframe',.012,'Yakın kadraj korunur') if explicit in ('pan','slow_zoom','ken_burns') or index%2==0 else ('none',0.,'Yakın kadraj korunur')
    if explicit in ('slow_zoom','ken_burns'):return 'push_in',strength,'Mevcut kamera hareketi'
    if explicit=='pan':return ('pan_right' if index%2 else 'pan_left'),strength,'Mevcut kamera hareketi'
    if index%(4 if style=='balanced' else 8)==3 and not opening and importance<75:return 'none',0.,'Sakin görsel aralık'
    sequence=('push_in','pan_right','push_out','pan_left','pan_up','pan_down','subtle_reframe')
    return sequence[index%len(sequence)],strength,'Açılış temposu' if opening else 'Dengeli görsel çeşitlilik'


def build(t,h,style,source_fingerprint,*,seed=None,subtitle_mode=None,media_details=None):
    meta={s['scene_id']:s for s in t['editing_scenes']};items=[];boundary=0
    for i,slot in enumerate(t['slots']):
        scene=meta[slot['scene_id']];duration=slot['frames']/30;opening=slot['start']<15
        if style=='basic':
            hint=scene.get('motion');image=slot['selected_media_local_identity']['media_type']=='image'
            effect=('pan_right' if hint=='pan' else 'push_in') if image and hint in ('pan','slow_zoom','ken_burns') else 'none'
            strength=.04 if effect!='none' else 0.;reason='Mevcut Part 9 kurgu';count=1
        else:
            effect,strength,reason=motion(scene,i,'balanced' if style=='adaptive' else style,opening)
            if style=='adaptive' and (slot['selected_media_local_identity']['media_type']=='video' and scene.get('motion') not in ('pan','slow_zoom','ken_burns') or i%3):effect,strength,reason='none',0.,'Sakin B-roll'
            count=3 if duration>(11 if style=='balanced' else 10) else 2 if duration>(7 if style=='balanced' else 6) or (opening and duration>5.5) else 1
            count=min(count,max(1,slot['frames']//75))
            if effect=='none' and scene.get('composition') in ('movement','close','detail','graphic','person'):count=1
            if reason=='Hareketli sahne korunur':count=1
        if style=='adaptive' and effect=='none':count=1
        segments=[]
        for j in range(count):
            a=round(j*slot['frames']/count);b=round((j+1)*slot['frames']/count)
            current=effect
            if j and effect!='none':
                if scene.get('motion')=='pan':current='pan_left' if effect=='pan_right' else 'pan_right'
                elif scene.get('motion') in ('slow_zoom','ken_burns'):current='push_in'
                elif scene.get('composition') in ('close','detail','person','graphic'):current='subtle_reframe'
                else:current='pan_right' if j==1 else 'push_out'
            elif j and style!='basic' and scene.get('composition') not in ('movement','close','detail','graphic','person'):
                current='subtle_reframe';strength=max(strength,.012)
            segments.append({'start_frame':a,'end_frame':b,'frames':b-a,'start':(slot['start_frame']+a)/30,'end':(slot['start_frame']+b)/30,
                             'motion_effect':current,'motion_strength':round(strength if current!='none' else 0,4),
                             'camera_curve':'neutral_cycle' if style!='basic' else 'legacy'})
        transition='hard_cut';seconds=0.
        if i<len(t['slots'])-1 and slot['scene_id']!=t['slots'][i+1]['scene_id']:
            original=scene.get('transition','none');boundary+=1
            if style=='basic':transition=original if original in ('crossfade','fade') else 'hard_cut';seconds=1/3 if transition=='crossfade' else .3 if transition=='fade' else 0.
            elif original in ('crossfade','fade') or boundary%(3 if style=='balanced' else 2)==1 or (opening and boundary==1):
                transition='fade_dark' if original=='fade' else 'crossfade' if original=='crossfade' or boundary%3 else 'dip_black'
                seconds=(12 if style=='balanced' else 14)/30
            if seconds:
                seconds=min(seconds,slot['frames']/120,t['slots'][i+1]['frames']/120)
                if seconds<2/30:transition='hard_cut';seconds=0.
        items.append({'slot_id':slot['slot_id'],'scene_id':slot['scene_id'],'start':slot['start'],'end':slot['end'],'media_type':slot['selected_media_local_identity']['media_type'],
                      'motion_effect':effect,'motion_strength':round(strength,4),'segments':segments,'transition_out':transition,'transition_in':'hard_cut',
                      'transition_duration':round(seconds,6),'visual_variant':scene.get('composition','medium'),'reason':reason})
    for previous,current in zip(items,items[1:]):current['transition_in']=previous['transition_out'] if previous['scene_id']!=current['scene_id'] else 'hard_cut'
    texts=emphasis(t,h,style)
    for previous in items[:-1]:
        if previous['transition_out'] in ('none','hard_cut'):continue
        a=previous['end']-previous['transition_duration'];b=previous['end']+previous['transition_duration']
        for item in texts:
            if item['punch_in'] and item['start']<b and item['end']>a:
                item['punch_in']=False;item['punch_suppressed']='transition'
    plan={'contract_version':1,'algorithm_version':'smart_edit_v3','editing_style':style,'style_label':STYLES[style],
          'source_fingerprint':source_fingerprint,'slots':items,'emphasis':texts}
    plan['summary']={'slots':len(items),'scenes':len(t['scenes']),
                     'motion_effects':sum(any(s['motion_effect']!='none' for s in item['segments']) for item in items) if style!='basic' else sum(s['editing'].get('motion') in ('slow_zoom','pan','ken_burns') and s['selected_media_local_identity']['media_type']=='image' for s in t['slots']),
                     'scene_transitions':sum(item['transition_out'] not in ('none','hard_cut') for item in items),
                     'emphasis_texts':len(texts),'internal_edits':sum(len(item['segments'])-1 for item in items)}
    plan['fingerprint']=digest(plan)
    if style=='adaptive':
        from app.rendering.adaptive import apply
        plan=apply(plan,t,h,seed,subtitle_mode or 'emphasis',media_details)
    if subtitle_mode=='none':
        plan['emphasis']=[];plan['summary']['emphasis_texts']=0
        plan['fingerprint']=digest({k:v for k,v in plan.items() if k!='fingerprint'})
    if media_details:
        from app.rendering.windows import source_window
        for item in plan['slots']:
            media=media_details.get(item['slot_id'],{})
            if media.get('type')=='video':item.update(source_window(media.get('duration'),item['end']-item['start'],media.get('sha256',item['slot_id'])+item['slot_id']))
            if media.get('type')=='image' and 0<media.get('width',0)<=media.get('height',0):item['fit']='contain'
        plan['fingerprint']=digest({k:v for k,v in plan.items() if k!='fingerprint'})
    return plan


def camera(segment,extra_frames=0,punches=(),*,head_hold=0,tail_hold=0):
    """One output frame per moving input frame: video never becomes a still."""
    effect=segment['motion_effect'];strength=segment['motion_strength']
    if effect=='none':return ''
    if segment.get('camera_curve')=='neutral_cycle':
        # Shared neutral framing at every treatment boundary. Both sides of a
        # transition hold this state; the input video itself keeps moving (d=1).
        start=max(0,head_hold);end=max(start+1,segment['frames']-1-max(0,tail_hold))
        p=f'max(0,min((on-{start})/{max(1,end-start)},1))'
        peak=.35 if effect=='push_out' else .65 if effect=='push_in' else .5
        up=f'min(({p})/{peak},1)';down=f'max(0,min((({p})-{peak})/{1-peak},1))'
        smooth=lambda t:f'(({t})*({t})*(3-2*({t})))'
        envelope=f'if(lt(({p}),{peak}),{smooth(up)},1-{smooth(down)})'
        zoom=f'1+{strength}*({envelope})'
        if punches and strength>=.02:
            # No punch may escape the neutral endpoint/hold envelope.
            bonus=[]
            for a,b in punches:bonus.append(f'max(0,min(min((on-{a})/6,({b}-on)/6),1))')
            punch=bonus[0]
            for value in bonus[1:]:punch=f'max({punch},{value})'
            zoom=f'min({max(1.05,1+strength):.4f},({zoom})+0.01*({punch})*({envelope}))'
        x='(iw-iw/zoom)/2'
        y='(ih-ih/zoom)/2'
        if effect in ('pan_left','pan_right','subtle_reframe'):
            sign=-1 if effect=='pan_left' else 1;amount=.1 if effect=='subtle_reframe' else .35
            x=f'(iw-iw/zoom)*(0.5+({sign*amount})*({envelope}))'
        elif effect in ('pan_up','pan_down'):
            sign=-1 if effect=='pan_up' else 1;y=f'(ih-ih/zoom)*(0.5+({sign*.35})*({envelope}))'
        x=f'2*floor(({x})/2)';y=f'2*floor(({y})/2)'
        return f",scale=3840:2160,zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s=1920x1080:fps=30,setsar=1"
    p=f'min(on/{max(segment["frames"]-1,1)},1)'
    zoom=f'1+{strength}*({p})' if effect=='push_in' else f'1+{strength}*(1-({p}))' if effect=='push_out' else str(1+strength)
    if punches and strength>=.02:
        bonus=[]
        for start,end in punches:bonus.append(f'max(0,min(min((on-{start})/6,({end}-on)/6),1))')
        envelope=bonus[0]
        for value in bonus[1:]:envelope=f'max({envelope},{value})'
        zoom=f'min({max(1.05,1+strength):.4f},({zoom})+0.01*({envelope}))'
    x='(iw-iw/zoom)/2';y='(ih-ih/zoom)/2'
    if effect in ('pan_left','pan_right'):x=f'(iw-iw/zoom)*({p})' if effect=='pan_right' else f'(iw-iw/zoom)*(1-({p}))'
    elif effect in ('pan_up','pan_down'):y=f'(ih-ih/zoom)*({p})' if effect=='pan_down' else f'(ih-ih/zoom)*(1-({p}))'
    elif effect=='subtle_reframe':x=f'(iw-iw/zoom)*(0.4+0.2*({p}))'
    return f",scale=2304:1296,zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s=1920x1080:fps=30,setsar=1"
