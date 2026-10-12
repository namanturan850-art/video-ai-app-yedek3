"""Clean-up of a scene plan's stock queries before media search (any engine,
especially small local models such as Ollama):

- a query that asks for a map (“map showing …”, “Karte …”, “harita …”)
  becomes a map infographic when a place of the narration is known;
  otherwise the map query is dropped (stock sites have no such maps);
- symbolic/abstract queries (“bird caged in wooden box symbolizing Hiskija”)
  keep only their concrete, filmable part (“bird caged in wooden box”);
- the same query is not copied into neighbouring scenes: a scene whose
  query was used in one of the two scenes before (or already twice in the
  video) takes an unused alternative, or is made specific with its own
  place/name.
The narration is never changed; the owner's [GÖRSEL] notes are applied
after this and still win."""
import re

MAP = re.compile(r'(?i)\b(maps?|karte\w*|landkarte\w*|harita\w*|mapa|carte)\b')
SYMBOLIC = re.compile(r'(?i)\b(symboli[sz]\w*|represent\w*|metaphor\w*|allegor\w*|evok\w*|signif\w*|conceptual\w*|concept of|'
                      r'as a symbol|standing for|embodying|illustrating the idea|the idea of|sinnbild\w*|symbolisch\w*)\b')
CHART = re.compile(r'(?i)\b(diagram|chart|infographic|timeline|graph|statistics?)\b')


def norm(query):
    return ' '.join(re.sub(r'[^\w\s-]', ' ', query or '').split()).casefold()


def concrete(query):
    """The filmable part of a query, or '' when nothing concrete is left."""
    query = ' '.join(str(query or '').split())
    match = SYMBOLIC.search(query)
    if match: query = query[:match.start()]
    query = re.sub(r'(?i)\b(showing|depicting|that shows|with text|labeled|labelled)\b.*$', '', query)
    query = query.strip(' ,;:-–')
    words = query.split()
    return ' '.join(words[:8]) if len(words) >= 2 else ''


def map_infographic(block):
    """A map spec for the block when its narration names a known place."""
    from app.motion.places import lookup, spoken_places
    from app.motion.templates import MotionError, validate
    narration = block.get('narration', '')
    found = spoken_places(narration)
    if not found:
        for text in (block.get('location', ''), *block.get('entities', [])):
            hit = lookup(text) if text else None
            if hit and text.casefold() in narration.casefold(): found = [(text, hit[0], hit[1])]; break
    if not found: return None
    name, lat, lon = found[0]
    try:
        return validate({'template': 'map', 'data': {'place': name, 'label': '', 'lat': lat, 'lon': lon}, 'emphasis': name.split()[0]},
                        narration, block.get('entities', []))
    except MotionError:
        return None


def refine(blocks):
    used = []  # normalized main queries in order
    counts = {}
    for index, block in enumerate(blocks):
        queries = [block.get('stock_query', ''), *block.get('alternative_stock_queries', [])]
        if block.get('media_type') != 'motion_graphic' and any(MAP.search(q) for q in queries[:1]):
            spec = None if block.get('motion_spec') else map_infographic(block)
            if spec:
                block['media_type'], block['motion_spec'], block['shot_count'] = 'motion_graphic', spec, 1
        cleaned = []
        for query in queries:
            if MAP.search(query) or CHART.search(query): continue  # no stock site has these maps/diagrams
            part = concrete(query)
            if part and norm(part) not in (norm(c) for c in cleaned): cleaned.append(part)
        if not cleaned:
            cleaned = [concrete(block.get('visual_intent', '')) or ' '.join(block.get('narration', '').split()[:4]) or 'historic landscape']
        # Not the same query as the scenes just before, nor a query used twice already.
        recent = set(used[-2:])
        fresh = [q for q in cleaned if norm(q) not in recent and counts.get(norm(q), 0) < 2]
        if not fresh:
            detail = next((d for d in (block.get('location'), *(block.get('entities') or []), block.get('action')) if d and norm(d) not in norm(cleaned[0])), '')
            fresh = [' '.join(f'{cleaned[0]} {detail}'.split()[:10])] if detail else []
        main = (fresh or cleaned)[0]
        alternatives = [q for q in cleaned if norm(q) != norm(main)]
        if not alternatives:
            alternatives = [' '.join(main.split()[:2] + ['closeup'])] if norm(main) != norm(' '.join(main.split()[:2] + ['closeup'])) else ['documentary landscape']
        block['stock_query'], block['alternative_stock_queries'] = main[:300], [a[:300] for a in alternatives[:5]]
        used.append(norm(main)); counts[norm(main)] = counts.get(norm(main), 0) + 1
    return blocks
