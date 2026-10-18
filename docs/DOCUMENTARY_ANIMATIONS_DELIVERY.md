# Manuel Plan ile belgesel animasyonları

18 Ekim 2026. Taban `origin/fix/manual-package-safe-import` / `17af5a7`.
Geliştirme dalı: `feature/manual-documentary-animations`.

## Kullanıcı akışı

Mevcut Manuel Plan düğmeleri ve yedi iz korunur. **Paketi Hazırla**, yalnız açık paylaşım/kota onayında mevcut Gemini sağlayıcısını çağırır. Gemini dış AI için talimat hazırlar; animasyon uygulamaz. **Paketi kopyala**, senaryo/seslendirme/altyazı/arşiv bağlamı yanında gerçek animasyon JSON şemasını, her bileşenin veri şemasını, sınırları ve üç açık DEMO örneğini içerir. Referans promptları Gemini'ye yürütülebilir talimat olarak aktarılmaz.

Dış AI, isteğe bağlı `animasyon_sahneleri` önerileri üretir. Kullanıcı cevabı veya `.json` dosyasını mevcut **Cevabı içe aktar** yolundan yükler. Her animasyon ve diğer öneriler ayrı ayrı doğrulanır; hatalı öğe sahne/saniye/özgün veri/düzeltme mesajıyla taslakta tutulur. Geçerli öğeler korunur. Gerçek JPEG önizleme kaydetmez. Yalnız seçilen öğeler açık onayla SQLite kurgu belgesine eklenir; final MP4 mevcut render yolunda oluşur.

Kullanıcı nesneleri tek tek çizmez. Dış AI desteklenen nesneleri konum, katman, renk, boyut ve keyframe ile tarif eder. Mevcut Motion nesne paneli üretilen nesnelerin kimliklerini gösterir; göster/gizle, zaman, X/Y, saydamlık ve renk kontrolleri kullanılabilir. Bu panelde zorunlu demo/şematik açıklaması düzenlenemez. Yeni ekran/menü/ana düğme eklenmedi.

## JSON sözleşmesi

`naman.manual-plan.v1` ve beş eski zorunlu bölüm değişmedi. Altıncı bölüm isteğe bağlıdır:

```json
{
  "scene_id": "paketteki-gercek-sahne-kimligi",
  "object_id": "istege-bagli-benzersiz-oneri-kimligi",
  "sentence_indices": [0],
  "start": 0.0,
  "end": 1.0,
  "track": "layers",
  "data": {
    "schema": "naman.animation.v1",
    "basis": "schematic",
    "background": null,
    "objects": [
      {"id": "bulut", "kind": "cloud", "x": 960.0, "y": 320.0,
       "width": 500.0, "height": 200.0, "color": "#93AAC7",
       "data": {"lobes": 5, "drift": 18.0}}
    ]
  }
}
```

Bu örnek bir bölüm kaydıdır; tam cevapta mevcut paketteki `schema/base` ve eski bölüm listeleri korunur. Gerçek `scene_id`, cümle kimlikleri ve saatler paketten alınmalıdır. `sentence_indices` isteğe bağlı, **sıfır tabanlı** `sentence_index` listesidir; ilgili altyazı aralığı sahne ve öneriyle kesişmelidir. Bir altyazı kutusu görsel sahne sınırını aşabilir; saatler bu yüzden değiştirilmez. Altyazı sürümü değişmiş animasyon taslağı uygulanmaz; eski animasyonsuz taslakların biçimi korunur.

- `start/end` ana proje saniyeleridir ve ilgili sahne içinde kalır. Nesne `start/end` ve keyframe `time` değerleri animasyon başlangıcına göre saniyedir.
- Çizim alanı **1920×1080 / 30 fps**. X/Y merkez konumu pikseldir; dönüş derece, ölçek çarpan, saydamlık/progress 0–1 değeridir. Yol noktaları nesne merkezine göre piksel farkıdır. Kamera X/Y görünüm merkezinin farkıdır; ölçeği 0.5–2 aralığındadır.
- Sınırlar: sahne 1 kare–30 saniye; 32 nesne; nesne başına 64 keyframe; kamera 32 keyframe; sahnede toplam 256 parçacık. Özgün isimler/alanlar dışında serbest kod, URL, dosya yolu veya eklenti kabul edilmez.
- `track`: `layers`, `infographics`, `maps` veya `emphasis`; mevcut yedi iz yapısı değişmez.
- `data.background=null` mevcut görüntünün üstünde şeffaf katman üretir. İsteğe bağlı `background_media`, yalnız arşivdeki `provider/media_id/sha256` kimliğidir; `source_start` kaynak girişidir. Bu öneri ayrı görüntü klibi olarak taslakta ve seçimde görünür. Temel kaynak silinmez veya değiştirilmez. Kısa/eksik/değişmiş kaynak açık hata olur; başka medya seçilmez.
- `background_media` ile opak arka plan birlikte reddedilir; kaynak sessizce örtülmez. Arka planı seçmeden yalnız animasyonu onaylamak da mümkündür.

