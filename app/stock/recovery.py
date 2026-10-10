"""Bounded progressive recovery. Counts are evidence, never guessed live causes."""
from collections import Counter
from contextlib import closing
import hashlib
import json
import subprocess

from app.stock import relevance
from app.stock.identities import identity_keys
from app.stock.models import StockError,rejection_reason
from app.stock.download import asset_path
from app.scripts.models import ScriptError

LABELS={
 'no_provider_results':'Sağlayıcı sonuç döndürmedi.',
 'all_candidates_irrelevant':'Adaylar sahnenin konusuyla uyumlu değil.',
 'all_candidates_duplicates':'Uygun adaylar başka alanlarda kullanılıyor.',
 'portrait_or_resolution_rejected':'Dikey/kare veya düşük çözünürlüklü adaylar elendi.',
 'download_failed':'Dosya indirilemedi veya doğrulanamadı.',
 'source_too_short':'Gerçek kaynak süresi bu aralık için yetersiz; otomatik tekrar yapılmadı.',
 'provider_rate_limited':'Sağlayıcı kullanım sınırı; daha sonra deneyin.',
 'provider_unreachable':'Sağlayıcı bağlantısı/yanıtı doğrulanamadı; interneti kontrol edip sonra deneyin.',
 'provider_key_rejected':'Sağlayıcı anahtarı kabul edilmedi; Ayarlar bölümünü kontrol edin.',
 'query_exhausted':'Mevcut konu sorguları ve sayfalar tüketildi; aynı arama tekrar edilmeyecek.',
 'no_visual_match':'Yerel kare analizi görsel özneyi doğrulamadı.',
 'locked_or_stale_selection':'Kilitli, eksik veya güncel olmayan seçim; elle kontrol gerekli.',
 'search_budget_reached':'Bu geçişin güvenli arama sınırına ulaşıldı; sonraki geçiş yeni kanıtları dener.',
 'semantic_unavailable':'Görsel analiz hazır değil; yalnız metadata/elle inceleme kullanıldı.'}


