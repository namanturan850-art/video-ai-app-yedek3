"""Bounded inspection of the downloaded local source, never an external URL."""
import subprocess
from pathlib import Path

from app.rendering import probe
from app.stock.download import asset_path
from app.stock.models import StockError


def inspect_media(projects, pid, media, tool, start=0.):
    path = asset_path(projects, pid, media)
    from app.rendering.models import RenderError
    try:data = probe.stock(tool.get('ffprobe'), path, media['media_type'])
    except RenderError:
        raise StockError('quality_unverified','Yerel medya dosyası okunamadı; başka aday deneniyor.') from None
    if not data:
        raise StockError('quality_unverified', 'Medya kalitesi doğrulanamadı. FFprobe kurulumunu kontrol edin.')
    stream = next(s for s in data['streams'] if s.get('codec_type') == 'video')
    width, height = stream['width'], stream['height']
    rotation = next((float(s.get('rotation',0)) for s in stream.get('side_data_list',[]) if 'rotation' in s), 0)
    if abs(rotation) % 180 > 45:width, height = height, width
    result = {'sha256': media['sha256'], 'width': width, 'height': height,
              'duration': data.get('stock_duration'), 'quality_version': 1}
    ratio=width/max(1,height)
    landscape=1.6<=ratio<=1.95 if media['media_type']=='video' else 1.3<=ratio<=2.
    if not landscape or width < 1280 or height < 720:
        return {**result, 'accepted': False, 'reason': 'orientation_or_resolution'}
    args = [tool['ffmpeg'], '-v', 'error', '-nostdin', '-threads', '1']
    if media['media_type'] == 'video':args += ['-ss', str(max(0.,start))]
    filters=('fps=1,' if media['media_type']=='video' else '')+'scale=320:180,format=gray'
    args += ['-i', str(path), '-vf', filters, '-frames:v', '3' if media['media_type']=='video' else '1',
             '-threads','1','-f', 'rawvideo', '-pix_fmt', 'gray', '-']
    try:
        decoded = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=20, check=True)
        import numpy as np
        count = len(decoded.stdout) // (320*180)
        if not count or len(decoded.stdout) % (320*180):raise ValueError()
        frames = np.frombuffer(decoded.stdout, np.uint8).reshape(count,180,320).astype(np.float32)
        lap = -4*frames[:,1:-1,1:-1]+frames[:,:-2,1:-1]+frames[:,2:,1:-1]+frames[:,1:-1,:-2]+frames[:,1:-1,2:]
        sharpness = float(np.median(lap.var(axis=(1,2))))
        contrast = float(np.median(frames.std(axis=(1,2))))
    except (OSError, ValueError, subprocess.SubprocessError):
        raise StockError('quality_unverified', 'Yerel medya çözümlenemedi; başka aday deneniyor.') from None
    # Flat sky/sea is inconclusive, not proof of blur. Reject sustained defocus
    # only when the image has contrast but almost no fine detail.
    blurred = contrast > 8 and sharpness < 8
    return {**result, 'accepted': not blurred, 'reason': 'blurred' if blurred else '',
            'sharpness': round(sharpness,2), 'contrast': round(contrast,2), 'samples': count}
