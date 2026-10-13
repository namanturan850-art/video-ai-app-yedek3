"""Period and place of a video ("antik Mezopotamya", "1960'lar ABD",
"günümüz okyanus"), read from the narration text itself — no AI needed.

The media director uses it on every stock candidate:
  * the local picture model (CLIP) also compares the frames with things
    that contradict the period (modern people/cars/cities in an ancient
    topic), with a cartoon/3D version of the shot (history documentaries
    are photographic) and with landmarks of places the video never
    mentions (Easter Island in a Babylon video) — a clear hit drops it;
  * provider tags get the same check when CLIP is not installed;
  * when nothing fits, neutral footage of the setting (landscape, sky,
    texture) is searched before a text card.
All word lists are plain data; a new region or era is one entry here."""
import re
from statistics import median

# ---- periods ----------------------------------------------------------------
BC = re.compile(r'(?i)(v\.\s*chr\.?|vor\s+christus|\bb\.?\s?c\.?(?:e\.?)?\b|\bm\.?\s?ö\.?(?=\s|$|[,.;])|milattan\s+önce|'
                r'av\.\s*j\.?-?c\.?|a\.\s*c\.(?=\s)|antes\s+de\s+cristo|before\s+christ)')
# A four-digit number is a year only with a year word around it ("im Jahr 1453", "1453 yılında", "in 1969"):
# "1200 Kilometer" or "10000 Soldaten" are not.
YEAR = re.compile(r'(?i)(?:\b(?:im\s+jahre?|jahr|anno|um|seit|bis|ab|in|year|since|until|by|en|año|vers|depuis|en\s+el\s+año|en\s+l\'an)\s+'
                  r'(1\d{3}|20[0-2]\d)(?![\d])(?![.,]\d))|(?:(?<![\d.,])(1\d{3}|20[0-2]\d)\s*[\'’]?\s*(?:de|da|te|ta|den|dan|ten|tan|yılı\w*|senesi\w*)\b)')
DECADE = re.compile(r'(?i)(?<!\d)(1[89]\d0|20[0-2]0)(?:\s*[\'’]?\s*(?:s|er|lar|ler|larda|lerde|lı|li)\b|-?ies\b)|'
                    r'\b(?:the\s+)?(?:twenties|thirties|forties|fifties|sixties|seventies|eighties|nineties)\b|'
                    r'\b(?:zwanziger|dreißiger|vierziger|fünfziger|sechziger|siebziger|achtziger|neunziger)\b')
DECADE_WORDS = {'twenties': 1920, 'thirties': 1930, 'forties': 1940, 'fifties': 1950, 'sixties': 1960, 'seventies': 1970,
                'eighties': 1980, 'nineties': 1990, 'zwanziger': 1920, 'dreißiger': 1930, 'vierziger': 1940, 'fünfziger': 1950,
                'sechziger': 1960, 'siebziger': 1970, 'achtziger': 1980, 'neunziger': 1990}
ERA_WORDS = {
    'prehistoric': r'stone age|steinzeit|taş devri|neanderthal\w*|neandertal\w*|höhlenmensch\w*|cave (?:man|men|painting)|mammut\w*|mammoth\w*|'
                   r'dinosaur\w*|dinosaurier\w*|dinozor\w*|prähistor\w*|prehistor\w*|tarih öncesi|préhistor\w*|prehistór\w*',
    'ancient': r'ancient|antiquity|antik\w*|altertum\w*|bronze age|bronzezeit|tunç çağı|iron age|eisenzeit|pharao\w*|pharaoh\w*|firavun\w*|'
               r'sumer\w*|sümer\w*|babylon\w*|babil\w*|assyr\w*|asur\w*|akkad\w*|hethit\w*|hitit\w*|mesopotam\w*|mezopotamya\w*|'
               r'gladiator\w*|gladyatör\w*|legion\w*|lejyon\w*|caesar|cäsar|sezar|römisches reich|roman empire|roma imparatorluğu|'
               r'pyramidenbau\w*|keilschrift|cuneiform|çivi yazısı|hieroglyph\w*|hiyeroglif\w*|antiqu\w*|antigu\w*',
    'medieval': r'medieval|middle ages|mittelalter\w*|orta ?çağ\w*|moyen âge|edad media|knight\w*|ritter\w*|şövalye\w*|crusade\w*|'
                r'kreuzz\w*|haçlı\w*|viking\w*|wikinger\w*|feudal\w*|burgherr\w*|chevalier\w*|caballero\w*|byzan\w*|bizans\w*',
    'early_modern': r'renaissance|rönesans\w*|renacimiento|baroque|barock|barok|conquistador\w*|konkistador\w*|'
                    r'pirate\w*|piraten?|korsan\w*|musket\w*|muskete\w*',
}
ERA_RE = {era: re.compile(r'(?i)\b(?:' + words + r')\b') for era, words in ERA_WORDS.items()}
MODERN_WORDS = re.compile(r'(?i)\b(?:today|nowadays|modern|heute|heutzutage|bugün|günümüz\w*|aujourd\'hui|hoy|actualmente|'
                          r'smartphone\w*|internet|klimawandel|climate change|iklim değişikliği)\b')
