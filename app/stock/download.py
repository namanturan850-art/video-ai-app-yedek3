"""Bounded, unauthenticated media downloads into a single project's stock folder."""
from contextlib import closing
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx

from app.projects import linked, now
from app.stock.models import StockError

# Hosts in official examples. Unrecognized redirect hosts are refused, not guessed.
HOSTS = {'pexels': {'images.pexels.com','videos.pexels.com','static-videos.pexels.com','player.vimeo.com'},
         'pixabay': {'pixabay.com','cdn.pixabay.com'}, 'magnific': {'cdn.freepik.com','videos.freepik.com','assets.magnific.com','cdn.magnific.com','joy1.videvo.net','joy2.videvo.net','cdn.videvo.net','vcdn.videvo.net','img.freepik.com'}, 'wikimedia': {'upload.wikimedia.org'}}
PAGES = {'pexels': {'www.pexels.com','pexels.com'}, 'pixabay': {'pixabay.com','www.pixabay.com'}, 'magnific': set(), 'wikimedia': {'commons.wikimedia.org'}}
TYPES = {'video/mp4':('.mp4','video'), 'image/jpeg':('.jpg','image'),
         'image/png':('.png','image'), 'image/webp':('.webp','image'),
         'video/webm':('.mp4','video')}  # Commons WebM is converted to MP4 here, so the rest of the app only sees MP4
# Wikimedia's User-Agent policy asks every client to identify itself with a contact URL.
USER_AGENT = 'AIVideoStudio/1.0 (local desktop app; https://github.com/naman85331/video-ai-app)'
WEBM_SECONDS = 60


def safe_url(value, provider, *, page=False):
    try:
        url = urlsplit(value)
        if (not isinstance(value,str) or len(value)>2000 or any(ord(c)<33 for c in value)
                or url.scheme!='https' or url.username is not None or url.password is not None
                or url.port not in (None,443) or url.fragment or '\\' in value
                or url.hostname not in (PAGES if page else HOSTS).get(provider,set())):
            raise ValueError()
        if url.path.startswith('/api/') or url.path.startswith('/v1/'):
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise StockError('unsafe_url','Medya adresi güvenli sağlayıcı adresi olarak doğrulanamadı.',422) from None


def directory(projects, project_id):
    root = projects._path(project_id)
    path = root/'stock'
    if linked(path) or (path.exists() and not path.is_dir()) or path.resolve()!=root.resolve()/'stock':
        raise StockError('unsafe_path','Stok klasörü dış konuma bağlı. Dosyaları korumak için işlem durduruldu.',409)
    path.mkdir(exist_ok=True)
    return path


def asset_path(projects, project_id, media):
    name = media.get('local_path','')
    if not re.fullmatch(r'stock/[a-f0-9]{32}\.(mp4|jpg|png|webp)', name):
        raise StockError('unsafe_path','Yerel medya dosyası doğrulanamadı.',409)
    target = directory(projects,project_id)/Path(name).name
    if linked(target) or not target.is_file() or target.stat().st_size != media.get('file_size'):
        raise StockError('missing_file','Yerel medya dosyası eksik veya değişmiş. Kilidi açıp Eksik Medyaları Tamamla deyin.',409)
    return target


def signature(data, mime):
    return ((mime=='video/mp4' and len(data)>=12 and data[4:8]==b'ftyp')
            or (mime=='image/jpeg' and data.startswith(b'\xff\xd8\xff'))
            or (mime=='image/png' and data.startswith(b'\x89PNG\r\n\x1a\n'))
            or (mime=='image/webp' and data.startswith(b'RIFF') and data[8:12]==b'WEBP')
            or (mime=='video/webm' and data.startswith(b'\x1aE\xdf\xa3')))


