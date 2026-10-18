"""Compile imported scene intervals onto the existing, immutable media clock."""
from copy import deepcopy
from app.editor.models import EditorError
from app.editor.transition_handles import frame_floor, issue


def upsert_slots(current, incoming):
    """Incoming records were conflict-checked against this document's revision."""
    if len({item['slot_id'] for item in incoming})!=len(incoming):
        raise EditorError('duplicate_adjustment','Aynı görüntü yuvası için birden fazla kurgu kaydı oluşturulamaz.')
    merged={item['slot_id']:deepcopy(item) for item in current}
    for item in incoming:
        merged[item['slot_id']]=deepcopy(item)
    return list(merged.values())


def import_scope(view):
    slots=sorted((s for track in view['tracks'].values() for s in track if s.get('slot_id')),key=lambda s:s['slot_id'])
    return {'stock_revision':view.get('stock_revision'),'stock_plan_id':view.get('stock_plan_id'),
        'scenes':[{k:s.get(k) for k in ('scene_id','start','end','locked')} for s in view['scenes']],
        'slots':[{**{k:s.get(k) for k in ('slot_id','scene_id','start','end','locked','clip_start','clip_end','intentional_empty')},
                  'media':{k:(s.get('media') or {}).get(k) for k in ('provider','media_id','sha256')}} for s in slots]}


def location(scene, start, end):
    return f"Sahne {scene}, {start:.3f}–{end:.3f} sn"


