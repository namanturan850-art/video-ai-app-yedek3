"""Video dönemi: the period is read from what MOST of the text speaks of (a few historical
sentences do not make a video about today's geography ancient), Ayarlar → Video dönemi
(Otomatik / Modern / Tarihsel), looser rules before a graphic when the motion share is
over the target, and Wikimedia answers that only hold filtered files. Offline fakes."""
import httpx
import pytest

import test_fast_media as F
import test_media_director_topics as T
from app.stock import setting
from app.stock.providers import WikimediaStockProvider

ANDES = {'topic': 'Los Andes', 'scenario': 'plenty', 'shots': 3, 'themes': [
    ('andes mountains aerial', ['andes peaks snow', 'mountain range aerial'], 'andes mountains', 'andes mountains aerial range peaks'),
    ('tourists hiking mountain trail', ['hikers andes trail', 'trekking peaks'], 'hikers on a trail', 'tourists hiking trail mountain andes'),
    ('road through the mountains', ['car on mountain road', 'highway andes'], 'road in the mountains', 'car road highway mountain andes'),
    ('village market andes', ['andean market people', 'peru market street'], 'village market', 'village market people andes street'),
    ('llama grazing highlands', ['alpaca andes', 'highland animals'], 'llamas', 'llama alpaca highlands andes'),
    ('lake titicaca', ['andes lake aerial', 'blue lake mountains'], 'a mountain lake', 'lake titicaca andes aerial')],
    'sentences': ['Los Andes recorren siete países de Sudamérica de norte a sur.',
                  'Hoy millones de turistas recorren sus senderos cada año.',
                  'Las carreteras de montaña conectan ciudades a más de tres mil metros.',
                  'Los mercados de los pueblos venden papas, maíz y lana de alpaca.',
                  'La cordillera tiene más de siete mil kilómetros de longitud.',
                  'El lago Titicaca es el lago navegable más alto del mundo.',
                  'Hace siglos el imperio inca construyó caminos entre los picos.']}


def text(aside=True, sentences=60):
    out = [ANDES['sentences'][i % 6] for i in range(sentences)]
    if aside: out[17] = 'Hace siglos los antiguos incas construyeron caminos entre los picos.'  # ONE historical sentence in sixty
    return '# Los Andes\n\n' + '\n\n'.join(' '.join(out[i:i + 4]) for i in range(0, len(out), 4))


def test_a_few_historical_sentences_do_not_make_the_video_ancient():
    sentences = [ANDES['sentences'][i % 6] for i in range(60)]
    sentences[17] = ANDES['sentences'][6]
    sentences[40] = 'Los antiguos pobladores adoraban a los picos como dioses.'
    auto = setting.infer(sentences, 'Los Andes')
    assert auto['era'] == 'contemporary' and auto['mode'] == 'auto'
    assert setting.infer(sentences, 'Los Andes', 'modern')['era'] == 'contemporary'
    assert setting.infer(sentences, 'Los Andes', 'historic')['era'] == 'ancient'  # the owner insists: the old strict reading
    # a truly historical video stays historical (every mode that reads the text)
    babylon = ['Babylon was the greatest city of Mesopotamia.', 'The king ruled the empire from the palace.'] * 10
    assert setting.infer(babylon, 'Babylon')['era'] == 'ancient'
    assert setting.infer(babylon, 'Babylon', 'modern')['era'] == 'contemporary'
    # unsure (no period words at all) → modern
    assert setting.infer(['Das Wetter ist heute schön.', 'Die Stadt liegt am Fluss.'], 'Reise')['era'] == 'contemporary'


def test_modern_mode_never_turns_a_scene_historical_and_has_no_period_rules():
    modern = setting.infer(['Los Andes.'], 'Andes', 'modern')
    assert setting.for_scene(modern, 'En el año 1450 los incas construyeron un camino.') is modern
    assert not [p for p in setting.penalties(modern) if p['kind'] in ('anachronism', 'style')]
    assert setting.tag_conflict(modern, ' tourists car cartoon ') is None


