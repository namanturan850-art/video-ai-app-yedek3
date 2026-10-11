"""Local motion renderer: Pillow draws each frame of a template scene and
FFmpeg encodes it. Needs nothing but Pillow and FFmpeg, so it is the
fallback that always works when OpenMontage is missing or fails."""
import subprocess

from PIL import Image, ImageDraw

from app.motion.templates import (FPS, H, W, _font, counter_text, land, map_view, props_at)


def rgba(hexcolor, opacity=1.):
    return (int(hexcolor[1:3], 16), int(hexcolor[3:5], 16), int(hexcolor[5:7], 16), max(0, min(255, round(255 * opacity))))


class MapLayer:
    """Land polygons projected per frame (equirectangular, same view boxes
    as the Remotion SVG), so zooming stays sharp."""
    def __init__(self, props):
        self.props = props
        self.polys = [(min(x for x, _ in p), max(x for x, _ in p), min(y for _, y in p), max(y for _, y in p), p) for p in land()]

    def frame(self, zoom):
        p = self.props
        left, top, span, height = map_view(p, zoom)
        image = Image.new('RGB', (W, H), p['ocean'])
        draw = ImageDraw.Draw(image)
        sx, sy = W / span, H / height
        for x0, x1, y0, y1, poly in self.polys:
            if y0 > top or y1 < top - height: continue
            for shift in (-360, 0, 360):
                if x1 + shift < left or x0 + shift > left + span: continue
                draw.polygon([((x + shift - left) * sx, (top - y) * sy) for x, y in poly], fill=p['land'], outline=p['coast'])
        return image


def draw_frame(scene, t, base, maps):
    image = base.copy()
    draw = ImageDraw.Draw(image, 'RGBA')
    name = scene['ease']
    for index, element in enumerate(scene['elements']):
        kind = element['type']
        p = props_at(element, t, name)
        if kind == 'map':
            image.paste(maps[index].frame(p.get('zoom', 0)))
            draw = ImageDraw.Draw(image, 'RGBA'); continue
        opacity = p.get('opacity', 1)
        if opacity <= .003: continue
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
        elif kind == 'pin':
            x, y, s = p['x'], p['y'] + p.get('dy', 0), p['size']
            draw.polygon([(x - s * .62, y - s * 1.6), (x + s * .62, y - s * 1.6), (x, y)], fill=rgba(p['fill'], opacity))
            draw.ellipse((x - s, y - s * 2.6, x + s, y - s * .6), fill=rgba(p['fill'], opacity))
            draw.ellipse((x - s * .4, y - s * 2, x + s * .4, y - s * 1.2), fill=rgba(p['hole'], opacity))
        elif kind in ('text', 'counter'):
            size = max(4, int(round(p['size'] * p.get('scale', 1))))
            font = _font(p['font'], size, p.get('bold', True))
            text = counter_text(p['target'], p.get('value', 1), p.get('language', 'de'), p.get('from_year', False)) if kind == 'counter' else p['text']
            anchor = {'mm': 'mm', 'lm': 'lm', 'rm': 'rm'}.get(p.get('anchor', 'mm'), 'mm')
            draw.text((p['x'], p['y'] + p.get('dy', 0)), text, font=font, fill=rgba(p['fill'], opacity), anchor=anchor)
    return image


def render(scene, output, ffmpeg):
    """Encode the scene to H.264 MP4 (yuv420p, 30 fps, exact frame count)."""
    frames = max(1, round(scene['duration'] * FPS))
    base = Image.new('RGB', (W, H), scene['background'])
    maps = {i: MapLayer(e['props']) for i, e in enumerate(scene['elements']) if e['type'] == 'map'}
    command = [ffmpeg, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
               '-frames:v', str(frames), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, shell=False)
    try:
        for i in range(frames):
            process.stdin.write(draw_frame(scene, i / FPS, base, maps).tobytes())
        process.stdin.close()
        error = process.stderr.read()
        if process.wait(timeout=600):
            raise RuntimeError(error.decode('utf-8', 'replace')[-300:] or 'ffmpeg failed')
    finally:
        if process.poll() is None:
            process.kill()
    return frames
