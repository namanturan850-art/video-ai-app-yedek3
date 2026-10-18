"""Reproducible text-only review of the supplied reference ZIP, never execution.

Usage: python scripts/review_animation_references.py supplied.zip docs
The report evaluates transferable techniques, not source video visual quality.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
from collections import Counter

# A match maps a technique to a documented, implemented component/old template.
TECHNIQUES={
 'Bilimsel/doğa':(r'cloud|lightning|wind|airflow|earthquake|fault|wave|water|rain|snow|bulut|yıldırım|deprem|akıntı|şimşek','cloud / flow / lightning / wave / particles (şematik)'),
 'Coğrafya':(r'\bmap\b|geograph|latitude|longitude|route|nemo|harita|地図','Mevcut map / route / zoom; proje anlatımı ve gerçek yer verisi gerekir'),
 'İnfografik':(r'\bchart\b|\bgraph\b|counter|timeline|data visual|bar chart|çubuk|grafik|sayaç','bar_chart / line_chart / counter; mevcut ratio / timeline / compare'),
 'Açıklayıcı':(r'diagram|arrow|node|cutaway|section|schematic|flowchart|explainer|explain|şema|kesit','node / box / arrow / flow / line / circle'),
 'Sinematik':(r'camera|zoom|pan\b|parallax|camera|kamera|yakınlaş','X/Y/scale kamera ve nesne keyframe; mevcut kaynak pan/zoom'),
 'Tipografi':(r'typograph|\btext\b|\btitle\b|\bword\b|label|metin|yazı|başlık|文字|字幕','label / node / kısa metin keyframe; mevcut vurgu'),
 '2.5D/parçacık':(r'particle|isometric|2\.5d|parallax|parçacık','Sınırlı tohumlu particles / isometric_box; tam 3D değil'),
 'Kare zamanı':(r'deterministic|frame|seek\(|closed.form|time.remap|kare|フレーム','30 fps analitik saat / keyframe; önizleme ve export ortak çizim'),
}
DEFERRED={
 'Tam 3D/PBR/shader':r'three\.?js|three\.js|webgl|webgpu|\bpbr\b|glsl|raymarch|ray.trac|3d|shader|volumetric|3次元',
 'Gerçek fizik/akış simülasyonu':r'physics|rigid.body|fluid sim|navier|collision|tectonic|friction|physically|fizik sim',
 'Glyph/malzeme morph ve özel sanat motoru':r'morph|fractal|mandelbrot|watercolor|watercolour|ink sim|glass|chrome|pixel.art|mosaic|origami|hand.drawn',
 'Spring/motion blur':r'\bspring|motion.blur|subframe|halation',
 'Otomatik ses/ritim analizi':r'beat|web.audio|music|sound.effect|tts|voiceover|lyric|narrat|seslendirme',
}
GAME_IDS={'froessell-562325','niegramotny-197521','dreyk0o0-165270','anduraio-570761','mycodecoach-459574','spacyapps-157886'}


def body(text):
    section=text.split('## Prompt',1)[-1]
    blocks=re.findall(r'```[^\n]*\n([\s\S]*?)```',section)
    if blocks:return '\n'.join(blocks)
    # Partial posts can have no fenced prompt: retain their actual summary text.
    return '\n'.join(line for line in section.splitlines() if not line.startswith(('- **','More Opus','[▶','An Opus')))


def review(source,output):
    output=Path(output);output.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(source) as z:
        if sum(i.file_size for i in z.infolist())>20*1024*1024:raise ValueError('Reference ZIP unexpectedly large')
        catalog=json.loads(z.read(next(n for n in z.namelist() if n.endswith('/CODEX_SECILEN_300.json'))))
        if len(catalog)!=300 or len({r['ID'] for r in catalog})!=300:raise ValueError('Expected 300 unique references')
        rows=[]
        for item in catalog:
            identifier=item['ID']
            if not re.fullmatch(r'[a-z0-9-]+',identifier):raise ValueError('Invalid reference ID')
            name=next(n for n in z.namelist() if n.endswith('/CODEX_SECILEN_300_PROMPT/'+identifier+'.md'))
            raw=z.read(name);text=raw.decode('utf-8-sig');prompt=body(text)
            available=[f'{group}: {tech}' for group,(pattern,tech) in TECHNIQUES.items() if re.search(pattern,prompt,re.I)]
            deferred=[tech for tech,pattern in DEFERRED.items() if re.search(pattern,prompt,re.I)]
            excluded=[]
            if identifier in GAME_IDS:excluded.append('Oynanabilir oyun/araç fiziği/oyun arayüzü NAMAN iş akışına uygun değil')
            elif re.search(r'interactive|mouse|keyboard|orbitcontrols|click to|slider',prompt,re.I):
                excluded.append('Gerçek zamanlı kullanıcı etkileşimi taşınmadı; yalnız zamanlanmış açıklayıcı hareket uygun')
            if re.search(r'download|fetch\(|https?://|scrape',prompt,re.I):excluded.append('Prompttan otomatik web indirme/kaynak üretme uygulanmaz')
            if identifier in GAME_IDS:status='Ana amaç uygun değil; yalnız sınırlı hareket teknikleri'
            elif available:status='Teknik parçalar kullanılabilir; kaynak videonun yeniden yapımı değil'
            else:status='Yetersiz teknik ayrıntı; özel sahne tasarımı/gelecek geliştirme'
            groups=[group for group,(pattern,_) in TECHNIQUES.items() if re.search(pattern,prompt,re.I)]
            rows.append({'id':identifier,'title':item['Başlık / İlk satır'][:180],
                         'catalog_theme':item['NAMAN teması'],'groups':groups,'prompt_status':item['Prompt durumu'],
                         'prompt_sha256':hashlib.sha256(raw).hexdigest(),'prompt_bytes':len(raw),'review_status':status,
                         'available_techniques':available,'deferred_techniques':deferred,'unsuitable_requests':excluded,
                         'source':item['Orijinal paylaşım'],'verification':'Metin incelemesi; kaynak video/model/kod ve görsel kalite testi yok'})
        license_text=z.read(next(n for n in z.namelist() if n.endswith('/ORIJINAL_MIT_LICENSE.txt'))).decode()
        (output/'ANIMATION_REFERENCE_MIT_LICENSE.txt').write_text(license_text,encoding='utf-8')
    report={'source_zip_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'count':len(rows),
            'method':'300 metadata ve 300 tam prompt dosyası okundu; teknik talepler metin desenleriyle eşlendi. Tam/kısmi kaynak ayrımı korundu. Kaynak videolar oynatılmadı; 300 efektin uygulanmış olduğu iddia edilmez.',
            'references':rows}
    (output/'ANIMATION_REFERENCE_REVIEW_300.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    counts=Counter(r['prompt_status'] for r in rows)
    lines=['# 300 animasyon referansı — teknik inceleme','','18 Ekim 2026. '+report['method'],
           '',f"Kapsam: **300/300** benzersiz kayıt ve prompt; kaynak durumu: **{dict(counts)}**.",
           '', 'Her satırdaki destek, referanstaki belirli teknik parçaya aittir; orijinal sahnenin/ürünün/oyunun tamamına değil. Konu etiketleri örnek kaynaktaki otomatik seçimden geldiği için ayrıca metne göre gruplandırıldı. Bazı referansların “Harita” etiketi gerçekte logo/ürün videosudur; bu etiket coğrafi veri kabul edilmez.',
           '', '## Ortak sonuç', '',
           '- Şimdi: sınırlı JSON nesneleri, katmanlama, X/Y/ölçek/dönüş/saydamlık keyframe, düzlemsel kamera, cloud/flow/lightning/wave, parçacık, bar/line chart/counter, node/arrow/line/box/circle, label ve 2.5D isometric_box.',
           '- Mevcut destek: map/route/zoom ve diğer NAMAN infografikleri, kaynak medya pan/zoom ve mevcut kontrollü geçişler. Doğrulanmış proje verisi gerekir; referanstaki sayı/koordinatlar alınmadı.',
           '- Sonra: tam 3D modeller/PBR/ışık/gölge, hacimsel bulut/ateş, gerçek fizik/CFD, özel fraktal/shader/glyph morph, kapalı form spring ve motion blur. Bu teknikler için motor/varlık/performans geliştirmesi gerekir; bu değişiklikte yok.',
           '- Uygun değil: oynanabilir oyunlar, kullanıcı etkileşimi/otomatik web varlığı toplama, kaynak seslendirmeyi değiştirme, serbest JS/Python çalıştırma. Uygun teknik alt parçalar ayrı belirtilir.',
           '', '## Gruplar','']
    for group in TECHNIQUES:
        lines.append(f"- {group}: {sum(group in r['groups'] for r in rows)} metinde teknik işaret (gruplar örtüşür).")
    lines+=['','## Lisans ve doğrulama sınırı','',
            'ZIP, Copyright (c) 2026 yihui-dev MIT lisansını içeriyor; bildirim ANIMATION_REFERENCE_MIT_LICENSE.txt içinde korundu. Dış bağlantılardaki video, müzik, marka, 3D model ve fotoğrafların hakları bu lisansla doğrulanmış sayılmadı; bu varlıklar indirilmedi veya kopyalanmadı. Kaynak promptlar çalıştırılmadı; yeni bağımlılık kurulmadı. Mevcut FFmpeg derlemesinin LGPL/GPL ve OFL font bildirimleri korunur.',
            '', '## Kayıt bazında sonuç','', '| # / ID | Gruplar / kaynak | Kullanılabilir teknik | Sonra / uygun olmayan |','|---|---|---|---|']
    for index,r in enumerate(rows):
        safe=lambda value:str(value).replace('|','/').replace('\n',' ')
        available='; '.join(r['available_techniques']) or 'Genel anlatım fikri; yeniden kullanılabilir somut teknik yok'
        later='; '.join(r['deferred_techniques']+r['unsuitable_requests']) or 'Kaynağa özel tasarım/varlıklar ayrıca gerekir'
        lines.append(f"| {index+1:03d} [{r['id']}]({r['source']}) | {safe(', '.join(r['groups']))} / {r['prompt_status']} | {safe(available)} | {safe(later)} |")
    (output/'ANIMATION_REFERENCE_REVIEW_300.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'count':len(rows),'source_status':dict(counts),'status':dict(Counter(r['review_status'] for r in rows))},ensure_ascii=False))


if __name__=='__main__':review(sys.argv[1],sys.argv[2])
