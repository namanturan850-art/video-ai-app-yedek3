"""Local motion renderer: Pillow draws each frame of a template scene and
FFmpeg encodes it. Needs nothing but Pillow and FFmpeg, so it is the
fallback that always works when OpenMontage is missing or fails."""
import math
import subprocess

from PIL import Image, ImageDraw

from app.motion.templates import (FPS, H, W, _font, counter_text, land, map_box, map_view, props_at)


def rgba(hexcolor, opacity=1.):
    return (int(hexcolor[1:3], 16), int(hexcolor[3:5], 16), int(hexcolor[5:7], 16), max(0, min(255, round(255 * opacity))))


class MapLayer:
    """Land polygons projected per frame (equirectangular, same view boxes
    as the Remotion SVG), so zooming stays sharp. Drawn at 2× and reduced:
    smooth (anti-aliased) coastlines instead of jagged pixel steps."""
    SS = 2

    def __init__(self, props):
        self.props = props
        self.polys = [(min(x for x, _ in p), max(x for x, _ in p), min(y for _, y in p), max(y for _, y in p), p) for p in land(map_box(props))]

    def frame(self, zoom):
        key = round(zoom, 4)  # once the zoom has settled every frame is the same picture
        if getattr(self, 'last', (None,))[0] != key:
            self.last = (key, self._draw(zoom))
        return self.last[1]

    def _draw(self, zoom):
        p, k = self.props, self.SS
        left, top, span, height = map_view(p, zoom)
        image = Image.new('RGB', (W * k, H * k), p['ocean'])
        draw = ImageDraw.Draw(image)
        sx, sy = W * k / span, H * k / height
        tiny = span / W / 2  # polygons smaller than half a pixel are skipped
        for x0, x1, y0, y1, poly in self.polys:
            if y0 > top or y1 < top - height or (x1 - x0 < tiny and y1 - y0 < tiny): continue
            for shift in (-360, 0, 360):
                if x1 + shift < left or x0 + shift > left + span: continue
                points = [((x + shift - left) * sx, (top - y) * sy) for x, y in poly]
                draw.polygon(points, fill=p['land'])
                draw.line(points + points[:1], fill=p['coast'], width=k)
        image = image.reduce(k)
        if span < 120:  # zoomed in: a faint degree grid, so open land or sea never looks like an empty frame
            sx, sy = W / span, H / height
            step = next(v for v in (1, 2, 5, 10, 20) if span / v <= 9)
            grid = ImageDraw.Draw(image, 'RGBA')
            colour = rgba(p['coast'], .35)
            lon = math.ceil(left / step) * step
            while lon < left + span:
                grid.line(((lon - left) * sx, 0, (lon - left) * sx, H), fill=colour, width=1); lon += step
            lat = math.floor(top / step) * step
            while lat > top - height:
                grid.line((0, (top - lat) * sy, W, (top - lat) * sy), fill=colour, width=1); lat -= step
        return image


class Pictures:
    """Photos used by a scene (İŞARETLE, ÖNCESONRA), loaded once."""
    def __init__(self):
        self.cache = {}

    def get(self, path):
        if path not in self.cache:
            try: self.cache[path] = Image.open(path).convert('RGB')
            except Exception: self.cache[path] = None
        return self.cache[path]


def cover(picture, w, h, zoom=1., fx=.5, fy=.5):
    """The picture filling a w×h box, zoomed around the focus point (fx, fy)."""
    scale = max(w / picture.width, h / picture.height) * max(1., zoom)
    cw, ch = w / scale, h / scale
    left = min(max(fx * picture.width - cw / 2, 0), picture.width - cw)
    top = min(max(fy * picture.height - ch / 2, 0), picture.height - ch)
    return picture.resize((int(w), int(h)), Image.BILINEAR, box=(left, top, left + cw, top + ch))