ERA_EN = {'prehistoric': 'prehistoric', 'ancient': 'ancient', 'medieval': 'medieval', 'early_modern': '16th-18th century',
          '19th': '19th century', '20th': '20th century', 'contemporary': 'present-day'}
ERA_TR = {'prehistoric': 'tarih öncesi', 'ancient': 'antik', 'medieval': 'Orta Çağ', 'early_modern': '16.–18. yüzyıl',
          '19th': '19. yüzyıl', '20th': '20. yüzyıl', 'contemporary': 'günümüz'}
PREMODERN = ('prehistoric', 'ancient', 'medieval', 'early_modern')
HISTORY = PREMODERN + ('19th', '20th')

# ---- places -----------------------------------------------------------------
# key: (words in any narration language, English name, Turkish name, family,
#       landmark prompts for the picture model, landmark words in provider tags,
#       neutral footage queries for this place)
REGIONS = {
    'mesopotamia': (r'mesopotam\w*|mezopotamya\w*|babylon\w*|babil\w*|sumer\w*|sümer\w*|akkad\w*|assyr\w*|asur\w*|ninive|nineveh|ninova|'
                    r'euphrat\w*|euphrates|fırat|tigris|dicle|uruk|ur|ziggurat\w*|zikkurat\w*|irak|iraq|nebukadnezar|nebuchadnezzar|hammurabi',
                    'Mesopotamia', 'Mezopotamya', 'near_east', (), (), ('desert landscape', 'river reeds sunset', 'mud brick wall texture')),
    'levant': (r'jerusalem|kudüs|jérusalem|israel\w*|juda\w*|judäa|judea|kanaan|canaan|palästin\w*|palestin\w*|filistin\w*|phöniz\w*|phoenic\w*|fenike\w*',
               'the Levant', 'Levant', 'near_east', (), (), ('desert hills landscape', 'olive trees', 'old stone wall texture')),
    'persia': (r'persien|persia\w*|pers(?:er|isch\w*|ian)|iran\w*|persepolis|achämenid\w*|achaemenid\w*|ahameniş\w*',
               'Persia', 'İran', 'near_east', ('the ruins of Persepolis',), ('persepolis',), ('desert mountains landscape', 'old stone texture')),
    'anatolia': (r'anatoli\w*|anadolu\w*|troja|troy|truva|hattusa|istanbul|konstantinopel|constantinople|kleinasien|asia minor',
                 'Anatolia', 'Anadolu', 'near_east', ('the Hagia Sophia in Istanbul',), ('hagia', 'sophia', 'istanbul'), ('steppe hills landscape', 'old stone wall texture')),
    'egypt': (r'ägypt\w*|egypt\w*|mısır\w*|égypt\w*|egipt\w*|pharao\w*|pharaoh\w*|firavun\w*|nil|nile|giza|gize|kairo|cairo|kahire|luxor|karnak|sphinx|sfenks',
              'Egypt', 'Mısır', 'egypt', ('the pyramids of Giza in Egypt', 'the Great Sphinx of Giza'), ('giza', 'sphinx', 'egypt', 'egyptian', 'pharaoh', 'cairo'),
              ('desert sand dunes', 'nile river sunset', 'sandstone texture')),
    'greece': (r'griech\w*|greece|greek|yunan\w*|grec\w*|athen\w*|athens|atina|sparta\w*|parthenon|akropolis|acropolis|mykene|mycenae|kreta|crete|girit',
               'Greece', 'Yunanistan', 'mediterranean', ('the Parthenon temple in Athens',), ('parthenon', 'acropolis', 'athens', 'santorini'),
               ('mediterranean coast cliffs', 'olive grove', 'marble texture')),
    'rome': (r'rom|rome|roma|römer\w*|römisch\w*|roman\w*|romain\w*|romano\w*|kolosseum|colosseum|kolezyum|caesar|cäsar|sezar|pompeji|pompeii',
             'Rome', 'Roma', 'mediterranean', ('the Colosseum in Rome',), ('colosseum', 'coliseum', 'vatican'), ('italian countryside hills', 'old stone texture')),
    'mesoamerica': (r'maya\w*|azte[kc]\w*|tenochtitlan|teotihuacan|mexik\w*|mexico|meksika\w*|olme[kc]\w*',
                    'Mesoamerica', 'Orta Amerika', 'americas', ('a Mayan step pyramid in the jungle',), ('mayan', 'maya', 'aztec', 'chichen', 'teotihuacan', 'tikal'),
                    ('tropical jungle canopy', 'misty rainforest')),
    'andes': (r'inka\w*|inca\w*|peru\w*|machu picchu|anden|andes|and dağları',
              'the Andes', 'And Dağları', 'americas', ('Machu Picchu in the Andes mountains',), ('machu', 'picchu', 'inca', 'inka', 'peru'),
              ('andes mountains clouds', 'mountain valley mist')),
    'china': (r'china|chines\w*|chinois\w*|çin|çinli\w*|peking|beijing|pekin|han-dynastie|han dynasty|ming|qin|große mauer|great wall',
              'China', 'Çin', 'east_asia', ('the Great Wall of China', 'a Chinese pagoda'), ('china', 'chinese', 'pagoda', 'beijing', 'shanghai'),
              ('misty mountains', 'bamboo forest')),
    'japan': (r'japan\w*|japon\w*|samurai\w*|tokio|tokyo|kyoto|shogun\w*|şogun\w*',
              'Japan', 'Japonya', 'east_asia', ('a Japanese shrine with a red torii gate',), ('japan', 'japanese', 'torii', 'tokyo', 'kyoto', 'fuji'),
              ('cherry blossom trees', 'misty mountains')),
    'india': (r'indien|india\w*|hindistan\w*|inde|hindu\w*|ganges|ganj|mogul\w*|mughal\w*|babür\w*|indus',
              'India', 'Hindistan', 'south_asia', ('the Taj Mahal in India', 'a Hindu temple in India'), ('taj', 'mahal', 'india', 'indian', 'hindu', 'varanasi'),
              ('river ghats sunrise', 'dusty plains landscape')),
    'cambodia': (r'angkor|khmer|kambodscha|cambodia|kamboçya',
                 'Cambodia', 'Kamboçya', 'south_asia', ('the Angkor Wat temple in Cambodia',), ('angkor', 'cambodia'), ('tropical jungle canopy',)),
    'easter_island': (r'osterinsel|easter island|paskalya adası|rapa nui|île de pâques|isla de pascua|moai',
                      'Easter Island', 'Paskalya Adası', 'pacific', ('moai stone head statues on Easter Island',), ('moai', 'easter', 'rapa', 'nui'),
                      ('volcanic coast grass', 'pacific ocean waves')),
    'britain': (r'stonehenge|britann\w*|britain|british|england|englisch\w*|english|ingiltere|ingiliz\w*|london|londra|schottland|scotland|iskoçya',
                'Britain', 'Britanya', 'europe_north', ('Stonehenge stone circle',), ('stonehenge',), ('green hills fog', 'rainy moor landscape')),
    'france': (r'frankreich|france|fransa\w*|französisch\w*|french|paris|eiffel',
               'France', 'Fransa', 'europe_west', ('the Eiffel Tower in Paris',), ('eiffel', 'paris'), ('countryside fields', 'old stone texture')),
    'usa': (r'usa|u\.s\.a?\.?|amerika\w*|america\w*|abd|vereinigte staaten|united states|états-unis|estados unidos|new york|washington|kalifornien|california',
            'the USA', 'ABD', 'americas_north', ('the New York City skyline', 'the Statue of Liberty'), ('manhattan', 'liberty', 'hollywood', 'york'),
            ('prairie landscape', 'highway desert landscape')),
    'arctic': (r'arktis|arctic|kuzey kutbu|antarktis|antarctic\w*|antarktika|grönland|greenland|grönland|polar\w*|kutup',
               'the polar regions', 'kutup bölgesi', 'polar', ('a snowy arctic landscape with icebergs',), ('arctic', 'iceberg', 'glacier', 'antarctica', 'igloo'),
               ('ice floes', 'snow landscape')),
    'ocean': (r'ozean\w*|ocean\w*|okyanus\w*|océan\w*|tiefsee|deep sea|derin deniz|korallen\w*|coral reef\w*|mercan\w*|wal(?:e|fisch\w*)|whale\w*|balina\w*|hai(?:e|fisch\w*)|shark\w*|köpekbalı\w*',
              'the ocean', 'okyanus', 'ocean', (), (), ('ocean waves', 'underwater light rays', 'deep blue water')),
    'space': (r'weltall|weltraum|universum|universe|evren|uzay|galax\w*|galaksi\w*|planet\w*|gezegen\w*|schwarze[sn]? loch|black hole|kara delik|nebula|nebel',
              'space', 'uzay', 'space', (), (), ('starry night sky', 'nebula stars')),
}
REGION_RE = {k: re.compile(r'(?i)(?<![\w])(?:' + v[0] + r')(?![\w])') for k, v in REGIONS.items()}