def test_relax_levels_drop_the_period_rules_then_the_place_rules():
    ancient = setting.describe('ancient', None, ['mesopotamia'])
    strict = {p['kind'] for p in setting.penalties(ancient)}
    assert {'anachronism', 'style', 'place'} <= strict
    assert {p['kind'] for p in setting.penalties({**ancient, 'relax': 1})} == {'place'}
    assert setting.penalties({**ancient, 'relax': 2}) == []
    assert setting.tag_conflict(ancient, ' tourists on a trail ')[0] == 'anachronism'
    assert setting.tag_conflict({**ancient, 'relax': 1}, ' tourists on a trail ') is None
    assert setting.tag_conflict({**ancient, 'relax': 1}, ' terracotta army ')[0] == 'place'
    assert setting.tag_conflict({**ancient, 'relax': 2}, ' terracotta army ') is None


def run_project(tmp_path, monkeypatch, mode):
    monkeypatch.setitem(T.TOPICS, 'andes', ANDES)
    client, pid, world, fake = F.make(tmp_path / mode, monkeypatch, text(), key='andes', language='es')
    try:
        client.app.state.settings.save('general', {'era_mode': mode})
        client.app.state.stock.clip_scorer = F.clip_fake(world, [])
        view = T.complete(client, pid)
        assert view['job']['status'] == 'completed', view['job']
        return view
    finally:
        client.__exit__(None, None, None)


def test_andes_text_motion_share_auto_vs_strict_historic(tmp_path, monkeypatch):
    strict = run_project(tmp_path, monkeypatch, 'historic')
    auto = run_project(tmp_path, monkeypatch, 'auto')
    ratio = lambda v: v['media_mix']['motion_ratio_percent']
    print('MOTION RATIO strict-historic', ratio(strict), 'auto', ratio(auto), 'slots', auto['media_mix']['total_slots'])
    assert auto['job']['progress']['setting']['era'] == 'contemporary' and strict['job']['progress']['setting']['era'] == 'ancient'
    assert ratio(auto) <= ratio(strict) and ratio(auto) <= 25


def wikimedia_page(pageid, mime, licence):
    info = {'url': f'https://upload.wikimedia.org/wikipedia/commons/a/ab/{pageid}.ogv', 'descriptionurl': f'https://commons.wikimedia.org/wiki/File:{pageid}',
            'width': 1280, 'height': 720, 'size': 5_000_000, 'mime': mime, 'duration': 30.0, 'thumburl': 'https://upload.wikimedia.org/x.jpg',
            'extmetadata': {'LicenseShortName': {'value': licence}}}
    return {'pageid': pageid, 'title': f'File:Clip {pageid}.ogv', 'index': pageid, 'imageinfo': [info]}


def test_wikimedia_answer_with_only_filtered_files_is_not_invalid_response():
    pages = [wikimedia_page(1, 'video/ogg', 'CC BY-SA 4.0'), wikimedia_page(2, 'video/webm', 'CC BY-NC 4.0'), {'pageid': 3, 'title': 'File:Gone.ogv', 'index': 3}]
    provider = WikimediaStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'query': {'pages': pages}})))
    assert provider.search_videos('andes mountains') == []  # ogv, NC licence, page without a file: nothing usable, but a valid answer
    assert provider.last_diagnostic['filtered'] == 3
    broken = WikimediaStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'query': {'pages': [{'pageid': 1, 'title': 'File:a', 'imageinfo': ['x']}, {'pageid': 2, 'title': 'File:b', 'imageinfo': [7]}]}})))
    from app.stock.models import StockError
    with pytest.raises(StockError) as error:
        broken.search_videos('andes')
    assert error.value.category == 'invalid_response'  # every item unreadable: still reported
    limited = WikimediaStockProvider('', transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'error': {'code': 'ratelimited'}})))
    with pytest.raises(StockError) as error:
        limited.search_videos('andes')
    assert error.value.category == 'rate_limit'