def draw_frame(scene, t, base, maps, pictures=None):
    image = base.copy()
    draw = ImageDraw.Draw(image, 'RGBA')
    name = scene['ease']
    view = None  # (left lon, top lat, span, height) of the map drawn last: geo elements are placed on it
    for index, element in enumerate(scene['elements']):
        kind = element['type']
        p = props_at(element, t, name)
        if kind == 'map':
            image.paste(maps[index].frame(p.get('zoom', 0)))
            view = map_view(maps[index].props, p.get('zoom', 0))
            draw = ImageDraw.Draw(image, 'RGBA'); continue
        if kind == 'image':
            picture = (pictures or Pictures()).get(p['path'])
            if picture is None or p.get('opacity', 1) <= .003: continue
            w, h = int(p['w']), int(p['h'])
            reveal = p.get('reveal', 1.)  # curtain: only the left part (0..1) is shown
            if reveal <= .001: continue
            frame = cover(picture, w, h, p.get('zoom', 1.), p.get('fx', .5), p.get('fy', .5))
            if reveal < 1: frame = frame.crop((0, 0, max(1, int(w * reveal)), h))
            if p.get('opacity', 1) < 1:
                under = image.crop((int(p['x']), int(p['y']), int(p['x']) + frame.width, int(p['y']) + frame.height))
                frame = Image.blend(under, frame, p['opacity'])
            image.paste(frame, (int(p['x']), int(p['y'])))
            draw = ImageDraw.Draw(image, 'RGBA'); continue
        opacity = p.get('opacity', 1)
        if opacity <= .003: continue
        if kind.startswith('geo') and view:
            left, top, span, height = view
            at = lambda lat, lon: ((lon - left) * W / span, (top - lat) * H / height)
            if kind == 'geoline':
                points = [at(lat, lon) for lat, lon in p['points']]
                done = p.get('progress', 1.)
                lengths = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** .5 for a, b in zip(points, points[1:])]
                total, drawn, path = sum(lengths) or 1, 0., [points[0]]
                for a, b, length in zip(points, points[1:], lengths):
                    if drawn + length <= done * total:
                        path.append(b); drawn += length; continue
                    part = (done * total - drawn) / (length or 1)
                    if part > 0: path.append((a[0] + (b[0] - a[0]) * part, a[1] + (b[1] - a[1]) * part))
                    break
                if len(path) > 1:
                    draw.line(path, fill=rgba(p['stroke'], opacity), width=int(p['width']), joint='curve')
            elif kind == 'geoarea':
                grow = p.get('grow', 1.)
                if grow <= .002: continue
                clat, clon = p['center']
                points = [at(clat + (lat - clat) * grow, clon + (lon - clon) * grow) for lat, lon in p['points']]
                draw.polygon(points, fill=rgba(p['fill'], opacity * p.get('fill_opacity', .55)), outline=rgba(p['stroke'], opacity), width=int(p.get('width', 5)))
            elif kind == 'geopin':
                x, y = at(p['lat'], p['lon'])
                y += p.get('dy', 0)
                r = p['size']
                draw.ellipse((x - r, y - r, x + r, y + r), fill=rgba(p['fill'], opacity), outline=rgba(p['hole'], opacity), width=max(2, int(r / 3)))
            elif kind == 'geotext':
                x, y = at(p['lat'], p['lon'])
                font = _font(p['font'], int(p['size']), p.get('bold', True))
                text = p['text']
                width = font.getlength(text)
                x = min(max(x, width / 2 + 30), W - width / 2 - 30)
                y = min(max(y + p.get('offset', 0) + p.get('dy', 0), p['size']), H - p['size'])
                if p.get('box'):
                    pad = p['size'] * .45
                    draw.rounded_rectangle((x - width / 2 - pad, y - p['size'] * .75, x + width / 2 + pad, y + p['size'] * .75), radius=12,
                                           fill=rgba(p['box'], opacity * .9))
                draw.text((x, y), text, font=font, fill=rgba(p['fill'], opacity), anchor='mm')
            continue
        if kind == 'arc':
            sweep = p.get('sweep', 360)
            if sweep <= .5: continue
            box = (p['cx'] - p['r'], p['cy'] - p['r'], p['cx'] + p['r'], p['cy'] + p['r'])
            draw.pieslice(box, p.get('start', -90), p.get('start', -90) + sweep, fill=rgba(p['fill'], opacity))
            continue
        if kind == 'icon':
            draw_icon(draw, p['icon'], p['x'], p['y'] + p.get('dy', 0), p['size'] * p.get('scale', 1), rgba(p['fill'], opacity))
            continue
        if kind == 'arrow':
            x1, y1, x2, y2 = p['x1'], p['y1'], p['x1'] + (p['x2'] - p['x1']) * p.get('progress', 1), p['y1'] + (p['y2'] - p['y1']) * p.get('progress', 1)
            colour = rgba(p['stroke'], opacity)
            draw.line((x1, y1, x2, y2), fill=colour, width=int(p['width']))
            import math
            angle, head = math.atan2(y2 - y1, x2 - x1), p['width'] * 3.2
            if p.get('progress', 1) > .2:
                draw.polygon([(x2, y2), (x2 - head * math.cos(angle - .45), y2 - head * math.sin(angle - .45)),
                              (x2 - head * math.cos(angle + .45), y2 - head * math.sin(angle + .45))], fill=colour)
            continue
        if kind == 'rect':
            if index == 0: continue  # background is in the base frame
            w = p['w']
            if w <= .5: continue
            box = (p['x'], p['y'] + p.get('dy', 0), p['x'] + w, p['y'] + p.get('dy', 0) + p['h'])
            draw.rounded_rectangle(box, radius=min(p.get('radius', 0), w / 2, p['h'] / 2), fill=rgba(p['fill'], opacity))
        elif kind == 'circle':
            r = p['r']
            if r <= .5: continue
            box = (p['cx'] - r, p['cy'] - r, p['cx'] + r, p['cy'] + r)
            if p.get('fill'): draw.ellipse(box, fill=rgba(p['fill'], opacity))
            if p.get('stroke'): draw.ellipse(box, outline=rgba(p['stroke'], opacity), width=int(p.get('width', 4)))
        elif kind == 'line':
            draw.line((p['x1'], p['y1'], p['x2'], p['y2']), fill=rgba(p['stroke'], opacity), width=int(p['width']))
        elif kind == 'ring':  # a circle drawn as it grows (İŞARETLE)
            r, done = p['r'], p.get('progress', 1.)
            if done > .01:
                draw.arc((p['cx'] - r, p['cy'] - r * p.get('squash', 1), p['cx'] + r, p['cy'] + r * p.get('squash', 1)), -90, -90 + 360 * done,
                         fill=rgba(p['stroke'], opacity), width=int(p['width']))
        elif kind == 'pin':
            x, y, s = p['x'], p['y'] + p.get('dy', 0), p['size']
            draw.polygon([(x - s * .62, y - s * 1.6), (x + s * .62, y - s * 1.6), (x, y)], fill=rgba(p['fill'], opacity))
            draw.ellipse((x - s, y - s * 2.6, x + s, y - s * .6), fill=rgba(p['fill'], opacity))
            draw.ellipse((x - s * .4, y - s * 2, x + s * .4, y - s * 1.2), fill=rgba(p['hole'], opacity))
        elif kind == 'years':  # İMPARATORLUK: the year runs with the growing border
            from app.motion.templates_extra import year_text
            value = round(p['start_year'] + (p['end_year'] - p['start_year']) * p.get('value', 1))
            font = _font(p['font'], int(p['size']), True)
            text = year_text(value, p.get('language', 'de'))
            if p.get('shadow'): draw.text((p['x'] + 3, p['y'] + 3), text, font=font, fill=(0, 0, 0, int(160 * opacity)), anchor=p.get('anchor', 'mm'))
            draw.text((p['x'], p['y']), text, font=font, fill=rgba(p['fill'], opacity), anchor=p.get('anchor', 'mm'))
        elif kind in ('text', 'counter'):
            size = max(4, int(round(p['size'] * p.get('scale', 1))))
            font = _font(p['font'], size, p.get('bold', True))
            text = counter_text(p['target'], p.get('value', 1), p.get('language', 'de'), p.get('from_year', False)) if kind == 'counter' else p['text']
            anchor = {'mm': 'mm', 'lm': 'lm', 'rm': 'rm'}.get(p.get('anchor', 'mm'), 'mm')
            if p.get('shadow'):
                draw.text((p['x'] + 3, p['y'] + p.get('dy', 0) + 3), text, font=font, fill=(0, 0, 0, int(160 * opacity)), anchor=anchor)
            draw.text((p['x'], p['y'] + p.get('dy', 0)), text, font=font, fill=rgba(p['fill'], opacity), anchor=anchor)
    return image


