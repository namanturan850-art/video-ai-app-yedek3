"""One local FFmpeg graph for saved edits in program frames AND final assembly.

All expressions are generated from validated numeric values, never user code.
Text is rasterized to RGBA; user text/paths never enter FFmpeg filter syntax.
"""
from copy import deepcopy
from pathlib import Path
import math

from app.editor.advanced import Document
from app.rendering.models import RenderError


def value_at(edit,prop,time):
    points=sorted((k for k in edit.get('keyframes',[]) if k['property']==prop),key=lambda k:k['time'])
    if not points:return edit.get('transform',{}).get(prop,1 if prop in ('scale','opacity') else 0)
    if time<=points[0]['time']:return points[0]['value']
    for a,b in zip(points,points[1:]):
        if time<=b['time']:
            u=(time-a['time'])/(b['time']-a['time'])
            if b['interpolation']=='ease_in_out':u=u*u*(3-2*u)
            return a['value']+(b['value']-a['value'])*u
    return points[-1]['value']


def expression(edit,prop,var='t'):
    points=sorted((k for k in edit.get('keyframes',[]) if k['property']==prop),key=lambda k:k['time'])
    if not points:return str(float(value_at(edit,prop,0)))
    result=str(float(points[-1]['value']))
    for a,b in reversed(list(zip(points,points[1:]))):
        u=f'clip((({var})-{a["time"]})/{b["time"]-a["time"]},0,1)'
        if b['interpolation']=='ease_in_out':u=f'({u})*({u})*(3-2*({u}))'
        result=f'if(lt(({var}),{b["time"]}),{a["value"]}+({b["value"]-a["value"]})*({u}),{result})'
    return f'if(lt(({var}),{points[0]["time"]}),{points[0]["value"]},{result})'


