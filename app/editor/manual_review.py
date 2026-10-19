"""Manual-plan boundary: strict JSON parts, loss-aware legacy mapping and review.

Independent NAMAN implementation; no ZADIAQ code or runtime dependencies.
"""
from copy import deepcopy
import json
import math
import re

from app.editor.models import EditorError
from app.providers.json_output import _unique_object, _reject_constant

SECTIONS=('sahneler','infografikler','harita_sahneleri','vurgular','katmanlar','animasyon_sahneleri','html_katmanlari')
MAX_RESPONSE_CHARS=2_000_000


def _finite_number(value):
    number=float(value)
    if not math.isfinite(number):raise ValueError('non-finite JSON number')
    return number


def parse_response(text):
    """Accept complete JSON parts, never repair syntax or recover nested objects."""
    if not isinstance(text,str) or not text.strip() or len(text)>MAX_RESPONSE_CHARS:
        raise EditorError('invalid_response','En fazla 2.000.000 karakterlik geçerli JSON cevabı yapıştırın.')
    if re.search(r'</?think(?:ing)?\s*>',text,re.I):
        raise EditorError('invalid_response','Düşünme blokları yerine yalnız JSON planını gönderin.')
    decoder=json.JSONDecoder(object_pairs_hook=_unique_object,parse_constant=_reject_constant,parse_float=_finite_number)
    parts=[]
    while text.strip():
        start=text.find('{')
        if start<0:
            if any(c in text for c in '{}[]') or '```' in text:
                raise EditorError('invalid_response','JSON parçaları veya kod blokları tamamlanmamış.')
            break
        prefix=text[:start]
        if any(c in prefix for c in '}[]'):
            raise EditorError('invalid_response','JSON kökü nesne olmalıdır.')
        fenced='```' in prefix
        if fenced and (prefix.count('```')!=1 or not re.search(r'```(?:json)?\s*$',prefix,re.I)):
            raise EditorError('invalid_response','Yalnız tamamlanmış JSON kod blokları kabul edilir.')
        try:
            part,end=decoder.raw_decode(text,start)
        except (ValueError,RecursionError):
            raise EditorError('invalid_response','JSON geçersiz. Eksik alanlar, yinelenen anahtarlar veya virgüller otomatik düzeltilmedi.') from None
        if not isinstance(part,dict):raise EditorError('invalid_response','JSON kökü nesne olmalıdır.')
        if fenced:
            closing=re.match(r'\s*```',text[end:])
            if not closing:raise EditorError('invalid_response','JSON kod bloğu kapatılmamış.')
            end+=closing.end()
        if not any(k in part for k in SECTIONS):
            raise EditorError('invalid_response','Cevapta desteklenen kurgu bölümü yok.')
        if part in parts:raise EditorError('duplicate_response','Aynı JSON parçası iki kez gönderilmiş; yinelenen parçayı kaldırın.')
        parts.append(part);text=text[end:]
        if len(parts)>30:raise EditorError('invalid_response','En fazla 30 JSON parçası gönderin.')
    if not parts:raise EditorError('invalid_response','Cevapta geçerli JSON planı bulunamadı.')
    result={key:[] for key in SECTIONS}
    for part in parts:
        for key,value in part.items():
            if key in SECTIONS:
                if not isinstance(value,list):raise EditorError('invalid_response',key+' bir liste olmalıdır.')
                result[key]+=value
            elif key in ('schema','base'):
                if key in result and result[key]!=value:
                    raise EditorError('invalid_response','JSON parçalarının şema veya temel plan bilgileri uyuşmuyor.')
                result[key]=value
            else:raise EditorError('invalid_response','Bilinmeyen üst alan: '+key)
    return result


