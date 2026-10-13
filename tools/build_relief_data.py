"""Builds the offline data of the relief map template (run once by a developer;
the outputs are committed, the app never downloads anything):

  app/motion/relief_etopo10.npz   ETOPO1 (NOAA, public domain) at 10 arc-minutes,
                                  via pyvista/vtk-data ETOPO_10min_Ice.vtp
  app/motion/areas_10m.json.gz    Natural Earth 1:10m (public domain): countries,
                                  admin-1 units, their regions, river lines

Usage: python tools/build_relief_data.py <folder with the downloads>
"""
import base64, gzip, json, math, sys, unicodedata, zlib
from pathlib import Path

import numpy as np
from shapely.geometry import shape, mapping, MultiPolygon, Polygon
from shapely.ops import unary_union

SRC = Path(sys.argv[1])
OUT = Path(__file__).resolve().parent.parent / 'app' / 'motion'


def etopo():
    raw = (SRC / 'etopo10.vtp').read_bytes()
    data = raw[raw.index(b'_', raw.index(b'<AppendedData')) + 1:]
    b64 = lambda n: math.ceil(n / 3) * 4
    n = int(np.frombuffer(base64.b64decode(data[:16]), np.uint32)[0])
    head = np.frombuffer(base64.b64decode(data[:b64(4 * (3 + n))]), np.uint32)
    body = base64.b64decode(data[b64(4 * (3 + n)):b64(4 * (3 + n)) + b64(int(head[3:].sum()))])
    out, p = b'', 0
    for c in head[3:]: out += zlib.decompress(body[p:p + int(c)]); p += int(c)
    grid = np.frombuffer(out, np.float32).reshape(1081, 2161)[:, :2160]  # rows 90N→90S, columns 0→360E
    grid = np.roll(grid, 1080, axis=1)  # columns 180W→180E
    np.savez_compressed(OUT / 'relief_etopo10.npz', z=np.round(grid).astype(np.int16))


def rings(geom, tol):
    geom = geom.simplify(tol, preserve_topology=True)
    polys = [geom] if isinstance(geom, Polygon) else list(getattr(geom, 'geoms', []))
    return [[[round(x, 3), round(y, 3)] for x, y in p.exterior.coords] for p in polys if p.area > tol * tol * 4]


def names(p, *keys):
    out = []
    for k in keys:
        v = p.get(k)
        if isinstance(v, str) and v.strip() and v not in out: out.append(v.strip())
    return out


def areas():
    units = []
    countries = json.loads((SRC / 'ne_10m_admin_0_countries.geojson').read_text())
    for f in countries['features']:
        p = f['properties']; g = shape(f['geometry'])
        units.append({'k': 'country', 'n': names(p, 'NAME', 'NAME_EN', 'NAME_FR', 'NAME_DE', 'NAME_TR', 'NAME_ES', 'NAME_IT', 'ADMIN', 'NAME_LONG'),
                      'c': p.get('ADM0_A3'), 'p': rings(g, .02), 'b': [round(x, 3) for x in g.bounds]})
    adm1 = json.loads((SRC / 'ne_10m_admin_1_states_provinces.geojson').read_text())
    groups = {}
    for f in adm1['features']:
        p = f['properties']; g = shape(f['geometry'])
        if not g.is_valid: g = g.buffer(0)
        units.append({'k': 'adm1', 'n': names(p, 'name', 'name_en', 'name_fr', 'name_de', 'name_tr', 'name_es', 'name_it', 'gn_name', 'woe_name', 'name_alt'),
                      'c': p.get('adm0_a3'), 'r': p.get('region') or '', 'p': rings(g, .008), 'b': [round(x, 3) for x in g.bounds]})
        if p.get('region') and p['region'] != p.get('name'): groups.setdefault((p['adm0_a3'], p['region']), []).append(g)
    for (country, region), parts in groups.items():
        g = unary_union([x.buffer(0) for x in parts])
        units.append({'k': 'region', 'n': [region], 'c': country, 'p': rings(g, .008), 'b': [round(x, 3) for x in g.bounds]})
    rivers = json.loads((SRC / 'ne_10m_rivers_lake_centerlines.geojson').read_text())
    lines = {}
    for f in rivers['features']:
        p = f['properties']
        key = p.get('name') or p.get('name_en')
        if not key or not f['geometry']: continue
        g = shape(f['geometry']).simplify(.01)
        parts = [g] if g.geom_type == 'LineString' else list(g.geoms)
        entry = lines.setdefault(key, {'k': 'river', 'n': names(p, 'name', 'name_en', 'name_fr', 'name_de', 'name_tr', 'name_es', 'name_it'), 'l': []})
        entry['l'] += [[[round(x, 3), round(y, 3)] for x, y in part.coords] for part in parts]
    for entry in lines.values():
        xs = [x for line in entry['l'] for x, _ in line]; ys = [y for line in entry['l'] for _, y in line]
        entry['b'] = [min(xs), min(ys), max(xs), max(ys)]
        units.append(entry)
    (OUT / 'areas_10m.json.gz').write_bytes(gzip.compress(json.dumps(units, ensure_ascii=False, separators=(',', ':')).encode(), 9))


if __name__ == '__main__':
    etopo(); areas()
