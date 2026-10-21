"""Diagnostics 2026-10-21: a Spanish video planned without AI ("yerel plan") searched the same three generic
queries for 37 slots ("documentary landscape", "cinematic landscape", "clouds sky timelapse"), so 17 slots ran out
of clips. Two causes: the Spanish word list had ~40 words, and a scene with exactly ONE filmable word lost it
(a query needs 2 words) and fell back to the generic ones."""
from app.scripts.local_plan import plan_scenes
from app.scripts.local_words import english, english_words
from app.scripts.query_clean import GENERIC

TOPIC = 'Por qué el relámpago del Catatumbo'


def scene(text, topic=TOPIC, language='es'):
    return plan_scenes([{'unit_id': 'U1', 'text': text}], topic, language)[0]


def queries(block):
    return [block['stock_query'], *block['alternative_stock_queries']]


def test_a_scene_with_one_filmable_word_keeps_it_instead_of_going_generic():
    block = scene('Y cuando llega al fondo de la V, se encuentra con dos murallas de montañas.', topic='Maracaibo')
    assert 'mountains' in block['stock_query'] and block['stock_query'] not in GENERIC
    assert any(q.startswith('mountains ') for q in queries(block))


def test_storm_and_mountain_range_and_oil_sentences_get_their_own_queries():
    storm = scene('Justo ahí, en el rincón donde las paredes se cierran, nace la tormenta.', topic='Maracaibo')
    assert 'storm' in storm['stock_query']
    range_ = scene('La V que se hundía entre dos cordilleras atrapó sedimentos durante millones de años, y de ahí salió el petróleo.', topic='Maracaibo')
    joined = ' | '.join(queries(range_))
    assert 'mountain range' in joined and 'oil' in joined


def test_different_sentences_no_longer_share_one_search():
    sentences = ['El aire húmedo atraviesa el golfo, cruza el lago y avanza hacia el sur.',
                 'Hasta la leyenda del pirata Drake nace de aquí.',
                 'La V que se hundía entre dos cordilleras atrapó sedimentos.',
                 'Justo ahí nace la tormenta.']
    mains = {scene(t, topic='Maracaibo')['stock_query'] for t in sentences}
    assert len(mains) == len(sentences) and not mains & set(GENERIC)


def test_a_sentence_without_any_filmable_word_still_gets_valid_queries():
    block = scene('¿Recuerdas el dato que te pedí guardar?', topic='Maracaibo')
    assert all(q.isascii() and len(q.split()) >= 2 for q in queries(block))


def test_every_query_is_english_and_has_two_words():
    for text in ('Los relámpagos iluminan el lago cada noche.', 'Un río cruza la selva hasta el golfo.', 'El petróleo de la cuenca.'):
        for q in queries(scene(text)):
            assert q.isascii() and len(q.split()) >= 2, q


def test_new_spanish_words_and_their_plurals_are_understood():
    assert english('relámpagos', 'es') == 'lightning storm' and english('cordilleras', 'es') == 'mountain range'
    assert english('petróleo', 'es') == 'oil' and english('tormenta', 'es') == 'storm clouds'
    assert english_words('El lago y la tormenta sobre las montañas', 'es', 3) == ['lake', 'storm clouds', 'mountains']


def test_spanish_water_wells_do_not_invent_oil_and_oil_context_is_preserved():
    assert english('pozo', 'es') == 'well'
    assert english('pozos', 'es') == 'well'
    text = 'Cenotes, esos pozos de agua cristalina donde la gente nada.'
    assert english_words(text, 'es', 6) == ['well', 'water']
    assert all('oil' not in q.split() for q in queries(scene(text, topic='Yucatán')))
    assert english_words('pozo de petróleo', 'es', 3) == ['well', 'oil']


def test_ambiguous_or_figurative_words_are_not_translated():
    for word in ('cabo', 'pico', 'carta', 'gente', 'muralla'):
        assert english(word, 'es') == '', word


def test_german_and_turkish_planning_is_unchanged_for_normal_sentences():
    block = scene('Die Assyrer zogen von Ninive nach Jerusalem.', topic='Das alte Jerusalem', language='de')
    assert all(q.isascii() and len(q.split()) >= 2 for q in queries(block))
