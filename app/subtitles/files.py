"""Immutable version files, atomic individually, activated only after both exist."""
import html
import os
from pathlib import Path
import re
from uuid import uuid4
from app.projects import linked
from app.subtitles.models import SubtitleError


def timestamp(seconds, separator=','):
    ms = round(seconds*1000)
    hours, ms = divmod(ms,3600000)
    minutes, ms = divmod(ms,60000)
    seconds, ms = divmod(ms,1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{separator}{ms:03}'


def srt(cues):
    return '\n\n'.join(f'{i}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["text"]}' for i,c in enumerate(cues,1))+'\n'


def vtt(cues):
    # VTT cue text is markup: escape literal source characters, don't execute tags.
    return 'WEBVTT\n\n'+'\n\n'.join(f'{timestamp(c["start"],".")} --> {timestamp(c["end"],".")}\n{html.escape(c["text"],quote=False)}' for c in cues)+'\n'


def directory(projects, pid):
    root = projects._path(pid)
    folder = root/'subtitles'
    if linked(folder) or (folder.exists() and not folder.is_dir()) or folder.resolve()!=root.resolve()/'subtitles':
        raise SubtitleError('unsafe_path','Altyazı klasörü güvenli değil. Dosyalar korunarak işlem durduruldu.',409)
    folder.mkdir(exist_ok=True)
    return folder


def file_path(projects, pid, value, *, must_exist=True):
    if not isinstance(value,str) or not re.fullmatch(r'subtitles/subtitles-v[1-9][0-9]*\.(srt|vtt)',value):
        raise SubtitleError('unsafe_path','Geçerli bir yerel altyazı dosyası gerekli.',409)
    path = directory(projects,pid)/Path(value).name
    if linked(path) or (must_exist and not path.is_file()):
        raise SubtitleError('missing_file','Yerel altyazı dosyası eksik veya güvenli değil. Önceki sürümler korundu.',409)
    return path


def atomic_write(path, content):
    if linked(path) or path.exists():
        raise SubtitleError('unsafe_path','Altyazı sürüm dosyası zaten var veya güvenli değil. Mevcut dosya değiştirilmedi.',409)
    temp = path.parent/('.subtitle-'+uuid4().hex)
    try:
        with temp.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp,path)
    finally: temp.unlink(missing_ok=True)
