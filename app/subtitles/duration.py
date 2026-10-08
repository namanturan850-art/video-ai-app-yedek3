"""Read duration from local metadata only; never upload, download or create TTS."""
import shutil
import subprocess
from pathlib import Path
import wave
import mutagen
from app.subtitles.models import valid_duration


def discover_duration(path, stored=None, *, ffmpeg_path=None, known_ffmpeg_paths=()):
    if valid_duration(stored): return float(stored), 'stored'
    probes = []
    found = shutil.which('ffprobe')
    if found: probes.append(found)
    # This app currently detects ffmpeg on PATH; it has no custom location setting.
    # Accept a detected/configured path for future callers without inventing a bundle.
    ffmpeg = ffmpeg_path or shutil.which('ffmpeg')
    for executable in [ffmpeg, *known_ffmpeg_paths]:
        if not executable: continue
        sibling = Path(executable).with_name('ffprobe.exe' if str(executable).lower().endswith('.exe') else 'ffprobe')
        if sibling.is_file() and str(sibling) not in probes: probes.append(str(sibling))
    for probe in probes:
        try:
            completed = subprocess.run([probe, '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', str(path)], capture_output=True, text=True, timeout=15)
            value = float(completed.stdout.strip())
            if completed.returncode == 0 and valid_duration(value): return round(value, 3), 'ffprobe'
        except (OSError, ValueError, subprocess.SubprocessError): pass
    try:
        if path.suffix.lower() == '.wav':
            with wave.open(str(path), 'rb') as reader:
                value = reader.getnframes() / reader.getframerate()
            if valid_duration(value): return round(value, 3), 'wav_metadata'
        metadata = mutagen.File(path)
        value = metadata.info.length if metadata is not None else None
        if valid_duration(value): return round(value, 3), 'mutagen'
    except (OSError, ValueError, TypeError, AttributeError, ZeroDivisionError, EOFError, wave.Error, mutagen.MutagenError): pass
    return None, 'unavailable'
