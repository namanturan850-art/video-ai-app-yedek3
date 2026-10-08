"""Provider-neutral records and deterministic slots from the Part 5 handoff."""
import math
import re
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal

from app.production import narration_units
from app.scripts.models import ScriptError, word_count


class StockError(ScriptError):
    def __init__(self, category, message, status_code=503):
        super().__init__(message, status_code)
        self.category = category


class Media(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    provider: Literal['pexels', 'pixabay']
    media_id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    media_type: Literal['video', 'image']
    source_url: str = Field(max_length=2000)
    page_url: str = Field(max_length=2000)
    creator_name: str = Field(default='', max_length=300)
    creator_url: str = Field(default='', max_length=2000)
    width: int = Field(gt=0, le=20000)
    height: int = Field(gt=0, le=20000)
    duration: float | None = Field(default=None, gt=0, le=86400)
    preview_url: str = Field(max_length=2000)
    download_url: str = Field(max_length=2000)
    query_used: str = Field(max_length=300)
    description: str = Field(default='', max_length=1000)
    source_metadata: dict = Field(default_factory=dict)


def normalized_media(value):
    try:
        media = Media.model_validate(value).model_dump()
        if media['media_type'] == 'video' and media['duration'] is None:
            raise ValueError()
        return media
    except (ValidationError, ValueError):
        raise StockError('invalid_response', 'Stok sağlayıcısı geçerli medya bilgisi döndürmedi.', 502) from None


def make_slots(scene):
    """Keep semantic scenes intact; choose visual beats near narration boundaries."""
    start, end = float(scene['start_estimate']), float(scene['end_estimate'])
    duration = end-start
    count = max(1, math.ceil(duration/8))
    # Sentence / deterministic narration-unit boundaries influence visual timing.
    units = narration_units(scene['narration_text'])
    total = word_count(scene['narration_text'])
    cumulative = 0
    boundaries = []
    for unit in units[:-1]:
        cumulative += word_count(unit['text'])
        boundaries.append(start + duration*cumulative/max(1, total))
    cuts = [start]
    for index in range(1, count):
        ideal = start + duration*index/count
        useful = [b for b in boundaries if b > cuts[-1]+3 and b < end-(count-index)*3
                  and abs(b-ideal) <= 2]
        cuts.append(min(useful, key=lambda b: abs(b-ideal)) if useful else ideal)
    cuts.append(end)
    alternatives = list(dict.fromkeys(scene['alternative_stock_queries']))
    slots = []
    for index, (a, b) in enumerate(zip(cuts, cuts[1:])):
        # Related Part 5 queries give variety without adding person/location facts.
        queries = [scene['primary_stock_query'], *alternatives]
        query = queries[min(index, len(queries)-1)]
        slots.append({'slot_id': uuid4().hex, 'scene_id': scene['scene_id'], 'order': index+1,
                      'estimated_start': round(a, 3), 'estimated_end': round(b, 3),
                      'duration': round(b-a, 3), 'visual_goal': scene['visual_intent'],
                      'search_query': query, 'fallback_queries': [q for q in queries if q != query],
                      'preferred_type': scene['preferred_media_type'], 'composition': scene['composition'],
                      'selected_media': None, 'locked': False, 'status': 'pending',
                      'candidates': [], 'warnings': [], 'message': ''})
    return slots


def identity(media):
    return media['provider'], media['media_type'], media['media_id']


DEFAULT_VIDEO_TOLERANCE = 1.25


def rejection_reason(media, slot, tolerance=DEFAULT_VIDEO_TOLERANCE):
    """Technical gates remain strict; Pixabay video tags are a ranking hint."""
    if media['width'] < 960 or media['height'] < 540:
        return 'resolution'
    if media['media_type'] == 'video':
        # Absolute tolerance also has a proportional cap: tiny clips cannot fill
        # a short slot just because their deficit is less than 1.25 seconds.
        allowed = min(tolerance, slot['duration'] * .2)
        if media['duration'] + allowed + .001 < slot['duration']:
            return 'duration'
    keywords = set(re.findall(r'[a-z]{3,}', media['query_used'].casefold())) - {'the','with','and','for'}
    description = media['description'].casefold()
    if (description and keywords and not any(word in description for word in keywords)
            and not (media['provider']=='pixabay' and media['media_type']=='video')):
        return 'relevance'
    return None


def coverage_warning(media, slot):
    if media and media['media_type']=='video' and media['duration'] < slot['duration']-.05:
        return 'Video yuva süresinden biraz kısa'
    return ''


def score(media, slot, tolerance=DEFAULT_VIDEO_TOLERANCE):
    """Conservative metadata match, never a claim of semantic image recognition."""
    if rejection_reason(media,slot,tolerance):
        return -1
    keywords = set(re.findall(r'[a-z]{3,}', media['query_used'].casefold()))
    keywords -= {'the', 'with', 'and', 'for'}
    description = media['description'].casefold()
    # Search ranking is baseline relevance; matching Pixabay video tags BOOST,
    # rather than acting as a compulsory exact-token intersection.
    relevance = 5 if description and keywords and any(word in description for word in keywords) else 3
    return (relevance + (2 if media['width'] >= media['height'] else 0)
            + (1 if media['height'] >= 1000 else 0) + (2 if media['media_type']=='video' else 0))
