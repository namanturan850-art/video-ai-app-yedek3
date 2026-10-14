"""Uçtan uca: Fransızca metin + kabartma harita işaretleri, seslendirme yok,
Gemini plan isteği 503 → yerel plan; Medyayı Tamamla çökmemeli."""
import test_fast_media as F
import test_media_director_topics as T

TEXT = """# La France cachée

La France cache quelque chose dont personne ne parle. [BÖLGE: Bretagne]
En Bretagne, certaines roches sont parmi les plus anciennes du pays. Elles ont environ deux milliards d'années. [SAYI: 2 milliards d'années]
Mais le vrai secret se trouve plus au sud. [OK: Lyon > Marseille]
Il y a environ six millions d'années, la Méditerranée s'est presque entièrement asséchée. [ÇİZELGE: -6 millions d'années, aujourd'hui]
Le Rhône a alors creusé un canyon gigantesque, profond de plusieurs centaines de mètres. [BÖLGE: Vallée du Rhône]
Aujourd'hui, ce canyon est caché sous nos pieds, rempli de sédiments.
Et ce n'est pas tout. À sept mille kilomètres de Paris, la France possède une forêt immense. [YAKINLAŞ: Guyane]
En Guyane, la forêt couvre plus de quatre-vingt-dix pour cent du territoire. [ORAN: 90% forêt]
Une partie de la France que presque personne ne connaît.
"""


def test_french_relief_markers_end_to_end(tmp_path, monkeypatch):
    import app.providers.gemini as gemini
    from app.providers.base import ScriptProviderError
    def busy(self, prompt): raise ScriptProviderError('Gemini meşgul.', 503, category='upstream_error', upstream_status=503)
    monkeypatch.setattr(gemini.GeminiScriptProvider, 'generate_script', busy)  # the plan request gets 503 → local plan
    client, pid, world, fake = F.make(tmp_path, monkeypatch, TEXT, language='fr', fast=False, plan='gemini')
    try:
        plan = client.get(f'/api/projects/{pid}/production').json()['plan']
        hints = {h['type'] for b in plan['blocks'] for h in b.get('owner_hints') or []}
        assert {'region', 'number', 'arrow', 'timeline', 'zoom', 'ratio'} <= hints  # the local plan read every marker
        queries = ' | '.join(q for b in plan['blocks'] for q in [b['stock_query'], *b['alternative_stock_queries']])
        for wanted in ('Rhone valley', 'French Guiana', 'canyon', 'rainforest'):
            assert wanted in queries, queries  # from the sentence's subject, not generic words
        assert not any(b['stock_query'] in ('documentary landscape', 'cinematic landscape', 'aerial city view') for b in plan['blocks'])
        client.app.state.stock.clip_scorer = F.clip_fake(world, [])
        view = T.complete(client, pid)  # no narration recorded: media selection still works
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0, view['job']
        made = [((s['selected_media'] or {}).get('source_metadata') or {}).get('motion', {}) for s in view['slots']]
        relief = [m for m in made if m.get('template') == 'relief']
        assert {m['data']['mode'] for m in relief} == {'region', 'arrow', 'zoom'} and len(relief) == 4
        templates = {m.get('template') for m in made}
        assert {'stat', 'timeline', 'ratio'} <= templates, templates  # [SAYI] / [ÇİZELGE] / [ORAN] infographics
        for slot in view['slots'][:4]:  # the media screen preview works without narration
            r = client.get(f'/api/projects/{pid}/production/stock/slots/{slot["slot_id"]}/preview')
            assert r.status_code == 200 and len(r.content) > 50  # (synthetic stock files are tiny; motion clips are real MP4s)
    finally:
        client.__exit__(None, None, None)


def test_missing_map_component_never_crashes_the_job(tmp_path, monkeypatch):
    import app.motion.relief as relief
    def broken(*a, **k): raise ModuleNotFoundError("No module named 'numpy'")
    monkeypatch.setattr(relief, 'find', broken); monkeypatch.setattr(relief, 'place', broken)
    client, pid, world, fake = F.make(tmp_path, monkeypatch, TEXT, language='fr')
    try:
        client.app.state.stock.clip_scorer = F.clip_fake(world, [])
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed' and view['media_summary']['missing'] == 0, view['job']
        warnings = ' '.join(view['job']['progress'].get('marker_warnings', []))
        assert 'Kabartma harita çizilemedi' in warnings, view['job']['progress']
    finally:
        client.__exit__(None, None, None)