def text_image(clip,folder,width,height):
    from PIL import Image,ImageDraw,ImageFont
    from app.text_layout import fit_text
    font_path=Path(__file__).resolve().parents[1]/'static/fonts/Inter.ttf'
    size=max(8,round(clip['font_size']*width/1920))
    def measure(text,size):return ImageFont.truetype(str(font_path),max(8,int(size))).getlength(text)
    size,lines=fit_text(clip['text'],measure,width*.84,4,size,smallest=8)
    font=ImageFont.truetype(str(font_path),max(8,int(size)))
    image=Image.new('RGBA',(width,height));draw=ImageDraw.Draw(image)
    content='\n'.join(lines);bounds=draw.multiline_textbbox((0,0),content,font=font,align='center')
    draw.multiline_text(((width-(bounds[2]-bounds[0]))/2,(height-(bounds[3]-bounds[1]))/2),content,font=font,fill=clip['color'],align='center',stroke_width=max(1,width//960),stroke_fill='#111111')
    path=Path(folder)/f'text-{clip["id"]}.png';image.save(path);return path


def resolve(projects,pid,document,archive_file,*,kit=None,draw=False,verify=None):
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
        elif clip['kind']=='motion' and draw:
            from app.motion.clips import render_clip
            from app.channels import DEFAULT_STYLE
            spec={**clip['motion'],'local_only':True}
            path,_,_=render_clip(projects._path(pid)/'stock',spec,kit or DEFAULT_STYLE,clip['end']-clip['start'],0,
                                 prefer_openmontage=False)
            assets[clip['id']]={'path':path,'type':'video','has_audio':False}
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


def compile_graph(args,document,assets,base='0:v',*,folder,duration,width=1920,height=1080,adjustment_slots=None,frame_time=None):
    """Append local inputs and return graph, video label, supplemental audio labels.

    Base adjustments operate before supplementary layers and before subtitles.
    frame_time uses the same graph with scalar keyframe values for a still.
    """
    doc=Document.model_validate(document).model_dump();graphs=[];current=base;audio=[];counter=0
    def label():
        nonlocal counter
        counter+=1;return f'adv{counter}'
    def input_file(path,kind,source_start=0,speed=1,seconds=None):
        index=args.count('-i')
        if kind=='image':args.extend(['-loop','1','-framerate','30'])
        elif source_start:args.extend(['-ss',f'{source_start:.6f}'])
        args.extend(['-t',f'{(seconds or duration)*speed+.1:.6f}','-i',str(path)])
        return index
    def audio_chain(index,edit,length,speed,start):
        al=label();chain=f'[{index}:a]aresample=48000,atrim=duration={length*speed},asetpts=PTS-STARTPTS'
        tempo=speed
        while tempo<.5:chain+=',atempo=0.5';tempo/=.5
        while tempo>2:chain+=',atempo=2';tempo/=2
        chain+=f',atempo={tempo},asetpts=N/SR/TB,volume=\'{expression(edit,"volume")}\':eval=frame'
        if edit['fade_in']:chain+=f',afade=t=in:st=0:d={edit["fade_in"]}'
        if edit['fade_out']:chain+=f',afade=t=out:st={length-edit["fade_out"]}:d={edit["fade_out"]}'
        # Sample counts keep delay/padding exact after atempo, whose last buffer
        # can carry a timestamp beyond its actual sample count.
        samples=round(duration*48000)
        chain+=f',adelay={round(start*48000)}S:all=1,apad=whole_len={samples},atrim=end_sample={samples},asetpts=N/SR/TB[{al}]'
        graphs.append(chain);audio.append(al)
    edits=[]
    for edit in doc['adjustments']:
        slot=(adjustment_slots or {}).get(edit['slot_id'])
        if slot:edits.append({**edit,**{k:slot[k] for k in ('start','end')},'id':edit['slot_id'],'kind':'adjustment','track':'visuals'})
    edits+=sorted((c for c in doc['clips'] if c['visible']),key=lambda c:(c['order'],c['id']))
    for edit in edits:
        start,end=edit['start'],edit['end'];length=end-start
        if frame_time is not None and not start<=frame_time<end:continue
        asset=assets.get(edit['id']);tr=edit['transform'];speed=tr['speed']
        local=(frame_time-start) if frame_time is not None else None
        expr=lambda prop,var='t':str(float(value_at(edit,prop,local))) if local is not None else expression(edit,prop,f'{var}-{start}')
        if edit.get('track')=='audio':
            i=input_file(asset['path'],'audio',edit.get('source_start',0),speed,length)
            audio_chain(i,edit,length,speed,start);continue
        adjustment=edit['kind']=='adjustment'
        if adjustment:
            keep,source=label(),label();graphs.append(f'[{current}]split[{keep}][{source}]');current=keep
            if frame_time is None and asset and asset.get('has_audio') and (tr['volume'] or any(k['property']=='volume' for k in edit['keyframes'])):
                i=input_file(asset['path'],'video',asset.get('segment_start',0),speed,length);audio_chain(i,edit,length,speed,start)
        else:
            if edit['kind']=='text':asset={'path':text_image(edit,folder,width,height),'type':'image','has_audio':False}
            if not asset:raise RenderError('advanced_missing','Ek animasyonun yerel önizleme dosyası hazırlanamadı.')
            source_start=edit.get('source_start',0)+(local*speed if local is not None else 0)
            i=input_file(asset['path'],asset['type'],source_start,speed,length if local is None else .04)
            source=f'{i}:v'
            if frame_time is None and asset.get('has_audio') and (tr['volume'] or any(k['property']=='volume' for k in edit['keyframes'])):audio_chain(i,edit,length,speed,start)
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
        chain+=f'scale={width}:{height}:force_original_aspect_ratio=decrease,setsar=1,format=rgba,'
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
        if frame_time is None:
            if edit['fade_in']:chain+=f'fade=t=in:st={start}:d={edit["fade_in"]}:alpha=1,'
            if edit['fade_out']:chain+=f'fade=t=out:st={end-edit["fade_out"]}:d={edit["fade_out"]}:alpha=1,'
        else:
            alpha=min(1,local/edit['fade_in'] if edit['fade_in'] else 1,(length-local)/edit['fade_out'] if edit['fade_out'] else 1)
            if alpha<1:chain+=f'colorchannelmixer=aa={alpha},'
        chain=chain.rstrip(',')+f'[{stage}]';graphs.append(chain)
        x=f'(W-w)/2+({expr("x")})*{width}/1920';y=f'(H-h)/2+({expr("y")})*{height}/1080'
        enabled=f"between(t,{start},{end-1/3000})" if frame_time is None else '1'
        if adjustment:
            black=label();graphs.append(f'color=c=black:s={width}x{height}:r=30:d={duration}[{black}]')
            filled=label();graphs.append(f'[{black}][{stage}]overlay=x=\'{x}\':y=\'{y}\':eval=frame:eof_action=pass:shortest=0[{filled}]');stage=filled;x=y='0'
        out=label();graphs.append(f'[{current}][{stage}]overlay=x=\'{x}\':y=\'{y}\':eval=frame:eof_action=pass:enable=\'{enabled}\'[{out}]');current=out
    return ';\n'.join(graphs),current,audio