def legacy_item(section,item,package):
    """Map exact sentence clocks only. Unsupported content is an explicit issue."""
    if not isinstance(item,dict):return item
    if 'scene_id' in item:return item
    if section=='html_katmanlari':raise EditorError('invalid_scene','HTML katmanı paketteki scene_id ve start/end ile gönderilmelidir.')
    cues=package['subtitles']['cues'];narration=package['narration']
    if 'cumleler' in item:
        numbers=item['cumleler']
    else:
        first=item.get('cumle_no',item.get('cumle_bas',item.get('no')))
        last=item.get('cumle_bit',first)
        if type(first)is not int or type(last)is not int or not 0<=first<=last<len(cues):
            raise EditorError('legacy_time','Cümle numaraları paketin sıfırdan başlayan sentence_index listesinde olmalıdır.')
        numbers=list(range(first,last+1))
    if not isinstance(numbers,list) or not numbers or any(type(n)is not int or not 0<=n<len(cues) for n in numbers) or numbers!=list(range(numbers[0],numbers[-1]+1)):
        raise EditorError('legacy_time','Cümleler sıralı, ardışık ve paketin sentence_index listesinde olmalıdır.')
    start,end=cues[numbers[0]]['start'],cues[numbers[-1]]['end']
    scene=next((s for s in narration if s['start'] is not None and s['start']<=start<end<=s['end']),None)
    if not scene:raise EditorError('legacy_time',f'{start:.3f}–{end:.3f} sn birden fazla NAMAN sahnesine taşıyor; scene_id ve start/end ile ayrı öneriler gönderin.')
    common={'scene_id':scene['scene_id'],'start':start,'end':end}
    if 'object_id' in item:common['object_id']=item['object_id']
    if section=='vurgular':
        allowed={'cumle_no','ekran','stil','ifade','ses','onem','neden','object_id'}
        if set(item)-allowed or item.get('ses') or item.get('stil','kelime')!='kelime':
            raise EditorError('legacy_effect','Vurguyu NAMAN text/effect alanlarıyla gönderin; ZADIAQ ses/kelime stilleri otomatik çevrilmez.')
        screen=item.get('ekran')
        if not isinstance(screen,list) or not screen or any(not isinstance(s,str) for s in screen):
            raise EditorError('legacy_text','ekran metin listesi olmalıdır.')
        return {**common,'text':' '.join(screen),'effect':'none'}
    if section=='infografikler':
        if set(item)-{'cumle_no','tur','buyuk','kucuk','object_id'} or item.get('tur')!='veri':
            raise EditorError('legacy_motion','İnfografiği paketteki template/data biçimiyle gönderin; grafik/stil kayıplı çevrilmez.')
        return {**common,'template':'stat','data':{'value':item.get('buyuk'),'label':item.get('kucuk','')}}
    if section=='sahneler':
        if set(item)-{'cumleler','no','dosya','kaynak_bas','vurgu','neden','object_id'} or item.get('vurgu'):
            raise EditorError('legacy_media','Bu sahne ek ZADIAQ işlemi içeriyor. Vurguyu ayrı text/effect önerisi olarak gönderin; görüntü seçimini NAMAN media/source_start alanlarıyla belirtin.')
        name=item.get('dosya')
        matches=[a for a in package.get('archive',[]) if a.get('file_name')==name and a.get('media_type') in ('image','video')]
        if not isinstance(name,str) or '/' in name or '\\' in name or len(matches)!=1:
            raise EditorError('legacy_media','Dosya adı arşivde tek bir gerçek video/görselle tam eşleşmelidir; benzer dosya seçilmedi.')
        return {**common,'media':{k:matches[0][k] for k in ('provider','media_id','sha256')},'source_start':item.get('kaynak_bas',0.)}
    raise EditorError('legacy_motion','ZADIAQ harita/katman motoru desteklenmiyor. Paketteki NAMAN template/data veya text/effect biçimiyle yeniden gönderin; öneri saklandı.')


def correction(issues):
    # Already-present items are kept as they are; asking the AI to resend them only adds noise.
    issues=[i for i in issues if i.get('category')!='duplicate']
    if not issues:return ''
    return ('NAMAN bu işlemleri uygulamadı. Geçerli öneriler taslakta korundu. '
            'Aşağıdaki işlemleri düzeltip yalnız düzeltilen önerileri output_template biçiminde gönderin. '
            'Mevcut sahne saatlerini, arşiv kimliklerini ve kilitleri koruyun; dosya, koordinat veya süre uydurmayın.\n'+
            '\n'.join(f"- {i['section']}[{i['index']}] · Sahne {i['scene_id']} · {i['start']}–{i['end']} sn: {i['message']}\n  Özgün işlem: {json.dumps(i['original'],ensure_ascii=False)}" for i in issues))


