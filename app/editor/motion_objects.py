"""Edits address generated scene indices, never guessed layers in flat MP4s."""
from copy import deepcopy
from app.editor.models import EditorError


def validate_edits(scene,edits):
    duration=scene['duration']
    for edit in edits:
        if edit['index']>=len(scene['elements']):raise ValueError('Motion nesnesi artık bu şablonda yok; nesneleri yeniden açın.')
        kind=scene['elements'][edit['index']]['type']
        if edit['start']>=duration or (edit['end'] is not None and edit['end']>duration+.001) or any(k['time']>duration for k in edit['keyframes']):raise ValueError('Nesne zamanı animasyon kaynağını aşıyor.')
        if kind in ('map','relief') and (edit['x'] or edit['y'] or edit['opacity']!=1 or edit['color'] or edit['text'] is not None or edit['keyframes']):raise ValueError('Harita arka planında yalnız göster/gizle ve zaman aralığı desteklenir; konum ana klipten düzenlenir.')
        if edit['text'] is not None and kind=='counter':
            from app.motion.templates import NUMBER
            if not NUMBER.search(edit['text']):raise ValueError('Sayı nesnesi sayısal değer içermelidir.')
        if edit['text'] is not None and kind not in ('text','counter'):raise ValueError('Bu nesne metin içermiyor.')


def scene_for(advanced,pid,cid):
    from app.channels import DEFAULT_STYLE
    from app.motion.templates import build
    from app.motion.places import offline
    state=advanced.get(pid);clip=next((c for c in state['document']['clips'] if c['id']==cid),None)
    if not clip or clip['kind']!='motion':raise EditorError('flat_source','Bu düz MP4/görselin içine işlenmiş yazılar ayrı katman olarak düzenlenemez.')
    with offline():scene=build({**clip['motion'],'local_only':True,'clean_source':clip.get('clean_map',False)},DEFAULT_STYLE,clip.get('animation_duration') or clip['end']-clip['start'],0,advanced.projects.get(pid)['language'])
    return {'source_type':'editable_naman','revision':state['revision'],'duration':scene['duration'],
            'elements':[{'index':i,'type':e['type'],'label':str(e['props'].get('text') or e['props'].get('target') or e['type'])[:160],
                         'controls':['visibility','time'] if e['type'] in ('map','relief') else ['visibility','time','x','y','opacity','color','keyframes']+(['text'] if e['type'] in ('text','counter') else [])} for i,e in enumerate(scene['elements'])]}


def properties(scene,index,p,t):
    edit=next((e for e in scene.get('_editor_elements',[]) if e['index']==index),None)
    if not edit:return p
    if not edit['visible'] or t<edit['start'] or edit['end'] is not None and t>=edit['end']:return None
    from app.editor.compositor import value_at
    offset={'transform':edit,'keyframes':edit['keyframes']}
    p=deepcopy(p);dx=value_at(offset,'x',t);dy=value_at(offset,'y',t)
    for name in ('x','x1','x2','cx'):
        if name in p:p[name]+=dx
    for name in ('y','y1','y2','cy'):
        if name in p:p[name]+=dy
    p['opacity']=p.get('opacity',1)*value_at(offset,'opacity',t)
    if edit['color']:
        for name in ('fill','stroke'):
            if p.get(name):p[name]=edit['color']
    if edit['text'] is not None:p['target' if 'target' in p else 'text']=edit['text']
    return p
