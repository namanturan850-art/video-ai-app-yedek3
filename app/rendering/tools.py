"""Discover existing trusted tools only. No downloads or HTTP executable paths."""
from pathlib import Path, PureWindowsPath
import os
import stat
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


def local_path(value):
    """Reject URLs/UNC/device paths before AND after resolving a trusted alias."""
    text=str(value)
    if not text or text.startswith(('\\\\','//')) or PureWindowsPath(text).drive.startswith('\\\\'):
        return False
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',text) and not re.match(r'^[a-zA-Z]:[\\/]',text):
        return False
    if os.name=='nt':
        # Mapped network drives also look like C:\...; do not execute them.
        import ctypes
        drive=PureWindowsPath(text).anchor
        drive_type=ctypes.windll.kernel32.GetDriveTypeW
        drive_type.argtypes=[ctypes.c_wchar_p];drive_type.restype=ctypes.c_uint
        if not drive or drive_type(drive) not in (2,3,5,6):
            return False
    return True


def resolve_executable(candidate):
    if not candidate or not local_path(candidate):return None
    try:
        # Tool aliases differ from project assets: trusted discovery may resolve
        # them, but only the final regular, local, non-reparse target is executed.
        path=Path(candidate).resolve(strict=True)
        if not local_path(path) or not stat.S_ISREG(path.stat().st_mode) or linked(path):return None
        return path
    except (OSError,RuntimeError,ValueError):return None


def winget_links():
    value=os.environ.get('LOCALAPPDATA')
    if not value or not local_path(value):return None
    return Path(value)/'Microsoft'/'WinGet'/'Links'


def discover(*,configured=None,root=ROOT):
    """Canonical discovery for Settings, diagnostics and rendering.

    No browser executable path is accepted. Invalid candidates may fall through
    to another independently verified local installation. ffprobe is optional.
    """
    links=winget_links()
    candidates=[shutil.which('ffmpeg'),links/'ffmpeg.exe' if links else None,
                configured,root/'tools'/'ffmpeg'/'ffmpeg.exe']
    executable=None;invalid=False;seen=set()
    for candidate in candidates:
        path=resolve_executable(candidate)
        if not path or str(path) in seen:continue
        seen.add(str(path))
        try:
            if not inspect(path,['-version']).startswith('ffmpeg version '):
                raise RenderError('ffmpeg_invalid','Bulunan araç geçerli FFmpeg değil.')
            encoders=inspect(path,['-hide_banner','-encoders'])
            filters=inspect(path,['-hide_banner','-filters'])
        except RenderError:
            invalid=True;continue
        executable=path;break
    if not executable:
        if invalid:raise RenderError('ffmpeg_invalid','Bulunan FFmpeg doğrulanamadı. Durumu Yenile ile tekrar kontrol edin.')
        return {'found':False,'status':'Bulunamadı','message':'Video oluşturmak için FFmpeg gerekli.','encoders':[],'filters':[],'ffmpeg':None,'ffprobe':None}
    adjacent=executable.with_name('ffprobe.exe' if executable.suffix.lower()=='.exe' else 'ffprobe')
    probes=[shutil.which('ffprobe'),adjacent,links/'ffprobe.exe' if links else None]
    probe=None;seen=set()
    for candidate in probes:
        path=resolve_executable(candidate)
        if not path or str(path) in seen:continue
        seen.add(str(path))
        try:
            if inspect(path,['-version']).startswith('ffprobe version '):probe=str(path);break
        except RenderError:pass
    return {'found':True,'status':'Hazır','message':'FFmpeg bulundu ve çalışıyor. Render tamamen yerel çalışır.',
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
