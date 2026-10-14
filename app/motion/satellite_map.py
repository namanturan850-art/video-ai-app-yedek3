"""Harita stili → Uydu görüntüsü: satellite tiles (SatelliteProvider) stitched
into the map canvas, plus this style's own marks:

  [OK]     a thick yellow wavy line with a white edge
  [BÖLGE]  a red-and-white diagonally hatched oval around the area
  badge    top left: the area's name + progress dots
  figure   a scale bar + a big number (“| 27.208 km²” in the marker)
  inset    a small blue-ringed magnifier (a closer tile of the target)
  note     bottom centre: “ŞEMATİK · SIMULATED” in the video's language
  credit   bottom right: “© Mapbox”

Any provider problem raises SatelliteError (Turkish message); the caller then
draws the offline dark map — the job never stops.
"""
from io import BytesIO
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.providers.satellite import TILE, SatelliteError, provider

W, H = 1920, 1080
MAX_TILES = 48
NOTE = {'tr': 'ŞEMATİK', 'de': 'SCHEMATISCH', 'en': 'SIMULATED', 'fr': 'SCHÉMATIQUE', 'es': 'ESQUEMÁTICO'}
YELLOW, RED, BLUE = (255, 214, 10), (226, 32, 40), (64, 156, 255)


def merc_y(lat):
    lat = max(-85.05, min(85.05, lat))
    return (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2  # 0 (north) … 1 (south)


def zoom_for(view, width):
    span = max(1e-6, view[2] - view[0])
    z = math.ceil(math.log2(max(1., width * 360 / (span * TILE))))
    return max(1, min(15, z))


def mosaic(view, width, height, source):
    """Equirectangular width×height picture of the view from Web-Mercator tiles."""
    lon0, lat0, lon1, lat1 = view
    z = zoom_for(view, width)
    while True:
        n = 2 ** z
        tx0, tx1 = int((lon0 + 180) / 360 * n), int((lon1 + 180) / 360 * n)
        ty0, ty1 = int(merc_y(lat1) * n), int(merc_y(lat0) * n)
        if (tx1 - tx0 + 1) * (ty1 - ty0 + 1) <= MAX_TILES or z <= 1: break
        z -= 1
    sheet = Image.new('RGB', ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE))
    for ty in range(max(0, ty0), min(n - 1, ty1) + 1):
        for tx in range(tx0, tx1 + 1):
            data = source.tile(z, tx % n, ty)
            try: tile = Image.open(BytesIO(data)).convert('RGB').resize((TILE, TILE))
            except Exception: raise SatelliteError('invalid_response', 'Mapbox karosu okunamadı; uydu yerine çizilmiş harita kullanıldı.') from None
            sheet.paste(tile, ((tx - tx0) * TILE, (ty - ty0) * TILE))
    pixels = np.asarray(sheet)
    lons = np.linspace(lon0, lon1, width); lats = np.linspace(lat1, lat0, height)
    xs = np.clip(((lons + 180) / 360 * n - tx0) * TILE, 0, pixels.shape[1] - 1).astype(int)
    ys = np.clip((np.array([merc_y(v) for v in lats]) * n - ty0) * TILE, 0, pixels.shape[0] - 1).astype(int)
    return Image.fromarray(pixels[ys][:, xs]), z


def base(view, width, height):
    """(picture, inset source, attribution) or SatelliteError."""
    source = provider()
    picture, z = mosaic(view, width, height, source)
    return picture.filter(ImageFilter.UnsharpMask(2, 60, 3)), (source, z), getattr(source, 'attribution', '')


def hatched_oval(picture, box):
    """[BÖLGE]: red/white diagonal stripes inside an oval + a red and a white ring."""
    l, t, r, b = box
    pad = .04 * max(r - l, b - t)
    box = (l - pad, t - pad, r + pad, b + pad)
    mask = Image.new('L', picture.size, 0); ImageDraw.Draw(mask).ellipse(box, fill=120)
    stripes = Image.new('RGB', picture.size, (255, 255, 255)); draw = ImageDraw.Draw(stripes)
    for x in range(-picture.size[1], picture.size[0], 36):
        draw.line([(x, picture.size[1]), (x + picture.size[1], 0)], fill=RED, width=18)
    picture = Image.composite(stripes, picture, mask)
    draw = ImageDraw.Draw(picture)
    draw.ellipse(box, outline=(255, 255, 255), width=12)
    draw.ellipse((box[0] + 6, box[1] + 6, box[2] - 6, box[3] - 6), outline=RED, width=6)
    return picture


