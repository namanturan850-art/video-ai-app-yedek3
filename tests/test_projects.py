from contextlib import closing
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
import stat
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.database import database_healthy, initialize_database
from app.main import create_app
from app.projects import FOLDERS, STAGES
from app.secret_store import SettingsStore

HEADERS = {'X-AI-Video-Studio': 'projects'}


def payload(**changes):
    return {'name': 'İlk Projem', 'topic': 'Yeni ve özgün bir doğa hikâyesi', **changes}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'data'), headers=HEADERS) as client:
        yield client


def create(client, **changes):
    response = client.post('/api/projects', json=payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def delete(client, project_id, **kwargs):
    return client.request('DELETE', '/api/projects/' + project_id, json={'confirm': True}, **kwargs)


def test_create_defaults_folders_and_database(client, tmp_path):
    project = create(client)
    assert UUID(project['id']).version == 4
    assert project['status'] == 'draft'
    assert project['status_label'] == 'Taslak'
    assert project['language'] == 'de'
    assert project['language_label'] == 'Almanca'
    assert project['reference_url'] == ''
    assert project['subtitles_enabled'] is True
    assert project['background_music_enabled'] is False
    assert project['thumbnail_planning_enabled'] is True
    root = tmp_path / 'data/projects' / project['id']
    assert {entry.name for entry in root.iterdir()} == set(FOLDERS)
    assert all((root / name).is_dir() for name in FOLDERS)
    assert all(not list((root / name).iterdir()) for name in FOLDERS)
    with closing(sqlite3.connect(tmp_path / 'data/app.db')) as db:
        row = db.execute('SELECT name, topic, language, status FROM projects').fetchone()
    assert row == (project['name'], project['topic'], 'de', 'draft')


def test_all_preferences_saved(client):
    preferences = payload(name='Tercihler', reference_url='https://youtu.be/dQw4w9WgXcQ', language='tr',
                          target_duration_minutes=2.5, content_style='Belgesel', min_scene_duration_seconds=3.5,
                          max_scene_duration_seconds=9, subtitles_enabled=False, background_music_enabled=True,
                          thumbnail_planning_enabled=False)
    project = client.post('/api/projects', json=preferences).json()
    loaded = client.get('/api/projects/' + project['id']).json()
    for key, value in preferences.items():
        assert loaded[key] == value


@pytest.mark.parametrize('changes,field,text', [
    ({'name': ''}, 'name', 'Proje adı gerekli.'),
    ({'name': '   '}, 'name', 'Proje adı gerekli.'),
    ({'topic': ''}, 'topic', 'Konu gerekli.'),
    ({'content_style': ''}, 'content_style', 'stil gerekli.'),
    ({'name': 'a' * 121}, 'name', 'çok uzun'),
    ({'topic': 'a' * 5001}, 'topic', 'çok uzun'),
    ({'name': 'bad\x00name'}, 'name', 'geçersiz karakter'),
    ({'target_duration_minutes': 0.5}, 'target_duration_minutes', 'Video süresi 1 dakikadan kısa olamaz.'),
    ({'target_duration_minutes': 181}, 'target_duration_minutes', 'sınırı aşıyor'),
    ({'target_duration_minutes': True}, 'target_duration_minutes', 'geçerli bir değer'),
    ({'target_duration_minutes': '5'}, 'target_duration_minutes', 'geçerli bir değer'),
    ({'target_duration_minutes': float('inf')}, 'target_duration_minutes', 'sınırı aşıyor'),
    ({'min_scene_duration_seconds': 0}, 'min_scene_duration_seconds', '1 saniyeden kısa'),
    ({'max_scene_duration_seconds': 121}, 'max_scene_duration_seconds', 'sınırı aşıyor'),
    ({'min_scene_duration_seconds': 10, 'max_scene_duration_seconds': 5}, 'scene_range', 'Minimum sahne süresi maksimum süreden büyük olamaz.'),
    ({'target_duration_minutes': 1, 'max_scene_duration_seconds': 70}, 'scene_range', 'toplam video süresini aşamaz'),
    ({'language': 'invalid'}, 'language', 'geçerli bir değer'),
    ({'subtitles_enabled': 'true'}, 'subtitles_enabled', 'geçerli bir değer'),
    ({'background_music_enabled': 1}, 'background_music_enabled', 'geçerli bir değer'),
    ({'thumbnail_planning_enabled': None}, 'thumbnail_planning_enabled', 'geçerli bir değer'),
    ({'reference_url': 'not-a-url'}, 'reference_url', "Geçerli bir YouTube video URL'si"),
    ({'reference_url': 'https://example.com/watch?v=dQw4w9WgXcQ'}, 'reference_url', 'Geçerli bir YouTube'),
    ({'reference_url': 'https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ'}, 'reference_url', 'Geçerli bir YouTube'),
    ({'reference_url': 'https://user:password@youtube.com/watch?v=dQw4w9WgXcQ'}, 'reference_url', 'Geçerli bir YouTube'),
    ({'reference_url': 'https://youtube.com:99999/watch?v=dQw4w9WgXcQ'}, 'reference_url', 'Geçerli bir YouTube'),
    ({'reference_url': 'https://www.youtube.com/'}, 'reference_url', 'Geçerli bir YouTube'),
    ({'reference_url': 'file:///data/app.db'}, 'reference_url', 'Geçerli bir YouTube'),
    ({'api_key': 'dummy-must-not-be-saved'}, 'form', 'API anahtarı'),
    ({'status': 'completed'}, 'form', 'işlem durumu'),
])
def test_validation_no_rows_or_folders(client, tmp_path, changes, field, text):
    # JSON does not support Infinity; send it as a raw invalid numeric token to exercise backend bounds.
    if changes.get('target_duration_minutes') == float('inf'):
        import json
        response = client.post('/api/projects', content=json.dumps(payload(**changes)), headers={'Content-Type': 'application/json'})
    else:
        response = client.post('/api/projects', json=payload(**changes))
    assert response.status_code == 422
    assert text in response.json()['fields'][field]
    assert client.get('/api/projects').json()['projects'] == []
    assert not (tmp_path / 'data/projects').exists()


@pytest.mark.parametrize('url', ['', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5',
                                  'https://youtu.be/dQw4w9WgXcQ', 'https://youtube.com/shorts/dQw4w9WgXcQ',
                                  'https://youtube.com/live/dQw4w9WgXcQ', 'https://youtube.com/embed/dQw4w9WgXcQ'])
def test_reference_url_formats_are_only_saved(client, monkeypatch, url):
    def forbidden(*args, **kwargs):
        raise AssertionError('Part 3 cannot call a provider')
    monkeypatch.setattr('app.main.check_ollama', forbidden)
    monkeypatch.setattr('app.projects.shutil.which', forbidden)
    project = create(client, reference_url=url)
    assert project['reference_url'] == url


def test_required_fields_and_invalid_json(client):
    response = client.post('/api/projects', json={})
    assert response.status_code == 422
    assert response.json()['fields']['name'] == 'Proje adı gerekli.'
    assert response.json()['fields']['topic'] == 'Konu gerekli.'
    for content in ('{bad JSON', '["invalid shape"]'):
        assert client.post('/api/projects', content=content, headers={'Content-Type': 'application/json'}).status_code == 422


def test_unique_projects_list_latest_first(client):
    first = create(client, name='Birinci')
    second = create(client, name='İkinci')
    projects = client.get('/api/projects').json()['projects']
    assert [project['id'] for project in projects] == [second['id'], first['id']]
    assert len({project['id'] for project in projects}) == 2
    for project in projects:
        for key in ('name', 'topic', 'language', 'target_duration_minutes', 'status', 'created_at', 'updated_at'):
            assert key in project


def test_get_detail_pipeline_is_only_placeholders(client):
    project = create(client)
    response = client.get('/api/projects/' + project['id'])
    assert response.status_code == 200
    assert [stage['name'] for stage in response.json()['pipeline']] == list(STAGES)
    assert all(stage['status'] == 'Bekliyor' and 'Hazır değil' in stage['message'] for stage in response.json()['pipeline'])
    assert client.get('/projects/' + project['id']).status_code == 200


@pytest.mark.parametrize('identifier', ['not-an-id', '0' * 32, "' OR 1=1 --"])
def test_missing_or_unsafe_ids(client, identifier):
    assert client.get('/api/projects/' + identifier).status_code == 404
    assert delete(client, identifier).status_code == 404


def test_delete_only_one_project_and_all_its_files(client, tmp_path):
    first = create(client, name='Silinecek')
    second = create(client, name='Korunacak')
    root = tmp_path / 'data/projects'
    (root / first['id'] / 'script/story.txt').write_text('test content')
    keep = root / second['id'] / 'script/keep.txt'
    keep.write_text('keep this')
    assert delete(client, first['id']).status_code == 200
    assert not (root / first['id']).exists()
    assert keep.read_text() == 'keep this'
    assert client.get('/api/projects/' + first['id']).status_code == 404
    assert client.get('/api/projects/' + second['id']).status_code == 200


@pytest.mark.parametrize('confirmation', [None, {}, {'confirm': False}, {'confirm': 1}, {'confirm': 'true'}, {'confirm': True, 'other': True}])
def test_delete_requires_explicit_confirmation(client, tmp_path, confirmation):
    project = create(client)
    response = client.request('DELETE', '/api/projects/' + project['id'], json=confirmation)
    assert response.status_code == 422
    assert 'onay gerekli' in response.json()['message']
    assert client.get('/api/projects/' + project['id']).status_code == 200
    assert (tmp_path / 'data/projects' / project['id']).is_dir()


def test_delete_missing_folder_safely(client, tmp_path):
    project = create(client)
    shutil.rmtree(tmp_path / 'data/projects' / project['id'])
    assert delete(client, project['id']).status_code == 200
    assert client.get('/api/projects').json()['projects'] == []


def test_delete_missing_projects_root_safely(client, tmp_path):
    project = create(client)
    shutil.rmtree(tmp_path / 'data/projects')
    assert delete(client, project['id']).status_code == 200


def test_creation_uses_id_not_user_name_as_path(client, tmp_path):
    project = create(client, name='../../secrets/../../outside')
    assert (tmp_path / 'data/projects' / project['id']).is_dir()
    assert not (tmp_path / 'outside').exists()


def symlink(source, target):
    try:
        source.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip('Creating symlinks needs OS permission')


def test_project_root_symlink_blocks_creation_and_deletion(client, tmp_path):
    project = create(client)
    projects = tmp_path / 'data/projects'
    moved = tmp_path / 'preserved-projects'
    projects.rename(moved)
    symlink(projects, moved)
    assert delete(client, project['id']).status_code == 409
    assert client.post('/api/projects', json=payload()).status_code == 409
    assert (moved / project['id']).is_dir()
    assert client.get('/api/projects/' + project['id']).status_code == 200


def test_nested_symlink_to_other_project_cannot_be_deleted(client, tmp_path):
    first = create(client)
    second = create(client)
    root = tmp_path / 'data/projects'
    target = root / second['id']
    (target / 'script/keep.txt').write_text('keep')
    symlink(root / first['id'] / 'stock/link', target)
    assert delete(client, first['id']).status_code == 409
    assert (target / 'script/keep.txt').read_text() == 'keep'
    assert client.get('/api/projects/' + first['id']).status_code == 200


def test_linked_project_folder_and_reparse_point_are_rejected(client, tmp_path, monkeypatch):
    project = create(client)
    path = tmp_path / 'data/projects' / project['id']
    original = Path.lstat
    def lstat(candidate):
        if candidate == path:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(candidate)
    monkeypatch.setattr(Path, 'lstat', lstat)
    assert delete(client, project['id']).status_code == 409
    assert client.get('/api/projects/' + project['id']).status_code == 200


def test_project_folder_replaced_by_file_is_preserved(client, tmp_path):
    project = create(client)
    path = tmp_path / 'data/projects' / project['id']
    shutil.rmtree(path)
    path.write_text('unexpected file')
    assert delete(client, project['id']).status_code == 409
    assert path.read_text() == 'unexpected file'


def test_file_deletion_failure_keeps_record(client, tmp_path, monkeypatch):
    project = create(client)
    def fail(path):
        raise PermissionError('locked file')
    monkeypatch.setattr('app.projects.shutil.rmtree', fail)
    response = delete(client, project['id'])
    assert response.status_code == 503
    assert 'kayıt korundu' in response.json()['message']
    assert client.get('/api/projects/' + project['id']).status_code == 200
    assert (tmp_path / 'data/projects' / project['id']).exists()


def test_partial_creation_failure_cleans_only_owned_folder(client, tmp_path, monkeypatch):
    existing = create(client)
    original = Path.mkdir
    def mkdir(path, *args, **kwargs):
        if path.name == 'voice':
            raise OSError('test failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', mkdir)
    assert client.post('/api/projects', json=payload()).status_code == 503
    assert [entry.name for entry in (tmp_path / 'data/projects').iterdir()] == [existing['id']]
    assert len(client.get('/api/projects').json()['projects']) == 1


def test_uuid_collision_never_cleans_existing_project(client, tmp_path, monkeypatch):
    existing = create(client)
    marker = tmp_path / 'data/projects' / existing['id'] / 'logs/keep.txt'
    marker.write_text('keep')
    monkeypatch.setattr('app.projects.uuid4', lambda: SimpleNamespace(hex=existing['id']))
    assert client.post('/api/projects', json=payload()).status_code == 503
    assert marker.read_text() == 'keep'
    assert client.get('/api/projects/' + existing['id']).status_code == 200


def test_database_insert_error_rolls_back_folders(client, tmp_path):
    with closing(sqlite3.connect(tmp_path / 'data/app.db')) as connection, connection:
        connection.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON projects BEGIN SELECT RAISE(ABORT, 'test'); END")
    assert client.post('/api/projects', json=payload()).status_code == 503
    assert client.get('/api/projects').json()['projects'] == []
    assert not list((tmp_path / 'data/projects').iterdir())


def test_database_delete_error_preserves_folders(client, tmp_path):
    project = create(client)
    with closing(sqlite3.connect(tmp_path / 'data/app.db')) as connection, connection:
        connection.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON projects BEGIN SELECT RAISE(ABORT, 'test'); END")
    assert delete(client, project['id']).status_code == 503
    assert (tmp_path / 'data/projects' / project['id']).is_dir()
    assert client.get('/api/projects/' + project['id']).status_code == 200


def test_timestamps_update_without_changing_created_at(client):
    project = create(client)
    created = datetime.fromisoformat(project['created_at'])
    assert created.utcoffset().total_seconds() == 0
    assert project['updated_at'] == project['created_at']
    updated = client.patch('/api/projects/' + project['id'], json={'name': 'Yeni ad', 'topic': 'Yeni konu'}).json()
    assert updated['name'] == 'Yeni ad'
    assert updated['topic'] == 'Yeni konu'
    assert updated['created_at'] == project['created_at']
    assert datetime.fromisoformat(updated['updated_at']) > created
    assert updated['id'] == project['id']


@pytest.mark.parametrize('changes', [{'api_key': 'never-store-this-dummy'}, {'status': 'completed'}, {'id': '0' * 32}, {}, {'name': ''}])
def test_unsafe_or_invalid_updates_do_not_change_record(client, changes):
    project = create(client)
    response = client.patch('/api/projects/' + project['id'], json=changes)
    assert response.status_code == 422
    assert client.get('/api/projects/' + project['id']).json() == project


def test_application_restart_persistence_and_settings_preservation(tmp_path):
    storage = tmp_path / 'data'
    with TestClient(create_app(storage), headers=HEADERS) as client:
        project = create(client)
        response = client.put('/api/settings/pexels', json={'api_key': 'synthetic-only-1234'}, headers={'X-AI-Video-Studio': 'settings'})
        assert response.status_code == 200
    with TestClient(create_app(storage), headers=HEADERS) as client:
        assert client.get('/api/projects/' + project['id']).json() == project
        assert client.get('/api/projects').json()['projects'][0]['id'] == project['id']
        assert client.get('/api/settings').json()['pexels']['masked_api_key'].endswith('1234')
        assert client.get('/api/health').status_code == 200
        assert all((storage / 'projects' / project['id'] / folder).is_dir() for folder in FOLDERS)
    with closing(sqlite3.connect(storage / 'app.db')) as connection:
        assert 'synthetic-only-1234' not in '\n'.join(connection.iterdump())
        assert 'api_key' not in {row[1] for row in connection.execute('PRAGMA table_info(projects)')}


def test_legacy_upgrade_preserves_data_and_encrypted_settings(tmp_path):
    storage = tmp_path / 'data'
    storage.mkdir()
    database = storage / 'app.db'
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute('CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.execute("INSERT INTO app_metadata VALUES ('schema_version', '1')")
        connection.execute("INSERT INTO app_metadata VALUES ('keep', 'existing')")
        connection.execute('CREATE TABLE legacy_user_data (value TEXT)')
        connection.execute("INSERT INTO legacy_user_data VALUES ('do not lose')")
    store = SettingsStore(storage / 'secrets')
    store.write({'pexels': {'api_key': 'synthetic-only-1234'}})
    before_key = store.key_path.read_bytes()
    before_vault = store.vault_path.read_bytes()
    keep = storage / 'projects/legacy-folder/file.txt'
    keep.parent.mkdir(parents=True)
    keep.write_text('preserve')
    initialize_database(storage)
    initialize_database(storage)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone() == ('2',)
        assert connection.execute("SELECT value FROM app_metadata WHERE key='keep'").fetchone() == ('existing',)
        assert connection.execute('SELECT value FROM legacy_user_data').fetchone() == ('do not lose',)
    assert before_key == store.key_path.read_bytes()
    assert before_vault == store.vault_path.read_bytes()
    assert keep.read_text() == 'preserve'
    assert database_healthy(database)


def test_failed_migration_is_transactional(tmp_path):
    database = tmp_path / 'app.db'
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute('CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.execute("INSERT INTO app_metadata VALUES ('schema_version', '1')")
        connection.execute('CREATE TABLE projects (legacy TEXT)')
        connection.execute("INSERT INTO projects VALUES ('keep')")
    with pytest.raises(sqlite3.Error):
        initialize_database(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone() == ('1',)
        assert connection.execute('SELECT legacy FROM projects').fetchone() == ('keep',)


def test_future_schema_is_not_downgraded(tmp_path):
    database = tmp_path / 'app.db'
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute('CREATE TABLE app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.execute("INSERT INTO app_metadata VALUES ('schema_version', '99')")
    with pytest.raises(sqlite3.DatabaseError):
        initialize_database(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone() == ('99',)


@pytest.mark.parametrize('status,label', [('draft', 'Taslak'), ('ready', 'Hazır'), ('processing', 'İşleniyor'), ('completed', 'Tamamlandı'), ('error', 'Hata')])
def test_database_statuses_and_turkish_labels(client, tmp_path, status, label):
    project = create(client)
    with closing(sqlite3.connect(tmp_path / 'data/app.db')) as connection, connection:
        connection.execute('UPDATE projects SET status=? WHERE id=?', (status, project['id']))
    assert client.get('/api/projects/' + project['id']).json()['status_label'] == label
    assert client.get('/api/projects').json()['projects'][0]['status'] == status


@pytest.mark.parametrize('method', ['POST', 'PATCH', 'DELETE'])
def test_project_mutations_block_cross_origin(client, method):
    project = create(client)
    path = '/api/projects' if method == 'POST' else '/api/projects/' + project['id']
    assert client.request(method, path, json={'confirm': True}, headers={'Origin': 'https://outside.example'}).status_code == 403
    assert client.get('/api/projects/' + project['id']).status_code == 200


def test_custom_header_required_and_get_not_cached(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/projects', json=payload()).status_code == 403
        assert client.get('/api/projects').headers['cache-control'] == 'no-store'
        assert client.get('/api/projects', headers={'Origin': 'null'}).status_code == 403
