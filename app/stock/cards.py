"""Code-generated 1920x1080 cards (title/quote, number, simple location map).

The last step of the media chain must never fail and must not depend on an
external service or on optional FFmpeg filters (many FFmpeg builds have no
drawtext). Cards are drawn with Pillow; if Pillow or every font is missing a
plain gradient PNG is written with the standard library only. Card text always
comes from the narration (see production.card_fields), never invented.
"""
import math
import struct
import zlib
from pathlib import Path

W, H = 1920, 1080
BACKGROUND = ((14, 22, 38), (28, 44, 70))
ACCENT = (242, 178, 62)
TEXT = (245, 247, 250)
MUTED = (170, 184, 204)
FONTS = ('C:/Windows/Fonts/segoeuib.ttf', 'C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/arial.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
         '/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/Library/Fonts/Arial Bold.ttf')


def _font(size):
    from PIL import ImageFont
    for path in FONTS:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)  # Pillow's bundled font


def _wrap(draw, text, font, width, lines=3):
    words, rows = text.split(), ['']
    for word in words:
        candidate = (rows[-1] + ' ' + word).strip()
        if draw.textlength(candidate, font=font) <= width or not rows[-1]:
            rows[-1] = candidate
        else:
            rows.append(word)
    if len(rows) > lines:
        rows = rows[:lines]
        rows[-1] = rows[-1].rstrip('.,;:') + '…'
    return rows


def _fit(draw, text, width, lines, start, smallest=44):
    size = start
    while size > smallest:
        font = _font(size)
        rows = _wrap(draw, text, font, width, lines)
        if all(draw.textlength(r, font=font) <= width for r in rows) and not rows[-1].endswith('…'):
            return font, rows
        size -= 6
    font = _font(smallest)
    return font, _wrap(draw, text, font, width, lines)


def _centered(draw, rows, font, top, fill, spacing=1.25):
    height = font.size * spacing
    for index, row in enumerate(rows):
        x = (W - draw.textlength(row, font=font)) / 2
        draw.text((x, top + index * height), row, font=font, fill=fill)
    return top + len(rows) * height


def _background(image):
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    (r1, g1, b1), (r2, g2, b2) = BACKGROUND
    for y in range(H):
        t = y / (H - 1)
        draw.line([(0, y), (W, y)], fill=(round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t), round(b1 + (b2 - b1) * t)))
    return draw


def _map(draw, place):
    for x in range(0, W + 1, 120):
        draw.line([(x, 0), (x, H)], fill=(40, 60, 92), width=2)
    for y in range(0, H + 1, 120):
        draw.line([(0, y), (W, y)], fill=(40, 60, 92), width=2)
    # Stylised coast line: a decorative curve, not real geography.
    points = [(x, 640 + 70 * math.sin(x / 210) + 35 * math.sin(x / 77)) for x in range(0, W + 1, 12)]
    draw.line(points, fill=(74, 110, 150), width=6)
    cx, cy = W // 2, 430
    draw.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], fill=ACCENT)
    draw.polygon([(cx - 46, cy + 38), (cx + 46, cy + 38), (cx, cy + 140)], fill=ACCENT)
    draw.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=BACKGROUND[0])
    font, rows = _fit(draw, place, 1500, 2, 110)
    _centered(draw, rows, font, 640, TEXT)


def _number(draw, text):
    import re
    match = re.search(r'\d[\d.,\s]*\d|\d', text)
    number = match.group(0).strip() if match else text
    # The full spoken phrase stays readable under the big number.
    caption = text if match and text.strip() != number else ''
    font, rows = _fit(draw, number, 1600, 1, 300, smallest=120)
    bottom = _centered(draw, rows, font, 300 if caption else 380, ACCENT, spacing=1.1)
    if caption:
        font, rows = _fit(draw, caption, 1500, 2, 72)
        _centered(draw, rows, font, bottom + 30, TEXT)


def _quote(draw, text):
    big = _font(260)
    draw.text((180, 90), '“', font=big, fill=ACCENT)
    font, rows = _fit(draw, text, 1440, 4, 92)
    top = (H - len(rows) * font.size * 1.3) / 2
    _centered(draw, rows, font, top, TEXT, spacing=1.3)


def _title(draw, text):
    font, rows = _fit(draw, text, 1500, 3, 120)
    height = len(rows) * font.size * 1.25
    top = (H - height) / 2
    draw.rectangle([W / 2 - 90, top - 70, W / 2 + 90, top - 58], fill=ACCENT)
    _centered(draw, rows, font, top, TEXT)


def _plain_png(path):
    """Standard-library fallback: gradient PNG, no text (never fails on Pillow/fonts)."""
    rows = bytearray()
    (r1, g1, b1), (r2, g2, b2) = BACKGROUND
    for y in range(H):
        t = y / (H - 1)
        pixel = bytes((round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t), round(b1 + (b2 - b1) * t)))
        rows += b'\x00' + pixel * W
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(rows), 6)) + chunk(b'IEND', b''))
    path.write_bytes(data)


def render_card(path, kind, text):
    """Write a 1920x1080 PNG. Returns 'drawn' or 'plain' (text could not be drawn)."""
    path = Path(path)
    try:
        from PIL import Image
        image = Image.new('RGB', (W, H))
        draw = _background(image)
        {'map': _map, 'number': _number, 'quote': _quote}.get(kind, _title)(draw, ' '.join(str(text).split())[:150])
        image.save(path, 'PNG', optimize=True)
        return 'drawn'
    except Exception:  # Pillow/fonts missing or broken: still produce a valid card
        _plain_png(path)
        return 'plain'
