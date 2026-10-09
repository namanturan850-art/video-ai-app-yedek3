"""Internally generated Unicode ASS; cue timing is read, never regenerated."""
import math
from app.rendering.models import RenderError
from app.subtitles.models import validate_cues,SubtitleError


def timecode(seconds):
    cs=round(seconds*100);h,cs=divmod(cs,360000);m,cs=divmod(cs,6000);s,cs=divmod(cs,100)
    return f'{h}:{m:02}:{s:02}.{cs:02}'


def escape(text):
    # ASS reserved syntax is escaped in the data file, never in shell/filter syntax.
    return text.replace('\\','\\\\').replace('{',r'\{').replace('}',r'\}').replace('\r','').replace('\n',r'\N')


def create(cues,scenes,duration,*,subtitles=True,overlays=True,editing_style='basic',emphasis=None):
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
    smart=editing_style in ('balanced','dynamic')
    if smart:
        size=50 if editing_style=='balanced' else 52
        header=header.replace('Style: Subtitle,Arial,48,','Style: Subtitle,Arial,'+str(size)+',').replace('&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,90,90,60,1','&H80000000,-1,0,0,0,100,100,0,0,1,3.5,1,2,100,100,72,1')
        emphasis_size=68 if editing_style=='balanced' else 74
        styles=f'Style: EmphasisLeft,Arial,{emphasis_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,7,110,110,120,1\nStyle: EmphasisCenter,Arial,{emphasis_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,8,110,110,120,1\n\n'
        header=header.replace('[Events]',styles+'[Events]')
    lines=[]
    if subtitles:
        try:valid=validate_cues([{k:c[k] for k in ('start','end','text')} for c in cues],duration)
        except SubtitleError:raise RenderError('subtitle_invalid','Aktif altyazı metni veya zamanları geçersiz. Altyazı ve Zamanlama ekranını kontrol edin.') from None
        for cue in valid:
            animation=r'{\fad(100,60)}' if smart else ''
            lines.append(f'Dialogue: 0,{timecode(cue["start"])},{timecode(cue["end"])},Subtitle,,0,0,0,,{animation}{escape(cue["text"])}')
    if smart and emphasis is not None and overlays:
        for item in emphasis:
            start,end=item['start'],item['end'];text=item['text']
            if not 0<=start<end<=duration or not isinstance(text,str) or len(text)>500 or any(ord(c)<32 and c not in '\n\r\t' for c in text):
                warnings.append('Geçersiz bir vurgu yazısı atlandı.');continue
            style='EmphasisLeft' if item.get('style')=='upper_left' else 'EmphasisCenter'
            animation=r'{\fad(180,100)\fscx98\fscy98\t(0,180,\fscx100\fscy100)}'
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
            lines.append(f'Dialogue: 1,{timecode(start)},{timecode(end)},Overlay,,0,0,0,,{escape(text)}')
    return header+'\n'.join(lines)+'\n',warnings,bool(lines)
