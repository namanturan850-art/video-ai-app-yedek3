"""Local dashboard, safe diagnostics and encrypted settings."""
from contextlib import asynccontextmanager
from pathlib import Path
import platform
import shutil
import sqlite3
import tempfile
import logging
import time

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
import subprocess

from app import __version__
from app.database import database_healthy, initialize_database
from app.secret_store import SettingsStore, SettingsStorageError
from app.settings import SettingsService, SettingsInputError, ffmpeg_status
from app.provider_checks import check_ollama
from app.projects import ProjectService, ProjectError
from app.providers.base import ScriptProviderError
from app.providers.factory import make_script_provider
from app.scripts.service import ScriptService
from app.scripts.models import ScriptError
from app.scripts.quality import QualityService
from app.languages import LANGUAGES
from app.production import ProductionService
from app.providers.images import LocalGPUImageProvider, GeminiImageProvider, OpenAIImageProvider
from app.provider_diagnostics import ProviderDiagnostics, DiagnosticInputError

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
GEMINI_LOG = logging.getLogger('uvicorn.error.gemini_settings')
GEMINI_UNEXPECTED_MESSAGE = 'Gemini ayarları işlenirken beklenmeyen bir sunucu hatası oluştu. Tekrar deneyin; sorun sürerse Tanılama ekranını kontrol edin.'
GEMINI_ERROR_CATEGORIES = {'none', 'gemini_timeout', 'no_internet', 'key_rejected', 'quota_limit',
                          'rate_limit', 'free_quota_exhausted', 'invalid_request', 'network_error',
                          'model_unsupported', 'blocked_response', 'no_candidates', 'malformed_candidate',
                          'unexpected_finish_reason', 'output_limit', 'malformed_content', 'malformed_parts',
                          'thought_only_response', 'response_schema_mismatch', 'empty_response', 'missing_model',
                          'model_unavailable', 'upstream_error', 'invalid_response', 'missing_key',
                          'provider_error', 'invalid_settings', 'local_storage', 'unexpected_backend'}


def gemini_unexpected_response():
    return JSONResponse(status_code=500, content={'message': GEMINI_UNEXPECTED_MESSAGE,
                                                'category': 'unexpected_backend'})


def directory_writable(directory: Path) -> bool:
    try:
        with tempfile.TemporaryFile(dir=directory):
            return True
    except OSError:
        return False


