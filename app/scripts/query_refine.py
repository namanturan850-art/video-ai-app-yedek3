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


def refine(blocks, language='de', topic=''):
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
    from app.scripts.query_clean import clean_block
    for block in blocks:  # stock sites are tagged in English: no German/Turkish word, number or “v. Chr.” in a search
        clean_block(block, language, topic=topic)
    return blocks


SHARE = .25  # at most this share of the scenes become infographics by default (owner markers and plan included)
ROUTE_WORDS = re.compile(r'(?i)\b(nach|von|über|bis|zog\w*|marschier\w*|reist\w*|segelt\w*|flog|to|from|via|sailed|marched|travell?ed|'
                         r'hasta|desde|vers|depuis)\b|\w+(?:’|\')?(?:[dt][ae]n|[ye]a)\b')


def suggestion(narration, entities=(), language='de'):
    """(score, spec) of the best infographic for a narration, or None: years → timeline,
    a percentage → pie, a counted thing → icons, two places with a movement → route, a number, a place."""
    from app.motion.places import spoken_places
    from app.motion.templates import MotionError, from_narration, validate
    from app.motion.templates_extra import icon_for, validate_extra
    best = None
    sentences = [s.strip() for s in re.split(r'(?<=[.!?…])\s+', narration) if s.strip()]
    for sentence in sentences:
        options = []
        places = spoken_places(sentence)
        if len(places) >= 2 and ROUTE_WORDS.search(sentence):
            stops = [{'name': name[:40], 'lat': lat, 'lon': lon} for name, lat, lon in places[:5]]
            options.append((3, {'template': 'route', 'data': {'stops': stops, 'missing': [], 'source': ' > '.join(s['name'] for s in stops)}, 'emphasis': ''}))
        spec = from_narration(sentence, entities)
        if spec['template'] == 'stat':
            value = spec['data']['value']
            percent = re.search(r'(\d+(?:[.,]\d+)?)\s*%|%\s*(\d+(?:[.,]\d+)?)', value)
            following = sentence[sentence.find(spec['emphasis']) + len(spec['emphasis']):].split()[:2] if spec.get('emphasis') and spec['emphasis'] in sentence else []
            thing = next((w.strip(',.;:') for w in following if icon_for(w.strip(',.;:')) != 'dot'), '')
            digits = re.sub(r'\D', '', value)
            if percent and 0 < float((percent.group(1) or percent.group(2)).replace(',', '.')) <= 100:
                number = float((percent.group(1) or percent.group(2)).replace(',', '.'))
                options.append((3, {'template': 'ratio', 'data': {'value': value, 'percent': number, 'label': spec['data']['label'], 'source': sentence[:120]}, 'emphasis': spec['emphasis']}))
            elif thing and digits and 2 <= int(digits) <= 10 ** 9 and not re.fullmatch(r'1\d{3}|20\d{2}', digits):
                options.append((3, {'template': 'icons', 'data': {'value': value, 'number': int(digits), 'object': thing[:40], 'icon': icon_for(thing), 'source': f'{value} {thing}'}, 'emphasis': spec['emphasis']}))
            else:
                options.append((2, spec))
        elif spec['template'] == 'timeline':
            options.append((3, spec))
        elif spec['template'] == 'map':
            options.append((1, spec))
        for score, option in options:
            try:
                checked = validate_extra(option) if option['template'] in ('route', 'ratio', 'icons') else validate(option, narration, entities)
            except (MotionError, ValueError, TypeError, KeyError):
                continue
            if best is None or score > best[0]: best = (score, checked)
    return best


def suggest_infographics(blocks, language='de', share=SHARE):
    """Sentences with numbers, dates, places or routes get an infographic the
    owner can approve or change on the media screen — at most `share` of the
    scenes are infographics in total (markers and the plan's own included)."""
    limit = int(len(blocks) * share)
    used = sum(max(1 if b.get('motion_spec') else 0, sum(1 for h in b.get('owner_hints') or [] if h.get('type') != 'visual')) for b in blocks)  # every marker counts
    if used >= limit: return blocks
    ranked = []
    for index, block in enumerate(blocks):
        if block.get('motion_spec') or block.get('owner_hints') or block.get('locked'): continue
        found = suggestion(block.get('narration', ''), block.get('entities') or [], language)
        if found: ranked.append((-found[0], index, found[1]))
    taken = []
    for _, index, spec in sorted(ranked):
        if used >= limit: break
        if any(abs(index - other) < 2 for other in taken): continue  # never two infographic scenes in a row
        before = next((b['motion_spec'] for b in reversed(blocks[:index]) if b.get('motion_spec')), None)
        after = next((b['motion_spec'] for b in blocks[index + 1:] if b.get('motion_spec')), None)
        if any(n and n.get('template') == spec['template'] for n in (before, after)): continue  # the next infographic is a different type
        blocks[index].update(media_type='motion_graphic', motion_spec=spec, motion_suggested=True)
        taken.append(index); used += 1
    return blocks