class SceneIntervals:
    def __init__(self, slots, document, fps=30):
        self.slots=sorted(slots,key=lambda slot:(slot['start'],slot['slot_id']))
        self.current={x['slot_id']:x for x in document['adjustments']}
        self.current_transitions={x['slot_id']:x for x in document['transitions']}
        self.fps=fps
        self.motions={}
        self.transitions={}
        self.boundary_requests={}
        self.changes=[]
        self.transition_issues=[]

    def add(self, scene, item, start, end):
        sid=scene['scene_id'];where=location(sid,start,end)
        affected=[s for s in self.slots if s['scene_id']==sid and max(start,s['start'])<min(end,s['end'])-1e-7]
        motion=item.get('motion','none')
        if motion!='none' and motion not in ('pan','slow_zoom','ken_burns','overlay','emphasis_text'):
            raise EditorError('unsupported_scene',where+': kamera hareketi desteklenmiyor.')
        if motion in ('pan','slow_zoom','ken_burns'):
            if not affected:raise EditorError('missing_slot',where+': bu aralıkta görüntü yuvası yok.')
            cursor=start
            for slot in affected:
                a,z=max(start,slot['start']),min(end,slot['end'])
                if a>cursor+1e-6:raise EditorError('missing_slot',location(sid,cursor,a)+': görüntü yuvası yok.')
                cursor=max(cursor,z)
                if slot.get('locked'):raise EditorError('locked',where+f": {slot['slot_id']} görüntü yuvası kilitli.",409)
                prop='x' if motion=='pan' else 'scale'
                old=self.current.get(slot['slot_id'],{})
                baseline=0. if prop=='x' else 1.
                if old.get('transform',{}).get(prop,baseline)!=baseline or any(k['property']==prop for k in old.get('keyframes',[])) or old.get('animation_offset') or old.get('animation_duration'):
                    raise EditorError('manual_conflict',where+f": {slot['slot_id']} yuvasında mevcut manuel {prop} / animasyon ayarı var; üzerine yazılmadı.",409)
                if z-a<1/self.fps-1e-6:raise EditorError('invalid_time',where+': kamera aralığı en az bir kare olmalıdır.')
                records=self.motions.setdefault(slot['slot_id'],[])
                # A scene proposal describes one camera operation. Even different
                # properties must not silently combine overlapping proposals.
                for previous in records:
                    if a<previous['end']-1e-7 and previous['start']<z-1e-7:
                        raise EditorError('interval_conflict',location(sid,max(a,previous['start']),min(z,previous['end']))+
                            f": {slot['slot_id']} yuvasında {previous['object']} ile {item.get('object_id','kurgu önerisi')} kamera önerileri çakışıyor.")
                records.append({'start':a,'end':z,'proposal_start':start,'proposal_end':end,
                    'property':prop,'object':item.get('object_id','kurgu önerisi')})
                self.changes.append(where+f": {slot['slot_id']} üzerinde {a:.3f}–{z:.3f} sn {motion}.")
            if cursor<end-1e-6:raise EditorError('missing_slot',location(sid,cursor,end)+': görüntü yuvası yok.')
        transition=item.get('transition','none')
        if transition=='none':return
        # end is the requested cut, never an implicit scene-end cut. Only a
        # tiny numeric tolerance is allowed; do not move an edit by a frame.
        last=next((s for s in affected if abs(s['end']-end)<=1e-6),None)
        nxt=next((s for s in self.slots if last and s['slot_id']!=last['slot_id'] and abs(s['start']-end)<=1e-6),None)
        if not last or not nxt:
            raise EditorError('unsupported_cut',location(sid,end,end)+': geçiş/kesim bitişik iki mevcut görüntü yuvasının sınırında olmalıdır. Bu noktada önce klibi bölün veya paketteki yuva sınırını kullanın.')
        if last.get('locked') or nxt.get('locked'):
            raise EditorError('locked',location(sid,end,end)+': geçişin görüntü yuvalarından biri kilitli.',409)
        kind={'hard_cut':'cut','crossfade':'cross_dissolve','fade':'dip_black'}[transition]
        previous=self.boundary_requests.get(last['slot_id'])
        if previous and previous!=kind:
            raise EditorError('transition_conflict',location(sid,end,end)+f': aynı kesimde {previous} ve {kind} geçişleri çakışıyor.')
        self.boundary_requests[last['slot_id']]=kind
        record={'slot_id':last['slot_id'],'next_slot_id':nxt['slot_id'],'kind':kind,
            'duration':frame_floor(min(.2,(last['end']-last['start'])/4,(nxt['end']-nxt['start'])/4))}
        manual=self.current_transitions.get(last['slot_id'])
        if manual:
            if manual['kind']!=kind or manual['next_slot_id']!=nxt['slot_id']:
                raise EditorError('manual_conflict',location(sid,end,end)+': mevcut manuel geçişle çakışıyor; üzerine yazılmadı.',409)
            self.changes.append(location(sid,end,end)+': istenen geçiş zaten mevcut; manuel süresi korundu.')
            return
        if last['slot_id'] in self.transitions:
            self.changes.append(location(sid,end,end)+': aynı geçiş önerileri tek kayıtta birleştirildi.')
        self.transitions[last['slot_id']]=record
        self.changes.append(location(sid,end,end)+f": {last['slot_id']} → {nxt['slot_id']} {transition}.")

    def compile(self):
        result=[]
        for slot in self.slots:
            records=self.motions.get(slot['slot_id'])
            if not records:continue
            adjustment=deepcopy(self.current.get(slot['slot_id'],{'slot_id':slot['slot_id'],'keyframes':[]}))
            duration=slot['end']-slot['start']
            for prop in sorted({r['property'] for r in records}):
                base=0. if prop=='x' else 1.
                points={0.:{'property':prop,'time':0.,'value':base,'interpolation':'hold'}}
                for r in sorted((r for r in records if r['property']==prop),key=lambda r:r['start']):
                    a=round(r['start']-slot['start'],6)
                    z=round(max(r['start'],r['end']-1/self.fps)-slot['start'],6)
                    reset=round(r['end']-slot['start'],6)
                    # Preserve progress when an interval crosses media boundaries.
                    total=r['proposal_end']-r['proposal_start']
                    low,high=(-100.,100.) if prop=='x' else (1.,1.12)
                    value=lambda t:low+(high-low)*(t-r['proposal_start'])/total
                    points[a]={'property':prop,'time':a,'value':value(r['start']),'interpolation':'hold'}
                    if z>a:points[z]={'property':prop,'time':z,'value':value(slot['start']+z),'interpolation':'linear'}
                    if reset<duration-1e-6:points[reset]={'property':prop,'time':reset,'value':base,'interpolation':'hold'}
                adjustment['keyframes']+=list(points.values())
            adjustment['keyframes'].sort(key=lambda k:(k['property'],k['time']))
            if len(adjustment['keyframes'])>128:
                raise EditorError('too_many_keyframes',f"{slot['slot_id']}: kurgu önerileri 128 keyframe sınırını aşıyor; planı daha az aralığa ayırın.")
            result.append(adjustment)
        transitions=[]
        for record in self.transitions.values():
            first=next(s for s in self.slots if s['slot_id']==record['slot_id'])
            second=next(s for s in self.slots if s['slot_id']==record['next_slot_id'])
            failure=issue(first,second,record,list(self.current.values()))
            if failure:
                self.transition_issues.append(failure)
                self.changes.append(failure['message']+' Geçiş beklemede; onaysız değiştirilmedi.')
            else:transitions.append(record)
        return result,transitions,self.changes
