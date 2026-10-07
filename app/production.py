"""Visual/edit planning and truthful pre-render checks; no rendering or upload."""
import re
import json
from copy import deepcopy
from functools import wraps
from contextlib import closing
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from app.projects import now
from app.scripts.models import ScriptError, word_count
from app.scripts.storage import dumps

MEDIA_PRIORITY = ['pexels', 'pixabay', 'local', 'cloud_with_permission']
MAX_SCENE_SECONDS = 18
EDIT_OPTIONS = {'transition':{'hard_cut','crossfade','fade','none'},
                'motion':{'none','slow_zoom','pan','ken_burns','overlay','emphasis_text'},
                'composition':{'wide','medium','close','detail','person','object','environment','movement','graphic'}}
SCENE_ERRORS = {
    'narration_units_missing': 'AI bazı senaryo parçalarını sahnelere atamadı.',
    'narration_units_duplicate': 'AI aynı senaryo parçasını birden fazla sahnede kullandı.',
    'narration_units_out_of_order': 'AI sahne sırasını değiştirdi; parçalar kaynak sırasıyla ve bitişik kullanılmalı.',
    'invalid_scene_schema': 'AI sahne alanlarını beklenen JSON biçiminde döndürmedi.',
    'invalid_stock_queries': 'AI stok arama sorgularını beklenen biçimde döndürmedi.',
    'invalid_overlay': 'AI vurgu yazısını beklenen kısa biçimde döndürmedi.',
    'invalid_media_type': 'AI geçerli bir medya türü döndürmedi.',
    'invalid_transition': 'AI geçerli bir geçiş veya hareket önerisi döndürmedi.',
    'invalid_composition': 'AI geçerli bir kompozisyon döndürmedi.',
}
SCENE_METADATA_ERRORS = {key for key in SCENE_ERRORS if key.startswith('invalid_')}
SCENE_FIELDS = {'purpose':'amaç','mood':'duygu','visual_intent':'görsel niyet','stock_query':'birincil stok sorgusu',
                'alternative_stock_queries':'alternatif stok sorguları','media_type':'medya türü',
                'unit_ids':'senaryo parçası kimlikleri','scenes':'sahneler','json':'JSON',
                'narration':'kaynak anlatım'}
MEDIA_ALIASES = {'video':'stock_video','stock video':'stock_video','image':'stock_image',
                 'stock image':'stock_image','ai image':'ai_image','motion graphic':'motion_graphic','user media':'user_media'}


def scene_error(category, field=None, *, missing=False):
    field = field if isinstance(field,str) and field in SCENE_FIELDS else None
    message=SCENE_ERRORS[category]
    if field:
        state='eksik' if missing else 'eksik veya geçersiz'
        message=f"AI sahne planında '{SCENE_FIELDS[field]}' alanını {state} döndürdü."
    error=ScriptError(message,category=category)
    error.field=field
    error.diagnostic=f'{category}:{field}' if field else category
    return error


def editable(method):
    @wraps(method)
    def wrapped(self, project_id, *args, **kwargs):
        with self.projects.lock, closing(self.projects._connection()) as connection:
            self.repo._idle(connection, project_id)
            return method(self, project_id, *args, **kwargs)
    return wrapped


class VisualBlock(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    narration: str = Field(min_length=1, max_length=12000)
    purpose: str = Field(min_length=1, max_length=1000)
    mood: str = Field(min_length=1, max_length=100)
    visual_intent: str = Field(min_length=1, max_length=1500)
    stock_query: str = Field(min_length=3, max_length=300)
    alternative_stock_queries: list[str] = Field(min_length=1, max_length=5)
    media_type: Literal['stock_video', 'stock_image', 'ai_image', 'motion_graphic', 'user_media']
    overlay_text: str = Field(default='', max_length=150)
    transition: Literal['hard_cut', 'crossfade', 'fade', 'none'] = 'none'
    motion: Literal['none', 'slow_zoom', 'pan', 'ken_burns', 'overlay', 'emphasis_text'] = 'none'
    composition: Literal['wide', 'medium', 'close', 'detail', 'person', 'object', 'environment', 'movement', 'graphic'] = 'medium'
    importance: int = Field(default=50, ge=0, le=100)
    entities: list[str] = Field(default_factory=list, max_length=20)
    location: str = Field(default='', max_length=300)
    action: str = Field(default='', max_length=300)
    shot_suggestion: str = Field(default='', max_length=500)
    notes: str = Field(default='', max_length=1500)

    @model_validator(mode='after')
    def semantic_queries(self):
        for field in ('narration','purpose','mood','visual_intent'):
            if not getattr(self,field).strip():
                raise PydanticCustomError('invalid_scene_schema', 'Anlatım, amaç, duygu ve görsel niyet boş olamaz.', {'field':field})
        if not any(char.isalpha() for char in self.visual_intent) or self.visual_intent.strip().casefold() in ('none','null','n/a','unknown','tbd','yok','belirtilmedi'):
            raise PydanticCustomError('invalid_scene_schema', 'Kullanılabilir bir görsel niyet gerekli.', {'field':'visual_intent'})
        queries = [self.stock_query, *self.alternative_stock_queries]
        for index,query in enumerate(queries):
            if not 2 <= len(query.split()) <= 12 or len(query) > 300 or re.search(r'[.!?;\n]',query):
                raise PydanticCustomError('invalid_stock_queries', 'Anlamsal stok sorgusu birden fazla anlamlı kelime içermeli.', {'field':'stock_query' if index==0 else 'alternative_stock_queries'})
        if len({normalize(query).casefold() for query in queries}) != len(queries):
            raise PydanticCustomError('invalid_stock_queries', 'Aynı sahnenin stok sorguları farklı olmalı.', {'field':'alternative_stock_queries'})
        if any(not entity.strip() or len(entity)>150 for entity in self.entities):
            raise ValueError('Varlık alanlarını kontrol edin.')
        if word_count(self.overlay_text)>12 or self.overlay_text and normalize(self.overlay_text)==normalize(self.narration):
            raise PydanticCustomError('invalid_overlay', 'Vurgu yazısı kısa olmalı; tüm anlatımı tekrarlamamalı.')
        return self


class NarrationTiming(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=12000)
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode='after')
    def range(self):
        if self.end <= self.start: raise ValueError('Zaman aralığı geçersiz.')
        return self


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip()


