"""Local metadata ranking, not visual recognition or an AI confidence score.

Names are copied from trusted scene fields. A small multilingual visual vocabulary
compares provider tags; it never adds a person, location, event or factual claim.
"""
import re
import unicodedata
from app.stock.identities import identity_keys

LABELS=('Zayıf eşleşme','Genel bağlantılı','İlgili','Çok ilgili')
MINIMUM=12
STRONG=60
RELATED=25
VIDEO_TOLERANCE=16
MODIFIERS={'new','old','black','white','north','south','east','west','mount','world','war','triangle','ii','iii'}
CONTEXT_GROUPS=({'ocean','ship','aircraft','storm','map','compass'},{'mountain','snow'},{'car','charging'})
STOP=set('the a an and or of in on at with for to from into by is are this that de der die das ein eine und im am mit von zu des den el la los las un una y en del le les une et du au aux sur dans il que bir ve ile bu da de için'.split())
GENERIC=set('world people city nature video background view travel beautiful general footage aerial panorama landscape scene context show showing modern wide close detail slow cinematic environment dunya insanlar sehir doga goruntu seyahat guzel genel welt menschen stadt natur hintergrund ansicht reise schon allgemein mundo gente ciudad naturaleza fondo vista viaje hermoso general monde personnes ville fond voyage beau'.split())
# Comparable *visual* terms in English/German/Spanish/French/Turkish. Proper names
# do not enter this dictionary: Bermuda/Titanic/Everest/Tokyo remain exact names.
WORDS={
 'ocean':'ocean sea seas oceans water waves wave coast coastal meer meere ozean wasser wellen kuste mar mares oceano agua olas costa mer eau vagues cote deniz okyanus su dalga dalgalar kiyi',
 'ship':'ship ships boat boats vessel vessels schiff schiffe boot barco barcos navire bateau gemi tekne',
 'aircraft':'aircraft airplane airplanes plane planes flugzeug flugzeuge avion aviones avions ucak',
 'storm':'storm storms tempest sturm gewitter tormenta tempete orage firtina',
 'mountain':'mountain mountains alpine berg berge gebirge montaña montana montañas montanas montagne montagnes dag daglar',
 'snow':'snow snowy ice schnee eis nieve hielo neige glace kar buz',
 'train':'train trains subway metro underground railway rail zug bahn ubahn tren ferrocarril chemin fer treni ray',
 'forest':'forest woods trees wald baume bosque arboles foret arbres orman agac',
 'beach':'beach beaches sand strand plage arena playa kum sahil plaj',
 'urban':'city skyline buildings building downtown architecture skyscraper office street traffic stadt gebaude buro strasse ciudad edificios oficina calle ville batiment bureau rue sehir bina ofis sokak trafik',
 'car':'car cars vehicle vehicles automobile automobiles auto autos automobil elektroauto elektroautos coche coches voiture voitures otomobil araba arac',
 'charging':'charging charger chargers charge laden ladestation cargador carga recharge sarj',
 'history':'history geschichte historia histoire tarih',
 'crew':'crew crews personnel ekip murettebat besatzung equipage tripulacion',
 'fatigue':'fatigue tired exhausted yorgun yorgunluk mudigkeit fatigue agotado',
 'map':'map maps chart karte karten mapa mapas carte cartes harita',
 'compass':'compass kompass brujula boussole pusula',
 'aviation':'aviation flight flights pilot pilots aeronautics luftfahrt flug pilot aviacion vuelo piloto vol pilote havacilik ucus pilot',
 'cockpit':'cockpit cockpits kokpit kokpiti kabine cabina cabine',
 'navigation':'navigation navigational gps navigasyon navegacion navegacion navigation ortung',
 'instrument':'instrument instruments instrumentation dashboard instrumente instrumentacion tableau gostergeler gosterge',
 'computer':'computer computers computing technology technological screen screens display displays monitor laptop bildschirm bildschirme ordinateur ecran pantalla computadora ordenador technologie technologie bilgisayar bilgisayarlar teknolojisi teknoloji ekran ekrani dijital digital',
 'animal':'animal animals dog dogs pet pets cat cats hund katze tier haustier perro gato mascota chien chat animaux kopek kedi hayvan evcil',
 'food':'food foods cooking meal cuisine essen kochen lebensmittel comida cocina nourriture yemek gida mutfak',
}
DOMAINS={'aviation':{'aircraft','aviation','cockpit','crew'},'rail':{'train'},'animal':{'animal'},'food':{'food'},
         'urban':{'urban'},'marine':{'ocean','ship','storm'},'mountain':{'mountain','snow'},
         'forest':{'forest'},'beach':{'beach'},'vehicle':{'car','charging'},'technology':{'computer','navigation','instrument'}}


