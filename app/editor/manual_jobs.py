"""Bounded local JSON review jobs. They create drafts, never apply edits."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from threading import RLock
from uuid import uuid4

from app.editor.models import EditorError
from app.editor.manual_review import MAX_RESPONSE_CHARS,parse_response,prepare_html_layers,review
from app.projects import now

VERSION='naman-manual-review-job-v1'
_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='manual-import')
_lock=RLock()
_jobs={}


def _save(editorial,pid,key,value):
    with closing(editorial.projects._connection()) as c,c:
        c.execute('INSERT OR REPLACE INTO archive_analysis_cache VALUES (?,?,?,?,?)',(pid,key,VERSION,json.dumps(value,ensure_ascii=False),now()))


def start(editorial,pid,payload):
    text=payload.get('text')
    if set(payload)!={'text'} or not isinstance(text,str) or not text.strip() or len(text)>MAX_RESPONSE_CHARS:
        raise EditorError('invalid_response','En fazla 2.000.000 karakterlik JSON cevabı gönderin.')
    # No project-wide edit lock: submitting/status must remain responsive even
    # while the compiler holds its consistent read/validation snapshot.
    with closing(editorial.projects._connection()) as c:editorial.projects._row(c,pid)
    root=str(editorial.projects.root);digest=hashlib.sha256(text.encode()).hexdigest()
    with _lock:
        for (owner,project,key),job in _jobs.items():
            if owner==root and project==pid and not job['future'].done():
                if job['digest']==digest:
                    value=deepcopy(job['report'])
                    # Submission never embeds a draft; terminal results are
                    # fetched through status, including the Future-finish race.
                    if value['status'] in ('completed','failed'):value['status']='running'
                    return value
                raise EditorError('manual_import_busy','Bu projenin JSON doğrulaması sürüyor. Durumun tamamlanmasını bekleyin.',409)
        if sum(not j['future'].done() for j in _jobs.values())>=2:
            raise EditorError('manual_import_busy','İçe aktarma kuyruğu dolu. Mevcut doğrulamanın bitmesini bekleyin.',503)
        for token in [k for k,j in _jobs.items() if j['future'].done()]:_jobs.pop(token,None)
        key=uuid4().hex
        report={'id':key,'status':'queued','processed':0,'total':0,'message':'JSON doğrulama sırasına alındı',
                'status_url':f'/api/projects/{pid}/editor/manual/response-jobs/{key}'}
        _save(editorial,pid,key,report)
        job={'digest':digest,'report':report};_jobs[(root,pid,key)]=job
        job['future']=_executor.submit(_run,editorial,pid,key,text,job)
        return deepcopy(report)


def _run(editorial,pid,key,text,job):
    report=job['report']
    def progress(done,total,message):
        with _lock:report.update(status='running',processed=done,total=total,message=message)
        # No DB write per proposal: keep the status route independent and cheap.
    try:
        progress(0,0,'JSON okunuyor')
        payload=parse_response(text)
        prepare_html_layers(editorial,pid,payload,progress=progress)
        draft=review(editorial,pid,payload,progress=progress)
        with _lock:final={**report,'status':'completed','draft_id':draft['id'],'processed':report['total'],'message':'Taslak hazır; onay bekliyor'}
    except EditorError as error:
        with _lock:final={**report,'status':'failed','category':error.category,'message':str(error)}
    except Exception:
        with _lock:final={**report,'status':'failed','category':'manual_import_failed','message':'JSON taslağı hazırlanamadı. Mevcut kurgu korunuyor; dosyayı kontrol edip yeniden deneyin.'}
    try:_save(editorial,pid,key,final)
    except Exception:
        final.update(status='failed',category='manual_import_storage',message='İş durumu kaydedilemedi. Mevcut kurgu korunuyor; veri klasörünü ve Kayıtlı plan taslakları bölümünü kontrol edin.')
    with _lock:report.update(final)


def status(editorial,pid,key):
    import re
    if not re.fullmatch('[a-f0-9]{32}',key):raise EditorError('manual_job_missing','İçe aktarma işi bulunamadı.',404)
    token=(str(editorial.projects.root),pid,key)
    with _lock:
        job=_jobs.get(token)
        result=deepcopy(job['report']) if job else None
    if result is None:
        with closing(editorial.projects._connection()) as c:
            row=c.execute('SELECT result_json FROM archive_analysis_cache WHERE project_id=? AND sha256=? AND analyzer_version=?',(pid,key,VERSION)).fetchone()
        if not row:raise EditorError('manual_job_missing','İçe aktarma işi bulunamadı.',404)
        result=json.loads(row[0])
        if result['status'] in ('queued','running'):
            result.update(status='failed',category='manual_import_interrupted',message='Uygulama yeniden başlatıldığı için doğrulama kesildi. Kurgu değiştirilmedi; cevabı yeniden içe aktarın.')
    if result['status']=='completed':
        # Retrieve just this draft, not the entire draft history/project view.
        with closing(editorial.projects._connection()) as c:
            row=c.execute("SELECT payload_json FROM editorial_events WHERE project_id=? AND kind='draft' AND json_extract(payload_json,'$.id')=? ORDER BY id DESC LIMIT 1",(pid,result['draft_id'])).fetchone()
        if not row:raise EditorError('manual_job_missing','Hazırlanan taslak bulunamadı. Kayıtlı taslakları kontrol edin.',404)
        result['draft']=json.loads(row[0])
    return result