def normalized_query(value):
    if not isinstance(value,str) or re.search(r'\n\s*\n',value): return None
    query=normalize(value).rstrip('.,!?;:…。！？').rstrip()
    if not 2<=len(query.split())<=12 or len(query)>300 or re.search(r'[.!?;\n]',query): return None
    if sum(bool(re.search(r'[^\W\d_]',word)) for word in query.split())<2: return None
    return query


def scene_metadata(scene, narration):
    """Strict semantic core, followed by non-factual editing defaults/sanitization."""
    query=normalized_query(scene.get('stock_query'))
    if query is None: raise scene_error('invalid_stock_queries','stock_query',missing='stock_query' not in scene)
    alternatives=scene.get('alternative_stock_queries')
    if not isinstance(alternatives,list):
        raise scene_error('invalid_stock_queries','alternative_stock_queries',missing='alternative_stock_queries' not in scene)
    cleaned=[normalized_query(value) for value in alternatives]
    valid=[value for value in cleaned if value is not None]
    if not valid: raise scene_error('invalid_stock_queries','alternative_stock_queries')
    if len({query.casefold(),*(value.casefold() for value in valid)})!=len(valid)+1:
        raise scene_error('invalid_stock_queries','alternative_stock_queries')
    media=scene.get('media_type','stock_video')
    if not isinstance(media,str): raise scene_error('invalid_media_type','media_type')
    media=media.strip().casefold();media=MEDIA_ALIASES.get(media,media)
    core={key:scene[key] for key in ('purpose','mood','visual_intent') if key in scene}
    core.update(narration=narration,stock_query=query,alternative_stock_queries=valid[:5],media_type=media)
    try: block=VisualBlock.model_validate(core).model_dump()
    except ValidationError as error:
        detail=error.errors()[0]
        field=detail.get('ctx',{}).get('field') or (detail['loc'][0] if detail['loc'] else None)
        category=detail['type'] if detail['type'] in SCENE_METADATA_ERRORS else {'stock_query':'invalid_stock_queries',
                 'alternative_stock_queries':'invalid_stock_queries','media_type':'invalid_media_type'}.get(field,'invalid_scene_schema')
        raise scene_error(category,field,missing=detail['type']=='missing') from None
    warnings=[]
    if len(valid)!=len(alternatives) or len(valid)>5:
        warnings.append('Kullanılamayan veya fazla alternatif sorgular çıkarıldı; geçerli sorgular korundu.')
    text_limits={'overlay_text':150,'location':300,'action':300,'shot_suggestion':500,'notes':1500}
    labels={'overlay_text':'Vurgu yazısı','location':'Konum','action':'Eylem','shot_suggestion':'Çekim önerisi',
            'notes':'Notlar','entities':'Özneler','importance':'Önem','transition':'Geçiş','motion':'Hareket','composition':'Kompozisyon'}
    for field,limit in text_limits.items():
        if field not in scene: continue
        value=scene[field]
        usable=isinstance(value,str) and len(value)<=limit
        if field=='overlay_text' and usable:
            usable=word_count(value)<=12 and (not value.strip() or normalize(value)!=normalize(narration))
        if usable: block[field]=value
        else: warnings.append(labels[field]+' alanı kullanılamadı; boş bırakıldı. Plan geçerli.')
    if 'entities' in scene:
        value=scene['entities']
        valid_entities=[item for item in value if isinstance(item,str) and item.strip() and len(item)<=150][:20] if isinstance(value,list) else []
        block['entities']=valid_entities
        if valid_entities!=value: warnings.append('Özneler alanındaki geçersiz değerler çıkarıldı. Yeni kişi/varlık eklenmedi.')
    defaults=[]
    for field,choices in EDIT_OPTIONS.items():
        if not isinstance(scene.get(field),str) or scene[field] not in choices: defaults.append(field)
        if field not in scene: continue
        value=scene[field]
        if isinstance(value,str) and value in choices: block[field]=value
        else: warnings.append(labels[field]+' önerisi kullanılamadı; güvenli varsayılan kullanıldı.')
    if 'importance' in scene:
        value=scene['importance']
        if type(value) is int and 0<=value<=100: block['importance']=value
        else: warnings.append('Önem puanı kullanılamadı; güvenli varsayılan 50 kullanıldı.')
    allowed=set(VisualBlock.model_fields)|{'unit_ids','narration_text'}
    if set(scene)-allowed: warnings.append('Ek sahne alanları kullanılmadı.')
    block['metadata_warnings']=warnings
    block['_editing_defaults']=defaults  # Consumed locally before blocks are persisted.
    return block


def narration_units(text, words_per_minute=135, *, prefix='U'):
    """Lossless sentence/paragraph units; long sentences use punctuation only."""
    if not isinstance(text, str) or not text.strip():
        raise scene_error('narration_units_missing')
    sentence_boundary = r'[.!?。！？]+["”’\)\]]*\s+|\r?\n[ \t]*\r?\n'
    pieces, start = [], 0
    for match in re.finditer(sentence_boundary, text):
        end = match.end()
        if text[start:end].strip():
            pieces.append(text[start:end]); start = end
    if start < len(text):
        if text[start:].strip(): pieces.append(text[start:])
        elif pieces: pieces[-1] += text[start:]
    exact = []
    for piece in pieces:
        if word_count(piece) / words_per_minute * 60 <= MAX_SCENE_SECONDS:
            exact.append(piece); continue
        # No arbitrary word/time cuts, even for a huge sentence without punctuation.
        start = 0
        for match in re.finditer(r'[,;:—]["”’\)\]]*\s+', piece):
            end = match.end()
            if piece[start:end].strip() and piece[end:].strip():
                exact.append(piece[start:end]); start = end
        exact.append(piece[start:])
    return [{'unit_id':f'{prefix}{index+1}', 'text':piece, 'order':index+1} for index,piece in enumerate(exact)]


