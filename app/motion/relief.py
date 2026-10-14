"""Colour relief (hypsometric) map: [BÖLGE: Bretagne], [OK: Lyon > Marseille],
[YAKINLAŞ: Guyane].

Offline data shipped with the app (tools/build_relief_data.py builds them):
  relief_etopo10.npz  ETOPO1 elevation (NOAA, public domain) at 10 arc-minutes
  areas_10m.json.gz   Natural Earth 1:10m (public domain): countries, admin-1
                      units (départements, Länder, provinces, states…), their
                      regions (Bretagne, Lombardia…) and river lines

Land is coloured by height (green → yellow → brown → white peaks) with a
hill shade; the sea is one flat, clean blue. A named area is filled red with
a bright glowing edge; “Vallée du Rhône”-style names become a corridor along
the river. The camera drifts slowly (or zooms slowly for [YAKINLAŞ]); labels
are bold and fully visible from the first frame.
"""
from functools import lru_cache
import gzip
import json
import math
from pathlib import Path
import re
import subprocess
import unicodedata

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
W, H, FPS = 1920, 1080, 30
LAST_WARNING = ''  # the last satellite problem (Turkish), read once by the media job
MARGIN = 1.22  # the drawn canvas is larger than the frame: room for the camera
SEA = (38, 92, 140)
RAMP = [(0, (74, 132, 72)), (150, (110, 156, 84)), (400, (176, 186, 104)), (800, (214, 196, 122)),
        (1300, (186, 146, 92)), (2000, (148, 106, 70)), (3000, (128, 100, 86)), (4200, (236, 236, 236))]
PREFIXES = r'^(?:la |le |les |the )?(?:vallee (?:du |de la |de l |des |de )|valley of (?:the )?|val (?:de |d )|valle (?:del |de )|tal (?:der |des )?)'  # on folded text
SUFFIXES = r'(?: valley| vadisi| tal| river| nehri| fluss)$'


