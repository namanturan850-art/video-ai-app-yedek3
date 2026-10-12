"""Local dashboard, safe diagnostics and encrypted settings."""
from contextlib import asynccontextmanager
from pathlib import Path
import platform
import sqlite3
import tempfile
import logging
import time

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

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
from app.production import ProductionService
from app.providers.images import LocalGPUImageProvider, GeminiImageProvider, OpenAIImageProvider
from app.provider_diagnostics import ProviderDiagnostics, DiagnosticInputError
from app.stock.service import StockService
from app.stock.routes import stock_router
from app.stock.models import StockError
from app.narration.service import NarrationService
from app.narration.routes import narration_router
from app.narration.models import NarrationError
from app.subtitles.service import SubtitleService
from app.subtitles.routes import subtitle_router
from app.subtitles.models import SubtitleError
from app.rendering.service import RenderService
from app.rendering.routes import render_router
from app.rendering.models import RenderError

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
            stock.recover()
            narration.recover()
            rendering.recover()
        except (OSError, sqlite3.Error) as error:
            raise RuntimeError("Veri klasörü açılamadı. Uygulamayı yazma izniniz olan bir klasöre taşıyıp yeniden açın.") from error
        try:
            yield
        finally:
            rendering.close()
            narration.close()
            stock.close()
            ai_diagnostics.close()
            director.close()
            scripts.close()

    application = FastAPI(title="AI Video Studio", version=__version__, lifespan=lifespan)
    settings = SettingsService(SettingsStore(storage / "secrets"))
    application.state.settings = settings
    ai_diagnostics = ProviderDiagnostics(settings)
    application.state.ai_diagnostics = ai_diagnostics
    projects = ProjectService(storage)
    application.state.projects = projects
    from app.channels import ChannelService
    from app.ai_usage import UsageLedger
    settings.usage_ledger = UsageLedger(projects)
    application.state.usage = settings.usage_ledger
    scripts = ScriptService(projects, settings)
    application.state.scripts = scripts
    quality = QualityService(scripts)
    application.state.quality = quality
    production = ProductionService(scripts)
    quality.production = production
    application.state.production = production
    from app.director import DirectorService
    director = DirectorService(scripts, quality, production, settings)
    application.state.director = director
    from app.source_analysis import SourceService
    sources = SourceService(projects, settings, scripts.repository)
    application.state.sources = scripts.sources = director.sources = sources
    channels = ChannelService(projects, settings)
    application.state.channels = channels
    stock = StockService(production,settings)
    application.state.stock = stock
    application.include_router(stock_router(stock))
    narration=NarrationService(scripts,settings)
    application.state.narration=narration
    application.include_router(narration_router(narration))
    subtitles=SubtitleService(narration,production,stock)
    stock.timing_handoff=subtitles.handoff
    application.state.subtitles=subtitles
    application.include_router(subtitle_router(subtitles))
    rendering=RenderService(subtitles,production,settings)
    rendering.channels=channels
    narration.channels=channels
    stock.channels=channels
    application.state.rendering=rendering
    stock.openmontage=rendering.openmontage
    from app.integrations.openmontage.routes import router as openmontage_router
    application.include_router(openmontage_router(rendering.openmontage))
    application.include_router(render_router(rendering))
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    application.mount("/static", StaticFiles(directory=STATIC), name="static")

    @application.middleware("http")
    async def fresh_screens(request: Request, call_next):
        # Screens (HTML/JS/CSS) must be revalidated on every open; otherwise a
        # browser can keep showing the previous version after an update.
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/") and path.endswith((".js", ".css", ".html")) or "text/html" in response.headers.get("content-type", ""):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @application.middleware("http")
    async def protect_local_data(request: Request, call_next):
        scope = "settings" if request.url.path.startswith("/api/settings") else "projects"
        if request.url.path.startswith(("/api/settings", "/api/projects", "/api/channels")):
            origin = request.headers.get("origin")
            same_origin = not origin or origin == f"{request.url.scheme}://{request.url.netloc}"
            mutation = request.method not in ("GET", "HEAD")
            if not same_origin or (mutation and request.headers.get("x-ai-video-studio") != scope):
                message = "Ayarlar yalnızca uygulamanın Ayarlar ekranından değiştirilebilir. Sayfayı yeniden açın." if scope == "settings" else "Projeler yalnızca uygulamanın proje ekranından değiştirilebilir. Sayfayı yeniden açın."
                return JSONResponse(status_code=403, content={"message": message}, headers={"Cache-Control": "no-store"})
            gemini = request.url.path == '/api/settings/gemini' or request.url.path.startswith('/api/settings/gemini/')
            script_route = any(part in request.url.path for part in ('/script', '/director', '/production','/narration','/subtitles','/render','/youtube')) and request.url.path.startswith('/api/projects/')
            stock_route = '/production/stock' in request.url.path
            settings_route = request.url.path.startswith('/api/settings')
            started = time.monotonic()
            try:
                response = await call_next(request)
            except Exception:
                if not settings_route and not script_route:
                    raise
                if script_route:
                    if "/render" in request.url.path:
                        logging.getLogger("uvicorn.error.rendering").warning("render operation=request category=unexpected_backend")
                        return JSONResponse(status_code=500,content={"message":"Video işlemi tamamlanamadı. Önceki videolar ve kaynak dosyalar korundu; tekrar deneyin.","category":"unexpected_backend"},headers={"Cache-Control":"no-store"})
                    if '/subtitles' in request.url.path:
                        logging.getLogger('uvicorn.error.subtitles').warning('subtitles operation=request category=unexpected_backend')
                        return JSONResponse(status_code=500,content={'message':'Altyazı işlemi tamamlanamadı. Önceki sürümler ve dosyalar korundu; sayfayı yenileyin.','category':'unexpected_backend'},headers={'Cache-Control':'no-store'})
                    if '/narration' in request.url.path:
                        return JSONResponse(status_code=500,content={'message':'Seslendirme işlemi tamamlanamadı. Görev ve dosyalar korundu; sayfayı yenileyin.','category':'unexpected_backend'},headers={'Cache-Control':'no-store'})
                    if stock_route:
                        return JSONResponse(status_code=500, content={'message':'Medya işlemi tamamlanamadı. Tamamlanan dosyalar korundu; yenileyip tekrar deneyin.',
                                                                     'category':'unexpected_backend'}, headers={'Cache-Control':'no-store'})
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

    @application.exception_handler(StockError)
    async def stock_error(request: Request, error: StockError):
        return JSONResponse(status_code=error.status_code, content={'message': str(error),'category':error.category})

    @application.exception_handler(NarrationError)
    async def narration_error(request:Request,error:NarrationError):
        from app.scripts.engine import SecretGuard
        content={'message':str(error),'category':error.category}
        if error.diagnostic:content['diagnostic']=error.diagnostic
        return JSONResponse(status_code=error.status_code,content=SecretGuard(settings.secret_values()).clean(content))

    @application.exception_handler(SubtitleError)
    async def subtitle_error(request:Request,error:SubtitleError):
        from app.scripts.engine import SecretGuard
        logging.getLogger('uvicorn.error.subtitles').warning('subtitles operation=request result=failure category=%s',error.category)
        return JSONResponse(status_code=error.status_code,content=SecretGuard(settings.secret_values()).clean({'message':str(error),'category':error.category}))

    @application.exception_handler(RenderError)
    async def render_error(request:Request,error:RenderError):
        from app.scripts.engine import SecretGuard
        return JSONResponse(status_code=error.status_code,content=SecretGuard(settings.secret_values()).clean({'message':str(error),'category':error.category}))

    def director_options():
        """Claude as default director when chosen; configured backups to offer on failure."""
        view = settings.safe_view()
        engine = settings.ai_engine()
        backups = [name for name in ('gemini', 'ollama', 'openai') if view[name]['status'] != 'Yapılandırılmadı' and name != engine]
        return {'claude_ready': view['claude']['has_api_key'], 'claude_default': settings.claude_director(), 'backup_providers': backups,
                'engine': engine, 'engine_label': {'claude': 'Claude (ücretli)', 'gemini': 'Gemini (ücretsiz kota)'}.get(engine, ''),
                'engine_paid': engine == 'claude'}

    @application.get('/api/projects/{project_id}/script')
    def get_script(project_id: str):
        result = {**scripts.repository.view(project_id), 'artifacts': quality.results(project_id), 'director': director_options()}
        # Real narration length once audio exists (beats any estimate).
        try:
            active = narration.view(project_id).get('active')
            audio = (active or {}).get('metadata', {}).get('audio') or {}
            result['narration'] = {'duration': audio.get('duration'), 'version_id': (active or {}).get('source_script_version_id')} if audio.get('duration') else None
        except Exception:
            result['narration'] = None
        # Gemini (free tier) everywhere by default; Claude only when the owner
        # ticked it in Settings. Never Ollama on its own: when Gemini cannot
        # plan, the screen asks (Ollama or the no-AI local plan).
        result['default_provider'] = result['director']['engine'] or 'gemini'
        return result

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

    @application.put('/api/projects/{project_id}/production/scenes/{scene_id}')
    def edit_production_scene(project_id: str, scene_id: str, payload: dict): return production.edit_scene(project_id,scene_id,payload)

    @application.post('/api/projects/{project_id}/production/scenes/{scene_id}/actions')
    def production_scene_action(project_id: str, scene_id: str, payload: dict): return production.scene_action(project_id,scene_id,payload)

    @application.post('/api/projects/{project_id}/production/scenes/{scene_id}/regenerate',status_code=202)
    def regenerate_production_scene(project_id: str, scene_id: str, payload: dict): return quality.start_scene(project_id,scene_id,payload)

    @application.post('/api/projects/{project_id}/production/versions/{plan_id}/select')
    def choose_production_plan(project_id: str, plan_id: str, payload: dict): return production.select_plan(project_id,plan_id,payload)

    @application.get('/api/projects/{project_id}/production/handoff')
    def production_handoff(project_id: str): return production.handoff(project_id)

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
        if set(payload)-{'confirm_replace_approved','visual_repair_cost_confirmed'} or type(payload.get('confirm_replace_approved')) is not bool or 'visual_repair_cost_confirmed' in payload and type(payload['visual_repair_cost_confirmed']) is not bool:
            raise ScriptError('Devam Et için açık onay tercihi gerekli.')
        action=scripts.repository.job(job_id)['action']
        if 'visual_repair_cost_confirmed' in payload and action not in ('visual','visual_scene'):
            raise ScriptError('Görsel düzeltme onayı yalnızca sahne planı işlemlerinde kullanılabilir.')
        if action not in ('generate', 'analyze'):
            return quality.resume(project_id, job_id, payload['confirm_replace_approved'],visual_repair_cost_confirmed=payload.get('visual_repair_cost_confirmed',False))
        return scripts.resume(project_id, job_id, payload['confirm_replace_approved'])

    @application.get('/api/projects/{project_id}/script/paste')
    def paste_view(project_id: str):
        return scripts.paste_view(project_id)

    @application.post('/api/projects/{project_id}/script/paste/preview')
    def paste_preview(project_id: str, payload: dict):
        return scripts.paste_preview(project_id, payload)

    @application.post('/api/projects/{project_id}/script/paste', status_code=201)
    def paste_script(project_id: str, payload: dict):
        return scripts.paste(project_id, payload)

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
        if isinstance(payload, dict) and not str(payload.get('topic', '')).strip() and str(payload.get('name', '')).strip():
            payload = {**payload, 'topic': payload['name']}  # “Metni yapıştır” flow: title and language are enough
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
            project['pipeline'][1].update(status=view['status'], message='Senaryoyu açıp inceleyebilir, düzenleyebilir ve onaylayabilirsiniz.' if settings.script_generation()
                                          else 'Metin kaydedildi. Düzenleyip yeni sürüm kaydedebilirsiniz.')
        scene_plan = production.view(project_id)['plan']
        if scene_plan:
            project['pipeline'][2].update(status='Plan hazır' if scene_plan['status']=='ready' else 'Eski plan / onay gerekli',
                                         message='Sahne planını açıp düzenleyebilirsiniz.')
        voice=narration.view(project_id)
        if voice['active'] or voice['job']:project['pipeline'][4].update(status='Eski senaryo sürümüne ait' if voice['active'] and voice['active']['stale'] else 'Hazır' if voice['active'] else voice['job']['status_label'] if voice['job'] else 'Bekliyor',
                                     message='Seslendirme ekranından ses seçimini, görev durumunu ve ses sürümlerini inceleyin.')
        rendered=rendering.view(project_id)
        if rendered['job'] or rendered['active']:
            video=rendered['active'];job=rendered['job']
            state='Eski kaynaklara ait' if video and video['stale'] else 'Hazır' if video and not video['video_missing'] else job['status_label'] if job else 'Bekliyor'
            if job and job['status'] in ('queued','preparing','rendering','validating'):state=job['status_label']
            project['pipeline'][6].update(status=state,message='Video Oluştur / Render ekranında yerel videoyu inceleyin.')
        subtitle_status=subtitles.pipeline_status(project_id)
        if subtitle_status!='Bekliyor':
            project['pipeline'][5].update(status=subtitle_status,message='Altyazı ve Zamanlama ekranında yaklaşık ses zamanlarını inceleyin.')
        if scene_plan and scene_plan['status']=='ready':
            project['pipeline'][3].update(status='Hazır' if subtitles.stock_ready(project_id,scene_plan) else 'Bekliyor',message='Stok Medya ekranında yerel dosyaları inceleyin.')
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

    @application.get('/api/projects/{project_id}/director')
    def director_view(project_id: str):
        return {**director.view(project_id), 'options': director_options()}

    @application.post('/api/projects/{project_id}/director/run', status_code=202)
    def director_run(project_id: str, payload: dict):
        return director.start(project_id, payload)

    @application.put('/api/projects/{project_id}/director/purpose')
    def director_purpose(project_id: str, payload: dict):
        return {'purpose': director.save_purpose(project_id, payload), 'message': 'Amaç özeti kaydedildi. Senaryo bir sonraki yönetmen çalıştırmasında bu özete göre yazılır.'}

    from app.youtube import YouTubeService
    youtube = YouTubeService(projects, scripts, production, rendering, stock, channels, settings)
    application.state.youtube = youtube

    @application.get('/api/projects/{project_id}/youtube')
    def youtube_view(project_id: str):
        return youtube.view(project_id)

    @application.post('/api/projects/{project_id}/youtube/text')
    def youtube_text(project_id: str):
        return youtube.generate_text(project_id)

    @application.put('/api/projects/{project_id}/youtube')
    def youtube_update(project_id: str, payload: dict):
        return youtube.update(project_id, payload)

    @application.post('/api/projects/{project_id}/youtube/check')
    def youtube_check(project_id: str):
        return youtube.proofread(project_id)

    @application.get('/api/channels')
    def list_channels():
        return {'channels': channels.list(), 'options': channels.options(), 'engine': settings.ai_engine()}

    @application.post('/api/channels', status_code=201)
    def create_channel(payload: dict):
        return channels.create(payload)

    @application.get('/api/projects/{project_id}/source')
    def get_source(project_id: str):
        return sources.view(project_id)

    @application.put('/api/projects/{project_id}/source/transcript')
    def save_transcript(project_id: str, payload: dict):
        return sources.save_transcript(project_id, payload.get('transcript') if isinstance(payload, dict) else None)

    @application.post('/api/projects/{project_id}/source/analyze')
    def analyze_source(project_id: str):
        return sources.analyze(project_id)

    @application.get('/api/projects/{project_id}/look')
    def get_look(project_id: str):
        projects.get(project_id)
        return channels.look(project_id)

    @application.put('/api/projects/{project_id}/look')
    def set_look(project_id: str, payload: dict):
        projects.get(project_id)
        return channels.set_look(project_id, payload.get('look') if isinstance(payload, dict) else None)

    @application.get('/api/channels/{channel_id}')
    def get_channel(channel_id: str):
        return channels.get(channel_id)

    @application.put('/api/channels/{channel_id}')
    def update_channel(channel_id: str, payload: dict):
        return channels.update(channel_id, payload)

    @application.delete('/api/channels/{channel_id}')
    def delete_channel(channel_id: str):
        return channels.delete(channel_id)

    @application.post('/api/channels/{channel_id}/style/suggest')
    def suggest_style(channel_id: str, payload: dict):
        return channels.suggest(channel_id, payload)

    @application.post('/api/channels/{channel_id}/sfx/{name}')
    async def upload_sfx(channel_id: str, name: str, request: Request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 5_000_000: raise ProjectError('Ses efekti dosyası 5 MB’dan büyük.')
        return channels.upload_sfx(channel_id, name, request.headers.get('x-file-name', ''), bytes(data))

    @application.get('/api/channels/{channel_id}/sfx/{name}')
    def play_sfx(channel_id: str, name: str):
        from app.channels import SFX_NAMES, SFX_TYPES
        channel = channels.get(channel_id)
        if name not in SFX_NAMES: raise ProjectError('Ses efekti bulunamadı.', 404)
        path = channels.sfx_path(channel_id, channel['style']['sfx'][name])
        if path is None: raise ProjectError('Bu ses efekti kapalı.', 404)
        return FileResponse(path, media_type=SFX_TYPES.get(path.suffix, (None, 'audio/wav'))[1], headers={'Cache-Control': 'no-store'})

    @application.get('/api/projects/{project_id}/ai-usage')
    def project_ai_usage(project_id: str):
        projects.get(project_id)
        return settings.usage_ledger.project_summary(project_id)

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
        if section == 'claude':
            config = settings.script_config('claude')
            started = time.monotonic()
            try:
                outcome = make_script_provider('claude', settings).test_connection()
            except ScriptProviderError as error:
                outcome = {'status': 'Hata', 'message': str(error), 'category': error.category}
            logging.getLogger('uvicorn.error.providers').info('provider=claude operation=test category=%s elapsed_ms=%.0f', outcome.get('category', 'success'), (time.monotonic() - started) * 1000)
            return {'result': outcome, 'settings': settings.record_claude_test(config, outcome)}
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
            outcome = {'status':'Hazır' if detected['found'] else 'Hata','message':detected['message']}
            return {"result": outcome, "settings": settings.safe_view()}
        if section == 'youtube':
            from app.integrations.youtube_data import YouTubeDataError
            config = settings.stock_config('youtube')
            try:outcome = sources.youtube_factory(config.get('api_key','')).test()
            except YouTubeDataError as error:outcome = {'status':'Hata','message':str(error),'category':error.category}
            return {'result':outcome,'settings':settings.record_stock_test('youtube',config,outcome)}
        if section == 'wikimedia':  # no key: one small image search against the official API
            from app.stock.providers import make_stock_provider
            try:
                found = make_stock_provider('wikimedia', settings).search_images('roman forum')
                outcome = {'status':'Hazır','message':f'Wikimedia Commons bağlantısı başarılı ({len(found)} ticari kullanıma uygun görsel bulundu).','category':'none'}
            except StockError as error:
                outcome = {'status':'Hata','message':str(error),'category':error.category}
            return {'result':outcome,'settings':settings.record_stock_test('wikimedia',{},outcome)}
        if section in ('pexels','pixabay'):
            from app.stock.providers import make_stock_provider
            from datetime import datetime, timedelta, timezone
            config = settings.stock_config(section)
            cached = config.get('last_test',{})
            if section=='pixabay' and cached.get('status')=='Hazır' and cached.get('checked_at'):
                try:
                    if datetime.fromisoformat(cached['checked_at']) > datetime.now(timezone.utc)-timedelta(hours=24):
                        return {'result':{'status':'Hazır','category':'none','message':'Pixabay: son 24 saat içindeki başarılı test kullanıldı (API önbellek kuralı).'},'settings':settings.safe_view()}
                except (ValueError,TypeError): pass
            try:
                make_stock_provider(section,settings).search_images('nature landscape')
                outcome = {'status':'Hazır','message':section.title()+' API bağlantısı başarılı. Medya araması kullanılabilir.','category':'none',
                           'checked_at':datetime.now(timezone.utc).isoformat()}
            except StockError as error:
                outcome = {'status':'Hata','message':str(error),'category':error.category}
            return {'result':outcome,'settings':settings.record_stock_test(section,config,outcome)}
        if section == "ai33":
            config=settings.tts_config()
            try:outcome=narration.factory(settings).test_connection()
            except NarrationError as error:outcome={'status':'Hata','message':str(error),'category':error.category}
            return {'result':outcome,'settings':settings.record_tts_test(config,outcome)}
        raise SettingsInputError("Bu bağlantı testi kullanılamıyor.")

    @application.post('/api/settings/ai33/voices')
    def tts_voices(payload:dict):
        if set(payload)-{'provider','search','page','page_size'}:
            raise NarrationError('invalid_request','Ses arama alanlarını kontrol edin.',422)
        tested=settings.tts_config()
        result=narration.factory(settings).list_voices(payload.get('provider'),payload.get('search',''),payload.get('page',1),payload.get('page_size',30))
        return {'voices':result,'settings':settings.record_tts_voices(tested,result)}

    @application.post('/api/settings/ai33/tasks/diagnose')
    def tts_task_history(payload:dict):
        if payload:raise NarrationError('invalid_request','Görev geçmişi tanısı ek alan almaz.',422)
        diagnostic=narration.factory(settings).task_history_diagnostic()
        return {'diagnostic':diagnostic,'message':'Görev geçmişi alındı. Alan adları/türleri ve varsa güvenli durum/tür değerleri gösterilir; yeni görev oluşturulmadı.'}

    @application.post('/api/settings/ai33/task/diagnose')
    def tts_existing_task(payload:dict):
        if set(payload)!={'task_id'}:raise NarrationError('invalid_task_id','İncelemek istediğiniz mevcut görevin Task ID bilgisini girin.',422)
        diagnostic=narration.factory(settings).task_diagnostic(payload['task_id'])
        message='Canlı AI33 TTS görev yapısı doğrulandı. Mevcut görev salt okunur incelendi; yeni ücretli görev oluşturulmadı.'
        return {'diagnostic':diagnostic,'message':message}

    @application.post('/api/settings/gemini/quota-reset')
    def gemini_quota_reset():
        # The owner says the quota is back (e.g. billing turned on): try every chain model again.
        return settings.clear_gemini_exhausted()

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
            "ffmpeg_found": ffmpeg_status()["found"],
            "providers": "Senaryo motorları: Gemini, Ollama ve OpenAI (isteğe bağlı). Anahtarlar yalnızca Ayarlar ekranında yönetilir.",
        }

    @application.get("/")
    @application.get("/new-project")
    @application.get("/projects")
    @application.get("/projects/{project_id}")
    @application.get("/projects/{project_id}/script")
    @application.get('/projects/{project_id}/production')
    @application.get('/projects/{project_id}/narration')
    @application.get('/projects/{project_id}/subtitles')
    @application.get('/projects/{project_id}/render')
    @application.get('/projects/{project_id}/youtube')
    @application.get("/settings")
    @application.get('/settings/ai-diagnostics')
    @application.get("/diagnostics")
    def page():
        # The page knows whether AI script writing is on (default: off).
        html = (STATIC / "index.html").read_text(encoding='utf-8')
        flag = '1' if settings.script_generation() else '0'
        return HTMLResponse(html.replace('<body>', f'<body data-script-generation="{flag}">', 1))

    return application


app = create_app()
