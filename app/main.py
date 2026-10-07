"""Local dashboard and safe diagnostics for milestone one."""
from contextlib import asynccontextmanager
from pathlib import Path
import platform
import shutil
import sqlite3
import tempfile

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app import __version__
from app.database import database_healthy, initialize_database

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
    application.mount("/static", StaticFiles(directory=STATIC), name="static")

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
            "providers": "Bu aşamada hiçbir sağlayıcı bağlı değil.",
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
