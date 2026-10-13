"""Deterministic, exact-source render projection; no provider calls or source writes."""
import hashlib
import re
from app.rendering.smart_edit import clean, digest, highlight
from app.rendering import ass

LAYOUTS={'full_broll':'Tam B-roll','split_media_text':'Medya ve metin','fact_card':'Bilgi kartı','big_number':'Büyük sayı',
         'timeline_card':'Zaman çizelgesi','dual_media':'İki medya','minimal_title':'Kısa başlık','quote_emphasis':'Kısa vurgu','location_card':'Konum kartı'}
THEMES=('minimal_dark','clean_light','soft_documentary','grid_dark')
NUMBER=re.compile(r'(?<!\w)\d+(?:[.,]\d+)?(?:\s?(?:%|€|\$|km|million|Millionen|minutes|Minuten|years|Jahre))?(?!\w)')
YEAR=re.compile(r'\b(?:1[5-9]\d{2}|20\d{2})\b')


def choice(seed,key,size):return int(hashlib.sha256(f'{seed}:{key}'.encode()).hexdigest()[:12],16)%size


def apply(plan,t,h,seed=None,subtitle_mode='emphasis',media_details=None):
    seed=seed or plan['source_fingerprint'][:16];details=media_details or {}
    meta={s['scene_id']:s for s in t['editing_scenes']};last_end=-100;special_seconds=0;split_index=0
    plan.update(algorithm_version='adaptive_edit_v1',edit_variation_seed=seed,subtitle_display=subtitle_mode,theme=THEMES[choice(seed,'theme',len(THEMES))])
    from app.rendering.smart_edit import lower_thirds
    plan['emphasis']=lower_thirds(t) if subtitle_mode!='none' else []  # band over the video instead of a full-screen card
    banded={e['slot_id'] for e in plan['emphasis']}
    for index,item in enumerate(plan['slots']):
        item.update(layout='full_broll',layout_label=LAYOUTS['full_broll'],texts=[],layout_window=None,secondary_slot_id=None,orientation='left' if (index+choice(seed,'side',2))%2==0 else 'right')
        # A motion graphic is already a graphic; it and its neighbours keep the
        # clean frame so the slide-in/out is never cut by a card.
        if any(details.get(s['slot_id'],{}).get('motion') for s in plan['slots'][max(0,index-1):index+2]):continue
        if item['slot_id'] in banded:continue  # never a card on top of the band
        original=meta[item['scene_id']];source=clean(original.get('narration_text',''))
        cues=[]
        for c in h['subtitles']:
            if c['start']>=item['end']-.2 or c['end']<=item['start']+.2:continue
            raw=clean(c['text'])
            candidates=[raw,*[part.strip() for part in re.split(r'(?<=[.;!?])\s+',raw)]]
            exact=next((text for text in candidates if text in source and 2<=len(text.split())<=22 and len(text)<=180),'')
            if exact:cues.append({**c,'text':exact,'whole_cue':exact==raw})
        cue=next((c for c in cues if NUMBER.search(c['text'])),None) or next((c for c in cues if 2<=len(c['text'].split())<=14),None)
        provenance='subtitle_cue' if not cue or cue.get('whole_cue') else 'subtitle_clause'
        overlay=clean(original.get('overlay_text',''))
        if not cue and overlay and len(overlay)<=150 and len(overlay.split())<=14:
            cue={'text':overlay,'start':item['start']+.2,'end':min(item['end']-.2,item['start']+2.5),'index':None};provenance='scene_overlay'
        if not cue or item['start']<last_end+7 or special_seconds>=t['duration']*.27:continue
        text=clean(cue['text']);start=max(item['start']+.2,cue['start']);end=min(cue['end'],item['end']-.2,start+3)
        if end-start<1.3 or len(text)>180:continue
        options=[];years=YEAR.findall(text)
        year_matches=list(YEAR.finditer(text))
        dated_parts=[text[m.start():(year_matches[i+1].start() if i+1<len(year_matches) else len(text))].strip() for i,m in enumerate(year_matches)]
        if len(years)>=2 and len(set(years))>=2 and list(map(int,years))==sorted(map(int,years)) and all(len(part.split())>=3 for part in dated_parts):options.append('timeline_card')
        if NUMBER.search(text):options.append('big_number')
        clauses=[c.strip() for c in re.split(r'(?<=[.;!?])\s+',text) if 2<=len(c.split())<=12]
        if len(clauses)>=2:options.append('fact_card')
        location=original.get('location','')
        desc=details.get(item['slot_id'],{}).get('description','').lower()
        if location and location in text and any(w in desc for w in ('map','karte','harita',location.lower())):options.append('location_card')
        secondary=next((other for other in plan['slots'] if other['scene_id']==item['scene_id'] and other['slot_id']!=item['slot_id'] and details.get(other['slot_id'],{}).get('sha256')!=details.get(item['slot_id'],{}).get('sha256') and details.get(other['slot_id'],{}).get('sha256') and not details.get(other['slot_id'],{}).get('motion')),None)
        if secondary:options.append('dual_media')
        if original.get('importance',50)>=75 or item['start']<12:
            if len(text.split())<=10:options.extend(['quote_emphasis','minimal_title'])
            options.append('split_media_text')
        if subtitle_mode=='none':options=[o for o in options if o=='dual_media']
        if not options:continue
        # Content-specific layouts take priority. Seed rotates among compatible alternatives only.
        preferred=options[:1] if options[0] in ('timeline_card','big_number','fact_card','location_card') else options
        layout=preferred[choice(seed,item['slot_id'],len(preferred))]
        previous_layouts=[s['layout'] for s in plan['slots'][max(0,index-2):index]]
        if previous_layouts==[layout,layout]:
            layout=next((o for o in options if o!=layout),'full_broll')
        if layout=='full_broll':continue
        if special_seconds+end-start>t['duration']*.3:continue
        texts=clauses[:3] if layout=='fact_card' else [] if subtitle_mode=='none' else [text]
        if layout=='timeline_card':
            matches=list(YEAR.finditer(text));texts=[text[m.start():(matches[i+1].start() if i+1<len(matches) else len(text))].strip() for i,m in enumerate(matches)][:3]
        if layout in ('split_media_text','dual_media'):
            item['orientation']='left' if (split_index+choice(seed,'side',2))%2==0 else 'right';split_index+=1
        item.update(layout=layout,layout_label=LAYOUTS[layout],texts=texts,layout_window={'start':start,'end':end},secondary_slot_id=secondary['slot_id'] if secondary and layout=='dual_media' else None)
        # Every card shows a 2-5 word accent, never the whole sentence (number cards: the words around the number).
        texts=[highlight(x) for x in texts if x.strip()]
        if layout=='big_number':
            item['number']=NUMBER.search(text).group()
            rest=' '.join(w for w in text.split() if item['number'] not in w)
            texts=[highlight(rest)] if rest.strip() else texts
        item['text_provenance']={'source':provenance,'cue_index':cue.get('index'),'start':cue['start'],'end':cue['end']}
        # The card stays fixed while the media behind it keeps one slow, gentle
        # move (no punch-in cut, no stacked zoom). Static cards read as slides.
        first=item['segments'][0];last=item['segments'][-1]
        effect='push_in' if first['motion_effect'] in ('none','push_out') else first['motion_effect']
        strength=round(min(first['motion_strength'] or .03,.03),4) if first.get('camera_curve')=='eased' else 0
        item['segments']=[{**first,'end_frame':last['end_frame'],'frames':last['end_frame']-first['start_frame'],'end':last['end'],'base_zoom':0.,
                           'motion_effect':effect if strength else 'none','motion_strength':strength}]
        item.update(motion_effect=item['segments'][0]['motion_effect'],motion_strength=strength,reason='İçeriğe uygun yerel görsel düzen')
        special_seconds+=end-start;last_end=end
    # Preserve neutral endpoints. Cards near boundaries use a clean cut.
    last_transition=None
    def clear(item,edge,seconds):
        # A transition may border a card only if the card text stays fully
        # outside the transition window (no text flashing through a blend).
        window=item.get('layout_window')
        if item['layout']=='full_broll' or not window:return True
        return window['end']<=item['end']-seconds-.25 if edge=='end' else window['start']>=item['start']+seconds+.25
    carried=None
    for boundary,(previous,current) in enumerate(zip(plan['slots'],plan['slots'][1:])):
        if current.get('continuation_of') or previous.get('continuation_of') and previous.get('transition_style') not in ('smoothleft','smoothright'):
            previous.update(transition_out='hard_cut',transition_duration=0);current['transition_in']='hard_cut';continue
        if carried and previous['scene_id']!=current['scene_id'] and previous['transition_out'] in ('none','hard_cut'):
            # A transition blocked by card text moves to the next scene boundary.
            seconds=min(carried[1],previous['frames']/120 if 'frames' in previous else carried[1],(current['end']-current['start'])/4,(previous['end']-previous['start'])/4)
            if seconds>=2/30:previous.update(transition_out=carried[0],transition_duration=round(seconds,6));carried=None
        seconds=previous.get('transition_duration') or 0
        if (previous['layout']!='full_broll' or current['layout']!='full_broll') and not (seconds and clear(previous,'end',seconds) and clear(current,'start',seconds)):
            if previous['transition_out'] not in ('none','hard_cut'):carried=(previous['transition_out'],seconds)
            previous.update(transition_out='hard_cut',transition_duration=0)
        elif previous.get('transition_style') in ('smoothleft','smoothright') and previous['transition_out']=='crossfade':
            pass  # motion graphic slides in/out: keep the push
        elif previous['transition_out'] not in ('none','hard_cut'):
            from app.rendering.smart_edit import PROFILES
            styles=PROFILES.get(plan.get('edit_profile'),{}).get('transitions',('crossfade','fade_dark','dip_black'))
            selected=choice(seed,f'transition-{boundary}',len(styles))
            if styles[selected]==last_transition and styles[selected]!='crossfade':selected=(selected+1)%len(styles)
            previous['transition_out']=styles[selected]
        if previous['transition_out'] not in ('none','hard_cut'):last_transition=previous['transition_out']
        current['transition_in']=previous['transition_out']
    counts={name:sum(s['layout']==name for s in plan['slots']) for name in LAYOUTS}
    plan['summary'].update(emphasis_texts=sum(len(s['texts']) for s in plan['slots']),layouts=counts,graphic_seconds=round(special_seconds,3),broll_seconds=round(t['duration']-special_seconds,3),layout_failures=0,
        motion_effects=sum(any(s['motion_effect']!='none' for s in item['segments']) for item in plan['slots']),scene_transitions=sum(s['transition_out'] not in ('none','hard_cut') for s in plan['slots']),internal_edits=sum(len(s['segments'])-1 for s in plan['slots']))
    plan['fingerprint']=digest({k:v for k,v in plan.items() if k!='fingerprint'})
    return plan


