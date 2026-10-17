"""Real local files, revision APIs and SQLite; no external providers or long render."""
import json
import hashlib
from contextlib import closing

from fastapi.testclient import TestClient

from app.main import create_app
from app.stock.service import fingerprint
from test_rendering import install_ready
from test_subtitles import HEADERS, wav


def stamp(view):
    return {'plan_id': view['stock_plan_id'], 'revision': view['stock_revision']}


def test_archive_assignment_history_lock_split_and_reopen(tmp_path):
    storage = tmp_path / 'workspace'
    with TestClient(create_app(storage), headers=HEADERS) as client:
        seeded = install_ready(client.app)
        pid = seeded['pid']
        base = f'/api/projects/{pid}/editor'
        # Bring the older render fixture up to the stock editor's current state contract.
        with closing(client.app.state.projects._connection()) as connection, connection:
            row = connection.execute('SELECT state_json FROM stock_plans WHERE project_id=?', (pid,)).fetchone()
            stock = json.loads(row[0])
            stock.update(handoff_fingerprint=fingerprint(client.app.state.production.handoff(pid)), bindings={}, warnings=[])
            for slot in stock['slots']:
                media = slot['selected_media']
                media.update(width=320, height=240, sha256=hashlib.sha256((seeded['root']/media['local_path']).read_bytes()).hexdigest())
            connection.execute('UPDATE stock_plans SET state_json=? WHERE project_id=?', (json.dumps(stock), pid))
        view = client.get(base).json()
        target = view['tracks']['visuals'][0]
        # Reuse a generated local PNG through the real, content-validated upload route.
        image = next((seeded['root'] / 'stock').glob('*.png'))
        response = client.post(base + '/archive/upload', content=image.read_bytes(),
                               headers={'Content-Type': 'application/octet-stream', 'X-File-Name': 'test.png'})
        assert response.status_code == 201, response.text
        asset = response.json()['item']
        payload = {**stamp(view), 'provider': asset['provider'], 'media_id': asset['media_id'],
                   'sha256': asset['sha256'], 'start': 0, 'end': 4}
        assert client.put(base + f'/slots/{target["slot_id"]}/media', json=payload).status_code == 409
        response = client.post(base + f'/slots/{target["slot_id"]}/edit',
                               json={**stamp(view), 'action': 'lock', 'locked': False})
        assert response.status_code == 200, response.text
        view = response.json()
        original = next(x for x in view['tracks']['visuals'] if x['slot_id'] == target['slot_id'])
        sound = client.post(base+'/archive/upload', content=wav(.1), headers={'Content-Type':'application/octet-stream','X-File-Name':'test.wav'}).json()['item']
        rejected = client.put(base+f'/slots/{target["slot_id"]}/media', json={**stamp(view),'provider':'local','media_id':sound['media_id'],'sha256':sound['sha256'],'start':0,'end':1})
        assert rejected.status_code == 422 and 'yalnız video veya görsel' in rejected.json()['message']
        response = client.put(base + f'/slots/{target["slot_id"]}/media', json={**payload, **stamp(view)})
        assert response.status_code == 200, response.text
        assigned = response.json()
        stale=client.put(base+f'/slots/{target["slot_id"]}/media',json={**payload,**stamp(view)})
        assert stale.status_code==409
        assert next(x for x in assigned['tracks']['visuals'] if x['slot_id'] == target['slot_id'])['media']['media_id'] == asset['media_id']
        undone = client.post(base + '/timeline/undo', json=stamp(assigned))
        assert undone.status_code == 200, undone.text
        restored = next(x for x in undone.json()['tracks']['visuals'] if x['slot_id'] == target['slot_id'])
        assert restored['media'] == original['media']
        redone = client.post(base + '/timeline/redo', json=stamp(undone.json())).json()
        assert next(x for x in redone['tracks']['visuals'] if x['slot_id'] == target['slot_id'])['media']['media_id'] == asset['media_id']
        clip = next(x for x in redone['tracks']['visuals'] if x['slot_id'] == target['slot_id'])
        count = len(redone['tracks']['visuals'])
        split = client.post(base + f'/slots/{target["slot_id"]}/edit', json={**stamp(redone), 'action': 'split', 'at': (clip['start'] + clip['end']) / 2})
        assert split.status_code == 200, split.text
        assert len(split.json()['tracks']['visuals']) == count + 1
        unsplit = client.post(base + '/timeline/undo', json=stamp(split.json()))
        assert unsplit.status_code == 200, unsplit.text
        assert len(unsplit.json()['tracks']['visuals']) == count
        resplit = client.post(base + '/timeline/redo', json=stamp(unsplit.json()))
        assert resplit.status_code == 200, resplit.text
        assert len(resplit.json()['tracks']['visuals']) == count + 1
        assert resplit.json()['duration'] == view['duration']
        assert resplit.json()['tracks']['subtitles'] == view['tracks']['subtitles']
        final_revision = resplit.json()['stock_revision']
        # Verify the persisted state through a new service/application instance.
    with TestClient(create_app(storage), headers=HEADERS) as reopened:
        persisted = reopened.get(base).json()
        assert persisted['stock_revision'] == final_revision
        assert len(persisted['tracks']['visuals']) == count + 1
        assert reopened.get(f'/api/projects/{pid}/render').status_code == 200


def test_saved_personal_theme_is_not_replaced_by_new_default(tmp_path):
    storage = tmp_path / 'theme'
    with TestClient(create_app(storage), headers=HEADERS) as client:
        assert client.get('/api/settings').json()['general']['appearance_theme'] == 'premiere'
        response = client.put('/api/settings/general', json={'appearance_theme': 'turquoise', 'accent_color': '#24D3C5'}, headers={'X-AI-Video-Studio':'settings'})
        assert response.status_code == 200
    with TestClient(create_app(storage), headers=HEADERS) as reopened:
        general = reopened.get('/api/settings').json()['general']
        assert general['appearance_theme'] == 'turquoise'
        assert general['accent_color'] == '#24D3C5'
