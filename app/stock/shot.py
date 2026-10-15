"""Bind a visual slot to its own immutable narration, without changing timing."""
import re

VERSION = 2


def narration(scene, slot):
    text = scene.get('narration_text', scene.get('narration', ''))
    parts = [p for p in re.split(r'(?<=[.!?…])\s+', text) if p.strip()]
    if len(parts) < 2:
        return text.strip()
    span = max(.001, scene['end_estimate'] - scene['start_estimate'])
    a = max(0., (slot['estimated_start'] - scene['start_estimate']) / span)
    b = min(1., (slot['estimated_end'] - scene['start_estimate']) / span)
    weights = [max(1, len(p.split())) for p in parts]
    total, cursor, selected = sum(weights), 0., []
    for part, weight in zip(parts, weights):
        end = cursor + weight / total
        if min(b, end) - max(a, cursor) > .00001:
            selected.append(part)
        cursor = end
    return ' '.join(selected or [parts[-1]]).strip()


def bind(scene, slot, language=None):
    if scene.get('_shot_bound'):
        return scene
    spoken = narration(scene, slot)
    result = {**scene, 'scene_context': scene.get('narration_text', ''),
              'narration_text': spoken, '_shot_bound': True}
    # Scene metadata may span several different subjects. Search the spoken
    # sentence first, keeping the original queries as candidate discovery only.
    from app.scripts.query_clean import english_query, place_english
    spoken_language = language or scene.get('stock_query_language') or 'en'
    query = english_query(spoken, spoken_language, strict=spoken_language != 'en', limit=6)
    for hint in scene.get('owner_hints') or []:
        sentence = str(hint.get('sentence') or '').strip()
        if hint.get('type') == 'visual' and (not sentence or sentence in spoken or spoken in sentence):
            explicit = english_query(hint.get('value', ''), spoken_language, strict=False, limit=6)
            if len(explicit.split()) >= 2:
                query = explicit
                break
    if len(query.split()) >= 2:
        from app.motion.places import spoken_places
        places=[place_english(name,exact=True) for name,_,_ in spoken_places(spoken)]
        entities=[e for e in scene.get('entities', []) if e.casefold() in spoken.casefold()]
        result.update(primary_stock_query=query, visual_intent=query, must_show=query, search_anchor='',
                      entities=list(dict.fromkeys([p for p in places if p]+entities)))
    return result


def memo_key(scene):
    return scene['scene_id'], scene.get('narration_text', '')