def narration_segments(text, words_per_minute=135, limit=600):
    """Bound API context at unit boundaries without losing any source characters."""
    segments, pending, count = [], [], 0
    for unit in narration_units(text, words_per_minute):
        size = word_count(unit['text'])
        if pending and count + size > limit:
            segments.append({'text':''.join(item['text'] for item in pending)}); pending=[]; count=0
        pending.append(unit); count += size
    if pending: segments.append({'text':''.join(item['text'] for item in pending)})
    return segments


def exact_source_slices(texts, source):
    """Align legacy whitespace-normalized block/segment boundaries to exact source."""
    tokens = list(re.finditer(r'\S+', source))
    if normalize(' '.join(texts)) != normalize(source):
        raise scene_error('narration_units_missing')
    result, offset, count = [], 0, 0
    for text in texts:
        count += len(text.split())
        end = tokens[count].start() if count < len(tokens) else len(source)
        result.append(source[offset:end]); offset = end
    return result


def scene_references(raw, units):
    """Validate references before metadata; flattened order implies contiguity."""
    if not isinstance(raw,dict) or not isinstance(raw.get('scenes'),list) or not 1 <= len(raw['scenes']) <= 200:
        raise scene_error('invalid_scene_schema')
    groups = []
    for scene in raw['scenes']:
        if not isinstance(scene,dict) or not isinstance(scene.get('unit_ids'),list) or not scene['unit_ids']:
            raise scene_error('narration_units_missing')
        if any(not isinstance(uid,str) for uid in scene['unit_ids']):
            raise scene_error('invalid_scene_schema')
        groups.append(scene['unit_ids'])
    expected = [unit['unit_id'] for unit in units]
    expected_set = set(expected)
    actual = [uid for group in groups for uid in group]
    if any(uid not in expected_set for uid in actual): raise scene_error('narration_units_missing')
    if len(set(actual)) != len(actual): raise scene_error('narration_units_duplicate')
    if set(actual) != set(expected): raise scene_error('narration_units_missing')
    if actual != expected: raise scene_error('narration_units_out_of_order')
    return groups


def compatible_compositions(block):
    """Camera suggestions only, using existing intent; never infer people/places."""
    intent=normalize(block['visual_intent']).casefold()
    if re.search(r'\b(detail|macro|close.?up|close (?:shot|view|framing)|nahaufnahme|detay|makro)\b|yakın plan',intent):
        return ['detail','close']
    if re.search(r'\bwide (?:establishing )?shot\b|geniş plan',intent): return ['wide']
    if re.search(r'\bmedium shot\b|orta plan',intent): return ['medium']
    if re.search(r'\b(chart|diagram|infographic|graph|graphic|map|karte|grafik|harita|diagramm)\b',intent):
        return ['graphic','detail','wide']
    if re.search(r'\b(landscape|habitat|forest|environment|skyline|wald|orman|manzara)\b',intent):
        return ['environment','wide','medium','detail']
    choices=['medium','wide','close']
    if re.search(r'\b(car|vehicle|charging|product|tool|computer|object|auto|fahrzeug|nesne|ürün)\b',intent):
        choices+=['detail','object']
    if block['media_type']=='stock_video' and re.search(r'\b(driving|running|walking|flying|movement|motion|fahren|laufen|hareket)\b',intent):
        choices.append('movement')
    return choices


def paced_unit_groups(ids, source_by_id, rate, *, opening=False, coarse=False):
    """Keep AI semantic groups, subdividing only on existing source-unit edges."""
    sizes=[word_count(source_by_id[uid])/rate*60 for uid in ids]
    if sum(sizes)<=MAX_SCENE_SECONDS and not coarse: return [ids]
    groups=[];offset=0
    while offset<len(ids):
        remaining=sum(sizes[offset:])
        target=5 if opening and not groups else 10
        if remaining<=12 or offset==len(ids)-1:
            groups.append(ids[offset:]);break
        duration=0;candidates=[]
        for end in range(offset,len(ids)-1):
            duration+=sizes[end]
            if duration>MAX_SCENE_SECONDS: break
            tail=remaining-duration
            # Avoid a tiny tail when the whole remainder already fits safely.
            if duration>=3 and tail>=3:
                candidates.append((abs(duration-target),end+1))
        if candidates:
            end=min(candidates)[1]
        elif remaining<=MAX_SCENE_SECONDS:
            groups.append(ids[offset:]);break
        else:
            # An indivisible overlong unit is isolated, never cut through words.
            end=offset+1
        groups.append(ids[offset:end]);offset=end
    return groups


def varied_query(block, used):
    """Reuse supplied alternatives, then add only non-factual camera framing."""
    original=[block['stock_query'],*block['alternative_stock_queries']]
    candidates=list(original)
    frames={'wide':'wide view','medium':'medium shot','close':'close up','detail':'detail view',
            'environment':'wide view','object':'object detail','movement':'action view','graphic':'detail view'}
    frame=frames.get(block['composition'],'medium shot')
    for query in original:
        variant=normalized_query(query+' '+frame)
        if variant is not None: candidates.append(variant)
    selected=next((query for query in candidates if query.casefold() not in used),original[0])
    block['stock_query']=selected
    block['alternative_stock_queries']=list(dict.fromkeys(query for query in original if query.casefold()!=selected.casefold()))[:5]