def webm_to_mp4(source, target):
    """First minute of a WebM as silent H.264 MP4 (at most 1080p). Raises StockError."""
    import subprocess
    from app.rendering.tools import discover
    ffmpeg = discover().get('ffmpeg')
    if not ffmpeg: raise StockError('download_type','Bu video WebM biçiminde; dönüştürmek için FFmpeg gerekli. Başka aday seçin.')
    try:
        done = subprocess.run([ffmpeg,'-v','error','-y','-t',str(WEBM_SECONDS),'-i',str(source),'-an','-vf',"scale='min(1920,iw)':-2",
                               '-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],
                              capture_output=True,timeout=900,stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        done = None
    if not done or done.returncode or not target.is_file() or target.stat().st_size < 12:
        raise StockError('incomplete_download','Video MP4’e dönüştürülemedi. Başka aday seçin.')


def mirror(projects, project_id, plan_id, state):
    path = directory(projects,project_id)
    for name in ('media_slots.json', 'media_slots_'+plan_id+'.json'):
        target = path/name
        if linked(target): raise StockError('unsafe_path','Medya kayıt dosyası dış konuma bağlı.',409)
        temporary = path/('.write-'+uuid4().hex)
        try:
            with temporary.open('x',encoding='utf-8',newline='\n') as stream:
                json.dump(state,stream,ensure_ascii=False,indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)


def archive_selection(projects,project_id,state):
    """Create-only snapshot before an explicit rebuild. Never remove old assets."""
    folder=directory(projects,project_id);identifier=uuid4().hex
    target=folder/('selection-'+identifier+'.json')
    # Avoid recursively copying historical snapshots and candidate URL lists.
    saved={k:v for k,v in state.items() if k not in ('selection_history','job')}
    saved['slots']=[{k:v for k,v in slot.items() if k not in ('candidates','search_diagnostics')} for slot in state['slots']]
    with target.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(saved,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    return {'id':identifier,'version':state.get('selection_version',1),'revision':state['revision'],
            'local_path':'stock/'+target.name,'created_at':now()}


class Downloader:
    def __init__(self, projects, *, transport=None):
        self.projects, self.transport = projects, transport


    def _download_magnific(self, project_id, media, folder):
        """Download only the selected original; never persist signed URLs."""
        from datetime import datetime, timezone
        from app.stock.magnific import MagnificStockProvider
        import subprocess
        from app.rendering.tools import discover
        settings=getattr(self, 'settings', None)
        config=settings.stock_config('magnific') if settings else {}
        if not config.get('enabled') or not config.get('api_key'):
            raise StockError('missing_key','Magnific Premium ayarı kapalı.')
        # Conservative per-installation guard: count even unsuccessful link requests.
        usage= self.projects.storage/'magnific_download_usage.json'
        today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
        with self.projects.lock:
            try:
                current=json.loads(usage.read_text('utf-8'))
            except (OSError, ValueError):
                current={}
            count=int(current.get('count',0)) if current.get('day')==today else 0
            if count>=50:
                raise StockError('rate_limit','Magnific günlük güvenlik sınırı (50) doldu.')
            next_count={'day':today,'count':count+1}
            temporary_count=usage.with_name('.magnific-'+uuid4().hex)
            try:
                temporary_count.write_text(json.dumps(next_count),encoding='utf-8')
                os.replace(temporary_count,usage)
            finally:temporary_count.unlink(missing_ok=True)
        provider=MagnificStockProvider(config['api_key'])
        link=provider.download_link(media['media_id'])
        # Signed URLs are ephemeral. No redirects, unknown hosts, loopback, or proxies.
        safe_url(link,'magnific')
        temporary=folder/('.download-'+uuid4().hex+'.part')
        converted=folder/('.converted-'+uuid4().hex+'.mp4')
        try:
            with httpx.Client(timeout=httpx.Timeout(90,connect=10), follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                with client.stream('GET',link,headers={'Accept-Encoding':'identity','User-Agent':USER_AGENT}) as response:
                    if response.status_code!=200:
                        raise StockError('download_http','Magnific özgün videosu alınamadı.')
                    mime=response.headers.get('content-type','').split(';')[0].lower()
                    if mime not in ('video/mp4','video/quicktime','application/octet-stream'):
                        raise StockError('download_type','Magnific özgün video türü desteklenmiyor.')
                    size=0;head=bytearray()
                    with temporary.open('xb') as stream:
                        for chunk in response.iter_bytes(65536):
                            size+=len(chunk)
                            if size>250_000_000:raise StockError('download_size','Magnific video boyutu sınırı aşıldı.')
                            if len(head)<32:head.extend(chunk[:32-len(head)])
                            stream.write(chunk)
                    if size<12 or head[4:8]!=b'ftyp':
                        raise StockError('download_type','Magnific videosunun içeriği doğrulanamadı.')
            # Normalize MOV or MP4 to local, sound-free H.264 for the existing renderer.
            ffmpeg=discover().get('ffmpeg')
            if not ffmpeg:raise StockError('download_type','Magnific videosu için FFmpeg gerekli.')
            result=subprocess.run([ffmpeg,'-v','error','-y','-i',str(temporary),'-an',
                                   '-vf',"scale='min(1920,iw)':-2",'-c:v','libx264','-preset','veryfast',
                                   '-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(converted)],
                                  capture_output=True,stdin=subprocess.DEVNULL,timeout=900)
            if result.returncode or not converted.is_file() or converted.stat().st_size<12:
                raise StockError('download_type','Magnific videosu dönüştürülemedi.')
            with self.projects.lock:
                target=directory(self.projects,project_id)/(uuid4().hex+'.mp4')
                os.replace(converted,target)
                with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                public={**media,'download_url':'','source_metadata':{k:v for k,v in (media.get('source_metadata') or {}).items() if not k.endswith('_url')},
                        'local_path':'stock/'+target.name,'content_type':'video/mp4',
                        'file_size':target.stat().st_size,'sha256':digest,'downloaded_at':now()}
                with closing(self.projects._connection()) as connection, connection:
                    self.projects._row(connection,project_id)
                    connection.execute('INSERT OR REPLACE INTO stock_assets VALUES (?,?,?,?,?)',
                                      (project_id,'magnific',media['media_id'],'video',json.dumps(public,ensure_ascii=False)))
                return public
        except (httpx.HTTPError,OSError,subprocess.SubprocessError):
            raise StockError('download_connection','Magnific videosu güvenli biçimde tamamlanamadı.') from None
        finally:
            temporary.unlink(missing_ok=True);converted.unlink(missing_ok=True)

    def download(self, project_id, media):
        with self.projects.lock, closing(self.projects._connection()) as connection:
            self.projects._row(connection,project_id)
            row = connection.execute('SELECT metadata_json FROM stock_assets WHERE project_id=? AND provider=? AND media_id=? AND media_type=?',
                                     (project_id,media['provider'],media['media_id'],media['media_type'])).fetchone()
            if row:
                cached = json.loads(row[0])
                try:
                    path = asset_path(self.projects,project_id,cached)
                    with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
                    if digest==cached['sha256']:
                        return {**media,**{k:cached[k] for k in ('local_path','file_size','sha256','downloaded_at','content_type')}}
                except (StockError, OSError, KeyError):
                    pass
            folder = directory(self.projects,project_id)
        if media['provider']=='magnific':
            return self._download_magnific(project_id, media, folder)
        if media['provider']=='openmontage':
            raise StockError('missing_file','OpenMontage adayının yerel dosyası eksik. Yeniden Ara ile başka aday bulun; eski seçim korunur.',409)
        # Only our generated filenames. No API key or API Authorization sent to CDN.
        for attempt in range(2):
            temporary = folder/('.download-'+uuid4().hex+'.part')
            target = None
            try:
                url = safe_url(media['download_url'],media['provider'])
                with httpx.Client(timeout=httpx.Timeout(60,connect=10), follow_redirects=False,
                                  transport=self.transport) as client:
                    for redirect in range(4):
                        with client.stream('GET',url,headers={'Accept-Encoding':'identity','User-Agent':USER_AGENT}) as response:
                            if response.status_code in (301,302,303,307,308):
                                if redirect==3 or not response.headers.get('location'):
                                    raise StockError('unsafe_redirect','Medya indirmesi çok fazla yönlendirildi.')
                                url = safe_url(urljoin(url,response.headers['location']),media['provider'])
                                continue
                            if response.status_code!=200:
                                raise StockError('download_http','Medya indirme tamamlanamadı. Kaynak dosyayı yeniden arayıp seçin.')
                            mime = response.headers.get('content-type','').split(';')[0].strip().lower()
                            if mime not in TYPES or TYPES[mime][1]!=media['media_type']:
                                raise StockError('download_type','Medya dosyasının türü doğrulanamadı. Başka aday seçin.')
                            limit = 250_000_000 if media['media_type']=='video' else 20_000_000
                            declared = response.headers.get('content-length')
                            if declared and (not declared.isdigit() or not 12<=int(declared)<=limit):
                                raise StockError('download_size','Medya dosyasının boyutu uygun değil. Başka aday seçin.')
                            size, head, digest = 0,bytearray(),hashlib.sha256()
                            # Recheck the path immediately before creating a file.
                            with self.projects.lock:
                                directory(self.projects,project_id)
                                stream = temporary.open('xb')
                            with stream:
                                for chunk in response.iter_bytes(65536):
                                    size+=len(chunk)
                                    if size>limit: raise StockError('download_size','Medya dosyası çok büyük. Başka aday seçin.')
                                    if len(head)<32: head.extend(chunk[:32-len(head)])
                                    digest.update(chunk);stream.write(chunk)
                                stream.flush();os.fsync(stream.fileno())
                            if size<12 or (declared and size!=int(declared)) or not signature(head,mime):
                                raise StockError('incomplete_download','Medya indirme tamamlanamadı veya dosya geçersiz. Tekrar deneyin.')
                            if mime=='video/webm':
                                converted = folder/('.convert-'+uuid4().hex+'.mp4')
                                try:
                                    webm_to_mp4(temporary,converted)
                                    os.replace(converted,temporary)
                                finally:
                                    converted.unlink(missing_ok=True)
                                with temporary.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256')
                                size, mime = temporary.stat().st_size, 'video/mp4'
                            with self.projects.lock:
                                directory(self.projects,project_id)
                                target = folder/(uuid4().hex+TYPES[mime][0])
                                os.replace(temporary,target)
                                saved = {**media,'local_path':'stock/'+target.name,'content_type':mime,
                                         'file_size':size,'sha256':digest.hexdigest(),'downloaded_at':now()}
                                with closing(self.projects._connection()) as connection, connection:
                                    self.projects._row(connection,project_id)
                                    connection.execute('INSERT OR REPLACE INTO stock_assets VALUES (?,?,?,?,?)',
                                        (project_id,media['provider'],media['media_id'],media['media_type'],json.dumps(saved,ensure_ascii=False)))
                            return saved
                    raise StockError('unsafe_redirect','Medya yönlendirmesi tamamlanamadı.')
            except httpx.HTTPError:
                if attempt==1:
                    raise StockError('download_connection','Medya indirme tamamlanamadı. İnternet bağlantısını kontrol edip Devam Et deyin.') from None
            except OSError:
                raise StockError('local_storage','Medya kaydedilemedi. Veri klasörünün yazılabilir olduğunu ve boş alanı kontrol edin.') from None
            finally:
                temporary.unlink(missing_ok=True)
