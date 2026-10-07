from contextlib import closing
import json
import os
from pathlib import Path
from uuid import uuid4

from app.projects import linked, now
from app.scripts.models import ScriptError, duration_metrics
from app.scripts.review import final_report, safe_review_issues

ACTIVE = ('queued', 'analyzing', 'planning', 'generating', 'checking')
STATUS_LABELS = {'queued': 'Oluşturuluyor', 'analyzing': 'Analiz ediliyor', 'planning': 'Plan hazırlanıyor',
                 'generating': 'Senaryo oluşturuluyor', 'checking': 'Son kontrol yapılıyor',
                 'draft': 'Taslak', 'approved': 'Onaylandı', 'analyzed': 'Analiz tamamlandı', 'error': 'Hata'}


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


class ScriptRepository:
    def __init__(self, projects):
        self.projects = projects

    def _file(self, project_id, name, content):
        root = self.projects._path(project_id)
        directory = root / 'script'
        if linked(directory) or (directory.exists() and not directory.is_dir()):
            raise ScriptError('Senaryo klasöründe dış konuma bağlantı var. Dosyaları korumak için işlem durduruldu.', 409)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise ScriptError('Senaryo klasörü açılamadı. Veri klasörünün yazılabilir olduğunu kontrol edin.', 503) from None
        target = directory / name
        if linked(target):
            raise ScriptError('Senaryo dosyası dış konuma bağlı. Dosya değiştirilmedi.', 409)
        temporary = directory / ('.write-' + uuid4().hex)
        try:
            with temporary.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except OSError:
            raise ScriptError('Senaryo dosyası kaydedilemedi. Veri klasörünün yazılabilir olduğunu kontrol edin; tamamlanan bölümler korundu.', 503) from None
        finally:
            temporary.unlink(missing_ok=True)

    def _idle(self, connection, project_id):
        row = connection.execute("SELECT 1 FROM script_jobs WHERE project_id=? AND status IN ('queued','analyzing','planning','generating','checking')", (project_id,)).fetchone()
        if row:
            raise ScriptError('Bu projede senaryo işlemi sürüyor. Tamamlanmasını bekleyin.', 409)

    def _current(self, connection, project_id):
        return connection.execute('SELECT v.* FROM script_versions v JOIN script_state s ON v.id=s.current_version_id WHERE s.project_id=? AND v.project_id=?', (project_id, project_id)).fetchone()

    def protect(self, connection, project_id, confirmed):
        current = self._current(connection, project_id)
        if current and current['status'] == 'approved' and not confirmed:
            raise ScriptError('Onaylı senaryonun yerine yeni çalışma seçilecek. Önce açık onay verin; eski onaylı sürüm korunur.', 409)

    def version(self, connection, project_id, version_id):
        row = connection.execute('SELECT * FROM script_versions WHERE project_id=? AND id=?', (project_id, version_id)).fetchone()
        if not row:
            raise ScriptError('Senaryo sürümü bulunamadı.', 404)
        return row

    def _public_version(self, row, full=False, target_minutes=1):
        if row is None:
            return None
        result = dict(row)
        options, report = json.loads(result.pop('options_json')), json.loads(result.pop('report_json'))
        # Repair public metrics/summaries from legacy reports without modifying
        # their database records, timestamps or script text.
        minutes = report.get('target_minutes', target_minutes)
        if type(minutes) not in (int, float) or minutes <= 0:
            minutes = target_minutes
        report = final_report(result['text'], minutes, options, report)
        result.update(word_count=report['word_count'], estimated_minutes=report['estimated_minutes'])
        result['status_label'] = STATUS_LABELS[result['status']]
        result['report'] = report
        if full:
            result['options'] = options
        else:
            result.pop('text')
        return result

    def view(self, project_id):
        with self.projects.lock, closing(self.projects._connection()) as connection:
            project = dict(self.projects._row(connection, project_id))
            versions = [self._public_version(row, target_minutes=project['target_duration_minutes']) for row in connection.execute('SELECT * FROM script_versions WHERE project_id=? ORDER BY version DESC', (project_id,))]
            current = self._public_version(self._current(connection, project_id), full=True, target_minutes=project['target_duration_minutes'])
            row = connection.execute('SELECT * FROM script_jobs WHERE project_id=? ORDER BY created_at DESC,id DESC LIMIT 1', (project_id,)).fetchone()
            job = self.public_job(row) if row else None
            return {'project_id': project_id, 'current': current, 'versions': versions, 'job': job,
                    'target_minutes': project['target_duration_minutes'], 'default_provider': project['script_engine'],
                    'status': job['status_label'] if job and job['status'] in ACTIVE + ('error',) else current['status_label'] if current else 'Oluşturulmadı'}

    def public_job(self, row):
        job = dict(row)
        progress = json.loads(job.pop('progress_json'))
        if 'reviews' in progress:
            progress['reviews'] = [{'consistent': review.get('consistent') is True,
                                    'issues': safe_review_issues(review.get('issues', []))}
                                   for review in progress['reviews'] if isinstance(review, dict)]
        job['options'] = json.loads(job.pop('options_json'))
        job.pop('input_json')
        job['progress'] = progress
        job['status_label'] = STATUS_LABELS[job['status']]
        job['completed_sections'] = len(progress.get('sections', []))
        job['partial_text'] = '\n\n'.join(section['text'] for section in progress.get('sections', []))
        correction = progress.get('duration_correction', {})
        if correction.get('applied'): job['partial_text'] = correction['final_text']
        return job

    def job(self, job_id):
        with self.projects.lock, closing(self.projects._connection()) as connection:
            row = connection.execute('SELECT * FROM script_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise ScriptError('Senaryo işlemi bulunamadı.', 404)
            return dict(row)

    def checkpoint(self, job_id, status, progress, error=''):
        with self.projects.lock:
            with closing(self.projects._connection()) as connection, connection:
                job = connection.execute('SELECT * FROM script_jobs WHERE id=?', (job_id,)).fetchone()
                if not job:
                    raise ScriptError('Proje silinmiş veya işlem bulunamadı.', 404)
                self.projects._row(connection, job['project_id'])
                connection.execute('UPDATE script_jobs SET status=?,progress_json=?,error_message=?,updated_at=? WHERE id=?', (status, dumps(progress), error, now(), job_id))
            # SQLite is the recovery source. A mirror failure must not lose completed text.
            self._file(job['project_id'], 'generation_progress.json', dumps({'job_id': job_id, 'status': status, 'error': error, **progress}))
            self._file(job['project_id'], 'job_' + job_id + '.json', dumps({'job_id': job_id, 'status': status, 'progress': progress}))
            if progress.get('blueprint'):
                self._file(job['project_id'], 'concept_blueprint.json', dumps(progress['blueprint']))
            if progress.get('plan'):
                self._file(job['project_id'], 'script_plan.json', dumps(progress['plan']))

    def create_version(self, project_id, text, provider, model, options, content_type, report, *, base_version=None, confirmed=False, generated=False, job_id=None, progress=None):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            project = dict(self.projects._row(connection, project_id))
            if not generated:
                self._idle(connection, project_id)
                self.protect(connection, project_id, confirmed)
            current = self._current(connection, project_id)
            if base_version is not None and (current is None or current['id'] != base_version):
                raise ScriptError('Geçerli sürüm başka bir sekmede değişti. Sayfayı yenileyip tekrar deneyin.', 409)
            version = connection.execute('SELECT COALESCE(MAX(version),0)+1 FROM script_versions WHERE project_id=?', (project_id,)).fetchone()[0]
            stamp, version_id = now(), uuid4().hex
            metrics = duration_metrics(text, report.get('target_minutes', project['target_duration_minutes']) if generated else project['target_duration_minutes'], options)
            report = final_report(text, metrics['target_minutes'], options, report)
            connection.execute('INSERT INTO script_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (version_id, project_id, version, provider, model, options['language'], options['mode'], content_type,
                 text, dumps(options), dumps(report), 'draft', metrics['word_count'], metrics['estimated_minutes'], stamp, stamp, None))
            connection.execute('INSERT INTO script_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET current_version_id=excluded.current_version_id, updated_at=excluded.updated_at', (project_id, version_id, stamp))
            connection.execute('UPDATE projects SET updated_at=? WHERE id=?', (stamp, project_id))
            if job_id:
                progress['version_id'] = version_id
                connection.execute('UPDATE script_jobs SET progress_json=? WHERE id=? AND project_id=?', (dumps(progress), job_id, project_id))
            self._file(project_id, f'script_v{version}.txt', text)
            self._file(project_id, f'script_v{version}.json', dumps({'id': version_id, 'version': version, 'provider': provider, 'model': model, 'mode': options['mode'], 'status': 'draft', **metrics, 'report': report}))
            self._file(project_id, 'current_script.json', dumps({'version_id': version_id, 'version': version, 'status': 'draft'}))
            return version_id

    def select(self, project_id, version_id, confirmed=False):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            self.projects._row(connection, project_id)
            self._idle(connection, project_id)
            row = self.version(connection, project_id, version_id)
            current = self._current(connection, project_id)
            if current is None or current['id'] != row['id']:
                self.protect(connection, project_id, confirmed)
            connection.execute('INSERT INTO script_state VALUES (?,?,?) ON CONFLICT(project_id) DO UPDATE SET current_version_id=excluded.current_version_id,updated_at=excluded.updated_at', (project_id, version_id, now()))
            self._file(project_id, 'current_script.json', dumps({'version_id': version_id, 'version': row['version'], 'status': row['status']}))

    def approve(self, project_id, version_id, confirmed):
        if confirmed is not True:
            raise ScriptError('Senaryoyu onaylamak için açık onay gerekli.')
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            self.projects._row(connection, project_id)
            self._idle(connection, project_id)
            row = self.version(connection, project_id, version_id)
            current = self._current(connection, project_id)
            if current is None or current['id'] != version_id:
                raise ScriptError('Yalnızca geçerli sürüm onaylanabilir. Önce sürümü seçin.', 409)
            if not row['text'].strip():
                raise ScriptError('Boş senaryo onaylanamaz.')
            stamp = now()
            connection.execute("UPDATE script_versions SET status='approved',approved_at=?,updated_at=? WHERE id=?", (stamp, stamp, version_id))
            connection.execute('UPDATE projects SET updated_at=? WHERE id=?', (stamp, project_id))
            self._file(project_id, 'current_script.json', dumps({'version_id': version_id, 'version': row['version'], 'status': 'approved'}))
            self._file(project_id, f'script_v{row["version"]}.json', dumps({'id': version_id, 'version': row['version'], 'provider': row['provider'], 'model': row['model'], 'status': 'approved', 'word_count': row['word_count'], 'estimated_minutes': row['estimated_minutes'], 'approved_at': stamp}))

    def approved_current(self, project_id):
        current = self.view(project_id)['current']
        if not current or current['status'] != 'approved':
            raise ScriptError('Geçerli senaryo henüz onaylanmadı. Önce Senaryo ekranından onaylayın.', 409)
        return current