def draw_icon(draw, icon, x, y, size, colour):
    """Simple flat icons drawn from shapes (no picture files): person, soldier, ship,
    house, coin, tree, building, animal, book, ring (generic)."""
    s = size / 2
    if icon in ('person', 'soldier'):
        draw.ellipse((x - s * .32, y - s, x + s * .32, y - s * .36), fill=colour)
        draw.rounded_rectangle((x - s * .5, y - s * .3, x + s * .5, y + s), radius=s * .3, fill=colour)
        if icon == 'soldier':
            draw.line((x + s * .7, y - s * 1.05, x + s * .7, y + s), fill=colour, width=max(2, int(s * .12)))
            draw.polygon([(x + s * .7, y - s * 1.25), (x + s * .58, y - s * .98), (x + s * .82, y - s * .98)], fill=colour)
    elif icon == 'ship':
        draw.polygon([(x - s, y + s * .2), (x + s, y + s * .2), (x + s * .65, y + s * .8), (x - s * .65, y + s * .8)], fill=colour)
        draw.polygon([(x - s * .05, y - s), (x - s * .05, y + s * .1), (x - s * .75, y + s * .1)], fill=colour)
        draw.polygon([(x + s * .05, y - s * .7), (x + s * .05, y + s * .1), (x + s * .6, y + s * .1)], fill=colour)
    elif icon == 'house':
        draw.polygon([(x - s, y - s * .1), (x, y - s), (x + s, y - s * .1)], fill=colour)
        draw.rectangle((x - s * .72, y - s * .1, x + s * .72, y + s), fill=colour)
    elif icon == 'building':
        for i, h in enumerate((.9, 1.0, .7)):
            draw.rectangle((x - s + i * s * .68, y + s - 2 * s * h, x - s + i * s * .68 + s * .6, y + s), fill=colour)
    elif icon == 'coin':
        draw.ellipse((x - s, y - s, x + s, y + s), fill=colour)
        draw.ellipse((x - s * .62, y - s * .62, x + s * .62, y + s * .62), outline=(0, 0, 0, 70), width=max(2, int(s * .12)))
    elif icon == 'tree':
        draw.polygon([(x, y - s), (x + s * .8, y + s * .35), (x - s * .8, y + s * .35)], fill=colour)
        draw.rectangle((x - s * .15, y + s * .3, x + s * .15, y + s), fill=colour)
    elif icon == 'animal':
        draw.ellipse((x - s * .8, y - s * .35, x + s * .5, y + s * .35), fill=colour)
        draw.ellipse((x + s * .3, y - s * .7, x + s * .9, y - s * .1), fill=colour)
        for dx in (-.6, -.3, .1, .35):
            draw.rectangle((x + s * dx, y + s * .2, x + s * dx + s * .14, y + s), fill=colour)
    elif icon == 'planet':
        draw.ellipse((x - s * .62, y - s * .62, x + s * .62, y + s * .62), fill=colour)
        draw.ellipse((x - s, y - s * .28, x + s, y + s * .28), outline=colour, width=max(2, int(s * .12)))
    elif icon == 'book':
        draw.polygon([(x - s, y - s * .7), (x, y - s * .45), (x, y + s * .9), (x - s, y + s * .65)], fill=colour)
        draw.polygon([(x + s, y - s * .7), (x + s * .08, y - s * .45), (x + s * .08, y + s * .9), (x + s, y + s * .65)], fill=colour)
    else:
        draw.ellipse((x - s * .8, y - s * .8, x + s * .8, y + s * .8), fill=colour)