def normalized(text):
    value=unicodedata.normalize('NFKD',str(text).casefold().replace('ı','i'))
    return ''.join(c for c in value if not unicodedata.combining(c))


ALIASES={word:meaning for meaning,words in WORDS.items() for word in normalized(words).split()}


def tokens(text):return re.findall(r'[^\W_]+',normalized(text))


STYLE=set(normalized("documentary interview style cinematic vintage retro archive archival black white old photo historical footage dramatic beautiful aerial close up wide shot background b roll belgesel tarz tarzı röportaj eski siyah beyaz fotoğraf tarihi arşiv sinematik dramatik güzel yakın plan geniş çekim görüntü dokümantasyon dokumentar dokumentarisch interview alt schwarz weiss historisch archiv filmisch nahaufnahme weitaufnahme documental entrevista antiguo blanco negro historico archivo cinematografico primer plano documentaire entretien ancien noir blanc historique archives cinematographique gros plan").split())


def meaningful(text):
    return canonical(text)-STYLE-MODIFIERS


def canonical(text):return {ALIASES.get(word,word) for word in tokens(text) if word not in STOP and word not in GENERIC and word not in STYLE}


def domains(concepts):return {name for name,group in DOMAINS.items() if concepts&group}


def phrase(text):
    if not isinstance(text,str):return ''
    value=' '.join(text.split())
    if not value or len(value)>300 or re.search(r'https?://|[?=&{}\\]|[\x00-\x1f]',value,re.I):return ''
    return value


def unique(values):
    result=[];seen=set()
    for value in values:
        value=phrase(value)
        if value and normalized(value) not in seen:
            result.append(value);seen.add(normalized(value))
    return result


def query_anchor(query):
    words=[w for w in phrase(query).split() if normalized(w) not in STYLE|STOP|GENERIC]
    known=[ALIASES[normalized(w)] for w in words if normalized(w) in ALIASES and ALIASES[normalized(w)] not in ('history','fatigue')]
    # An exact proper noun prefix takes priority over its visual modifiers.
    if words and normalized(words[0]) not in ALIASES and not normalized(words[0]).isdigit():
        prefix=[]
        for word in words:
            if normalized(word) in ALIASES or normalized(word) in ('atlantic','pacific'):break
            prefix.append(word)
        if len(prefix)>=2:return ' '.join(prefix[:4])
    if known:return ' '.join(dict.fromkeys(known[:3]))
    return ' '.join(words[:4])


def exact_named_terms(text):
    # A local fallback only: exact capitalized source phrases, no inferred names.
    found=re.findall(r'\b[A-ZÀ-ÖØ-Þİ][^\W_]*(?:\s+[A-ZÀ-ÖØ-Þİ][^\W_]*){0,3}',text)
    found=[' '.join(w for w in item.split() if normalized(w) not in STOP) for item in found]
    return next((item for item in found if len(item.split())>=2 and canonical(item)-set(WORDS)), '')


def profile(scene,slot=None):
    slot=slot or {}
    primary=phrase(scene.get('primary_stock_query',scene.get('stock_query','')) or slot.get('search_query',''))
    queries=unique([phrase(scene.get('provider_query','')),primary,slot.get('search_query',''),*scene.get('alternative_stock_queries',[]),*slot.get('fallback_queries',[])])
    entities=unique(scene.get('entities',[]));location=phrase(scene.get('location',''))
    visual=phrase(scene.get('visual_intent',slot.get('visual_goal','')))
    narration=phrase(scene.get('narration_text',scene.get('narration',''))[:300])
    trusted=' '.join([*entities,location,primary,visual,narration])
    core=meaningful(primary+' '+visual)
    valid=lambda value: bool(canonical(value)) and (bool(meaningful(value)&core) or normalized(value) in normalized(trusted))
    entities=[e for e in entities if valid(e)]
    location=location if valid(location) else ''
    explicit=phrase(scene.get('search_anchor',''))
    if not valid(explicit) or not meaningful(explicit)&core:explicit=''
    anchor=next(iter(entities),'') or location or query_anchor(primary) or query_anchor(visual) or exact_named_terms(narration) or explicit
    anchor=anchor[:150]
    # Primary visual metadata defines the subject. Incidental narration words or
    # a polluted alternative cannot certify an unrelated result as relevant.
    base=canonical(' '.join([primary,visual]))|canonical(anchor)
    # A weak old alternative (e.g. random urban footage for an ocean scene)
    # must not certify its own irrelevant tags as valid context.
    queries=[q for q in unique([*queries,*scene.get('search_alternatives',[])])
             if canonical(q)&base or not base or any(canonical(q)&group and base&group for group in CONTEXT_GROUPS)]
    core=canonical(anchor)&set(WORDS)
    expected=domains(core or base)
    if 'aviation' in expected:expected={'aviation'}
    elif expected-{'technology'}:expected.discard('technology')
    compatible=set().union(*(DOMAINS[name] for name in expected)) if expected else set()
    if 'marine' in expected:compatible|={'map','compass','aircraft'}
    if 'aviation' in expected:compatible|={'navigation','instrument','computer','map','compass'}
    hints=canonical(' '.join([*queries,phrase(scene.get('search_context',''))]))
    context=(base|hints&compatible)-canonical(anchor)
    context|=base&set(WORDS)
    protected_name=anchor if not meaningful(anchor)-set(WORDS) and sum(w[:1].isupper() for w in anchor.split())>=2 and any(normalized(w) in MODIFIERS for w in anchor.split()) else ''
    return {'protected_name':protected_name,'subject_anchor':anchor,'anchor_tokens':sorted(canonical(anchor)),
            'context_tokens':sorted(context),'queries':queries,'visual_goal':visual,
            'search_context':phrase(scene.get('search_context','')),'expected_domains':sorted(expected),
            'specificity':'named_specific' if protected_name or meaningful(anchor)-set(WORDS) else 'domain_specific' if expected&{'aviation','technology','rail','vehicle','animal','food'} else 'generic_visual'}


