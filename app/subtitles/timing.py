"""Deterministic, language-neutral text weights; these are not forced alignment."""
import re
from app.subtitles.models import SubtitleError, valid_duration


def normalize(text): return ' '.join(text.split())


def words_and_weights(text):
    matches = list(re.finditer(r'\S+', text))
    words = [m.group() for m in matches]
    weights = []
    for index, match in enumerate(matches):
        word = match.group()
        # Primarily spoken characters, plus a modest per-word articulation cost.
        value = max(1, sum(c.isalnum() for c in word)) + 1
        terminal = word.rstrip('"\'”’»)]}')
        if terminal.endswith((',', '，')): value += 1
        elif terminal.endswith((';', ':', '；', '：')): value += 2
        elif terminal.endswith(('.', '?', '!', '…', '。', '？', '！')): value += 3
        following = text[match.end():matches[index + 1].start()] if index + 1 < len(matches) else ''
        if re.search(r'\n\s*\n', following): value += 4
        weights.append(float(value))
    return words, weights, matches


def wrap(words, width=42):
    text = ' '.join(words)
    if len(text) <= width: return text
    candidates = [(abs(len(' '.join(words[:i])) - len(' '.join(words[i:]))), i)
                  for i in range(1, len(words))
                  if len(' '.join(words[:i])) <= width and len(' '.join(words[i:])) <= width]
    if candidates:
        cut = min(candidates)[1]
    else:
        # An indivisible long word may exceed the readability target. Never truncate it.
        cut = min(range(1, len(words)), key=lambda i:abs(len(' '.join(words[:i])) - len(' '.join(words[i:])))) if len(words)>1 else 0
    return '\n'.join((' '.join(words[:cut]), ' '.join(words[cut:]))) if cut else text


def segment(text):
    words, weights, matches = words_and_weights(text)
    if not words: raise SubtitleError('empty_source', 'Onaylı seslendirme metni boş olamaz.')
    ranges = []
    start = 0
    while start < len(words):
        stop = start
        length = 0
        while stop < len(words):
            extra = len(words[stop]) + (1 if stop > start else 0)
            if stop > start and length + extra > 84: break
            length += extra
            stop += 1
        # Prefer a substantial sentence/paragraph, then clause, then word boundary.
        choices = []
        for end in range(start + 1, stop + 1):
            size = len(' '.join(words[start:end]))
            gap = text[matches[end-1].end():matches[end].start()] if end < len(words) else ''
            terminal = words[end-1].rstrip('"\'”’»)]}')
            rank = 4 if re.search(r'\n\s*\n', gap) else 3 if terminal.endswith(('.', '!', '?', '…')) else 2 if terminal.endswith((';', ':')) else 1 if terminal.endswith(',') else 0
            if rank and (size >= 32 or rank == 4): choices.append((rank, end))
        end = max(choices)[1] if choices else stop
        ranges.append((start, end))
        start = end
    # Avoid a tiny trailing cue when the preceding cue has room.
    if len(ranges)>1 and ranges[-1][1]-ranges[-1][0]==1:
        a, b = ranges[-2][0], ranges[-1][1]
        if len(' '.join(words[a:b])) <= 84: ranges[-2:] = [(a, b)]
        elif ranges[-2][1]-ranges[-2][0] >= 3:
            boundary = ranges[-1][0]-1
            ranges[-2:] = [(a, boundary), (boundary, b)]
    return words, weights, ranges


def allocate(weights, duration, minimum=.8):
    # Water-fill a feasible display floor; never add seconds or overflow the audio.
    floor = min(minimum, duration / len(weights))
    pending = set(range(len(weights)))
    result = [0.0] * len(weights)
    remaining = duration
    while pending:
        total = sum(weights[i] for i in pending)
        short = [i for i in pending if remaining * weights[i] / total < floor]
        if not short:
            for i in pending: result[i] = remaining * weights[i] / total
            break
        for i in short:
            result[i] = floor
            remaining -= floor
            pending.remove(i)
    return result


def generate(text, duration):
    if not valid_duration(duration): raise SubtitleError('duration_required', 'Ses süresi ölçülemedi. Yerel ses dosyasını ve Tanılama ekranını kontrol edin.', 409)
    duration = round(duration, 3)
    words, weights, ranges = segment(text)
    # Merge neighboring short cues if even a .8s display floor is infeasible.
    while len(ranges)>1 and len(ranges)*.8 > duration:
        index = min(range(len(ranges)-1), key=lambda i:sum(weights[ranges[i][0]:ranges[i+1][1]]))
        ranges[index:index+2] = [(ranges[index][0], ranges[index+1][1])]
    lengths = allocate([sum(weights[a:b]) for a,b in ranges], duration)
    cues, boundaries = [], [0.0] * (len(words)+1)
    cursor = 0.0
    for index, ((a,b), length) in enumerate(zip(ranges,lengths), 1):
        end = duration if index==len(ranges) else cursor+length
        total = sum(weights[a:b])
        elapsed = cursor
        for word in range(a,b):
            boundaries[word] = round(elapsed, 6)
            elapsed += (end-cursor)*weights[word]/total
        boundaries[b] = round(end, 6)
        cues.append({'index':index, 'start':round(cursor,3), 'end':round(end,3), 'text':wrap(words[a:b])})
        cursor = end
    if any(c['end']<=c['start'] for c in cues):
        raise SubtitleError('duration_required', 'Ses süresi okunabilir altyazı zamanlaması için çok kısa.', 409)
    assert normalize(' '.join(c['text'] for c in cues)) == normalize(text)
    return cues, boundaries


