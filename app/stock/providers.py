"""Official contracts verified 2026-10-08; sources in docs/STOCK_MEDIA.md
(Wikimedia Commons: docs/WIKIMEDIA_COMMONS.md)."""
import html
import logging
import re
import time
from urllib.parse import quote, unquote, urlsplit

import httpx
from pydantic import SecretStr

from app.scripts.engine import SecretGuard
from app.stock.models import StockError, normalized_media
from app.stock.download import safe_url, USER_AGENT
from app.stock.diagnostics import safe_query
from app.scripts.models import ScriptError

LOG = logging.getLogger('uvicorn.error.stock')
PRIVATE_KEYS = set()
# Pexels stopped giving out new API keys: the provider stays in the code and
# its key field in Settings, but searches use Pixabay and Wikimedia Commons.
PEXELS_ENABLED = False
ACTIVE = ('pixabay', 'wikimedia') + (('pexels',) if PEXELS_ENABLED else ())


class PrivateHTTPFilter(logging.Filter):
    """httpx logs full URLs, which would expose Pixabay's query-string key.

    Stock requests opt into an extension; httpx records use positional request URL.
    Suppress HTTP client debug/request logs containing either stock API/CDN, without
    changing logs of Gemini, Ollama or OpenAI. Our diagnostic log is metadata-only.
    """
    def filter(self, record):
        text = record.getMessage().lower()
        return not (any(key.lower() in text for key in tuple(PRIVATE_KEYS) if key)
                    or any(domain in text for domain in ('pixabay.com', 'pexels.com', 'vimeo.com', 'vimeocdn.com', 'videvo.net', 'freepik.com', 'magnific.com')))


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
    needs_key = True
    def __init__(self, key, *, transport=None):
        self._key = SecretStr(key)
        if key:
            PRIVATE_KEYS.update((key,quote(key,safe='')))
        self.transport = transport
        self.last_diagnostic = None

    def search(self, query, media_type, *, page=1):
        return self._search(query,media_type,page=page)

    def page_params(self, page): return {'page': page}
    def results(self, data, field): return data[field]

    def search_videos(self, query): return self._search(query, 'video')
    def search_images(self, query): return self._search(query, 'image')

    def _search(self, query, media_type, *, page=1):
        if type(page) is not int or not 1<=page<=3:
            raise StockError('invalid_query','Arama sayfası geçersiz.',422)
        key = self._key.get_secret_value()
        if self.needs_key and not key:
            raise StockError('missing_key', self.label+' API anahtarını Ayarlar ekranında kaydedin.', 422)
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise StockError('invalid_query', 'Stok arama sorgusunu kontrol edin.', 422)
        SecretGuard((key,)).validate(query)
        started, category = time.monotonic(), 'success'
        self.last_diagnostic = {'raw_count':None,'normalized_count':0,
                                'rejected':{'malformed_result':0,'unsafe_url':0},'filtered':0}
        try:
            url, headers, params, field = self.request(query, media_type, key)
            if page>1:params.update(self.page_params(page))
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
            results = self.results(data, field)
            if not isinstance(results, list) or len(results) > 80: raise ValueError()
            self.last_diagnostic['raw_count'] = len(results)
            normalized = []
            for item in results:
                try:
                    media = self.normalize_result(item, media_type, query)
                    SecretGuard((key,)).validate(media)
                    for field in ('source_url','page_url','preview_url','download_url','creator_url'):
                        if media[field]: safe_url(media[field], self.name, page=field in ('source_url','page_url','creator_url'))
                    normalized.append(media)
                except FilteredResult:
                    self.last_diagnostic['filtered'] += 1  # a valid answer that is not usable here (licence, file type): not an error
                    continue
                except (ValueError, TypeError, KeyError, AttributeError, ScriptError) as error:
                    reason = 'unsafe_url' if isinstance(error,StockError) and error.category=='unsafe_url' else 'malformed_result'
                    self.last_diagnostic['rejected'][reason] += 1
                    continue  # A malformed/unsafe item cannot become a download.
            self.last_diagnostic['normalized_count'] = len(normalized)
            if results and not normalized and not self.last_diagnostic['filtered']:
                raise ValueError()  # every item unreadable (none merely filtered out): the answer's shape changed
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
            LOG.info('stock stage=normalization provider=%s media_type=%s query=%s raw_count=%s normalized_count=%s '
                     'rejected_malformed_result=%s rejected_unsafe_url=%s',
                     self.name,media_type,safe_query(query,tuple(PRIVATE_KEYS)),self.last_diagnostic['raw_count'],
                     self.last_diagnostic['normalized_count'],self.last_diagnostic['rejected']['malformed_result'],
                     self.last_diagnostic['rejected']['unsafe_url'])


