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
    # scale bar + big number (bottom left)
    kmpp = km_per_pixel(crop_view, W)
    length_km = nice(kmpp * 260); length_px = length_km / max(1e-9, kmpp)
    y = H - 120
    draw.rectangle((60, y, 60 + length_px, y + 10), fill=(255, 255, 255, 255))
    draw.rectangle((60, y, 60 + length_px / 2, y + 10), fill=(20, 20, 20, 255))
    draw.text((60, y - 12), f'{length_km:g} km', font=font(30), fill=(255, 255, 255), anchor='ls', stroke_width=3, stroke_fill=(0, 0, 0))
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
