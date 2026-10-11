"""AI33 credit-loss protection: lost create answers, history recovery, duplicate
guard, "AI33’ten kurtar" and manual upload. Synthetic responses only; no paid
or live AI33 call is ever made.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.narration.provider import OpenSpeakerProvider, text_matches
from test_scripts import studio
from test_narration import narration_studio, base, KEY
from test_narration_foundation import wav_data
from test_ai33_tts_verified import verified_studio, start_verified, VOICE, COMPLETED, AUDIO


def stamp(delta=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta)).isoformat().replace('+00:00', 'Z')


def task(task_id, text, created_at, status='done', voice=None):
    return {**COMPLETED, 'id': task_id, 'created_at': created_at, 'status': status, 'text': text, 'text_length': len(text),
            'text_truncated': False, 'metadata': {**COMPLETED['metadata'], 'voice_id': voice or VOICE['voice_id']}}


@pytest.fixture
def recovery_studio(verified_studio):
    st, external = verified_studio
    service = st[0].app.state.narration
    service.verify_interval = .01; service.verify_seconds = .3
    original = external.serve
    external.timeout_posts = False; external.history_after = 0; external.history_calls = 0
    def serve(request):
        if request.url.host == 'api.ai33.pro' and request.method == 'POST' and external.timeout_posts:
            external.calls.append(request)
            raise httpx.ReadTimeout('AI33 answered too late', request=request)  # sent, answer lost
        if request.url.host == 'api.ai33.pro' and request.url.path == '/v1/tasks':
            external.calls.append(request); external.history_calls += 1
            visible = external.history if external.history_calls > external.history_after else []
            return httpx.Response(200, json={'success': True, 'data': visible, 'page': 1, 'limit': 20, 'total': str(len(visible))})
        # Single-task polls answer with the matching history record.
        if request.url.host == 'api.ai33.pro' and request.url.path.startswith('/v1/task/'):
            wanted = request.url.path.rsplit('/', 1)[-1]
            record = next((t for t in external.history if t['id'] == wanted), None)
            if record: external.calls.append(request); return httpx.Response(200, json=record)
        return original(request)
    external.serve = serve; external.connect(st[0])
    return st, external, service


def wait(st, response):
    assert response.status_code == 202, response.text
    st[0].app.state.narration.futures[response.json()['job_id']].result(timeout=15)
    return st[0].get(base(st)).json()


def test_lost_create_answer_is_verified_from_history_and_completes_without_second_charge(recovery_studio):
    st, external, _ = recovery_studio
    external.timeout_posts = True; external.history_after = 2  # AI33 history lags behind
    external.history = [task('ai33-late-task', st[4]['text'], stamp(3))]
    state = wait(st, start_verified(st))
    meta = state['versions'][0]['metadata']
    assert state['job']['status'] == 'completed' and meta['task_id'] == 'ai33-late-task' and meta['recovered_from_history']
    assert meta['audio']['duration'] == 1 and len(external.posts) == 1
    assert state['active']['id'] == state['versions'][0]['id']


def test_lost_answer_without_history_task_says_credit_probably_not_used(recovery_studio):
    st, external, _ = recovery_studio
    external.timeout_posts = True
    state = wait(st, start_verified(st))
    assert state['job']['status'] == 'error' and state['job']['progress']['category'] == 'task_not_found'
    assert 'kredi harcanmadı' in state['job']['error_message'] and len(external.posts) == 1


def test_connection_failure_before_sending_never_verifies_or_charges(recovery_studio):
    st, external, service = recovery_studio
    def refuse(request): raise httpx.ConnectError('no route', request=request)
    service.factory = lambda settings: OpenSpeakerProvider(KEY, secrets=settings.secret_values(), transport=httpx.MockTransport(
        lambda r: refuse(r) if r.method == 'POST' else external.serve(r)))
    state = wait(st, start_verified(st))
    assert state['job']['status'] == 'error' and state['job']['progress']['category'] == 'connection_error'


def test_recent_identical_unlinked_task_is_reused_instead_of_paying_again(recovery_studio):
    st, external, _ = recovery_studio
    external.history = [task('ai33-done-5min', st[4]['text'], stamp(-300))]
    state = wait(st, start_verified(st))
    meta = state['versions'][0]['metadata']
    assert state['job']['status'] == 'completed' and meta['task_id'] == 'ai33-done-5min' and meta['reused_existing_task']
    assert len(external.posts) == 0


@pytest.mark.parametrize('history', ['old', 'other_text', 'other_voice', 'failed'])
def test_only_recent_exact_text_and_voice_tasks_are_reused(recovery_studio, history):
    st, external, _ = recovery_studio
    text = st[4]['text']
    external.history = [{'old': task('t-old', text, stamp(-20 * 60)), 'other_text': task('t-text', text + ' Extra.', stamp(-60)),
                         'other_voice': task('t-voice', text, stamp(-60), voice='elevenlabs_other'),
                         'failed': {**task('t-fail', text, stamp(-60)), 'error_message': 'failed'}}[history]]
    state = wait(st, start_verified(st))
    assert state['job']['status'] == 'completed' and len(external.posts) == 1
    assert not state['versions'][0]['metadata'].get('reused_existing_task')


def test_regenerate_within_15_minutes_asks_before_spending_again(recovery_studio):
    st, external, _ = recovery_studio
    first = wait(st, start_verified(st)); first_task = first['versions'][0]['metadata']['task_id']
    external.history = [task(first_task, st[4]['text'], stamp(-60))]  # already linked to Sürüm 1
    second = wait(st, start_verified(st, regenerate_confirmed=True))
    assert second['job']['status'] == 'error' and second['job']['progress']['category'] == 'recent_duplicate'
    assert len(external.posts) == 1 and 'Kredi harcanmadı' in second['job']['error_message']
    forced = wait(st, start_verified(st, regenerate_confirmed=True, force_new_task=True))
    assert forced['job']['status'] == 'completed' and len(external.posts) == 2


def test_owner_case_two_failed_versions_are_recovered_to_their_own_tasks(recovery_studio):
    """11:19:07 and 11:20:34: two same-text versions errored without task ids."""
    st, external, service = recovery_studio
    external.timeout_posts = True
    v1 = wait(st, start_verified(st))['versions'][0]
    v2 = wait(st, start_verified(st, regenerate_confirmed=True, force_new_task=True))['versions'][0]
    assert v1['metadata']['status'] == v2['metadata']['status'] == 'error' and not v1['metadata']['task_id']
    with closing(service.projects._connection()) as c, c:
        for vid, created in ((v1['id'], '2026-10-11T08:19:07+00:00'), (v2['id'], '2026-10-11T08:20:34+00:00')):
            row = c.execute('SELECT metadata_json FROM narration_versions WHERE id=?', (vid,)).fetchone()
            meta = json.loads(row[0]); meta.pop('creation_attempted_at', None)  # pre-fix versions lack it
            c.execute('UPDATE narration_versions SET metadata_json=?,created_at=? WHERE id=?', (json.dumps(meta), created, vid))
    text = st[4]['text']
    external.history = [task('ai33-v2-task', text, '2026-10-11T08:20:41Z'), task('ai33-v1-task', text, '2026-10-11T08:19:15Z')]
    posts = len(external.posts)
    for vid, expected in ((v1['id'], 'ai33-v1-task'), (v2['id'], 'ai33-v2-task')):
        state = wait(st, st[0].post(base(st) + f'/versions/{vid}/recover', json={}))
        meta = next(v for v in state['versions'] if v['id'] == vid)['metadata']
        assert meta['status'] == 'completed' and meta['task_id'] == expected and meta['audio']['duration'] == 1
    assert len(external.posts) == posts  # recovery never pays again


def test_recover_requires_a_sent_failed_version(recovery_studio):
    st, external, _ = recovery_studio
    done = wait(st, start_verified(st))['versions'][0]
    r = st[0].post(base(st) + f'/versions/{done["id"]}/recover', json={})
    assert r.status_code == 409


def test_manual_upload_completes_version_and_rejects_bad_files(recovery_studio):
    st, external, _ = recovery_studio
    external.timeout_posts = True
    failed = wait(st, start_verified(st))['versions'][0]
    headers = {'X-AI-Video-Studio': 'projects', 'X-Audio-Format': 'wav'}
    bad = st[0].post(base(st) + f'/versions/{failed["id"]}/upload', content=b'not audio at all', headers=headers)
    assert bad.status_code == 422
    good = st[0].post(base(st) + f'/versions/{failed["id"]}/upload', content=wav_data(), headers=headers)
    assert good.status_code == 200, good.text
    meta = next(v for v in good.json()['versions'] if v['id'] == failed['id'])['metadata']
    assert meta['status'] == 'completed' and meta['audio_source'] == 'manual_upload' and meta['audio']['duration'] == 1
    assert good.json()['active']['id'] == failed['id']
    assert st[0].get(base(st) + f'/versions/{failed["id"]}/audio').content == wav_data()
    again = st[0].post(base(st) + f'/versions/{failed["id"]}/upload', content=wav_data(), headers=headers)
    assert again.status_code == 409


def test_text_match_is_exact_or_verified_truncated_prefix_only():
    text = 'Ein langer Text über das Bermuda-Dreieck. ' * 10
    assert text_matches({'text': text}, text)
    assert text_matches({'text': text[:100], 'text_truncated': True, 'text_length': len(text)}, text)
    assert not text_matches({'text': text[:100], 'text_truncated': True, 'text_length': len(text) + 1}, text)
    assert not text_matches({'text': text[:100], 'text_truncated': False, 'text_length': len(text)}, text)
    assert not text_matches({'text': text[:20], 'text_truncated': True, 'text_length': len(text)}, text)
    assert not text_matches({'text': None}, text)


def test_history_never_leaks_text_or_urls(recovery_studio, caplog):
    st, external, service = recovery_studio
    external.history = [task('ai33-x', 'PRIVATE_OTHER_SCRIPT', stamp(-30))]
    provider = service.factory(st[0].app.state.settings)
    items = provider.task_history()
    assert items[0]['task_id'] == 'ai33-x' and 'audio_url' not in json.dumps(items, default=str)
    assert 'PRIVATE_OTHER_SCRIPT' not in caplog.text and AUDIO not in caplog.text


def test_recover_tolerates_unverified_ai33_time_zone(recovery_studio):
    st, external, service = recovery_studio
    external.timeout_posts = True
    failed = wait(st, start_verified(st))['versions'][0]
    # AI33 history clock 7 hours off (e.g. local time without zone).
    external.history = [task('ai33-other-zone', st[4]['text'], stamp(7 * 3600))]
    state = wait(st, st[0].post(base(st) + f'/versions/{failed["id"]}/recover', json={}))
    meta = next(v for v in state['versions'] if v['id'] == failed['id'])['metadata']
    assert meta['status'] == 'completed' and meta['task_id'] == 'ai33-other-zone' and meta['recovery_time_check'] == 'skipped'


def test_automatic_verification_never_guesses_outside_the_time_window(recovery_studio):
    st, external, _ = recovery_studio
    external.timeout_posts = True
    external.history = [task('ai33-other-zone', st[4]['text'], stamp(7 * 3600))]
    state = wait(st, start_verified(st))
    assert state['job']['status'] == 'error' and state['job']['progress']['category'] == 'task_not_found'