def review(editorial,pid,payload,*,persist=True,progress=None):
    """Compile isolated operations through the authoritative editor validator.

    Invalid records remain in the draft report, never in the render document.
    Every cumulative candidate is validated, so cross-record conflicts survive.
    """
    try:json.dumps(payload,allow_nan=False)
    except (ValueError,TypeError,RecursionError):
        raise EditorError('invalid_response','JSON yalnız sonlu sayılar ve geçerli veri içermelidir.') from None
    with editorial.projects.lock:
        if progress:progress(0,0,'Proje ve kaynak bilgileri okunuyor')
        package=editorial.editor.task_package(pid)
        if not isinstance(payload,dict) or set(payload)-{'schema','base',*SECTIONS}:
            raise EditorError('invalid_response','Plan kökü ve bölüm adları çıktı şablonuyla eşleşmelidir.')
        legacy='schema' not in payload and 'base' not in payload
        if not legacy and (payload.get('schema')!=package['schema'] or payload.get('base')!=package['base']):
            raise EditorError('stale_plan','Temel plan veya şema değişmiş. Güncel paketi alın.',409)
        if any(not isinstance(payload.get(s,[]),list) for s in SECTIONS):
            raise EditorError('invalid_response','Kurgu bölümleri liste olmalıdır.')
        if legacy and any(isinstance(x,dict) and 'scene_id' in x for s in SECTIONS for x in payload.get(s,[])):
            raise EditorError('missing_base','NAMAN önerileri schema ve base içermelidir. Güncel çıktı şablonunu kullanın.')
        if sum(len(payload.get(s,[])) for s in SECTIONS)>500:
            raise EditorError('too_many_operations','Tek taslakta en fazla 500 işlem doğrulanabilir.')
        accepted=deepcopy(package['output_template']);issues=[];scenes={s['scene_id']:s for s in package['narration']}
        total=sum(len(payload.get(s,[])) for s in SECTIONS)
        def finish(draft,accepted):
            draft.update(import_issues=issues,correction_message=correction(issues),original_response=deepcopy(payload),
                         accepted_response=accepted,legacy_converted=legacy)
            if persist:
                from contextlib import closing
                from app.projects import now
                with closing(editorial.projects._connection()) as c,c:
                    c.execute('INSERT INTO editorial_events(project_id,plan_id,kind,payload_json,created_at) VALUES (?,?,?,?,?)',(pid,draft['plan_id'],'draft',json.dumps(draft),now()))
            if progress:progress(total,total,'Taslak hazır; henüz kurguya uygulanmadı')
            return draft
        # Valid plans need one authoritative cumulative validation, not N full
        # recompilations of ever larger prefixes. Fall back to loss-aware review
        # only when the batch has an invalid/conflicting operation.
        if progress:progress(0,total,'Plan topluca doğrulanıyor')
        batch=deepcopy(accepted)
        try:
            for section in SECTIONS:
                batch[section]=[legacy_item(section,item,package) for item in payload.get(section,[])]
                if any(not isinstance(item,dict) or not isinstance(item.get('scene_id'),str) for item in batch[section]):
                    raise EditorError('invalid_scene','İşlem geçerli bir scene_id metni içermelidir.')
            complete=editorial._import_draft(pid,batch,persist=False)
        except EditorError:pass
        else:return finish(complete,batch)
        processed=0
        def failed(section,index,item,error,converted=None):
            source=converted if isinstance(converted,dict) else item if isinstance(item,dict) else {}
            if 'scene_id' not in source:
                numbers=source.get('cumleler',[source.get('cumle_no',source.get('cumle_bas',source.get('no')))])
                cues=package['subtitles']['cues']
                if isinstance(numbers,list) and numbers and all(type(n)is int and 0<=n<len(cues) for n in numbers):
                    last=source.get('cumle_bit',numbers[-1])
                    if type(last)is int and 0<=last<len(cues):
                        a,z=cues[numbers[0]]['start'],cues[last]['end']
                        located=next((s for s in scenes.values() if s['start'] is not None and s['start']<=a<z<=s['end']),{})
                        source={**source,'scene_id':located.get('scene_id','birden fazla sahne'),'start':a,'end':z}
            scene=scenes.get(source.get('scene_id'),{}) if isinstance(source.get('scene_id'),str) else {}
            message=str(error)
            if scene and error.category=='invalid_time':
                message+=f" Geçerli sahne aralığı: {scene['start']}–{scene['end']} sn."
            if error.category=='short_source':
                # The validator reports the probed duration. Old archive metadata
                # may be the longer container/audio duration; do not contradict
                # the verified error by presenting that value as source length.
                message+=f" Önerilen kaynak başlangıcı: {source.get('source_start',0)} sn. Kaynak başlangıcını veya önerinin end saniyesini azaltıp yeniden doğrulayın."

            issues.append({'section':section,'index':index,'scene_id':source.get('scene_id','cümle '+str(source.get('cumle_no',source.get('cumleler','?')))),
                'start':source.get('start',scene.get('start','?')),'end':source.get('end',scene.get('end','?')),
                'category':error.category,'message':message,'original':deepcopy(item),'status':'pending',
                'options':['İşlemi düzenleyip yeniden doğrula','Düzeltme mesajını dış yapay zekâya gönder','Bu işlemi uygulamadan geçerli önerileri onayla']})
        for section in SECTIONS:
            for index,original in enumerate(payload.get(section,[])):
                if progress:progress(processed,total,'Hatalı öneriler ayrılıyor; geçerli öneriler korunuyor')
                item=original
                try:
                    item=legacy_item(section,original,package)
                    if not isinstance(item,dict) or not isinstance(item.get('scene_id'),str):
                        raise EditorError('invalid_scene','İşlem geçerli bir scene_id metni içermelidir.')
                    candidate=deepcopy(accepted);candidate[section].append(item)
                    editorial._import_draft(pid,candidate,persist=False)
                except EditorError as error:
                    retained=False
                    # A bad cut must not discard the valid camera/text portion
                    # of the same proposal. The rejected transition remains
                    # explicit in the report with the full original operation.
                    if section=='sahneler' and isinstance(item,dict) and item.get('transition','none')!='none' and (item.get('motion','none')!='none' or item.get('overlay_text')):
                        without_transition={**item,'transition':'none'}
                        partial=deepcopy(accepted);partial[section].append(without_transition)
                        try:editorial._import_draft(pid,partial,persist=False)
                        except EditorError:pass
                        else:accepted=partial;retained=True
                    failed(section,index,original,error,item)
                    if retained:
                        issues[-1]['retained_fields']=[k for k in item if k not in ('transition','scene_id','start','end','object_id')]
                        issues[-1]['message']+=' Kamera/yazı/görüntü bölümü taslakta korundu. Yalnız geçişi düzeltin: ayrı öneride motion=none kullanın; overlay_text/media eklemeyin.'
                else:accepted=candidate
                processed+=1
        draft=editorial._import_draft(pid,accepted,persist=False)
        return finish(draft,accepted)


