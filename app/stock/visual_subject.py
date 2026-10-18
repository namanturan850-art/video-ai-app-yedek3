"""Conservative local visual planning; attribution is not a filming location.

Only concepts actually present in narration are composed. Unknown subjects keep
existing planner queries. This is vocabulary matching, never factual inference.
"""
import re
from app.stock.relevance import canonical, normalized, unique

# Research attribution only. A university/building scene without a separate
# visual subject is left intact. Keep the original narration elsewhere.
INSTITUTION = re.compile(
    r'(?:\b(?:University|Universidad|Université|Universität)\s+(?:of|de|do|da|von)\s+[A-ZÀ-ÖØ-Þ][\wÀ-ÿ]*(?:\s+[A-ZÀ-ÖØ-Þ][\wÀ-ÿ]*){0,3}'
    r'|\b[A-ZÀ-ÖØ-Þİ][\wÀ-ÿ]*(?:\s+[A-ZÀ-ÖØ-Þİ][\wÀ-ÿ]*){0,3}\s+(?:Üniversitesi|University|Universität))')
RESEARCH = ('arastir', 'karsilastir', 'research', 'study', 'studied', 'compared', 'investig', 'estudio', 'comparo', 'recherche', 'etude', 'untersuch')
EVENTS = ('lightning', 'wind', 'current', 'storm', 'charging', 'navigation', 'flight')
SUBJECTS = ('lake', 'waterfall', 'ship', 'aircraft', 'train', 'car', 'animal', 'food', 'ocean', 'water', 'forest', 'mountain', 'beach', 'computer', 'urban')


def analyze(text):
    text = str(text or '')
    concepts = canonical(text)
    institutions = []
    clean = text
    if concepts & set(SUBJECTS) and any(w in normalized(text) for w in RESEARCH):
        for match in INSTITUTION.finditer(text):
            institutions.append(match.group())
            clean = clean.replace(match.group(), ' ')
    actual = canonical(clean)
    # Co-occurrence in text alone does not establish a specific geographic link.
    events = [w for w in EVENTS if w in actual]
    subjects = [w for w in SUBJECTS if w in actual]
    modifiers = [w for w in ('tropical', 'night') if w in actual]
    queries = []
    if subjects and (events or institutions):
        queries.append(' '.join([*events[:2], *modifiers, *subjects[:2]]))
        for event in events:
            queries.append(' '.join([event, *subjects[:1]]))
        queries.extend(' '.join([*modifiers, subject]) for subject in subjects)
        if len(subjects) > 1:
            queries.append(' '.join(subjects[:2]))
        for subject in subjects[:2]:
            queries.extend((subject + ' landscape', subject + ' aerial view', subject + ' surface'))
    return {'concepts': sorted(actual & (set(SUBJECTS) | set(EVENTS))),
            'institutions': institutions, 'location_text': clean.strip(),
            'queries': unique(queries), 'subject': ' '.join(subjects[:2])}


def contradiction(media, profile):
    """Reject explicit opposing subjects, not incomplete or absent provider tags."""
    expected = set(profile.get('anchor_tokens', [])) | set(profile.get('context_tokens', []))
    actual = canonical(media.get('description', ''))
    if 'waterfall' in actual and 'waterfall' not in expected and expected & {'lake', 'current', 'wind'}:
        return 'waterfall_instead_of_water_process'
    if 'urban' in actual and 'urban' not in expected and expected & {'lake', 'current', 'lightning'} and not actual & {'lake', 'current', 'lightning'}:
        return 'city_instead_of_natural_subject'
    return None
