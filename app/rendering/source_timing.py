"""Shared, read-only source coverage checks for Program and final rendering."""
from functools import lru_cache
import math
from pathlib import Path

from app.rendering.models import RenderError

FPS = 30


def video_duration(data):
    video = next(s for s in data['streams'] if s.get('codec_type') == 'video')
    # Container duration can include longer audio or a nonzero video start PTS.
    for value in (video.get('duration'),):
        try:
            duration = float(value)
            if math.isfinite(duration) and duration > 0:
                # Some shifted MP4 tracks omit the last sample's duration from
                # their duration field (125 frames at 25 fps reported as 4.96s).
                # Correct only a single-frame discrepancy with an explicit frame
                # count/rate; never infer seconds of coverage from container audio.
                try:
                    a,b=video['r_frame_rate'].split('/');rate=float(a)/float(b)
                    counted=int(video['nb_frames'])/rate
                    if 1<=rate<=240 and 0<=counted-duration<=1/rate+1e-6:duration=counted
                except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
                return duration
        except (TypeError, ValueError):pass
    try:
        a,b = video['time_base'].split('/')
        duration = float(video['duration_ts']) * float(a) / float(b)
        if math.isfinite(duration) and duration > 0:return duration
    except (KeyError, TypeError, ValueError, ZeroDivisionError):pass
    # A mux with other streams cannot prove video coverage from its container
    # duration alone. Refuse uncertainty rather than borrowing audio duration.
    if any(s.get('codec_type')=='audio' for s in data['streams']):raise ValueError('video duration unavailable')
    start = float(video.get('start_time') or 0)
    duration = float(data['format']['duration']) - max(0, start)
    if not math.isfinite(duration) or duration <= 0:raise ValueError('video duration')
    return duration


@lru_cache(maxsize=128)
def _duration(path, size, stamp, changed, probe):
    from app.rendering.probe import metadata
    try:
        data=metadata(probe,path)
        video=next(s for s in data['streams'] if s.get('codec_type')=='video')
        offset=float(video.get('start_time') or 0)-float(data.get('format',{}).get('start_time') or 0)
        if not math.isfinite(offset):raise ValueError('source start')
        return video_duration(data),max(0.,offset)
    except (KeyError, TypeError, ValueError, StopIteration):
        raise RenderError('input_invalid','Kaynak videonun görüntü süresi doğrulanamadı; dosyayı kontrol edin.') from None


def info(path, probe):
    if not probe:raise RenderError('input_invalid','Kaynak süresini doğrulamak için FFprobe gerekli. FFmpeg kurulumunu kontrol edin.')
    path = Path(path);stat = path.stat()
    return _duration(str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, probe)


def duration(path,probe):return info(path,probe)[0]


def input_time(path,probe,relative):return info(path,probe)[1]+relative


def coverage(source_duration, start, end, speed, length, *, where='Klip'):
    values = (source_duration, start, speed, length)
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values) or source_duration <= 0 or start < 0 or speed <= 0 or length <= 0:
        raise RenderError('invalid_source_range',where+': kaynak başlangıcı, hız veya süre geçersiz.')
    limit = source_duration if end is None else end
    if type(limit) not in (int,float) or not math.isfinite(limit):
        raise RenderError('invalid_source_range',where+': kaynak bitişi gerçek video süresinin dışında. Kesiti düzeltin.')
    if end is not None and not start < limit <= source_duration + 1/FPS:
        raise RenderError('invalid_source_range',f'{where}: gerçek kaynak {source_duration:.3f} sn; seçilen kesit {start:.3f}–{limit:.3f} sn geçersiz. Kaynak başlangıç/bitişini düzeltin; kurgu değiştirilmedi.')
    needed = start + length * speed
    if needed > min(limit, source_duration) + 1/FPS + 1e-6:
        raise RenderError('short_source',f'{where}: kaynak {source_duration:.3f} sn, kesit {start:.3f}–{min(limit,source_duration):.3f} sn; {length:.3f} sn timeline × {speed:g} hız için {needed:.3f} sn kaynak bitişi gerekli. Kesiti/timeline süresini kısaltın, hızı azaltın veya yeterli bir kaynak seçin. Kurgu değiştirilmedi; siyah dolgu veya otomatik döngü uygulanmadı.')
    return start


def editor_coverage(path, probe, start, end, speed, length, where):
    from app.editor.models import EditorError
    try:return coverage(duration(path,probe),start,end,speed,length,where=where)
    except RenderError as error:raise EditorError(error.category,str(error)) from None


def verified_slot(editor,pid,slot):
    """Read-only real-media projection for draft/transition capacity checks.

    Filesystem-free adapters can still use the pure metadata validator. Actual
    stock slots carry local_path and must verify the file before using its clock.
    """
    media=slot.get('media') or {}
    if media.get('media_type')!='video' or not media.get('local_path'):return slot
    from app.editor.models import EditorError
    from app.editor.service import sha256_file
    from app.stock.download import asset_path
    from app.rendering.tools import discover
    path=asset_path(editor.projects,pid,media)
    verify=getattr(getattr(editor.stock,'downloader',None),'verified_hash',None)
    digest=verify(path,media.get('sha256')) if verify else sha256_file(path)
    if media.get('sha256') and digest!=media['sha256']:
        raise EditorError('stale_media','Kurgu kaynağı değişmiş. Arşivi kontrol edin; plan uygulanmadı.',409)
    try:actual=duration(path,discover().get('ffprobe'))
    except RenderError as error:raise EditorError(error.category,str(error)) from None
    return {**slot,'media':{**media,'duration':actual}}
