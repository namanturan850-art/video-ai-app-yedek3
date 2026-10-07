import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.database import database_healthy, initialize_database
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "data")) as client:
        yield client


def test_health_initializes_database(tmp_path):
    data = tmp_path / "nested" / "data"
    assert not data.exists()
    with TestClient(create_app(data)) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["version"] == "0.1.0"
    assert database_healthy(data / "app.db")


def test_database_initialization_preserves_existing_data(tmp_path):
    database = initialize_database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO app_metadata VALUES ('keep', 'existing')")
    initialize_database(tmp_path)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='keep'").fetchone() == ("existing",)
        assert connection.execute("SELECT count(*) FROM app_metadata WHERE key='schema_version'").fetchone() == (1,)


@pytest.mark.parametrize("route", ["/", "/new-project", "/projects", "/settings", "/diagnostics"])
def test_pages_and_static_assets(client, route):
    response = client.get(route)
    assert response.status_code == 200
    assert 'lang="tr"' in response.text
    for title in ["Yeni Proje", "Projeler", "Ayarlar", "Tanılama"]:
        assert title in response.text
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_diagnostics_without_ffmpeg_or_secrets(client, monkeypatch):
    monkeypatch.setattr("app.main.shutil.which", lambda name: None)
    monkeypatch.setenv("AI33_API_KEY", "TEST-SECRET-MUST-NOT-LEAK")
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert data["ffmpeg_found"] is False
    assert data["database_ok"] is True
    assert data["data_directory_writable"] is True
    assert data["python_version"]
    assert data["operating_system"]
    assert "TEST-SECRET" not in response.text
    assert client.get("/api/health").status_code == 200


def test_health_reports_missing_database(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        (tmp_path / "app.db").unlink()
        assert client.get("/api/health").status_code == 503
        assert client.get("/api/diagnostics").json()["database_ok"] is False
        assert not (tmp_path / "app.db").exists()


def test_corrupt_database_is_unhealthy(tmp_path):
    database = tmp_path / "app.db"
    database.write_bytes(b"not a database")
    assert database_healthy(database) is False


def test_diagnostics_reports_unwritable_directory(client, monkeypatch):
    monkeypatch.setattr("app.main.directory_writable", lambda path: False)
    assert client.get("/api/diagnostics").json()["data_directory_writable"] is False
    assert client.get("/api/health").status_code == 503


def test_startup_failure_has_actionable_message(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a directory")
    with pytest.raises(RuntimeError, match="yazma izniniz"):
        with TestClient(create_app(blocked)):
            pass


def test_unknown_page_has_turkish_error(client):
    response = client.get('/missing')
    assert response.status_code == 404
    assert 'Ana sayfaya' in response.json()['message']
