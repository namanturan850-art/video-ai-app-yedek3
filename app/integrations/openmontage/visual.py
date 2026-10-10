"""Safe local semantic cache over real downloaded assets. No model download."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import shutil
from app.stock.download import asset_path,directory
from app.stock.models import StockError
from app.stock import relevance
from app.rendering.models import RenderError


def descriptor(profile):
    return profile.get('semantic_descriptor') or relevance.provider_query(profile['subject_anchor']+' '+profile['visual_goal'],profile['subject_anchor'])[:300]


def analyse(bridge,pid,media,profile):
    return analyse_many(bridge,pid,[media],profile)[0]


def analyse_many(bridge,pid,media_items,profile):
    """At most four candidates share one offline model load and frame batch."""
    if not 1<=len(media_items)<=4:raise StockError('input_invalid','Görsel analiz grubu en fazla dört dosya içerebilir.')
    status=bridge.status()
    if not status.get('semantic_ready'):
        # Honest metadata/manual degradation; never claim frames were inspected.
        result=deepcopy(media_items)
        for m in result:m.setdefault('source_metadata',{})['visual_analysis']={'verdict':'not_available','message':'Kurulum gerekli; metadata/elle kontrol.'}
        return result
    desc=descriptor(profile)
    version=status.get('semantic_model_version','unknown')
    try:
        pending=[];checks={};caches={}
        for media in media_items:
            path=asset_path(bridge.projects,pid,media)
            key=hashlib.sha256((media['sha256']+desc+version).encode()).hexdigest()
            cache=directory(bridge.projects,pid)/('visual-'+key+'.json')
            if cache.is_symlink():raise StockError('unsafe_path','Görsel analiz önbelleği güvenli değil.')
            caches[media['sha256']]=cache
            if cache.exists():checks[media['sha256']]=json.loads(cache.read_text(encoding='utf-8'))
            elif not any(c['sha256']==media['sha256'] for c in pending):
                pending.append({'path':str(path),'sha256':media['sha256'],'media_type':media['media_type'],'duration':media.get('duration')})
        if pending:
            work=directory(bridge.projects,pid)/('.visual-'+uuid4().hex);work.mkdir()
            try:
                results=bridge.call('visual',{'descriptor':desc,'candidates':pending},work)['results']
                if len(results)!=len(pending):raise ValueError()
                for item,checked in zip(pending,results):
                    if checked.get('sha256')!=item['sha256'] or checked.get('verdict') not in ('match','mismatch','uncertain'):raise ValueError()
                    bridge.settings_guard(checked);checks[item['sha256']]=checked
                    try:
                        with caches[item['sha256']].open('x',encoding='utf-8') as f:json.dump(checked,f)
                    except FileExistsError:pass  # Another bounded job saved the same immutable check.
            finally:shutil.rmtree(work)
        output=[]
        for media in media_items:
            checked=checks[media['sha256']]
            if checked.get('sha256')!=media['sha256'] or checked.get('verdict') not in ('match','mismatch','uncertain'):raise ValueError()
            m=deepcopy(media);m.setdefault('source_metadata',{})['visual_analysis']=checked
            if m['source_metadata'].get('footage_role') not in ('direct_factual','contextual_broll','illustrative'):
                m['source_metadata']['footage_role']='contextual_broll'
            output.append(relevance.annotate(m,profile,m.get('search_tier') or 1,m['query_used']))
        if getattr(bridge,'semantic_error',False):
            bridge.semantic_error=False;bridge.cache=None
        return output
    except (RenderError,OSError,ValueError,KeyError,IndexError,TypeError):
        bridge.semantic_error=True
        bridge.cache=None
        raise StockError('semantic_unavailable','Yerel görsel analiz tamamlanamadı; görüntü doğrulandı olarak işaretlenmedi. Ayarlar → OpenMontage bölümünü kontrol edin.') from None
