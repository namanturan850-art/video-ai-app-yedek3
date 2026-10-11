"""Screens are revalidated on every open so an update is visible without a hard refresh."""
from fastapi.testclient import TestClient

from app.main import create_app


def test_screens_and_scripts_are_revalidated(tmp_path):
    with TestClient(create_app(tmp_path / 'data')) as client:
        for path in ('/static/channels.js', '/static/style.css', '/channels', '/'):
            r = client.get(path)
            assert r.status_code == 200 and r.headers['cache-control'] == 'no-cache', path
        assert client.get('/static/fonts/Inter.ttf').headers.get('cache-control') != 'no-cache'