def edited_boundaries(source, cues, previous):
    if normalize(' '.join(c['text'] for c in cues)) != normalize(source): return previous
    _, weights, _ = words_and_weights(source)
    boundaries = [0.0]*(len(weights)+1)
    offset = 0
    for cue in cues:
        count = len(cue['text'].split())
        total = sum(weights[offset:offset+count]); cursor = cue['start']
        for index in range(offset,offset+count):
            boundaries[index] = round(cursor,6)
            cursor += (cue['end']-cue['start'])*weights[index]/total
        offset += count
        boundaries[offset] = cue['end']
    return boundaries


def map_scenes(source, scenes, boundaries, duration):
    source_words = normalize(source).split()
    offset = 0
    result = []
    for scene in scenes:
        words = normalize(scene['narration_text']).split()
        if not words or source_words[offset:offset+len(words)] != words:
            raise SubtitleError('scene_source_mismatch', 'Sahne anlatımı seslendirme kaynağıyla eşleşmiyor. Güncel onaylı sahne planını kontrol edin.', 409)
        start, end = boundaries[offset], boundaries[offset+len(words)]
        result.append({'scene_id':scene['scene_id'], 'narration_text':scene['narration_text'],
                       'start':start, 'end':end, 'duration':round(end-start,6),
                       'estimated_start':scene.get('start_estimate'), 'estimated_end':scene.get('end_estimate'),
                       'timing_source':'approximate_audio_duration'})
        offset += len(words)
    if offset != len(source_words): raise SubtitleError('scene_source_mismatch', 'Sahne planı onaylı anlatımın tamamını kapsamıyor.', 409)
    result[-1]['end'] = duration
    result[-1]['duration'] = round(duration-result[-1]['start'],6)
    return result


def project_slots(scenes, slots):
    result = []
    for scene in scenes:
        group = [s for s in slots if s['scene_id']==scene['scene_id']]
        group.sort(key=lambda s:s['order'])
        if not group: continue
        weights = [s['duration'] for s in group]
        if any(not valid_duration(w) for w in weights):
            raise SubtitleError('stock_timing_invalid', 'Stok yuvalarının tahmini süreleri geçersiz; mevcut dosyalar korundu.',409)
        cursor = scene['start']
        for index, (slot, weight) in enumerate(zip(group, weights)):
            end = scene['end'] if index==len(group)-1 else cursor+scene['duration']*weight/sum(weights)
            media = slot.get('selected_media')
            identity = {k:media.get(k) for k in ('provider','media_id','media_type','local_path')} if media else None
            if identity and (not isinstance(identity['local_path'],str) or not re.fullmatch(r'stock/[a-f0-9]{32}\.(mp4|jpg|png|webp)',identity['local_path'])):
                identity=None  # Never return an unsafe system path, even in an unready handoff.
            result.append({'slot_id':slot['slot_id'], 'scene_id':scene['scene_id'], 'order':slot['order'],
                           'start':round(cursor,6), 'end':round(end,6), 'duration':round(end-cursor,6),
                           'estimated_start':slot['estimated_start'], 'estimated_end':slot['estimated_end'],
                           'locked':slot['locked'], 'status':slot['status'],
                           'selected_media_local_identity':identity, 'timing_source':'approximate_audio_duration',
                           # Director media: a very short slot continuing its neighbour's
                           # take, or a different part of the same long clip.
                           **({'continuation_of':slot['continuation_of']} if slot.get('continuation_of') else {}),
                           **({'segment_start':slot['segment_start']} if slot.get('segment_start') is not None else {}),
                           # Text shown as a band over the continuing video instead of a full-screen card.
                           # Opening scene: the card's 2-5 words over moving footage, at most 4 s.
                           **({'lower_third':slot['lower_third']} if (slot.get('continuation_of') or slot.get('lower_third_seconds')) and isinstance(slot.get('lower_third'),str) and slot['lower_third'].strip() else {}),
                           **({'lower_third_seconds':float(slot['lower_third_seconds'])} if isinstance(slot.get('lower_third_seconds'),(int,float)) and slot['lower_third_seconds']>0 else {}),
                           # [ŞERİT]: two-line band (top / bottom) over this slot's footage.
                           **({'band':{'top':str(slot['band'].get('top') or '')[:60],'bottom':str(slot['band'].get('bottom') or '')[:60]}} if isinstance(slot.get('band'),dict) and slot['band'].get('bottom') else {})})
            cursor=end
    return result