def render(scene, output, ffmpeg):
    """Encode the scene to H.264 MP4 (yuv420p, 30 fps, exact frame count)."""
    if any(e['type'] == 'relief' for e in scene['elements']):
        from app.motion.relief import render as relief_render
        return relief_render(scene, output, ffmpeg)
    frames = max(1, round(scene['duration'] * FPS))
    base = Image.new('RGB', (W, H), scene['background'])
    maps = {i: MapLayer(e['props']) for i, e in enumerate(scene['elements']) if e['type'] == 'map'}
    pictures = Pictures()
    command = [ffmpeg, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
               '-frames:v', str(frames), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, shell=False)
    try:
        # Nothing changes after the last keyframe: the settled picture is written again, not redrawn.
        settled = max((key[0] for e in scene['elements'] for track in (e.get('tracks') or {}).values() for key in track), default=0)
        data = None
        for i in range(frames):
            if data is None or i / FPS <= settled + 1e-6:
                data = draw_frame(scene, i / FPS, base, maps, pictures).tobytes()
            process.stdin.write(data)
        process.stdin.close()
        error = process.stderr.read()
        if process.wait(timeout=600):
            raise RuntimeError(error.decode('utf-8', 'replace')[-300:] or 'ffmpeg failed')
    finally:
        if process.poll() is None:
            process.kill()
    return frames