def refine_scene_metadata(blocks, groups, source_by_id, rate, start, *, previous=None, single=False):
    """Cost-free quality gate after critical validation, before timing/save."""
    previous=previous or []
    used={normalize(b['stock_query']).casefold() for b in previous}
    last=previous[-1]['composition'] if previous else None
    elapsed=start;result=[]
    total=sum(word_count(b['narration'])/rate*60 for b in blocks)
    coarse=total>=30 and total/len(blocks)>15
    for block,ids in zip(blocks,groups):
        defaults=block.pop('_editing_defaults')
        parts=[ids] if single else paced_unit_groups(ids,source_by_id,rate,opening=elapsed==0,coarse=coarse)
        for index,part in enumerate(parts):
            child=deepcopy(block);child['narration']=''.join(source_by_id[uid] for uid in part)
            duration=word_count(child['narration'])/rate*60
            choices=compatible_compositions(child)
            if 'composition' in defaults or index:
                order=len(previous)+len(result)
                choice=choices[order%len(choices)]
                if choice==last: choice=choices[(order+1)%len(choices)]
                child['composition']=choice
            if index: child['overlay_text']=''  # Do not repeat the same caption on every subdivision.
            if 'motion' in defaults and child['media_type'] in ('stock_image','ai_image'):
                child['motion']='slow_zoom' if len(result)%2==0 else 'pan'
            if index or normalize(child['stock_query']).casefold() in used:
                varied_query(child,used)
            if duration>MAX_SCENE_SECONDS:
                child['pacing_reason']='Tek sahne yenilemesi anlatım sınırlarını korur; bölmek için tüm planı yeniden hazırlayın.' if single else 'Bu anlatım biriminde güvenli cümle/ifade sınırı yok; kelimeler bölünmedi.'
            result.append(child);elapsed+=duration;last=child['composition'];used.add(normalize(child['stock_query']).casefold())
    return result


def enrich_blocks(blocks):
    """Extend the existing block contract; original fields stay authoritative."""
    for index, block in enumerate(blocks):
        block.setdefault('id', uuid4().hex)
        block.update(scene_id=block['id'], order=index+1, narration_text=block['narration'],
                     preferred_media_type=block['media_type'], primary_stock_query=block['stock_query'])
        for key, default in {'entities':[], 'location':'', 'action':'', 'shot_suggestion':'', 'notes':'', 'locked':False}.items():
            block.setdefault(key, deepcopy(default))
        block.setdefault('estimated_duration', round(block['end']-block['start'],3))
        block.setdefault('start_estimate', block['start'])
        block.setdefault('end_estimate', block['end'])
    return blocks


def coverage(blocks, text):
    return normalize(' '.join(block.get('narration','') for block in blocks)) == normalize(text)


def scene_checks(blocks, text):
    warnings = []
    if not coverage(blocks,text): warnings.append('Sahne anlatımı onaylı senaryoyu tam ve aynı sırayla kapsamıyor.')
    if not blocks: return warnings + ['Plan içinde sahne yok.']
    total_duration=sum(b.get('estimated_duration',b['end']-b['start']) for b in blocks)
    if total_duration>=30 and total_duration/len(blocks)>15:
        warnings.append('Bu uzunluktaki senaryo için çok az sahne var; anlamlı görsel geçişleri inceleyin.')
    queries, concept_run, image_run = set(), 0, 0
    for index, block in enumerate(blocks):
        label=f'Sahne {index+1}: '
        warnings.extend(label+message for message in block.get('metadata_warnings',[]))
        duration=block.get('estimated_duration',block['end']-block['start'])
        if duration<2: warnings.append(label+'çok kısa; yararlı bir görsel fikir oluşturduğunu kontrol edin.')
        if duration>MAX_SCENE_SECONDS:
            reason='Kilitli sahne kullanıcı tercihiyle aynen korundu.' if block.get('locked') else block.get('pacing_reason','Uygun cümle/anlam sınırlarında bölmeyi değerlendirin.')
            warnings.append(label+'çok uzun; '+reason)
        query=normalize(block['stock_query']).casefold()
        if query in queries: warnings.append(label+'stok sorgusu başka bir sahnede tekrarlanıyor.')
        queries.add(query)
        image_run=image_run+1 if block['media_type'] in ('stock_image','ai_image') and block['motion']=='none' else 0
        if image_run==4: warnings.append('Arka arkaya çok fazla sabit görsel var; ilgili video veya hareket önerilerini inceleyin.')
        if index>=2 and len({item['composition'] for item in blocks[index-2:index+1]})==1:
            warnings.append(label+'benzer kompozisyon arka arkaya geliyor.')
        if index and normalize(block['visual_intent']).casefold()==normalize(blocks[index-1]['visual_intent']).casefold():
            concept_run+=1
            if concept_run==2: warnings.append(label+'aynı görsel fikir tekrarlanıyor; konuyla ilgili çeşitlilik sağlayın.')
        else: concept_run=0
        if index>=2 and block.get('location') and all(item.get('location')==block['location'] for item in blocks[index-2:index+1]):
            warnings.append(label+'aynı konum art arda kullanılıyor; bağlam uygunsa farklı açıları değerlendirin.')
        if index>=2 and block.get('entities') and all(item.get('entities')==block['entities'] for item in blocks[index-2:index+1]):
            warnings.append(label+'aynı kişi/özne art arda kullanılıyor; bağlama uygun çeşitlilik kontrolü yapın.')
    if len(blocks)>=3 and len({b['composition'] for b in blocks})==1:
        warnings.append('Plan boyunca kompozisyon değişmiyor; bağlama uygun çeşitlilik kontrolü yapın.')
    return list(dict.fromkeys(warnings))


def visual_blocks(raw, source, language, words_per_minute, start=0, *, units=None, single=False, previous=None):
    units = units if units is not None else narration_units(source,words_per_minute)
    if ''.join(unit['text'] for unit in units) != source: raise scene_error('narration_units_missing')
    groups = scene_references(raw,units)
    if set(raw) != {'scenes'} or single and len(groups)!=1: raise scene_error('invalid_scene_schema','scenes')
    source_by_id = {unit['unit_id']:unit['text'] for unit in units}
    blocks=[scene_metadata(scene,''.join(source_by_id[uid] for uid in ids)) for scene,ids in zip(raw['scenes'],groups)]
    blocks=refine_scene_metadata(blocks,groups,source_by_id,words_per_minute,start,previous=previous,single=single)
    if ''.join(block['narration'] for block in blocks) != source:
        raise scene_error('narration_units_missing')
    for index, block in enumerate(blocks):
        duration = word_count(block['narration']) / words_per_minute * 60
        block_id = uuid4().hex
        block.update(id=block_id, scene_id=block_id, order=index+1,
                     language=language, overlay_language=language, stock_query_language='en', timing_source='estimated',
                     start=round(start, 3), end=round(start+duration, 3), estimated_duration=round(duration,3),
                     locked=False, media=None, image_status='prepared')
        start += duration
    return blocks