def decode(tool,path):
    """A bounded actual frame decode prevents unsupported media becoming ready."""
    try:
        result=subprocess.run([tool['ffmpeg'],'-v','error','-i',str(path),'-map','0:v:0','-frames:v','1','-f','null','-'],
            shell=False,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        if result.returncode:raise ValueError()
    except (OSError,KeyError,TypeError,ValueError,subprocess.SubprocessError):
        raise StockError('download_failed','Yerel medya çözümlenemedi; mevcut dosya korundu.') from None


def valid(service,pid,slot):
    if slot.get('status')!='complete' or not slot.get('selected_media'):return False
    if slot.get('local_validation',{}).get('error') or slot.get('visual_check',{}).get('verdict')=='mismatch':return False
    try:
        m=slot['selected_media'];path=asset_path(service.projects,pid,m)
        if m.get('sha256'):
            with path.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=m['sha256']:return False
        return True
    except (StockError,OSError):return False


def queries(profile):
    result=list(relevance.queries_for(profile));seen={q for _,q in result}
    anchor=profile['subject_anchor']
    # Only existing scene concepts are combined; never fabricate locations/facts.
    for suffix in [profile['visual_goal'],profile.get('search_context',''),*profile['context_tokens']]:
        q=relevance.provider_query((anchor+' '+suffix).strip(),anchor)
        if q and q not in seen and (not anchor or relevance.canonical(q)&set(profile['anchor_tokens'])):
            result.append((2,q));seen.add(q)
        if len(result)>=10:break
    return result[:10]


def search(service,pid,slot,used,progress,job):
    scene=next(s for s in service._handoff(pid)['scenes'] if s['scene_id']==slot['scene_id'])
    profile=relevance.profile(scene,slot);slot['relevance_profile']=profile
    attempts=slot.setdefault('recovery_attempts',{})
    reasons=set(slot.get('missing_reasons',[])) - {'search_budget_reached'};candidates=list(slot.get('candidates',[]))
    bridge=getattr(service,'openmontage',None)
    names=[n for n in ('pexels','pixabay') if service.settings.stock_config(n).get('api_key')]
    if bridge and bridge.config().get('media_search'):names.append('openmontage')
    work=[(kind,tier,q,n,page) for kind in ('video','image') for page in range(1,4)
          for tier,q in queries(profile) for n in names if not (n=='openmontage' and (page>1 or kind!='video'))]
    # Earlier Part 9.7 evidence is page one, not permission to rerun it endlessly.
    for d in slot.get('search_diagnostics',[]):
        key=json.dumps([d['provider'],d['media_type'],d['query'],1],ensure_ascii=False)
        if d.get('category') in ('none','success'):attempts.setdefault(key,{'category':'none','count':d.get('normalized_count',0)})
    if not names:reasons.add('no_provider_results')
    calls=0
    for kind,tier,q,name,page in work:
        key=json.dumps([name,kind,q[:100] if name=='pixabay' else q,page],ensure_ascii=False)
        if key in attempts:continue
        if calls>=8 or progress.get('recovery_calls',0)>=48:
            reasons.add('search_budget_reached');break
        if name in progress.setdefault('limited_providers',[]):continue
        calls+=1;progress['recovery_calls']=progress.get('recovery_calls',0)+1
        progress['message']=f'Yeni konu araması · {name.title()} · sayfa {page}'
        service._checkpoint(job,progress)
        try:
            results,counts,cached=service._cache_search(pid,name,kind,q,page=page)
            attempts[key]={'category':'none','count':len(results)}
        except StockError as error:
            category='provider_rate_limited' if error.category=='rate_limit' else 'provider_key_rejected' if error.category in ('key_rejected','missing_key') else 'provider_unreachable'
            reasons.add(category)
            # One unavailable/rejected provider should not consume the whole
            # pass repeating the same network failure under different queries.
            progress['limited_providers'].append(name)
            # An unavailable network/key is not evidence of an empty result;
            # keep this operation retryable after the underlying issue is fixed.
            service._checkpoint(job,progress,slot=slot);continue
        if not results:reasons.add('no_provider_results')
        eligible=[];rejected={r:0 for r in ('resolution','duration','relevance','orientation')}
        for m in results:
            reason=rejection_reason(m,slot,technical_only=True)
            if reason:
                rejected[reason]+=1
                if reason in ('orientation','resolution'):reasons.add('portrait_or_resolution_rejected')
                continue
            m=relevance.annotate(m,profile,tier,q)
            can_check=bool(bridge and bridge.config().get('visual_analysis') and bridge.status().get('semantic_ready'))
            if not relevance.acceptable(m,profile) and not can_check:reasons.add('all_candidates_irrelevant');rejected['relevance']+=1;continue
            if identity_keys(m)&used:reasons.add('all_candidates_duplicates');continue
            eligible.append(m)
        service._record_diagnostic(name,kind,q,counts,eligible,used,rejected,cached,'none',slot,progress)
        # Real downloaded bytes are analysed locally, never provider thumbnails.
        if eligible and bridge and bridge.config().get('visual_analysis'):
            from app.integrations.openmontage.visual import analyse_many
            downloaded=[]
            for m in sorted(eligible,key=lambda m:relevance.rank(m,slot),reverse=True)[:4]:
                try:
                    if progress.get('recovery_downloads',0)>=16:
                        reasons.add('search_budget_reached');break
                    progress['recovery_downloads']=progress.get('recovery_downloads',0)+1
                    saved=service.downloader.download(pid,m)
                    if identity_keys(saved)&used:reasons.add('all_candidates_duplicates');continue
                    downloaded.append(saved)
                except StockError as error:
                    reasons.add('semantic_unavailable' if error.category=='semantic_unavailable' else 'download_failed')
                    # Explicit analysis failure is never fabricated confirmation.
            try:
                eligible=analyse_many(bridge,pid,downloaded,profile) if downloaded else []
                if any(m['source_metadata'].get('visual_analysis',{}).get('verdict')=='mismatch' for m in eligible):reasons.add('no_visual_match')
            except StockError:
                reasons.add('semantic_unavailable');eligible=[]
        candidates.extend(eligible)
        unique={(m['provider'],m['media_type'],m['media_id']):m for m in candidates}
        candidates=list(unique.values())[-80:]
        slot['candidates']=candidates;slot['missing_reasons']=sorted(reasons)
        service._checkpoint(job,progress,slot=slot)
        if relevance.choose(candidates,used,slot):return relevance.ordered(candidates,used,slot),[]
    if all(json.dumps([n,k,q[:100] if n=='pixabay' else q,p],ensure_ascii=False) in attempts for k,_,q,n,p in work):reasons.add('query_exhausted')
    slot['missing_reasons']=sorted(reasons);service._checkpoint(job,progress,slot=slot)
    return relevance.ordered(candidates,used,slot),[]


def report(slots):
    missing=[s for s in slots if s.get('status')!='complete' or not s.get('selected_media')]
    counts=Counter(r for s in missing for r in s.get('missing_reasons',[]))
    return {'raw_stock_slots':len(slots),'selected_stock_assets':len(slots)-len(missing),
            'unresolved_raw_slots':len(missing),'reasons':[{'code':r,'count':n,'message':LABELS[r]} for r,n in sorted(counts.items()) if r in LABELS]}


def evidence(slot):
    reasons=set(slot.get('missing_reasons',[]))
    for d in slot.get('search_diagnostics',[]):
        if d.get('normalized_count')==0 and d.get('category') in ('none','success'):reasons.add('no_provider_results')
        if d.get('category')=='rate_limit':reasons.add('provider_rate_limited')
        if d.get('accepted_count',0)>0 and d.get('available_count')==0:reasons.add('all_candidates_duplicates')
        rejected=d.get('rejected',{})
        if rejected.get('relevance'):reasons.add('all_candidates_irrelevant')
        if rejected.get('orientation') or rejected.get('resolution'):reasons.add('portrait_or_resolution_rejected')
    if slot.get('locked'):reasons.add('locked_or_stale_selection')
    return sorted(reasons)


def run(service,job):
    from copy import deepcopy
    from app.rendering import reflow
    pid=job['project_id'];progress=job['progress']
    with service.projects.lock,closing(service.projects._connection()) as c:
        state=service._load(c,pid,job['plan_id'])
    slots=deepcopy(state['slots'])
    from app.rendering.tools import discover
    from app.rendering.probe import stock as probe_stock
    tool=discover();proofs={}
    durations={s['slot_id']:s['duration'] for s in service.timing_handoff(pid).get('stock_slots',[])}
    for s in slots:
        if not valid(service,pid,s):continue
        m=s['selected_media']
        try:
            if not tool.get('ffprobe'):raise StockError('tool_missing','Yerel medya doğrulaması için ffprobe gerekli.')
            path=asset_path(service.projects,pid,m)
            digest=m.get('sha256')
            if not digest:
                with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
            if digest not in proofs:
                actual=probe_stock(tool['ffprobe'],path,m['media_type'])
                decode(tool,path)
                stream=next(x for x in actual['streams'] if x.get('codec_type')=='video')
                proofs[digest]={'sha256':digest,'duration':actual.get('stock_duration'),
                               'width':stream['width'],'height':stream['height'],'media_type':m['media_type']}
            s['local_validation']=proofs[digest]
            if not s['locked'] and m['media_type']=='video' and (s['local_validation']['width']<=s['local_validation']['height'] or s['local_validation']['width']<1280 or s['local_validation']['height']<720):
                s.update(status='pending',missing_reasons=['portrait_or_resolution_rejected'])
            if not s['locked'] and m['media_type']=='video' and s['local_validation']['duration']+1/30<durations.get(s['slot_id'],s['duration']):
                s.update(status='pending',missing_reasons=['source_too_short'])
        except (ScriptError,OSError,KeyError,StopIteration):
            s['local_validation']={'error':True};s['missing_reasons']=['download_failed']
            if not s['locked']:s['status']='pending'
        # Validation proof is separate metadata; selected asset and lock remain.
        with service.projects.lock,closing(service.projects._connection()) as c,c:
            current=service._load(c,pid,job['plan_id']);target=service._slot(current,s['slot_id'])
            target.update(local_validation=s['local_validation'])
            if not s['locked']:target.update(status=s['status'],missing_reasons=s.get('missing_reasons',[]))
            service._save(c,current)
    bridge=getattr(service,'openmontage',None)
    if bridge and bridge.config().get('visual_analysis'):
        from app.integrations.openmontage.visual import analyse_many
        for scene in service._handoff(pid)['scenes']:
            group=[s for s in slots if s['scene_id']==scene['scene_id'] and valid(service,pid,s)]
            for start in range(0,len(group),4):
                batch=group[start:start+4]
                try:
                    checked=analyse_many(bridge,pid,[s['selected_media'] for s in batch],relevance.profile(scene,batch[0]))
                    for s,m in zip(batch,checked):
                        s['visual_check']=m['source_metadata'].get('visual_analysis',{})
                        if s['visual_check'].get('verdict')=='mismatch' and not s['locked']:
                            s.update(status='pending',missing_reasons=['no_visual_match'])
                        if not s['locked']:service._checkpoint(job,progress,slot=s)
                except StockError:
                    for s in batch:
                        if not s['locked']:s['visual_check']={'verdict':'error'};service._checkpoint(job,progress,slot=s)
    used=set().union(*(identity_keys(s['selected_media']) for s in slots if valid(service,pid,s)))
    for index,slot in enumerate(slots):
        if service.closed:raise StockError('interrupted','İşlem durdu; mevcut dosyalar korundu.')
        progress['percent']=int(index/max(1,len(slots))*90)
        if valid(service,pid,slot):continue
        if slot['locked']:
            slot['missing_reasons']=['locked_or_stale_selection'];continue
        if slot['slot_id'] in progress['completed']:continue
        progress.update(slot_id=slot['slot_id'],message='Eksik medya güvenli biçimde inceleniyor.')
        try:
            candidates,_=search(service,pid,slot,used,progress,job)
            chosen=relevance.choose(candidates,used,slot)
            if chosen:
                if not chosen.get('local_path'):
                    if progress.get('recovery_downloads',0)>=16:raise StockError('search_budget_reached',LABELS['search_budget_reached'])
                    progress['recovery_downloads']=progress.get('recovery_downloads',0)+1
                chosen=service.downloader.download(pid,chosen)
                if identity_keys(chosen)&used:slot.setdefault('missing_reasons',[]).append('all_candidates_duplicates')
                else:
                    slot.update(selected_media=chosen,status='complete',message='Yeni benzersiz ilgili medya bulundu.',missing_reasons=[])
                    # New source will be probed before effective coverage activation.
                    slot['local_validation']={}
                    slot['visual_check']=chosen.get('source_metadata',{}).get('visual_analysis',{})
                    used.update(identity_keys(chosen))
            if not valid(service,pid,slot):slot.update(status='ai_needed',message='Arama kanıtı kaydedildi; zaman çizelgesi güvenli biçimde toparlanacak.')
        except StockError as error:
            slot.setdefault('missing_reasons',[]).append('provider_rate_limited' if error.category=='rate_limit' else 'search_budget_reached' if error.category=='search_budget_reached' else 'download_failed')
            slot['message']='Bu alan tamamlanamadı; mevcut dosyalar korundu.'
        service._checkpoint(job,progress,slot=slot)
        progress['completed'].append(slot['slot_id']);service._checkpoint(job,progress)
    with service.projects.lock,closing(service.projects._connection()) as c,c:
        state=service._load(c,pid,job['plan_id'])
        for s in state['slots']:
            original=next(x for x in slots if x['slot_id']==s['slot_id'])
            if s['locked'] and original.get('visual_check'):s['visual_check']=original['visual_check']
            if s.get('selected_media') and s.get('status')=='complete' and not s.get('local_validation'):
                try:
                    m=s['selected_media'];path=asset_path(service.projects,pid,m);actual=probe_stock(tool.get('ffprobe'),path,m['media_type'])
                    decode(tool,path)
                    stream=next(x for x in actual['streams'] if x.get('codec_type')=='video')
                    s['local_validation']={'sha256':m['sha256'],'duration':actual.get('stock_duration'),'width':stream['width'],'height':stream['height'],'media_type':m['media_type']}
                    if not s['locked'] and m['media_type']=='video' and s['local_validation']['duration']+1/30<durations.get(s['slot_id'],s['duration']):
                        s.update(status='ai_needed',missing_reasons=['source_too_short'])
                except (ScriptError,OSError,KeyError,StopIteration,TypeError):s['local_validation']={'error':True};s['missing_reasons']=['download_failed']
        for s in state['slots']:
            if s['locked'] and not valid(service,pid,s):s['missing_reasons']=['locked_or_stale_selection']
        h=service.timing_handoff(pid);p=service._handoff(pid)
        coverage=reflow.save(service,pid,state,h,p)
        state['recovery_report']={**report(state['slots']),**coverage}
        service._save(c,state);service._mirror(state)
    progress.update(percent=100,category='none',recovery_report=state['recovery_report'],
        message='Akıllı kurgu tamamlandı. Render ekranında motor hazırlığını kontrol edin.' if coverage['render_ready'] else 'Güvenli toparlama tamamlandı; kalan eksik süreyi ve nedenleri kontrol edin.')
    service._checkpoint(job,progress,status='completed')
