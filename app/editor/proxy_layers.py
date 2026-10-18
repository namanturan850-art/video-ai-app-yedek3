"""Flatten adjacent static text layers only inside disposable proxy snapshots."""
from copy import deepcopy
import math
from PIL import Image
from app.editor.compositor import text_image


def flatten(document,assets,folder,width,height):
    doc=deepcopy(document);resolved=dict(assets)
    ordered=sorted(doc['clips'],key=lambda c:(c['order'],c['id']));output=[];group=[]
    def eligible(c):
        tr=c['transform'];fx=c['effects']
        return (c['kind']=='text' and c['visible'] and not c['keyframes'] and not c['fade_in'] and not c['fade_out']
                and tr['scale']==1 and tr['rotation']==0 and tr['opacity']==1 and not tr['flip_x'] and not tr['flip_y']
                and not any(tr[k] for k in ('crop_left','crop_right','crop_top','crop_bottom'))
                and (not fx['enabled'] or (fx['brightness']==0 and fx['contrast']==1 and fx['saturation']==1 and not any(fx[k] for k in ('blur','sharpen','monochrome','vignette')))))
    def flush():
        if len(group)<2:output.extend(group);group.clear();return
        canvas=Image.new('RGBA',(width,height),(0,0,0,0))
        for clip in group:
            with Image.open(text_image(clip,folder,width,height)) as image:
                tr=clip['transform'];x=math.floor(tr['x']*width/1920/2)*2;y=math.floor(tr['y']*height/1080/2)*2
                canvas.alpha_composite(image.convert('RGBA'),(x,y))
        clip=deepcopy(group[0]);clip['transform']['x']=clip['transform']['y']=0
        bounds=canvas.getbbox() or (0,0,2,2)
        left,top=(bounds[0]//2)*2,(bounds[1]//2)*2
        right,bottom=min(width,math.ceil(bounds[2]/2)*2),min(height,math.ceil(bounds[3]/2)*2)
        path=folder/f'static-{clip["id"]}.png';canvas.crop((left,top,right,bottom)).save(path)
        resolved[clip['id']]={'path':path,'type':'image','has_audio':False,'proxy_static':True,'proxy_rect':(left,top)};output.append(clip);group.clear()
    for clip in ordered:
        if not eligible(clip):flush();output.append(clip);continue
        if group and (clip['start'],clip['end'])!=(group[0]['start'],group[0]['end']):flush()
        group.append(clip)
    flush();doc['clips']=output
    return doc,resolved
