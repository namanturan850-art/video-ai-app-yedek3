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
ACTIVE = ('pixabay', 'wikimedia', 'nasa', 'archive', 'europeana') + (('pexels',) if PEXELS_ENABLED else ())


class PrivateHTTPFilter(logging.Filter):
    """httpx logs full URLs, which would expose Pixabay's query-string key.

    Stock requests opt into an extension; httpx records use positional request URL.
    Suppress HTTP client debug/request logs containing either stock API/CDN, without
    changing logs of Gemini, Ollama or OpenAI. Our diagnostic log is metadata-only.
    """
    def filter(self, record):
        text = record.getMessage().lower()
        return not (any(key.lower() in text for key in tuple(PRIVATE_KEYS) if key)
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


def retry_after(response):
    """Documented HTTP Retry-After, seconds or date; no immediate retries."""
    value = response.headers.get('retry-after', '')
    try:
        delay = float(value)
    except ValueError:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone
        try: delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError): return 60.
    return min(86400., max(1., delay)) if delay == delay else 60.


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
                        error = StockError(category, self.label+message)
                        if category == 'rate_limit': error.retry_after = retry_after(response)
                        raise error
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 4_000_000: raise ValueError('answer_too_large')
            import json
            data = json.loads(raw)
            results = self.results(data, field)
            if not isinstance(results, list) or len(results) > 80: raise ValueError('result_list_shape')
            self.last_diagnostic['raw_count'] = len(results)
            normalized = []
            for item in results:
                try:
                    media = self.normalize_result(item, media_type, query)
                    SecretGuard((key,)).validate(media)
                    for field in ('source_url','page_url','preview_url','download_url','creator_url'):
                        if media[field]:
                            try: safe_url(media[field], self.name, page=field in ('source_url','page_url','creator_url'), preview=field=='preview_url')
                            except StockError:
                                # Which address failed (field + host only, never the path or a key): shown in the diagnostics.
                                self.last_diagnostic.setdefault('result_category', unsafe_label(field, media[field]))
                                raise
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
                raise ValueError('all_items_unreadable')  # every item unreadable (none merely filtered out): the answer's shape changed
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
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            category = 'invalid_response'
            self.last_diagnostic['response_category'] = response_reason(error)  # the real cause, for the diagnostics file
            raise StockError(category, self.label+' API yanıtı okunamadı. Daha sonra tekrar deneyin.', 502) from None
        finally:
            LOG.info('stock provider=%s operation=search_%s category=%s elapsed_ms=%.0f',
                     self.name, media_type, category, (time.monotonic()-started)*1000)
            LOG.info('stock stage=normalization provider=%s media_type=%s query=%s raw_count=%s normalized_count=%s '
                     'rejected_malformed_result=%s rejected_unsafe_url=%s',
                     self.name,media_type,safe_query(query,tuple(PRIVATE_KEYS)),self.last_diagnostic['raw_count'],
                     self.last_diagnostic['normalized_count'],self.last_diagnostic['rejected']['malformed_result'],
                     self.last_diagnostic['rejected']['unsafe_url'])


def unsafe_label(field, value):
    """'unsafe_url:<field>@<host>' (or why the address is not even a normal one); no path, no query."""
    try:
        if not isinstance(value, str): return f'unsafe_url:{field}@not_text'
        if len(value) > 2000: return f'unsafe_url:{field}@too_long'
        parts = urlsplit(value)
        if parts.scheme != 'https': return f'unsafe_url:{field}@scheme_{re.sub(r"[^a-z]", "", parts.scheme.lower())[:8] or "none"}'
        host = re.sub(r'[^A-Za-z0-9.-]', '', parts.hostname or '')[:60] or 'no_host'
        return f'unsafe_url:{field}@{host}'
    except (ValueError, TypeError, AttributeError):
        return f'unsafe_url:{field}@unreadable'


def response_reason(error):
    """A short, secret-free label for why an answer could not be read (diagnostics file only)."""
    import json
    if isinstance(error, json.JSONDecodeError): return 'not_json'
    text = str(error)
    if isinstance(error, ValueError) and re.fullmatch(r'[a-z_]+(:[A-Za-z0-9_.-]{0,60})?', text): return text
    return type(error).__name__


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
        params = {'key':key,'q':query[:100],'per_page':80,'safesearch':'true'}  # documented 3-200; the shared answer guard allows 80
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
            raise ValueError('api_error:' + re.sub(r'[^A-Za-z0-9_.-]', '', str((data['error'] or {}).get('code', '')))[:60])
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


