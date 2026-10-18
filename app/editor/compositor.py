"""One local FFmpeg graph for saved edits in program frames AND final assembly.

All expressions are generated from validated numeric values, never user code.
Text is rasterized to RGBA; user text/paths never enter FFmpeg filter syntax.
"""
from copy import deepcopy
from pathlib import Path
import math

from app.editor.advanced import Document
from app.editor.curves import progress,progress_expression
from app.rendering.models import RenderError


def value_at(edit,prop,time):
    points=sorted((k for k in edit.get('keyframes',[]) if k['property']==prop),key=lambda k:k['time'])
    if not points:return edit.get('transform',{}).get(prop,1 if prop in ('scale','opacity') else 0)
    if time<=points[0]['time']:return points[0]['value']
    for a,b in zip(points,points[1:]):
        if time<=b['time']:
            u=(time-a['time'])/(b['time']-a['time'])
            u=progress(b,u)
            return a['value']+(b['value']-a['value'])*u
    return points[-1]['value']


def expression(edit,prop,var='t'):
    points=sorted((k for k in edit.get('keyframes',[]) if k['property']==prop),key=lambda k:k['time'])
    if not points:return str(float(value_at(edit,prop,0)))
    result=str(float(points[-1]['value']))
    for a,b in reversed(list(zip(points,points[1:]))):
        u=f'clip((({var})-{a["time"]})/{b["time"]-a["time"]},0,1)'
        u=progress_expression(b,u)
        result=f'if(lt(({var}),{b["time"]}),{a["value"]}+({b["value"]-a["value"]})*({u}),{result})'
    return f'if(lt(({var}),{points[0]["time"]}),{points[0]["value"]},{result})'


