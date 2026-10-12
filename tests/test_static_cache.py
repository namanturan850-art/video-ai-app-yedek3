"""Screens are revalidated on every open so an update is visible without a hard refresh."""
from fastapi.testclient import TestClient

from app.main import create_app


def test_screens_and_scripts_are_revalidated(tmp_path):
    with TestClient(create_app(tmp_path / 'data')) as client:
        for path in ('/static/stock.js', '/static/style.css', '/settings', '/'):
            r = client.get(path)
            assert r.status_code == 200 and r.headers['cache-control'] == 'no-cache', path
        assert client.get('/static/fonts/Inter.ttf').headers.get('cache-control') != 'no-cache'
        assert client.get('/channels').status_code == 404  # the hidden Kanallar screen is gone; the channel data/API stay
