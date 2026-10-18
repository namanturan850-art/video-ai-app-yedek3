"""Adapt declarative scenes to existing supplementary clips; never apply directly."""
from uuid import uuid4
from pydantic import ValidationError
from app.animation.schema import validate,validation_text
from app.editor.models import EditorError


def description(error):
    if isinstance(error,ValidationError):
        return validation_text(error)
    return str(error)


def validate_item(editor,pid,item,known):
    if not isinstance(item,dict) or not isinstance(item.get('scene_id'),str) or item['scene_id'] not in known:
        raise ValueError('Geçerli scene_id gerekir.')
    if set(item)-{'scene_id','start','end','object_id','track','data','background_media','source_start','sentence_indices'}:
        raise ValueError('Desteklenmeyen animasyon alanı; yalnız paketteki kayıt alanlarını kullanın.')
    if known[item['scene_id']].get('locked'):raise ValueError('Sahne kilitli; değiştirilemez.')
    if item.get('track','layers') not in ('layers','infographics','maps','emphasis'):
        raise ValueError('Animasyon izi layers/infographics/maps/emphasis olmalıdır.')
    try:validate(item.get('data'),known[item['scene_id']]['narration'])
    except (ValueError,TypeError) as error:raise ValueError(description(error)) from None
    if 'background_media' in item:
        from app.editor.advanced import Media
        try:Media.model_validate(item['background_media'])
        except ValidationError as error:raise ValueError(description(error)) from None
    elif 'source_start' in item:raise ValueError('source_start yalnız background_media ile kullanılabilir.')
    indices=item.get('sentence_indices')
    if indices is not None:
        if not isinstance(indices,list) or not 1<=len(indices)<=30 or any(type(i)is not int for i in indices) or len(set(indices))!=len(indices):
            raise ValueError('sentence_indices, 1–30 benzersiz cümle numarası içermelidir.')
        cues=(editor.subtitles.view(pid).get('active') or {}).get('cues',[])
        scene=next(s for s in editor.view(pid)['scenes'] if s['scene_id']==item['scene_id'])
        if any(not 0<=i<len(cues) or not (cues[i]['start']<scene['end'] and cues[i]['end']>scene['start']) for i in indices):
            raise ValueError('Cümle kimliği bu sahnenin altyazı saatleriyle eşleşmiyor.')


def clips_for(item,scene,start,end,slots,source_key,editor=None,pid=None):
    if any(s.get('locked') and start<s['end'] and end>s['start'] for s in slots):
        raise EditorError('locked','Animasyon aralığında kilitli görüntü yuvası var; üzerine eklenmedi.',409)
    if item.get('sentence_indices') is not None and editor is not None:
        cues=(editor.subtitles.view(pid).get('active') or {}).get('cues',[])
        if any(not (0<=i<len(cues) and cues[i]['start']<end and cues[i]['end']>start) for i in item['sentence_indices']):
            raise EditorError('invalid_animation','Cümle kimliği animasyonun start/end saniyeleriyle kesişmiyor.')
    try:data=validate(item.get('data'),scene['narration'],end-start)
    except (ValueError,TypeError) as error:raise EditorError('invalid_animation',description(error)) from None
    clips=[]
    if 'background_media' in item:
        if data['background'] is not None:
            raise EditorError('invalid_animation','background_media kullanırken background=null olmalıdır; arşiv kaynağı kapatılmadı.')
        clips.append({'id':uuid4().hex,'kind':'media','track':'visuals','start':start,'end':end,
                      'media':item['background_media'],'source_start':item.get('source_start',0.),'origin':'json','source_key':source_key})
    clips.append({'id':uuid4().hex,'kind':'motion','track':item.get('track','layers'),'start':start,'end':end,
                  'motion':{'template':'documentary','data':data,'emphasis':''},'origin':'json','source_key':source_key})
    return clips
