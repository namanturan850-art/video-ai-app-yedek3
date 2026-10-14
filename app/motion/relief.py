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


def highlight(picture, unit, view):
    """Red fill + bright glowing edge (a river valley: a corridor along the river)."""
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
    red = Image.new('RGB', picture.size, (222, 30, 36))
    picture = Image.composite(red, picture, shape.point(lambda v: int(v * .42)))  # the relief stays visible under the red
    picture = Image.composite(Image.new('RGB', picture.size, (255, 120, 90)), picture, glow.point(lambda v: min(255, v * 2)))
    return Image.composite(Image.new('RGB', picture.size, (255, 236, 220)), picture, edge.point(lambda v: 255 if v > 100 else 0))


def bezier(a, b, bend=.22, steps=60):
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    c = (mx - dy * bend, my + dx * bend)
    return [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1])
            for t in (i / steps for i in range(steps + 1))]


def font(size):
    from app.motion.templates import _font
    return _font('Montserrat.ttf', size, True)


def label(draw, text, x, y, size=58, anchor='mm'):
    f = font(size)
    draw.text((x, y), text, font=f, fill=(255, 255, 255), anchor=anchor, stroke_width=max(4, size // 9), stroke_fill=(20, 24, 30))


def plan(spec):
    """Everything the clip needs, resolved from the offline data."""
    d = spec['data']
    mode = d.get('mode', 'region')
    if mode == 'arrow':
        a, b = place(d['from']), place(d['to'])
        if not a or not b: raise ValueError('arrow places')
        bbox = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        return {'mode': mode, 'view': view_around(bbox, pad=1.9, minimum=2.5), 'arrow': [a, b], 'unit': None, 'title': d.get('title') or ''}
    unit = find(d['target'])
    if unit is None:
        p = place(d['target'])
        if not p: raise ValueError('area not found')
        unit = {'kind': 'point', 'name': p[2], 'polygons': [], 'lines': [], 'bbox': (p[0] - .3, p[1] - .3, p[0] + .3, p[1] + .3)}
    view = view_around(unit['bbox'], pad=1.7 if mode == 'region' else 1.4, minimum=1.5)
    title = d.get('title') or (d['target'] if unit['kind'] == 'river' else unit['name'])  # “Vallée du Rhône”, not “Rhône”
    return {'mode': mode, 'view': view, 'unit': unit, 'arrow': None, 'title': title}


def render(scene, output, ffmpeg):
    """The relief clip (local renderer). Camera: slow drift (region/arrow) or a
    slow zoom-in (zoom), all within the pre-drawn canvas."""
    element = next(e for e in scene['elements'] if e['type'] == 'relief')
    info = plan(element['props']['spec'])
    duration = scene['duration']; frames = max(1, round(duration * FPS))
    view = info['view']
    cx, cy = (view[0] + view[2]) / 2, (view[1] + view[3]) / 2
    hw, hh = (view[2] - view[0]) / 2 * MARGIN * (1.6 if info['mode'] == 'zoom' else 1), (view[3] - view[1]) / 2 * MARGIN * (1.6 if info['mode'] == 'zoom' else 1)
    canvas_view = (cx - hw, cy - hh, cx + hw, cy + hh)
    cw, ch = int(W * MARGIN * (1.6 if info['mode'] == 'zoom' else 1)), int(H * MARGIN * (1.6 if info['mode'] == 'zoom' else 1))
    base = terrain(canvas_view, cw, ch)
    if info['unit'] and (info['unit']['polygons'] or info['unit']['lines']): base = highlight(base, info['unit'], canvas_view)
    xy = projector(canvas_view, cw, ch)
    # Labels and the arrow are drawn on the canvas: they move with the map, readable from frame 0.
    overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    path = None
    if info['arrow']:
        (ax, ay, an), (bx, by, bn) = info['arrow']
        end = xy(bx, by)
        path = [q for q in bezier(xy(ax, ay), end) if math.dist(q, end) >= 34] or [xy(ax, ay), end]  # the tip stops at the dot
        down = end[1] >= xy(ax, ay)[1]
        for (x, y, n), first in (((ax, ay, an), True), ((bx, by, bn), False)):
            px, py = xy(x, y)
            draw.ellipse((px - 12, py - 12, px + 12, py + 12), fill=(255, 255, 255), outline=(20, 24, 30), width=4)
            above = down == first  # each name sits on the side the arrow does not use
            label(draw, n, px, py - 50 if above else py + 54, 54)
    elif info['unit']:
        w, s, e, n = info['unit']['bbox']
        px, py = xy((w + e) / 2, (s + n) / 2)
        if info['unit']['lines']:  # a valley: the label sits beside the middle of the river
            line = max(info['unit']['lines'], key=len); mx, my = line[len(line) // 2]
            px, py = xy(mx, my); px += 40
            label(draw, info['title'], px, py, 66, anchor='lm')
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
    drift = (cw - w) * .5 * (.35 + .3 * p) if info['mode'] != 'zoom' else (cw - w) / 2  # gentle sideways drift
    left, top = drift, (ch - h) / 2 - (ch - h) * .08 * (p - .5)
    image = base
    if path:
        k = max(2, int(len(path) * min(1., t / max(.6, duration * .45))))
        image = base.copy(); draw = ImageDraw.Draw(image)
        part = path[:k]
        draw.line([(x + 4, y + 5) for x, y in part], fill=(0, 0, 0, 120), width=14, joint='curve')
        draw.line(part, fill=(255, 255, 255, 255), width=12, joint='curve')
        (x1, y1), (x2, y2) = part[-2], part[-1]
        angle = math.atan2(y2 - y1, x2 - x1)
        tip = [(x2 + 30 * math.cos(angle), y2 + 30 * math.sin(angle)), (x2 + 26 * math.cos(angle + 2.4), y2 + 26 * math.sin(angle + 2.4)),
               (x2 + 26 * math.cos(angle - 2.4), y2 + 26 * math.sin(angle - 2.4))]
        draw.polygon(tip, fill=(255, 255, 255, 255))
    return image.convert('RGB').resize((W, H), Image.BICUBIC, box=(left, top, left + w, top + h))
