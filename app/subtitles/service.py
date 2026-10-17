"""Local immutable subtitle versions. No network client/provider factory is used."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import logging
import sqlite3
import time
from uuid import uuid4

from app.projects import now
from app.narration.audio import audio_path
from app.narration.models import NarrationError, script_fingerprint
from app.scripts.engine import SecretGuard
from app.stock.download import asset_path
from app.stock.models import StockError
from app.subtitles import files
from app.subtitles.duration import discover_duration
from app.subtitles.models import SubtitleError, TIMING_SOURCE, TIMING_LABEL, validate_cues
from app.subtitles.timing import normalize, generate, edited_boundaries, map_scenes, project_slots

LOG = logging.getLogger('uvicorn.error.subtitles')


def digest_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''): digest.update(chunk)
    return digest.hexdigest()


class SubtitleService:
    def __init__(self,narration,production,stock):
        self.narration,self.production,self.stock=narration,production,stock
        self.projects=narration.projects
        self.scripts=narration.scripts
        self.settings=narration.settings

    def _guard(self,value): SecretGuard(self.settings.secret_values()).validate(value)

    def _source(self,c,pid,*,require_current=True):
        row=c.execute('SELECT active_version_id FROM narration_state WHERE project_id=?',(pid,)).fetchone()
        if not row or not row[0]: raise SubtitleError('narration_required','Önce tamamlanmış bir seslendirmeyi aktif seçin.',409)
        version=self.narration._version(c,pid,row[0]);meta=version['metadata']
        if version['kind']!='narration' or meta['status']!='completed' or not meta.get('audio'):
            raise SubtitleError('narration_required','Aktif tam seslendirme henüz tamamlanmadı.',409)
        script=self.scripts.repository.version(c,pid,version['source_script_version_id'])
        if script_fingerprint(script['text'])!=meta['script_fingerprint'] or meta.get('text')!=script['text'] or len(script['text'])!=meta['character_count']:
            raise SubtitleError('source_mismatch','Seslendirme kaynağı doğrulanamadı. Senaryo ve ses dosyaları korundu.',409)
        if require_current:
            current=self.scripts.repository._current(c,pid)
            if not current or current['status']!='approved' or current['id']!=script['id'] or script_fingerprint(current['text'])!=meta['script_fingerprint']:
                raise SubtitleError('stale_source','Aktif seslendirme eski senaryoya ait. Yeni onaylı senaryoyla eşleşen seslendirmeyi seçin.',409)
        try: path=audio_path(self.projects,pid,meta['audio'])
        except (NarrationError,OSError):
            raise SubtitleError('invalid_audio','Aktif yerel ses dosyası eksik veya değişmiş. Dosyaları silmeden Seslendirme ekranını kontrol edin.',409) from None
        try:identity=digest_file(path)
        except OSError:
            raise SubtitleError('invalid_audio','Yerel ses dosyası okunamadı. Açık dosyaları kapatıp tekrar deneyin.',409) from None
        if identity!=meta['audio'].get('sha256'):
            raise SubtitleError('audio_changed','Yerel ses dosyası değişmiş; altyazı kaynağı doğrulanamadı. Önceki sürümler korundu.',409)
        return version,dict(script),path

    def refresh_duration(self,pid):
        started=time.monotonic();category='none'
        try:
            with self.projects.lock,closing(self.projects._connection()) as c,c:
                self.projects._row(c,pid)
                version,_,path=self._source(c,pid,require_current=False)
                meta=version['metadata'];audio=meta['audio']
                duration,method=discover_duration(path,audio.get('duration'))
                if duration is None:
                    raise SubtitleError('duration_required','Ses süresi ölçülemedi. Yerel ses dosyasının açıldığını kontrol edin; sorun sürerse Tanılama ekranını açın.',409)
                if audio.get('duration')!=duration or audio.get('duration_message'):
                    audio.update(duration=duration,duration_message='',duration_method=method)
                    self.narration._save_metadata(c,version['id'],meta)
                return {'narration_version_id':version['id'],'duration':duration,'method':method}
        except SubtitleError as error:
            category=error.category;raise
        finally: LOG.info('subtitles operation=duration category=%s elapsed_ms=%.0f',category,(time.monotonic()-started)*1000)

    def _version(self,c,pid,vid):
        row=c.execute('SELECT * FROM subtitle_versions WHERE project_id=? AND id=?',(pid,vid)).fetchone()
        if not row: raise SubtitleError('missing_version','Altyazı sürümü bulunamadı.',404)
        result=dict(row);result['metadata']=json.loads(result.pop('metadata_json'))
        result['cues']=[{'index':r['cue_index'],'start':r['start'],'end':r['end'],'text':r['text']} for r in c.execute('SELECT * FROM subtitle_cues WHERE version_id=? ORDER BY cue_index',(vid,))]
        return result

    def _stale(self,version,source):
        if source is None: return True
        voice,script,_=source;meta=version['metadata']
        return (version['source_narration_version_id']!=voice['id'] or version['source_script_version_id']!=script['id']
                or meta['script_fingerprint']!=script_fingerprint(script['text'])
                or meta['audio_identity']!=voice['metadata']['audio']['sha256'])

    def view(self,pid):
        project=self.projects.get(pid);voice=self.narration.view(pid)['active']
        message='';source=None
        try:
            if voice: self.refresh_duration(pid)
        except SubtitleError as error: message=str(error)
        with self.projects.lock,closing(self.projects._connection()) as c:
            try: source=self._source(c,pid)
            except SubtitleError as error:
                if not message:message=str(error)
            voice=self.narration.view(pid)['active']
            rows=c.execute('SELECT id FROM subtitle_versions WHERE project_id=? ORDER BY version DESC',(pid,)).fetchall()
            active=c.execute('SELECT active_version_id FROM subtitle_state WHERE project_id=?',(pid,)).fetchone()
            versions=[];chosen=None
            for row in rows:
                item=self._version(c,pid,row[0]);item['stale']=self._stale(item,source)
                item['stale_message']='Eski seslendirme veya senaryo sürümüne ait' if item['stale'] else ''
                item['metadata'].pop('word_boundaries',None)
                if active and active[0]==item['id']: chosen=deepcopy(item)
                item.pop('cues');versions.append(item)
            result={'project_id':pid,'target_language':project['language'],'narration':voice,'timing_source':TIMING_SOURCE,
                    'timing_label':TIMING_LABEL,'versions':versions,'active':chosen,'can_generate':bool(source and not message),
                    'message':message or 'Altyazı ve zamanlama yerel olarak hazırlanır; API kredisi kullanılmaz.'}
            self._guard(result);return result

    def _commit(self,c,pid,voice,script,cues,metadata):
        self._guard(cues);self._guard(metadata)
        number=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM subtitle_versions WHERE project_id=?',(pid,)).fetchone()[0]
        # Orphaned files from an interrupted transaction are retained, never overwritten.
        folder=files.directory(self.projects,pid)
        while any((folder/f'subtitles-v{number}.{ext}').exists() or (folder/f'subtitles-v{number}.{ext}').is_symlink() for ext in ('srt','vtt')): number+=1
        vid,stamp=uuid4().hex,now()
        metadata.update(srt_local_path=f'subtitles/subtitles-v{number}.srt',vtt_local_path=f'subtitles/subtitles-v{number}.vtt')
        created=[]
        try:
            for ext,content in (('srt',files.srt(cues)),('vtt',files.vtt(cues))):
                path=files.file_path(self.projects,pid,metadata[f'{ext}_local_path'],must_exist=False)
                files.atomic_write(path,content);created.append(path)
            c.execute('INSERT INTO subtitle_versions VALUES (?,?,?,?,?,?,?,?)',
                      (vid,pid,number,script['id'],voice['id'],json.dumps(metadata,ensure_ascii=False),stamp,stamp))
            c.executemany('INSERT INTO subtitle_cues VALUES (?,?,?,?,?)',[(vid,q['index'],q['start'],q['end'],q['text']) for q in cues])
            c.execute('INSERT INTO subtitle_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET active_version_id=excluded.active_version_id,updated_at=excluded.updated_at',(pid,vid,stamp))
        except Exception:
            for path in created:
                if not path.is_symlink():path.unlink(missing_ok=True)
            raise
        return vid

    def create(self,pid,payload):
        started=time.monotonic();category='none'
        try:
            if not isinstance(payload,dict) or set(payload)!={'regenerate_confirmed'} or type(payload['regenerate_confirmed']) is not bool:
                raise SubtitleError('invalid_request','Altyazı oluşturma bilgileri geçersiz.')
            self.refresh_duration(pid)
            with self.projects.lock,closing(self.projects._connection()) as c,c:
                c.execute('BEGIN IMMEDIATE')
                voice,script,_=self._source(c,pid)
                if c.execute('SELECT 1 FROM subtitle_versions WHERE project_id=?',(pid,)).fetchone() and not payload['regenerate_confirmed']:
                    raise SubtitleError('confirmation_required','Yeni bir altyazı sürümü oluşturulacak. Mevcut sürüm korunacak.',409)
                duration=voice['metadata']['audio']['duration']
                cues,boundaries=generate(script['text'],duration)
                metadata={'script_fingerprint':script_fingerprint(script['text']), 'audio_identity':voice['metadata']['audio']['sha256'],
                          'audio_local_path':voice['metadata']['audio']['local_path'], 'audio_duration':duration,
                          'target_language':voice['metadata']['target_language'], 'timing_source':TIMING_SOURCE,
                          'text_matches_narration':True,'word_boundaries':boundaries,'origin':'generated','parent_version_id':None}
                self._commit(c,pid,voice,script,cues,metadata)
            return self.view(pid)
        except SubtitleError as error: category=error.category;raise
        except (OSError,sqlite3.Error):
            category='local_storage'
            raise SubtitleError(category,'Altyazılar tamamen kaydedilemedi. Önceki aktif sürüm korundu; boş alanı ve yazma iznini kontrol edin.',503) from None
        except Exception:
            category='unexpected_backend';raise
        finally:LOG.info('subtitles operation=create category=%s elapsed_ms=%.0f',category,(time.monotonic()-started)*1000)

    def edit(self,pid,vid,payload,*,allow_empty=False,preserve_clock=False):
        if not isinstance(payload,dict) or set(payload)!={'cues'}:
            raise SubtitleError('invalid_request','Yalnız altyazı metni ve zamanları düzenlenebilir.')
        try:
            with self.projects.lock,closing(self.projects._connection()) as c,c:
                c.execute('BEGIN IMMEDIATE')
                old=self._version(c,pid,vid);source=self._source(c,pid)
                if self._stale(old,source): raise SubtitleError('stale_source','Eski altyazı sürümünü düzenlemek için eşleşen güncel seslendirmeyi seçin.',409)
                voice,script,_=source;metadata=deepcopy(old['metadata'])
                cues=validate_cues(payload['cues'],metadata['audio_duration'],allow_empty=allow_empty)
                metadata.update(text_matches_narration=normalize(' '.join(q['text'] for q in cues))==normalize(script['text']),
                                word_boundaries=metadata['word_boundaries'] if preserve_clock else edited_boundaries(script['text'],cues,metadata['word_boundaries']),
                                origin='manual',parent_version_id=vid)
                self._commit(c,pid,voice,script,cues,metadata)
            return self.view(pid)
        except (OSError,sqlite3.Error):
            raise SubtitleError('local_storage','Altyazı değişiklikleri kaydedilemedi. Önceki sürüm korundu; boş alanı ve yazma iznini kontrol edin.',503) from None

    def activate(self,pid,vid,payload):
        if payload!={'confirm':True} or type(payload.get('confirm')) is not bool:
            raise SubtitleError('confirmation_required','Aktif altyazı seçimini onaylayın.')
        with self.projects.lock,closing(self.projects._connection()) as c,c:
            self.projects._row(c,pid);item=self._version(c,pid,vid)
            for ext in ('srt','vtt'): files.file_path(self.projects,pid,item['metadata'][f'{ext}_local_path'])
            c.execute('INSERT INTO subtitle_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET active_version_id=excluded.active_version_id,updated_at=excluded.updated_at',(pid,vid,now()))
        return self.view(pid)

    def export(self,pid,vid,ext):
        if ext not in ('srt','vtt'):raise SubtitleError('invalid_format','SRT veya VTT dosyası seçin.',404)
        with self.projects.lock,closing(self.projects._connection()) as c:
            self.projects._row(c,pid);item=self._version(c,pid,vid)
            return files.file_path(self.projects,pid,item['metadata'][f'{ext}_local_path'])

    def pipeline_status(self,pid):
        """Read-only pipeline check; no probing, providers or stock-state updates."""
        with self.projects.lock,closing(self.projects._connection()) as c:
            active=c.execute('SELECT active_version_id FROM subtitle_state WHERE project_id=?',(pid,)).fetchone()
            if not active or not active[0]:return 'Bekliyor'
            try:
                item=self._version(c,pid,active[0]);source=self._source(c,pid)
                if self._stale(item,source):return 'Eski sürüm / kontrol gerekli'
                for ext in ('srt','vtt'):files.file_path(self.projects,pid,item['metadata'][f'{ext}_local_path'])
                return 'Hazır'
            except (SubtitleError,OSError):return 'Eski sürüm / kontrol gerekli'

    def stock_ready(self,pid,plan):
        with self.projects.lock,closing(self.projects._connection()) as c:
            row=c.execute('SELECT state_json FROM stock_plans WHERE project_id=? AND plan_id=?',(pid,plan['plan_id'])).fetchone()
            if not row:return False
            slots=json.loads(row[0])['slots']
            for slot in slots:
                if slot['status']!='complete' or not slot.get('selected_media'):return False
                try:asset_path(self.projects,pid,slot['selected_media'])
                except (StockError,OSError):return False
            return bool(slots)

    def handoff(self,pid):
        with self.projects.lock,closing(self.projects._connection()) as c:
            self.projects._row(c,pid)
            active=c.execute('SELECT active_version_id FROM subtitle_state WHERE project_id=?',(pid,)).fetchone()
            result={'contract_version':1,'project_id':pid,'ready':False,'timing_source':TIMING_SOURCE,'subtitles':[],'scenes':[],'stock_slots':[], 'warnings':[]}
            if not active or not active[0]:result['warnings'].append('Önce altyazıları oluşturun.');return result
            item=self._version(c,pid,active[0]);meta=item['metadata']
            result.update(source_script_version_id=item['source_script_version_id'],narration_version_id=item['source_narration_version_id'],
                          subtitle_version_id=item['id'],target_language=meta['target_language'],audio_local_path=meta['audio_local_path'],
                          audio_duration=meta['audio_duration'],subtitles=item['cues'],text_matches_narration=meta['text_matches_narration'],
                          srt_local_path=meta['srt_local_path'],vtt_local_path=meta['vtt_local_path'])
            try:
                source=self._source(c,pid)
                if self._stale(item,source):raise SubtitleError('stale_source','Altyazı sürümü eski seslendirme veya senaryoya ait.',409)
                for ext in ('srt','vtt'):files.file_path(self.projects,pid,meta[f'{ext}_local_path'])
                plan=self.production.handoff(pid)
                if plan['source_script_version_id']!=item['source_script_version_id']:raise SubtitleError('scene_source_mismatch','Sahne planı altyazı kaynağıyla eşleşmiyor.',409)
                scenes=map_scenes(source[1]['text'],plan['scenes'],meta['word_boundaries'],meta['audio_duration'])
                row=c.execute('SELECT source_version_id,state_json FROM stock_plans WHERE project_id=? AND plan_id=?',(pid,plan['plan_id'])).fetchone()
                result.update(scene_plan_id=plan['plan_id'],scenes=scenes)
                if not row or row['source_version_id']!=item['source_script_version_id']:
                    result['warnings'].append('Eşleşen stok medya planı henüz hazır değil.');return result
                state=json.loads(row['state_json'])
                # Read existing slots only; StockService.view/_ensure would mutate state.
                result['stock_slots']=project_slots(scenes,state['slots'])
                complete=bool(result['stock_slots'])
                for slot in state['slots']:
                    if slot['status']!='complete' or not slot.get('selected_media'):complete=False;continue
                    try:asset_path(self.projects,pid,slot['selected_media'])
                    except (StockError,OSError):complete=False
                if {q['scene_id'] for q in result['stock_slots']}!={s['scene_id'] for s in scenes}:complete=False
                result['ready']=complete
                if not complete:result['warnings'].append('Bazı stok medya yuvaları veya yerel dosyaları henüz hazır değil.')
                if not meta['text_matches_narration']:result['warnings'].append('Altyazı metni seslendirme metninden farklı. Sahne zamanları özgün anlatım üzerinden korunur.')
            except (SubtitleError,NarrationError,StockError) as error:result['warnings'].append(str(error))
            except Exception as error:
                from app.scripts.models import ScriptError
                if isinstance(error,ScriptError):result['warnings'].append('Güncel onaylı sahne planı gerekli.')
                else:raise
            self._guard(result);return result
