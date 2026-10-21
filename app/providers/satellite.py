"""SatelliteProvider: satellite imagery tiles for the map template
(Harita stili → Uydu görüntüsü).

SatelliteProvider is the interface (one Web-Mercator tile as image bytes);
MapboxSatelliteProvider is the first implementation. Its URL template comes
from Settings (default: the Raster Tiles API pattern in
MAPBOX_INTEGRATION_NOTES.md) and the key from the encrypted settings store —
never from .env or source files. Every failure is a SatelliteError with a
plain Turkish message; the caller then draws the offline map instead.
"""
import hashlib
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

import httpx

TILE = 512  # pixels per tile of the @2x template
# Static Images API (eğik görünüm): the pattern given by the owner; a setting so it can be corrected without code.
STATIC_URL = 'https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{lon},{lat},{zoom},{bearing},{pitch}/{width}x{height}@2x'


class MapboxHTTPPrivacy(logging.Filter):
    def filter(self, record):
        text = record.getMessage().lower()
        return 'api.mapbox.com' not in text and 'access_token' not in text


for _logger in ('httpx', 'httpcore', 'httpcore.connection', 'httpcore.http11', 'httpcore.http2', 'httpcore.proxy'):
    logging.getLogger(_logger).addFilter(MapboxHTTPPrivacy())


class SatelliteError(Exception):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category


class SatelliteProvider:
    name = 'satellite'
    attribution = ''

    def tile(self, z, x, y):  # pragma: no cover - interface
        """Image bytes (JPEG/PNG) of tile z/x/y, or SatelliteError."""
        raise NotImplementedError

    def static(self, lon, lat, zoom, bearing, pitch, width, height):  # pragma: no cover - interface
        """One whole picture (eğik görünüm: bearing/pitch) of width×height logical pixels
        (@2x: twice as many real pixels), or SatelliteError."""
        raise SatelliteError('static_unsupported', 'Bu uydu sağlayıcısı eğik görünüm vermiyor; düz görünüm kullanıldı.')


MESSAGES = {
    'missing_key': 'Mapbox API anahtarı girilmeli (Ayarlar). Uydu yerine çizilmiş harita kullanıldı.',
    'key_rejected': 'Mapbox anahtarı kabul edilmedi (401/403); Mapbox hesabında kullanım sınırı veya ödeme sorunu olabilir. Ayarlar → Mapbox anahtarını ve hesabınızı kontrol edin; uydu yerine çizilmiş harita kullanıldı.',
    'monthly_limit': 'Bu ayki Mapbox güvenlik sınırına ulaşıldı. Uydu yerine çizilmiş harita kullanıldı; sınırı Ayarlar → Mapbox bölümünden değiştirebilirsiniz.',
    'rate_limit': 'Mapbox istek sınırına takıldı (429). Biraz sonra yeniden deneyin; uydu yerine çizilmiş harita kullanıldı.',
    'not_found': 'Mapbox bu karoyu bulamadı (404). Ayarlar → Mapbox karo adresini kontrol edin; uydu yerine çizilmiş harita kullanıldı.',
    'upstream_error': 'Mapbox sunucusu hata verdi. Biraz sonra yeniden deneyin; uydu yerine çizilmiş harita kullanıldı.',
    'network_error': 'Mapbox’a bağlanılamadı (internet bağlantısını kontrol edin). Uydu yerine çizilmiş harita kullanıldı.',
    'invalid_response': 'Mapbox resim yerine okunamayan bir yanıt verdi. Uydu yerine çizilmiş harita kullanıldı.',
    'invalid_request': 'Mapbox eğik görünüm isteğini kabul etmedi (422). Ayarlar → Mapbox “Eğik görünüm adresi” alanını kontrol edin.',
}


