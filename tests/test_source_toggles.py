"""Settings → NASA / Wikimedia Commons / Internet Archive each get an on/off switch for
Medyayı Tamamla (a switched-off source is not searched, which saves time). Default: on."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.stock.director_media import MediaDirector

HEADERS = {"X-AI-Video-Studio": "settings"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "data"), headers=HEADERS) as c:
        yield c


@pytest.mark.parametrize('name', ['wikimedia', 'nasa', 'archive'])
def test_source_is_on_by_default_and_can_be_switched_off_and_on(client, name):
    view = client.get('/api/settings').json()[name]
    assert view['enabled'] is True and view['status'] == 'Hazır'
    assert client.put(f'/api/settings/{name}', json={'enabled': False}).status_code == 200
    view = client.get('/api/settings').json()[name]
    assert view['enabled'] is False and view['status'] == 'Kapalı' and 'aramaz' in view['message']
    assert client.put(f'/api/settings/{name}', json={'enabled': True}).status_code == 200
    view = client.get('/api/settings').json()[name]
    assert view['enabled'] is True and view['status'] == 'Hazır'


def test_switching_one_source_off_leaves_the_others_alone(client):
    client.put('/api/settings/nasa', json={'enabled': False})
    data = client.get('/api/settings').json()
    assert data['nasa']['enabled'] is False
    assert data['wikimedia']['enabled'] is True and data['archive']['enabled'] is True


def director_with(configs):
    settings = SimpleNamespace(stock_config=lambda name: configs.get(name, {}))
    return MediaDirector(SimpleNamespace(settings=settings), {'project_id': 'p', 'progress': {}})


def test_director_skips_a_switched_off_source():
    director = director_with({'pixabay': {'api_key': 'k'}, 'nasa': {'enabled': False}})
    assert director.providers() == ['pixabay', 'wikimedia', 'archive']


def test_director_uses_every_source_when_nothing_was_switched_off():
    director = director_with({'pixabay': {'api_key': 'k'}})
    assert director.providers() == ['pixabay', 'wikimedia', 'nasa', 'archive']
