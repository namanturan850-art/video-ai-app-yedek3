"""Kanal anları: giriş / kapanış (abone ol + zil) / bitiş ekranı; dil kalıpları."""
import pytest

from app.channels import DEFAULT_STYLE
from app.moments import phrases
from app.moments.plan import apply_moments, closing_present
from app.moments.spec import endscreen_spec, moment_spec
from app.motion import templates
from app.scripts.paste import clean


@pytest.mark.parametrize('language,sentence,kind', [
    ('de', 'Herzlich willkommen auf meinem Kanal.', 'intro'), ('de', 'Vergesst nicht, den Kanal zu abonnieren!', 'subscribe'), ('de', 'Bis zum nächsten Mal!', 'farewell'),
    ('es', 'Bienvenidos a este vídeo.', 'intro'), ('es', 'Suscríbete y activa la campanita.', 'subscribe'), ('es', 'Hasta la próxima.', 'farewell'),
    ('fr', 'Bienvenue sur la chaîne !', 'intro'), ('fr', "N'oubliez pas de vous abonner.", 'subscribe'), ('fr', 'À bientôt !', 'farewell'),
    ('en', 'Welcome back to the channel.', 'intro'), ('en', 'Please subscribe and hit the bell.', 'subscribe'), ('en', 'See you next time.', 'farewell'),
    ('tr', 'Kanalıma hoş geldiniz.', 'intro'), ('tr', 'Abone olmayı unutmayın.', 'subscribe'), ('tr', 'Bir sonraki videoda görüşmek üzere.', 'farewell')])
def test_phrases_are_recognised_in_the_videos_language(language, sentence, kind):
    assert phrases.classify(sentence, language) == kind


def test_phrases_do_not_fire_on_ordinary_sentences_or_other_languages():
    assert phrases.classify('Rom war die größte Stadt der Antike.', 'de') is None
    assert phrases.classify('Die Zilyonen waren zahlreich.', 'tr') is None
    assert phrases.classify('Willkommen zu diesem Video.', 'fr') is None  # only the video's own language counts
    assert phrases.classify('Willkommen zu diesem Video.', 'xx') is None


def test_a_new_language_needs_only_one_entry(monkeypatch):
    monkeypatch.setitem(phrases.LANGUAGE_DATA, 'it', {'intro': ['benvenuti'], 'subscribe': ['iscrivetevi'], 'farewell': ['alla prossima'],
                                                       'labels': {'subscribe': 'Iscriviti', 'subscribed': 'Iscritto', 'thanks': 'Grazie per la visione!'}})
    phrases._COMPILED.clear()
    assert phrases.classify('Benvenuti sul canale.', 'it') == 'intro' and phrases.classify('Alla prossima!', 'it') == 'farewell'
    assert phrases.labels('it')['subscribe'] == 'Iscriviti'
    assert phrases.labels('zz') == phrases.LANGUAGE_DATA['en']['labels']  # unknown language: English texts
    phrases._COMPILED.clear()


def test_markers_never_reach_narration_or_subtitles():
    result = clean('[GİRİŞ] Willkommen zu diesem Video. Es geht um Rom.\n\nRom fiel. [KAPANIŞ] Abonniert den Kanal. Bis bald!')
    assert '[' not in result['text'] and 'GİRİŞ' not in result['text'] and 'KAPANIŞ' not in result['text']
    assert [(m['type'], m['value']) for m in result['markers']] == [('intro', '*'), ('outro', '*')] and not result['warnings']
    assert clean('[GİRİŞ: Der Fall Roms] Hallo.')['markers'][0]['value'] == 'Der Fall Roms'


def blocks(*texts):
    return [{'narration': text} for text in texts]


def hints(items):
    return [(h['type'], h['value']) for b in items for h in b.get('owner_hints', [])]


def test_automatic_intro_and_closing_without_markers():
    items = apply_moments(blocks('Willkommen zu diesem Video. Heute geht es um Rom.', 'Rom war groß. ' * 12, 'Abonniert den Kanal! Bis zum nächsten Mal.'), 'de')
    assert hints(items) == [('intro', '*'), ('outro', 'subscribe'), ('outro', 'farewell')] and closing_present(items)


def test_subscribe_call_in_the_middle_gets_no_animation():
    middle = apply_moments(blocks('Hallo zusammen. Es geht um Rom.', 'Abonniert den Kanal. ' + 'Rom war groß. ' * 30, 'Rom fiel. Das war es.'), 'de')
    assert ('outro', 'subscribe') not in hints(middle) and not closing_present(middle)
    explicit = blocks('Hallo zusammen. Es geht um Rom.', 'Rom war groß. ' * 30, 'Rom fiel. Das war es.')
    explicit[1]['owner_hints'] = [{'type': 'outro', 'value': '*', 'sentence': 'Rom war groß.'}]  # [KAPANIŞ] in the middle
    assert not closing_present(apply_moments(explicit, 'de'))


def test_explicit_marker_is_not_doubled_by_automatic_recognition():
    items = blocks('Willkommen zu diesem Video.', 'Rom war groß. ' * 12, 'Abonniert den Kanal.')
    items[2]['owner_hints'] = [{'type': 'outro', 'value': '*', 'sentence': 'Abonniert den Kanal.'}]
    assert hints(apply_moments(items, 'de')).count(('outro', '*')) == 1 and ('outro', 'subscribe') not in hints(items)


def texts(scene):
    return [e['props'].get('text', '') for e in scene['elements'] if e['type'] == 'text']


@pytest.mark.parametrize('language,subscribe,subscribed', [('de', 'ABONNIEREN', 'ABONNIERT'), ('es', 'SUSCRIBIRSE', 'SUSCRITO'), ('fr', "S'ABONNER", 'ABONNÉ'),
                                                            ('en', 'SUBSCRIBE', 'SUBSCRIBED'), ('tr', 'ABONE OL', 'ABONE OLUNDU'), ('xx', 'SUBSCRIBE', 'SUBSCRIBED')])
def test_closing_texts_are_in_the_videos_language(language, subscribe, subscribed):
    spec = moment_spec('outro', '*', 'Der Fall Roms', 'Geschichte Pur')
    scene = templates.build(templates.validate(spec, ''), DEFAULT_STYLE, 7.0, 4.0, language)
    assert subscribe in texts(scene) and subscribed in texts(scene)


def test_intro_has_title_and_channel_and_a_short_animation():
    spec = templates.validate(moment_spec('intro', '*', 'Der Fall Roms', 'Geschichte Pur'), '')
    scene = templates.build(spec, DEFAULT_STYLE, 4.5, 2.7, 'de')
    assert 'Der Fall Roms' in ' '.join(texts(scene)) and any('GESCHICHTE PUR' == t for t in texts(scene))
    assert moment_spec('intro', 'Eigener Titel', 'Projekt', 'Kanal')['data']['title'] == 'Eigener Titel'


def test_endscreen_leaves_the_middle_empty():
    from PIL import Image
    from app.motion.raster import Pictures, draw_frame
    scene = templates.build(templates.validate(endscreen_spec('Kanal'), ''), DEFAULT_STYLE, 20.0, 12.0, 'de')
    assert texts(scene) == [] and scene['duration'] == 20.0
    frame = draw_frame(scene, 8.0, Image.new('RGB', (1920, 1080), scene['background']), {}, Pictures())
    centre = {frame.getpixel((x, y)) for x in range(300, 1700, 100) for y in range(200, 900, 100)}
    assert len(centre) == 1  # one flat colour: room for YouTube's end-screen elements
