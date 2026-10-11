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


# Multilingual mood words (de/en/es/fr/tr). Free-text scene moods drive the
# project's edit rhythm instead of one fixed template for every topic.
CALM=re.compile(r'ruhig|nachdenk|geheimnis|mysteri|myst|melanchol|traurig|ernst|sakin|gizem|huzur|duygusal|hüzün|calm|quiet|reflect|sad|serious|somber|tranquil|tranquilo|misterio|triste|serio|calme|mystère|mystere|triste|grave|sérieux|serieux',re.I)
ENERGETIC=re.compile(r'spannend|aufregend|dramat|energ|schnell|intens|action|heyecan|dinamik|hızlı|hizli|gerilim|exciting|upbeat|fast|thrill|tense|urgent|emocionante|rápido|rapido|tenso|excitant|rapide|tendu|urgent',re.I)
PROFILES={
 'calm':{'video':.035,'image':.06,'split':6.5,'transition_every':2,'transition_seconds':.6,'transitions':('crossfade','crossfade','fade_dark'),'label':'Sakin belgesel ritmi'},
 'balanced':{'video':.045,'image':.075,'split':5.5,'transition_every':3,'transition_seconds':.45,'transitions':('crossfade','fade_dark','crossfade'),'label':'Dengeli anlatım ritmi'},
 'energetic':{'video':.055,'image':.09,'split':4.5,'transition_every':4,'transition_seconds':.3,'transitions':('crossfade','dip_black'),'label':'Hızlı ve enerjik ritim'},
}


def edit_profile(t):
    """Project-level rhythm from the actual scene moods and narration pace."""
    calm=energetic=0
    for scene in t['editing_scenes']:
        mood=str(scene.get('mood',''))
        calm+=bool(CALM.search(mood));energetic+=bool(ENERGETIC.search(mood))
    total=max(1,len(t['editing_scenes']))
    name='energetic' if energetic>calm and energetic/total>=.3 else 'calm' if calm>energetic and calm/total>=.3 else 'balanced'
    return name


def adaptive_motion(scene,slot,index,profile,seed,previous):
    """Every shot gets a gentle, varied operator move; stills move more than
    video. Fast-moving footage and tight compositions stay restrained."""
    settings=PROFILES[profile];image=slot['selected_media_local_identity']['media_type']=='image'
    if slot['selected_media_local_identity'].get('graphic'):return 'push_in',.015,'Metin kartında çok hafif yaklaşma'
    strength=settings['image' if image else 'video'];composition=scene.get('composition','medium')
    importance=scene.get('importance',50);mood=str(scene.get('mood',''))
    moving=composition=='movement' or bool(re.search(r'\b(?:running|driving|flying|racing|laufen|fahren|fliegen|koşu|hareket|vuelo|correr|voler|courir)\b',str(scene.get('action','')).casefold()))
    if moving and not image:return 'subtle_reframe',.012,'Hareketli çekimde sakin kadraj'
    if composition in ('close','detail','person') and not image:return 'push_in',min(strength,.025),'Yakın kadrajda hafif yaklaşma'
    if importance>=75 or ENERGETIC.search(mood):strength*=1.15
    if importance<40:strength*=.8
    explicit=scene.get('motion','none')
    if explicit in ('slow_zoom','ken_burns'):options=('push_in','push_out') if image else ('push_in',)
    elif explicit=='pan':options=('pan_right','pan_left')
    elif profile=='calm':options=('push_in','push_in','pan_right','push_out','pan_left')
    elif profile=='energetic':options=('pan_right','push_in','pan_left','pan_up','push_out','pan_down')
    else:options=('push_in','pan_right','push_out','pan_left','pan_up','push_in')
    pick=int(hashlib.sha256(f'{seed}:motion:{slot["slot_id"]}'.encode()).hexdigest()[:8],16)%len(options)
    effect=options[pick]
    if effect==previous and len(set(options))>1:effect=next(o for o in options[pick+1:]+options[:pick] if o!=previous)
    return effect,round(strength,4),settings['label']