# Things that did not exist in a period (picture-model prompts, Turkish label for the screen, tag words).
ANACHRONISMS = (  # (exists since year, its tag words prove it before year, picture-model prompt, Turkish label, provider tag words)
    (1995, 1950, 'modern people in contemporary clothes', 'modern insanlar', ('jeans', 'tourist', 'tourists', 'selfie', 'hipster', 'businessman')),
    (1975, 1900, 'cars driving on a modern road', 'araba/trafik', ('car', 'cars', 'traffic', 'highway', 'taxi', 'bus', 'truck', 'motorcycle')),
    (1900, 1900, 'a modern city with concrete buildings and street lights', 'modern şehir', ('skyline', 'skyscraper', 'apartment', 'downtown', 'metropolis')),
    (1970, 1900, 'people shopping in a modern store', 'modern alışveriş', ('shopping', 'mall', 'supermarket', 'shop', 'store', 'boutique', 'retail', 'checkout')),
    (1900, 1890, 'power lines and electric poles', 'elektrik hattı', ('powerline', 'pylon')),
    (1955, 1910, 'a modern jet airplane in the sky', 'uçak', ('airplane', 'aircraft', 'airport', 'jet')),
    (1980, 1970, 'a smartphone or a computer screen', 'telefon/ekran', ('smartphone', 'phone', 'laptop', 'computer', 'screen', 'tablet', 'keyboard')),
    (1970, 1930, 'a modern glass skyscraper', 'cam gökdelen', ('skyscraper',)),
    (2005, 2005, 'a modern electric car', 'modern araba', ('tesla',)),
    (1990, 1985, 'wind turbines', 'rüzgâr türbini', ('turbine',)),
)
STYLE = (  # history documentaries are photographic: same subject, other look
    ('a cartoon drawing of {subject}', 'karikatür/çizgi film', ('cartoon', 'comic', 'clipart', 'clip art', 'anime', 'emoji', 'kawaii'), True),
    ('a 3D computer rendering of {subject}', '3D çizim', ('3d', 'render', 'rendering', 'cgi', 'blender'), False),
    ('a video game screenshot of {subject}', 'video oyunu', ('game', 'gaming', 'videogame'), False),
)
KIND_TR = {'anachronism': 'dönemle çelişiyor', 'style': 'belgesel üslubuna uymuyor', 'place': 'yanlış coğrafya'}
NEUTRAL_ANY = ('clouds sky timelapse', 'old stone texture', 'sunset sky')


