"""Readable task brief for an external AI: one pasteable message or a file set.

The structure (self-sufficient instructions, data appended or as separate files,
a "check before sending" list, multi-message answers) follows the idea of the
user's ZADIAQ manual mode; the text and code are NAMAN's own and keep NAMAN's
rules: proposals are drafts, nothing reaches the timeline without approval.
"""
import io
import json
import zipfile

LANGUAGES = {'de': 'Almanca', 'en': 'İngilizce', 'tr': 'Türkçe', 'es': 'İspanyolca', 'fr': 'Fransızca', 'it': 'İtalyanca',
             'pt': 'Portekizce', 'pl': 'Lehçe', 'ru': 'Rusça', 'ar': 'Arapça', 'nl': 'Felemenkçe'}


def _seconds(value):
    return '?' if value is None else f'{float(value):.2f}'


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=1)


def scenes_text(package):
    lines = []
    for scene in package['narration']:
        lock = ' [KİLİTLİ — dokunma]' if scene.get('locked') else ''
        lines.append(f"[{scene['scene_id']}] ({_seconds(scene.get('start'))}–{_seconds(scene.get('end'))} sn){lock} {scene['text']}")
    return '\n'.join(lines)


def sentences_text(package):
    return '\n'.join(f"[{c['index']}] ({_seconds(c.get('start'))}–{_seconds(c.get('end'))} sn) {c.get('text', '')}"
                     for c in package.get('sentence_index', []))


def archive_data(package):
    return [{k: item.get(k) for k in ('provider', 'media_id', 'sha256', 'media_type', 'file_name', 'title', 'duration')}
            for item in package.get('archive', [])]


def timeline_data(package):
    return {'editing_slots': package.get('editing_slots', []),
            'maps': [m for m in package.get('maps', []) if m.get('sources') or m.get('overlays')]}


def references_text(package):
    selection = package.get('animation_reference_selection') or {}
    lines = ['Bu bölüm yalnız İLHAM içindir. Kaynakları kopyalama; tekniği bu belgesele uyarla.']
    lines += [f'- {rule}' for rule in selection.get('rules', [])]
    for scene in selection.get('scenes', []):
        if not scene.get('purpose'):
            continue
        lines.append(f"\n### Sahne {scene['scene_id']} ({_seconds(scene.get('start'))}–{_seconds(scene.get('end'))} sn) — amaç: {scene['purpose']}")
        for idea in scene.get('ideas', []):
            lines.append(f"- NAMAN fikri {idea['id']} «{idea['ad']}» ({idea['naman_izi']}): {idea['animasyon_tarifi']} Kural: {idea['dogruluk_kurali']}")
        for ref in scene.get('references', []):
            lines.append(f"- Referans {ref['reference_id']} «{ref['title']}» — {ref['how_to_use']}\n  Özet: {ref['excerpt']}")
    if len(lines) == 1 + len(selection.get('rules', [])):
        lines.append('\n(Bu senaryoda belirgin animasyon amacı bulunmadı; animasyon eklemek zorunlu değil.)')
    return '\n'.join(lines)


