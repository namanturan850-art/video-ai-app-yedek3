"""Internally generated Unicode ASS; cue timing is read, never regenerated."""
import math
import re
from app.rendering.models import RenderError
from app.subtitles.models import validate_cues,SubtitleError


def timecode(seconds):
    cs=round(seconds*100);h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);s,cs=divmod(cs,100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'


def escape(text):
    # ASS reserved syntax is escaped in the data file, never in shell/filter syntax.
    return text.replace('\\','\\\\').replace('{',r'\{').replace('}',r'\}').replace('\r','').replace('\n',r'\N')


def ass_colour(hexcolor):
    return '&H00'+hexcolor[5:7]+hexcolor[3:5]+hexcolor[1:3]


def styled(header,style):
    """Channel “Tarzım” subtitle style (font, colours, position, size).
    The default kit (Arial/white/bottom/48) leaves the header unchanged."""
    from app.channels import DEFAULT_STYLE,FONTS
    if not style or style==DEFAULT_STYLE['subtitle']:return header
    lines=header.split('\n')
    for i,line in enumerate(lines):
        if line.startswith('Style: Subtitle,'):
            f=line[len('Style: '):].split(',')
            f[1]=FONTS[style['font']][0];f[2]=str(style['size']);f[3]=f[4]=ass_colour(style['color']);f[5]=ass_colour(style['outline'])
            f[18]={'bottom':'2','middle':'5','top':'8'}[style['position']]
            lines[i]='Style: '+','.join(f)
    return '\n'.join(lines)


H_LOWER=630  # reserve the bottom area for two-line subtitles


def fitted(text, font, width, lines, size):
    from app.channels import FONTS
    from app.motion.templates import measure
    from app.text_layout import fit_text
    file = FONTS[font][1] if font in FONTS else next((v[1] for v in FONTS.values() if v[0] == font), 'Inter.ttf')
    size, rows = fit_text(text, lambda value, size: measure(value, file, size), width, lines, size)
    return size, '\n'.join(rows)


def graphic(item,start,end,g):
    """Emphasis text as a broadcast-style graphic (kit colours and heading
    font): a translucent box slides in, an accent bar grows, the text follows.
    Vector drawing only (libass), no images."""
    size,text=fitted(item['text'],g['font'],1500,2,64)
    width=1640;squeeze=100
    height=int(size*1.4*len(text.splitlines())+30);bg=ass_colour(g['background'])[4:];accent=ass_colour(g['accent'])[4:];fg=ass_colour(g['primary'])[4:]
    a,b=timecode(start),timecode(end);out=max(0,int((end-start)*1000)-220)
    font=g['font'];shape=lambda w,h:f'm 0 0 l {w} 0 {w} {h} 0 {h}'
    if item.get('style') in ('upper_left','lower_third'):  # kicker on the left; lower_third: band over the video, above subtitles
        x,y=(120,110) if item.get('style')=='upper_left' else (120,H_LOWER)
        return [f'Dialogue: 2,{a},{b},Graphic,,0,0,0,,{{\\an7\\move({x-60},{y},{x},{y},0,260)\\p1\\bord0\\shad0\\1c&H{bg}&\\1a&H20&\\fad(160,200)}}{shape(width,height)}{{\\p0}}',
                f'Dialogue: 3,{a},{b},Graphic,,0,0,0,,{{\\an7\\pos({x},{y})\\p1\\bord0\\shad0\\1c&H{accent}&\\fscy0\\t(80,360,\\fscy100)\\fad(0,200)}}{shape(12,height)}{{\\p0}}',
                f'Dialogue: 4,{a},{b},Graphic,,0,0,0,,{{\\an4\\move({x+10},{y+height//2},{x+40},{y+height//2},60,340)\\fn{font}\\fs{size}\\fscx{squeeze}\\b1\\bord0\\shad2\\4c&H000000&\\1c&H{fg}&\\fad(220,200)}}{escape(text)}']
    x,y=960,150  # centred title with an underline that grows from the middle
    return [f'Dialogue: 2,{a},{b},Graphic,,0,0,0,,{{\\an8\\pos({x},{y})\\p1\\bord0\\shad0\\1c&H{bg}&\\1a&H28&\\fscx92\\fscy92\\t(0,240,\\fscx100\\fscy100)\\fad(160,200)}}{shape(width,height+18)}{{\\p0}}',
            f'Dialogue: 3,{a},{b},Graphic,,0,0,0,,{{\\an8\\pos({x},{y+height+8})\\p1\\bord0\\shad0\\1c&H{accent}&\\fscx0\\t(120,460,\\fscx100)\\fad(0,200)}}{shape(max(120,width-160),10)}{{\\p0}}',
            f'Dialogue: 4,{a},{b},Graphic,,0,0,0,,{{\\an5\\move({x},{y+height//2+30},{x},{y+height//2+9},40,320)\\fn{font}\\fs{size}\\fscx{squeeze}\\b1\\bord0\\shad2\\4c&H000000&\\1c&H{fg}&\\fad(220,200)}}{escape(text)}']


def badge(item,start,end,g):
    """[SIRA]: “23/30 · TITLE” in a dark box at the top left + a thin progress line under it."""
    g=g or {};accent=ass_colour(g.get('accent') or '#3D9BFF')[4:];bg=ass_colour(g.get('background') or '#0B1426')[4:];font=g.get('font') or 'Arial'
    size,text=fitted(item['text'],font,1500,1,36)
    width=1600;a,b=timecode(start),timecode(end)
    filled=max(4,int((width-0)*min(1,max(0,float(item.get('fraction') or 0)))))
    shape=lambda w,h:f'm 0 0 l {w} 0 {w} {h} 0 {h}'
    return [f'Dialogue: 5,{a},{b},Graphic,,0,0,0,,{{\\an7\\pos(60,48)\\p1\\bord0\\shad0\\1c&H{bg}&\\1a&H30&\\fad(250,250)}}{shape(width,64)}{{\\p0}}',
            f'Dialogue: 6,{a},{b},Graphic,,0,0,0,,{{\\an4\\pos(84,80)\\fn{font}\\fs{size}\\b1\\bord0\\shad0\\1c&HFFFFFF&\\fad(250,250)}}{escape(text)}',
            f'Dialogue: 6,{a},{b},Graphic,,0,0,0,,{{\\an7\\pos(60,116)\\p1\\bord0\\shad0\\1c&HFFFFFF&\\1a&HB0&\\fad(250,250)}}{shape(width,6)}{{\\p0}}',
            f'Dialogue: 7,{a},{b},Graphic,,0,0,0,,{{\\an7\\pos(60,116)\\p1\\bord0\\shad0\\1c&H{accent}&\\fscx0\\t(200,900,\\fscx100)\\fad(250,250)}}{shape(filled,6)}{{\\p0}}']


def band2(item,start,end,g):
    """[ŞERİT]: a fitted heading and complete phrase over real footage."""
    g=g or {};accent=ass_colour(g.get('accent') or '#3D9BFF')[4:];bg=ass_colour(g.get('background') or '#0B1426')[4:];font=g.get('font') or 'Arial'
    top=' '.join(str(item.get('top') or '').split()).upper();bottom=' '.join(item['text'].split());a,b=timecode(start),timecode(end)
    size,bottom=fitted(bottom,font,1560,2,52)
    top_size,top=fitted(top,font,1560,1,30)
    width=1680;y=H_LOWER-10
    shape=lambda w,h:f'm 0 0 l {w} 0 {w} {h} 0 {h}'
    lines=[f'Dialogue: 2,{a},{b},Graphic,,0,0,0,,{{\\an7\\move(40,{y},90,{y},0,300)\\p1\\bord0\\shad0\\1c&H{bg}&\\1a&H38&\\fad(200,250)}}{shape(width,160)}{{\\p0}}',
           f'Dialogue: 3,{a},{b},Graphic,,0,0,0,,{{\\an7\\pos(90,{y})\\p1\\bord0\\shad0\\1c&H{accent}&\\fscy0\\t(100,400,\\fscy100)\\fad(0,250)}}{shape(10,160)}{{\\p0}}']
    if top:lines.append(f'Dialogue: 4,{a},{b},Graphic,,0,0,0,,{{\\an7\\pos(130,{y+18})\\fn{font}\\fs{top_size}\\b1\\bord0\\shad0\\1c&H{accent}&\\fad(250,250)}}{escape(top)}')
    # Keep the complete phrase visible; per-letter delays could outlast a short slot.
    typed=escape(bottom)
    lines.append(f'Dialogue: 4,{a},{b},Graphic,,0,0,0,,{{\\an7\\pos(130,{y+54})\\fn{font}\\fs{size}\\b1\\bord0\\shad2\\4c&H000000&\\1c&HFFFFFF&\\fad(180,250)}}{typed}')
    return lines


def word_boxes(cue,colour):
    """The word being read gets a coloured box (thick outline in the accent colour);
    word times are spread over the cue by word length (cue timing stays exact)."""
    words=cue['text'].split()
    size=f'\\fs{cue["font_size"]}' if cue.get('font_size') else ''
    if len(words)<2:return [f'Dialogue: 0,{timecode(cue["start"])},{timecode(cue["end"])},Subtitle,,0,0,0,,'+ ('{'+size+'}' if size else '') + escape(cue['text'])]
    weights=[len(w)+1 for w in words];total=sum(weights);span=cue['end']-cue['start'];at=cue['start'];out=[];box=ass_colour(colour)[4:]
    for i,w in enumerate(weights):
        end=cue['end'] if i==len(words)-1 else at+span*w/total
        parts=re.split(r'(\s+)',cue['text']);word_index=-1;rendered=[]
        for part in parts:
            if not part.isspace() and part:
                word_index+=1
                rendered.append(f'{{\\3c&H{box}&\\bord10\\shad0}}{escape(part)}{{\\r{size}}}' if word_index==i else escape(part))
            else:rendered.append(escape(part))
        text=('{'+size+'}' if size else '')+''.join(rendered)
        out.append(f'Dialogue: 0,{timecode(at)},{timecode(end)},Subtitle,,0,0,0,,{text}');at=end
    return out


def create(cues,scenes,duration,*,subtitles=True,overlays=True,editing_style='basic',emphasis=None,subtitle_style=None,graphic_style=None):
    warnings=[]
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,90,90,60,1
Style: Overlay,Arial,56,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,100,100,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    smart=editing_style in ('balanced','dynamic','adaptive')
    if smart:
        # Owner preference is explicit in the Render UI. Words/times stay exact;
        # only the visual profile changes, independently of upper emphasis.
        size=50 if editing_style in ('balanced','adaptive') else 52
        header=header.replace('Style: Subtitle,Arial,48,','Style: Subtitle,Arial,'+str(size)+',').replace(
            '&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,90,90,60,1',
            '&H80000000,-1,0,0,0,100,100,0,0,1,3.5,1,2,100,100,72,1')
        emphasis_size=68 if editing_style in ('balanced','adaptive') else 74
        styles=f'Style: EmphasisLeft,Arial,{emphasis_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,7,110,110,120,1\nStyle: EmphasisCenter,Arial,{emphasis_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,8,110,110,120,1\n\n'
        styles=styles.replace('\n\n','\nStyle: Graphic,Arial,60,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n\n',1)  # graphics, [SIRA] badge, [ŞERİT] band
        header=header.replace('[Events]',styles+'[Events]')
    header=styled(header,subtitle_style)
    lines=[]
    if subtitles:
        try:valid=validate_cues([{k:c[k] for k in ('start','end','text')} for c in cues],duration,allow_empty=True)
        except SubtitleError:raise RenderError('subtitle_invalid','Aktif altyazı metni veya zamanları geçersiz. Altyazı ve Zamanlama ekranını kontrol edin.') from None
        highlight=(graphic_style or {}).get('accent') or '#3D9BFF' if (subtitle_style or {}).get('word_highlight') else None
        for cue in valid:
            # Fit using the actual selected font; only presentation changes.
            cue=dict(cue)
            requested=(subtitle_style or {}).get('size',50 if smart else 48)
            if any(e.get('style') in ('lower_third','band2') and e['start']<cue['end'] and e['end']>cue['start'] for e in emphasis or []):requested=min(requested,64)
            size,text=fitted(cue['text'], (subtitle_style or {}).get('font','Arial'), 1680, 2,requested)
            cue['text']=text
            cue['font_size']=size
            if highlight:lines+=word_boxes(cue,highlight);continue
            lines.append(f'Dialogue: 0,{timecode(cue["start"])},{timecode(cue["end"])},Subtitle,,0,0,0,,{{\\fs{size}}}{escape(cue["text"])}')
    if smart and emphasis is not None and overlays:
        for item in emphasis:
            start,end=item['start'],item['end'];text=item['text']
            if not 0<=start<end<=duration or not isinstance(text,str) or len(text)>500 or any(ord(c)<32 and c not in '\n\r\t' for c in text):
                warnings.append('Geçersiz bir vurgu yazısı atlandı.');continue
            if item.get('style')=='badge':lines+=badge(item,start,end,graphic_style);continue
            if item.get('style')=='band2':lines+=band2(item,start,end,graphic_style);continue
            if graphic_style:
                lines+=graphic(item,start,end,graphic_style);continue
            style='EmphasisLeft' if item.get('style') in ('upper_left','lower_third') else 'EmphasisCenter'
            size,text=fitted(text,'Arial',1500,2,64)
            animation=r'{\fad(180,100)\fscx98\fscy98\t(0,180,\fscx100\fscy100)}'
            if item.get('style')=='lower_third':animation=r'{\an7\pos(120,'+str(H_LOWER)+r')\fad(180,100)}'
            animation+='{\\fs'+str(size)+'}'
            lines.append(f'Dialogue: 1,{timecode(start)},{timecode(end)},{style},,0,0,0,,{animation}{escape(text)}')
    elif overlays:
        for scene in scenes:
            text=scene.get('overlay_text','')
            if not text:continue
            if (not isinstance(text,str) or len(text)>500 or any(ord(c)<32 and c not in '\r\n\t' for c in text)
                    or not isinstance(scene['start'],(int,float)) or not math.isfinite(scene['start'])):
                warnings.append('Geçersiz bir vurgu yazısı atlandı.');continue
            start=scene['start'];end=min(scene['end'],start+3,duration)
            if end-start<.1:warnings.append('Çok kısa sahnede vurgu yazısı atlandı.');continue
            size,text=fitted(text,'Arial',1500,2,56)
            lines.append(f'Dialogue: 1,{timecode(start)},{timecode(end)},Overlay,,0,0,0,,{{\\fs{size}}}{escape(text)}')
    return header+'\n'.join(lines)+'\n',warnings,bool(lines)