class NASAStockProvider(APIStockProvider):
    """NASA Image and Video Library (images-api.nasa.gov, no key; docs/NASA_IMAGE_LIBRARY.md).
    Images only: the search response gives no duration/size for video files, and probing every
    candidate would slow Medyayı Tamamla down (see the doc's "Neden video yok")."""
    name, label, needs_key = 'nasa', 'NASA Görsel Kütüphanesi', False

    def request(self, query, media_type, key):
        return 'https://images-api.nasa.gov/search', {}, {'q': query[:200], 'media_type': 'image', 'page_size': 40}, 'items'

    def _search(self, query, media_type, *, page=1):
        if media_type == 'video':
            return []  # no network call: this source has images only
        return super()._search(query, media_type, page=page)

    def results(self, data, field):
        return ((data.get('collection') or {}).get(field) or [])

    def normalize_result(self, item, media_type, query):
        info = (item.get('data') or [{}])[0]
        if info.get('copyright'): raise FilteredResult()  # rare non-NASA-owned exception: never offered
        nasa_id = info.get('nasa_id')
        if not nasa_id: raise FilteredResult()
        files = [{'url': l['href'], 'width': l.get('width'), 'height': l.get('height')} for l in (item.get('links') or [])
                 if l.get('render') == 'image' and isinstance(l.get('width'), int) and isinstance(l.get('height'), int)]
        chosen = rendition(files)
        preview = min(files, key=lambda f: f['width'] * f['height'])['url']
        creator = info.get('secondary_creator') or info.get('center') or 'NASA'
        description = ' '.join(f"{info.get('title', '')} {info.get('description', '')}".split())[:600]
        return normalized_media({'provider': self.name, 'media_id': nasa_id, 'media_type': 'image',
            'source_url': f'https://images.nasa.gov/details/{nasa_id}', 'page_url': f'https://images.nasa.gov/details/{nasa_id}',
            'creator_name': creator[:300], 'creator_url': '', 'width': chosen['width'], 'height': chosen['height'],
            'duration': None, 'preview_url': preview, 'download_url': chosen['url'], 'query_used': query,
            'description': description, 'source_metadata': {'documentation_url': 'https://images.nasa.gov/docs',
                'title': str(info.get('title', ''))[:300], 'center': str(info.get('center', ''))[:120],
                'date_created': str(info.get('date_created', ''))[:40], 'keywords': [str(k)[:60] for k in (info.get('keywords') or [])][:12]}})


# Internet Archive: only these licences (monetised YouTube video): Public Domain Mark, CC0, CC BY, CC BY-SA.
ARCHIVE_LICENCE = re.compile(r'^https?://(?:www\.)?creativecommons\.org/(publicdomain/(mark|zero)/|licenses/(by|by-sa)/)(\d+\.\d+)/?(?:deed\.[a-zA-Z_-]+|legalcode)?$', re.I)
ARCHIVE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$')
ARCHIVE_SERVER = re.compile(r'^ia\d{3,7}\.us\.archive\.org$')
ARCHIVE_DIR = re.compile(r'^/[0-9]{1,3}/items/[A-Za-z0-9._-]{1,100}$')
ARCHIVE_MAX_BYTES = 250_000_000  # the downloader's video limit


def archive_licence(url):
    """(short name, url) for an accepted licence URL, else None (NC, ND, unknown, missing)."""
    match = ARCHIVE_LICENCE.match(str(url or '').strip())
    if not match: return None
    version = f' {match.group(4)}' if match.group(4) else ''
    name = {'mark': 'Public Domain Mark', 'zero': 'CC0'}.get(match.group(2)) or ('CC BY' if match.group(3) == 'by' else 'CC BY-SA') + version
    return name, str(url).strip()


def archive_seconds(value):
    """'123.45' or 'HH:MM:SS(.ss)' -> seconds, else None."""
    try:
        text = str(value).strip()
        if ':' in text:
            total = 0.
            for part in text.split(':'): total = total * 60 + float(part)
            return total if total > 0 else None
        number = float(text)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


