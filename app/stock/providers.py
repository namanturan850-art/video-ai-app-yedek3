"""Official contracts verified 2026-10-08; sources in docs/STOCK_MEDIA.md."""
import logging
import re
import time
from urllib.parse import quote, unquote, urlsplit

import httpx
from pydantic import SecretStr

from app.scripts.engine import SecretGuard
from app.stock.models import StockError, normalized_media
from app.stock.download import safe_url

LOG = logging.getLogger('uvicorn.error.stock')
PRIVATE_KEYS = set()


class PrivateHTTPFilter(logging.Filter):
    """httpx logs full URLs, which would expose Pixabay's query-string key.

    Stock requests opt into an extension; httpx records use positional request URL.
    Suppress HTTP client debug/request logs containing either stock API/CDN, without
    changing logs of Gemini, Ollama or OpenAI. Our diagnostic log is metadata-only.
    """
    def filter(self, record):
        text = record.getMessage().lower()
        return not (any(key.lower() in text for key in PRIVATE_KEYS if key)
                    or any(domain in text for domain in ('pixabay.com', 'pexels.com', 'vimeo.com', 'vimeocdn.com')))


for name in ('httpx', 'httpcore', 'httpcore.connection', 'httpcore.http11', 'httpcore.http2', 'httpcore.proxy'):
    logging.getLogger(name).addFilter(PrivateHTTPFilter())


def rendition(files):
    usable = [f for f in files if f.get('url') and isinstance(f.get('width'), int)
              and isinstance(f.get('height'), int) and f['width'] > 0 and f['height'] > 0]
    if not usable:
        raise ValueError()
    # Smallest rendition at least 1080-class, otherwise best available.
    suitable = [f for f in usable if f['width'] >= 1800 and f['height'] >= 1000]
    return min(suitable, key=lambda f: f['width']*f['height']) if suitable else max(usable, key=lambda f: f['width']*f['height'])


class APIStockProvider:
    name = ''
    label = ''
    def __init__(self, key, *, transport=None):
        self._key = SecretStr(key)
        if key:
            PRIVATE_KEYS.update((key,quote(key,safe='')))
        self.transport = transport

    def search(self, query, media_type):
        return self.search_videos(query) if media_type == 'video' else self.search_images(query)

    def search_videos(self, query): return self._search(query, 'video')
    def search_images(self, query): return self._search(query, 'image')

    def _search(self, query, media_type):
        key = self._key.get_secret_value()
        if not key:
            raise StockError('missing_key', self.label+' API anahtarını Ayarlar ekranında kaydedin.', 422)
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise StockError('invalid_query', 'Stok arama sorgusunu kontrol edin.', 422)
        SecretGuard((key,)).validate(query)
        started, category = time.monotonic(), 'success'
        try:
            url, headers, params, field = self.request(query, media_type, key)
            with httpx.Client(timeout=httpx.Timeout(30, connect=10), transport=self.transport,
                              follow_redirects=False) as client:
                with client.stream('GET', url, headers=headers, params=params) as response:
                    if response.status_code != 200:
                        category = {401:'key_rejected',403:'key_rejected',429:'rate_limit',400:'invalid_request'}.get(response.status_code, 'upstream_error')
                        message = {'key_rejected':' API anahtarı kabul edilmedi.',
                                   'rate_limit':' kullanım sınırına ulaşıldı. Bir süre bekleyip Devam Et deyin.',
                                   'invalid_request':' API isteği kabul edilmedi. Ayarlar ekranındaki anahtarı kontrol edin.',
                                   'upstream_error':' API şu anda yanıt veremiyor. Daha sonra tekrar deneyin.'}[category]
                        raise StockError(category, self.label+message)
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 4_000_000: raise ValueError()
            import json
            data = json.loads(raw)
            results = data[field]
            if not isinstance(results, list) or len(results) > 80: raise ValueError()
            normalized = []
            for item in results:
                try:
                    media = self.normalize_result(item, media_type, query)
                    SecretGuard((key,)).validate(media)
                    for field in ('source_url','page_url','preview_url','download_url','creator_url'):
                        if media[field]: safe_url(media[field], self.name, page=field in ('source_url','page_url','creator_url'))
                    normalized.append(media)
                except (ValueError, TypeError, KeyError, AttributeError, StockError):
                    continue  # A malformed/unsafe item cannot become a download.
            if results and not normalized:
                raise ValueError()
            return normalized
        except httpx.TimeoutException:
            category = 'timeout'
            raise StockError(category, self.label+' API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edin.') from None
        except httpx.HTTPError:
            category = 'connection_error'
            raise StockError(category, self.label+' API bağlantısı kurulamadı. İnternet bağlantınızı kontrol edin.') from None
        except StockError as error:
            category = error.category
            raise
        except (ValueError, TypeError, KeyError):
            category = 'invalid_response'
            raise StockError(category, self.label+' API yanıtı okunamadı. Daha sonra tekrar deneyin.', 502) from None
        finally:
            LOG.info('stock provider=%s operation=search_%s category=%s elapsed_ms=%.0f',
                     self.name, media_type, category, (time.monotonic()-started)*1000)


