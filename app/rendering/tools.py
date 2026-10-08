"""Discover existing trusted tools only. No downloads or HTTP executable paths."""
from pathlib import Path
import re
import shutil
import subprocess
from app.projects import linked
from app.rendering.models import RenderError

ROOT=Path(__file__).resolve().parents[2]


def inspect(executable,arguments):
    try:
        result=subprocess.run([str(executable),*arguments],shell=False,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        if result.returncode!=0:raise ValueError()
        return result.stdout+result.stderr
    except (OSError,ValueError,subprocess.SubprocessError):
        raise RenderError('ffmpeg_invalid','FFmpeg çalıştırılamadı. Kurulumunu ve Tanılama ekranını kontrol edin.') from None


def discover(*,configured=None,root=ROOT):
    candidates=[shutil.which('ffmpeg'),configured,root/'tools'/'ffmpeg'/'ffmpeg.exe']
    executable=None
    for candidate in candidates:
        if not candidate:continue
        path=Path(candidate)
        if path.is_file() and not linked(path):executable=path;break
    if not executable:return {'found':False,'status':'Bulunamadı','message':'Video oluşturmak için FFmpeg gerekli.','encoders':[],'filters':[],'ffmpeg':None,'ffprobe':None}
    version=inspect(executable,['-version'])
    if not version.startswith('ffmpeg version '):raise RenderError('ffmpeg_invalid','Bulunan araç geçerli FFmpeg değil.')
    encoders=inspect(executable,['-hide_banner','-encoders'])
    filters=inspect(executable,['-hide_banner','-filters'])
    probe=shutil.which('ffprobe')
    if not probe:
        adjacent=executable.with_name('ffprobe.exe' if executable.suffix.lower()=='.exe' else 'ffprobe')
        if adjacent.is_file() and not linked(adjacent):probe=str(adjacent)
    return {'found':True,'status':'Hazır','message':'FFmpeg hazır. Render tamamen yerel çalışır.',
            'ffmpeg':str(executable),'ffprobe':probe,
            'encoders':[name for name in ('libx264','h264_nvenc') if re.search(r'\b'+name+r'\b',encoders)],
            'filters':[name for name in ('ass','xfade','fade','zoompan','sidechaincompress','amix','afade') if re.search(r'\b'+name+r'\b',filters)]}


def select_encoder(requested,tools):
    encoders=tools['encoders']
    if requested=='nvenc':
        if 'h264_nvenc' not in encoders:raise RenderError('encoder_unavailable','Bu FFmpeg sürümünde NVIDIA NVENC yok. Otomatik veya CPU seçin.')
        return 'h264_nvenc'
    if requested=='auto' and 'h264_nvenc' in encoders:return 'h264_nvenc'
    if 'libx264' not in encoders:raise RenderError('encoder_unavailable','Bu FFmpeg sürümünde CPU / libx264 encoder yok.')
    return 'libx264'


def nvenc_initialization_failure(stderr):
    text=stderr.lower()
    return any(token in text for token in ('cannot load libcuda','cannot load nvcuda','cannot load libnvidia-encode',
        'cannot load nvencodeapi','no capable devices found','no nvenc capable devices found','openencodesessionex failed',
        'driver does not support the required nvenc','minimum required nvidia driver','cuda_error_no_device',
        'cuda_error_system_driver_mismatch','failed to initialize nvenc','cannot init cuda','cuinit(0) failed'))