def create_app(data_dir: Path | None = None) -> FastAPI:
    storage = Path(data_dir) if data_dir is not None else ROOT / "data"

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            application.state.database = initialize_database(storage)
            scripts.recover()
        except (OSError, sqlite3.Error) as error:
            raise RuntimeError("Veri klasörü açılamadı. Uygulamayı yazma izniniz olan bir klasöre taşıyıp yeniden açın.") from error
        try:
            yield
        finally:
            ai_diagnostics.close()
            scripts.close()

    application = FastAPI(title="AI Video Studio", version=__version__, lifespan=lifespan)
    settings = SettingsService(SettingsStore(storage / "secrets"))
    application.state.settings = settings
    ai_diagnostics = ProviderDiagnostics(settings)
    application.state.ai_diagnostics = ai_diagnostics
    projects = ProjectService(storage)
    application.state.projects = projects
    scripts = ScriptService(projects, settings)
    application.state.scripts = scripts
    quality = QualityService(scripts)
    application.state.quality = quality
    production = ProductionService(scripts)
    quality.production = production
    application.state.production = production
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    application.mount("/static", StaticFiles(directory=STATIC), name="static")

    @application.middleware("http")
    async def protect_local_data(request: Request, call_next):
        scope = "settings" if request.url.path.startswith("/api/settings") else "projects"
        if request.url.path.startswith(("/api/settings", "/api/projects")):
            origin = request.headers.get("origin")
            same_origin = not origin or origin == f"{request.url.scheme}://{request.url.netloc}"
            mutation = request.method not in ("GET", "HEAD")
            if not same_origin or (mutation and request.headers.get("x-ai-video-studio") != scope):
                message = "Ayarlar yalnızca uygulamanın Ayarlar ekranından değiştirilebilir. Sayfayı yeniden açın." if scope == "settings" else "Projeler yalnızca uygulamanın proje ekranından değiştirilebilir. Sayfayı yeniden açın."
                return JSONResponse(status_code=403, content={"message": message}, headers={"Cache-Control": "no-store"})
            gemini = request.url.path == '/api/settings/gemini' or request.url.path.startswith('/api/settings/gemini/')
            script_route = any(part in request.url.path for part in ('/script', '/production')) and request.url.path.startswith('/api/projects/')
            settings_route = request.url.path.startswith('/api/settings')
            started = time.monotonic()
            try:
                response = await call_next(request)
            except Exception:
                if not settings_route and not script_route:
                    raise
                if script_route:
                    return JSONResponse(status_code=500, content={'message': 'Senaryo işlemi tamamlanamadı. Sayfayı yeniden açıp tekrar deneyin.'}, headers={'Cache-Control': 'no-store'})
                if not gemini:
                    return JSONResponse(status_code=500, content={'message': 'Ayarlar işlenirken beklenmeyen hata oluştu. Tekrar deneyin; mevcut dosyaları silmeyin.', 'category': 'unexpected_backend'}, headers={'Cache-Control': 'no-store'})
                # Catch inside the middleware, before Starlette's outer server-error
                # handler can re-raise and reset the connection. Never log the exception.
                request.state.gemini_category = 'unexpected_backend'
                response = gemini_unexpected_response()
            if gemini:
                operation = {'/api/settings/gemini/models': 'list_models',
                             '/api/settings/gemini/test': 'test_connection'}.get(request.url.path, 'settings')
                category = getattr(request.state, 'gemini_category', 'none' if response.status_code < 400 else 'invalid_settings')
                if category not in GEMINI_ERROR_CATEGORIES:
                    category = 'unexpected_backend'
                success = response.status_code < 400 and category == 'none'
                GEMINI_LOG.info('gemini_settings operation=%s result=%s category=%s elapsed_ms=%.0f',
                                operation, 'success' if success else 'failure', category,
                                (time.monotonic() - started) * 1000)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            return response
        return await call_next(request)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"message": "Bilgiler okunamadı. Alanları kontrol edip yeniden kaydedin."})

    @application.exception_handler(SettingsInputError)
    async def invalid_settings(request: Request, error: SettingsInputError):
        request.state.gemini_category = 'invalid_settings'
        content = {'message': str(error)}
        if request.url.path.startswith('/api/settings/gemini'):
            content['category'] = 'invalid_settings'
        return JSONResponse(status_code=422, content=content)

    @application.exception_handler(DiagnosticInputError)
    async def invalid_diagnostic(request: Request, error: DiagnosticInputError):
        return JSONResponse(status_code=error.status_code, content={'message': str(error)})

    @application.exception_handler(SettingsStorageError)
    async def settings_storage_error(request: Request, error: SettingsStorageError):
        request.state.gemini_category = 'local_storage'
        content = {'message': str(error)}
        content['storage_category'] = error.category
        if request.url.path.startswith('/api/settings/gemini'):
            content['category'] = 'local_storage'
        return JSONResponse(status_code=503, content=content)

    @application.exception_handler(ProjectError)
    async def project_error(request: Request, error: ProjectError):
        return JSONResponse(status_code=error.status_code, content={"message": str(error), "fields": error.fields})

    @application.exception_handler(ScriptProviderError)
    async def script_provider_error(request: Request, error: ScriptProviderError):
        request.state.gemini_category = error.category
        return JSONResponse(status_code=error.status_code, content={"message": str(error), 'category': error.category})

    @application.exception_handler(ScriptError)
    async def script_error(request: Request, error: ScriptError):
        return JSONResponse(status_code=error.status_code, content={'message': str(error)})

    @application.get('/api/projects/{project_id}/script')
    def get_script(project_id: str):
        return {**scripts.repository.view(project_id), 'artifacts': quality.results(project_id)}

    @application.get('/api/languages')
    def languages():
        return LANGUAGES

    @application.post('/api/projects/{project_id}/script/tools/{kind}', status_code=202)
    def script_tool(project_id: str, kind: str, payload: dict):
        return quality.start(project_id, kind, payload)

    @application.post('/api/projects/{project_id}/script/tools/{artifact_id}/apply', status_code=202)
    def apply_script_tool(project_id: str, artifact_id: str, payload: dict):
        return quality.apply(project_id, artifact_id, payload)

    @application.post('/api/projects/{project_id}/script/tools/{artifact_id}/select')
    def choose_script_tool(project_id: str, artifact_id: str, payload: dict):
        return quality.choose(project_id, artifact_id, payload)

    @application.get('/api/projects/{project_id}/production')
    def get_production(project_id: str): return production.view(project_id)

    @application.post('/api/projects/{project_id}/production/plan', status_code=202)
    def plan_production(project_id: str, payload: dict): return quality.start(project_id, 'visual', payload)

    @application.put('/api/projects/{project_id}/production')
    def production_preferences(project_id: str, payload: dict): return production.update(project_id, payload)

    @application.put('/api/projects/{project_id}/production/blocks/{block_id}/media')
    def production_media(project_id: str, block_id: str, payload: dict): return production.attach_media(project_id, block_id, payload)

    @application.put('/api/projects/{project_id}/production/timing')
    def production_timing(project_id: str, payload: dict): return production.attach_timing(project_id, payload)

    @application.post('/api/projects/{project_id}/script/analyze', status_code=202)
    def analyze_script(project_id: str, payload: dict):
        return scripts.start(project_id, payload, 'analyze')

    @application.post('/api/projects/{project_id}/script/generate', status_code=202)
    def generate_script(project_id: str, payload: dict):
        return scripts.start(project_id, payload)

    @application.post('/api/projects/{project_id}/script/jobs/{job_id}/resume', status_code=202)
    def resume_script(project_id: str, job_id: str, payload: dict):
        if set(payload) != {'confirm_replace_approved'} or type(payload.get('confirm_replace_approved')) is not bool:
            raise ScriptError('Devam Et için açık onay tercihi gerekli.')
        if scripts.repository.job(job_id)['action'] not in ('generate', 'analyze'):
            return quality.resume(project_id, job_id, payload['confirm_replace_approved'])
        return scripts.resume(project_id, job_id, payload['confirm_replace_approved'])

    @application.post('/api/projects/{project_id}/script/versions', status_code=201)
    def edit_script(project_id: str, payload: dict):
        return scripts.edit(project_id, payload)

    @application.post('/api/projects/{project_id}/script/versions/{version_id}/select')
    def select_script(project_id: str, version_id: str, payload: dict):
        if set(payload) != {'confirm_replace_approved'} or type(payload.get('confirm_replace_approved')) is not bool:
            raise ScriptError('Sürüm değiştirmek için açık onay tercihi gerekli.')
        scripts.repository.select(project_id, version_id, payload['confirm_replace_approved'])
        return scripts.repository.view(project_id)

    @application.post('/api/projects/{project_id}/script/versions/{version_id}/approve')
    def approve_script(project_id: str, version_id: str, payload: dict):
        if set(payload) != {'confirm'} or type(payload.get('confirm')) is not bool:
            raise ScriptError('Senaryoyu onaylamak için açık onay gerekli.')
        scripts.repository.approve(project_id, version_id, payload['confirm'])
        return scripts.repository.view(project_id)

    @application.get('/api/projects/{project_id}/script/approved')
    def approved_script(project_id: str):
        return scripts.repository.approved_current(project_id)

    @application.post("/api/projects", status_code=201)
    def create_project(payload: dict):
        return projects.create(payload)

    @application.get("/api/projects")
    def list_projects():
        return {"projects": projects.list()}

    @application.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        project = projects.get(project_id)
        view = scripts.repository.view(project_id)
        if view['job'] and view['job']['progress'].get('blueprint'):
            project['pipeline'][0].update(status='Hazır', message='Konsept analizi Senaryo ekranında görüntülenebilir.')
        if view['current'] or view['job']:
            project['pipeline'][1].update(status=view['status'], message='Senaryoyu açıp inceleyebilir, düzenleyebilir ve onaylayabilirsiniz.')
        if production.view(project_id)['plan']:
            project['pipeline'][2].update(status='Çalıştırma daha sonra', message='Görsel/kurgu önerileri ayrı plan ekranında hazır. Gerçek medya ve sahne çalıştırması henüz yok.')
        return project

    @application.patch("/api/projects/{project_id}")
    def update_project(project_id: str, payload: dict):
        return projects.update(project_id, payload)

    @application.delete("/api/projects/{project_id}")
    def delete_project(project_id: str, payload: dict | None = Body(default=None)):
        projects.delete(project_id, payload)
        return {"message": "Proje ve yerel dosyaları silindi."}

    @application.get("/api/settings")
    def read_settings():
        return settings.safe_view()

    @application.get('/api/settings/ai-diagnostics')
    def read_ai_diagnostics():
        return ai_diagnostics.view()

    @application.post('/api/settings/ai-diagnostics/{provider}/{test}', status_code=202)
    def run_ai_diagnostic(provider: str, test: str, payload: dict):
        return ai_diagnostics.start(provider, test, payload)

    @application.put("/api/settings/{section}")
    def save_settings(section: str, payload: dict):
        return settings.save(section, payload)

    @application.delete("/api/settings/{section}")
    def clear_settings(section: str):
        return settings.clear(section)

    @application.post("/api/settings/{section}/test")
    def test_connection(section: str, request: Request):
        if section == 'images':
            raise SettingsInputError('Görsel sağlayıcısını kendi bağlantı düğmesinden test edin.')
        if section == 'openai':
            config = settings.script_config('openai')
            started = time.monotonic()
            try:
                outcome = make_script_provider('openai', settings).test_connection()
            except ScriptProviderError as error:
                outcome = {'status': 'Hata', 'message': str(error), 'category': error.category}
            logging.getLogger('uvicorn.error.providers').info('provider=openai operation=test category=%s elapsed_ms=%.0f', outcome.get('category', 'success'), (time.monotonic() - started) * 1000)
            return {'result': outcome, 'settings': settings.record_openai_test(config, outcome)}
        if section == "gemini":
            config = settings.gemini_config()
            try:
                checked = make_script_provider("gemini", settings, discovery=True).test_connection(selected_model=config['model'])
                models = checked.pop("models")
                outcome = checked
            except ScriptProviderError as error:
                models = None
                outcome = {"status": "Hata", "message": str(error), 'category': error.category}
            request.state.gemini_category = outcome.get('category', 'none')
            view = settings.record_gemini_test(config, outcome, models)
            return {"result": outcome, "models": view['gemini']['models'] if models is not None else [], "settings": view}
        if section == "ollama":
            config = settings.ollama_config()
            outcome = check_ollama(config)
            view = settings.record_ollama_test(config, outcome)
            return {"result": outcome, "settings": view}
        if section == "ffmpeg":
            detected = ffmpeg_status()
            try:
                if not detected["found"]:
                    raise OSError()
                completed = subprocess.run([detected["executable_path"], "-version"], timeout=5,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if completed.returncode:
                    raise OSError()
                outcome = {"status": "Hazır", "message": "FFmpeg bulundu ve çalışıyor."}
            except (OSError, subprocess.SubprocessError):
                outcome = {"status": "Hata", "message": "FFmpeg çalıştırılamadı veya bulunamadı. Ayarlar ekranını yine kullanabilirsiniz."}
            return {"result": outcome, "settings": settings.safe_view()}
        if section in ("pexels", "pixabay", "ai33"):
            prefix = "AI33 " if section == "ai33" else ""
            return {"result": {"status": "API belgeleri gerekli", "message": prefix + "API belgeleri gerekli. Bu aşamada gerçek bağlantı testi kapalıdır."}, "settings": settings.safe_view()}
        raise SettingsInputError("Bu bağlantı testi kullanılamıyor.")

    @application.post("/api/settings/gemini/models")
    def gemini_models():
        config = settings.gemini_config()
        models = make_script_provider("gemini", settings, discovery=True).list_models()
        view = settings.record_gemini_models(config, models)
        return {"models": view['gemini']['models'], 'settings': view}

    def image_provider(name):
        config = settings.image_config()
        if name == 'local': return LocalGPUImageProvider(config)
        if name == 'gemini': return GeminiImageProvider(settings.gemini_config().get('api_key', ''), config['gemini_model'])
        if name == 'openai': return OpenAIImageProvider(settings.script_config('openai').get('api_key', ''), config['openai_model'])
        raise SettingsInputError('Geçerli görsel sağlayıcısını seçin.')

    @application.post('/api/settings/images/{provider}/test')
    def image_connection(provider: str):
        started, category = time.monotonic(), 'success'
        try:
            return {'result': image_provider(provider).test_connection()}
        except ScriptProviderError as error:
            category = error.category
            raise
        finally:
            name = provider if provider in ('local', 'gemini', 'openai') else 'unknown'
            logging.getLogger('uvicorn.error.providers').info('provider=%s operation=image_test category=%s elapsed_ms=%.0f', name, category, (time.monotonic() - started) * 1000)

    @application.post('/api/settings/images/{provider}/models')
    def image_models(provider: str):
        tested = settings.gemini_config() if provider == 'gemini' else settings.image_config()
        models = image_provider(provider).models() if provider in ('gemini', 'local') else []
        return {'images': settings.record_image_models(provider, models, tested)}

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        message = "Bu sayfa bulunamadı. Ana sayfaya dönüp yeniden deneyin." if error.status_code == 404 else "İstek tamamlanamadı. Ana sayfaya dönüp yeniden deneyin."
        return JSONResponse(status_code=error.status_code, content={"message": message}, headers=error.headers)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        if request.url.path == '/api/settings/gemini' or request.url.path.startswith('/api/settings/gemini/'):
            return gemini_unexpected_response()
        return JSONResponse(status_code=500, content={"message": "İşlem tamamlanamadı. Uygulamayı kapatıp yeniden açın; sorun sürerse Tanılama sayfasını kontrol edin."})

    @application.get("/api/health")
    def health():
        healthy = database_healthy(storage / "app.db") and directory_writable(storage)
        return JSONResponse(status_code=200 if healthy else 503, content={
            "status": "ok" if healthy else "error", "version": __version__,
            "message": "Uygulama hazır." if healthy else "Veri klasörü veya veritabanı kullanılamıyor. Uygulamayı yazma izniniz olan bir klasörde yeniden açın.",
        })

    @application.get("/api/diagnostics")
    def diagnostics():
        return {
            "app_version": __version__, "python_version": platform.python_version(),
            "operating_system": platform.system(),
            "database_ok": database_healthy(storage / "app.db"),
            "data_directory_writable": directory_writable(storage),
            "ffmpeg_found": shutil.which("ffmpeg") is not None,
            "providers": "Senaryo motorları: Gemini, Ollama ve OpenAI (isteğe bağlı). Anahtarlar yalnızca Ayarlar ekranında yönetilir.",
        }

    @application.get("/")
    @application.get("/new-project")
    @application.get("/projects")
    @application.get("/projects/{project_id}")
    @application.get("/projects/{project_id}/script")
    @application.get('/projects/{project_id}/production')
    @application.get("/settings")
    @application.get('/settings/ai-diagnostics')
    @application.get("/diagnostics")
    def page():
        return FileResponse(STATIC / "index.html")

    return application


app = create_app()