class ArchiveStockProvider(APIStockProvider):
    """Internet Archive (no key; docs/INTERNET_ARCHIVE.md): advancedsearch for films with an
    accepted licence, then the item's metadata (files with width/height/length) for each hit.
    Videos only. Archive films are often 4:3 and SD: app/stock/quality.py accepts them for this source."""
    name, label, needs_key = 'archive', 'Internet Archive', False
    ROWS = 12

    def request(self, query, media_type, key):
        words = ' '.join(re.findall(r'[\w-]+', query))[:200] or 'film'
        # Slashes inside a wildcard term must be escaped, otherwise the search backend fails (checked live 2026-10-20).
        q = (f'({words}) AND mediatype:(movies) AND (licenseurl:*publicdomain* OR licenseurl:*licenses\\/by\\/* '
             'OR licenseurl:*licenses\\/by-sa\\/*)')
        params = {'q': q, 'fl[]': ['identifier', 'title', 'licenseurl'], 'rows': self.ROWS, 'output': 'json'}
        return 'https://archive.org/advancedsearch.php', {'User-Agent': USER_AGENT}, params, 'docs'

    def page_params(self, page):
        return {'page': page}

    def _search(self, query, media_type, *, page=1):
        if media_type != 'video':
            return []  # no network call: this source has films only
        return super()._search(query, media_type, page=page)

    CACHE, CACHE_LOCK, CACHE_TTL, CACHE_MAX = {}, __import__('threading').Lock(), 3600, 400  # provider objects are per search: shared across them

    def metadata(self, identifier):
        now = time.monotonic()
        with self.CACHE_LOCK:
            hit = self.CACHE.get(identifier)
        if hit and now - hit[0] < self.CACHE_TTL: return hit[1]
        data = self._fetch_metadata(identifier)
        if data is not None:  # a failed fetch is retried next time, never remembered
            with self.CACHE_LOCK:
                if len(self.CACHE) >= self.CACHE_MAX: self.CACHE.clear()
                self.CACHE[identifier] = (now, data)
        return data

    def _fetch_metadata(self, identifier):
        try:
            with httpx.Client(timeout=httpx.Timeout(15, connect=8), transport=self.transport, follow_redirects=False) as client:
                response = client.get(f'https://archive.org/metadata/{identifier}', headers={'User-Agent': USER_AGENT})
                if response.status_code != 200 or len(response.content) > 3_000_000: return None
                data = response.json()
                return data if isinstance(data, dict) else None
        except (httpx.HTTPError, ValueError):
            return None

    def results(self, data, field):
        docs = (data.get('response') or {}).get(field)
        if not isinstance(docs, list): raise ValueError()
        keep = [d for d in docs if isinstance(d, dict) and isinstance(d.get('identifier'), str) and ARCHIVE_ID.match(d['identifier'])]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as pool:
            for doc, meta in zip(keep, pool.map(self.metadata, [d['identifier'] for d in keep])):
                doc['_metadata'] = meta
        return docs

    def normalize_result(self, doc, media_type, query):
        identifier = doc.get('identifier')
        meta = doc.get('_metadata')
        if not isinstance(identifier, str) or not ARCHIVE_ID.match(identifier) or not isinstance(meta, dict): raise FilteredResult()
        info = meta.get('metadata') if isinstance(meta.get('metadata'), dict) else {}
        licence = archive_licence(info.get('licenseurl') or doc.get('licenseurl'))
        if not licence: raise FilteredResult()  # NC/ND/unknown: never offered
        server, folder = meta.get('server'), meta.get('dir')
        if not (isinstance(server, str) and ARCHIVE_SERVER.match(server) and isinstance(folder, str) and ARCHIVE_DIR.match(folder)): raise FilteredResult()
        files = [f for f in meta.get('files') or [] if isinstance(f, dict) and isinstance(f.get('name'), str) and '..' not in f['name']]
        videos = []
        for f in files:
            if not f['name'].lower().endswith('.mp4'): continue
            try: width, height, size = int(f['width']), int(f['height']), int(f.get('size') or 0)
            except (KeyError, TypeError, ValueError): continue
            length = archive_seconds(f.get('length'))
            if not length or width < 640 or height < 480 or not 1.25 <= width / height <= 1.95 or not 0 < size <= ARCHIVE_MAX_BYTES: continue
            videos.append({'name': f['name'], 'width': width, 'height': height, 'size': size, 'length': length})
        if not videos: raise FilteredResult()  # no usable MP4 (too small, too big, unknown length)
        hd = [v for v in videos if v['width'] >= 1280]
        chosen = min(hd, key=lambda v: v['size']) if hd else max(videos, key=lambda v: (v['width'] * v['height'], -v['size']))
        link = lambda name: f'https://{server}{folder}/' + quote(name, safe='/')
        thumbs = sorted(f['name'] for f in files if f.get('format') == 'Thumbnail' and f['name'].lower().endswith('.jpg'))
        picked = [thumbs[i] for i in sorted({0, len(thumbs) // 2, len(thumbs) - 1})] if thumbs else []
        frames = [link(name) for name in picked]
        creator = info.get('creator')
        creator = text_of(creator[0] if isinstance(creator, list) and creator else creator, 300) or 'Internet Archive'
        title = text_of(info.get('title') or doc.get('title'), 300)
        about = text_of(info.get('description'), 600)
        page = f'https://archive.org/details/{identifier}'
        return normalized_media({'provider': self.name, 'media_id': re.sub(r'[^A-Za-z0-9_-]', '_', identifier)[:100], 'media_type': 'video',
            'source_url': page, 'page_url': page, 'creator_name': creator, 'creator_url': '',
            'width': chosen['width'], 'height': chosen['height'], 'duration': chosen['length'],
            'preview_url': frames[0] if frames else '', 'download_url': link(chosen['name']), 'query_used': query,
            'description': ' '.join(f'{title} {about}'.split())[:1000],
            'source_metadata': {'documentation_url': 'https://archive.org/developers/', 'identifier': identifier, 'title': title,
                                'license': licence[0], 'license_url': licence[1], 'author': creator,
                                'original_width': chosen['width'], 'original_height': chosen['height'],
                                **({'preview_frames': frames} if frames else {}),
                                **({'sample_url': link(chosen['name'])} if not frames and chosen['size'] <= 60_000_000 else {})}})


def europeana_strings(value):
    """Search metadata can contain either one string or a list of strings."""
    if isinstance(value, str): return [value] if value.strip() else []
    if isinstance(value, list): return [v for v in value if isinstance(v, str) and v.strip()]
    return []


class EuropeanaStockProvider(APIStockProvider):
    """Image-only Search API adapter. Image dimensions come from the actual file."""
    name, label = 'europeana', 'Europeana'

    def _search(self, query, media_type, *, page=1):
        # No invented video metadata or undocumented pagination parameters.
        if media_type == 'video': return []
        if type(page) is not int or not 1 <= page <= 3:
            raise StockError('invalid_query', 'Arama sayfası geçersiz.', 422)
        if page > 1: return []
        return super()._search(query, media_type, page=page)

    def request(self, query, media_type, key):
        return ('https://api.europeana.eu/record/v2/search.json',
                {'X-Api-Key': key, 'User-Agent': USER_AGENT},
                {'query': query, 'reusability': 'open', 'media': 'true', 'rows': 24,
                 'qf': ['IMAGE_ASPECTRATIO:landscape', 'IMAGE_SIZE:large']}, 'items')

    def results(self, data, field):
        if not isinstance(data, dict) or data.get('success') is not True or data.get('error'):
            # Never echo server error text: it may contain credentials.
            raise ValueError('api_error')
        for name in ('itemsCount', 'totalResults'):
            if type(data.get(name)) is not int or data[name] < 0:
                raise ValueError('result_count_shape')
        items = data.get(field, []) if data['itemsCount'] == 0 else data[field]
        if not isinstance(items, list) or len(items) != data['itemsCount'] or len(items) > 24:
            raise ValueError('result_list_shape')
        # The real size comes from each museum's own file: read those headers side by side,
        # not one after another (24 slow museum servers in a row made one search take minutes).
        # Only for a hit that could ever be offered (open, unambiguous licence; an author when the
        # licence needs one) — the museum is never contacted for one we would reject anyway.
        from concurrent.futures import ThreadPoolExecutor
        def size(item):
            try:
                self._licence_and_author(item)
                url = europeana_strings(item.get('edmIsShownBy'))[0]
                SecretGuard((self._key.get_secret_value(),)).validate(url)
                return self.image_dimensions(safe_url(url, self.name))
            except Exception:  # not offerable, unreadable, unsafe, too big, not an image
                return None
        usable = [item for item in items if isinstance(item, dict) and europeana_strings(item.get('edmIsShownBy'))]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for item, dimensions in zip(usable, pool.map(size, usable)):
                item['_dimensions'] = dimensions
        return items

    def _licence_and_author(self, item):
        """(licence, author) for a hit we would ever offer, else raises FilteredResult. No network."""
        rights = europeana_strings(item.get('rights'))
        licences = [archive_licence(right) for right in rights]
        if not licences or not all(licences) or len(set(licences)) != 1: raise FilteredResult()
        licence = licences[0]
        author = text_of('; '.join(europeana_strings(item.get('dcCreator'))), 300)
        if licence[0].startswith('CC BY') and not author: raise FilteredResult()
        return licence, author

    def image_dimensions(self, url):
        from PIL import ImageFile
        # Read only enough of a bounded image header to obtain its real size.
        # A separate unauthenticated client never leaks X-Api-Key to a museum.
        with httpx.Client(timeout=httpx.Timeout(15, connect=8), transport=self.transport,
                          follow_redirects=False) as client:
            for redirect in range(4):
                safe_url(url, self.name)  # DNS rechecked before each request, including redirects
                with client.stream('GET', url, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        from urllib.parse import urljoin
                        if redirect == 3 or not response.headers.get('location'): raise FilteredResult()
                        url = urljoin(url, response.headers['location'])
                        continue
                    if response.status_code != 200: raise FilteredResult()
                    mime = response.headers.get('content-type', '').split(';')[0].strip().lower()
                    if mime not in ('image/jpeg', 'image/png', 'image/webp'): raise FilteredResult()
                    length = response.headers.get('content-length')
                    if length and (not length.isdigit() or not 12 <= int(length) <= 20_000_000):
                        raise FilteredResult()
                    parser, size = ImageFile.Parser(), 0
                    for chunk in response.iter_bytes(16384):
                        size += len(chunk)
                        if size > 262144: raise FilteredResult()
                        parser.feed(chunk)
                        if parser.image:
                            if parser.image.format not in ('JPEG', 'PNG', 'WEBP'): raise FilteredResult()
                            width, height = parser.image.size
                            if not (0 < width <= 20000 and 0 < height <= 20000): raise FilteredResult()
                            return width, height
                    raise FilteredResult()
        raise FilteredResult()

    def normalize_result(self, item, media_type, query):
        import hashlib
        from PIL import Image
        if not isinstance(item, dict): raise ValueError('item_shape')
        # Not the whole item: Europeana itself writes the caller's key into some of its own links
        # (the item page's tracking parameters, the record link). Those are never used; every field
        # that is used is checked below, and the final record is checked again by the shared search code.
        licence, author = self._licence_and_author(item)
        title = text_of('; '.join(europeana_strings(item.get('title'))), 300)
        pages = europeana_strings(item.get('guid'))
        if not pages: raise FilteredResult()
        # The item page as Europeana gives it, without its query part (utm_* tracking, which can
        # contain the caller's API key): the page itself is the same.
        page = urlsplit(pages[0])._replace(query='').geturl()
        page = safe_url(page, self.name, page=True)
        SecretGuard((self._key.get_secret_value(),)).validate(page)
        urls = europeana_strings(item.get('edmIsShownBy'))
        if not urls: raise FilteredResult()
        download = urls[0]
        SecretGuard((self._key.get_secret_value(),)).validate(download)
        dimensions = item.get('_dimensions')
        if dimensions is None and '_dimensions' not in item:  # not prefetched (direct call)
            try:
                dimensions = self.image_dimensions(safe_url(download, self.name))
            except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError):
                dimensions = None
        if not dimensions: raise FilteredResult()
        width, height = dimensions
        download = safe_url(download, self.name)
        preview = ''
        for url in europeana_strings(item.get('edmPreview')):
            try: preview = safe_url(url, self.name, preview=True)
            except StockError: continue
            break
        return normalized_media({'provider': self.name, 'media_id': hashlib.sha256(page.encode()).hexdigest(),
            'media_type': 'image', 'source_url': page, 'page_url': page, 'creator_name': author,
            'creator_url': '', 'width': width, 'height': height, 'duration': None,
            'preview_url': preview, 'download_url': download, 'query_used': query, 'description': title,
            'source_metadata': {'title': title, 'author': author, 'license': licence[0], 'license_url': licence[1],
                                'data_provider': text_of('; '.join(europeana_strings(item.get('dataProvider'))), 300)}})


def make_stock_provider(name, settings):
    providers = {'pexels':PexelsStockProvider,'pixabay':PixabayStockProvider,'wikimedia':WikimediaStockProvider,'nasa':NASAStockProvider,'archive':ArchiveStockProvider,'europeana':EuropeanaStockProvider}
    if name not in providers: raise StockError('invalid_provider','Bu stok sağlayıcısı kullanılamıyor.',422)
    for key in settings.secret_values(): PRIVATE_KEYS.update((key,quote(key,safe='')))
    if name in ('wikimedia', 'nasa', 'archive'): return providers[name]('')
    return providers[name](settings.stock_config(name).get('api_key',''))