class MapboxSatelliteProvider(SatelliteProvider):
    name = 'mapbox'
    attribution = '© Mapbox'

    def __init__(self, api_key, tile_url, *, static_url=STATIC_URL, cache=None, transport=None, timeout=20., selected_style=''):
        if not api_key: raise SatelliteError('missing_key', MESSAGES['missing_key'])
        self.api_key, self.tile_url, self.static_url, self.cache = api_key, tile_url, static_url or STATIC_URL, Path(cache) if cache else None
        self.client = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)
        self.selected_style = selected_style

    def tile(self, z, x, y):
        if self.selected_style:
            # Static Images' world is 512*2**zoom logical pixels. A 256px @2x
            # request at z-1 covers exactly one standard tile and returns 512px.
            import math
            n = 2 ** int(z)
            lon = (int(x) + .5) / n * 360 - 180
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (int(y) + .5) / n))))
            return self.static(lon, lat, int(z) - 1, 0, 0, 256, 256)
        return self._get(self.tile_url.format(z=int(z), x=int(x), y=int(y)), 'tiles')

    def static(self, lon, lat, zoom, bearing, pitch, width, height):
        """Static Images API: the whole view in one request (pitch 0–60, bearing 0–360,
        at most 1280×1280 logical pixels — the limits are kept here, the API checks them too)."""
        url = self.static_url.format(lon=f'{lon:.5f}', lat=f'{max(-85., min(85., lat)):.5f}', zoom=f'{max(0., min(22., zoom)):.2f}',
                                     bearing=f'{bearing % 360:.1f}', pitch=f'{max(0., min(60., pitch)):.1f}',
                                     width=int(max(1, min(1280, width))), height=int(max(1, min(1280, height))))
        return self._get(url, 'static')

    def masked(self, url):
        """The request URL for logs and the render diagnostics: the key hidden (pk.***abcd)."""
        return f'{url}?access_token={self.api_key[:3]}***{self.api_key[-4:]}'

    def _get(self, url, kind='tiles'):
        self.last_request = self.masked(url)
        path = None
        if self.cache:  # tiles are reused between clips (the key is never part of the file name)
            path = self.cache / (hashlib.sha256(url.encode()).hexdigest()[:32] + '.img')
            if path.is_file() and path.stat().st_size > 0: return path.read_bytes()  # already downloaded: no request, not counted
        if not allow(kind): raise SatelliteError('monthly_limit', MESSAGES['monthly_limit'])
        count(kind)  # every request sent counts, whatever the answer
        try:
            response = self.client.get(url, params={'access_token': self.api_key})
        except httpx.HTTPError:
            raise SatelliteError('network_error', MESSAGES['network_error']) from None
        status = response.status_code
        self.last_response = f'{status} {response.headers.get("content-type", "?")} {len(response.content)} bayt'
        if status in (401, 403): raise SatelliteError('key_rejected', MESSAGES['key_rejected'])
        if status == 429: raise SatelliteError('rate_limit', MESSAGES['rate_limit'])
        if status == 404: raise SatelliteError('not_found', MESSAGES['not_found'])
        if status == 422: raise SatelliteError('invalid_request', MESSAGES['invalid_request'])
        if status != 200: raise SatelliteError('upstream_error', MESSAGES['upstream_error'])
        data = response.content
        if not (data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG') or data[8:12] == b'WEBP'):
            raise SatelliteError('invalid_response', MESSAGES['invalid_response'])
        if path:
            try:
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            except OSError:
                pass
        return data


# Set by the app at start-up: () -> SatelliteProvider (raises SatelliteError when not usable).
FACTORY = None
STYLE_KEY = None  # () -> selected style identity, also included in generated-scene cache keys

# ---- monthly safety limit (Ayarlar → Mapbox) ----
USAGE_FILE = None  # Path of data/mapbox_usage.json, set at start-up; None: nothing counted (tests)
LIMITS = None      # () -> {'tiles': int, 'static': int}, set at start-up from Settings
DEFAULT_LIMITS = {'tiles': 600_000, 'static': 40_000}
_USAGE_LOCK = threading.Lock()


def month():
    return datetime.now().strftime('%Y-%m')


def usage():
    """{'month', 'tiles', 'static'} of this month (a new month starts at 0)."""
    data = {}
    if USAGE_FILE:
        try: data = json.loads(Path(USAGE_FILE).read_text(encoding='utf-8'))
        except (OSError, ValueError): data = {}
    if data.get('month') != month(): data = {}
    return {'month': month(), 'tiles': int(data.get('tiles') or 0), 'static': int(data.get('static') or 0)}


def limits():
    try: return {**DEFAULT_LIMITS, **(LIMITS() if LIMITS else {})}
    except Exception: return dict(DEFAULT_LIMITS)


def allow(kind):
    return usage()[kind] < limits()[kind]


def count(kind):
    if not USAGE_FILE: return
    with _USAGE_LOCK:
        data = usage(); data[kind] += 1
        try:
            Path(USAGE_FILE).parent.mkdir(parents=True, exist_ok=True)
            Path(USAGE_FILE).write_text(json.dumps(data), encoding='utf-8')
        except OSError:
            pass


def usage_text():
    u, l = usage(), limits()
    return f'Bu ay: {u["tiles"]:,} karo / {u["static"]:,} eğik görüntü (sınır {l["tiles"]:,} / {l["static"]:,}).'.replace(',', '.')


def provider():
    if FACTORY is None: raise SatelliteError('missing_key', MESSAGES['missing_key'])
    return FACTORY()


# Set by the app at start-up: () -> bool, Ayarlar → Mapbox → “Eğik görünüm”.
OBLIQUE = None


def oblique():
    try: return bool(OBLIQUE and OBLIQUE())
    except Exception: return False


TEST_SECONDS = 15


def mapbox_check(config, transport=None):
    """“Bağlantıyı Test Et”: one tile (0/0/0) with a hard TEST_SECONDS limit.
    {'status': 'Hazır'|'Hata', 'message' (Turkish), 'category'}."""
    import threading
    if not config.get('api_key'):
        return {'status': 'Hata', 'category': 'missing_key', 'message': 'Mapbox API anahtarı girilmeli: anahtarı yazıp Kaydet deyin, sonra test edin.'}
    box = {}

    def work():
        try:
            p = MapboxSatelliteProvider(config['api_key'], config['tile_url'], static_url=config.get('static_url'), selected_style=config.get('selected_style', ''), transport=transport, timeout=TEST_SECONDS)
            try: p.tile(1 if config.get('selected_style') else 0, 0, 0)
            finally: p.client.close()
            box['ok'] = True
        except SatelliteError as error:
            box['error'] = error
        except Exception:  # never leave the button hanging
            box['error'] = SatelliteError('network_error', MESSAGES['network_error'])
    thread = threading.Thread(target=work, daemon=True)
    thread.start(); thread.join(TEST_SECONDS + 1)
    if thread.is_alive():
        return {'status': 'Hata', 'category': 'timeout', 'message': f'Mapbox {TEST_SECONDS} sn içinde yanıt vermedi. İnternet bağlantısını kontrol edip yeniden deneyin.'}
    if box.get('ok'):
        if not config.get('oblique', True):
            return {'status': 'Hazır', 'category': 'none', 'message': 'Mapbox bağlantısı başarılı: uydu karosu indirildi. Eğik görünüm kapalı (düz görünüm kullanılacak).'}
        tilted = static_check(config, transport)
        return {'status': 'Hazır' if tilted['ok'] else 'Hata', 'category': 'none' if tilted['ok'] else tilted['category'], 'request': tilted['request'],
                'message': 'Mapbox bağlantısı başarılı: uydu karosu indirildi. ' + tilted['message']}
    error = box['error']
    text = {'key_rejected': 'Mapbox anahtarı geçersiz veya yetkisiz (401/403); Mapbox hesabında kullanım sınırı veya ödeme sorunu olabilir. Anahtarı ve hesabınızı kontrol edip yeniden kaydedin.',
            'monthly_limit': MESSAGES['monthly_limit'],
            'network_error': 'Mapbox’a bağlanılamadı. İnternet bağlantısını kontrol edip yeniden deneyin.',
            'not_found': 'Mapbox karo adresi bulunamadı (404). “Uydu karo adresi” alanını kontrol edin.',
            'rate_limit': 'Mapbox istek sınırına takıldı (429). Biraz sonra yeniden deneyin.'}.get(error.category, str(error).split(';')[0] + '.')
    return {'status': 'Hata', 'category': error.category, 'message': text}


def static_check(config, transport=None):
    """One small tilted picture (pitch 45) from the Eğik görünüm address; the answer must be an image.
    {'ok', 'category', 'message' (Turkish), 'request' (URL, key hidden)}."""
    import threading
    box = {}

    def work():
        p = None
        try:
            p = MapboxSatelliteProvider(config['api_key'], config['tile_url'], static_url=config.get('static_url'), transport=transport, timeout=TEST_SECONDS)
            box['data'] = p.static(2.35, 48.86, 5, 0, 45, 300, 200)
        except SatelliteError as error:
            box['error'] = error
        except Exception:
            box['error'] = SatelliteError('network_error', MESSAGES['network_error'])
        box['request'] = getattr(p, 'last_request', '')
    thread = threading.Thread(target=work, daemon=True)
    thread.start(); thread.join(TEST_SECONDS + 1)
    if thread.is_alive():
        return {'ok': False, 'category': 'timeout', 'request': '', 'message': f'Eğik görünüm isteği {TEST_SECONDS} sn içinde yanıt vermedi; videoda düz görünüm kullanılır.'}
    if 'data' in box:
        return {'ok': True, 'category': 'none', 'request': box['request'], 'message': 'Eğik görünüm (Static Images API) de çalışıyor.'}
    error = box['error']
    reason = {'key_rejected': 'anahtar bu istek için yetkisiz (401/403; anahtarın “styles:tiles” izni olmalı; Mapbox hesabında kullanım sınırı veya ödeme sorunu olabilir)', 'not_found': 'adres bulunamadı (404)',
              'invalid_request': 'Mapbox isteği kabul etmedi (422)', 'rate_limit': 'istek sınırı (429)'}.get(error.category, str(error).split(';')[0].split('. ')[0].rstrip('.'))
    return {'ok': False, 'category': error.category, 'request': box['request'],
            'message': f'AMA eğik görünüm çalışmıyor: {reason}. Videoda düz görünüm kullanılır. Ayarlar → Mapbox → “Eğik görünüm adresi” alanını ve anahtar izinlerini kontrol edin.'}
