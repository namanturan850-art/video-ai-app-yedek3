"""Opt-in Magnific stock-video discovery. Never invokes generative APIs.

The API key is sent only to the fixed Magnific API origin. Search responses
contain public preview metadata; the temporary original-download URL is
resolved only after a candidate has passed the visual checks.
"""
from urllib.parse import urlsplit

import httpx

from app.stock.models import StockError, normalized_media


API = 'https://api.magnific.com'
DOCUMENTATION = 'https://docs.magnific.com/api-reference/videos/videos-api'
MAX_PAGE = 3
MAX_RESULTS = 40
API_HOST = urlsplit(API).hostname


def _items(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _https_url(items):
    for item in _items(items):
        value = item if isinstance(item, str) else item.get('url') if isinstance(item, dict) else None
        if isinstance(value, str) and value.startswith('https://') and len(value) <= 2048:
            return value
    return ''


def _license(item):
    """Public, non-URL licence/source labels safe to keep with the project."""
    values = _items(item.get('licenses')) or _items(item.get('license'))
    names = []
    for value in values:
        name = (value.get('name') or value.get('type')) if isinstance(value, dict) else value
        if isinstance(name, str) and name.strip():
            names.append(' '.join(name.split())[:120])
    return ' / '.join(dict.fromkeys(names))[:240]


class MagnificStockProvider:
    name = 'magnific'

    def __init__(self, key, *, transport=None):
        self.key, self.transport = key, transport
        self.last_diagnostic = None

    def _client(self):
        return httpx.Client(base_url=API, timeout=httpx.Timeout(20, connect=10), follow_redirects=False,
                            trust_env=False, transport=self.transport)

    def _request(self, path, *, params=None):
        if not self.key:
            raise StockError('missing_key', 'Magnific API anahtarı ayarlanmadı.')
        try:
            with self._client() as client:
                response = client.get(path, params=params, headers={'x-magnific-api-key': self.key})
        except httpx.TimeoutException:
            raise StockError('timeout', 'Magnific stok API zamanında yanıt vermedi.') from None
        except httpx.HTTPError:
            raise StockError('connection_error', 'Magnific stok API bağlantısı tamamlanamadı.') from None
        if response.status_code == 401:
            raise StockError('key_rejected', 'Magnific API anahtarı kabul edilmedi.')
        if response.status_code == 403:
            raise StockError('key_rejected', 'Magnific hesabının stok video API erişimi yok.')
        if response.status_code == 429:
            raise StockError('rate_limit', 'Magnific API kullanım sınırına ulaşıldı.')
        if response.status_code != 200:
            raise StockError('upstream_error', 'Magnific stok API isteği tamamlanamadı.')
        try:
            value = response.json()
        except ValueError:
            raise StockError('invalid_response', 'Magnific stok API yanıtı JSON değil.') from None
        if not isinstance(value, dict):
            raise StockError('invalid_response', 'Magnific stok API yanıtı okunamadı.')
        return value

    def search(self, query, media_type, *, page=1):
        if media_type != 'video':
            return []
        if not isinstance(page, int) or not 1 <= page <= MAX_PAGE:
            raise StockError('invalid_query', 'Arama sayfası geçersiz.')
        query = ' '.join(str(query or '').split())[:100]
        if not query:
            raise StockError('invalid_query', 'Magnific arama metni boş olamaz.')
        body = self._request('/v1/videos', params={'term': query, 'page': page, 'order': 'relevance'})
        listing = body.get('data')
        if isinstance(listing, dict):
            listing = listing.get('data', listing.get('items', listing.get('videos')))
        if not isinstance(listing, list):
            raise StockError('invalid_response', 'Magnific video listesi okunamadı.')
        output = []
        for item in listing[:MAX_RESULTS]:
            if not isinstance(item, dict) or item.get('is_ai_generated') is True:
                continue
            try:
                ident = str(item['id'])
                if not ident.isalnum() or len(ident) > 80:
                    raise ValueError()
                duration = float(item['duration'])
                if not 0 < duration <= 3600:
                    raise ValueError()
                options = [option for option in _items(item.get('options')) if isinstance(option, dict)]
                best = max(options, key=lambda option: int(option.get('width') or 0) * int(option.get('height') or 0), default={})
                width = int(item.get('width') or best.get('width') or 0)
                height = int(item.get('height') or best.get('height') or 0)
                if not 0 < width <= 16384 or not 0 < height <= 16384:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                continue
            preview_url = _https_url(item.get('thumbnails'))
            if not preview_url:
                continue  # Premium media is never selected from tags alone.
            tags = item.get('tags') or []
            description = ' '.join(str(tag.get('name', '') if isinstance(tag, dict) else tag) for tag in tags) if isinstance(tags, list) else ''
            title = item.get('name') or item.get('title') or ''
            output.append(normalized_media({
                'provider': 'magnific', 'media_id': ident, 'media_type': 'video',
                'source_url': '', 'page_url': '', 'creator_name': 'Magnific / Freepik', 'creator_url': '',
                'width': width, 'height': height, 'duration': duration, 'preview_url': preview_url,
                'download_url': '', 'query_used': query, 'provider_query': query,
                'description': (' '.join(str(title).split()) + ' ' + description).strip()[:1000],
                'source_metadata': {
                    'stock_api_id': ident, 'premium': bool(item.get('premium', True)),
                    'license': _license(item), 'source': 'Magnific / Freepik Premium stock',
                    'preview_frames': [url for url in dict.fromkeys([preview_url, _https_url(item.get('previews'))]) if url][:3],
                },
            }))
        meta = body.get('meta') if isinstance(body.get('meta'), dict) else {}
        self.last_diagnostic = {'page': page, 'results': len(output),
                                'current_page': meta.get('current_page'), 'last_page': meta.get('last_page')}
        return output

    def download_link(self, ident):
        """Resolve one temporary original URL at selection time."""
        ident = str(ident)
        if not ident.isalnum() or len(ident) > 80:
            raise StockError('invalid_query', 'Geçersiz Magnific medya kimliği.')
        data = self._request('/v1/videos/' + ident + '/download')
        data = data.get('data', data)
        if not isinstance(data, dict):
            raise StockError('invalid_response', 'Magnific indirme bağlantısı okunamadı.')
        url = data.get('url') or data.get('download_url')
        if not isinstance(url, str) or not url.startswith('https://') or len(url) > 4096:
            raise StockError('invalid_response', 'Magnific indirme bağlantısı okunamadı.')
        return url