class PexelsStockProvider(APIStockProvider):
    name, label = 'pexels', 'Pexels'
    def request(self, query, media_type, key):
        # Current docs announce /v1/videos/; old SDK /videos/ is deprecated.
        url = 'https://api.pexels.com/v1/videos/search' if media_type == 'video' else 'https://api.pexels.com/v1/search'
        return url, {'Authorization':key}, {'query':query,'per_page':40,'orientation':'landscape'}, 'videos' if media_type == 'video' else 'photos'

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
            # Documented `video_pictures`: preview frames across the clip, so
            # the media judge can see more than the cover image.
            pictures = [p['picture'] for p in item.get('video_pictures') or [] if isinstance(p, dict) and isinstance(p.get('picture'), str)]
            frames = [pictures[i] for i in sorted({0, len(pictures)//2, len(pictures)-1})] if pictures else []
        else:
            width, height = item['width'], item['height']
            chosen = {'url':item['src']['large2x'], 'width':1880,'height':1300}
            creator = {'name':item['photographer'],'url':item['photographer_url']}
            description, preview, duration = item.get('alt') or '', item['src']['medium'], None
            frames = []
        return normalized_media({'provider':self.name,'media_id':str(item['id']),'media_type':media_type,
             'source_url':item['url'],'page_url':item['url'],'creator_name':creator['name'],'creator_url':creator['url'],
             'width':chosen['width'],'height':chosen['height'],'duration':duration,'preview_url':preview,
             'download_url':chosen['url'],'query_used':query,'description':description,
             'source_metadata':{'original_width':item['width'],'original_height':item['height'],
                                'documentation_url':'https://www.pexels.com/api/documentation/',
                                **({'preview_frames':frames} if frames else {})}})


class PixabayStockProvider(APIStockProvider):
    name, label = 'pixabay', 'Pixabay'
    def request(self, query, media_type, key):
        # Pixabay documents a 100-character query limit and 24-hour caching.
        params = {'key':key,'q':query[:100],'per_page':40,'safesearch':'true'}
        if media_type == 'image': params.update(image_type='photo',orientation='horizontal')
        return 'https://pixabay.com/api/videos/' if media_type == 'video' else 'https://pixabay.com/api/', {}, params, 'hits'

    def normalize_result(self, item, media_type, query):
        if media_type == 'video':
            files = [f for f in item['videos'].values() if isinstance(f,dict) and isinstance(f.get('url'),str)
                     and urlsplit(f['url']).path.lower().endswith('.mp4')]
            chosen = rendition(files)
            preview, duration = chosen.get('thumbnail') or '', item['duration']
            # Smallest rendition: the media judge reads start/middle/end frames from it
            # (Pixabay documents only one thumbnail per video).
            smallest = min(files, key=lambda f: f.get('width') or 10**6)['url'] if files else ''
        else:
            smallest = ''
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
            'source_metadata':{'documentation_url':'https://pixabay.com/api/docs/',**({'sample_url':smallest} if smallest else {}),
                               **({'original_width':item['imageWidth'],'original_height':item['imageHeight']} if media_type=='image' else {})}})


# Licences that allow commercial use (YouTube): public domain, CC0, CC BY, CC BY-SA.
FREE_LICENCE = re.compile(r'^(public domain|pd([- ].*)?|cc0( 1\.0)?|cc[- ]by([- ]sa)?([- ]\d(\.\d)?([- ][a-z]{2,3})?)?)$')
NOT_FREE = re.compile(r'(^|[^a-z])(nc|nd|non[- ]?commercial|no[- ]?deriv|fair use|non-free|all rights reserved)([^a-z]|$)')
MAX_VIDEO_SECONDS = 60   # Commons videos are converted to MP4 locally; the first minute is plenty for B-roll


def text_of(value, limit=300):
    """Commons metadata is HTML: plain text only."""
    text = html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))
    return ' '.join(text.split())[:limit]


def commercial_licence(meta):
    """(short name, licence url) when the file may be used in a monetised
    video, else None. Unknown, NC, ND, fair-use and non-free files never pass."""
    field = lambda name: (meta.get(name) or {}).get('value') if isinstance(meta.get(name), dict) else None
    short = text_of(field('LicenseShortName'), 80)
    if not short or str(field('NonFree') or '').strip().lower() in ('true', '1', 'yes'):
        return None
    name = short.casefold().replace('_', ' ').strip()
    if NOT_FREE.search(name) or not FREE_LICENCE.match(name):
        return None
    if text_of(field('Restrictions'), 80):  # trademark/personality restrictions: not for automatic use
        return None
    url = field('LicenseUrl') or ''
    return short, url if isinstance(url, str) and url.startswith('https://') else ''