def prepare_html_layers(editorial,pid,payload,progress=None):
    """Render incoming HTML/CSS layers once (Remotion) before the review compiles
    the draft. Not under the project lock: a slow browser render must not block
    the editor. Failures stay per layer and appear as draft issues."""
    if not isinstance(payload,dict):return 0
    from app.motion.html_layer import prerender,MAX_SECONDS
    from app.rendering.tools import discover
    editor=editorial.editor
    bridge=getattr(getattr(editor,'rendering',None),'openmontage',None)
    # Plain-text proposals look like subtitles. When Remotion is ready they become designed,
    # animated layers; otherwise they stay ordinary text clips, so nothing is lost.
    try:ready=bridge is not None and bool(bridge.status().get('ready'))
    except Exception:ready=False
    if ready and any(isinstance(payload.get(k),list) and payload[k] for k in ('vurgular','katmanlar')):
        from app.motion.text_layers import convert
        known={s['scene_id']:s for s in editor.view(pid)['scenes']}
        try:language=editor.projects.get(pid).get('language') or 'en'
        except Exception:language='en'
        convert(payload,known,MAX_SECONDS,language)
    items=payload.get('html_katmanlari')
    if not isinstance(items,list) or not items:return 0
    scenes={s['scene_id']:s for s in editor.view(pid)['scenes']}
    report=(lambda done,total,message:progress(done,total,message)) if progress else (lambda *a:None)
    return prerender(bridge,editor.projects._path(pid)/'stock',items,scenes,discover().get('ffmpeg'),progress=report)


def review_validation(editorial,pid,payload):
    """Read-only preflight uses exactly the same compiler as pasted/file import."""
    try:
        draft=review(editorial,pid,payload,persist=False)
        issues=draft['import_issues'];transitions=draft.get('transition_issues',[])
        return {'valid':not issues,'errors':[i['message'] for i in issues],
                'correction_message':draft['correction_message'],'import_issues':issues,
                'changes':draft['changes'],'transition_issues':transitions,
                'requires_transition_resolution':any(i['status']=='pending' for i in transitions),
                'base_plan_id':draft['plan_id'],'base_revision':payload.get('base',{}).get('revision')}
    except EditorError as error:
        return {'valid':False,'errors':[str(error)],'correction_message':str(error),'changes':[]}
