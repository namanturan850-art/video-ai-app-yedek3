"""Medya ekranı: her yuvanın cümlesi + Türkçesi (video başına tek istek, kayıtlı),
[GÖRSEL] notunun Türkçesi ve “Kontrol edilmesi gerekenler” listesi."""
import test_fast_media as F
import test_media_director_topics as T
from app.stock.director_media import review_flags
from app.editor.editorial import Editorial


def legacy_translation_fixture(client,pid):
    # These scenarios exercise the old automatic media/translation pipeline.
    # New projects retain the separately tested manual/source-only default.
    editorial=Editorial(client.app.state.editor);state=editorial.get(pid)
    state["preferences"].update(editing_mode="legacy",media_preparation_mode="legacy")
    editorial.save(pid,state)


class Translator:
    def __init__(self, fail=False): self.calls, self.fail = [], fail
    def complete_json(self, purpose, prompt, schema, **kwargs):
        if purpose != 'media_translate': raise AssertionError(purpose)
        self.calls.append(prompt)
        if self.fail: raise RuntimeError('down')
        lines = [l for l in prompt.split('\n\n', 1)[1].splitlines() if l.strip()]
        return {'items': [{'id': int(l.split(':', 1)[0]), 'tr': 'TR ' + l.split(':', 1)[1].strip()} for l in lines]}


def test_each_slot_gets_its_sentence_in_turkish_with_one_saved_request(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch)
    try:
        legacy_translation_fixture(client,pid)
        client.app.state.stock.clip_scorer = F.clip_fake(world, [])
        translator = Translator()
        client.app.state.stock.ai_factory = lambda: translator
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and len(translator.calls) == 1  # one request per video
        slots = [s for s in view['slots'] if s.get('sentence')]
        assert slots and all(s['sentence_tr'] == 'TR ' + s['sentence'] for s in slots)
        noted = [s for s in view['slots'] if s.get('visual_note')]
        assert noted and all(s['visual_note_tr'].startswith('TR ') for s in noted)  # the [GÖRSEL] note in Turkish
        T.complete(client, pid)
        assert len(translator.calls) == 1  # saved: the next run asks nothing
        page = client.get('/static/stock.js').text
        assert 'Kontrol edilmesi gerekenler' in page and 'Kontrol gerekmiyor' in page and 'Türkçesi' in page
    finally:
        client.__exit__(None, None, None)


def test_without_ai_the_translation_stays_empty_and_the_job_finishes(tmp_path, monkeypatch):
    client, pid, world, fake = F.make(tmp_path, monkeypatch)
    try:
        legacy_translation_fixture(client,pid)
        client.app.state.stock.ai_factory = lambda: Translator(fail=True)
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0
        assert all(s.get('sentence_tr', '') == '' for s in view['slots'])
        assert all(isinstance(s.get('review_flags'), list) for s in view['slots'])
        # no CLIP, no Gemini look: stock picks were chosen by tags only → on the check list
        assert any('etiket' in f for s in view['slots'] for f in s['review_flags'])
    finally:
        client.__exit__(None, None, None)


def test_review_flags():
    stock = {'provider': 'pixabay', 'media_type': 'video', 'media_id': '1'}
    base = {'selected_media': stock, 'status': 'complete', 'locked': False}
    assert review_flags({**base, 'ai_review': {'approved': True, 'score': 8}}) == []
    assert 'CLIP puanı düşük (5/10)' in review_flags({**base, 'local_review': {'method': 'words', 'clip': {'score': 5}}})
    assert review_flags({**base, 'local_review': {'method': 'clip', 'clip': {'score': 8, 'setting_margin': -.05}}}) == []
    near = review_flags({**base, 'local_review': {'method': 'clip', 'clip': {'score': 8, 'setting_margin': -.004, 'setting_closest': 'Çin'}}})
    assert near and 'sınıra yakın (Çin' in near[0]
    assert review_flags({**base, 'selected_media': {**stock, 'provider': 'generated'}}) == []
