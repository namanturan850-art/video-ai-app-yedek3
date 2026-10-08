"""Validated, atomic audio storage. No transcoding, rendering or scene changes."""
from contextlib import closing
import hashlib
import ipaddress
import logging
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urljoin,urlsplit
from uuid import uuid4
import wave

import httpx

from app.projects import linked
from app.narration.models import NarrationError

TYPES={'audio/mpeg':('.mp3','mp3'),'audio/mp3':('.mp3','mp3'),
       'audio/wav':('.wav','wav'),'audio/x-wav':('.wav','wav'),
       'audio/flac':('.flac','flac'),'audio/x-flac':('.flac','flac'),
       'audio/ogg':('.ogg','ogg'),'application/ogg':('.ogg','ogg'),
       'audio/mp4':('.m4a','m4a'),'audio/x-m4a':('.m4a','m4a')}
LIMIT=500_000_000
PRIVATE_AUDIO_HOSTS=set()


class PrivateAudioHTTPFilter(logging.Filter):
    def filter(self,record):
        # HTTP client debug logs include signed URLs. Only audio-host logs are
        # suppressed; this does not change other providers' diagnostic output.
        return not any(host in record.getMessage().lower() for host in tuple(PRIVATE_AUDIO_HOSTS))


for name in ('httpx','httpcore','httpcore.connection','httpcore.http11','httpcore.http2','httpcore.proxy'):
    logging.getLogger(name).addFilter(PrivateAudioHTTPFilter())


def directory(projects,project_id):
    root=projects._path(project_id);folder=root/'voice'
    if linked(folder) or (folder.exists() and not folder.is_dir()) or folder.resolve()!=root.resolve()/'voice':
        raise NarrationError('local_storage','Ses klasörü güvenli yerel klasör değil. Dosyalar korunarak işlem durduruldu.',409)
    try:folder.mkdir(exist_ok=True)
    except OSError:
        raise NarrationError('local_storage','Ses klasörü açılamadı. Veri klasörünün yazılabilir olduğunu kontrol edin.') from None
    return folder


def safe_audio_url(value,allowed_hosts):
    """Only documentation-verified output hosts; no private/loopback addresses."""
    try:
        url=urlsplit(value)
        if (not isinstance(value,str) or len(value)>4000 or url.scheme!='https'
            or url.username is not None or url.password is not None or url.port not in (None,443)
            or url.fragment or '\\' in value or any(ord(c)<33 for c in value)
            or url.hostname not in allowed_hosts):raise ValueError()
        try:
            address=ipaddress.ip_address(url.hostname)
            if not address.is_global:raise ValueError()
        except ValueError:
            if url.hostname in ('localhost','127.0.0.1','::1') or re.fullmatch(r'[\d.:]+',url.hostname):raise
        return value
    except (ValueError,TypeError,AttributeError):
        raise NarrationError('audio_download_failed','Ses indirme adresi doğrulanamadı. Görev kimliği korundu; destek isteyin.',502) from None


def valid_signature(head,format):
    return ((format=='mp3' and (head.startswith(b'ID3') or (len(head)>1 and head[0]==255 and head[1]&224==224)))
            or (format=='wav' and head[:4]==b'RIFF' and head[8:12]==b'WAVE')
            or (format=='flac' and head.startswith(b'fLaC')) or (format=='ogg' and head.startswith(b'OggS'))
            or (format=='m4a' and head[4:8]==b'ftyp'))


def audio_path(projects,project_id,audio):
    value=audio.get('local_path','')
    if not re.fullmatch(r'voice/[a-f0-9]{32}\.(mp3|wav|flac|ogg|m4a)',value):
        raise NarrationError('invalid_audio','Yerel ses dosyası doğrulanamadı. Dosyaları silmeden destek isteyin.',409)
    path=directory(projects,project_id)/Path(value).name
    if linked(path) or not path.is_file() or path.stat().st_size!=audio.get('file_size'):
        raise NarrationError('invalid_audio','Yerel ses dosyası eksik veya değişmiş. Görev kimliği korundu; Devam Et deyin.',409)
    return path


