"""Reusable 2D/2.5D actors evaluated from frame time, shared by preview/export."""
import math
from random import Random
from PIL import Image,ImageDraw

FPS=30


def at(edit,t):
    result={k:edit.get(k,v) for k,v in (('x',0),('y',0),('scale',1),('rotation',0),('opacity',1),('progress',1))}
    for prop in {k['property'] for k in edit.get('keyframes',[])}:
        keys=sorted((k for k in edit['keyframes'] if k['property']==prop),key=lambda k:k['time'])
        value=keys[0]['value']
        for a,b in zip(keys,keys[1:]):
            if t<a['time']:break
            if t>=b['time']:value=b['value'];continue
            f=(t-a['time'])/(b['time']-a['time'])
            if b['easing']=='hold':f=0
            elif b['easing']=='ease_in_out':f=f*f*(3-2*f)
            value=a['value']+(b['value']-a['value'])*f;break
        result[prop]=value
    return result


def build(data,kit,duration):
    from app.motion.templates import Scene
    # The importer/AdvancedEditor validated context and local keyframe bounds.
    s=Scene(kit,duration,0);s.ease='linear'
    for obj in sorted(data['objects'],key=lambda a:a['layer']):
        s.add('documentary_object',object=obj,label=obj['id']+' · '+obj['kind'],camera=data['camera'],duration=s.D,x=obj['x'],y=obj['y'],opacity=1,
              fill=obj['color'],stroke=obj['stroke'],font=s.body)
    notice={'demo':'DEMO — temsili veriler','schematic':'ŞEMATİK ANLATIM — fizik simülasyonu değildir','narration':'VERİLER: PROJE ANLATIMI'}[data['basis']]
    if data['basis']=='narration' and any(o['kind'] in ('cloud','flow','lightning','wave','particles') for o in data['objects']):notice+=' · ŞEMATİK'
    s.add('text',text=notice,x=960,y=64,size=24,font=s.body,fill='#FFFFFF',anchor='mm',opacity=1,
          shadow=True,required_notice=True)
    result=s.result();result.update(background=data['background'] or '#000000',alpha=data['background'] is None,
                                    procedural=True,animation_engine_version=1)
    return result