def provider_query(value,anchor=''):
    """Local vocabulary normalization, not a translation API or inferred entity."""
    source=phrase(value);anchor=phrase(anchor)
    named=canonical(anchor)-set(WORDS)-MODIFIERS
    words=anchor.split()
    named=named or (2<=len(words)<=4 and sum(w[:1].isupper() for w in words)>=2 and any(normalized(w) not in ALIASES and normalized(w) not in GENERIC for w in words))
    prefix=anchor.split()[:6] if named and normalized(anchor) in normalized(source) else []
    represented=canonical(' '.join(prefix));result=list(prefix)
    for word in tokens(source):
        concept=ALIASES.get(word,word)
        if concept in represented or word in STOP or word in GENERIC or word in STYLE:continue
        if concept in WORDS:
            result.append('buildings' if concept=='urban' else concept);represented.add(concept)
        elif word not in MODIFIERS and (normalized(word) in {normalized(w) for w in anchor.split()} or any(w[:1].isupper() and normalized(w)==word for w in source.split())):
            original=next(w for w in [*anchor.split(),*source.split()] if normalized(w)==word)
            result.append(original);represented.add(concept)
        if len(result)>=5:break
    if not result:result=[w for w in source.split() if normalized(w) not in STYLE|STOP|GENERIC][:5]
    return ' '.join(result)[:300]


def queries_for(profile):
    """Up to six concise provider queries, ordered by subject specificity."""
    anchor=profile['subject_anchor'];queries=profile['queries'];direct=[];combined=[];close=[]
    if anchor:direct.append(anchor)
    for q in queries:
        if anchor and normalized(anchor) in normalized(q):direct.append(q)
        elif anchor:combined.append((anchor+' '+q)[:300]);close.append(q)
        else:direct.append(q)
    if anchor:
        for q in queries:
            remainder=re.sub(re.escape(anchor),'',q,flags=re.I).strip()
            if remainder and canonical(remainder):close.append(remainder)
    context=profile.get('search_context','')
    if context:
        combined.append((anchor+' '+context).strip()[:300]);close.append(context)
    general=' '.join(word for word in profile['context_tokens'] if word in WORDS)
    if not general:general=profile['visual_goal']
    tiers=[];seen=set()
    for tier,values in ((1,direct[:2]),(2,[*direct[2:],*combined][:2]),(3,close[:2]),(4,[general])):
        for q in unique(values):
            if normalized(q) not in seen:
                optimized=provider_query(q,anchor)
                if optimized and normalized(optimized) not in seen:
                    tiers.append((tier,optimized));seen.add(normalized(optimized))
    # Always leave room for a compatible final contextual query.
    return tiers[:5]+tiers[-1:] if len(tiers)>6 else tiers