def captions(item,theme,g=None):
    """Unicode text lives exclusively in an escaped local ASS file. With a
    video look (g) the cards use its colours and heading font and animate in."""
    content,_,_=ass.create([],[],item['end']-item['start'],subtitles=False,overlays=False,editing_style='adaptive',emphasis=[])
    light=theme=='clean_light';colour='&H00202020' if light else '&H00FFFFFF'
    font,number_colour,number_size='Arial',colour,110
    if g:font,colour,number_colour,number_size=g['font'],ass.ass_colour(g['primary']),ass.ass_colour(g['accent']),130
    styles=f'Style: Card,{font},54,{colour},{colour},&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,120,120,80,1\nStyle: Number,{font},{number_size},{number_colour},{number_colour},&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,120,120,80,1\n'
    content=content.replace('[Events]',styles+'\n[Events]')
    window=item['layout_window'];a=window['start']-item['start'];b=window['end']-item['start'];layout=item['layout']
    x=1440 if item['orientation']=='left' else 480
    if layout not in ('split_media_text','dual_media'):x=960
    texts=item['texts'];lines=[]
    if layout=='big_number':
        lines.append((a,b,'Number',960,410,item['number']))
        lines.append((a,b,'Card',960,620,texts[0]))
    else:
        for i,text in enumerate(texts):
            y=(280 if layout=='minimal_title' else 480)+(i-(len(texts)-1)/2)*135
            if layout in ('split_media_text','dual_media'):
                # Bounded short text, wrap at word boundaries in the 960px panel.
                words=text.split();text='\n'.join(' '.join(words[j:j+5]) for j in range(0,len(words),5))
            lines.append((min(a+i*.15,b-.1),b,'Card',x,int(y),text))
    for start,end,style,x,y,text in lines:
        # Small fade is independent of all camera/transition handles.
        motion=(f'\\move({x},{y+28},{x},{y},0,320)' if style=='Card' else f'\\pos({x},{y})\\fscx70\\fscy70\\t(0,320,\\fscx100\\fscy100)') if g else f'\\pos({x},{y})'
        content+=f'Dialogue: 2,{ass.timecode(start)},{ass.timecode(end)},{style},,0,0,0,,{{{motion}\\fad({200 if g else 150},150)}}{ass.escape(text)}\n'
    return content


