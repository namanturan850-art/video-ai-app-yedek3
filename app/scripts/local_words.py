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
# French: filmable nouns/adjectives of documentary narration (elisions “d'années” are split before lookup).
FR = {'roche': 'rock formation', 'roches': 'rock formation', 'rocher': 'rocks', 'pierre': 'stone', 'falaise': 'cliffs', 'falaises': 'cliffs',
      'côte': 'coast', 'côtes': 'coast', 'littoral': 'coastline', 'mer': 'sea', 'océan': 'ocean', 'plage': 'beach', 'île': 'island', 'îles': 'island',
      'port': 'harbor', 'phare': 'lighthouse', 'vague': 'waves', 'vagues': 'waves', 'canyon': 'canyon', 'gorge': 'gorge', 'gorges': 'gorge',
      'vallée': 'valley', 'fleuve': 'river', 'rivière': 'river', 'lac': 'lake', 'montagne': 'mountains', 'montagnes': 'mountains', 'colline': 'hills',
      'collines': 'hills', 'plaine': 'plain', 'désert': 'desert', 'forêt': 'rainforest', 'forêts': 'forest', 'jungle': 'jungle', 'arbre': 'trees',
      'arbres': 'trees', 'champ': 'field', 'champs': 'fields', 'village': 'village', 'ville': 'city', 'villes': 'city', 'château': 'castle',
      'église': 'church', 'cathédrale': 'cathedral', 'ruines': 'ruins', 'pont': 'bridge', 'route': 'road', 'carte': 'map', 'ciel': 'sky',
      'nuage': 'clouds', 'nuages': 'clouds', 'soleil': 'sun', 'étoiles': 'stars', 'lune': 'moon', 'neige': 'snow', 'glace': 'ice', 'glacier': 'glacier',
      'volcan': 'volcano', 'sédiments': 'sediment layers', 'sédiment': 'sediment layers', 'sel': 'salt flat', 'sable': 'sand', 'boue': 'mud',
      'eau': 'water', 'pluie': 'rain', 'tempête': 'storm', 'sécheresse': 'drought', 'fossile': 'fossil', 'fossiles': 'fossil', 'grotte': 'cave',
      'grottes': 'cave', 'sous-sol': 'underground', 'sol': 'ground', 'terre': 'earth', 'paysage': 'landscape', 'territoire': 'aerial landscape',
      'navire': 'ship', 'bateau': 'boat', 'pêcheur': 'fisherman', 'ferme': 'farm', 'vigne': 'vineyard', 'vignes': 'vineyard', 'vin': 'wine',
      'soldat': 'soldiers', 'soldats': 'soldiers', 'roi': 'king', 'reine': 'queen', 'armée': 'army', 'guerre': 'war', 'bataille': 'battle',
      'animaux': 'wild animals', 'oiseaux': 'birds', 'poisson': 'fish', 'singe': 'monkey', 'jaguar': 'jaguar', 'fusée': 'rocket launch',
      'ancien': 'ancient', 'anciennes': 'ancient', 'anciens': 'ancient', 'ancienne': 'ancient', 'immense': 'vast', 'gigantesque': 'giant',
      'profond': 'deep', 'profonde': 'deep', 'sec': 'dry', 'sèche': 'dry', 'asséchée': 'dried up', 'tropical': 'tropical', 'tropicale': 'tropical'}
ES = {'roca': 'rocks', 'costa': 'coast', 'mar': 'sea', 'océano': 'ocean', 'playa': 'beach', 'isla': 'island', 'cañón': 'canyon', 'valle': 'valley',
      'río': 'river', 'lago': 'lake', 'montaña': 'mountains', 'montañas': 'mountains', 'desierto': 'desert', 'bosque': 'forest', 'selva': 'rainforest',
      'ciudad': 'city', 'castillo': 'castle', 'iglesia': 'church', 'ruinas': 'ruins', 'puente': 'bridge', 'mapa': 'map', 'cielo': 'sky',
      'nubes': 'clouds', 'volcán': 'volcano', 'arena': 'sand', 'agua': 'water', 'tormenta': 'storm', 'cueva': 'cave', 'barco': 'ship',
      'soldados': 'soldiers', 'rey': 'king', 'ejército': 'army', 'guerra': 'war', 'antiguo': 'ancient', 'antigua': 'ancient'}
