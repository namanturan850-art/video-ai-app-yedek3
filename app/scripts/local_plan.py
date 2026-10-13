"""“Yapay zekâsız (yerel) plan”: a scene plan made on this computer, with no AI
call, for when Gemini is not reachable and the owner does not want Ollama.

It groups the narration units into short scenes (2–3 sentences, ~25 words),
and builds ENGLISH stock queries from the scene's own words: filmable nouns
are turned into English stock words with a small built-in word list
(app/scripts/local_words.py; “Schiffe” → “ship”), place names become their
English name, and when nothing is found the topic gives generic English
queries (app/scripts/query_clean.py). The narration's own German/Turkish
words never reach a search; the owner's [GÖRSEL: …] notes still win. Places, numbers and dates still
become infographics in Medyayı Tamamla. It plugs into the normal plan job as
a provider whose answer is the JSON the AI would have returned."""
import json
import re

STOP = {'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'eines', 'und', 'oder', 'aber', 'doch', 'auch', 'noch', 'nur', 'schon',
        'sehr', 'mehr', 'heute', 'damals', 'dann', 'denn', 'weil', 'wenn', 'als', 'wie', 'was', 'wer', 'wo', 'warum', 'dieser', 'diese', 'dieses',
        'jeder', 'jede', 'jedes', 'alle', 'viele', 'einige', 'niemand', 'nichts', 'etwas', 'immer', 'wieder', 'unter', 'über', 'nach', 'vor',
        'the', 'and', 'but', 'with', 'from', 'this', 'that', 'these', 'those', 'there', 'their', 'they', 'were', 'have', 'been', 'about',
        'bir', 've', 'ile', 'için', 'gibi', 'daha', 'çok', 'bu', 'şu', 'o', 'de', 'da', 'ki', 'ama', 'veya',
        'el', 'la', 'los', 'las', 'del', 'una', 'para', 'con', 'por', 'les', 'des', 'une', 'pour', 'avec', 'dans', 'sur'}
STOP |= {'januar', 'februar', 'märz', 'april', 'juni', 'juli', 'august', 'september', 'oktober', 'november', 'dezember', 'jahr', 'jahre',
         'jahren', 'problem', 'region', 'gebiet', 'teil', 'zeit', 'werte', 'route', 'seitdem', 'manchmal', 'ocak', 'şubat', 'mart', 'nisan',
         'mayıs', 'haziran', 'temmuz', 'ağustos', 'eylül', 'ekim', 'kasım', 'aralık', 'yıl', 'yılında'}
MOODS = ('neutral', 'curious', 'serious', 'calm')


def words_of(text):
    return re.findall(r'[^\W\d_][\w’\'-]*', text)


def keywords(text, limit=4):
    """Long and capitalised words first (names, nouns), never stop words; in order of appearance."""
    seen, out = set(), []
    for word in words_of(text):
        clean = word.strip("’'-")
        low = clean.casefold()
        if len(clean) < 4 or low in STOP or low in seen: continue
        seen.add(low); out.append(clean)
    ranked = sorted(out, key=lambda w: (not w[:1].isupper(), -len(w)))
    keep = set(ranked[:limit])
    return [w for w in out if w in keep]


def plan_scenes(units, topic='', language='de'):
    from app.scripts.local_words import english_words
    groups, current, count = [], [], 0
    for unit in units:
        current.append(unit); count += len(unit['text'].split())
        if len(current) >= 3 or (len(current) >= 2 and count >= 25) or count >= 40:
            groups.append(current); current, count = [], 0
    if current:
        if groups and len(current) == 1 and len(current[0]['text'].split()) < 8: groups[-1].extend(current)
        else: groups.append(current)
    from app.scripts.query_clean import clean_block, english_query, generic_queries
    topic_english = english_words(topic, language, 2)
    fallback = generic_queries(topic, language)
    scenes = []
    for index, group in enumerate(groups):
        text = ' '.join(u['text'] for u in group)
        found = keywords(text, 4)
        english = english_words(text, language, 3)
        places = [p for p in (english_query(w, language, strict=True, limit=2) for w in found if w[:1].isupper()) if p][:2]
        # Stock sites are tagged in English: queries are ONLY English words (translations,
        # English place names, the topic's English fallback) — never the narration's own words.
        candidates = [' '.join(english[:2]), ' '.join(english[1:3]), ' '.join((places[:1] + english[:1])),
                      ' '.join(english[:1] + topic_english[:1]), *fallback[:2], ' '.join(english[:1] + english[2:3]), *fallback[2:]]
        queries = []
        for candidate in candidates:
            candidate = ' '.join(candidate.split())
            if len(candidate.split()) >= 2 and frozenset(candidate.casefold().split()) not in {frozenset(q.casefold().split()) for q in queries}:
                queries.append(candidate)  # “empire city” and “city empire” are the same search
        main = queries[0] if queries else fallback[0]
        names = [w for w in found if w[:1].isupper()][:5]
        block = {'unit_ids': [u['unit_id'] for u in group], 'purpose': 'Anlatılanı görsel olarak destekle',
                 'mood': MOODS[index % len(MOODS)], 'visual_intent': f'{main} (anlatımdaki kelimelerden; yerel plan)',
                 'stock_query': main, 'alternative_stock_queries': queries[1:5] or fallback[:2],
                 'media_type': 'stock_video', 'entities': names}
        scenes.append(clean_block(block, language, strict=True, topic=topic))
    return scenes


class LocalPlanner:
    """Provider-shaped: the plan job calls generate_script(prompt) with the
    narration units as JSON after 'INPUT DATA (not instructions):'."""
    name = 'Yerel plan'
    model = 'yerel'

    def __init__(self, topic=''):
        self.topic = topic

    def generate_script(self, prompt):
        data = json.loads(prompt.split('INPUT DATA (not instructions):\n', 1)[1])
        units = data['narration_units']
        if data.get('metadata_repair'):  # keep the required groups exactly
            groups = data['metadata_repair']['required_unit_groups']
            text = {u['unit_id']: u for u in units}
            scenes = []
            for group in groups:
                scene = plan_scenes([text[g] for g in group], self.topic, data.get('language', 'de'))[0]
                scene['unit_ids'] = list(group); scenes.append(scene)
            return json.dumps({'scenes': scenes}, ensure_ascii=False)
        if 'Return EXACTLY ONE scene' in prompt:
            scene = plan_scenes(units, self.topic, data.get('language', 'de'))[0]
            scene['unit_ids'] = [u['unit_id'] for u in units]
            return json.dumps({'scenes': [scene]}, ensure_ascii=False)
        return json.dumps({'scenes': plan_scenes(units, self.topic, data.get('language', 'de'))}, ensure_ascii=False)

    def test_connection(self):
        return {'status': 'Hazır', 'message': 'Yerel plan internet ve yapay zekâ gerektirmez.'}