def text_image(clip,folder,width,height):
    from PIL import Image,ImageDraw,ImageFont
    from app.text_layout import fit_text
    from app.channels import FONTS
    font_path=Path(__file__).resolve().parents[1]/'static/fonts'/FONTS[clip.get('font','inter')][1]
    def make_font(size):
        font=ImageFont.truetype(str(font_path),max(8,int(size)))
        try:font.set_variation_by_axes([700 if b'Weight' in a['name'] and clip.get('font_weight')=='bold' else a['default'] for a in font.get_variation_axes()])
        except (OSError,AttributeError):pass
        return font
    size=max(8,round(clip['font_size']*width/1920))
    def measure(text,size):return make_font(size).getlength(text)
    size,lines=fit_text(clip['text'],measure,width*clip.get('text_width',.84),4,size,smallest=8)
    font=make_font(size)
    synthetic_bold=False
    if clip.get('font_weight')=='bold':
        try:font.get_variation_axes()
        except (OSError,AttributeError):synthetic_bold=True
    image=Image.new('RGBA',(width,height));draw=ImageDraw.Draw(image)
    align=clip.get('text_align','center');content='\n'.join(lines);bounds=draw.multiline_textbbox((0,0),content,font=font,align=align)
    x=(width-(bounds[2]-bounds[0]))/2;y=(height-(bounds[3]-bounds[1]))/2
    if clip.get('text_background'):
        from PIL import ImageColor
        draw.rounded_rectangle((x-12,y-8,x+bounds[2]+12,y+bounds[3]+8),radius=8,fill=(*ImageColor.getrgb(clip['text_background']),round(clip['background_opacity']*255)))
    draw.multiline_text((x,y),content,font=font,fill=clip['color'],align=align,stroke_width=max(1,width//960),stroke_fill='#111111')
    if synthetic_bold:draw.multiline_text((x,y),content,font=font,fill=clip['color'],align=align,stroke_width=1,stroke_fill=clip['color'])
    path=Path(folder)/f'text-{clip["id"]}.png';image.save(path);return path


def shape_image(clip,folder,width,height):
    from PIL import Image,ImageDraw
    image=Image.new('RGBA',(width,height));draw=ImageDraw.Draw(image);r=height*clip['shape_size'];x,y=width/2,height/2;color=clip['color']
    if clip['shape']=='pin':
        draw.polygon([(x-r,y-r/2),(x+r,y-r/2),(x,y+r*2)],fill=color)
        draw.ellipse((x-r,y-r*1.5,x+r,y+r/2),fill=color)
        draw.ellipse((x-r*.35,y-r*.85,x+r*.35,y-r*.15),fill='#18181B')
    elif clip['shape']=='arrow':draw.polygon([(x-2*r,y-r/3),(x,y-r/3),(x,y-r),(x+2*r,y),(x,y+r),(x,y+r/3),(x-2*r,y+r/3)],fill=color)
    else:draw.rectangle((x-2*r,y-r,x+2*r,y+r),fill=color)
    path=Path(folder)/f'shape-{clip["id"]}.png';image.save(path);return path


def motion_asset(clip,folder,kit=None,cancelled=None,language='de',sample_time=None):
    from app.motion.clips import render_clip
    from app.channels import DEFAULT_STYLE
    style=deepcopy(kit or DEFAULT_STYLE)
    if clip.get('motion_color'):style['palette']['accent']=clip['motion_color']
    spec={**clip['motion'],'local_only':True,'clean_source':clip.get('clean_map',False)}
    from app.motion.places import offline
    from app.motion.control import MotionCancelled
    try:
        with offline():
            path,_,_=render_clip(folder,spec,style,clip.get('animation_duration') or clip['end']-clip['start'],0,language=language,prefer_openmontage=False,cancelled=cancelled,sample_time=(sample_time+clip.get('animation_offset',0) if sample_time is not None else None),element_edits=clip.get('motion_elements'))
    except MotionCancelled:raise
    except (RuntimeError,OSError,ValueError):
        if spec['template']=='documentary':
            raise RenderError('animation_render_failed','Animasyon yerel olarak çizilemedi. FFmpeg kurulumunu ve animasyon verisini kontrol edin; şeffaf sahnelerde qtrle desteği gerekir.') from None
        raise
    return {'path':path,'type':'video','has_audio':False,'sampled':sample_time is not None}


def resolve(projects,pid,document,archive_file,*,kit=None,draw=False,verify=None,language='de',frame_time=None):
    """Verify file identities even on a cache hit. Motion draws only in a job/preview."""
    from app.editor.service import sha256_file
    assets={}
    for clip in document['clips']:
        if not clip['visible']:continue
        if clip['kind']=='media':
            ref=clip['media'];path,asset=archive_file(pid,ref['provider'],ref['media_id'])
            digest=verify(path,ref['sha256']) if verify else sha256_file(path)
            if digest!=ref['sha256']:raise RenderError('source_stale','Ek kurgu kaynak dosyası değişmiş.')
            assets[clip['id']]={'path':path,'type':asset['media_type'],'sha256':ref['sha256'],'has_audio':asset.get('has_audio',asset['media_type']=='audio')}
        elif clip['kind']=='motion':
            for ref in clip.get('motion_sources',[]):
                path,_=archive_file(pid,ref['provider'],ref['media_id'])
                digest=verify(path,ref['sha256']) if verify else sha256_file(path)
                if digest!=ref['sha256']:raise RenderError('source_stale','Animasyonun görsel kaynağı değişmiş.')
            if draw:assets[clip['id']]=motion_asset(clip,projects._path(pid)/'stock',kit,language=language,sample_time=frame_time-clip['start'] if frame_time is not None else None)
    return assets


def archive_file(projects,pid,provider,media_id):
    from contextlib import closing
    import json
    from app.stock.download import asset_path
    with closing(projects._connection()) as c:
        row=c.execute('SELECT media_type,metadata_json FROM stock_assets WHERE project_id=? AND provider=? AND media_id=?',(pid,provider,media_id)).fetchone()
    if not row:raise RenderError('source_stale','Ek kurgu arşiv kaynağı bulunamadı.')
    item={**json.loads(row['metadata_json']),'provider':provider,'media_id':media_id,'media_type':row['media_type']}
    return asset_path(projects,pid,item),item


def compile_graph(args,document,assets,base='0:v',*,folder,duration,width=1920,height=1080,adjustment_slots=None,frame_time=None,narration=None,audio_only=False,include_audio=True):
    """Append local inputs and return graph, video label, supplemental audio labels.

    Base adjustments operate before supplementary layers and before subtitles.
    frame_time uses the same graph with scalar keyframe values for a still.
    """
    doc=Document.model_validate(document).model_dump();graphs=[];current=base;audio=[];counter=0
    def label():
        nonlocal counter
        counter+=1;return f'adv{counter}'
    def input_file(path,kind,source_start=0,speed=1,seconds=None):
        index=args.count('-i');args.extend(['-threads','1'])
        if kind=='image':args.extend(['-loop','1','-framerate','30'])
        elif source_start:args.extend(['-ss',f'{source_start:.6f}'])
        args.extend(['-t',f'{(seconds or duration)*speed+.1:.6f}','-i',str(path)])
        return index
    def audio_chain(index,edit,length,speed,start):
        offset=edit.get('animation_offset',0);animation_length=edit.get('animation_duration') or length
        al=label();chain=f'[{index}:a]aresample=48000,atrim=duration={length*speed},asetpts=PTS-STARTPTS'
        tempo=speed
        while tempo<.5:chain+=',atempo=0.5';tempo/=.5
        while tempo>2:chain+=',atempo=2';tempo/=2
        chain+=f',atempo={tempo},asetpts=N/SR/TB,volume=\'{expression(edit,"volume",f"t+{offset}")}\':eval=frame'
        if edit['fade_in']:chain+=f",volume='min(1,(t+{offset})/{edit['fade_in']})':eval=frame"
        if edit['fade_out']:chain+=f",volume='max(0,min(1,({animation_length}-t-{offset})/{edit['fade_out']}))':eval=frame"
        # Sample counts keep delay/padding exact after atempo, whose last buffer
        # can carry a timestamp beyond its actual sample count.
        samples=round(duration*48000)
        chain+=f',adelay={round(start*48000)}S:all=1,apad=whole_len={samples},atrim=end_sample={samples},asetpts=N/SR/TB[{al}]'
        graphs.append(chain)
        if edit.get('ducking') and narration:
            side=input_file(narration,'audio',seconds=duration);voice=label();out=label()
            # Pad the sidechain clock: decoder EOF must not truncate delayed/
            # atempo music before its exact master-clock end.
            graphs.append(f'[{side}:a]aresample=48000,asetpts=PTS-STARTPTS,apad[{voice}]')
            graphs.append(f'[{al}][{voice}]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=250,atrim=end_sample={samples},asetpts=N/SR/TB[{out}]');al=out
        audio.append(al)
    edits=[]
    for edit in doc['adjustments']:
        slot=(adjustment_slots or {}).get(edit['slot_id'])
        if slot:edits.append({**edit,**{k:slot[k] for k in ('start','end')},'id':edit['slot_id'],'kind':'adjustment','track':'visuals'})
    edits+=sorted((c for c in doc['clips'] if c['visible']),key=lambda c:(c['order'],c['id']))
    for edit in edits:
        start,end=edit['start'],edit['end'];length=end-start
        offset=edit.get('animation_offset',0);animation_length=edit.get('animation_duration') or length
        if frame_time is not None and not start<=frame_time<end:continue
        asset=assets.get(edit['id']);tr=edit['transform'];speed=tr['speed']
        local=(frame_time-start+offset) if frame_time is not None else None
        expr=lambda prop,var='t':str(float(value_at(edit,prop,local))) if local is not None else expression(edit,prop,f'{var}-{start}+{offset}')
        if audio_only:
            if asset and (asset.get('type')=='audio' or asset.get('has_audio')) and (tr['volume'] or any(k['property']=='volume' for k in edit['keyframes'])):
                source_start=asset.get('segment_start',0) if edit['kind']=='adjustment' else edit.get('source_start',0)
                i=input_file(asset['path'],asset['type'],source_start,speed,length);audio_chain(i,edit,length,speed,start)
            continue
        if edit.get('track')=='audio':
            if not include_audio:continue
            i=input_file(asset['path'],'audio',edit.get('source_start',0),speed,length)
            audio_chain(i,edit,length,speed,start);continue
        adjustment=edit['kind']=='adjustment'
        if adjustment:
            keep,source=label(),label();graphs.append(f'[{current}]split[{keep}][{source}]');current=keep
            if include_audio and frame_time is None and asset and asset.get('has_audio') and (tr['volume'] or any(k['property']=='volume' for k in edit['keyframes'])):
                i=input_file(asset['path'],'video',asset.get('segment_start',0),speed,length);audio_chain(i,edit,length,speed,start)
        else:
            if edit['kind']=='text' and not (asset or {}).get('proxy_static'):asset={'path':text_image(edit,folder,width,height),'type':'image','has_audio':False}
            if edit['kind']=='shape':asset={'path':shape_image(edit,folder,width,height),'type':'image','has_audio':False}
            if not asset:raise RenderError('advanced_missing','Ek animasyonun yerel önizleme dosyası hazırlanamadı.')
            source_start=edit.get('source_start',0)+((local-offset)*speed if local is not None else 0)
            if asset.get('sampled'):source_start=0
            i=input_file(asset['path'],asset['type'],source_start,speed,length if local is None else .04)
            source=f'{i}:v'
            if include_audio and frame_time is None and asset.get('has_audio') and (tr['volume'] or any(k['property']=='volume' for k in edit['keyframes'])):audio_chain(i,edit,length,speed,start)
        stage=label();chain=f'[{source}]'
        if not adjustment:chain+=f'setpts=(PTS-STARTPTS)/{speed}'+(f'+{start}/TB,' if local is None else ',')
        l,r,t,b=(tr[k] for k in ('crop_left','crop_right','crop_top','crop_bottom'))
        chain+=f'crop=iw*{1-l-r}:ih*{1-t-b}:iw*{l}:ih*{t},'
        if tr['flip_x']:chain+='hflip,'
        if tr['flip_y']:chain+='vflip,'
        fx=edit['effects']
        if fx['enabled']:
            chain+=f'eq=brightness={fx["brightness"]}:contrast={fx["contrast"]}:saturation={0 if fx["monochrome"] else fx["saturation"]},'
            if fx['blur']:chain+=f'gblur=sigma={fx["blur"]},'
            if fx['sharpen']:chain+=f'unsharp=5:5:{fx["sharpen"]},'
            if fx['vignette']:chain+='vignette=PI/5,'
        # Source aspect ratio remains intact; scale is uniform, never a stretch.
        if not (asset or {}).get('proxy_rect'):chain+=f'scale={width}:{height}:force_original_aspect_ratio=decrease,'
        chain+='setsar=1,format=rgba,'
        if tr['scale']!=1 or any(k['property']=='scale' for k in edit['keyframes']):
            chain+=f'scale=w=\'max(2,trunc(iw*({expr("scale")} )/2)*2)\':h=\'max(2,trunc(ih*({expr("scale")})/2)*2)\':eval=frame,'
        if tr['rotation'] or any(k['property']=='rotation' for k in edit['keyframes']):
            # rotate evaluates output dimensions at graph initialization. Reserve
            # a stable canvas for the largest saved scale so later zoom frames
            # are not clipped and sampled previews use the same geometry.
            largest=max([tr['scale']]+[k['value'] for k in edit['keyframes'] if k['property']=='scale'])
            canvas=max(2,math.ceil(math.hypot(width,height)*largest/2)*2)
            chain+=f'rotate=angle=\'({expr("rotation")})*PI/180\':ow={canvas}:oh={canvas}:c=none,'
        if any(k['property']=='opacity' for k in edit['keyframes']):
            chain+=f'geq=r=\'r(X,Y)\':g=\'g(X,Y)\':b=\'b(X,Y)\':a=\'alpha(X,Y)*({expr("opacity","T")})\','
        elif tr['opacity']!=1:chain+=f'colorchannelmixer=aa={tr["opacity"]},'
        if edit['fade_in'] or edit['fade_out']:
            if frame_time is None:
                clock=f'(T-{start}+{offset})'
                alpha=f"min(1,{clock}/{edit['fade_in']})" if edit['fade_in'] else '1'
                if edit['fade_out']:alpha=f"({alpha})*max(0,min(1,({animation_length}-{clock})/{edit['fade_out']}))"
                chain+=f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*({alpha})',"
            else:
                alpha=min(1,local/edit['fade_in'] if edit['fade_in'] else 1,(animation_length-local)/edit['fade_out'] if edit['fade_out'] else 1)
                if alpha<1:chain+=f'colorchannelmixer=aa={max(0,alpha)},'
        chain=chain.rstrip(',')+f'[{stage}]';graphs.append(chain)
        x=f'(W-w)/2+({expr("x")})*{width}/1920';y=f'(H-h)/2+({expr("y")})*{height}/1080'
        if (asset or {}).get('proxy_rect'):x,y=map(str,asset['proxy_rect'])
        enabled=f"between(t,{start},{end-1/3000})" if frame_time is None else '1'
        if adjustment:
            black=label();graphs.append(f'color=c=black:s={width}x{height}:r=30:d={duration}[{black}]')
            filled=label();graphs.append(f'[{black}][{stage}]overlay=x=\'{x}\':y=\'{y}\':eval=frame:eof_action=pass:shortest=0[{filled}]');stage=filled;x=y='0'
        out=label();graphs.append(f'[{current}][{stage}]overlay=x=\'{x}\':y=\'{y}\':eval=frame:eof_action=pass:enable=\'{enabled}\'[{out}]');current=out
    return ';\n'.join(graphs),current,audio
