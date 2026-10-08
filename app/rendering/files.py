"""Only job-owned temp trees, immutable final videos and local music are writable."""
import hashlib
import os
from pathlib import Path
import re
import shutil
from app.projects import linked
from app.rendering.models import RenderError


def directory(projects,pid,name='renders'):
    if name not in ('renders','music'):raise RenderError('local_storage','Geçersiz yerel render klasörü.')
    root=projects._path(pid);folder=root/name
    if linked(folder) or (folder.exists() and not folder.is_dir()) or folder.resolve()!=root.resolve()/name:
        raise RenderError('local_storage','Render veya müzik klasörü güvenli değil. Kaynak dosyalar korundu.')
    try:folder.mkdir(exist_ok=True)
    except OSError:raise RenderError('local_storage','Render klasörü açılamadı. Boş alanı ve yazma iznini kontrol edin.',503) from None
    return folder


def job_directory(projects,pid,jid):
    if not re.fullmatch('[a-f0-9]{32}',jid):raise RenderError('local_storage','Geçersiz render görevi.')
    path=directory(projects,pid)/('.job-'+jid)
    if linked(path) or (path.exists() and not path.is_dir()):raise RenderError('local_storage','Geçici render klasörü güvenli değil.')
    path.mkdir(exist_ok=True)
    return path


def cleanup(projects,pid,jid):
    if not re.fullmatch('[a-f0-9]{32}',jid):return
    path=directory(projects,pid)/('.job-'+jid)
    if not path.exists():return
    if linked(path):raise RenderError('local_storage','Geçici render klasörü bağlantı içeriyor; temizlenmedi.')
    for base,dirs,names in os.walk(path,followlinks=False):
        if any(linked(Path(base)/n) for n in dirs+names):
            raise RenderError('local_storage','Geçici render dosyaları bağlantı içeriyor; temizlenmedi.')
    shutil.rmtree(path)


def video_path(projects,pid,metadata):
    value=metadata.get('output_local_path','')
    if not isinstance(value,str) or not re.fullmatch(r'renders/video-v[1-9][0-9]*\.mp4',value):
        raise RenderError('input_invalid','Geçerli bir yerel video dosyası gerekli.',404)
    path=directory(projects,pid)/Path(value).name
    if linked(path) or not path.is_file() or path.stat().st_size!=metadata.get('file_size'):
        raise RenderError('input_missing','Yerel video dosyası eksik veya değişmiş. Önceki kayıtlar korundu.',404)
    return path


def music_path(projects,pid,metadata):
    value=metadata.get('local_path','')
    if not isinstance(value,str) or not re.fullmatch(r'music/[a-f0-9]{32}\.(mp3|wav|m4a|ogg|flac)',value):
        raise RenderError('music_invalid','Geçerli proje içi müzik dosyası gerekli.')
    path=directory(projects,pid,'music')/Path(value).name
    if linked(path) or not path.is_file() or path.stat().st_size!=metadata.get('file_size'):
        raise RenderError('music_invalid','Yerel müzik dosyası eksik veya değişmiş.')
    return path


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
    return digest.hexdigest()


def write(path,text):
    if linked(path):raise RenderError('local_storage','Geçici render dosyası güvenli değil.')
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(text);stream.flush();os.fsync(stream.fileno())