class PexelsStockProvider(APIStockProvider):
    name, label = 'pexels', 'Pexels'
    def request(self, query, media_type, key):
        # Current docs announce /v1/videos/; old SDK /videos/ is deprecated.
        url = 'https://api.pexels.com/v1/videos/search' if media_type == 'video' else 'https://api.pexels.com/v1/search'
        return url, {'Authorization':key}, {'query':query,'per_page':12,'orientation':'landscape'}, 'videos' if media_type == 'video' else 'photos'

    def normalize_result(self, item, media_type, query):
        if media_type == 'video':
            files = [{'url':f['link'],'width':f['width'],'height':f['height']} for f in item['video_files']
                     if f['file_type']=='video/mp4' and not urlsplit(f['link']).path.endswith('.m3u8')]
            chosen = rendition(files)
            creator = item['user']
            # Official video schema lacks an alt text. Slug is only a ranking hint.
            description = ' '.join(token for token in re.findall(r'[^\W\d_]+',unquote(urlsplit(item['url']).path))
                                   if token.casefold() not in ('video','videos'))
            preview, duration = item['image'], item['duration']
        else:
            width, height = item['width'], item['height']
            chosen = {'url':item['src']['large2x'], 'width':1880,'height':1300}
            creator = {'name':item['photographer'],'url':item['photographer_url']}
            description, preview, duration = item.get('alt') or '', item['src']['medium'], None
        return normalized_media({'provider':self.name,'media_id':str(item['id']),'media_type':media_type,
             'source_url':item['url'],'page_url':item['url'],'creator_name':creator['name'],'creator_url':creator['url'],
             'width':chosen['width'],'height':chosen['height'],'duration':duration,'preview_url':preview,
             'download_url':chosen['url'],'query_used':query,'description':description,
             'source_metadata':{'original_width':item['width'],'original_height':item['height'],
                                'documentation_url':'https://www.pexels.com/api/documentation/'}})


class PixabayStockProvider(APIStockProvider):
    name, label = 'pixabay', 'Pixabay'
    def request(self, query, media_type, key):
        # Pixabay documents a 100-character query limit and 24-hour caching.
        params = {'key':key,'q':query[:100],'per_page':12,'safesearch':'true'}
        if media_type == 'image': params.update(image_type='photo',orientation='horizontal')
        return 'https://pixabay.com/api/videos/' if media_type == 'video' else 'https://pixabay.com/api/', {}, params, 'hits'

    def normalize_result(self, item, media_type, query):
        if media_type == 'video':
            chosen = rendition(item['videos'].values())
            preview, duration = chosen['thumbnail'], item['duration']
        else:
            max_side = 1920 if item.get('fullHDURL') else 1280
            factor = min(1, max_side/max(item['imageWidth'],item['imageHeight']))
            chosen = {'url':item.get('fullHDURL') or item['largeImageURL'],
                      'width':round(item['imageWidth']*factor),'height':round(item['imageHeight']*factor)}
            preview, duration = item['previewURL'], None
        return normalized_media({'provider':self.name,'media_id':str(item['id']),'media_type':media_type,
            'source_url':item['pageURL'],'page_url':item['pageURL'],'creator_name':item['user'],
            'creator_url':'https://pixabay.com/users/'+quote(item['user'],safe='')+'-'+str(item['user_id'])+'/',
            'width':chosen['width'],'height':chosen['height'],'duration':duration,'preview_url':preview,
            'download_url':chosen['url'],'query_used':query,'description':item['tags'],
            'source_metadata':{'documentation_url':'https://pixabay.com/api/docs/',
                               **({'original_width':item['imageWidth'],'original_height':item['imageHeight']} if media_type=='image' else {})}})


def make_stock_provider(name, settings):
    providers = {'pexels':PexelsStockProvider,'pixabay':PixabayStockProvider}
    if name not in providers: raise StockError('invalid_provider','Bu stok sağlayıcısı kullanılamıyor.',422)
    return providers[name](settings.stock_config(name).get('api_key',''))