def wavy(path, amplitude=10., waves=6):
    """The path with a gentle sideways wave (for the [OK] line)."""
    out = []
    for i, (x, y) in enumerate(path):
        a, b = path[max(0, i - 1)], path[min(len(path) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]; length = math.hypot(dx, dy) or 1
        k = amplitude * math.sin(i / max(1, len(path) - 1) * waves * 2 * math.pi)
        out.append((x - dy / length * k, y + dx / length * k))
    return out


def arrow(draw, part):
    """Thick yellow line with a white edge and an arrow head."""
    draw.line(part, fill=(255, 255, 255, 255), width=22, joint='curve')
    draw.line(part, fill=YELLOW + (255,), width=12, joint='curve')
    (x1, y1), (x2, y2) = part[-2], part[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    head = [(x2 + 40 * math.cos(angle), y2 + 40 * math.sin(angle)), (x2 + 32 * math.cos(angle + 2.5), y2 + 32 * math.sin(angle + 2.5)),
            (x2 + 32 * math.cos(angle - 2.5), y2 + 32 * math.sin(angle - 2.5))]
    draw.polygon(head, fill=YELLOW + (255,), outline=(255, 255, 255, 255), width=4)


def km_per_pixel(view, width):
    lat = (view[1] + view[3]) / 2
    return (view[2] - view[0]) * 111.32 * math.cos(math.radians(lat)) / width


def nice(km):
    for value in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if value >= km: return value
    return 5000


def overlays(image, info, t, duration, crop_view, font):
    """Marks fixed on screen: badge + dots, scale bar + number, inset, note, credit."""
    draw = ImageDraw.Draw(image, 'RGBA')
    # badge + progress dots (top left)
    title = (info.get('title') or (f'{info["arrow"][0][2]} → {info["arrow"][-1][2]}' if info.get('arrow') else '')).upper()[:32]
    f = font(34)
    width = draw.textlength(title, font=f) + 60
    draw.rounded_rectangle((50, 46, 50 + width, 106), radius=8, fill=(10, 16, 26, 210))
    draw.text((80, 76), title, font=f, fill=(255, 255, 255), anchor='lm')
    dots, done = 5, 1 + int(min(.999, t / max(.1, duration)) * 5)
    for i in range(dots):
        x = 64 + i * 26
        draw.ellipse((x - 7, 124 - 7, x + 7, 124 + 7), fill=(255, 255, 255, 255) if i < done else (255, 255, 255, 80))
    # scale bar + big number (bottom left); a tilted picture has no single scale: number only
    y = H - 120
    if not info.get('oblique'):
        kmpp = km_per_pixel(crop_view, W)
        length_km = nice(kmpp * 260); length_px = length_km / max(1e-9, kmpp)
        draw.rectangle((60, y, 60 + length_px, y + 10), fill=(255, 255, 255, 255))
        draw.rectangle((60, y, 60 + length_px / 2, y + 10), fill=(20, 20, 20, 255))
        draw.text((60, y - 12), f'{length_km:g} km', font=font(30), fill=(255, 255, 255), anchor='ls', stroke_width=3, stroke_fill=(0, 0, 0))
    else:
        y += 60
    if info.get('figure'):
        draw.text((60, y - 60), info['figure'].upper(), font=font(92), fill=(255, 255, 255), anchor='ls', stroke_width=5, stroke_fill=(0, 0, 0))
    # note + credit
    note = NOTE.get(info.get('lang', 'en'), 'SIMULATED')
    note = note if note == 'SIMULATED' else f'{note} · SIMULATED'
    draw.text((W / 2, H - 34), note, font=font(26), fill=(255, 255, 255, 220), anchor='mm', stroke_width=3, stroke_fill=(0, 0, 0))
    if info.get('credit'):
        draw.text((W - 24, H - 22), info['credit'], font=font(22), fill=(255, 255, 255, 230), anchor='rs', stroke_width=2, stroke_fill=(0, 0, 0))


def inset(image, picture):
    """A small blue-ringed magnifier (bottom right) with a closer picture of the target."""
    if picture is None: return
    size = 260
    round_mask = Image.new('L', (size, size), 0); ImageDraw.Draw(round_mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    x, y = W - size - 60, H - size - 90
    image.paste(picture.resize((size, size)), (x, y), round_mask)
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - 4, y - 4, x + size + 4, y + size + 4), outline=BLUE, width=8)
    draw.ellipse((x - 10, y - 10, x + size + 10, y + size + 10), outline=(255, 255, 255), width=3)


def closer(source_z, lon, lat):
    """One tile three zoom levels closer around (lon, lat), or None."""
    if not source_z: return None
    source, z = source_z
    z = min(17, z + 3); n = 2 ** z
    try:
        data = source.tile(z, int((lon + 180) / 360 * n) % n, int(merc_y(lat) * n))
        return Image.open(BytesIO(data)).convert('RGB')
    except Exception:
        return None


# ---- Eğik görünüm (Static Images API: one picture with bearing + pitch) ----
FOV = 0.6435011087932844  # vertical field of view of the Mapbox GL camera (36.87°); our marks use the same camera
SIZE = (1280, 720)  # logical pixels requested (@2x: 2560×1440)


def camera(lon, lat, zoom, bearing, pitch, width, height):
    """(lon, lat) → (x, y) logical pixels of a Static Images picture. An approximation of
    the GL camera (centre at the middle, 512-px world tiles, perspective tilt), close
    enough to put a line and labels on the right town; None behind the horizon."""
    world = 512 * 2 ** zoom
    cx, cy = (lon + 180) / 360 * world, merc_y(lat) * world
    b, p = math.radians(bearing), math.radians(pitch)
    distance = .5 / math.tan(FOV / 2) * height

    def project(plon, plat):
        dx, dy = (plon + 180) / 360 * world - cx, merc_y(plat) * world - cy
        rx, ry = dx * math.cos(b) + dy * math.sin(b), -dx * math.sin(b) + dy * math.cos(b)
        depth = distance - ry * math.sin(p)
        if depth <= distance * .05: return None
        return width / 2 + distance * rx / depth, height / 2 + distance * ry * math.cos(p) / depth
    return project


def azimuth(a, b):
    """Compass direction (degrees) from a to b, each (lon, lat)."""
    la1, la2, dl = math.radians(a[1]), math.radians(b[1]), math.radians(b[0] - a[0])
    return math.degrees(math.atan2(math.sin(dl) * math.cos(la2), math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl))) % 360