def production_checks(plan, current, project):
    warnings = []
    if not current or current['status'] != 'approved': warnings.append('Geçerli senaryo onaylanmamış.')
    if current:
        from app.scripts.engine import repetition_warnings
        warnings.extend(repetition_warnings(current.get('text', '')))
    if not plan: return warnings + ['Görsel plan henüz oluşturulmadı.', 'Seslendirme ve render sonraki çalıştırma aşaması için hazırlanıyor.']
    if not current or plan['version_id'] != current['id']: warnings.append('Görsel plan eski senaryo sürümüne ait. Yeniden planlayın.')
    blocks = plan['blocks']
    if current and current.get('text'): warnings.extend(scene_checks(blocks,current['text']))
    ids, image_run = set(), 0
    for index, block in enumerate(blocks):
        prefix = f'Görsel blok {index+1}: '
        if not block['narration'].strip(): warnings.append(prefix + 'anlatım boş.')
        if not block.get('media'): warnings.append(prefix + 'medya henüz atanmadı.')
        else:
            media = block['media']; identity = (media['provider'], media['media_id'])
            if identity in ids: warnings.append(prefix + 'aynı medya tekrar kullanılıyor.')
            ids.add(identity)
            if (media.get('width'), media.get('height')) != (plan['width'], plan['height']): warnings.append(prefix + 'çözünürlük hedefle eşleşmiyor; uyarlama gerekli.')
            if not media.get('available', False): warnings.append(prefix + 'medya dosyası henüz doğrulanmadı.')
        if block['end'] - block['start'] > MAX_SCENE_SECONDS: warnings.append(prefix + 'görsel uzun sürüyor; cümle sonlarında çeşitlendirin.')
        if block['language'] != plan['language'] or block['overlay_language'] != plan['language']: warnings.append(prefix + 'dil eşleşmiyor.')
        if block.get('image_status') == 'error': warnings.append(prefix + 'görsel üretimi başarısız.')
        image_run = image_run+1 if block['media_type'] in ('stock_image', 'ai_image') and block['motion']=='none' else 0
        if image_run == 4: warnings.append('Arka arkaya çok fazla sabit görsel var; ilgili video veya hareket önerilerini inceleyin.')
        if index >= 2 and len({item['composition'] for item in blocks[index-2:index+1]}) == 1: warnings.append(prefix + 'benzer kompozisyon arka arkaya geliyor.')
    if not plan.get('voice'): warnings.append('Seslendirme dosyası eksik; TTS çalıştırması daha sonra.')
    if project['subtitles_enabled'] and not plan.get('subtitles'): warnings.append('Altyazı/timing henüz yok; üretim daha sonra.')
    if project['subtitles_enabled'] and plan.get('subtitles') and plan['subtitles'].get('language') != plan['language']: warnings.append('Altyazı dili hedef dille eşleşmiyor.')
    music = plan['music']
    if music['enabled'] and not music['local_file_label']: warnings.append('Müzik açık ancak lisanslı yerel müzik seçilmedi.')
    if music['enabled']: warnings.append('Müzik dosyası henüz içe aktarılmadı veya doğrulanmadı; dosya işleme daha sonra.')
    if music['enabled'] and not music['license_confirmed']: warnings.append('Müzik kullanım lisansı onaylanmamış.')
    if music['enabled'] and music['volume'] > .3: warnings.append('Müzik seslendirmeyi bastırabilir; ses seviyesini azaltın.')
    return list(dict.fromkeys(warnings))


