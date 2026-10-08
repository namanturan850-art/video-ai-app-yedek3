"""Versioned narration jobs over immutable approved script snapshots.

Uses internal TTSProvider results, never provider-specific response guesses.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json
import logging
from threading import Event
import time
from uuid import uuid4

from app.projects import now
from app.scripts.engine import SecretGuard
from app.scripts.models import ScriptError
from app.narration.audio import AudioDownloader,audio_path
from app.narration.models import (NarrationError,PREVIEW_TEXT,Voice,script_fingerprint,
                                 validate_input,safe_task_id)
from app.narration.provider import make_tts_provider

LOG=logging.getLogger('uvicorn.error.narration')
ACTIVE=('queued','running')
LABELS={'queued':'Görev oluşturuluyor','running':'AI33 seslendirme hazırlıyor',
        'completed':'Tamamlandı','error':'Hata'}


class NarrationService:
    def __init__(self,scripts,settings):
        self.scripts,self.settings=scripts,settings;self.projects=scripts.projects
        self.factory=make_tts_provider;self.downloader=AudioDownloader(self.projects)
        self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='narration')
        self.futures={};self.stop=Event();self.poll_interval=3;self.max_poll_seconds=1800

    def close(self):
        self.stop.set();self.executor.shutdown(wait=True,cancel_futures=True)

    def recover(self):
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            for row in c.execute("SELECT project_id,narration_version_id FROM narration_jobs WHERE status IN ('queued','running')").fetchall():
                item=self._version(c,row['project_id'],row['narration_version_id'])
                item['metadata']['status']='error'
                self._save_metadata(c,item['id'],item['metadata'])
            c.execute("UPDATE narration_jobs SET status='error',error_message=?,updated_at=? WHERE status IN ('queued','running')",
                      ('Uygulama kapanırken işlem durdu. Görev kimliği korundu; Devam Et aynı görevi izler.',now()))

    def _guard(self,value):SecretGuard(self.settings.secret_values()).validate(value)

    def _approved(self,pid):
        try:return self.scripts.repository.approved_current(pid)
        except ScriptError:raise NarrationError('approval_required','Önce senaryo sürümünü onaylayın.',409) from None

    def _version(self,c,pid,vid):
        row=c.execute('SELECT * FROM narration_versions WHERE project_id=? AND id=?',(pid,vid)).fetchone()
        if not row:raise NarrationError('missing_version','Seslendirme sürümü bulunamadı.',404)
        return {**dict(row),'metadata':json.loads(row['metadata_json'])}

    def _save_metadata(self,c,vid,metadata):
        self._guard(metadata)
        c.execute('UPDATE narration_versions SET metadata_json=?,updated_at=? WHERE id=?',
                  (json.dumps(metadata,ensure_ascii=False),now(),vid))

    def _idle(self,c,pid):
        if c.execute("SELECT 1 FROM narration_jobs WHERE project_id=? AND status IN ('queued','running')",(pid,)).fetchone():
            raise NarrationError('busy','Seslendirme işlemi sürüyor. Tamamlanmasını bekleyin.',409)

    def view(self,pid):
        project=self.projects.get(pid);current=self.scripts.repository.view(pid)['current']
        with self.projects.lock,closing(self.projects._connection()) as c:
            versions=[]
            for row in c.execute('SELECT id FROM narration_versions WHERE project_id=? ORDER BY created_at DESC,rowid DESC',(pid,)):
                item=self._version(c,pid,row['id']);item.pop('metadata_json')
                meta=item['metadata'];meta.pop('text',None)
                item['stale']=not current or current['status']!='approved' or current['id']!=item['source_script_version_id'] or script_fingerprint(current['text'])!=meta['script_fingerprint']
                item['stale_message']='Eski senaryo sürümüne ait' if item['stale'] else ''
                if meta.get('audio'):
                    try:audio_path(self.projects,pid,meta['audio'])
                    except (NarrationError,OSError):item['audio_missing']=True
                versions.append(item)
            active=c.execute('SELECT active_version_id FROM narration_state WHERE project_id=?',(pid,)).fetchone()
            active=next((v for v in versions if active and v['id']==active[0]),None)
            job=c.execute('SELECT * FROM narration_jobs WHERE project_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(pid,)).fetchone()
            if job:
                job=dict(job);job['progress']=json.loads(job.pop('progress_json'));job['status_label']=LABELS.get(job['status'],'Bekliyor')
            config=self.settings.safe_view()['ai33']
            result={'project_id':pid,'target_language':project['language'],'approved_script':
                    {'id':current['id'],'version':current['version'],'character_count':len(current['text']),'language':current['language']}
                    if current and current['status']=='approved' else None,
                    'settings':config,'versions':versions,'active':active,'job':job}
            self._guard(result);return result

    def start(self,pid,payload):
        options=validate_input(payload)
        if options.cost_confirmed is not True:
            raise NarrationError('cost_confirmation','AI33/OpenSpeaker seslendirmesi kredi kullanabilir. Devam etmek için açık onay gerekli.',422)
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            approved=self._approved(pid);self._idle(c,pid)
            if options.source_script_version_id!=approved['id']:
                raise NarrationError('stale_script','Onaylı senaryo değişti. Sayfayı yenileyip tekrar deneyin.',409)
            config=self.settings.tts_config()
            if not config.get('api_key'):raise NarrationError('missing_key','Ayarlar → AI33 / OpenSpeaker API anahtarını kaydedin.',422)
            provider=self.factory(self.settings)
            if not provider.contract_ready:
                raise NarrationError('documentation_required','Tamamlanan AI33 TTS görevinin ses çıktı belgesi gerekli. Ücretli görev başlatılmadı.',409)
            voice=next((v for v in config.get('available_voices',[]) if v['provider']==options.voice_provider and v['voice_id']==options.voice_id),None)
            if not voice:raise NarrationError('invalid_voice','Sesleri Getir ile doğrulanmış listeden bir ses seçip kaydedin.',422)
            voice=Voice.model_validate(voice).model_dump()
            old=c.execute("SELECT 1 FROM narration_versions WHERE project_id=? AND kind='narration'",(pid,)).fetchone()
            if old and options.kind=='narration' and not options.regenerate_confirmed:
                raise NarrationError('regeneration_confirmation','Yeni bir AI33 görevi oluşturulacak ve ek kredi kullanabilir. Mevcut seslendirme korunacak; açık onay gerekli.',409)
            # Source is exact approved text; preview is isolated and never active.
            text=approved['text'] if options.kind=='narration' else PREVIEW_TEXT[approved['language']]
            if not text.strip() or len(text)>1_000_000:
                raise NarrationError('invalid_request','Ses metni boş olamaz ve 1.000.000 karakter sınırını aşamaz.',422)
            self._guard(text);self._guard(voice)
            version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM narration_versions WHERE project_id=? AND kind=?',(pid,options.kind)).fetchone()[0]
            vid,jid,stamp=uuid4().hex,uuid4().hex,now()
            metadata={'provider':'AI33 / OpenSpeaker','voice_provider':voice['provider'],'voice_id':voice['voice_id'],
                      'voice_name':voice['display_name'],'speed':options.speed,'target_language':approved['language'],
                      'source_script_version':approved['version'],
                      'character_count':len(text),'script_fingerprint':script_fingerprint(approved['text']),
                      'text':text,'task_id':'','creation_attempted':False,'audio':None,'status':'queued'}
            self._guard(metadata)
            c.execute('INSERT INTO narration_versions VALUES (?,?,?,?,?,?,?,?)',
                      (vid,pid,version,options.kind,approved['id'],json.dumps(metadata,ensure_ascii=False),stamp,stamp))
            progress={'phase':'queued','message':'Görev oluşturuluyor.','category':'none','task_id':''}
            c.execute('INSERT INTO narration_jobs VALUES (?,?,?,?,?,?,?,?)',(jid,pid,vid,'queued',json.dumps(progress),'',stamp,stamp))
        self.futures[jid]=self.executor.submit(self._run,jid)
        return {'job_id':jid,'narration_version_id':vid}

    def resume(self,pid,jid):
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            self.projects._row(c,pid);self._idle(c,pid)
            row=c.execute('SELECT * FROM narration_jobs WHERE project_id=? AND id=?',(pid,jid)).fetchone()
            if not row or row['status']!='error':raise NarrationError('invalid_request','Sürdürülebilir seslendirme görevi bulunamadı.',409)
            version=self._version(c,pid,row['narration_version_id']);meta=version['metadata']
            if not meta['task_id']:
                raise NarrationError('task_create_failed','Görev kimliği alınamadı. Yeni ücretli görev otomatik oluşturulmaz; AI33 görev geçmişini kontrol edip destek isteyin.',409)
            safe_task_id(meta['task_id'])
            c.execute("UPDATE narration_jobs SET status='queued',error_message='',updated_at=? WHERE id=?",(now(),jid))
        self.futures[jid]=self.executor.submit(self._run,jid)
        return {'job_id':jid}

    def select_active(self,pid,vid):
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            self.projects._row(c,pid);self._idle(c,pid);item=self._version(c,pid,vid)
            if item['kind']!='narration' or not item['metadata'].get('audio'):
                raise NarrationError('invalid_request','Yalnız tamamlanmış tam seslendirme aktif seçilebilir.',422)
            audio_path(self.projects,pid,item['metadata']['audio'])
            c.execute('INSERT INTO narration_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET active_version_id=excluded.active_version_id,updated_at=excluded.updated_at',(pid,vid,now()))
        return self.view(pid)

    def _checkpoint(self,job,meta,progress,status='running',error=''):
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            self.projects._row(c,job['project_id']);self._guard(progress)
            meta['status']=status
            self._save_metadata(c,job['narration_version_id'],meta)
            c.execute('UPDATE narration_jobs SET status=?,progress_json=?,error_message=?,updated_at=? WHERE id=?',
                      (status,json.dumps(progress,ensure_ascii=False),error,now(),job['id']))

    def _run(self,jid):
        started=time.monotonic();category='success';job=None;meta=None;progress={}
        try:
            with self.projects.lock,closing(self.projects._connection()) as c:
                row=c.execute('SELECT * FROM narration_jobs WHERE id=?',(jid,)).fetchone()
                if not row:return
                job=dict(row);meta=self._version(c,job['project_id'],job['narration_version_id'])['metadata']
                progress=json.loads(job['progress_json'])
            provider=self.factory(self.settings)
            if not meta['task_id']:
                if meta['creation_attempted']:raise NarrationError('task_create_failed','Görev oluşturma sonucu belirsiz. Yeni ücretli görev başlatılmadı; AI33 görev geçmişini kontrol edin.',409)
                if not provider.contract_ready:raise NarrationError('documentation_required','AI33 görev çıktı belgesi gerekli. Ücretli görev başlatılmadı.',409)
                self._guard(meta['text'])
                meta['creation_attempted']=True
                progress.update(phase='creating',message='Görev oluşturuluyor.')
                self._checkpoint(job,meta,progress)  # Persist BEFORE the single paid call.
                created=provider.synthesize(meta['text'],meta['voice_id'],{'speed':meta['speed']})
                meta['task_id']=safe_task_id(created['task_id']);self._guard(meta['task_id'])
                progress['task_id']=meta['task_id'];self._checkpoint(job,meta,progress)
            if meta.get('audio'):
                try:audio_path(self.projects,job['project_id'],meta['audio'])
                except (NarrationError,OSError):meta['audio']=None
            while not meta.get('audio'):
                if self.stop.is_set():raise NarrationError('interrupted','İşlem durdu. Görev kimliği korundu; Devam Et deyin.')
                if time.monotonic()-started>self.max_poll_seconds:
                    raise NarrationError('timeout','AI33 görevi hâlâ sürüyor. Görev kimliği korundu; Devam Et aynı görevi izler.')
                progress.update(phase='waiting',message='AI33 seslendirme hazırlıyor. Görev bekleniyor.')
                self._checkpoint(job,meta,progress)
                result=provider.get_job_status(meta['task_id'])  # INTERNAL normalized contract.
                if result['state']=='failed':raise NarrationError('task_failed','AI33 görevi başarısız oldu. Mevcut seslendirmeler korundu; görev geçmişini kontrol edin.')
                if result['state']=='complete':
                    progress.update(phase='downloading',message='Ses dosyası indiriliyor.')
                    self._checkpoint(job,meta,progress)
                    meta['audio']=self.downloader.download(job['project_id'],result['audio_url'],provider.output_hosts)
                    self._guard(meta['audio']);break
                if result['state']!='pending':raise NarrationError('unexpected_task_schema','AI33 görev yanıtı bu sürümün beklediği biçimden farklı.',502)
                self.stop.wait(self.poll_interval)
            meta.update(status='completed');progress.update(phase='complete',message='Tamamlandı. Ses dosyasını oynatabilirsiniz.',category='none')
            self._checkpoint(job,meta,progress,'completed')
            with self.projects.lock,closing(self.projects._connection()) as c,c:
                version=self._version(c,job['project_id'],job['narration_version_id'])
                if version['kind']=='narration':
                    current=self.scripts.repository.view(job['project_id'])['current']
                    if current and current['status']=='approved' and current['id']==version['source_script_version_id'] and script_fingerprint(current['text'])==meta['script_fingerprint']:
                        c.execute('INSERT INTO narration_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET active_version_id=excluded.active_version_id,updated_at=excluded.updated_at',(job['project_id'],version['id'],now()))
        except Exception as error:
            category=error.category if isinstance(error,NarrationError) else 'unexpected_backend'
            message=str(error) if isinstance(error,NarrationError) else 'Seslendirme işlemi tamamlanamadı. Görev ve mevcut dosyalar korundu; destek isteyin.'
            guard=SecretGuard(self.settings.secret_values());message=guard.clean(message)
            if job and meta:
                if isinstance(error,NarrationError) and error.remote_task_id and not meta['task_id']:
                    meta['task_id']=safe_task_id(error.remote_task_id)
                    self._guard(meta['task_id'])
                    progress['task_id']=meta['task_id']
                progress.update(category=category,message=message)
                if isinstance(error,NarrationError) and error.diagnostic:progress['diagnostic']=guard.clean(error.diagnostic)
                meta['status']='error'
                self._checkpoint(job,guard.clean(meta),guard.clean(progress),'error',message)
        finally:LOG.info('narration operation=job category=%s elapsed_ms=%.0f',category,(time.monotonic()-started)*1000)

    def handoff(self,pid):
        view=self.view(pid);active=view['active'];meta=active['metadata'] if active else {};audio=meta.get('audio') or {}
        return {'project_id':pid,'source_script_version_id':active['source_script_version_id'] if active else None,
                'narration_version_id':active['id'] if active else None,'audio_local_path':audio.get('local_path'),
                'audio_duration':audio.get('duration'),'voice_id':meta.get('voice_id'),'voice_provider':meta.get('voice_provider'),
                'speed':meta.get('speed'),'target_language':meta.get('target_language',view['target_language']),
                'transcript':None,'timing_source':'audio_duration' if audio.get('duration') else 'unknown',
                'scene_timing_source':'estimated','ready':bool(active and audio and not active['stale'] and not active.get('audio_missing'))}