def evaluate(media,profile):
    desc=media.get('description','');actual=canonical(desc)
    protected=profile.get('protected_name','')
    if protected and not re.search(r'(?<!\w)'+re.escape(normalized(protected))+r'(?!\w)',normalized(desc)):return {'relevance_score':0,'relevance_label':LABELS[0]}
    anchor=set(profile['anchor_tokens']);context=set(profile['context_tokens'])
    matches=anchor&actual;context_matches=(context&actual)-matches
    named=anchor-set(WORDS)-MODIFIERS
    # An unknown shared descriptor (e.g. "electric") is not by itself a
    # verified proper subject. Do not let it bypass missing visual concepts.
    named_match=bool(named&actual) and (anchor&set(WORDS))<=actual
    expected=set(profile.get('expected_domains',[]));actual_domains=domains(actual)
    if expected and not named_match:
        supported=bool(expected&actual_domains)
        if expected=={'aviation'}:
            supported=bool(actual&DOMAINS['aviation']) or ({'navigation','instrument'}<=actual and not actual_domains-{'technology'})
        elif 'marine' in expected:supported=supported or bool(actual&{'map','compass'})
        if not supported:return {'relevance_score':0,'relevance_label':LABELS[0]}
    full=bool(anchor and re.search(r'(?<!\w)'+re.escape(normalized(profile['subject_anchor']))+r'(?!\w)',normalized(desc)))
    value=sum(2 if w in MODIFIERS else 6 if w in WORDS else 12 for w in matches)+4*len(context_matches)+(52 if full else 0)
    if anchor and matches==anchor:value+=12
    # A close-context fallback needs genuine visual evidence, not generic words.
    if (matches|context_matches)&set(WORDS):
        value=max(value,MINIMUM)
    if profile.get('specificity')=='domain_specific' and len(matches&set(WORDS))>=2:value=max(value,RELATED)
    conflict=(('ocean','urban'),('mountain','beach'),('train','forest'))
    for expected,wrong in conflict:
        if expected in context|anchor and wrong in actual and expected not in actual and not matches:value-=20
    value=max(0,min(300,value))
    label=LABELS[3] if value>=STRONG else LABELS[2] if value>=25 else LABELS[1] if value>=MINIMUM else LABELS[0]
    return {'relevance_score':value,'relevance_label':label}


def annotate(media,profile,tier,query):
    return {**media,**evaluate(media,profile),'search_tier':tier,'query_used':query,'provider_query':query}


def acceptable(media,current=None):
    threshold=RELATED if current and current.get('specificity') in ('named_specific','domain_specific') else MINIMUM
    return type(media.get('relevance_score')) is int and media['relevance_score']>=threshold


def rank(media,slot):
    ratio=media['width']/media['height']
    duration=media.get('duration') or 0
    quality=(int(1.5<=ratio<=2),int(media['width']>media['height']),int(4<=duration<=12) if media['media_type']=='video' else 0,min(media['height'],2160),min(media['width']*media['height'],3840*2160))
    preferred='image' if slot.get('preferred_type')=='stock_image' else 'video'
    return media['relevance_score'],quality,int(media['media_type']==preferred)


def choose(candidates,used,slot):
    current=slot.get('relevance_profile') or profile({'entities':[slot.get('subject_anchor','')]},slot)
    # Saved scores are history/display only. Never infer the current scene from
    # candidate query_used; search provenance is not evidence about its content.
    refreshed=[{**m,**evaluate(m,current)} for m in candidates]
    valid=sorted((m for m in refreshed if acceptable(m,current) and not identity_keys(m)&used
                  and (m['media_type']!='video' or m['width']>m['height'] and m['width']>=1280 and m['height']>=720)
                  and (m['media_type']!='video' or not slot.get('pacing_version') or (m.get('duration') or 0)>=slot.get('actual_duration_hint',slot['duration'])-.001)),key=lambda m:rank(m,slot),reverse=True)
    landscape=[m for m in valid if m['width']>m['height']]
    valid=[m for m in valid if m['width']>m['height'] or m['media_type']=='image' and m['relevance_score']>=STRONG and not landscape]
    if not valid:return None
    best=valid[0]
    videos=[m for m in valid if m['media_type']=='video' and (m['relevance_score']>=RELATED or best['relevance_score']<RELATED)]
    if videos and slot.get('preferred_type')!='stock_image' and videos[0]['relevance_score']>=best['relevance_score']-VIDEO_TOLERANCE:
        best=videos[0]
    return best


def ordered(candidates,used,slot):
    current=slot.get('relevance_profile') or profile({'entities':[slot.get('subject_anchor','')]},slot)
    ranked=sorted(({**m,**evaluate(m,current)} for m in candidates),key=lambda m:rank(m,slot),reverse=True)
    chosen=choose(ranked,used,slot)
    if chosen:ranked=[chosen,*[m for m in ranked if (m['provider'],m['media_type'],m['media_id'])!=(chosen['provider'],chosen['media_type'],chosen['media_id'])]]
    return ranked[:12]
