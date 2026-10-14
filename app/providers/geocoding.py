"""GeocodingProvider: a place name → (lat, lon), for map markers whose place the
offline lists do not know (“Genêts”).

MapboxGeocodingProvider sends one forward-geocoding request (the address is a
setting, default GEOCODE_URL; key from the encrypted settings store) and reads
only standard GeoJSON from the answer: features[0].geometry.coordinates =
[longitude, latitude] (RFC 7946). Nothing else of the response is used. See
MAPBOX_INTEGRATION_NOTES.md (not verified against a real account from the
development environment). Answers (also “not found”) are cached on disk, so a
name is asked only once. Any failure → None; the caller then draws the map
around the nearest known region and warns in Turkish.
"""
import json
import logging
import threading
from pathlib import Path

import httpx

LOG = logging.getLogger('uvicorn.error.geocoding')
GEOCODE_URL = 'https://api.mapbox.com/search/geocode/v6/forward'


class GeocodingProvider:
    name = 'geocoding'

    def forward(self, name):  # pragma: no cover - interface
        """(lat, lon) of the first match, or None."""
        raise NotImplementedError


class MapboxGeocodingProvider(GeocodingProvider):
    name = 'mapbox'

    def __init__(self, api_key, url=GEOCODE_URL, *, transport=None, timeout=15.):
        self.api_key, self.url = api_key, url or GEOCODE_URL
        self.client = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)
        self.last_problem = ''

    def forward(self, name):
        if not self.api_key:
            self.last_problem = 'Mapbox anahtarı yok'; return None
        try:
            response = self.client.get(self.url, params={'q': name, 'access_token': self.api_key})
        except httpx.HTTPError:
            self.last_problem = 'Mapbox’a bağlanılamadı'; return None
        if response.status_code != 200:
            self.last_problem = f'Mapbox yer arama yanıtı {response.status_code}'; return None
        try:
            features = response.json().get('features') or []
            lon, lat = features[0]['geometry']['coordinates'][:2]
            lat, lon = float(lat), float(lon)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            self.last_problem = ''  # nothing found (or an unreadable answer)
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180): return None
        return round(lat, 5), round(lon, 5)


# Set by the app at start-up: () -> GeocodingProvider or None (no Mapbox key).
FACTORY = None
CACHE = None  # Path of the JSON answer cache (data/geocode_cache.json)
_LOCK = threading.Lock()


def _key(name):
    return ' '.join(str(name).casefold().split())


def _read():
    try: return json.loads(Path(CACHE).read_text(encoding='utf-8')) if CACHE else {}
    except (OSError, ValueError): return {}


def geocode(name):
    """(lat, lon) for a place name from Mapbox (cached), or None."""
    key = _key(name)
    if not key or len(key) > 100: return None
    with _LOCK:
        cached = _read()
        if key in cached:
            return tuple(cached[key]) if cached[key] else None
    try:
        provider = FACTORY() if FACTORY else None
    except Exception:
        provider = None
    if provider is None: return None
    found = provider.forward(str(name).strip())
    if found is None and provider.last_problem:  # a network/key problem is not cached: asked again next time
        LOG.info('geocoding result=failed reason=%s', provider.last_problem)
        return None
    with _LOCK:
        cached = _read(); cached[key] = list(found) if found else None
        if CACHE:
            try:
                Path(CACHE).parent.mkdir(parents=True, exist_ok=True)
                Path(CACHE).write_text(json.dumps(cached, ensure_ascii=False), encoding='utf-8')
            except OSError:
                pass
    return found