def draw(image,p,t):
    """Draw one object; no wall clock, network, callbacks or accumulated state."""
    t=max(0,math.floor(t*FPS+1e-6)/FPS)
    obj=p['object'];end=obj['end'] if obj['end'] is not None else p['duration']
    if t<obj['start'] or end is not None and t>=end:return
    elapsed=t-obj['start'];state=at(obj,t);camera=at(p['camera'],t)
    state['x']+=p['x']-obj['x'];state['y']+=p['y']-obj['y']
    opacity=state['opacity']*p.get('opacity',1)
    if opacity<=.003:return
    from app.motion.raster import rgba
    from app.motion.templates import _font
    draw=ImageDraw.Draw(image,'RGBA');w,h=obj['width'],obj['height'];scale=state['scale']*camera['scale']
    angle=math.radians(state['rotation']);ca,sa=math.cos(angle),math.sin(angle)
    def xy(x,y):
        xx=state['x']+state['scale']*(x*ca-y*sa)
        yy=state['y']+state['scale']*(x*sa+y*ca)
        return (960+(xx-960-camera['x'])*camera['scale'],540+(yy-540-camera['y'])*camera['scale'])
    color=rgba(p['fill'],opacity);stroke=rgba(p['stroke'],opacity);lw=max(1,round(obj['line_width']*scale))
    available=max(0,end-obj['start']-1/FPS)
    progress=state['progress'] if any(k['property']=='progress' for k in obj['keyframes']) else (1 if available<=1/FPS else min(1,elapsed/min(.8,available)))
    def line(points,fill=stroke,width=lw):
        draw.line([xy(x,y) for x,y in points],fill=fill,width=width,joint='curve')
    def polygon(points,fill=color):draw.polygon([xy(x,y) for x,y in points],fill=fill)
    def circle(x,y,r,fill=color,outline=None):
        cx,cy=xy(x,y);rr=max(.5,r*scale)
        draw.ellipse((cx-rr,cy-rr,cx+rr,cy+rr),fill=fill,outline=outline,width=lw)
    def text(value,x,y,size=36,fill=stroke,width=None):
        cx,cy=xy(x,y);size=max(12,min(768,round(size*scale)))
        font=_font(p['font'],size,True);limit=min(1760,(width or w)*scale)
        measured=font.getlength(value)
        if measured>limit:
            size=max(12,math.floor(size*limit/max(1,measured)));font=_font(p['font'],size,True)
            while size>12 and font.getlength(value)>limit:
                size-=1;font=_font(p['font'],size,True)
        cx=min(max(cx,80+font.getlength(value)/2),1840-font.getlength(value)/2)
        bounds=font.getbbox(value)
        patch=Image.new('RGBA',(max(1,bounds[2]-bounds[0]+8),max(1,bounds[3]-bounds[1]+8)),(0,0,0,0))
        ImageDraw.Draw(patch).text((4-bounds[0],4-bounds[1]),value,font=font,fill=fill)
        if state['rotation']:
            patch=patch.rotate(-state['rotation'],resample=Image.Resampling.BICUBIC,expand=True)
        image.alpha_composite(patch,(round(cx-patch.width/2),round(cy-patch.height/2)))
    def rect(x,y,ww,hh,fill=color):polygon([(x,y),(x+ww,y),(x+ww,y+hh),(x,y+hh)],fill)
    d=obj['data'];kind=obj['kind']
    if kind=='cloud':
        drift=d['drift']*elapsed
        # Layered lobes, restrained lower shadow, no claim of volumetric physics.
        for i in range(d['lobes']):
            x=(i/(d['lobes']-1)-.5)*w*.7+drift;y=-math.sin(i/(d['lobes']-1)*math.pi)*h*.22
            circle(x,y,min(h*.40,w/d['lobes']*.9))
        line([(-w*.34+drift,h*.25),(w*.34+drift,h*.25)],fill=rgba(p['stroke'],opacity*.35),width=max(1,lw//2))
    elif kind in ('box','node','isometric_box'):
        if kind=='isometric_box':
            depth=min(w,h)*.25
            polygon([(-w/2,-h/2),(-w/2+depth,-h/2-depth),(w/2+depth,-h/2-depth),(w/2,-h/2)],stroke)
            polygon([(w/2,-h/2),(w/2+depth,-h/2-depth),(w/2+depth,h/2-depth),(w/2,h/2)],rgba(p['fill'],opacity*.55))
        rect(-w/2,-h/2,w,h)
        if kind=='node':text(d['text'],0,0,d['font_size'])
    elif kind=='circle':circle(0,0,min(w,h)/2)
    elif kind=='label':text(d['text'],0,0,d['font_size'],color)
    elif kind in ('line','arrow','flow'):
        points=[(q['x'],q['y']) for q in d['points']]
        lengths=[math.dist(a,b) for a,b in zip(points,points[1:])];total=sum(lengths) or 1
        def path_at(distance):
            for a,b,length in zip(points,points[1:],lengths):
                if distance<=length:
                    f=distance/(length or 1);return (a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f)
                distance-=length
            return points[-1]
        limit=total*progress;shown=[points[0]];distance=0
        for point,length in zip(points[1:],lengths):
            if distance+length>limit:break
            shown.append(point);distance+=length
        shown.append(path_at(limit));line(shown)
        if kind in ('arrow','flow') and progress>.02:
            a=path_at(max(0,limit-20));b=path_at(limit);angle=math.atan2(b[1]-a[1],b[0]-a[0]);head=12
            polygon([b,(b[0]-head*math.cos(angle-.55),b[1]-head*math.sin(angle-.55)),(b[0]-head*math.cos(angle+.55),b[1]-head*math.sin(angle+.55))],stroke)
        if kind=='flow':
            for i in range(d['particles']):
                distance=(elapsed*d['speed']+i*total/max(1,d['particles']))%total
                if distance<=limit:circle(*path_at(distance),5)
    elif kind=='lightning':
        phase=(elapsed*d['frequency'])%1
        if not .35<=phase<=.65:return
        rng=Random(d['seed']+int(elapsed*d['frequency']));points=[(0,-h/2)]
        points += [(rng.uniform(-w/2,w/2),-h/2+h*i/d['segments']) for i in range(1,d['segments'])]
        points.append((0,h/2))
        line(points,rgba(p['fill'],opacity*.18),lw*5);line(points,color,lw*2);line(points,stroke,max(1,lw//2))
    elif kind in ('bar_chart','line_chart'):
        items=d['items'];maximum=max(i['value'] for i in items) or 1
        line([(-w/2,-h/2),(-w/2,h/2),(w/2,h/2)],rgba(p['stroke'],opacity*.5),max(1,lw//2))
        points=[];gap=w/len(items)
        for i,item in enumerate(items):
            stagger=min(.08,available/(len(items)*3))
            span=min(.8,max(1e-6,available-stagger*(len(items)-1)))
            grow=(1 if available<=1/FPS else max(0,min(1,(elapsed-i*stagger)/span))) if not any(k['property']=='progress' for k in obj['keyframes']) else progress
            height=h*item['value']/maximum*grow;x=-w/2+gap*(i+.5)
            if kind=='bar_chart' and height>.5:rect(x-gap*.3,h/2-height,gap*.6,height)
            points.append((x,h/2-height))
            text(item['label'],x,h/2+32,28,width=gap*.85)
            text(format(item['value'],'.12g'),x,h/2-height-26,28,width=gap*.85)
        if kind=='line_chart':
            line(points,color,lw)
            for x,y in points:circle(x,y,6)
        if d['unit']:text(d['unit'],0,-h/2-35,30)
    elif kind=='counter':text(format(d['value']*progress,'.12g')+(' '+d['unit'] if d['unit'] else ''),0,0,d['font_size'],color)
    elif kind=='wave':
        points=[(-w/2+w*i/128,d['amplitude']*math.sin(2*math.pi*(i/128*d['cycles']-elapsed*d['frequency']))) for i in range(129)]
        line(points,color,lw)
    elif kind=='particles':
        rng=Random(d['seed']);direction=math.radians(d['direction'])
        for _ in range(d['count']):
            x=(rng.uniform(0,w)+math.cos(direction)*elapsed*d['speed'])%w-w/2
            y=(rng.uniform(0,h)+math.sin(direction)*elapsed*d['speed'])%h-h/2
            circle(x,y,rng.uniform(1.5,4))