def probe_duration(path):
    # Native WAV support avoids requiring FFmpeg just to hear narration.
    if path.suffix=='.wav':
        try:
            with wave.open(str(path),'rb') as reader:
                return round(reader.getnframes()/reader.getframerate(),3)
        except (OSError,EOFError,wave.Error,ZeroDivisionError):pass
    probe=shutil.which('ffprobe')
    if not probe:
        ffmpeg=shutil.which('ffmpeg')
        if ffmpeg:
            adjacent=Path(ffmpeg).with_name('ffprobe.exe' if os.name=='nt' else 'ffprobe')
            if adjacent.is_file():probe=str(adjacent)
    if not probe:return None
    try:
        result=subprocess.run([probe,'-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],
                              capture_output=True,text=True,timeout=15)
        value=float(result.stdout.strip())
        if result.returncode==0 and math.isfinite(value) and 0<value<86400:return round(value,3)
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return None


class AudioDownloader:
    def __init__(self,projects,*,transport=None):self.projects,self.transport=projects,transport

    def download(self,project_id,url,allowed_hosts):
        PRIVATE_AUDIO_HOSTS.update(allowed_hosts)
        with self.projects.lock,closing(self.projects._connection()) as connection:
            self.projects._row(connection,project_id);folder=directory(self.projects,project_id)
        temporary=folder/('.audio-'+uuid4().hex)
        try:
            with httpx.Client(timeout=httpx.Timeout(60,connect=10),transport=self.transport,follow_redirects=False) as client:
                # Downloads are unauthenticated: never forward xi-api-key to a CDN.
                for _ in range(4):
                    url=safe_audio_url(url,allowed_hosts)
                    with client.stream('GET',url,headers={'Accept-Encoding':'identity'}) as response:
                        if response.status_code in (301,302,303,307,308):
                            location=response.headers.get('location')
                            if not location:break
                            url=urljoin(url,location);continue
                        if response.status_code!=200:
                            raise NarrationError('audio_download_failed','Ses dosyası indirilemedi. Görev korunuyor; Devam Et ile aynı görevi deneyin.')
                        mime=response.headers.get('content-type','').split(';')[0].lower().strip()
                        if mime not in TYPES:raise NarrationError('invalid_audio','Ses dosyasının türü doğrulanamadı. Görev kimliği korundu.',502)
                        declared=response.headers.get('content-length')
                        if declared and (not declared.isdigit() or not 12<=int(declared)<=LIMIT):
                            raise NarrationError('invalid_audio','Ses dosyasının boyutu uygun değil. Görev kimliği korundu.',502)
                        size=0;head=bytearray();digest=hashlib.sha256()
                        with self.projects.lock:
                            directory(self.projects,project_id);stream=temporary.open('xb')
                        with stream:
                            for chunk in response.iter_bytes(65536):
                                size+=len(chunk)
                                if size>LIMIT:raise NarrationError('invalid_audio','Ses dosyası izin verilen boyutu aşıyor.',502)
                                if len(head)<32:head.extend(chunk[:32-len(head)])
                                digest.update(chunk);stream.write(chunk)
                            stream.flush();os.fsync(stream.fileno())
                        suffix,format=TYPES[mime]
                        incomplete_wav=(format=='wav' and (size<44 or int.from_bytes(head[4:8],'little')+8>size))
                        if size<12 or (declared and size!=int(declared)) or incomplete_wav or not valid_signature(head,format):
                            raise NarrationError('invalid_audio','Ses dosyası eksik veya geçersiz. Görev kimliği korundu; Devam Et deyin.',502)
                        with self.projects.lock:
                            directory(self.projects,project_id);path=folder/(uuid4().hex+suffix)
                            os.replace(temporary,path)
                        duration=probe_duration(path)
                        return {'local_path':'voice/'+path.name,'format':format,'content_type':mime,
                                'file_size':size,'sha256':digest.hexdigest(),'duration':duration,
                                'duration_message':'' if duration is not None else 'Ses süresi daha sonra hesaplanacak.'}
            raise NarrationError('audio_download_failed','Ses dosyası yönlendirmesi doğrulanamadı. Görev kimliği korundu.',502)
        except httpx.HTTPError:
            raise NarrationError('audio_download_failed','Ses indirilemedi. İnternet bağlantısını kontrol edip Devam Et deyin.') from None
        except OSError:
            raise NarrationError('local_storage','Ses kaydedilemedi. Veri klasörünün yazılabilir olduğunu ve boş alanı kontrol edin.') from None
        finally:temporary.unlink(missing_ok=True)