def oblique_view(points, *, route=False):
    """Centre, zoom, bearing and pitch so all points fit (about 60 % of the picture)."""
    lon = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
    ys = [merc_y(p[1]) for p in points]
    mid = (min(ys) + max(ys)) / 2
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * mid))))
    # North stays up (bearing 0): Marseille → Nice runs left to right as on any map. Turning the camera
    # toward the travel direction put Nice “on top” and read as a wrong direction.
    bearing = 0
    pitch = 60 if route else 55  # the API's maximum (60): on a flat satellite photo less tilt hardly shows
    w, h = SIZE
    zoom = 12.
    for _ in range(6):
        project = camera(lon, lat, zoom, bearing, pitch, w, h)
        spots = [project(*p[:2]) for p in points]
        if any(s is None for s in spots): zoom -= 1; continue
        need = max(max(abs(x - w / 2) / (w / 2), abs(y - h / 2) / (h / 2)) for x, y in spots) / .6
        if abs(math.log2(max(need, 1e-6))) < .05: break
        zoom -= math.log2(max(need, 1e-6))
        zoom = max(1., min(15., zoom))
    return lon, lat, round(zoom, 2), bearing, pitch


def oblique(points, width, height, *, route=False, target=None):
    """(picture width×height, projector (lon, lat) → canvas pixels, attribution) or SatelliteError.
    target (lon, lat): where a closer view ends; it may make the zoom a little closer."""
    lon, lat, zoom, bearing, pitch = oblique_view(points, route=route)
    source = provider()
    try: data = source.static(lon, lat, zoom, bearing, pitch, *SIZE)
    except SatelliteError as error:
        error.request = getattr(source, 'last_request', '')  # for the render diagnostics (key hidden)
        raise
    try: picture = Image.open(BytesIO(data)).convert('RGB')
    except Exception: raise SatelliteError('invalid_response', 'Mapbox eğik görünüm resmi okunamadı; düz görünüm kullanıldı.') from None
    project = camera(lon, lat, zoom, bearing, pitch, *SIZE)
    sx, sy = width / SIZE[0], height / SIZE[1]

    def xy(plon, plat):
        spot = project(plon, plat)
        if spot is None: return (width / 2, -height)  # behind the horizon: off the top
        return spot[0] * sx, spot[1] * sy
    received = f'{getattr(source, "last_response", "")} {picture.size[0]}×{picture.size[1]}'.strip()
    picture = haze(picture.resize((width, height), Image.LANCZOS).filter(ImageFilter.UnsharpMask(2, 50, 3)))
    return picture, xy, getattr(source, 'attribution', ''), {'zoom': zoom, 'bearing': bearing, 'pitch': pitch,
                                                             'request': getattr(source, 'last_request', ''), 'response': received}


def haze(picture):
    """Light atmospheric haze toward the far (top) edge: depth reads at a glance."""
    w, h = picture.size
    alpha = np.clip(1 - np.arange(h) / (h * .42), 0, 1) ** 1.6 * 150
    mask = Image.fromarray(np.repeat(alpha[:, None], w, axis=1).astype('uint8'), 'L')
    return Image.composite(Image.new('RGB', (w, h), (196, 212, 228)), picture, mask)