def _words(text):
    return set(re.findall(r'[a-z]+', str(text or '').casefold()))


def _decade(text):
    found = []
    for match in DECADE.finditer(text):
        if match.group(1): found.append(int(match.group(1)))
        else:
            word = match.group(0).casefold().split()[-1]
            if word in DECADE_WORDS: found.append(DECADE_WORDS[word])
    return found


def _era_of_year(year):
    if year < 500: return 'ancient'
    if year < 1500: return 'medieval'
    if year < 1800: return 'early_modern'
    if year < 1900: return '19th'
    if year < 2000: return '20th'
    return 'contemporary'


def period(text):
    """(era, decade or None, evidence count) of a piece of text."""
    text = ' '.join(str(text or '').split())
    votes = {}
    bc = len(BC.findall(text))
    if bc: votes['ancient'] = votes.get('ancient', 0) + 3 * bc
    for era, pattern in ERA_RE.items():
        hits = len(pattern.findall(text))
        if hits: votes[era] = votes.get(era, 0) + 2 * hits
    years = [] if bc else [int(a or b) for a, b in YEAR.findall(text)]
    decades = _decade(text)
    for year in years + decades:
        era = _era_of_year(year)
        votes[era] = votes.get(era, 0) + 2
    for region, pattern in REGION_RE.items():  # places that only exist in the past (Babylon, Sumer …) are period evidence too
        if region in ('mesopotamia',) and pattern.search(text): votes['ancient'] = votes.get('ancient', 0) + 1
    if not votes:
        return ('contemporary', None, 0) if MODERN_WORDS.search(text) else (None, None, 0)
    era = max(votes, key=lambda e: (votes[e], HISTORY.index(e) if e in HISTORY else -1))
    decade = None
    if era == '20th':
        modern = [y for y in years + decades if 1900 <= y < 2000]
        if decades: decade = max(set(decades), key=decades.count)
        elif modern: decade = int(median(modern)) // 10 * 10
    return era, decade, votes[era]