def graph(item,theme,caption_name,g=None,fontsdir=''):
    """Decorate a normalized 1080p stream; windows never alter media timestamps."""
    layout=item['layout'];w=item['layout_window'];a=w['start']-item['start'];b=w['end']-item['start'];enable=f"between(t,{a:.6f},{b:.6f})"
    light=theme=='clean_light';bg='0xeceee8' if light else '0x19232d' if theme=='soft_documentary' else '0x101823';accent='0x559eaa'
    if g:bg,accent='0x'+g['background'][1:],'0x'+g['accent'][1:]  # the video look's colours
    graph='';source='treated'
    if layout in ('split_media_text','dual_media'):
        left=item['orientation']=='left';mx=0 if left else 960;tx=960 if left else 0
        graph+='[treated]split=2[base][small];[small]scale=960:1080:force_original_aspect_ratio=increase,crop=960:1080[panel];'
        graph+=f"[base]drawbox=x={tx}:y=0:w=960:h=1080:color={bg}:t=fill:enable='{enable}'[back];[back][panel]overlay=x={mx}:y=0:enable='{enable}'[splitview];"
        source='splitview'
        if layout=='dual_media':
            graph+=f"[1:v]scale=960:1080:force_original_aspect_ratio=increase,crop=960:1080,setsar=1,fps=30,settb=1/30,setpts=PTS-STARTPTS[second];[splitview][second]overlay=x={tx}:y=0:enable='{enable}':eof_action=repeat[dual];"
            source='dual'
    elif layout in ('fact_card','big_number','timeline_card','location_card'):
        graph+=f"[treated]drawbox=x=120:y=180:w=1680:h=720:color={bg}:t=fill:enable='{enable}',drawbox=x=120:y=180:w=12:h=720:color={accent}:t=fill:enable='{enable}'[card];";source='card'
        if theme=='grid_dark':
            graph+=f"[card]drawgrid=w=120:h=120:t=1:c=white@0.04:enable='{enable}'[grid];";source='grid'
    else:
        top,height=(180,200) if layout=='minimal_title' else (350,300)
        graph+=f"[treated]drawbox=x=180:y={top}:w=1560:h={height}:color={bg}:t=fill:enable='{enable}'[title];";source='title'
    if layout=='timeline_card':
        graph+=f"[{source}]drawbox=x=300:y=300:w=5:h=480:color={accent}:t=fill:enable='{enable}'[timeline];";source='timeline'
    return graph+f'[{source}]ass=filename={caption_name}{fontsdir},format=yuv420p[layouttreated];'
