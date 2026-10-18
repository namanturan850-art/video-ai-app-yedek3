"""Select abstract, supported techniques from the audited 300-reference index.

No source prompt, video, URL or executable code is sent to the AI. Selection is
local and deterministic; Gemini can contextualize it only after explicit consent.
"""
from functools import lru_cache
import json
from pathlib import Path
import re

# Topics select techniques, never invented factual data or media.
TOPICS={
    'Bilimsel/doğa':('cloud','storm','lightning','weather','wind','atmos','climate','bulut','fırtına','şimşek','hava','iklim','nube','tormenta','viento','clima'),
    'İnfografik':('percent','population','growth','million','data','ratio','yüzde','nüfus','milyon','oran','veri','artış','población','millones','porcentaje','datos'),
    'Coğrafya':('map','river','city','country','border','route','harita','nehir','şehir','ülke','sınır','rota','río','ciudad','país','ruta','roma','amazon'),
    'Açıklayıcı':('process','system','cause','network','süreç','sistem','neden','ağ','proceso','sistema','red'),
}


@lru_cache(maxsize=1)
def catalog():
    path=Path(__file__).resolve().parents[2]/'docs/ANIMATION_REFERENCE_REVIEW_300.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    return tuple(data['references'])


def select_techniques(narration):
    selected=[]
    for scene in narration:
        words=set(re.findall(r'[^\W\d_]+',scene.get('text','').replace('İ','i').lower()))
        matches={group:sorted(w for w in words if any(w==term or len(term)>=4 and w.startswith(term) for term in terms)) for group,terms in TOPICS.items()}
        groups=[g for g,hits in matches.items() if hits] or ['Açıklayıcı','Sinematik','Tipografi']
        ranked=sorted(enumerate(catalog()),key=lambda pair:(-sum(g in pair[1]['groups'] for g in groups),pair[0]))
        references=[]
        for _,ref in ranked:
            techniques=[t for t in ref['available_techniques'] if t.split(':')[0] in groups]
            if not techniques:continue
            references.append({'reference_id':ref['id'],'techniques':techniques,'prompt_status':ref['prompt_status']})
            if len(references)==3:break
        selected.append({'scene_id':scene['scene_id'],'start':scene.get('start'),'end':scene.get('end'),
                         'reason':{g:hits for g,hits in matches.items() if hits} or {'default':['anlatımı açıklayan sade şema / kamera / kısa metin']},
                         'references':references})
    return {'catalog_count':len(catalog()),'selection':'Yerel konu eşlemesi; sahne başına en fazla üç teknik referansı.',
            'rules':['Kaynak videoları, olayları, karakterleri veya kompozisyonları kopyalama; yalnız soyut teknikleri bu anlatıma uyarla.',
                     'Her referans zorunlu efekt değildir. Anlatıma katkı sağlamıyorsa animasyon ekleme.',
                     'Yalnız animation_capabilities ve output_contract işlemlerini kullan. Referanslar yeni bir motor veya serbest kod izni vermez.',
                     'Harita gerçek yer verisi, grafik gerçek anlatım verisi gerektirir. Kaynak yoksa öneriyi boş bırak.',
                     'Bu seçim kurguya yazılmaz; gelen her işlem doğrulama, taslak, önizleme ve kullanıcı onayından geçer.'],
            'scenes':selected}