def _instructions(package, gemini_instructions, inline):
    project = package['project']
    language = project.get('language') or 'de'
    scenes = package['narration']
    ends = [s['end'] for s in scenes if s.get('end') is not None]
    minutes = (max(ends) / 60) if ends else 0
    extra = ''
    if gemini_instructions:
        extra = '\n## EK TALİMATLAR (Gemini tarafından bu proje için hazırlandı)\n' + '\n'.join(f'- {x}' for x in gemini_instructions) + '\n'
    if inline:
        data = f"""
================================================================
VERİ 1 — SAHNELER (kullanıcının senaryosu)  [scene_id] (başlangıç–bitiş sn) metin
================================================================
{scenes_text(package)}

================================================================
VERİ 2 — ALTYAZI CÜMLELERİ  [index] (başlangıç–bitiş sn) metin
================================================================
{sentences_text(package) or '(altyazı yok)'}

================================================================
VERİ 3 — ARŞİV (yalnız bu gerçek kaynakları kullanabilirsin)
================================================================
{_json(archive_data(package))}

================================================================
VERİ 4 — MEVCUT KURGU (görüntü yuvaları, kilitler, haritalar)
================================================================
{_json(timeline_data(package))}

================================================================
VERİ 5 — ANİMASYON REFERANSLARI (ilham)
================================================================
{references_text(package)}
"""
    else:
        data = """
VERİLER bu paketteki dosyalarda:
- 01_sahneler_ve_cumleler.txt : senaryo sahneleri ve altyazı cümleleri (saniyeleriyle)
- 02_arsiv.json               : kullanabileceğin gerçek video/görsel/ses kaynakları
- 03_mevcut_kurgu.json        : mevcut görüntü yuvaları, kilitler ve haritalar
- 04_referanslar.md           : sahnelere göre seçilmiş animasyon fikirleri (yalnız ilham)
- 05_cikti_sablonu.json       : doldurman gereken JSON şablonu
- NAMAN_GOREV_PAKETI.json     : tüm makine okunur ayrıntılar (output_contract dahil)
"""
    return f"""# NAMAN — BELGESEL KURGU PLANI GÖREVİ

Bu metni okuyan yapay zekâ: önceki hiçbir konuşmayı bilmen gerekmiyor. Yapacağın her şey burada yazıyor.

## NE OLDUĞU
NAMAN bir belgesel kurgu programı. Elinde kullanıcının yazdığı senaryo (sahnelere bölünmüş), seslendirme ve altyazı
cümleleri (saniyeleriyle), indirilmiş gerçek video/görsel arşivi ve mevcut kurgu var. Senden kurgu ÖNERİLERİ istiyor:
hangi saniyede bilgi kartı/infografik, harita, vurgu yazısı, kamera hareketi, gerekiyorsa HTML/CSS ile çizilmiş grafik.
NAMAN önerilerini doğrular ve taslak olarak gösterir. Kullanıcı seçip onaylamadan hiçbir şey kurguya işlenmez.

- Proje: {project.get('name', '')} — Konu: {project.get('topic', '')}
- Dil: {LANGUAGES.get(language, language)} ({language}). Ekranda görünen bütün yazılar bu dilde olacak.
- Süre: yaklaşık {minutes:.1f} dakika, {len(scenes)} sahne, {len(package.get('sentence_index', []))} altyazı cümlesi.
- Senaryo kullanıcıya ait. Vurgu ve katman yazıları (text) sahne metninde AYNEN geçmeli; NAMAN bunu kontrol eder.
- Profesyonel, sade belgesel üslubu: gereksiz efekt ve yazı yok. Her sahneye animasyon koymak zorunda değilsin.

## ÇIKTI: TEK BİR JSON
Cevabın yalnızca JSON olsun (açıklama yazma). Aşağıdaki şablonu doldur; "schema" ve "base" değerlerini AYNEN koru:

```json
{_json(package['output_template'])}
```

- Zorunlu bölümler (boş liste olabilir): sahneler, infografikler, harita_sahneleri, vurgular, katmanlar.
- İsteğe bağlı: animasyon_sahneleri (NAMAN nesne animasyonları), html_katmanlari (statik HTML + CSS @keyframes).
- Cevap tek mesaja sığmazsa bölümleri ayrı mesajlarda gönder. Her mesaj aynı schema ve base ile kendi başına geçerli bir JSON olsun; NAMAN parçaları birleştirir. Her öneriyi yalnız bir kez gönder.

## KURALLAR
- Her öneride geçerli scene_id olmalı. start/end ana proje saniyesidir ve kendi sahnesinin aralığında kalmalı.
- Kilitli sahnelere ve medyaya dokunma. Uygun kaynak yoksa öneriyi boş bırak; dosya, koordinat, sayı, tarih uydurma.
- Medya seçeceksen yalnız arşivdeki provider/media_id/sha256 kimliğini aynen kullan.
- Bölümlerin alanları ve izin verilen değerler (output_contract):

```json
{_json(package['output_contract'])}
```

## HTML/CSS KATMANLARI (html_katmanlari)
""" + '\n'.join(f'- {rule}' for rule in package['output_contract']['html_katmanlari']['rules']) + f"""
- Örnek:
```json
{_json(package['output_contract']['html_katmanlari']['example'])}
```

## GÖNDERMEDEN ÖNCE KONTROL ET
1. JSON geçerli mi (tırnaklar, virgüller, köşeli parantezler)? Yorum satırı yok mu?
2. schema ve base şablondakiyle birebir aynı mı?
3. Her önerinin scene_id'si VERİ 1'de var mı, start/end o sahnenin içinde mi?
4. Medya kimlikleri arşivdekiyle birebir aynı mı?
5. Vurgu/katman yazıları sahne metninde aynen geçiyor mu? Ekran yazıları doğru dilde mi?
6. Sayı, tarih, yer anlatımda var mı? Harita koordinatı uydurmadın mı?
7. HTML katmanlarında script, img, a, url(...), on... olayı yok mu? Hareket yalnız @keyframes ile mi?
8. Gereksiz animasyon veya yazı eklemedin mi?
{extra}{data}
(Paket NAMAN tarafından hazırlandı. Plan kimliği {package['base']['plan_id']}, revizyon {package['base']['revision']}.)
"""