Tam veri örnekleri: [Üç demo tanımı](examples/documentary_animations_demo.json). Bunlar tam proje planı değildir; aynı tanımlar görev paketinde de bulunur. Tam/gerçek veri şemaları `animation_capabilities.record_contract.data_schema` ve `component_data_schemas` alanlarında verilir.

## Gerçekte desteklenen teknikler

| Grup | Uygulanan kapsam | Desteklenmeyen / sonraki kapsam |
|---|---|---|
| Bilimsel/doğa | `cloud`, `flow`, `lightning`, `wave`, tohumlu sınırlı `particles`; diğer nesnelerle şematik kesit/süreç | Gerçek meteoroloji, CFD, sismik/rijit cisim simülasyonu, hacimsel ateş/bulut yok. |
| Coğrafya | Mevcut `map/route/zoom` ve harita kanalı korunur; yeni çizimler bunların yanında kullanılabilir | Yeni bir 3D dünya, harita veri üreticisi veya bileşen içinde keyfi koordinat sistemi eklenmedi. |
| Veri | `bar_chart`, `line_chart`, `counter`; eski oran/karşılaştırma/zaman çizelgesi şablonları korunur | Yeni grafikler negatif olmayan değerlerle, sıfır tabanıyla çalışır. Otomatik veri araştırması veya dış AI'ın “doğrulandı” iddiasını kabul etme yok. |
| Açıklayıcı | `node`, `box`, `circle`, `line`, `arrow`, `flow`; yolların açılması ve bağlantı hareketi | Nesne/katman keyframe bileşimidir; nedensellik veya teknik doğruluk motor tarafından icat edilmez. |
| Sinematik | Nesnede X/Y, ölçek, dönüş, saydamlık, progress; kamerada X/Y/ölçek; farklı katman hareketiyle düzlemsel paralaks | Perspektif kamera/PBR/ışık, gerçek 3D model/mesh animasyonu yok. Eski video geçişleri korundu; yeni geçiş motoru yok. |
| Tipografi | Kısa tek satırlı `label`, düğüm yazıları; mevcut vurgu; konum/ölçek/saydamlık keyframe | Glyph morph, özel font dosyası yükleme, otomatik kelime hizalama veya yeni TTS yok. |
| 2.5D/parçacık | `isometric_box` üç yüzlü şema; analitik, sabit tohumlu parçacık hareketi | Gerçek 3D veya parçacık fiziği değil. |

Easing seçenekleri `linear`, `ease_in_out`, `hold` ile sınırlıdır. Rastlantı yalnız sabit tohumdan gelir; duvar saati, biriken fizik veya çalıştırılabilir AI kodu yoktur.

## Veri güvenliği ve görsel tutarlılık

- `basis=narration`: grafik sayıları, etiketler, birimler ve metinler gerçek sahne anlatımına göre doğrulanır. Doğrulanamayan değer otomatik düzeltilmez.
- `basis=schematic`: bilimsel/teknik çizimler şematik olarak etiketlenir; ölçülü veri grafiği için bu temel yeterli sayılmaz.
- `basis=demo`: temsili sayılar/metinler kullanılabilir; çizimin üstünde sabit **DEMO — temsili veriler** görünür. Nesne/kamera hareketi bu etiketi taşımaz. Bilimsel nesneler fizik simülasyonu olarak sunulmaz.
- Kilitli sahne/görüntü aralığına animasyon eklenmez. Kaynak hash/süreleri, eski revizyon ve yeni altyazı sürümü kontrol edilir. Seslendirme, altyazı saatleri, medya, manuel klipler ve eski kayıtlar silinmez.
- Önizleme ve export aynı `draw_frame` / nesne zaman hesaplayıcısını kullanır. Saniyeler yerel 30 fps karelerine bağlanır. Hareketli sahne yanlışlıkla “son keyframe bitti” önbelleğiyle dondurulmaz.
- Şeffaf sahne mevcut Pillow/FFmpeg yolunda kayıpsız **qtrle/ARGB MOV ara dosyası**, opak sahne eski H.264 MP4 ara yolu kullanır. Final çıktı yine mevcut H.264/AAC MP4'tür. Yeni büyük bağımlılık veya ayrı render uygulaması yoktur. Şeffaf katmanın FFmpeg çizimi başarısızsa opak/sahte alternatif uygulanmaz; kullanıcıya eyleme dönük hata gösterilir, durdurma sinyali korunur.

