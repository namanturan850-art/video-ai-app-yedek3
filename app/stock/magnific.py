"""Opt-in Magnific stock video discovery. Never invokes generative endpoints."""
import httpx
from app.stock.models import normalized_media, StockError

API = 'https://api.magnific.com'
class MagnificStockProvider:
    name = 'magnific'
    def __init__(self, key, *, transport=None):
        self.key, self.transport = key, transport
        self.last_diagnostic = None

    def search(self, query, media_type, *, page=1):
        if media_type != 'video': return []
        if not isinstance(page, int) or not 1 <= page <= 3: raise StockError('invalid_query','Arama sayfası geçersiz.')
        if not self.key: raise StockError('missing_key','Magnific API anahtarı ayarlanmadı.')
        try:
            with httpx.Client(base_url=API, timeout=20, follow_redirects=False, transport=self.transport) as client:
                r=client.get('/v1/videos',params={'term':query[:100],'page':page,'order':'relevance'},headers={'x-magnific-api-key':self.key})
            if r.status_code in (401,403): raise StockError('key_rejected','Magnific hesabının API erişimi doğrulanamadı.')
            if r.status_code == 429: raise StockError('rate_limit','Magnific API kullanım sınırına ulaşıldı.')
            if r.status_code != 200: raise StockError('upstream_error','Magnific araması tamamlanamadı.')
            body=r.json(); listing=body.get('data',[]) if isinstance(body,dict) else []
            if isinstance(listing,dict): listing=listing.get('data',listing.get('items',listing.get('videos',[])))
            if not isinstance(listing,list): raise ValueError()
            out=[]
            for item in listing[:40]:
                try:
                    if not isinstance(item,dict) or item.get('is_ai_generated'): continue
                    ident=str(item['id']); duration=float(item['duration'])
                    opts=item.get('options') or [];opts=opts if isinstance(opts,list) else list(opts.values()) if isinstance(opts,dict) else []
                    best=next((o for o in opts if isinstance(o,dict) and int(o.get('width') or 0)>=1280 and int(o.get('height') or 0)>=720),None)
                    best=best or (opts[0] if opts else {})
                    width=int(item.get('width') or best.get('width') or 0);height=int(item.get('height') or best.get('height') or 0)
                    previews=item.get('previews') or []; previews=previews if isinstance(previews,list) else list(previews.values()) if isinstance(previews,dict) else []
                    thumbs=item.get('thumbnails') or [];thumbs=thumbs if isinstance(thumbs,list) else list(thumbs.values()) if isinstance(thumbs,dict) else []
                    def url(items):
                        for x in items:
                            u=x if isinstance(x,str) else x.get('url') if isinstance(x,dict) else None
                            if isinstance(u,str) and u.startswith('https://'):return u
                        return ''
                    tags=item.get('tags') or []
                    desc=' '.join(str(t.get('name','') if isinstance(t,dict) else t) for t in tags) if isinstance(tags,list) else str(tags)
                    out.append(normalized_media({'provider':'magnific','media_id':ident,'media_type':'video',
                        'source_url':'','page_url':'','creator_name':'Magnific / Freepik','creator_url':'',
                        'width':width,'height':height,'duration':duration,'preview_url':url(thumbs),
                        'download_url':'','query_used':query,'provider_query':query,
                        'description':(str(item.get('name') or '')+' '+desc)[:1000],
                        'source_metadata':{'stock_api_id':ident,'preview_video_url':url(previews),'premium':bool(item.get('premium'))}}))
                except (KeyError,TypeError,ValueError,StockError): continue
            return out
        except StockError:raise
        except (httpx.HTTPError,ValueError,TypeError,KeyError):
            raise StockError('invalid_response','Magnific stok araması şu anda kullanılamıyor.') from None