def brief(package, gemini_instructions=None):
    """The single pasteable message: instructions plus all data."""
    return _instructions(package, gemini_instructions, inline=True)


def files(package, gemini_instructions=None):
    """File set for AIs that accept uploads, plus the single message."""
    readme = ('BU PAKET NE?\nNAMAN Manuel Plan görev paketi.\n\nNASIL KULLANILIR\n'
              'Yol 1 (dosya yükleyebilen yapay zekâ): 00_TALIMAT.md, 01–05 numaralı dosyalar ve NAMAN_GOREV_PAKETI.json dosyalarını yükle ve\n'
              '  "00_TALIMAT.md dosyasındaki görevi yap. Cevabın yalnızca JSON olsun." yaz.\n'
              'Yol 2 (dosya yükleyemiyorsan): TEK_MESAJ.txt dosyasının tamamını kopyalayıp sohbete yapıştır.\n\n'
              'Gelen JSON cevabını NAMAN → Kurgu → Manuel Plan → "2. Cevabı içe aktar" kutusuna yapıştır.\n'
              'NAMAN önerileri taslak olarak gösterir; sorun varsa yapay zekâya geri gönderilecek düzeltme mesajını kendisi yazar.\n'
              'Sen seçip onaylamadan kurgu değişmez.\n')
    return {
        'OKU_BENI.txt': readme,
        '00_TALIMAT.md': _instructions(package, gemini_instructions, inline=False),
        '01_sahneler_ve_cumleler.txt': 'SAHNELER [scene_id] (başlangıç–bitiş sn) metin\n' + scenes_text(package)
                                       + '\n\nALTYAZI CÜMLELERİ [index] (başlangıç–bitiş sn) metin\n' + sentences_text(package) + '\n',
        '02_arsiv.json': _json(archive_data(package)),
        '03_mevcut_kurgu.json': _json(timeline_data(package)),
        '04_referanslar.md': references_text(package) + '\n',
        '05_cikti_sablonu.json': _json(package['output_template']),
        'NAMAN_GOREV_PAKETI.json': json.dumps(package, ensure_ascii=False, indent=2),
        'NAMAN_CIKTI_SABLONU.json': json.dumps(package['output_template'], ensure_ascii=False, indent=2),
        'TEK_MESAJ.txt': brief(package, gemini_instructions),
    }


def zip_bytes(package, gemini_instructions=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, text in files(package, gemini_instructions).items():
            archive.writestr(name, text)
    return stream.getvalue()


def valid_instructions(value):
    """Gemini instructions echoed back by the client: same bounds as at creation."""
    if value is None:
        return None
    if not isinstance(value, list) or not 1 <= len(value) <= 30 or any(not isinstance(x, str) or not x.strip() or len(x) > 2000 for x in value):
        from app.editor.models import EditorError
        raise EditorError('invalid_package', 'Gemini talimatları 1–30 kısa metin olmalıdır.', 422)
    return value
