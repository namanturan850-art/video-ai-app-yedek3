from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import logging
from threading import Event
import time
from uuid import uuid4

from pydantic import ValidationError

from app.projects import now
from app.providers.base import ScriptProviderError
from app.providers.factory import make_script_provider, SCRIPT_ENGINE_LABELS
from app.scripts.engine import YouTubeScriptEngine, SecretGuard, assert_original, repetition_warnings, translation_chunks
from app.scripts.models import ScriptOptions, ScriptError, duration_metrics
from app.scripts.storage import ScriptRepository, dumps, ACTIVE

LOG = logging.getLogger('uvicorn.error.scripts')


class ScriptService:
    def __init__(self, projects, settings, *, provider_factory=None):
        self.projects, self.settings = projects, settings
        self.repository = ScriptRepository(projects)
        self.provider_factory = provider_factory or make_script_provider
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='script')
        self.stopping = Event()
        self.futures = {}

    def recover(self):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute("UPDATE script_jobs SET status='error',error_message=?,updated_at=? WHERE status IN ('queued','analyzing','planning','generating','checking')",
                ('Üretim uygulama kapatıldığı için durdu. Tamamlanan bölümler korundu; Devam Et düğmesini kullanın.', now()))

    def close(self):
        self.stopping.set()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def options(self, payload):
        try:
            return ScriptOptions.model_validate(payload)
        except ValidationError:
            raise ScriptError('Senaryo alanlarını kontrol edin. Konuşma hızı 80–220 arasında olmalı; minimum maksimumdan büyük olamaz. Çeviri için kendi metninizi ve sahiplik onayını girin.') from None

    def _provider(self, name):
        config = self.settings.script_config(name)
        guard = SecretGuard(self.settings.secret_values())
        guard.validate(config.get('model', ''))
        if name == 'gemini' and not self.settings.safe_view()['gemini']['model_verified']:
            raise ScriptError('Ayarlar → Gemini bölümünde Modelleri Getir deyin, listeden bir model seçip kaydedin.')
        return self.provider_factory(name, self.settings), config['model'], guard

    def start(self, project_id, payload, action='generate'):
        if action not in ('generate', 'analyze'):
            raise ScriptError('Bu senaryo işlemi kullanılamıyor.')
        project_language = self.projects.get(project_id)['language']
        options = self.options({'language': project_language, **payload})
        if action == 'analyze' and options.mode == 'translate_owned':
            raise ScriptError('Kendi metninizi çevirmek için Senaryo Oluştur düğmesini kullanın; konsept analizi gerekmez.')
        # Authorization/validation before any provider request; only construction here.
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            project = dict(self.projects._row(connection, project_id))
            self.repository._idle(connection, project_id)
            if action == 'generate':
                self.repository.protect(connection, project_id, options.confirm_replace_approved)
            provider, model, guard = self._provider(options.provider)
            saved = options.model_dump(exclude={'confirm_replace_approved'})
            inputs = {'topic': project['topic'], 'target_duration_minutes': project['target_duration_minutes']}
            guard.validate([saved, inputs])
            progress = {'phase': 'queued', 'percent': 0, 'blueprint': None, 'plan': None, 'sections': [], 'reviews': [], 'version_id': None}
            if action == 'generate' and options.mode == 'original':
                previous = connection.execute("SELECT * FROM script_jobs WHERE project_id=? AND status='analyzed' ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone()
                if previous and previous['options_json'] == dumps(saved) and previous['input_json'] == dumps(inputs) and previous['provider'] == options.provider and previous['model'] == model:
                    progress['blueprint'] = json.loads(previous['progress_json'])['blueprint']
            job_id, stamp = uuid4().hex, now()
            connection.execute('INSERT INTO script_jobs (id,project_id,provider,model,action,status,options_json,input_json,progress_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (job_id, project_id, options.provider, model, action, 'queued', dumps(saved), dumps(inputs), dumps(progress), stamp, stamp))
        self.futures[job_id] = self.executor.submit(self._run, job_id, provider, guard)
        return {'job_id': job_id, 'message': 'Senaryo işlemi başladı. Bu sayfayı kapatsanız da uygulama penceresi açıkken devam eder.'}

    def resume(self, project_id, job_id, confirmed=False):
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            self.projects._row(connection, project_id)
            job = self.repository.job(job_id)
            if job['project_id'] != project_id:
                raise ScriptError('Bu işlem projeye ait değil.', 404)
            self.repository._idle(connection, project_id)
            if job['status'] != 'error':
                raise ScriptError('Yalnızca kesilen veya başarısız işlem sürdürülebilir.', 409)
            retry_at = json.loads(job['progress_json']).get('retry_not_before', 0)
            if retry_at > time.time():
                raise ScriptError(f'Sağlayıcının istek sınırı nedeniyle yaklaşık {int(retry_at - time.time()) + 1} saniye bekleyip Devam Et deyin.', 429)
            if job['action'] == 'generate':
                self.repository.protect(connection, project_id, confirmed)
            provider, model, guard = self._provider(job['provider'])
            if model != job['model']:
                raise ScriptError('Model önceki üretimden farklı. Aynı modeli Ayarlar ekranında seçin veya yeni üretim başlatın.', 409)
            guard.validate([json.loads(job['options_json']), json.loads(job['input_json'])])
            connection.execute("UPDATE script_jobs SET status='queued',error_message='',updated_at=? WHERE id=?", (now(), job_id))
        self.futures[job_id] = self.executor.submit(self._run, job_id, provider, guard)
        return {'job_id': job_id, 'message': 'Tamamlanan bölümler korunarak devam ediliyor.'}

    def _run(self, job_id, provider, guard):
        started = time.monotonic()
        job = self.repository.job(job_id)
        options, project, progress = (json.loads(job[name]) for name in ('options_json', 'input_json', 'progress_json'))
        engine = YouTubeScriptEngine(provider, guard)

        def save(status, phase, percent):
            if self.stopping.is_set():
                raise ScriptError('Üretim uygulama kapatıldığı için durdu. Devam Et ile sürdürebilirsiniz.')
            progress.update(phase=phase, percent=percent)
            self.repository.checkpoint(job_id, status, guard.clean(progress))

        try:
            if progress.get('version_id'):
                save('draft', 'done', 100)
                return
            if options['mode'] == 'original':
                if not progress['blueprint']:
                    save('analyzing', 'concept', 5)
                    progress['blueprint'] = engine.analyzer.analyze(project, options)
                    if len(dumps(progress['blueprint'])) > 16000:
                        raise ScriptError('Konsept özeti çok uzun. Analizi yeniden deneyin.')
                    assert_original(dumps(progress['blueprint']), options)
                    save('analyzing', 'concept_complete', 15)
                if job['action'] == 'analyze':
                    save('analyzed', 'done', 100)
                    LOG.info('script provider=%s operation=analyze result=success category=success elapsed_ms=%.0f', job['provider'], (time.monotonic() - started) * 1000)
                    return
                if not progress['plan']:
                    save('planning', 'plan', 20)
                    progress['plan'] = engine.plan(progress['blueprint'], project, options)
                    assert_original(dumps(progress['plan']), options)
                    save('planning', 'plan_complete', 25)
            else:
                chunks = translation_chunks(options['owned_text'])
                progress['blueprint'] = {'content_type': 'Kullanıcıya ait metin çevirisi', 'core_topic': project['topic'], 'language': options['language']}
                progress['plan'] = {'sections': [{'title': f'Çeviri bölümü {i + 1}', 'source': text} for i, text in enumerate(chunks)]}

            plan = progress['plan']
            context = progress['sections'][-1].get('context', '') if progress['sections'] else ''
            for index, section in enumerate(plan['sections']):
                progress['section_index'] = index + 1
                completed = progress['sections'][index] if index < len(progress['sections']) else None
                if completed and completed.get('context'):
                    context = completed['context']
                    continue
                if not completed:
                    save('generating', 'section', 25 + round(index / len(plan['sections']) * 55))
                    text = engine.translate(section['source'], context, index == len(plan['sections']) - 1, options['language']) if options['mode'] == 'translate_owned' else engine.section(progress['blueprint'], plan, index, context, options)
                    assert_original(text, options)
                    completed = {'title': section['title'], 'text': text, 'context': ''}
                    progress['sections'].append(completed)
                    save('generating', 'section_saved', progress['percent'])
                save('generating', 'continuity', progress['percent'])
                context = engine.continuity(completed['text'], context, [item['title'] for item in plan['sections'][index + 1:]])
                completed['context'] = context
                save('generating', 'context_saved', 25 + round((index + 1) / len(plan['sections']) * 55))

            text = '\n\n'.join(section['text'] for section in progress['sections'])
            assert_original(text, options)
            groups = [progress['sections'][i:i + 8] for i in range(0, len(progress['sections']), 8)]
            for index, group in enumerate(groups):
                if index < len(progress['reviews']):
                    continue
                save('checking', 'review', 85 + round(index / len(groups) * 10))
                progress['reviews'].append(engine.review(progress['blueprint'], group, options))
                save('checking', 'review_saved', progress['percent'])
            issues = [issue for review in progress['reviews'] for issue in review['issues']] + repetition_warnings(text)
            metrics = duration_metrics(text, project['target_duration_minutes'], options)
            if not metrics['target_word_min'] <= metrics['word_count'] <= metrics['target_word_max']:
                issues.append('Kelime sayısı hedef süre aralığının dışında. Kaliteyi ve tahmini süreyi inceleyin; gerekirse metni düzenleyin.')
            if options['mode'] == 'translate_owned':
                issues.append('Çeviri kaynak metnin uzunluğunu korur; proje hedef süresine göre genişletilmez.')
            report = {'consistent': all(review['consistent'] for review in progress['reviews']), 'issues': issues[:40], **metrics}
            save('checking', 'saving', 98)
            self.repository.create_version(job['project_id'], text, job['provider'], job['model'], options,
                progress['blueprint']['content_type'], report, generated=True, job_id=job_id, progress=progress)
            save('draft', 'done', 100)
            LOG.info('script provider=%s operation=generate result=success category=success elapsed_ms=%.0f', job['provider'], (time.monotonic() - started) * 1000)
        except Exception as error:
            category = error.category if isinstance(error, ScriptProviderError) and error.category in {'key_rejected', 'quota_limit', 'rate_limit', 'billing_quota', 'invalid_model', 'model_unavailable', 'no_internet', 'gemini_timeout', 'generation_timeout', 'invalid_response', 'upstream_error'} else 'generation_error'
            messages = {'key_rejected': 'API anahtarı kabul edilmedi. Ayarlar bölümünü kontrol edin.',
                        'quota_limit': 'Kullanım sınırına ulaşıldı. Bir süre bekleyip Devam Et deyin.',
                        'rate_limit': 'İstek hız sınırına ulaşıldı. Bir süre bekleyip Devam Et deyin.',
                        'billing_quota': 'API faturalandırma veya kota sınırına ulaşıldı. API hesabınızın bakiye ve limitlerini kontrol edin.',
                        'invalid_model': 'Model veya desteklediği istek geçersiz. Ayarlar bölümünü kontrol edin.',
                        'model_unavailable': 'Seçilen model kullanılamıyor. Ayarlar bölümünü kontrol edin.',
                        'no_internet': 'Sağlayıcı bağlantısı kurulamadı. Bağlantınızı kontrol edin.',
                        'gemini_timeout': 'Gemini API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.',
                        'generation_timeout': 'Sağlayıcı zamanında yanıt vermedi. Tekrar deneyin.'}
            message = str(error) if isinstance(error, ScriptError) else messages.get(category, 'Senaryo oluşturulurken işlem kesildi. Tekrar deneyin.')
            message = guard.clean(message) + ' Üretim tamamlanamadı. Tamamlanan bölümler korundu.'
            # Preserve the last committed checkpoint even if a file mirror caused the failure.
            with self.projects.lock, closing(self.projects._connection()) as connection, connection:
                row = connection.execute('SELECT progress_json FROM script_jobs WHERE id=?', (job_id,)).fetchone()
                saved_progress = json.loads(row['progress_json'])
                saved_progress['error_category'] = category
                saved_progress['retry_not_before'] = time.time() + (error.retry_after if isinstance(error, ScriptProviderError) else 0)
                connection.execute("UPDATE script_jobs SET status='error',error_message=?,progress_json=?,updated_at=? WHERE id=?", (message, dumps(saved_progress), now(), job_id))
            LOG.info('script provider=%s operation=%s result=failure category=%s elapsed_ms=%.0f', job['provider'], job['action'], category, (time.monotonic() - started) * 1000)

    def edit(self, project_id, payload):
        allowed = {'text', 'base_version_id', 'confirm_replace_approved'}
        if any(key not in allowed for key in payload) or not isinstance(payload.get('text'), str) or not payload['text'].strip() or len(payload['text']) > 300000 or not isinstance(payload.get('base_version_id'), str) or type(payload.get('confirm_replace_approved', False)) is not bool:
            raise ScriptError('Senaryo metnini ve geçerli sürümü kontrol edin; boş metin kaydedilemez.')
        self.repository.view(project_id)
        current = self.repository.view(project_id)['current']
        if not current:
            raise ScriptError('Önce senaryo oluşturun.')
        guard = SecretGuard(self.settings.secret_values())
        guard.validate(payload['text'])
        assert_original(payload['text'], current['options'])
        report = {'consistent': False, 'issues': ['Elle düzenlenen metni onaylamadan önce tutarlılık ve gerçek bilgiler açısından inceleyin.'] + repetition_warnings(payload['text'])}
        version_id = self.repository.create_version(project_id, payload['text'], current['provider'], current['model'],
            current['options'], current['content_type'], report, base_version=payload['base_version_id'], confirmed=payload.get('confirm_replace_approved', False))
        return {'version_id': version_id, 'message': 'Düzenleme yeni sürüm olarak kaydedildi. Önceki sürüm korundu.'}