def fold(text):
    text = unicodedata.normalize('NFKD', str(text or '').casefold().replace('ı', 'i'))
    return ' '.join(re.sub(r'[^a-z0-9 ]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())


@lru_cache(maxsize=1)
def grid():
    return np.load(HERE / 'relief_etopo10.npz')['z'].astype(np.float32)  # 1081 rows 90N→90S, 2160 columns 180W→180E


@lru_cache(maxsize=1)
def areas():
    return json.loads(gzip.decompress((HERE / 'areas_10m.json.gz').read_bytes()))


def find(name):
    """The named country / region / admin-1 unit / river valley:
    {'kind', 'name', 'polygons' | 'lines', 'bbox'} or None."""
    wanted = fold(name)
    if not wanted: return None
    river = fold(re.sub(SUFFIXES, '', re.sub(PREFIXES, '', wanted)))
    valley = river != wanted
    for kind in (('river',) if valley else ()) + ('region', 'adm1', 'country') + (() if valley else ('river',)):
        for unit in areas():
            if unit['k'] != kind: continue
            names = [fold(n) for n in unit['n']]
            if (river if kind == 'river' else wanted) in names:
                return {'kind': kind, 'name': unit['n'][0], 'polygons': unit.get('p') or [], 'lines': unit.get('l') or [], 'bbox': unit['b']}
    return None


def search_name(name):
    """English stock-search words for a marker's area (“Brittany”, “Rhone valley”, “French Guiana”, “Marseille”), '' when unknown."""
    found = _search_name(name)
    try:
        from app.scripts.query_clean import place_english
        english = place_english(name)  # the place list knows exonyms the area list lacks (Bretagne → Brittany)
    except Exception:
        english = ''
    return english if english and (not found or fold(found) == fold(name)) else found


def _search_name(name):
    """English stock-search words for a marker's area (“Brittany”, “Rhone valley”, “French Guiana”), '' when unknown."""
    wanted = fold(name)
    river = fold(re.sub(SUFFIXES, '', re.sub(PREFIXES, '', wanted)))
    for unit in areas():
        names = [fold(n) for n in unit['n']]
        if (river if unit['k'] == 'river' else wanted) in names and (unit['k'] != 'river' or river != wanted):
            english = unit['n'][1] if len(unit['n']) > 1 else unit['n'][0]
            plain = ''.join(c for c in unicodedata.normalize('NFKD', english) if not unicodedata.combining(c))
            return f'{plain} valley' if unit['k'] == 'river' else plain
    unit = find(name)
    return '' if not unit else ''.join(c for c in unicodedata.normalize('NFKD', unit['name']) if not unicodedata.combining(c))


def place(name):
    """(lon, lat, label) of an area's centre or a place from the offline place list."""
    unit = find(name)
    if unit:
        w, s, e, n = unit['bbox']
        return ((w + e) / 2, (s + n) / 2, unit['name'])
    from app.motion.templates_extra import where
    found = where(name)
    return (found[2], found[1], found[0]) if found else None


def view_around(bbox, aspect=W / H, pad=1.6, minimum=1.2):
    """(lon0, lat0, lon1, lat1) of a 16:9 view showing the bbox with room around it."""
    w, s, e, n = bbox
    lat = (s + n) / 2
    k = max(.2, math.cos(math.radians(lat)))
    half_h = max((n - s) / 2 * pad, (e - w) / 2 * pad * k / aspect, minimum / 2)
    half_w = half_h * aspect / k
    cx = (w + e) / 2
    return (cx - half_w, lat - half_h, cx + half_w, lat + half_h)


def sample(view, width, height):
    """Bilinear elevation (m) for a width×height equirectangular raster of the view."""
    z = grid()
    lon0, lat0, lon1, lat1 = view
    lons = np.linspace(lon0, lon1, width); lats = np.linspace(lat1, lat0, height)
    cols = ((lons + 180) % 360) * 6; rows = (90 - lats) * 6  # grid nodes: row 0 = 90N, column 0 = 180W, 1/6° apart
    c0 = np.floor(cols).astype(int); r0 = np.clip(np.floor(rows).astype(int), 0, z.shape[0] - 2)
    fc = (cols - c0)[None, :]; fr = np.clip(rows - r0, 0, 1)[:, None]
    c0 %= z.shape[1]; c1 = (c0 + 1) % z.shape[1]
    a = z[r0][:, c0]; b = z[r0][:, c1]; c = z[r0 + 1][:, c0]; d = z[r0 + 1][:, c1]
    return (a * (1 - fc) + b * fc) * (1 - fr) + (c * (1 - fc) + d * fc) * fr


def projector(view, width, height):
    lon0, lat0, lon1, lat1 = view
    return lambda lon, lat: ((lon - lon0) / (lon1 - lon0) * width, (lat1 - lat) / (lat1 - lat0) * height)


def visible(bbox, view, slack=2.):
    return not (bbox[2] < view[0] - slack or bbox[0] > view[2] + slack or bbox[3] < view[1] - slack or bbox[1] > view[3] + slack)


def smooth(z, size):
    """Two box blurs (≈ Gaussian) of `size` pixels; numpy only."""
    if size < 3: return z
    for _ in range(2):
        for axis in (0, 1):
            c = np.cumsum(np.pad(z, [(size, size) if a == axis else (0, 0) for a in (0, 1)], mode='edge'), axis=axis)
            hi = np.take(c, np.arange(2 * size, c.shape[axis]), axis=axis); lo = np.take(c, np.arange(0, c.shape[axis] - 2 * size), axis=axis)
            z = ((hi - lo) / (2 * size))[:z.shape[0], :z.shape[1]] if axis == 0 else (hi - lo) / (2 * size)
    return z


def terrain(view, width, height):
    """RGB picture: land coloured by height + hill shade, flat sea, crisp coasts."""
    mask = Image.new('L', (width, height), 0)
    draw, xy = ImageDraw.Draw(mask), projector(view, width, height)
    for unit in areas():
        if unit['k'] == 'country' and visible(unit['b'], view):
            for ring in unit['p']: draw.polygon([xy(x, y) for x, y in ring], fill=255)
    land = np.asarray(mask, dtype=np.float32) / 255
    small = sample(view, max(64, width // 4), max(36, height // 4))  # the data are coarse: smooth, then enlarge
    z = np.asarray(Image.fromarray(small).resize((width, height), Image.BICUBIC), dtype=np.float32)
    cell = height / max(.01, (view[3] - view[1]) * 6)  # one 10' data cell in pixels
    z = smooth(np.maximum(z, 0), int(cell * .8))  # no visible data squares at regional scale
    heights = np.array([h for h, _ in RAMP], dtype=np.float32)
    colour = np.stack([np.interp(z, heights, [c[i] for _, c in RAMP]) for i in range(3)], axis=-1)
    km_per_px = (view[3] - view[1]) * 111 / height
    gy, gx = np.gradient(z / max(.05, km_per_px * 1000) * 6)  # vertical exaggeration grows with the view's scale
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(315), math.radians(45)
    shade = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    colour *= (.62 + .5 * np.clip(shade, 0, 1))[..., None]
    sea = np.array(SEA, dtype=np.float32)
    out = colour * land[..., None] + sea * (1 - land[..., None])
    picture = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    lines = ImageDraw.Draw(picture, 'RGBA')
    for unit in areas():  # admin-1 lines thin, country borders stronger
        if unit['k'] in ('adm1', 'country') and visible(unit['b'], view, 0.):
            fill, size = ((255, 255, 255, 70), 1) if unit['k'] == 'adm1' else ((255, 255, 255, 170), 3)
            for ring in unit['p']: lines.line([xy(x, y) for x, y in ring], fill=fill, width=size, joint='curve')
    return picture


RED = {'fill': (222, 30, 36), 'alpha': .42, 'glow': (255, 120, 90), 'edge': (255, 236, 220)}
BLUE = {'fill': (52, 146, 255), 'alpha': .55, 'glow': (90, 175, 255), 'edge': (205, 232, 255)}       # dark theme: the selected area
ORANGE = {'fill': (255, 138, 42), 'alpha': .42, 'glow': (255, 170, 90), 'edge': (255, 222, 186)}    # dark theme: the compared area
DARK = {'sea': (10, 18, 34), 'land': (26, 40, 64), 'border': (74, 96, 134), 'adm1': (44, 61, 90)}


def dark_map(view, width, height):
    """Flat vector map in dark navy (Natural Earth): land, country and admin-1 lines; no relief."""
    picture = Image.new('RGB', (width, height), DARK['sea'])
    draw, xy = ImageDraw.Draw(picture), projector(view, width, height)
    for unit in areas():
        if unit['k'] == 'country' and visible(unit['b'], view):
            for ring in unit['p']: draw.polygon([xy(x, y) for x, y in ring], fill=DARK['land'])
    for unit in areas():
        if unit['k'] in ('adm1', 'country') and visible(unit['b'], view, 0.):
            colour, size = (DARK['adm1'], 1) if unit['k'] == 'adm1' else (DARK['border'], 2)
            for ring in unit['p']: draw.line([xy(x, y) for x, y in ring], fill=colour, width=size, joint='curve')
    return picture


def area_km2(unit):
    """Area of an area's polygons (km², local equal-area approximation)."""
    total = 0.
    for ring in unit['polygons']:
        lat0 = sum(y for _, y in ring) / len(ring); k = math.cos(math.radians(lat0)) * 111.32
        pts = [(x * k, y * 110.57) for x, y in ring]
        total += abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2
    return total


def centre(unit):
    w, s, e, n = unit['bbox']
    return (w + e) / 2, (s + n) / 2


def moved_onto(unit, target):
    """The unit's shape at the same scale, centred on the target (for the size comparison overlay)."""
    (bx, by), (ax, ay) = centre(unit), centre(target)
    kb, ka = math.cos(math.radians(by)), math.cos(math.radians(ay))
    move = lambda x, y: (ax + (x - bx) * kb / ka, ay + (y - by))
    polygons = [[move(x, y) for x, y in ring] for ring in unit['polygons']]
    xs = [x for r in polygons for x, _ in r]; ys = [y for r in polygons for _, y in r]
    return {**unit, 'polygons': polygons, 'lines': [], 'bbox': (min(xs), min(ys), max(xs), max(ys))}


def highlight(picture, unit, view, colours=RED):
    """Coloured fill + bright glowing edge (a river valley: a corridor along the river)."""
    width, height = picture.size
    xy = projector(view, width, height)
    shape = Image.new('L', picture.size, 0)
    draw = ImageDraw.Draw(shape)
    if unit['polygons']:
        for ring in unit['polygons']: draw.polygon([xy(x, y) for x, y in ring], fill=255)
    for line in unit['lines']:
        draw.line([xy(x, y) for x, y in line], fill=255, width=max(18, int(width * .022)), joint='curve')
    if unit['lines']: shape = shape.filter(ImageFilter.GaussianBlur(6)).point(lambda v: 255 if v > 90 else 0)
    edge = shape.filter(ImageFilter.MaxFilter(9)).point(lambda v: v)
    edge = Image.fromarray(np.clip(np.asarray(edge, np.int16) - np.asarray(shape.filter(ImageFilter.MinFilter(5)), np.int16), 0, 255).astype(np.uint8))
    glow = edge.filter(ImageFilter.GaussianBlur(10))
    fill = Image.new('RGB', picture.size, colours['fill'])
    picture = Image.composite(fill, picture, shape.point(lambda v: int(v * colours['alpha'])))  # what is underneath stays visible
    picture = Image.composite(Image.new('RGB', picture.size, colours['glow']), picture, glow.point(lambda v: min(255, v * 2)))
    return Image.composite(Image.new('RGB', picture.size, colours['edge']), picture, edge.point(lambda v: 255 if v > 100 else 0))


def bezier(a, b, bend=.22, steps=60):
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    c = (mx - dy * bend, my + dx * bend)
    return [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1])
            for t in (i / steps for i in range(steps + 1))]


def font(size):
    from app.motion.templates import _font
    return _font('Montserrat.ttf', size, True)


def label_box(draw, text, x, y, size=48, anchor='mm'):
    """Dark theme: dark text in a white box."""
    f = font(size)
    l, t, r, b = draw.textbbox((x, y), text, font=f, anchor=anchor)
    draw.rounded_rectangle((l - 22, t - 14, r + 22, b + 14), radius=10, fill=(250, 251, 253))
    draw.text((x, y), text, font=f, fill=(12, 22, 40), anchor=anchor)


def pin(draw, x, y, colour=(255, 255, 255)):
    draw.ellipse((x - 16, y - 58, x + 16, y - 26), fill=colour, outline=(10, 18, 34), width=3)
    draw.polygon([(x - 12, y - 36), (x + 12, y - 36), (x, y)], fill=colour)
    draw.ellipse((x - 6, y - 48, x + 6, y - 36), fill=(10, 18, 34))


def legend(image, entries):
    """Bottom-left names with their colours (fixed on screen, always readable)."""
    draw = ImageDraw.Draw(image)
    f = font(40)
    y = H - 80 - 64 * (len(entries) - 1)
    for colour, text in entries:
        width = draw.textlength(text, font=f)
        draw.rounded_rectangle((60, y - 30, 60 + width + 104, y + 30), radius=10, fill=(250, 251, 253))
        draw.rounded_rectangle((78, y - 14, 106, y + 14), radius=4, fill=colour)
        draw.text((122, y), text, font=f, fill=(12, 22, 40), anchor='lm')
        y += 64


def figure_box(image, text, sub=''):
    """Top-right number box (“6.640 MİL”, “2,5×”), fixed on screen."""
    draw = ImageDraw.Draw(image)
    f, g = font(64), font(28)
    width = min(W - 140, max(draw.textlength(text, font=f), draw.textlength(sub, font=g) if sub else 0) + 64)
    x1, y0 = W - 70, 64
    x0, y1 = x1 - width, y0 + (150 if sub else 112)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=12, fill=(10, 18, 34), outline=(61, 155, 255), width=4)
    draw.text(((x0 + x1) / 2, y0 + 58), text, font=f, fill=(255, 255, 255), anchor='mm')
    if sub: draw.text(((x0 + x1) / 2, y0 + 118), sub, font=g, fill=(170, 200, 240), anchor='mm')


def label(draw, text, x, y, size=58, anchor='mm'):
    f = font(size)
    draw.text((x, y), text, font=f, fill=(255, 255, 255), anchor=anchor, stroke_width=max(4, size // 9), stroke_fill=(20, 24, 30))


def plan(spec):
    """Everything the clip needs, resolved from the offline data."""
    d = spec['data']
    mode = d.get('mode', 'region')
    figure = str(d.get('figure') or '')[:24]
    if mode == 'compare':
        a, b = find(d['target']), find(d['other'])
        if not a or not b or not a['polygons'] or not b['polygons']: raise ValueError('compare areas')
        over = moved_onto(b, a)
        box = (min(a['bbox'][0], over['bbox'][0]), min(a['bbox'][1], over['bbox'][1]), max(a['bbox'][2], over['bbox'][2]), max(a['bbox'][3], over['bbox'][3]))
        ratio = area_km2(a) / max(1e-6, area_km2(b))
        big = ratio if ratio >= 1 else 1 / ratio
        shown = f'{big:.1f}×'.replace('.', ',') if d.get('language', 'tr') != 'en' else f'{big:.1f}×'
        return {'mode': mode, 'view': view_around(box, pad=1.5, minimum=1.5), 'unit': a, 'other': over, 'arrow': None, 'pair': (a, b),
                'title': d.get('title') or d['target'], 'other_title': d['other'], 'figure': figure or shown}  # the names as the owner wrote them (Belgique)
    if mode == 'arrow':
        if d.get('stops'):  # [ROTA: A > B > C] on the satellite style: the route's own places, in order
            points = [(float(p['lon']), float(p['lat']), str(p['name'])[:40]) for p in d['stops']]
        else:
            points = [place(d['from'])] + [place(v) for v in d.get('via') or []] + [place(d['to'])]
        if len(points) < 2 or not all(points): raise ValueError('arrow places')
        from app.motion.templates_extra import near_each_other  # [OK: Paris > Brest]: Brest in France
        points = [(p['lon'], p['lat'], p['name']) for p in near_each_other([{'name': n, 'lat': y, 'lon': x} for x, y, n in points])]
        bbox = (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))
        return {'mode': mode, 'view': view_around(bbox, pad=1.9, minimum=2.5), 'arrow': points, 'unit': None, 'title': d.get('title') or '', 'figure': figure}
    unit = find(d['target'])
    if unit is None:
        p = place(d['target'])
        if not p: raise ValueError('area not found')
        unit = {'kind': 'point', 'name': p[2], 'polygons': [], 'lines': [], 'bbox': (p[0] - .3, p[1] - .3, p[0] + .3, p[1] + .3)}
    view = view_around(unit['bbox'], pad=1.7 if mode == 'region' else 1.4, minimum=1.5)
    title = d.get('title') or (d['target'] if unit['kind'] == 'river' else unit['name'])  # “Vallée du Rhône”, not “Rhône”
    return {'mode': mode, 'view': view, 'unit': unit, 'arrow': None, 'title': title, 'figure': figure}


def km_shape(unit):
    """The unit's polygons in km around its own centre (x east, y north)."""
    cx, cy = centre(unit); k = math.cos(math.radians(cy)) * 111.32
    return [[((x - cx) * k, (y - cy) * 110.57) for x, y in ring] for ring in unit['polygons']]


def side_by_side(info, width, height):
    """[KARŞILAŞTIR]: both areas next to each other at the same scale (km), blue and orange,
    each name in a white box under its shape, on a plain dark ground with a faint grid."""
    a, b = (km_shape(u) for u in info['pair'])
    span = lambda rings, i: (min(p[i] for r in rings for p in r), max(p[i] for r in rings for p in r))
    (ax0, ax1), (ay0, ay1), (bx0, bx1), (by0, by1) = span(a, 0), span(a, 1), span(b, 0), span(b, 1)
    gap = max(ax1 - ax0, bx1 - bx0) * .18
    total_w = (ax1 - ax0) + gap + (bx1 - bx0); total_h = max(ay1 - ay0, by1 - by0)
    # the pair fills about 70 % of the visible frame width / 60 % of its height (room for the names and the number box)
    scale = min(W * .70 / total_w, H * .58 / total_h)
    km_w, km_h = width / scale, height / scale
    left = -total_w / 2
    move = lambda rings, dx, dy: [[(x + dx, y + dy) for x, y in r] for r in rings]
    a = move(a, left - ax0, -(ay0 + ay1) / 2 + total_h * .05); b = move(b, left + (ax1 - ax0) + gap - bx0, -(by0 + by1) / 2 + total_h * .05)
    view = (-km_w / 2, -km_h / 2, km_w / 2, km_h / 2)
    picture = Image.new('RGB', (width, height), DARK['sea'])
    draw = ImageDraw.Draw(picture)
    step = max(40, int(scale * 100))  # a faint 100 km grid
    for x in range(width // 2 % step, width, step): draw.line([(x, 0), (x, height)], fill=(20, 32, 54), width=1)
    for y in range(height // 2 % step, height, step): draw.line([(0, y), (width, y)], fill=(20, 32, 54), width=1)
    picture = highlight(picture, {'polygons': a, 'lines': []}, view, BLUE)
    picture = highlight(picture, {'polygons': b, 'lines': []}, view, ORANGE)
    xy = projector(view, width, height)
    draw = ImageDraw.Draw(picture)
    for rings, name in ((a, info['title']), (b, info['other_title'])):
        xs = [p[0] for r in rings for p in r]; ys = [p[1] for r in rings for p in r]
        x, y = xy((min(xs) + max(xs)) / 2, min(ys))
        label_box(draw, name, x, y + 56, 46)
    return picture


def render(scene, output, ffmpeg):
    """The relief clip (local renderer). Camera: slow drift (region/arrow) or a
    slow zoom-in (zoom), all within the pre-drawn canvas."""
    element = next(e for e in scene['elements'] if e['type'] == 'relief')
    info = plan(element['props']['spec'])
    theme = element['props'].get('theme')
    info['lang'] = element['props'].get('lang', 'en')
    sat = theme == 'satellite' and info['mode'] != 'compare'
    dark = theme == 'dark' or info['mode'] == 'compare' or sat  # a size comparison is always on the plain dark map
    info['dark'] = dark
    duration = scene['duration']; frames = max(1, round(duration * FPS))
    view = info['view']
    cx, cy = (view[0] + view[2]) / 2, (view[1] + view[3]) / 2
    hw, hh = (view[2] - view[0]) / 2 * MARGIN * (1.6 if info['mode'] == 'zoom' else 1), (view[3] - view[1]) / 2 * MARGIN * (1.6 if info['mode'] == 'zoom' else 1)
    canvas_view = (cx - hw, cy - hh, cx + hw, cy + hh)
    cw, ch = int(W * MARGIN * (1.6 if info['mode'] == 'zoom' else 1)), int(H * MARGIN * (1.6 if info['mode'] == 'zoom' else 1))
    if info['mode'] == 'compare':  # side by side at the same scale on a plain dark ground: neither fill hides the other
        base = side_by_side(info, cw, ch)
    else:
        base = None
        if sat:  # satellite tiles (SatelliteProvider); any problem: the dark map, with a Turkish warning
            from app.motion import satellite_map
            from app.providers.satellite import SatelliteError
            try:
                base, source_z, info['credit'] = satellite_map.base(canvas_view, cw, ch)
                info['satellite'] = True
                if info['unit']:
                    w, s_, e, n = info['unit']['bbox']
                    info['inset'] = satellite_map.closer(source_z, (w + e) / 2, (s_ + n) / 2)
                elif info['arrow']:
                    info['inset'] = satellite_map.closer(source_z, info['arrow'][-1][0], info['arrow'][-1][1])
            except SatelliteError as error:
                global LAST_WARNING
                LAST_WARNING = str(error)
                base = None
        if base is None:
            base = dark_map(canvas_view, cw, ch) if dark else terrain(canvas_view, cw, ch)
            if info['unit'] and (info['unit']['polygons'] or info['unit']['lines']): base = highlight(base, info['unit'], canvas_view, BLUE if dark else RED)
        elif info['unit'] and (info['unit']['polygons'] or info['unit']['lines']):  # [BÖLGE] on satellite: red/white hatched oval
            xy0 = projector(canvas_view, cw, ch)
            w, s_, e, n = info['unit']['bbox']; (l, t_), (r, b) = xy0(w, n), xy0(e, s_)
            base = satellite_map.hatched_oval(base, (l, t_, r, b))
    info['canvas_view'] = canvas_view
    xy = projector(canvas_view, cw, ch)
    # Labels and the arrow are drawn on the canvas: they move with the map, readable from frame 0.
    overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    path = None
    if info['arrow']:
        stops = info['arrow']  # two places ([OK]) or a whole route ([ROTA] on satellite)
        path = []
        for (ax, ay, _), (bx, by, _) in zip(stops, stops[1:]):
            path += bezier(xy(ax, ay), xy(bx, by))[(1 if path else 0):]
        end = xy(stops[-1][0], stops[-1][1])
        while len(path) > 2 and math.dist(path[-1], end) < 34: path.pop()  # the tip stops at the dot
        down = end[1] >= xy(stops[0][0], stops[0][1])[1]
        for i, (x, y, n) in enumerate(stops):
            px, py = xy(x, y)
            first = i == 0 if len(stops) == 2 else i % 2 == 0
            above = down == first  # each name sits on the side the arrow does not use
            if info.get('satellite'):
                draw.ellipse((px - 14, py - 14, px + 14, py + 14), fill=(255, 214, 10), outline=(255, 255, 255), width=5)
                label_box(draw, n, px, py - 70 if above else py + 50, 44)
            elif dark:
                pin(draw, px, py)
                label_box(draw, n, px, py - 100 if above else py + 50, 44)
            else:
                draw.ellipse((px - 12, py - 12, px + 12, py + 12), fill=(255, 255, 255), outline=(20, 24, 30), width=4)
                label(draw, n, px, py - 50 if above else py + 54, 54)
    elif info['unit']:
        w, s, e, n = info['unit']['bbox']
        px, py = xy((w + e) / 2, (s + n) / 2)
        if info['unit']['lines']:  # a valley: the label sits beside the middle of the river
            line = max(info['unit']['lines'], key=len); mx, my = line[len(line) // 2]
            px, py = xy(mx, my); px += 40
            label(draw, info['title'], px, py, 66, anchor='lm')
        elif info['mode'] == 'compare':
            pass  # names are in the on-screen legend (always inside the frame)
        elif dark:
            label_box(draw, info['title'], px, py, 50)
            if info['mode'] == 'zoom': pin(draw, px, py - 60)
        else:
            label(draw, info['title'], px, py, 66)
    base = Image.alpha_composite(base.convert('RGBA'), overlay)
    command = [ffmpeg, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
               '-frames:v', str(frames), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, shell=False)
    try:
        for i in range(frames):
            process.stdin.write(frame(base, info, i / FPS, duration, path).tobytes())
        process.stdin.close()
        error = process.stderr.read()
        if process.wait(timeout=600): raise RuntimeError(error.decode('utf-8', 'replace')[-300:] or 'ffmpeg failed')
    finally:
        if process.poll() is None: process.kill()
    return frames


def ease(t):
    return t * t * (3 - 2 * t)


def frame(base, info, t, duration, path):
    """Crop of the canvas for time t (+ the arrow drawn so far)."""
    cw, ch = base.size
    p = ease(min(1., t / max(.1, duration)))
    if info['mode'] == 'zoom':
        scale = 1.6 - .6 * p  # the crop shrinks: a slow zoom-in to the area
    else:
        scale = 1.0
    w, h = cw / MARGIN / (1.6 if info['mode'] == 'zoom' else 1) * scale, ch / MARGIN / (1.6 if info['mode'] == 'zoom' else 1) * scale
    drift = (cw - w) * .5 * (.35 + .3 * p) if info['mode'] not in ('zoom', 'compare') else (cw - w) / 2  # gentle sideways drift (compare: still)
    left, top = drift, (ch - h) / 2 - ((ch - h) * .08 * (p - .5) if info['mode'] != 'compare' else 0)
    image = base
    if path:
        k = max(2, int(len(path) * min(1., t / max(.6, duration * .45))))
        image = base.copy(); draw = ImageDraw.Draw(image)
        part = path[:k]
        if info.get('satellite'):  # thick yellow wavy line with a white edge
            from app.motion.satellite_map import arrow as yellow_arrow, wavy
            yellow_arrow(draw, wavy(part))
            part = None
        elif info.get('dark'):  # dashed line
            for i in range(0, len(part) - 1, 2):
                draw.line(part[i:i + 2], fill=(255, 255, 255, 255), width=8)
        else:
            draw.line([(x + 4, y + 5) for x, y in part], fill=(0, 0, 0, 120), width=14, joint='curve')
            draw.line(part, fill=(255, 255, 255, 255), width=12, joint='curve')
        if part:
            (x1, y1), (x2, y2) = part[-2], part[-1]
            angle = math.atan2(y2 - y1, x2 - x1)
            tip = [(x2 + 30 * math.cos(angle), y2 + 30 * math.sin(angle)), (x2 + 26 * math.cos(angle + 2.4), y2 + 26 * math.sin(angle + 2.4)),
                   (x2 + 26 * math.cos(angle - 2.4), y2 + 26 * math.sin(angle - 2.4))]
            draw.polygon(tip, fill=(255, 255, 255, 255))
    out = image.convert('RGB').resize((W, H), Image.BICUBIC, box=(left, top, left + w, top + h))
    if info.get('satellite'):  # badge + dots, scale bar + big number, magnifier, ŞEMATİK note, © Mapbox
        from app.motion import satellite_map
        crop_view = (info['canvas_view'][0] + left / cw * (info['canvas_view'][2] - info['canvas_view'][0]), 0,
                     info['canvas_view'][0] + (left + w) / cw * (info['canvas_view'][2] - info['canvas_view'][0]), 0)
        crop_view = (crop_view[0], info['view'][1], crop_view[2], info['view'][3])
        satellite_map.inset(out, info.get('inset'))
        satellite_map.overlays(out, info, t, duration, crop_view, font)
    elif info.get('figure'): figure_box(out, info['figure'].upper(), f'{info["title"]} / {info["other_title"]}' if info.get('other') else '')

    return out
