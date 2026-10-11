"""AI director (Gemini free tier by default, Claude on request): purpose → script → (auto) approval → edit plan.

The owner enters only topic, language and target duration. Each step reuses
the existing, tested engines (script jobs, visual scene plan jobs), so
narration and subtitle flows are unchanged. Progress lives in the project's
script folder (director_state.json) and is shown on the script page. A failed
step never switches provider silently: backups are offered and used only
after the owner picks one.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from threading import Event, Lock

from app.ai_usage import CURRENT_PROJECT
from app.languages import LANGUAGES
from app.projects import now
from app.providers.base import ScriptProviderError
from app.providers.claude import BACKUP_WORTHY
from app.scripts.models import ScriptError
from app.scripts.storage import dumps

LOG = logging.getLogger('uvicorn.error.director')
# Spoken pace per language (words/minute). German ~130 as requested.
PACE = {'de': (125, 135), 'en': (140, 155), 'es': (145, 160), 'fr': (140, 155), 'tr': (115, 130)}
PURPOSE_FIELDS = {'audience': 300, 'main_message': 400, 'tone': 120, 'hook': 400, 'viewer_promise': 400, 'content_type': 120, 'summary': 900}
PURPOSE_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': list(PURPOSE_FIELDS),
                  'properties': {name: {'type': 'string'} for name in PURPOSE_FIELDS}}
STEPS = {'purpose': 'Amaç belirleniyor', 'script': 'Senaryo yazılıyor', 'approve': 'Senaryo onaylanıyor',
         'plan': 'Kurgu planı hazırlanıyor', 'done': 'Tamamlandı'}
BUSY = ('queued', 'running')


def purpose_prompt(project):
    language = LANGUAGES.get(project['language'], project['language'])
    return (f'Plan the PURPOSE of a new, original YouTube video before any writing.\n'
            f'Topic: {project["topic"]}\nSpoken language of the video: {project["language"]} ({language})\n'
            f'Target duration: {project["target_duration_minutes"]} minutes\n\n'
            'Return JSON with: audience (who watches and why), main_message (the one idea viewers keep), '
            'tone (2-4 words), hook (the opening question/tension in one sentence), viewer_promise '
            '(what the viewer will understand by the end), content_type (e.g. documentary explainer), '
            'summary (3-5 short sentences). Write every field in TURKISH, because the channel owner '
            'reads Turkish; the script itself will later be written in the spoken language. '
            'Do not invent facts, numbers or sources.')


def clean_purpose(data):
    if not isinstance(data, dict):
        raise ScriptError('Amaç özeti okunamadı.')
    purpose = {}
    for name, limit in PURPOSE_FIELDS.items():
        value = data.get(name, '')
        if not isinstance(value, str):
            raise ScriptError('Amaç özeti alanlarını metin olarak girin.')
        purpose[name] = ' '.join(value.split())[:limit]
    if not purpose['main_message'] or not purpose['summary']:
        raise ScriptError('Amaç özetinde ana mesaj ve özet boş olamaz.')
    return purpose


def script_payload(project, purpose, provider):
    low, high = PACE.get(project['language'], (125, 145))
    instructions = (f'VIDEO PURPOSE (decided by the director; the notes are in Turkish, write the script in the project language):\n'
                    f'- Main message: {purpose["main_message"]}\n- Opening hook idea: {purpose["hook"]}\n'
                    f'- Viewer promise: {purpose["viewer_promise"]}\n- Summary: {purpose["summary"]}\n'
                    'Write narration that can be illustrated with real footage: concrete places, objects, '
                    'actions and people; avoid long abstract stretches.')
    return {'provider': provider, 'mode': 'original', 'content_type': purpose['content_type'][:150],
            'tone': (purpose['tone'] or 'Otomatik')[:150], 'audience': purpose['audience'][:500],
            'instructions': instructions[:4000], 'words_per_minute_min': low, 'words_per_minute_max': high}


class DirectorService:
    def __init__(self, scripts, quality, production, settings, provider_factory=None):
        self.scripts, self.quality, self.production, self.settings = scripts, quality, production, settings
        self.repo, self.projects = scripts.repository, scripts.projects
        self.provider_factory = provider_factory
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='director')
        self.futures, self.stopping, self.lock = {}, Event(), Lock()

    def close(self):
        self.stopping.set()
        self.executor.shutdown(wait=False, cancel_futures=True)

    # ---- persisted state ----------------------------------------------
    def _read(self, project_id, name):
        path = self.projects._path(project_id) / 'script' / name
        try:
            return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
        except (OSError, ValueError):
            return None

    def state(self, project_id):
        return self._read(project_id, 'director_state.json') or {'status': 'idle'}

    def _save_state(self, project_id, state):
        state['updated_at'] = now()
        self.repo._file(project_id, 'director_state.json', dumps(state))

    def purpose(self, project_id):
        return self._read(project_id, 'director_purpose.json')

    def save_purpose(self, project_id, payload):
        self.projects.get(project_id)
        if not isinstance(payload, dict) or set(payload) - set(PURPOSE_FIELDS):
            raise ScriptError('Amaç özeti alanlarını kontrol edin.')
        if self.state(project_id).get('status') in BUSY:
            raise ScriptError('Yönetmen çalışırken amaç değiştirilemez. Bitmesini bekleyin.', 409)
        purpose = clean_purpose({**(self.purpose(project_id) or {}), **payload})
        purpose['edited_by_owner'] = True
        self.repo._file(project_id, 'director_purpose.json', dumps(purpose))
        return purpose

    def view(self, project_id):
        self.projects.get(project_id)
        state = self.state(project_id)
        if state.get('status') in BUSY and not self._alive(project_id):
            state.update(status='error', message='Uygulama kapatıldığı için yönetmen durdu. Devam Et ile kaldığı yerden sürer.')
        return {'state': state, 'purpose': self.purpose(project_id), 'steps': STEPS}

    def _alive(self, project_id):
        future = self.futures.get(project_id)
        return future is not None and not future.done()

    # ---- run -----------------------------------------------------------
    def start(self, project_id, payload):
        allowed = {'cost_confirmed', 'auto_approve', 'confirm_replace', 'provider', 'rewrite_purpose'}
        if not isinstance(payload, dict) or set(payload) - allowed or any(type(payload.get(k, False)) is not bool for k in allowed - {'provider'}):
            raise ScriptError('Yönetmen seçeneklerini kontrol edin.')
        provider = payload.get('provider') or self.settings.ai_engine()
        if provider is None:
            raise ScriptError('Yönetmen için Ayarlar → Gemini bölümünde ücretsiz API anahtarınızı kaydedip Modelleri Getir ile bir model seçin.', 422)
        if provider not in ('claude', 'gemini', 'ollama', 'openai'):
            raise ScriptError('Geçerli bir AI motoru seçin.')
        if provider in ('claude', 'openai') and not payload.get('cost_confirmed'):
            raise ScriptError('Bu motor ücretli API kullanır. Başlatmadan önce maliyet onayı verin.', 409)
        project = self.projects.get(project_id)
        current = self.repo.view(project_id)['current']
        previous = self.state(project_id)
        resuming = previous.get('status') in ('error', 'waiting')
        same_engine = previous.get('provider') == provider
        if current and not resuming and not payload.get('confirm_replace'):
            raise ScriptError('Bu projede zaten senaryo var. Yönetmen yeni bir sürüm yazar; eski sürümler silinmez. Devam etmek için onay verin.', 409)
        if provider == 'claude' and not self.settings.safe_view()['claude']['has_api_key']:
            raise ScriptError('Claude API anahtarı kaydedilmemiş. Ayarlar → Claude bölümünden ekleyin.', 422)
        with self.lock:
            if self._alive(project_id):
                raise ScriptError('Yönetmen bu projede zaten çalışıyor.', 409)
            state = {'status': 'queued', 'step': 'purpose', 'provider': provider, 'message': 'Sıraya alındı.',
                     'auto_approve': payload.get('auto_approve', True), 'started_at': now(),
                     # A backup engine starts its own script job; finished steps are kept.
                     'script_job_id': previous.get('script_job_id') if resuming and same_engine else None,
                     'script_version_id': previous.get('script_version_id') if resuming else None,
                     'plan_job_id': previous.get('plan_job_id') if resuming else None}
            if payload.get('rewrite_purpose'):
                self.repo._file(project_id, 'director_purpose.json', dumps({}))
            self._save_state(project_id, state)
            self.futures[project_id] = self.executor.submit(self._run, project_id, project['language'])
        return {'message': 'Yönetmen başladı. Adımları bu sayfada izleyebilirsiniz.', 'state': state}

    def _step(self, project_id, state, step, message):
        if self.stopping.is_set():
            raise ScriptError('Uygulama kapatıldığı için yönetmen durdu. Devam Et ile sürdürülebilir.')
        state.update(status='running', step=step, message=message)
        self._save_state(project_id, state)

    def _wait(self, job_id, label):
        future = self.scripts.futures.get(job_id)
        if future is not None:
            future.result()
        job = self.repo.job(job_id)
        if job['status'] == 'error':
            progress = json.loads(job['progress_json'])
            error = ScriptError(f'{label}: {job["error_message"]}', 502)
            error.category = progress.get('error_category', 'generation_error')
            raise error
        return job

    def _run(self, project_id, language):
        CURRENT_PROJECT.set(project_id)
        state = self.state(project_id)
        provider = state['provider']
        try:
            project = self.projects.get(project_id)
            # 1) Purpose (editable summary). Owner edits are kept.
            purpose = self.purpose(project_id) or {}
            if not purpose.get('main_message'):
                self._step(project_id, state, 'purpose', STEPS['purpose'])
                if provider in ('claude', 'gemini'):
                    from app.providers.factory import make_script_provider
                    engine = (self.provider_factory or make_script_provider)(provider, self.settings)
                    purpose = clean_purpose(engine.complete_json('purpose', purpose_prompt(project), PURPOSE_SCHEMA, effort='medium', max_tokens=4000))
                else:  # backup engines: a plain purpose from the topic, still editable
                    purpose = clean_purpose({'audience': 'Genel izleyici', 'main_message': project['topic'], 'tone': 'Merak uyandıran, sakin',
                                             'hook': '', 'viewer_promise': '', 'content_type': 'Belgesel anlatım',
                                             'summary': f'{project["topic"]} hakkında özgün bir anlatım.'})
                self.repo._file(project_id, 'director_purpose.json', dumps(purpose))
            # 2) Script in the project language at the language's pace.
            current = self.repo.view(project_id)['current']
            if not (state.get('script_version_id') and current and current['id'] == state['script_version_id']):
                self._step(project_id, state, 'script', STEPS['script'])
                old = state.get('script_job_id') and self.repo.job(state['script_job_id'])
                if old and old['status'] == 'error':
                    started = self.scripts.resume(project_id, old['id'], True)
                else:
                    started = self.scripts.start(project_id, {**script_payload(project, purpose, provider), 'confirm_replace_approved': True}, 'generate')
                state['script_job_id'] = started['job_id']
                self._save_state(project_id, state)
                job = self._wait(started['job_id'], 'Senaryo yazılamadı')
                state['script_version_id'] = json.loads(job['progress_json']).get('version_id')
                current = self.repo.view(project_id)['current']
            # 3) Approval (automatic unless the owner turned it off).
            if current['status'] != 'approved':
                if not state.get('auto_approve', True):
                    state.update(status='waiting', step='approve', message='Senaryo hazır. Okuyup onayladıktan sonra Yönetmeni Devam Ettir deyin.')
                    self._save_state(project_id, state)
                    return
                self._step(project_id, state, 'approve', STEPS['approve'])
                self.repo.approve(project_id, current['id'], True)
            # 4) Edit plan: scenes, types, queries, must/must-not, shot counts.
            self._step(project_id, state, 'plan', STEPS['plan'])
            plan = self.production.view(project_id)['plan']
            if not plan or plan.get('version_id') != current['id']:
                started = self.quality.start(project_id, 'visual', {'provider': provider, 'cost_confirmed': True, 'confirm_replace_plan': True, 'director': True})
                state['plan_job_id'] = started['job_id']
                self._save_state(project_id, state)
                try:
                    self._wait(started['job_id'], 'Kurgu planı hazırlanamadı')
                except ScriptError:
                    # The owner asked the director for one automatic plan repair;
                    # engines that normally ask first get that consent here.
                    progress = json.loads(self.repo.job(started['job_id'])['progress_json'])
                    if progress.get('visual_repair', {}).get('status') != 'awaiting_cost_confirmation':
                        raise
                    self.quality.resume(project_id, started['job_id'], True, visual_repair_cost_confirmed=True)
                    self._wait(started['job_id'], 'Kurgu planı hazırlanamadı')
            plan = self.production.view(project_id)['plan']
            if not plan:
                raise ScriptError('Kurgu planı kaydedilemedi. Devam Et ile tekrar deneyin.')
            state.update(status='done', step='done', message=f'Hazır: amaç, senaryo ve {len(plan.get("blocks", []))} sahnelik kurgu planı. Medya adımına geçebilirsiniz.')
            self._save_state(project_id, state)
        except Exception as error:  # every failure is reported, nothing is switched silently
            category = getattr(error, 'category', None) or 'director_error'
            message = str(error) if isinstance(error, (ScriptError, ScriptProviderError)) else 'Yönetmen beklenmeyen bir hatayla durdu. Devam Et ile tekrar deneyin; tamamlanan adımlar korundu.'
            state.update(status='error', message=message, category=category,
                         offer_backup=provider in ('claude', 'gemini') and category in BACKUP_WORTHY | {'free_quota_exhausted', 'quota_limit', 'gemini_timeout'})
            LOG.info('director project=%s step=%s category=%s', project_id, state.get('step'), category)
            try:
                self._save_state(project_id, state)
            except Exception:
                LOG.warning('director state could not be saved')