class FilteredResult(ValueError):
    """A readable search hit that may not be offered (non-commercial licence, a file type we cannot use).
    Not a malformed answer: Wikimedia searches often return only such files, which used to be reported as “invalid_response”."""


class WikimediaStockProvider(APIStockProvider):
    """Wikimedia Commons through the documented MediaWiki Action API (no key):
    full-text search in the File namespace + imageinfo with licence metadata."""
    name, label, needs_key = 'wikimedia', 'Wikimedia Commons', False

    def request(self, query, media_type, key):
        params = {'action': 'query', 'format': 'json', 'formatversion': '2', 'generator': 'search',
                  'gsrsearch': f'{query[:200]} filetype:{"video" if media_type == "video" else "bitmap"}',
                  'gsrnamespace': '6', 'gsrlimit': '30', 'prop': 'imageinfo',
                  'iiprop': 'url|size|mime|mediatype|extmetadata', 'iiurlwidth': '1920',
                  'iiextmetadatafilter': 'LicenseShortName|LicenseUrl|Artist|Credit|ImageDescription|ObjectName|NonFree|Restrictions|AttributionRequired'}
        return 'https://commons.wikimedia.org/w/api.php', {'User-Agent': USER_AGENT}, params, 'pages'

    def page_params(self, page):
        return {'gsroffset': str((page - 1) * 30)}

    def results(self, data, field):
        if 'error' in data:
            if str((data['error'] or {}).get('code', '')) in ('ratelimited', 'maxlag', 'readonly'):
                raise StockError('rate_limit', self.label + ' kullanım sınırına ulaşıldı. Bir süre bekleyip Devam Et deyin.')
            raise ValueError()
        pages = (data.get('query') or {}).get('pages', [])  # no hits: no 'query' at all
        return sorted(pages, key=lambda p: p.get('index', 0)) if isinstance(pages, list) else pages

    def normalize_result(self, item, media_type, query):
        if not item.get('imageinfo'): raise FilteredResult()  # a page without a file (deleted / redirect)
        info = item['imageinfo'][0]
        meta = info.get('extmetadata') or {}
        licence = commercial_licence(meta)
        if not licence: raise FilteredResult()  # NC/ND/unknown licence: never offered
        mime = info['mime']
        title = item['title'].removeprefix('File:')
        author = text_of((meta.get('Artist') or {}).get('value')) or text_of((meta.get('Credit') or {}).get('value')) or 'Bilinmeyen yazar'
        about = text_of((meta.get('ImageDescription') or {}).get('value'), 600)
        description = ' '.join(f'{re.sub(r"[_.-]+", " ", title.rsplit(".", 1)[0])} {about}'.split())[:1000]
        if media_type == 'video':
            if mime not in ('video/webm',) or not info.get('duration') or info.get('size', 0) > 200_000_000: raise FilteredResult()  # ogv/mpeg, too long, too big
            download, width, height = info['url'], info['width'], info['height']
            duration = min(float(info['duration']), MAX_VIDEO_SECONDS)
            preview = info.get('thumburl') or ''
        else:
            if not mime.startswith('image/') or not info.get('thumburl'): raise FilteredResult()  # PDF/audio, or no 1920 px thumbnail
            download, width, height = info['thumburl'], info.get('thumbwidth') or info['width'], info.get('thumbheight') or info['height']
            duration, preview = None, info['thumburl']
        return normalized_media({'provider': self.name, 'media_id': str(item['pageid']), 'media_type': media_type,
            'source_url': info['descriptionurl'], 'page_url': info['descriptionurl'], 'creator_name': author[:300], 'creator_url': '',
            'width': width, 'height': height, 'duration': duration, 'preview_url': preview,
            'download_url': download, 'query_used': query, 'description': description,
            'source_metadata': {'documentation_url': 'https://www.mediawiki.org/wiki/API:Imageinfo', 'title': title[:300],
                                'license': licence[0], 'license_url': licence[1], 'author': author[:300], 'original_mime': mime,
                                'original_width': info['width'], 'original_height': info['height'],
                                **({'sample_url': download} if media_type == 'video' and info.get('size', 0) <= 15_000_000 else {})}})


def make_stock_provider(name, settings):
    providers = {'pexels':PexelsStockProvider,'pixabay':PixabayStockProvider,'wikimedia':WikimediaStockProvider}
    if name not in providers: raise StockError('invalid_provider','Bu stok sağlayıcısı kullanılamıyor.',422)
    for key in settings.secret_values(): PRIVATE_KEYS.update((key,quote(key,safe='')))
    if name == 'wikimedia': return WikimediaStockProvider('')
    return providers[name](settings.stock_config(name).get('api_key',''))