class ProductionService:
    def __init__(self, scripts):
        self.scripts, self.repo, self.projects = scripts, scripts.repository, scripts.projects

    def view(self, project_id):
        with self.projects.lock:
            return self._view(project_id)

    def _view(self, project_id):
        project = self.projects.get(project_id)
        current = self.repo.view(project_id)['current']
        with closing(self.projects._connection()) as connection:
            row = connection.execute('SELECT * FROM project_production WHERE project_id=?', (project_id,)).fetchone()
            history = connection.execute('SELECT * FROM scene_plan_versions WHERE project_id=? ORDER BY version DESC',(project_id,)).fetchall()
        plan = json.loads(row['plan_json']) if row else None
        def status(source_id,language):
            if not current or current['id']!=source_id or language!=project['language']: return 'outdated'
            return 'ready' if current['status']=='approved' else 'approval_required'
        if plan:
            enrich_blocks(plan['blocks'])
            plan['status']=status(plan['version_id'],plan['language'])
        versions = [{'plan_id':item['id'],'plan_version':item['version'],'version_id':item['version_id'],
                     'provider':item['provider'],'model':item['model'],'created_at':item['created_at'],
                     'scene_count':len(json.loads(item['plan_json'])['blocks']),
                     'status':status(item['version_id'],json.loads(item['plan_json'])['language']),
                     'active':bool(plan and plan['plan_id']==item['id'])} for item in history]
        state = 'Plan hazır — çalıştırma daha sonra' if plan else 'Plan henüz hazırlanmadı'
        if plan and plan['status']!='ready': state='Plan eski veya senaryo onaysız. Yeni onaylı senaryodan plan hazırlayın.'
        warnings=production_checks(plan,current,project)
        if not current or current['status']!='approved': warnings.insert(0,'Önce senaryo sürümünü onaylayın.')
        return {'state': state, 'plan': plan, 'versions':versions, 'approved_script':bool(current and current['status']=='approved'),
                'warnings':list(dict.fromkeys(warnings)), 'scene_warnings':scene_checks(plan['blocks'],current['text']) if plan and current else [],
                'coverage_complete':bool(plan and current and plan['version_id']==current['id'] and coverage(plan['blocks'],current['text'])),
                'media_priority': MEDIA_PRIORITY, 'render_available': False, 'upload_available': False}

    def require_approved(self, project_id):
        current=self.repo.view(project_id)['current']
        if not current or current['status']!='approved': raise ScriptError('Önce senaryo sürümünü onaylayın.',409)
        return current

    def snapshot(self, project_id):
        plan=self.view(project_id)['plan']
        return {'plan_id':plan['plan_id'],'revision':plan['revision']} if plan else None

    def check_snapshot(self, project_id, snapshot):
        if self.snapshot(project_id)!=snapshot: raise ScriptError('Plan değişti. Sayfayı yenileyip bu plan için yeniden deneyin.',409)

    def planning_segments(self, project_id, current):
        rate=(current['options']['words_per_minute_min']+current['options']['words_per_minute_max'])/2
        existing=self.view(project_id)['plan']
        if not existing or existing['version_id']!=current['id'] or not any(b['locked'] for b in existing['blocks']):
            segments=narration_segments(current['text'],rate)
        else:
            if not coverage(existing['blocks'],current['text']): raise ScriptError('Kilitli plan anlatımı senaryoyla eşleşmiyor. Önce sahne kapsamını kontrol edin.',409)
            segments, pending=[],[]
            def flush():
                if pending: segments.extend(narration_segments(''.join(pending),rate))
                pending.clear()
            exact=exact_source_slices([b['narration'] for b in existing['blocks']],current['text'])
            for block,text in zip(existing['blocks'],exact):
                if block['locked']:
                    flush(); segments.append({'text':block['narration'],'locked_block':deepcopy(block)})
                else: pending.append(text)
            flush()
        for index,segment in enumerate(segments):
            if not segment.get('locked_block'):
                segment['narration_units']=narration_units(segment['text'],rate,prefix=f'S{index+1}U')
        return segments

    def retime(self, plan, options, *, preserve_locked=False):
        rate=(options['words_per_minute_min']+options['words_per_minute_max'])/2
        count=0
        for block in plan['blocks']:
            start=count/rate*60
            count+=word_count(block['narration'])
            end=count/rate*60
            if preserve_locked and block.get('locked'): continue
            block.update(start=round(start,3),end=round(end,3),start_estimate=round(start,3),end_estimate=round(end,3),
                         estimated_duration=round(end-start,3),timing_source='estimated')
        plan.update(timing_source='estimated',speech_rate_min=options['words_per_minute_min'],speech_rate_max=options['words_per_minute_max'])
        enrich_blocks(plan['blocks'])
        sources={b['timing_source'] for b in plan['blocks']}
        if sources: plan['timing_source']=next(iter(sources)) if len(sources)==1 else 'mixed'

    def save_generated(self, project_id, version_id, language, blocks, confirmed=False, *, provider='legacy', model='', job_id=None, snapshot=None):
        with self.projects.lock:
            if job_id:
                with closing(self.projects._connection()) as connection:
                    saved=connection.execute('SELECT plan_json FROM scene_plan_versions WHERE origin_job_id=? AND project_id=?',(job_id,project_id)).fetchone()
                if saved:
                    plan=json.loads(saved['plan_json'])
                    self._mirror(project_id,plan,active=self.view(project_id)['plan']['plan_id']==plan['plan_id'])
                    return plan  # Exactly once; repair failed JSON mirrors without another API call.
            current=self.require_approved(project_id)
            if current['id']!=version_id or language!=self.projects.get(project_id)['language']:
                raise ScriptError('Onaylı senaryo veya proje dili değişti; yeni sürüm için plan hazırlayın.',409)
            if snapshot is not None: self.check_snapshot(project_id,snapshot)
            return self._save_generated(project_id,current,language,blocks,confirmed,provider,model,job_id)

    def _save_generated(self, project_id, current, language, blocks, confirmed, provider, model, job_id):
        existing = self.view(project_id)['plan']
        if existing and not confirmed: raise ScriptError('Mevcut görsel plan korunuyor. Yenisiyle değiştirmek için açık onay verin.', 409)
        if not coverage(blocks,current['text']): raise ScriptError('Sahne anlatımı onaylı senaryoyu tam ve aynı sırayla kapsamıyor.',422)
        image_config = self.scripts.settings.image_config()
        plan = {'version_id': current['id'], 'source_script_version':current['version'], 'language': language,
                'provider':provider,'model':model,'status':'ready','width': image_config['width'], 'height': image_config['height'], 'blocks': deepcopy(blocks),
                'media_priority': MEDIA_PRIORITY, 'timing_source': 'estimated', 'voice': None, 'subtitles': None,
                'music': {'enabled': self.projects.get(project_id)['background_music_enabled'], 'mood': 'neutral', 'local_file_label': '', 'license_confirmed': False, 'volume': .15, 'fade_in': 2., 'fade_out': 3., 'ducking': True, 'section_changes': []}}
        if existing: plan['music']=deepcopy(existing['music'])
        self.retime(plan,current['options'],preserve_locked=True)
        self._save(project_id, plan, new_version=True,job_id=job_id)
        return plan

    def save_scene_generated(self, project_id, inputs, block, provider, model, job_id):
        with self.projects.lock:
            with closing(self.projects._connection()) as connection:
                saved=connection.execute('SELECT plan_json FROM scene_plan_versions WHERE origin_job_id=? AND project_id=?',(job_id,project_id)).fetchone()
            if saved:
                plan=json.loads(saved['plan_json'])
                self._mirror(project_id,plan,active=self.view(project_id)['plan']['plan_id']==plan['plan_id'])
                return plan
            current=self.require_approved(project_id)
            if current['id']!=inputs['version_id']: raise ScriptError('Onaylı senaryo değişti; sahneyi güncel planda yeniden seçin.',409)
            if inputs['base_plan']['language']!=self.projects.get(project_id)['language']:
                raise ScriptError('Proje dili değişti; yeni dil için plan hazırlayın.',409)
            self.check_snapshot(project_id,inputs['plan_snapshot'])
            plan=deepcopy(inputs['base_plan']);target=self._scene(plan,inputs['scene_id'])
            if target['locked']: raise ScriptError('Önce sahnenin kilidini açın.',409)
            if normalize(block['narration'])!=normalize(target['narration']): raise ScriptError('Tek sahne planlaması anlatımı değiştiremez.',422)
            fields=('visual_intent','stock_query','alternative_stock_queries','media_type','overlay_text',
                    'transition','motion','composition','shot_suggestion','notes')
            target.update({key:block[key] for key in fields})
            target['metadata_warnings']=block.get('metadata_warnings',[])
            target.update(media=None,image_status='prepared')
            plan.update(provider=provider,model=model)
            self._save(project_id,plan,new_version=True,job_id=job_id)
            return plan

    def _save(self, project_id, plan, *, new_version=False, job_id=None):
        from app.scripts.engine import SecretGuard
        SecretGuard(self.scripts.settings.secret_values()).validate(plan)
        enrich_blocks(plan['blocks'])
        with self.projects.lock, closing(self.projects._connection()) as connection, connection:
            stamp=now()
            if new_version:
                number=connection.execute('SELECT COALESCE(MAX(version),0)+1 FROM scene_plan_versions WHERE project_id=?',(project_id,)).fetchone()[0]
                plan.update(plan_id=uuid4().hex,plan_version=number,revision=1,created_at=stamp,status='ready')
                connection.execute('INSERT INTO scene_plan_versions VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (plan['plan_id'],project_id,plan['version_id'],number,plan['provider'],plan['model'],dumps(plan),stamp,stamp,job_id))
            else:
                plan['revision']+=1
                connection.execute('UPDATE scene_plan_versions SET plan_json=?,updated_at=? WHERE id=? AND project_id=?',(dumps(plan),stamp,plan['plan_id'],project_id))
            connection.execute('INSERT INTO project_production VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET version_id=excluded.version_id,plan_json=excluded.plan_json,updated_at=excluded.updated_at', (project_id, plan['version_id'], dumps(plan), now()))
        self._mirror(project_id,plan)

    def _mirror(self, project_id, plan, *, active=True):
        self.repo._file(project_id, f'plan_v{plan["plan_version"]}.json', dumps(plan),folder='scenes')
        if active:
            self.repo._file(project_id, 'visual_plan.json', dumps(plan))
            self.repo._file(project_id, 'active_plan.json', dumps(plan),folder='scenes')

    def editable_plan(self, project_id, payload):
        current=self.require_approved(project_id)
        plan=self.view(project_id)['plan']
        if not plan: raise ScriptError('Önce onaylı senaryodan görsel plan hazırlayın.',409)
        if plan['status']!='ready' or not coverage(plan['blocks'],current['text']):
            raise ScriptError('Plan eski senaryoya ait veya anlatım sırası geçersiz. Güncel onaylı senaryodan plan hazırlayın.',409)
        if payload.get('plan_id')!=plan['plan_id'] or type(payload.get('revision')) is not int or payload['revision']!=plan['revision']:
            raise ScriptError('Plan değişti. Sayfayı yenileyip yeniden deneyin.',409)
        return plan,current

    @editable
    def edit_scene(self, project_id, scene_id, payload):
        if set(payload)!={'plan_id','revision','changes'} or not isinstance(payload['changes'],dict) or not payload['changes']:
            raise ScriptError('Sahne düzenleme alanlarını kontrol edin.')
        plan,_=self.editable_plan(project_id,payload)
        block=self._scene(plan,scene_id)
        if block['locked']: raise ScriptError('Önce sahnenin kilidini açın.',409)
        allowed=set(VisualBlock.model_fields)-{'narration'}
        if set(payload['changes'])-allowed: raise ScriptError('Anlatım burada değiştirilemez. Metin için Senaryo ekranını kullanın.')
        try:
            visual=VisualBlock.model_validate({**{key:block[key] for key in VisualBlock.model_fields},**payload['changes']}).model_dump()
        except ValueError: raise ScriptError('Sahne alanlarını kontrol edin. Bir–beş farklı kısa stok alternatifi, kısa vurgu yazısı ve 0–100 önem puanı gerekli.') from None
        block.update(visual)
        block['metadata_warnings']=[]
        self._save(project_id,plan,new_version=True)
        return self.view(project_id)

    @staticmethod
    def _scene(plan, scene_id):
        block=next((b for b in plan['blocks'] if b['id']==scene_id),None)
        if not block: raise ScriptError('Sahne bu aktif planda bulunamadı.',404)
        return block

    @editable
    def scene_action(self, project_id, scene_id, payload):
        if set(payload)-{'plan_id','revision','action','split_at'} or not {'plan_id','revision','action'}<=set(payload):
            raise ScriptError('Sahne işlemini kontrol edin.')
        plan,current=self.editable_plan(project_id,payload)
        block=self._scene(plan,scene_id);index=plan['blocks'].index(block);action=payload['action']
        if action not in ('lock','unlock','split','merge','up','down'): raise ScriptError('Geçerli sahne işlemi seçin.')
        if action not in ('lock','unlock') and block['locked']: raise ScriptError('Önce sahnenin kilidini açın.',409)
        if action in ('lock','unlock'): block['locked']=action=='lock'
        elif action=='split':
            at=payload.get('split_at');text=block['narration']
            if type(at) is not int or not 0<at<len(text) or not (text[at].isspace() or text[at-1].isspace()) or not text[:at].strip() or not text[at:].strip():
                raise ScriptError('Sahneyi bölmek için iki dolu anlatım arasında cümle/kelime sınırı seçin.')
            second=deepcopy(block);second.update(id=uuid4().hex,narration=text[at:].strip(),media=None)
            block['narration']=text[:at].strip();plan['blocks'].insert(index+1,second)
            plan.update(voice=None,subtitles=None);self.retime(plan,current['options'])
        else:
            other_index=index+1 if action in ('merge','down') else index-1
            if not 0<=other_index<len(plan['blocks']): raise ScriptError('Bu yönde komşu sahne bulunmuyor.')
            other=plan['blocks'][other_index]
            if other['locked']: raise ScriptError('Komşu sahne kilitli; önce kilidini açın.',409)
            if action=='merge':
                block['narration']=normalize(block['narration']+' '+other['narration'])
                if len(block['narration'])>12000: raise ScriptError('Birleşen sahne çok uzun; daha küçük sahneleri birleştirin.')
                block['entities']=list(dict.fromkeys(block['entities']+other['entities']))[:20]
                block['notes']=(block['notes']+' '+other['notes']).strip()[:1500]
                plan['blocks'].pop(other_index);plan.update(voice=None,subtitles=None);self.retime(plan,current['options'])
            else:
                # Owner choice: move VISUAL designs; approved narration order stays fixed.
                keys=(set(VisualBlock.model_fields)-{'narration'})|{'media','image_status'}
                first={key:deepcopy(block[key]) for key in keys};second={key:deepcopy(other[key]) for key in keys}
                block.update(second);other.update(first)
        if not coverage(plan['blocks'],current['text']): raise ScriptError('İşlem anlatım kapsamını değiştiremez; mevcut plan korundu.',409)
        self._save(project_id,plan,new_version=True)
        return self.view(project_id)

    @editable
    def select_plan(self, project_id, plan_id, payload):
        if set(payload)!={'confirm'} or payload['confirm'] is not True: raise ScriptError('Plan sürümü seçmek için açık onay gerekli.',409)
        with closing(self.projects._connection()) as connection,connection:
            row=connection.execute('SELECT plan_json FROM scene_plan_versions WHERE id=? AND project_id=?',(plan_id,project_id)).fetchone()
            if not row: raise ScriptError('Plan sürümü bulunamadı.',404)
            plan=json.loads(row['plan_json'])
            connection.execute('INSERT INTO project_production VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET version_id=excluded.version_id,plan_json=excluded.plan_json,updated_at=excluded.updated_at',
                               (project_id,plan['version_id'],dumps(plan),now()))
        self._mirror(project_id,plan)
        return self.view(project_id)

    def handoff(self, project_id):
        with self.projects.lock:
            return self._handoff(project_id)

    def _handoff(self, project_id):
        current=self.require_approved(project_id);plan=self.view(project_id)['plan']
        if not plan or plan['status']!='ready' or not coverage(plan['blocks'],current['text']):
            raise ScriptError('Part 6 için güncel onaylı senaryoyu tam ve sıralı kapsayan aktif plan gerekli.',409)
        fields=('scene_id','order','narration_text','start_estimate','end_estimate','estimated_duration','timing_source',
                'start','end','purpose','mood','importance','visual_intent','preferred_media_type','primary_stock_query',
                'alternative_stock_queries','stock_query_language','entities','location','action','composition','shot_suggestion',
                'transition','motion','overlay_text','overlay_language','notes','locked','media')
        return {'contract_version':1,'project_id':project_id,'plan_id':plan['plan_id'],'plan_version':plan['plan_version'],
                'source_script_version_id':current['id'],'language':plan['language'],'width':plan['width'],'height':plan['height'],
                'timing_source':plan['timing_source'],'media_priority':MEDIA_PRIORITY,'scenes':[{key:b[key] for key in fields} for b in plan['blocks']]}

    @editable
    def update(self, project_id, payload):
        plan = self.view(project_id)['plan']
        if not plan: raise ScriptError('Önce onaylı senaryodan görsel plan hazırlayın.')
        if set(payload) != {'music'} or not isinstance(payload['music'], dict): raise ScriptError('Müzik tercihlerini kontrol edin.')
        from app.production_settings import MusicSettings
        try: music = MusicSettings.model_validate(payload['music']).model_dump()
        except ValueError: raise ScriptError('Müzik ses seviyesi 0–1, geçiş süreleri 0–30 saniye olmalı. Lisans onayını kontrol edin.') from None
        from app.scripts.engine import SecretGuard
        SecretGuard(self.scripts.settings.secret_values()).validate(music)
        plan['music'] = music
        self._save(project_id, plan)
        return self.view(project_id)

    @editable
    def attach_media(self, project_id, block_id, media):
        from app.production_settings import MediaSelection
        try: media = MediaSelection.model_validate(media).model_dump()
        except ValueError: raise ScriptError('Medya seçimi bilgileri geçersiz.') from None
        from app.scripts.engine import SecretGuard
        SecretGuard(self.scripts.settings.secret_values()).validate(media)
        plan = self.view(project_id)['plan']
        if not plan: raise ScriptError('Görsel plan bulunamadı.', 404)
        if any(block.get('media') and (block['media']['provider'], block['media']['media_id']) == (media['provider'], media['media_id']) and block['id'] != block_id for block in plan['blocks']):
            raise ScriptError('Bu medya başka bir blokta seçilmiş. İlgili farklı bir görsel seçin.', 409)
        block = next((block for block in plan['blocks'] if block['id'] == block_id), None)
        if not block: raise ScriptError('Görsel blok bulunamadı.', 404)
        block['media'] = {**media, 'available': False}  # Metadata is never proof that a file exists.
        self._save(project_id, plan)
        return self.view(project_id)

    @editable
    def attach_timing(self, project_id, payload):
        plan = self.view(project_id)['plan']
        if not plan or not isinstance(payload, dict) or set(payload) != {'timings'} or not isinstance(payload['timings'], list) or len(payload['timings']) != len(plan['blocks']):
            raise ScriptError('Her görsel blok için gerçek anlatım zamanlaması gerekli.')
        try:
            timings = [NarrationTiming.model_validate(item) for item in payload['timings']]
            previous = 0
            for block, timing in zip(plan['blocks'], timings):
                if normalize(block['narration']) != normalize(timing.text) or timing.start < previous: raise ValueError()
                previous = timing.end
        except ValueError: raise ScriptError('Zamanlamalar sıralı ve blok metniyle aynı olmalıdır.') from None
        for block, timing in zip(plan['blocks'], timings): block.update(start=timing.start, end=timing.end, timing_source='tts')
        plan['timing_source'] = 'tts'
        self._save(project_id, plan)
        return self.view(project_id)
