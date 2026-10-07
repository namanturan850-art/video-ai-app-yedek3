"""Local dashboard, safe diagnostics and encrypted settings."""
from contextlib import asynccontextmanager
from pathlib import Path
import platform
import shutil
import sqlite3
import tempfile

from fastapi import FastAPI, Request
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

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"


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
        except (OSError, sqlite3.Error) as error:
            raise RuntimeError("Veri klasörü açılamadı. Uygulamayı yazma izniniz olan bir klasöre taşıyıp yeniden açın.") from error
        yield

    application = FastAPI(title="AI Video Studio", version=__version__, lifespan=lifespan)
    settings = SettingsService(SettingsStore(storage / "secrets"))
    application.state.settings = settings
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    application.mount("/static", StaticFiles(directory=STATIC), name="static")

    @application.middleware("http")
    async def protect_settings(request: Request, call_next):
        if request.url.path.startswith("/api/settings"):
            origin = request.headers.get("origin")
            same_origin = not origin or origin == f"{request.url.scheme}://{request.url.netloc}"
            mutation = request.method not in ("GET", "HEAD")
            if not same_origin or (mutation and request.headers.get("x-ai-video-studio") != "settings"):
                return JSONResponse(status_code=403, content={"message": "Ayarlar yalnızca uygulamanın Ayarlar ekranından değiştirilebilir. Sayfayı yeniden açın."}, headers={"Cache-Control": "no-store"})
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            return response
        return await call_next(request)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"message": "Bilgiler okunamadı. Alanları kontrol edip yeniden kaydedin."})

    @application.exception_handler(SettingsInputError)
    async def invalid_settings(request: Request, error: SettingsInputError):
        return JSONResponse(status_code=422, content={"message": str(error)})

    @application.exception_handler(SettingsStorageError)
    async def settings_storage_error(request: Request, error: SettingsStorageError):
        return JSONResponse(status_code=503, content={"message": str(error)})

    @application.get("/api/settings")
    def read_settings():
        return settings.safe_view()

    @application.put("/api/settings/{section}")
    def save_settings(section: str, payload: dict):
        return settings.save(section, payload)

    @application.delete("/api/settings/{section}")
    def clear_settings(section: str):
        return settings.clear(section)

    @application.post("/api/settings/{section}/test")
    def test_connection(section: str):
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
        if section in ("openai", "pexels", "pixabay", "ai33"):
            prefix = "AI33 " if section == "ai33" else ""
            return {"result": {"status": "API belgeleri gerekli", "message": prefix + "API belgeleri gerekli. Bu aşamada gerçek bağlantı testi kapalıdır."}, "settings": settings.safe_view()}
        raise SettingsInputError("Bu bağlantı testi kullanılamıyor.")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        message = "Bu sayfa bulunamadı. Ana sayfaya dönüp yeniden deneyin." if error.status_code == 404 else "İstek tamamlanamadı. Ana sayfaya dönüp yeniden deneyin."
        return JSONResponse(status_code=error.status_code, content={"message": message}, headers=error.headers)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
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
            "providers": "Sağlayıcı tercihleri Ayarlar ekranından yönetilir. İçerik üretimi henüz eklenmedi.",
        }

    @application.get("/")
    @application.get("/new-project")
    @application.get("/projects")
    @application.get("/settings")
    @application.get("/diagnostics")
    def page():
        return FileResponse(STATIC / "index.html")

    return application


app = create_app()
