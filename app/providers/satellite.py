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
from pathlib import Path

import httpx

TILE = 512  # pixels per tile of the @2x template


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


MESSAGES = {
    'missing_key': 'Mapbox API anahtarı girilmeli (Ayarlar). Uydu yerine çizilmiş harita kullanıldı.',
    'key_rejected': 'Mapbox anahtarı kabul edilmedi (401/403). Ayarlar → Mapbox anahtarını kontrol edin; uydu yerine çizilmiş harita kullanıldı.',
    'rate_limit': 'Mapbox istek sınırına takıldı (429). Biraz sonra yeniden deneyin; uydu yerine çizilmiş harita kullanıldı.',
    'not_found': 'Mapbox bu karoyu bulamadı (404). Ayarlar → Mapbox karo adresini kontrol edin; uydu yerine çizilmiş harita kullanıldı.',
    'upstream_error': 'Mapbox sunucusu hata verdi. Biraz sonra yeniden deneyin; uydu yerine çizilmiş harita kullanıldı.',
    'network_error': 'Mapbox’a bağlanılamadı (internet bağlantısını kontrol edin). Uydu yerine çizilmiş harita kullanıldı.',
    'invalid_response': 'Mapbox resim yerine okunamayan bir yanıt verdi. Uydu yerine çizilmiş harita kullanıldı.',
}


class MapboxSatelliteProvider(SatelliteProvider):
    name = 'mapbox'
    attribution = '© Mapbox'

    def __init__(self, api_key, tile_url, *, cache=None, transport=None, timeout=20.):
        if not api_key: raise SatelliteError('missing_key', MESSAGES['missing_key'])
        self.api_key, self.tile_url, self.cache = api_key, tile_url, Path(cache) if cache else None
        self.client = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)

    def tile(self, z, x, y):
        url = self.tile_url.format(z=int(z), x=int(x), y=int(y))
        path = None
        if self.cache:  # tiles are reused between clips (the key is never part of the file name)
            path = self.cache / (hashlib.sha256(url.encode()).hexdigest()[:32] + '.img')
            if path.is_file() and path.stat().st_size > 0: return path.read_bytes()
        try:
            response = self.client.get(url, params={'access_token': self.api_key})
        except httpx.HTTPError:
            raise SatelliteError('network_error', MESSAGES['network_error']) from None
        status = response.status_code
        if status in (401, 403): raise SatelliteError('key_rejected', MESSAGES['key_rejected'])
        if status == 429: raise SatelliteError('rate_limit', MESSAGES['rate_limit'])
        if status == 404: raise SatelliteError('not_found', MESSAGES['not_found'])
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


def provider():
    if FACTORY is None: raise SatelliteError('missing_key', MESSAGES['missing_key'])
    return FACTORY()
