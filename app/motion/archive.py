"""[ARŞİV: …] — an archive photo in a white frame, slightly tilted, on a dark
blurred copy of itself; the camera zooms in slowly. Local renderer only."""
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageOps

W, H, FPS = 1920, 1080, 30
TILT = -3.0       # degrees
ZOOM = .06        # slow push-in over the whole clip


def compose(photo, caption, font):
    """The still picture (without camera move), 1.12× the frame for room to zoom."""
    cw, ch = int(W * 1.12), int(H * 1.12)
    back = ImageOps.fit(photo, (cw, ch)).filter(ImageFilter.GaussianBlur(28))
    back = Image.blend(back, Image.new('RGB', back.size, (8, 12, 20)), .62)
    inner = ImageOps.contain(photo, (int(cw * .58), int(ch * .62)))
    border = 26
    framed = Image.new('RGB', (inner.width + 2 * border, inner.height + 2 * border + (70 if caption else 0)), (246, 244, 238))
    framed.paste(inner, (border, border))
    if caption:
        draw = ImageDraw.Draw(framed)
        draw.text((framed.width // 2, inner.height + border + 40), caption, font=font, fill=(30, 30, 34), anchor='mm')
    shadow = Image.new('RGBA', (framed.width + 80, framed.height + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((40, 50, framed.width + 40, framed.height + 50), fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    tilted = framed.convert('RGBA').rotate(TILT, resample=Image.BICUBIC, expand=True)
    shadow = shadow.rotate(TILT, resample=Image.BICUBIC, expand=True)
    canvas = back.convert('RGBA')
    x, y = (cw - tilted.width) // 2, (ch - tilted.height) // 2
    canvas.alpha_composite(shadow, (x - 40 + 10, y - 40 + 14))
    canvas.alpha_composite(tilted, (x, y))
    return canvas.convert('RGB')


def render(scene, output, ffmpeg):
    element = next(e for e in scene['elements'] if e['type'] == 'archive')
    props = element['props']
    from app.motion.templates import _font
    photo = Image.open(props['image_path']).convert('RGB')
    still = compose(photo, props.get('caption', ''), _font('Montserrat.ttf', 38, True))
    frames = max(1, round(scene['duration'] * FPS))
    command = [ffmpeg, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
               '-frames:v', str(frames), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, shell=False)
    try:
        cw, ch = still.size
        for i in range(frames):
            p = i / max(1, frames - 1)
            scale = 1 / 1.12 * (1 - ZOOM * p)  # crop shrinks → slow zoom-in
            w, h = cw * scale * 1.12 / 1.12, ch * scale
            w = W / H * h
            left, top = (cw - w) / 2, (ch - h) / 2
            process.stdin.write(still.resize((W, H), Image.BICUBIC, box=(left, top, left + w, top + h)).tobytes())
        process.stdin.close()
        error = process.stderr.read()
        if process.wait(timeout=600): raise RuntimeError(error.decode('utf-8', 'replace')[-300:] or 'ffmpeg failed')
    finally:
        if process.poll() is None: process.kill()
    return frames
