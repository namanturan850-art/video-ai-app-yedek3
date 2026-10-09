"""Import bounded external search assets into the existing stock cache.

No external path/response is returned to the browser; rendering needs no search.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit
from uuid import uuid4

from app.projects import linked,now
from app.rendering.models import RenderError
from app.rendering.probe import stock as probe_stock
from app.rendering.tools import discover
from app.stock.download import asset_path,directory,signature
from app.stock.models import StockError,normalized_media

SOURCES={'archive_org':{'archive.org'},'nasa':{'images.nasa.gov','www.nasa.gov','nasa.gov'},
         'wikimedia':{'commons.wikimedia.org','upload.wikimedia.org'},
         'pexels':{'www.pexels.com','pexels.com'},'pixabay_video':{'pixabay.com','www.pixabay.com'}}


def valid_asset(projects,project_id,saved):
    """Missing/modified imports require an explicit search, never a render download."""
    try:
        path=asset_path(projects,project_id,saved)
        with path.open('rb') as stream:
            return hashlib.file_digest(stream,'sha256').hexdigest()==saved['sha256']
    except (StockError,OSError,KeyError,TypeError):return False


def cached_assets_valid(projects,project_id,connection,candidates):
    for candidate in candidates:
        row=connection.execute('SELECT metadata_json FROM stock_assets WHERE project_id=? AND provider=? AND media_id=? AND media_type=?',
            (project_id,'openmontage',candidate['media_id'],candidate['media_type'])).fetchone()
        if not row or not valid_asset(projects,project_id,json.loads(row[0])):return False
    return True


def source_page(value,source):
    try:
        u=urlsplit(value)
        if (u.scheme!='https' or u.hostname not in SOURCES.get(source,set()) or u.port not in (None,443)
                or u.username or u.password or u.query or u.fragment or '\\' in value or len(value)>2000):raise ValueError()
        return value
    except (TypeError,ValueError,AttributeError):raise StockError('unsafe_url','OpenMontage kaynak sayfası doğrulanamadı.') from None


def search(bridge,project_id,query):
    cfg=bridge.config()
    if not cfg.get('media_search'):return []
    status=bridge.status()
    if not status['ready']:raise StockError('connection_error',status['message'])
    semantic=cfg.get('matching')=='semantic'
    if semantic and not status['semantic_ready']:
        raise StockError('invalid_request','Semantik OpenMontage için isteğe bağlı CLIP kurulumu gerekli. Ayarlar bölümünde Hızlı seçebilirsiniz.')
    # Owned UUID work directory, under this project's stock directory only.
    folder=directory(bridge.projects,project_id);work=folder/('.om-search-'+uuid4().hex);work.mkdir()
    tool=discover();probe=tool.get('ffprobe')
    if not probe:
        work.rmdir();raise StockError('invalid_request','OpenMontage adaylarını doğrulamak için ffprobe gerekli. FFmpeg kurulumunu kontrol edin.')
    try:
        inputs={'output_dir':str(work),'queries':[{'query':query,'kind':'video'}],'clips_per_query':4,
                'filters':{'orientation':'landscape','min_duration':3,'max_duration':12,'min_width':1280},
                'extract_thumbnails':False,'skip_existing':True,'timeout_seconds':60}
        result=bridge.call('semantic' if semantic else 'search',inputs,work)
        clips=result.get('clips',[])
        if not isinstance(clips,list):raise StockError('invalid_response','OpenMontage aday listesi okunamadı.')
        selected=[]
        for record in clips[:4]:
            try:
                path=Path(record['path'])
                if (not path.is_absolute() or not path.resolve().is_relative_to(work.resolve())
                        or any(linked(p) for p in (path,*path.parents)) or not path.is_file()
                        or not 12<=path.stat().st_size<=250_000_000):raise ValueError()
                with path.open('rb') as stream:
                    if not signature(stream.read(32),'video/mp4'):raise ValueError()
                measured=probe_stock(probe,path,'video');v=next(s for s in measured['streams'] if s.get('codec_type')=='video')
                if v['width']<=v['height'] or v['width']<1280 or v['height']<720 or not 3<=measured['stock_duration']<=12.1:continue
                page=source_page(record.get('source_url'),record.get('source'))
                mid=hashlib.sha256((record['source']+':'+str(record['source_id'])).encode()).hexdigest()
                # Fields below come from the pinned, verified ClipRecord contract.
                m=normalized_media({'provider':'openmontage','media_id':mid,'media_type':'video','source_url':page,'page_url':page,
                    'creator_name':str(record.get('creator') or '')[:300],'width':v['width'],'height':v['height'],
                    'duration':measured['stock_duration'],'preview_url':'','download_url':page,'query_used':query,
                    'description':str(record.get('source_tags') or '')[:1000],
                    'source_metadata':{'source':record['source'],'license':str(record.get('license') or '')[:300]}})
                bridge.settings_guard(m)
                with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                target=folder/(uuid4().hex+'.mp4');shutil.copyfile(path,target)
                saved={**m,'local_path':'stock/'+target.name,'file_size':target.stat().st_size,
                       'sha256':digest,'content_type':'video/mp4','downloaded_at':now()}
                with bridge.projects.lock,closing(bridge.projects._connection()) as c,c:
                    bridge.projects._row(c,project_id)
                    existing=c.execute('SELECT metadata_json FROM stock_assets WHERE project_id=? AND provider=? AND media_id=? AND media_type=?',
                        (project_id,'openmontage',mid,'video')).fetchone()
                    if existing and valid_asset(bridge.projects,project_id,json.loads(existing[0])):
                        # Reuse an intact prior asset; no old file is removed.
                        target.unlink();saved=json.loads(existing[0]);m.update(sha256=saved.get('sha256'))
                    else:
                        # A fresh UUID repairs a missing/corrupt cache without deleting
                        # any prior file or rewriting historical selections/renders.
                        c.execute('INSERT OR REPLACE INTO stock_assets VALUES (?,?,?,?,?)',(project_id,'openmontage',mid,'video',json.dumps(saved,ensure_ascii=False)))
                        m.update(sha256=digest)
                selected.append(m)
            except (ValueError,KeyError,TypeError,OSError,StopIteration,StockError,RenderError):continue
        return selected
    except RenderError as e:raise StockError('connection_error',str(e)) from None
    finally:
        if not linked(work) and not any(linked(p) for p in work.rglob('*')):shutil.rmtree(work)