def places(text):
    """Region keys named in the text, most mentioned first."""
    counts = {k: len(p.findall(str(text or ''))) for k, p in REGION_RE.items()}
    return [k for k in sorted(counts, key=counts.get, reverse=True) if counts[k]]


def infer(texts, topic=''):
    """The video's setting from all of its narration (+ the topic, counted twice)."""
    joined = ' '.join([str(topic or '')] * 2 + [str(t or '') for t in texts])
    era, decade, evidence = period(joined)
    regions = places(joined)
    if era is None:
        era = 'contemporary' if regions and set(regions) <= {'ocean', 'space'} else None
    return describe(era, decade, regions, evidence)


def describe(era, decade, regions, evidence=0):
    main = [r for r in regions if r not in ('ocean', 'space')][:1] or regions[:1]
    era_en = f'{decade}s' if decade else ERA_EN.get(era, '')
    era_tr = f"{decade}'lar" if decade else ERA_TR.get(era, '')
    place_en = REGIONS[main[0]][1] if main else ''
    place_tr = REGIONS[main[0]][2] if main else ''
    return {'era': era, 'decade': decade, 'regions': regions[:6], 'evidence': evidence,
            'label': ' '.join(x for x in (era_tr, place_tr) if x),
            'label_en': ' '.join(x for x in (era_en, place_en.removeprefix('the ')) if x)}


