"""Builds app/motion/places_world.json.gz, the offline place list used by the
map infographics. Run once by the developer (not by the app):

    pip install geonamescache babel
    python tools/build_places.py

Sources (open licences, see docs/LICENSES.md):
- GeoNames via the geonamescache package (MIT code; GeoNames data CC BY 4.0):
  cities with 15 000+ inhabitants and their other names (ancient names such
  as Byzantium or Hierosolyma are among them), countries (size, capital).
- Unicode CLDR via Babel (BSD code; CLDR data Unicode License): country and
  region names in German, Turkish, English, French and Spanish.
Ancient places, regions and seas come from app/motion/places_extra.py.
"""
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LANGS = ('en', 'de', 'tr', 'fr', 'es')
LATIN = re.compile(r"^[A-Za-zÀ-ɏḀ-ỿ’'`.\- ]+$")


def latin_names(names, limit):
    out, seen = [], set()
    for name in names:
        name = ' '.join(str(name).split())
        if not (3 <= len(name) <= 40) or not LATIN.match(name) or name.isupper() or name.casefold() in seen: continue
        seen.add(name.casefold()); out.append(name)
        if len(out) >= limit: break
    return out


def main():
    import geonamescache
    from babel import Locale
    cache = geonamescache.GeonamesCache(min_city_population=15000)
    cities, countries = cache.get_cities(), cache.get_countries()
    locales = {lang: Locale(lang).territories for lang in LANGS}
    capital = {}
    for city in cities.values():
        key = (city['countrycode'], city['name'])
        if key not in capital or city['population'] > capital[key]['population']: capital[key] = city
    places = []
    # Countries: names in five languages, pin at the capital, zoom from the area.
    for code, country in countries.items():
        names = [locales[lang].get(code) for lang in LANGS] + [country['name']]
        names = latin_names([n for n in names if n], 12)
        city = capital.get((code, country.get('capital', '')))
        if not city or not names: continue
        extent = max(30, round((country.get('areakm2') or 1000) ** .5))
        places.append([names[0], round(city['latitude'], 3), round(city['longitude'], 3), 'country', code, extent, 10**9, names[1:]])
    # Cities: the bigger ones carry their other (also ancient) names.
    for city in sorted(cities.values(), key=lambda c: -c['population']):
        others = latin_names(city.get('alternatenames') or [], 40 if city['population'] >= 100_000 else 6)
        names = latin_names([city['name']] + others, 41)
        if not names: continue
        country = city['countrycode']
        extent = 25 if city['population'] >= 1_000_000 else 12 if city['population'] >= 100_000 else 6
        places.append([names[0], round(city['latitude'], 3), round(city['longitude'], 3), 'city', country, extent, city['population'], names[1:]])
    target = ROOT / 'app' / 'motion' / 'places_world.json.gz'
    data = json.dumps({'source': 'GeoNames (CC BY 4.0, geonames.org) via geonamescache; Unicode CLDR via Babel',
                       'fields': ['name', 'lat', 'lon', 'kind', 'country_code', 'extent_km', 'population', 'other_names'],
                       'countries': {code: {lang: locales[lang].get(code, '') for lang in LANGS} for code in countries},
                       'places': places}, ensure_ascii=False, separators=(',', ':'))
    with gzip.open(target, 'wt', encoding='utf-8', compresslevel=9) as out:
        out.write(data)
    print(f'{len(places)} places → {target} ({target.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
