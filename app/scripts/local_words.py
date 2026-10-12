"""Small built-in word list (German and Turkish → English) for the no-AI
local scene plan: stock sites are tagged in English, so the filmable nouns
of a sentence (“Schiffe”, “Sturm”, “Tempel”) become English search words
(“ship”, “storm”, “temple”). Only concrete, filmable things are listed; a
word that is not here is simply not translated (no guessing)."""
import re
import unicodedata

DE = {
    # nature, sea, weather
    'meer': 'sea', 'ozean': 'ocean', 'atlantik': 'atlantic ocean', 'pazifik': 'pacific ocean', 'welle': 'waves', 'küste': 'coast',
    'strand': 'beach', 'insel': 'island', 'sturm': 'storm', 'gewitter': 'thunderstorm', 'blitz': 'lightning', 'regen': 'rain', 'nebel': 'fog',
    'wolke': 'clouds', 'himmel': 'sky', 'sonne': 'sun', 'mond': 'moon', 'stern': 'stars', 'nacht': 'night sky', 'wald': 'forest',
    'regenwald': 'rainforest', 'dschungel': 'jungle', 'berg': 'mountain', 'gebirge': 'mountains', 'vulkan': 'volcano', 'fluss': 'river',
    'see': 'lake', 'wüste': 'desert', 'eis': 'ice', 'schnee': 'snow', 'gletscher': 'glacier', 'feuer': 'fire', 'wasser': 'water',
    'quelle': 'spring water', 'höhle': 'cave', 'tiefsee': 'deep sea', 'meeresboden': 'seabed', 'korallenriff': 'coral reef',
    # animals
    'tier': 'animals', 'fisch': 'fish', 'hai': 'shark', 'wal': 'whale', 'qualle': 'jellyfish', 'vogel': 'bird', 'adler': 'eagle',
    'pferd': 'horse', 'hund': 'dog', 'kamel': 'camel', 'löwe': 'lion', 'schlange': 'snake', 'insekt': 'insects', 'tintenfisch': 'squid',
    # transport, technology
    'schiff': 'ship', 'boot': 'boat', 'flugzeug': 'airplane', 'pilot': 'pilot', 'cockpit': 'cockpit', 'hubschrauber': 'helicopter',
    'zug': 'train', 'auto': 'car', 'rakete': 'rocket', 'satellit': 'satellite', 'teleskop': 'telescope', 'radar': 'radar screen',
    'kompass': 'compass', 'karte': 'map', 'funk': 'radio', 'computer': 'computer', 'roboter': 'robot', 'tauchboot': 'submarine',
    'u-boot': 'submarine', 'leuchtturm': 'lighthouse', 'hafen': 'harbor', 'brücke': 'bridge', 'straße': 'road', 'piste': 'runway',
    # history, places, buildings
    'stadt': 'city', 'dorf': 'village', 'burg': 'castle', 'festung': 'fortress', 'mauer': 'stone wall', 'tor': 'city gate',
    'tempel': 'temple', 'kirche': 'church', 'kathedrale': 'cathedral', 'kloster': 'monastery', 'moschee': 'mosque', 'palast': 'palace',
    'pyramide': 'pyramid', 'ruine': 'ruins', 'grab': 'tomb', 'statue': 'statue', 'säule': 'columns', 'forum': 'ancient forum',
    'kolosseum': 'colosseum', 'aquädukt': 'roman aqueduct', 'arena': 'arena', 'markt': 'market', 'haus': 'house', 'hütte': 'hut',
    'museum': 'museum', 'bibliothek': 'library', 'schrift': 'ancient writing', 'manuskript': 'manuscript', 'buch': 'old book',
    'schriftrolle': 'scroll', 'münze': 'ancient coins', 'schwert': 'sword', 'schild': 'shield', 'helm': 'helmet', 'rüstung': 'armor',
    'krone': 'crown', 'thron': 'throne', 'relief': 'stone relief', 'mosaik': 'mosaic', 'fresko': 'fresco', 'gemälde': 'painting',
    'ausgrabung': 'archaeological excavation', 'archäologe': 'archaeologist', 'reich': 'empire', 'weltreich': 'empire',
    # people, roles, events
    'könig': 'king', 'königin': 'queen', 'kaiser': 'emperor', 'pharao': 'pharaoh', 'soldat': 'soldiers', 'legion': 'roman legion',
    'armee': 'army', 'heer': 'army', 'krieg': 'war', 'schlacht': 'battle', 'belagerung': 'siege', 'priester': 'priest',
    'prophet': 'prophet', 'mönch': 'monk', 'bauer': 'farmer', 'händler': 'merchant', 'sklave': 'slaves', 'gefangene': 'prisoners',
    'flüchtling': 'refugees', 'volk': 'people crowd', 'menge': 'crowd', 'familie': 'family', 'kind': 'children', 'forscher': 'scientist',
    'wissenschaftler': 'scientist', 'arzt': 'doctor', 'stamm': 'tribe', 'jäger': 'hunter', 'fischer': 'fisherman', 'seemann': 'sailor',
    'zuschauer': 'spectators', 'gebet': 'prayer', 'opfer': 'sacrifice ritual', 'fest': 'festival', 'hochzeit': 'wedding',
    # science, space
    'galaxie': 'galaxy', 'planet': 'planet', 'erde': 'earth from space', 'weltall': 'outer space', 'labor': 'laboratory',
    'licht': 'light rays', 'schatten': 'shadow', 'feuerwerk': 'fireworks', 'explosion': 'explosion', 'krankheit': 'disease',
    # objects
    'brief': 'old letter', 'kerze': 'candle', 'fackel': 'torch', 'lampe': 'lamp', 'uhr': 'clock', 'kiste': 'wooden box', 'käfig': 'cage',
    'gold': 'gold', 'silber': 'silver', 'stein': 'stones', 'holz': 'wood', 'brot': 'bread', 'wein': 'wine', 'öl': 'oil', 'netz': 'fishing net',
}
TR = {
    'deniz': 'sea', 'okyanus': 'ocean', 'dalga': 'waves', 'sahil': 'coast', 'ada': 'island', 'fırtına': 'storm', 'yağmur': 'rain',
    'gökyüzü': 'sky', 'orman': 'forest', 'dağ': 'mountain', 'nehir': 'river', 'çöl': 'desert', 'ateş': 'fire', 'su': 'water',
    'gemi': 'ship', 'tekne': 'boat', 'uçak': 'airplane', 'pusula': 'compass', 'harita': 'map', 'şehir': 'city', 'köy': 'village',
    'kale': 'castle', 'sur': 'city walls', 'tapınak': 'temple', 'kilise': 'church', 'cami': 'mosque', 'saray': 'palace',
    'piramit': 'pyramid', 'harabe': 'ruins', 'kalıntı': 'ruins', 'mezar': 'tomb', 'heykel': 'statue', 'sütun': 'columns',
    'müze': 'museum', 'kitap': 'old book', 'para': 'coins', 'sikke': 'ancient coins', 'kılıç': 'sword', 'kalkan': 'shield',
    'taç': 'crown', 'kabartma': 'stone relief', 'mozaik': 'mosaic', 'kral': 'king', 'kraliçe': 'queen', 'imparator': 'emperor',
    'firavun': 'pharaoh', 'asker': 'soldiers', 'ordu': 'army', 'savaş': 'war', 'kuşatma': 'siege', 'rahip': 'priest',
    'peygamber': 'prophet', 'kabile': 'tribe', 'çocuk': 'children', 'aile': 'family', 'kalabalık': 'crowd', 'kuş': 'bird',
    'kafes': 'cage', 'kutu': 'wooden box', 'mum': 'candle', 'meşale': 'torch', 'galaksi': 'galaxy', 'gezegen': 'planet', 'yıldız': 'stars',
}
ENDINGS = {'de': ('en', 'n', 'e', 'er', 's', 'es'), 'tr': ('lar', 'ler', 'ları', 'leri', 'ı', 'i', 'u', 'ü', 'da', 'de', 'ta', 'te', 'dan', 'den')}


def fold(word):
    return unicodedata.normalize('NFC', word.casefold().strip("’'-.,;:!?"))


def english(word, language='de'):
    """English stock words for one narration word, or ''."""
    table = TR if language == 'tr' else DE
    low = fold(word)
    if low in table: return table[low]
    for ending in sorted(ENDINGS.get(language, ()), key=len, reverse=True):
        if low.endswith(ending) and len(low) - len(ending) >= 3 and low[:-len(ending)] in table:
            return table[low[:-len(ending)]]
    if language == 'de':  # Umlaut plurals: Stürme → sturm, Schiffe → schiff
        plain = low.replace('ü', 'u').replace('ä', 'a').replace('ö', 'o')
        for key, value in table.items():
            if key.replace('ü', 'u').replace('ä', 'a').replace('ö', 'o') in (plain, plain[:-1], plain[:-2]) and len(key) >= 4:
                return value
    return ''


def english_words(text, language='de', limit=3):
    """Filmable English search words found in the text, in order of appearance."""
    out = []
    for word in re.findall(r"[^\W\d_][\w’'-]*", text):
        value = english(word, language)
        if value and value not in out: out.append(value)
        if len(out) >= limit: break
    return out