def for_scene(setting, scene_text):
    """The video's setting; a scene that names its own years/period (a flashback,
    "1850", "v. Chr.") gets that period. Places stay the video's (all allowed)."""
    if not setting: return setting
    era, decade, evidence = period(scene_text)
    if era and era != setting.get('era') and evidence >= 2 and (BC.search(scene_text or '') or YEAR.search(scene_text or '') or _decade(scene_text or '')):
        return {**describe(era, decade, setting.get('regions') or [], evidence), 'scene_override': True}
    return setting


def year(setting):
    """A representative year of the setting (None: present day / unknown)."""
    era, decade = setting.get('era'), setting.get('decade')
    if decade: return decade + 5
    return {'prehistoric': -10000, 'ancient': -500, 'medieval': 1100, 'early_modern': 1650, '19th': 1850, '20th': 1950}.get(era)


def penalties(setting, descriptor=''):
    """Picture-model prompts for what contradicts the setting:
    [{'kind', 'text', 'label'}]. Prompts that share all their words with
    the shot's own description are left out (it may ask for exactly that)."""
    if not setting or not setting.get('era'): return []
    out, own = [], _words(descriptor) - {'a', 'an', 'the', 'of', 'in', 'on', 'with', 'and', 'or', 'photo'}
    when = year(setting)
    for since, _, text, label, _ in ANACHRONISMS:
        if when is not None and when < since and not (_words(text) - {'a', 'an', 'the', 'in', 'on', 'and', 'or', 'with'}) <= own:
            out.append({'kind': 'anachronism', 'text': text, 'label': label})
    if setting['era'] in HISTORY:
        for text, label, _, always in STYLE:
            if setting['era'] == 'prehistoric' and not always: continue  # dinosaurs/early humans: reconstructions are normal
            out.append({'kind': 'style', 'text': text, 'label': label})
    allowed = set(setting.get('regions') or [])
    if allowed - {'ocean', 'space'}:
        families = {REGIONS[r][3] for r in allowed}
        for region, (_, name, name_tr, family, prompts, _, _) in REGIONS.items():
            if region in allowed or family in families: continue
            for text in prompts[:1]:
                if not (_words(text) & own - {'temple', 'stone', 'statues', 'statue', 'ruins'}):
                    out.append({'kind': 'place', 'text': text, 'label': name_tr})
    seen, unique = set(), []
    for item in out:
        if item['text'] not in seen: seen.add(item['text']); unique.append(item)
    return unique[:30]


def tag_conflict(setting, tags, provider=''):
    """(kind, label) when the provider's tags contradict the setting, else None.
    `tags` is the normalized, space-padded tag text."""
    if not setting or not setting.get('era'): return None
    tags = ' ' + ' '.join(re.findall(r'\w+', str(tags).casefold())) + ' '  # provider tags come comma-separated
    has = lambda word: f' {word} ' in tags or f' {word}s ' in tags
    when = year(setting)
    if provider != 'wikimedia' and when is not None:  # museum/archive photos may mention modern things in their captions
        for _, before, _, label, words in ANACHRONISMS:
            if when < before and any(has(w) for w in words): return 'anachronism', label
    if setting['era'] in HISTORY:
        for _, label, words, always in STYLE:
            if setting['era'] == 'prehistoric' and not always: continue
            if any(has(w) for w in words): return 'style', label
    allowed = set(setting.get('regions') or [])
    if allowed - {'ocean', 'space'}:
        families = {REGIONS[r][3] for r in allowed}
        for region, (_, _, name_tr, family, _, words, _) in REGIONS.items():
            if region in allowed or family in families: continue
            if any(has(w) for w in words): return 'place', name_tr
    return None


def neutral_queries(setting):
    """English stock queries for neutral footage of the setting (landscape, sky, texture)."""
    out = []
    for region in (setting or {}).get('regions') or []:
        out += list(REGIONS[region][6])
    if (setting or {}).get('era') in PREMODERN and not out:
        out += ['desert landscape', 'old stone texture']
    out += list(NEUTRAL_ANY)
    return list(dict.fromkeys(out))[:5]


def reason(conflict):
    """Plain Turkish sentence for a rejected candidate."""
    return f'{KIND_TR.get(conflict.get("kind"), "uygunsuz")} ({conflict.get("label", "")})'
