"""Opt-in bounded frame batches, cancellable between requests; persisted partials.

Only the repository's documented image input is used. Full-video capability
cannot be inferred from a model name or generateContent method availability.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from threading import Event,RLock
from uuid import uuid4
from pydantic import Field,ValidationError
from app.editor.advanced import Strict
from app.editor.models import EditorError
from app.projects import now

VERSION='naman-comprehensive-review-v1'
_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='video-review')
_lock=RLock();_jobs={}


class Request(Strict):
    confirmed: bool
    data_sharing_confirmed: bool
    cost_confirmed: bool
    start: float=Field(ge=0)
    end: float=Field(gt=0)
    frames: int=Field(ge=8,le=48)


def save(editor,pid,key,report):
    with closing(editor.projects._connection()) as c,c:c.execute('INSERT OR REPLACE INTO archive_analysis_cache VALUES (?,?,?,?,?)',(pid,key,VERSION,json.dumps(report,ensure_ascii=False),now()))


def start(editor,pid,payload):
    try:req=Request.model_validate(payload)
    except ValidationError:raise EditorError('invalid_review','İnceleme bölümünü, 8–48 kare sayısını ve ayrı onayları kontrol edin.') from None
    if not all((req.confirmed,req.data_sharing_confirmed,req.cost_confirmed)):raise EditorError('confirmation_required','Kare paylaşımını ve olası ücreti ayrı ayrı onaylayın.')
    if not editor.settings or not editor.settings.ai_visual_check():raise EditorError('gemini_disabled','Ayarlar bölümünde Gemini görsel kontrolünü açın.',409)
    version=editor.rendering.view(pid).get('active')
    if not version or version['status']!='completed':raise EditorError('render_required','Önce tamamlanmış videoyu aktif seçin.',409)
    duration=version.get('metadata',{}).get('duration',0)
    if not req.start<req.end<=duration:raise EditorError('invalid_review','Bölüm aralığı tamamlanmış videonun içinde olmalıdır.')
    path=editor.rendering.export(pid,version['id'])
    from app.editor.service import sha256_file
    digest=sha256_file(path)
    model=editor.settings.gemini_config().get('model') if hasattr(editor.settings,'gemini_config') else None
    key=hashlib.sha256(json.dumps([digest,version['id'],model,req.start,req.end,req.frames],sort_keys=True,default=str).encode()).hexdigest()
    with closing(editor.projects._connection()) as c:row=c.execute('SELECT result_json FROM archive_analysis_cache WHERE project_id=? AND sha256=? AND analyzer_version=?',(pid,key,VERSION)).fetchone()
    if row and json.loads(row[0]).get('status')=='completed':return {**json.loads(row[0]),'cached':True}
    token=(str(editor.projects._path(pid)),key)
    with _lock:
        if token in _jobs and not _jobs[token]['future'].done():return _jobs[token]['report']
        if any(not j['future'].done() for j in _jobs.values()):raise EditorError('review_busy','Başka inceleme sürüyor; tamamlanmasını veya iptalini bekleyin.',409)
        for old in [k for k,v in _jobs.items() if v['future'].done()]:_jobs.pop(old,None)
        samples=[round(req.start+(req.end-req.start)*(i+.5)/req.frames,3) for i in range(req.frames)]
        report={'render_version_id':'review-'+key,'video_version_id':version['id'],'review_id':key,'source_sha256':digest,'summary':'Kapsamlı örnek kare incelemesi',
                'basis':'Tam video gönderilmedi. Yalnız listelenen zaman kodlarındaki kareler incelenir; ses/anlam/tarih/coğrafya bulguları bağımsız doğrulama gerektirir.',
                'analysis_scope':'sample_frames','requested_range':[req.start,req.end],'requested_frames':req.frames,'sample_timecodes':[],
                'issues':[],'status':'queued','cached':False,'input_mode':'images','video_capability':'unverified','max_requests':(req.frames+7)//8}
        save(editor,pid,key,report);cancel=Event();job={'report':report,'cancel':cancel};_jobs[token]=job
        job['future']=_executor.submit(run,editor,pid,key,report,samples,cancel)
        return dict(report)


def run(editor,pid,key,report,samples,cancel):
    report['status']='running';save(editor,pid,key,report)
    try:
        for i in range(0,len(samples),8):
            if cancel.is_set():report['status']='cancelled';break
            batch=samples[i:i+8]
            result=editor.video_review(pid,{'confirm':True,'data_sharing_confirmed':True,'cost_confirmed':True},sample_times=batch,
                                       review_version='naman-comprehensive-piece-'+key,expected_version=report['video_version_id'])
            report['sample_timecodes']+=result.get('sample_timecodes',[]);report['issues']+=result.get('issues',[])
            report['summary']=result.get('summary',report['summary']);save(editor,pid,key,report)
        else:report['status']='completed'
    except Exception:
        report['status']='failed';report['error']='İnceleme tamamlanamadı. Başarılı parçalar korundu; bağlantı/model ayarlarını kontrol edin.'
    save(editor,pid,key,report)


def status(editor,pid,key,cancel=False):
    import re
    if not re.fullmatch('[a-f0-9]{64}',key):raise EditorError('review_missing','İnceleme kimliği geçersiz.',404)
    if cancel:
        token=(str(editor.projects._path(pid)),key)
        with _lock:
            job=_jobs.get(token)
            if job:job['cancel'].set()
    with closing(editor.projects._connection()) as c:row=c.execute('SELECT result_json FROM archive_analysis_cache WHERE project_id=? AND sha256=? AND analyzer_version=?',(pid,key,VERSION)).fetchone()
    if not row:raise EditorError('review_missing','Bu projeye ait inceleme bulunamadı.',404)
    report=json.loads(row[0])
    token=(str(editor.projects._path(pid)),key)
    with _lock:job=_jobs.get(token)
    if report.get('status') in ('queued','running') and (not job or job['future'].done()):
        report['status']='interrupted';save(editor,pid,key,report)
    return {**report,'cancel_requested':cancel,'notice':'İptal, devam eden sağlayıcı isteğinden sonra yeni parça gönderimini durdurur; mevcut isteği/ücreti geri alamaz.'}
