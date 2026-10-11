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
from datetime import datetime,timedelta,timezone

from app.projects import now
from app.scripts.engine import SecretGuard
from app.scripts.models import ScriptError
from app.narration.audio import AudioDownloader,audio_path,store_upload
from app.narration.models import (NarrationError,PREVIEW_TEXT,Voice,script_fingerprint,
                                 validate_input,safe_task_id,VOICE_ID_PREFIXES)
from app.narration.provider import make_tts_provider,text_matches,parse_time

LOG=logging.getLogger('uvicorn.error.narration')
ACTIVE=('queued','running','verifying')
LABELS={'queued':'Görev oluşturuluyor','running':'AI33 seslendirme hazırlıyor','verifying':'Doğrulanıyor',
        'completed':'Tamamlandı','error':'Hata'}
DUPLICATE_WINDOW=timedelta(minutes=15)
NOT_FOUND=('AI33 görev geçmişinde bu isteğe ait görev bulunamadı; büyük olasılıkla kredi harcanmadı. '
           'Bir süre sonra “AI33’ten kurtar” ile tekrar arayabilir veya sesi elle yükleyebilirsiniz.')


class NarrationService:
    def __init__(self,scripts,settings):
        self.scripts,self.settings=scripts,settings;self.projects=scripts.projects
        self.factory=make_tts_provider;self.downloader=AudioDownloader(self.projects)
        self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='narration')
        self.futures={};self.stop=Event();self.poll_interval=3;self.max_poll_seconds=1800
        # AI33 can take minutes before a sent task shows up in its history.
        self.verify_interval=20;self.verify_seconds=900

    def close(self):
        self.stop.set();self.executor.shutdown(wait=True,cancel_futures=True)

    def recover(self):
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            for row in c.execute("SELECT project_id,narration_version_id FROM narration_jobs WHERE status IN ('queued','running','verifying')").fetchall():
                item=self._version(c,row['project_id'],row['narration_version_id'])
                item['metadata']['status']='error'
                self._save_metadata(c,item['id'],item['metadata'])
            c.execute("UPDATE narration_jobs SET status='error',error_message=?,updated_at=? WHERE status IN ('queued','running','verifying')",
                      ('Uygulama kapanırken işlem durdu. Devam Et veya AI33’ten kurtar aynı görevi izler; yeni kredi harcanmaz.',now()))

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
        if c.execute("SELECT 1 FROM narration_jobs WHERE project_id=? AND status IN ('queued','running','verifying')",(pid,)).fetchone():
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
            if not any(voice['voice_id'].startswith(p) and len(voice['voice_id'])>len(p) for p in VOICE_ID_PREFIXES) or any(c.isspace() for c in voice['voice_id']):
                raise NarrationError('invalid_voice','Ses kimliği geçersiz. Ayarlar bölümünden doğrulanmış bir ses seçin.',422)
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
                      'text':text,'task_id':'','creation_attempted':False,'audio':None,'status':'queued',
                      'force_new_task':options.force_new_task is True}
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
            if meta['task_id']:safe_task_id(meta['task_id'])
            elif not meta['creation_attempted']:
                raise NarrationError('invalid_request','Bu sürüm için AI33 görevi gönderilmemiş. Yeni seslendirme oluşturun.',409)
            # Without an id the worker only searches AI33 history; never a new paid POST.
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

    def linked_task_ids(self,c):
        """Task ids already owned by a local version (any project)."""
        ids=set()
        for row in c.execute('SELECT metadata_json FROM narration_versions'):
            task=json.loads(row[0]).get('task_id')
            if task:ids.add(task)
        return ids

    def recover_version(self,pid,vid):
        """'AI33’ten kurtar': find this version's task in AI33 history and finish it."""
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            self.projects._row(c,pid);self._idle(c,pid);item=self._version(c,pid,vid);meta=item['metadata']
            if meta.get('audio'):raise NarrationError('invalid_request','Bu sürümün ses dosyası zaten hazır.',409)
            if not meta.get('task_id') and not meta.get('creation_attempted'):
                raise NarrationError('invalid_request','Bu sürüm için AI33 görevi gönderilmemiş. Yeni seslendirme oluşturun.',409)
            meta['recovery_requested']=True;self._save_metadata(c,vid,meta)
            jid,stamp=uuid4().hex,now()
            progress={'phase':'verifying','message':'AI33 görev geçmişinde aranıyor.','category':'none','task_id':meta.get('task_id','')}
            c.execute('INSERT INTO narration_jobs VALUES (?,?,?,?,?,?,?,?)',(jid,pid,vid,'queued',json.dumps(progress),'',stamp,stamp))
        self.futures[jid]=self.executor.submit(self._run,jid)
        return {'job_id':jid,'narration_version_id':vid}

    def upload_audio(self,pid,vid,format,data):
        """Attach an audio file the owner downloaded from the AI33 panel."""
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            self.projects._row(c,pid);self._idle(c,pid);item=self._version(c,pid,vid);meta=item['metadata']
            if meta.get('audio'):
                try:present=bool(audio_path(self.projects,pid,meta['audio']))
                except (NarrationError,OSError):present=False  # Missing/changed file may be replaced.
                if present:raise NarrationError('invalid_request','Bu sürümün ses dosyası zaten hazır; mevcut dosya korunur.',409)
        audio=store_upload(self.projects,pid,format,data)
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            item=self._version(c,pid,vid);meta=item['metadata']
            meta.update(audio=audio,status='completed',audio_source='manual_upload');self._save_metadata(c,vid,meta)
            c.execute("UPDATE narration_jobs SET status='completed',error_message='',progress_json=?,updated_at=? WHERE narration_version_id=? AND status!='completed'",
                      (json.dumps({'phase':'complete','message':'Ses dosyası elle yüklendi.','category':'none','task_id':meta.get('task_id','')}),now(),vid))
            self._activate_if_current(c,item)
        return self.view(pid)

    def _activate_if_current(self,c,version):
        meta=version['metadata']
        if version['kind']!='narration':return
        current=self.scripts.repository.view(version['project_id'])['current']
        if current and current['status']=='approved' and current['id']==version['source_script_version_id'] and script_fingerprint(current['text'])==meta['script_fingerprint']:
            c.execute('INSERT INTO narration_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET active_version_id=excluded.active_version_id,updated_at=excluded.updated_at',(version['project_id'],version['id'],now()))

    def _matches(self,provider,meta,anchor,before,after):
        """Unlinked AI33 tasks with the exact text and voice near `anchor`."""
        if not callable(getattr(provider,'task_history',None)):
            raise NarrationError('task_history_unavailable','AI33 görev geçmişi okunamadı; görev doğrulanamadı. Yeni kredi harcanmadı. Sesi elle yükleyebilirsiniz.',409)
        history=provider.task_history()
        with self.projects.lock,closing(self.projects._connection()) as c:linked=self.linked_task_ids(c)
        same=[item for item in history if item['task_id'] not in linked and item['voice_id']==meta['voice_id'] and text_matches(item,meta['text'])]
        found=[]
        for item in same:
            stamp=item['created_at']
            if anchor and stamp is not None and not (anchor-before<=stamp<=anchor+after):continue
            if anchor and stamp is None and not meta.get('recovery_requested'):continue
            found.append(item)
        if not found and meta.get('recovery_requested') and same:
            # The owner asked explicitly. AI33's created_at time zone is not
            # verified; if no task falls in the window, take the oldest
            # unlinked task with this exact text and voice (same narration).
            meta['recovery_time_check']='skipped'
            return sorted(same,key=lambda i:i['created_at'] or datetime.max.replace(tzinfo=timezone.utc))
        # Nearest to the local send time first: two same-text versions sent a
        # minute apart each get their own task.
        found.sort(key=lambda i:abs((i['created_at']-anchor).total_seconds()) if anchor and i['created_at'] else 1e9)
        return found

    def _verify(self,job,meta,progress,provider,wait):
        """A sent request whose answer was lost: find it in AI33 history."""
        anchor=parse_time(meta.get('creation_attempted_at') or job.get('version_created_at'))
        deadline=time.monotonic()+(self.verify_seconds if wait else 3*self.verify_interval)
        while True:
            if self.stop.is_set():raise NarrationError('interrupted','İşlem durdu. AI33’ten kurtar ile aynı görev aranır; yeni kredi harcanmaz.')
            progress.update(phase='verifying',message='Doğrulanıyor: AI33 görev geçmişinde bu istek aranıyor. Yeni kredi harcanmaz.')
            self._checkpoint(job,meta,progress,'verifying')
            try:found=self._matches(provider,meta,anchor,timedelta(minutes=2),timedelta(hours=1) if meta.get('recovery_requested') else timedelta(minutes=20))
            except NarrationError as error:
                if error.category in ('key_rejected','task_history_unavailable'):raise
                found=[]
            if found:
                meta['task_id']=found[0]['task_id'];meta['recovered_from_history']=True;self._guard(meta['task_id'])
                progress.update(task_id=meta['task_id'],message='AI33 görevi bulundu; ses bekleniyor.')
                self._checkpoint(job,meta,progress)
                LOG.info('narration operation=verify result=found')
                return
            if time.monotonic()>=deadline:raise NarrationError('task_not_found',NOT_FOUND,409)
            self.stop.wait(self.verify_interval)

    def _recent_duplicate(self,provider,meta):
        """Before a NEW paid task: reuse an identical AI33 task from the last 15 min."""
        if not callable(getattr(provider,'task_history',None)):return None,False
        try:history=provider.task_history()
        except NarrationError:return None,False  # No history: same as before, send once.
        with self.projects.lock,closing(self.projects._connection()) as c:linked=self.linked_task_ids(c)
        current=datetime.now(timezone.utc);limit=current-DUPLICATE_WINDOW;owned=False
        for item in history:
            if item['voice_id']!=meta['voice_id'] or not text_matches(item,meta['text']) or item['state']=='failed':continue
            # Unknown or skewed (future) clocks never count as "recent".
            if item['created_at'] is None or not limit<=item['created_at']<=current+timedelta(minutes=2):continue
            if item['task_id'] in linked:owned=True;continue
            return item,owned
        return None,owned

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
            with self.projects.lock,closing(self.projects._connection()) as c:
                job['version_created_at']=self._version(c,job['project_id'],job['narration_version_id'])['created_at']
            if not meta['task_id'] and meta['creation_attempted']:
                # Earlier send whose answer was lost (or the owner pressed
                # "AI33’ten kurtar"): search history only, never a second POST.
                self._verify(job,meta,progress,provider,wait=not meta.get('recovery_requested'))
            if not meta['task_id']:
                if not provider.contract_ready:raise NarrationError('documentation_required','AI33 görev çıktı belgesi gerekli. Ücretli görev başlatılmadı.',409)
                self._guard(meta['text'])
                if not meta.get('force_new_task'):
                    existing,owned=self._recent_duplicate(provider,meta)
                    if existing:
                        meta['task_id']=existing['task_id'];meta['reused_existing_task']=True;self._guard(meta['task_id'])
                        progress.update(task_id=meta['task_id'],message='AI33’te son 15 dakikada aynı metin ve sesle oluşturulmuş görev bulundu; yeni kredi harcanmadı.')
                        self._checkpoint(job,meta,progress)
                    elif owned:
                        raise NarrationError('recent_duplicate','Aynı metin ve sesle son 15 dakikada oluşturulmuş bir AI33 görevi zaten bir sürüme bağlı. '
                                             'Kredi harcanmadı. Yine de yeni ses istiyorsanız “Yeni görev oluştur (kredi harcanır)” seçeneğini kullanın.',409)
            if not meta['task_id']:
                meta['creation_attempted']=True;meta['creation_attempted_at']=now()
                progress.update(phase='creating',message='Görev oluşturuluyor.')
                self._checkpoint(job,meta,progress)  # Persist BEFORE the single paid call.
                try:
                    created=provider.synthesize(meta['text'],meta['voice_id'],{'speed':meta['speed']})
                except NarrationError as error:
                    if error.category!='creation_unconfirmed':raise
                    LOG.info('narration operation=create result=unconfirmed')
                    self._verify(job,meta,progress,provider,wait=True)
                else:
                    meta['task_id']=safe_task_id(created['task_id']);self._guard(meta['task_id'])
                    progress['task_id']=meta['task_id'];self._checkpoint(job,meta,progress)
            if meta.get('audio'):
                try:audio_path(self.projects,job['project_id'],meta['audio'])
                except (NarrationError,OSError):meta['audio']=None
            polling_started=time.monotonic()
            while not meta.get('audio'):
                if self.stop.is_set():raise NarrationError('interrupted','İşlem durdu. Görev kimliği korundu; Devam Et deyin.')
                if time.monotonic()-polling_started>self.max_poll_seconds:
                    raise NarrationError('timeout','AI33 görevi hâlâ sürüyor. Görev kimliği korundu; Devam Et aynı görevi izler.')
                progress.update(phase='waiting',message='AI33 seslendirme hazırlıyor. Görev bekleniyor.')
                self._checkpoint(job,meta,progress)
                result=provider.get_job_status(meta['task_id'])  # INTERNAL normalized contract.
                if result.get('progress') is not None:progress['percent']=result['progress']
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
                self._activate_if_current(c,self._version(c,job['project_id'],job['narration_version_id']))
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
                'transcript':None,'timing_source':'audio_duration' if audio else 'unknown',
                'scene_timing_source':'estimated','ready':bool(active and audio and not active['stale'] and not active.get('audio_missing'))}