def build(t,h,style,source_fingerprint,*,seed=None,subtitle_mode=None,media_details=None):
    meta={s['scene_id']:s for s in t['editing_scenes']};items=[];boundary=0
    profile=edit_profile(t) if style=='adaptive' else None;motion_seed=seed or source_fingerprint[:16];previous_effect=None
    for i,slot in enumerate(t['slots']):
        scene=meta[slot['scene_id']];duration=slot['frames']/30;opening=slot['start']<15
        if style=='basic':
            hint=scene.get('motion');image=slot['selected_media_local_identity']['media_type']=='image'
            effect=('pan_right' if hint=='pan' else 'push_in') if image and hint in ('pan','slow_zoom','ken_burns') else 'none'
            strength=.04 if effect!='none' else 0.;reason='Mevcut Part 9 kurgu';count=1
        elif style=='adaptive':
            effect,strength,reason=adaptive_motion(scene,slot,i,profile,motion_seed,previous_effect);previous_effect=effect
            # Long single shots are split by a clear punch-in cut on the same
            # source (a deliberate reframe, never a small accidental jump).
            split=PROFILES[profile]['split'];count=1 if effect=='subtle_reframe' else 3 if duration>split*2.2 else 2 if duration>split else 1
            count=min(count,max(1,slot['frames']//60))
        else:
            effect,strength,reason=motion(scene,i,style,opening)
            count=3 if duration>(11 if style=='balanced' else 10) else 2 if duration>(7 if style=='balanced' else 6) or (opening and duration>5.5) else 1
            count=min(count,max(1,slot['frames']//75))
            if effect=='none' and scene.get('composition') in ('movement','close','detail','graphic','person'):count=1
            if reason=='Hareketli sahne korunur':count=1
        segments=[]
        for j in range(count):
            a=round(j*slot['frames']/count);b=round((j+1)*slot['frames']/count)
            current=effect
            if style=='adaptive':
                # Alternate wide → tighter → wide framing; each piece moves on its own.
                punch=(.12 if j%2 else 0.) if count>1 else 0.
                current=effect if j%2==0 else ('push_out' if effect=='push_in' else 'push_in' if effect in ('push_out','subtle_reframe') else effect)
                segments.append({'start_frame':a,'end_frame':b,'frames':b-a,'start':(slot['start_frame']+a)/30,'end':(slot['start_frame']+b)/30,
                                 'motion_effect':current,'motion_strength':round(strength,4),'base_zoom':punch,'camera_curve':'eased'})
                continue
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
            elif style=='adaptive':
                settings=PROFILES[profile]
                if original in ('crossfade','fade') or boundary%settings['transition_every']==1:
                    transition='fade_dark' if original=='fade' else 'crossfade';seconds=settings['transition_seconds']
            elif original in ('crossfade','fade') or boundary%(3 if style=='balanced' else 2)==1 or (opening and boundary==1):
                transition='fade_dark' if original=='fade' else 'crossfade' if original=='crossfade' or boundary%3 else 'dip_black'
                seconds=(12 if style=='balanced' else 14)/30
            if seconds:
                seconds=min(seconds,slot['frames']/120,t['slots'][i+1]['frames']/120)
                if seconds<2/30:transition='hard_cut';seconds=0.
        items.append({'slot_id':slot['slot_id'],'scene_id':slot['scene_id'],'start':slot['start'],'end':slot['end'],'media_type':slot['selected_media_local_identity']['media_type'],
                      'motion_effect':effect,'motion_strength':round(strength,4),'segments':segments,'transition_out':transition,'transition_in':'hard_cut',
                      'transition_duration':round(seconds,6),'visual_variant':scene.get('composition','medium'),'reason':reason})
    continuing={s['slot_id']:s.get('continuation_of') for s in t['slots'] if s.get('continuation_of')}
    for previous,current in zip(items,items[1:]):
        if continuing.get(current['slot_id']) or continuing.get(previous['slot_id']):
            # The same take continues: a blend would ghost it over itself.
            previous.update(transition_out='hard_cut',transition_duration=0.)
        current['transition_in']=previous['transition_out'] if previous['scene_id']!=current['scene_id'] else 'hard_cut'
    if style!='basic':
        # Professional transition variety: motion graphics slide in/out with a
        # push; other scene changes rotate subtle styles (fade stays dominant).
        variety=('fade','zoomin','fade','smoothleft','fade','circleopen');k=0
        for idx,(previous,current) in enumerate(zip(items,items[1:])):
            if previous['scene_id']==current['scene_id'] or continuing.get(current['slot_id']) or continuing.get(previous['slot_id']):continue
            motion_out=bool((media_details or {}).get(previous['slot_id'],{}).get('motion'))
            motion_in=bool((media_details or {}).get(current['slot_id'],{}).get('motion'))
            if motion_out or motion_in:
                seconds=min(.4,t['slots'][idx]['frames']/120,t['slots'][idx+1]['frames']/120)
                if seconds>=2/30:
                    previous.update(transition_out='crossfade',transition_duration=round(seconds,6),transition_style='smoothleft' if motion_in else 'smoothright')
                    current['transition_in']='crossfade'
            elif previous['transition_out']=='crossfade':
                previous['transition_style']=variety[k%len(variety)];k+=1
    for item in items:
        if continuing.get(item['slot_id']) and style!='basic':
            for segment in item['segments']:
                segment['base_zoom']=round(segment.get('base_zoom',0.)+.12,4)
                segment['camera_curve']='eased'
                if segment['motion_effect']=='none':segment.update(motion_effect='push_in',motion_strength=.03)
            item['reason']='Önceki çekimin kesintisiz devamı (yakın kadraj)'
        if continuing.get(item['slot_id']):item['continuation_of']=continuing[item['slot_id']]
    texts=emphasis(t,h,style)
    for previous in items[:-1]:
        if previous['transition_out'] in ('none','hard_cut'):continue
        a=previous['end']-previous['transition_duration'];b=previous['end']+previous['transition_duration']
        for item in texts:
            if item['punch_in'] and item['start']<b and item['end']>a:
                item['punch_in']=False;item['punch_suppressed']='transition'
    plan={'contract_version':1,'algorithm_version':'smart_edit_v3','editing_style':style,'style_label':STYLES[style],
          **({'edit_profile':profile,'edit_profile_label':PROFILES[profile]['label']} if profile else {}),
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
        roots={s['slot_id']:s.get('continuation_of') or s['slot_id'] for s in t['slots']}
        chains={}
        for item in plan['slots']:chains.setdefault(roots[item['slot_id']],[]).append(item)
        for root,items in chains.items():
            media=media_details.get(items[0]['slot_id'],{})
            if media.get('type')=='video':
                # One continuous take: consecutive parts of a single source window.
                window=source_window(media.get('duration'),sum(i['end']-i['start'] for i in items),media.get('sha256',root)+root)
                cursor=window['source_in']
                if media.get('segment_start') is not None:  # assigned non-overlapping part of a reused clip
                    cursor=max(0.,min(float(media['segment_start']),window['source_duration']-sum(i['end']-i['start'] for i in items)))
                for item in items:
                    used=item['end']-item['start']
                    item.update(source_duration=window['source_duration'],source_in=round(cursor,6),source_out=round(min(window['source_duration'],cursor+used),6),
                                source_trim_start=round(cursor,6),source_trim_end=round(min(window['source_duration'],cursor+used),6),used_duration=used)
                    cursor+=used
            for item in items:
                if 0<media.get('width',0)<=media.get('height',0):item['fit']='contain'  # portrait/square: blurred backdrop
        plan['fingerprint']=digest({k:v for k,v in plan.items() if k!='fingerprint'})
    return plan


def _perspective(zoom,fx,fy):
    """Sub-pixel crop+scale. zoompan rounds its window to whole pixels, which
    shows as visible stepping/jitter on slow pushes; perspective resamples the
    exact fractional window (measured ~6x lower frame-to-frame jitter)."""
    w=f'(W/({zoom}))';h=f'(H/({zoom}))';left=f'((W-{w})*({fx}))';top=f'((H-{h})*({fy}))'
    return (f",perspective=x0='{left}':y0='{top}':x1='{left}+{w}':y1='{top}':x2='{left}':y2='{top}+{h}'"
            f":x3='{left}+{w}':y3='{top}+{h}':interpolation=cubic:eval=frame,setsar=1")


def _punch(punches,envelope='1'):
    bonus=[f'max(0,min(min((on-{a})/6,({b}-on)/6),1))' for a,b in punches]
    value=bonus[0]
    for item in bonus[1:]:value=f'max({value},{item})'
    return f'0.01*({value})*({envelope})'


def camera(segment,extra_frames=0,punches=(),*,head_hold=0,tail_hold=0,length=None):
    """One output frame per moving input frame: video never becomes a still."""
    effect=segment['motion_effect'];strength=segment['motion_strength']
    if effect=='none':return ''
    if segment.get('camera_curve')=='eased':
        # One direction per shot with soft start/stop (half linear, half
        # cosine ease): reads as a steady operator move, never a "breathing"
        # in-out cycle. Clamped, so it holds on the final frame.
        n=max(2,length or segment['frames']);p=f'min(max(on/{n-1},0),1)'
        e=f'(0.5*{p}+0.25*(1-cos(PI*{p})))'
        base=1+segment.get('base_zoom',0.);fx=fy='0.5'
        if effect=='push_in':zoom=f'{base}+{strength}*{e}'
        elif effect=='push_out':zoom=f'{base}+{strength}*(1-{e})'
        else:
            zoom=f'{base+strength}'
            if effect in ('pan_left','pan_right'):fx=f'(0.5+{.35 if effect=="pan_right" else -.35}*(2*{e}-1))'
            elif effect in ('pan_up','pan_down'):fy=f'(0.5+{.35 if effect=="pan_down" else -.35}*(2*{e}-1))'
            else:zoom=f'{base}+{strength}*(0.5+0.5*{e})';fx=f'(0.42+0.16*{e})'
        if punches and strength>=.02:zoom=f'({zoom})+{_punch(punches)}'
        return _perspective(zoom,fx,fy)
    if segment.get('camera_curve')=='neutral_cycle':
        # Shared neutral framing at every treatment boundary. Both sides of a
        # transition hold this state; the input video itself keeps moving.
        start=max(0,head_hold);end=max(start+1,segment['frames']-1-max(0,tail_hold))
        p=f'max(0,min((on-{start})/{max(1,end-start)},1))'
        peak=.35 if effect=='push_out' else .65 if effect=='push_in' else .5
        up=f'min(({p})/{peak},1)';down=f'max(0,min((({p})-{peak})/{1-peak},1))'
        smooth=lambda t:f'(({t})*({t})*(3-2*({t})))'
        envelope=f'if(lt(({p}),{peak}),{smooth(up)},1-{smooth(down)})'
        zoom=f'1+{strength}*({envelope})'
        if punches and strength>=.02:
            # No punch may escape the neutral endpoint/hold envelope.
            zoom=f'min({max(1.05,1+strength):.4f},({zoom})+{_punch(punches,envelope)})'
        fx=fy='0.5'
        if effect in ('pan_left','pan_right','subtle_reframe'):
            sign=-1 if effect=='pan_left' else 1;amount=.1 if effect=='subtle_reframe' else .35
            fx=f'(0.5+({sign*amount})*({envelope}))'
        elif effect in ('pan_up','pan_down'):
            sign=-1 if effect=='pan_up' else 1;fy=f'(0.5+({sign*.35})*({envelope}))'
        return _perspective(zoom,fx,fy)
    p=f'min(on/{max(segment["frames"]-1,1)},1)'
    zoom=f'1+{strength}*({p})' if effect=='push_in' else f'1+{strength}*(1-({p}))' if effect=='push_out' else str(1+strength)
    if punches and strength>=.02:
        zoom=f'min({max(1.05,1+strength):.4f},({zoom})+{_punch(punches)})'
    fx=fy='0.5'
    if effect in ('pan_left','pan_right'):fx=f'({p})' if effect=='pan_right' else f'(1-({p}))'
    elif effect in ('pan_up','pan_down'):fy=f'({p})' if effect=='pan_down' else f'(1-({p}))'
    elif effect=='subtle_reframe':fx=f'(0.4+0.2*({p}))'
    return _perspective(zoom,fx,fy)
