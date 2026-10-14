"""Builds app/motion/places_local.json.gz: towns, villages and populated
places that the main list (places_world.json.gz, 15 000+ inhabitants) lacks.
Used only when a map marker's place is not found in the main lists
(“Avranches”, “Pontorson”). Run once by the developer (not by the app):

    pip install geonamescache
    python tools/build_places_local.py [ne_10m_populated_places_simple.geojson]

Sources (open licences, see docs/LICENSES.md):
- GeoNames via the geonamescache package (MIT code; GeoNames data CC BY 4.0):
  cities1000 (places with 1 000+ inhabitants) below 15 000 inhabitants.
- Natural Earth 1:10m populated places (public domain), optional file argument
  (github.com/nvkelso/natural-earth-vector, geojson/ne_10m_populated_places_simple.geojson):
  added when no GeoNames place of that name lies within ~5 km.
"""
import gzip
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.build_places import latin_names  # noqa: E402


def main():
    import geonamescache
    from app.motion.places import plain
    cities = geonamescache.GeonamesCache(min_city_population=1000).get_cities()
    rows = []
    for city in sorted(cities.values(), key=lambda c: -c['population']):
        if city['population'] >= 15000: continue  # already in places_world.json.gz
        names = latin_names([city['name']] + list(city.get('alternatenames') or []), 3)
        if not names: continue
        rows.append([names[0], round(city['latitude'], 4), round(city['longitude'], 4), city['countrycode'], city['population'], names[1:]])
    added = 0
    if len(sys.argv) > 1:
        seen = {}
        for row in rows: seen.setdefault(plain(row[0]), []).append((row[1], row[2]))
        world = json.loads(gzip.decompress((ROOT / 'app' / 'motion' / 'places_world.json.gz').read_bytes()))
        for p in world['places']: seen.setdefault(plain(p[0]), []).append((p[1], p[2]))
        for feature in json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))['features']:
            p = feature['properties']
            name, lat, lon = p.get('name') or p.get('nameascii'), p.get('latitude'), p.get('longitude')
            if not name or lat is None or lon is None: continue
            if any(math.hypot(lat - a, (lon - b) * math.cos(math.radians(lat))) < .05 for a, b in seen.get(plain(name), [])): continue
            rows.append([name, round(lat, 4), round(lon, 4), p.get('iso_a2') or '', int(p.get('pop_max') or 0), []])
            added += 1
    target = ROOT / 'app' / 'motion' / 'places_local.json.gz'
    data = json.dumps({'source': 'GeoNames (CC BY 4.0, geonames.org) via geonamescache; Natural Earth populated places (public domain)',
                       'fields': ['name', 'lat', 'lon', 'country_code', 'population', 'other_names'], 'places': rows},
                      ensure_ascii=False, separators=(',', ':'))
    with gzip.open(target, 'wt', encoding='utf-8', compresslevel=9) as out:
        out.write(data)
    print(f'{len(rows)} places ({added} from Natural Earth) → {target} ({target.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