## 300 referans ve lisanslar

[300 kayıtlık okunabilir teknik rapor](ANIMATION_REFERENCE_REVIEW_300.md) ve [makine okunur rapor](ANIMATION_REFERENCE_REVIEW_300.json) eklendi. **300/300** kayıt ve karşılık gelen prompt dosyaları tarandı; **263 tam**, **37 kısmi** kaynak. Dosya hashleri ve kaynak bağlantıları kayıtlıdır. Raporda her referansın aktarılabilir teknik parçaları, sonraki geliştirmeler ve uygun olmayan etkileşim/oyun talepleri ayrılır. Kaynak videolar ZIP'te yok; 300 videonun görsel kalite/çalışırlık testi yapıldığı veya 300 hazır efekt uygulandığı iddia edilmez.

ZIP'in **MIT / Copyright (c) 2026 yihui-dev** bildirimi [aynen korundu](ANIMATION_REFERENCE_MIT_LICENSE.txt). Dış video/müzik/marka/3D varlıkların hakları bu bildirimle doğrulanmış sayılmadı; bu varlıklar indirilmedi veya kopyalanmadı. Kaynak promptlar teknik referans olarak kullanıldı; yabancı JS/Python kodu taşınmadı/çalıştırılmadı. Mevcut FFmpeg ve OFL font koşulları korunur.

## Doğrulama ve sınırlar

- Bilimsel bulut/akış/yıldırım/yağış, hareketli veri grafiği ve açıklayıcı bağlantı/2.5D şema; her biri sentetik proje üzerinde JSON → doğrulama → taslak → gerçek JPEG → açık onay → **4 saniyelik gerçek 1920×1080/30 fps FFmpeg MP4** yolunda test edilir. Örneklerin temsili verileri DEMO etiketlidir.
- Ayrı kayıpsız ara dosya kontrolünde önizleme örneği ile tam animasyonun aynı karedeki RGBA pikselleri eşittir; hareketin sonraki karelerde sürdüğü ve arka plandaki kaynak videonun şeffaf bölgelerde kaldığı doğrulanır.
- Gerçek Chromium'da JSON dosyası yükleme, yeteneklerin pakette görünmesi, hatalı animasyonu ayırma, JPEG, onayı iptal etme ve yalnız geçerli animasyonu kaydetme kontrol edilir. Yedi iz ve orijinal kaynaklar korunur; harici ağ isteği yapılmaz.
- Yeni bileşen/katman/kamera/keyframe/veri/altyazı sürümü/kilit/notice kontrolleri ve eski Manuel Plan/geçiş/motion/render regresyonları çalıştırılır. Sonuç: **266 farklı Python testi passed / 3 skipped** (269 toplandı); 68, 197 ve son 43-testlik grupların örtüşmeleri çıkarıldı. Son çizim/validasyon kontrolü 20 passed (örtüşen tekrar). Frontend 70 passed ve üç gerçek Chromium akışı başarılı. Atlananlar 1 yerel Remotion ve 2 ek görsel/yer verisi gerektiren mevcut marker testidir. Ayrıntılar `docs/STATUS.md` içinde.
- **Canlı Gemini, Windows ve gerçek OpenMontage testi yapılmadı.** Gemini hazırlığı sağlayıcı taklidiyle doğrulandı. Bu bileşenler mevcut yerel Pillow/FFmpeg yolunu kullanır. Kullanıcı verileri veya ücretli API çağrısı kullanılmadı.

## GitHub teslim sonucu

Uygulama, testler, lisans ve 300 referans raporu **`b14e611`** commit'iyle `feature/manual-documentary-animations` dalına gönderildi. Draft PR açıklaması hazırlandı; oluşturma isteği hem GraphQL hem REST üzerinden **Forbidden** ile engellendi. Bu ortamda PR oluşturulamadı; main merge yapılmadı.

[Gönderilen dal farkı / PR oluşturma ekranı](https://github.com/naman85331/video-ai-app/compare/fix/manual-package-safe-import...feature/manual-documentary-animations?expand=1)

PR başlığı: **Manuel Plan: güvenli belgesel animasyon bileşimi ve 300 referans incelemesi**. Taban `fix/manual-package-safe-import`; kaynak `feature/manual-documentary-animations`. Draft inceleme içindir. Kullanım, kapsam ve test sonuçları bu raporda bulunur.