# The Spanish list above was tiny (about 40 words), so most Spanish sentences found no filmable word and fell back
# to the same three generic searches. These are common, filmable documentary nouns (nature, weather, places, industry).
# Words with several or figurative meanings ("cabo", "pico", "carta", "gente", "muralla") are left out on purpose.
ES.update({
    'tormenta': 'storm clouds', 'relámpago': 'lightning storm', 'relámpagos': 'lightning storm', 'rayo': 'lightning', 'trueno': 'thunderstorm',
    'lluvia': 'rain', 'amanecer': 'sunrise', 'atardecer': 'sunset', 'noche': 'night sky', 'luna': 'moon', 'estrellas': 'stars', 'estrella': 'stars',
    'viento': 'wind', 'niebla': 'fog', 'nieve': 'snow', 'hielo': 'ice', 'glaciar': 'glacier', 'fuego': 'fire', 'incendio': 'wildfire', 'humo': 'smoke',
    'terremoto': 'earthquake', 'inundación': 'flood', 'inundaciones': 'flood', 'sequía': 'drought', 'huracán': 'hurricane', 'tornado': 'tornado',
    'golfo': 'gulf coast', 'bahía': 'bay', 'laguna': 'lagoon', 'pantano': 'swamp', 'humedal': 'wetland', 'manglar': 'mangrove', 'delta': 'river delta',
    'cascada': 'waterfall', 'catarata': 'waterfall', 'manantial': 'spring water', 'orilla': 'shoreline', 'ola': 'ocean waves', 'olas': 'ocean waves',
    'cordillera': 'mountain range', 'sierra': 'mountain range', 'cima': 'mountain peak', 'colina': 'hills', 'llanura': 'plains', 'pradera': 'grassland',
    'meseta': 'plateau', 'acantilado': 'cliffs', 'península': 'peninsula', 'arrecife': 'coral reef', 'coral': 'coral reef', 'dunas': 'sand dunes',
    'duna': 'sand dunes', 'jungla': 'jungle', 'lava': 'lava', 'ríos': 'river', 'cuenca': 'basin valley', 'volcanes': 'volcano',
    'ballena': 'whale', 'delfín': 'dolphin', 'pez': 'fish', 'peces': 'fish', 'tiburón': 'shark', 'ave': 'birds', 'aves': 'birds', 'pájaro': 'birds',
    'águila': 'eagle', 'caballo': 'horse', 'ganado': 'cattle', 'ovejas': 'sheep', 'árbol': 'trees', 'árboles': 'trees', 'palmera': 'palm trees',
    'palmeras': 'palm trees', 'flor': 'flowers', 'flores': 'flowers', 'hierba': 'grass', 'campo': 'countryside fields', 'cultivo': 'farm fields',
    'agricultor': 'farmer', 'granja': 'farm', 'pueblo': 'village', 'aldea': 'village', 'calle': 'street', 'plaza': 'town square', 'mercado': 'market',
    'puerto': 'harbor', 'muelle': 'pier', 'faro': 'lighthouse', 'carretera': 'highway', 'camino': 'dirt road', 'tren': 'train', 'avión': 'airplane',
    'helicóptero': 'helicopter', 'satélite': 'satellite', 'planeta': 'planet', 'espacio': 'outer space', 'galaxia': 'galaxy', 'cohete': 'rocket launch',
    'petróleo': 'oil', 'pozo': 'well', 'refinería': 'oil refinery', 'torre': 'tower', 'fábrica': 'factory', 'chimenea': 'smokestack', 'mina': 'mine',
    'minería': 'mining', 'oro': 'gold', 'electricidad': 'power lines', 'bandera': 'flag waving', 'pirata': 'pirate ship', 'tesoro': 'treasure chest',
    'brújula': 'compass', 'velero': 'sailboat', 'submarino': 'submarine', 'fortaleza': 'fortress', 'templo': 'temple',
    'catedral': 'cathedral', 'palacio': 'palace', 'pirámide': 'pyramid', 'estatua': 'statue', 'museo': 'museum', 'monumento': 'monument',
    'biblioteca': 'library', 'libro': 'old book', 'manuscrito': 'old manuscript', 'reloj': 'clock', 'laboratorio': 'laboratory',
    'científico': 'scientist', 'microscopio': 'microscope', 'hospital': 'hospital', 'escuela': 'school', 'niños': 'children', 'multitud': 'crowd',
    'pescador': 'fisherman', 'pescadores': 'fisherman', 'comida': 'food', 'fruta': 'fruit', 'cacao': 'cocoa', 'maíz': 'corn field', 'nube': 'clouds',
})
ENDINGS = {'de': ('en', 'n', 'e', 'er', 's', 'es'), 'fr': ('s', 'x', 'es'), 'es': ('s', 'es'), 'tr': ('lar', 'ler', 'ları', 'leri', 'ı', 'i', 'u', 'ü', 'da', 'de', 'ta', 'te', 'dan', 'den')}


def fold(word):
    return unicodedata.normalize('NFC', word.casefold().strip("’'-.,;:!?"))


def english(word, language='de'):
    """English stock words for one narration word, or ''."""
    table = {'tr': TR, 'fr': FR, 'es': ES}.get(language, DE)
    low = fold(word)
    if language in ('fr', 'es', 'it') and re.match(r"^[a-z]{1,2}['’]", low): low = re.split(r"['’]", low, maxsplit=1)[1]  # d'années → années
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
