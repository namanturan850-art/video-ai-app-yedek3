# NAMAN — Gelişmiş kurgu teslim raporu

Dal: `feature/naman-advanced-editing`. Başlangıç: `main` / `bfb5144` (PR #90).
Bu çalışma main'e birleştirilmez. Ücretli servis, gerçek kullanıcı projesi veya uzun render kullanılmadı.

## Denetim ve uygulanan kapsam

| İstek | Önceki durum | Bu dalın sonucu |
| --- | --- | --- |
| Serbest timeline | Mevcut anlatım yuvalarını düzenleme | Ayrı, kalıcı ek medya/metin/motion katmanları; boş ize bırakma, taşıma, uygun iz değiştirme, trim, çoğaltma, bölme, kaynak değiştirme, kilit, silme ve Shift ile çoklu seçim |
| Keyframe | Ortak veri/render sistemi yok | X/Y, ölçek, döndürme, saydamlık ve doğrulanmış kaynak sesi; zaman/değer/interpolasyon düzenleme, ekle/sil/önceki/sonraki |
| Dönüşüm/efekt | Temel plan hareketleri var | Oran korumalı ölçek, crop, flip, hız, dönüşüm, parlaklık/kontrast/doygunluk/blur/sharpen/monochrome/vignette; sabit sıra ve aç/kapat |
| Geçiş | Motor geçişleri mevcut, manuel kontrol sınırlı | Bitişik temel kliplerde Cut, Cross Dissolve, Dip to Black, Wipe ve süre doğrulaması; klip fade in/out |
| İşaretleyici | Menü var, kalıcı kayıt yok | Ad/not/renk/zaman, cetvel simgesi, ekle/düzenle/sil/önceki/sonraki; çıktı videosuna yazılmaz |
| Katman/motion | Ana motion ve Manuel AI/JSON yolu mevcut | Uygun plan metni/overlay ek kurguya alınabilir; eski katman kimliği bastırılır. Ana yuvada zaten bulunan motion yeniden kopyalanmaz; mevcut Motion/JSON akışı kullanılır |
| Monitör | Kaynak önizlemesi ve kesit kaydı mevcut | Program / Kaynak / Yan yana; ayrı oynatım saatleri; Program'a dönüşte kaynak oynatımı durur |
| Thumbnail | Görsel küçük resmi, video ikonu | Gerçek 240×135 FFmpeg karesi; kaynak hash önbelleği, görünür kartlarda talep, iki decoder sınırı |
| Güvenli silme/boşluk | Temel yuvalar anlatıma bağlı | Ek klip silinirken kaynak dosya ve temel kurgu korunur; altında temel video görünür; ripple ile anlatım kaydırılmaz |
| Dosya bırakma | Dosya seçerek güvenli yükleme mevcut | OS Files bırakma aynı içerik/boyut/proje/SHA doğrulamasına gider; önce arşiv, sonra kullanıcı ataması |
| Render kesintisi | Görev/sürüm ve kurtarma kayıtları mevcut | Aynı plan/kaynak hash/ayar kimliği doğrulanarak yeni render sürümü; eski tamamlanan çıktı korunur; sahte kareden devam yok |
| Medya hızı/tekrar | Arama paylaşımı, kota, CLIP/hash önbelleği ve tekrar denetimi mevcut | Bu sistem yeniden yazılmadı; kalite, coğrafya/tarih eşikleri gevşetilmedi; yeni önizleme görünür kaynaklarla sınırlı |
| Motion oranı | Durum ve raporda farklı paydalar | İkisinde de **seçili ana motion klip / seçili ana klip**; ek katmanlar hariç. Sahne oranı ve süre oranı ayrı adlarla gösterilir |
| Windows | Mevcut WebView2 smoke aracı | Linux Chromium ölçümü yapıldı; gerçek Windows/WebView2/GPU doğrulanmış sayılmaz |

## Kayıt ve güvenlik

SQLite **14 → 15** eklemeli yükselir. `editor_documents` proje ve aktif üretim planı anahtarıyla son belge/revizyonu saklar. `editor_document_events` önce/sonra belge geçmişini saklar. Eski tablolar ve medya dosyaları silinmez.

Belge sürümü `schema_version: 1`: `clips`, `adjustments`, `transitions`, `markers`, eski plan katmanını bastıran `suppressed_layers` ve geriye uyumluluk alanı `suppressed_scenes`. Klipte timeline `start/end` ile `source_start` ayrıdır. Dönüşüm, efekt ve yerel zamanlı keyframe listesi her düzenlenebilir öğeye bağlıdır.

Kaydetme aktif plan/revizyon, kilit, kaynak türü/hash/süre, interpolasyon, komşu geçiş ve anlatım sınırlarını doğrular. Eski revizyon hata verir. Render veya medya işi sürerken kurgu kaydı reddedilir. Geri al/yinele yalnız aynı proje ve planı etkiler. Kilitli bir sahneden dışarı taşıma da reddedilir.

Temel yuvaların geçmişi ile ek kurgu geçmişi ayrıdır. Ek klip/özellik bağlamında Geri al/Yinele ve kısayollar ek geçmişi kullanır; temel klibe dönüldüğünde mevcut temel geçmiş kullanılır. **Diğer araçlar → Ek kurgu geri al/yinele** her zaman açık seçenektir.

## Önizleme ve final bağlantısı

`app/editor/compositor.py` doğrulanmış sayılardan FFmpeg ifadeleri üretir. Kullanıcı filtre kodu veya shell komutu giremez. Metin Pillow ile şeffaf PNG'ye çizilir; altyazılar finalde en son mevcut altyazı zincirinden geçer. Dönüşüm/efekt/keyframe işlemleri aynı graph üreticisinden hem örnek Program karesine hem final montaja aktarılır.

Final FFmpeg montajı mevcut anlatım/müzik/SFX üzerine ek sesi miksler; gecikme ve dolgu 48 kHz örnek sayısıyla hesaplanır. Ses hızı `atempo`, seviye keyframe'leri ve fade gerçek filtrelerdir. Kaynak sesi doğrulanmamış kliplerde ses kontrolü kabul edilmez. Kaynak video hızı ana anlatım saatini değiştirmez; yeterli kaynak süresi zorunludur.

Yeni düzenleme belgesi ve ek kaynak hash'leri render parmak izine girer. İşaretleyici notları girmez. Çıktı metadata'sı uygulanan ek klip, ayar, geçiş ve keyframe sayısını içerir. OpenMontage hibrit yolunun final montajı mevcut FFmpeg sağlayıcısına gider; kurulu harici OpenMontage/Remotion ile uçtan uca çalışma burada denenmedi.

Program'daki yeni katman/efekt görüntüsü **640×360, en fazla 5 fps örnek kare** önizlemesidir; 30 fps kesintisiz proxy değildir. Kaynak ve anlatım saatleri bağımsızdır. Arka plandaki mevcut adaptif/Remotion dekorlarının ve HTML altyazı tipografisinin finalle piksel eşitliği iddia edilmez. Tam son görünüm için kısa yerel çıktı incelenmelidir. Görünür katmanlar için yeni bir medya araması başlatılmaz.

## Dosyalar

- `app/database.py`, `app/editor/advanced.py`: eklemeli şema, doğrulama, kalıcılık ve geçmiş.
- `app/editor/compositor.py`, `previews.py`, `routes.py`, `service.py`: ortak graph, hash doğrulamalı thumbnail/Program kareleri, API ve medya ölçümleri.
- `app/rendering/engine.py`, `service.py`, `routes.py`: final entegrasyonu, kaynak parmak izi, doğrulanmış yeniden başlatma.
- `app/static/advanced-editor.js`, `editor.js`, `workspace.js`, `workspace.css`, `index.html`, `render.js`: mevcut kabuğa bağlı gerçek kontroller ve durum bildirimleri.
- `tests/test_advanced_editing.py`, `test_advanced_render.py`, `test_render_restart.py`, ilgili migration/DOM testleri ve `scripts/advanced_browser_smoke.py`: sentetik doğrulama.

## Açık sınırlar

- Tam kaldığı kareden devam/checkpoint yok; doğrulanmış yeniden başlatma vardır.
- Ease eğrili klibin ortadan bölünmesi ve fade aralığı içinde bölme güvenli hata verir. Linear animasyon bölünürken sınır değerleri korunur. Trim sonrası dışarıda kalan keyframe'ler otomatik silinmez; geçersiz işlem reddedilir, kullanıcı önce keyframe zamanlarını düzenler.
- Çoklu seçim silmeyi destekler; grup halinde taşıma yok. Filmstrip, bezier eğri editörü ve serbest efekt sıralama eklenmedi.
- Temel anlatım yuvalarını silip süreyi kısaltma yapılmaz. Bu görevde anlatım/altyazı saati korunur.
- Yeni motion önizlemesi yerel motordadır. Canlı harita/ücretli servis çağrısı yapılmaz.
- Windows WebView2, gerçek %125 ölçekleme, NVENC, kurulu harici motor ve büyük gerçek kullanıcı arşivinde hız ölçümü açık doğrulamalardır.

## Kullanıcının basit kontrolü

1. Bu dalın güncellemesi kurulduğunda NAMAN'ı normal kısayolundan açın; tamamlanan işi korumak için önce ayrı bir deneme projesi kullanın.
2. **Kurgu** ekranına bir PNG veya kısa MP4 bırakın. Arşiv kartını boş Katman/Harita/Görüntü izine sürükleyin veya **Diğer araçlar → Seçili arşivi imlece ekle** seçin.
3. Ek klibi seçin; **Efektler** ile parlaklığı değiştirip kaydedin. **Keyframe** sekmesinde farklı iki zamanda ölçek ekleyin. Program karesi güncellenmelidir.
4. **İşaretleyiciler** menüsünden not ekleyin. Sayfayı yeniden açın; klip, efekt, keyframe ve not kalmalıdır.
5. Klip seçiliyken Delete ve Geri al deneyin. Kaynak dosya, seslendirme ve altyazı zamanları korunmalıdır.
6. Arşivdeki videoyu **Kaynak** sekmesinde oynatın; Program zaman kodu ilerlememelidir. **Yan yana** ve **Program** seçeneklerini deneyin.
7. Yalnız kısa deneme projesinde yerel CPU çıktısı alın; efekt/keyframe/katman ve ses senkronunu karşılaştırın. Uzun çalışan mevcut işinizi kesmeyin.

## Son doğrulama

| Kontrol | Kesin sonuç |
| --- | --- |
| Son seçili Python regresyon paketi | **192 geçti**, 3 deprecation uyarısı; **229,66 sn** |
| Ek kanal migration + eski render sürümleri uyumluluğu | **2 geçti**, 14,87 sn |
| Editör ve render tanısı DOM testleri | **7 geçti** |
| Gerçek API/SQLite Chromium paketi | Geçti: efekt kaydı, yeniden açılış, keyframe CRUD/undo, işaretleyici CRUD/undo, trim/taşı/böl/sil/undo, boş ize medya bırakma, OS dosya yükleme, bağımsız Kaynak/Program/yan yana, son revizyonun çözülmüş FFmpeg karesi, gerçek thumbnail |
| Yeni arayüz ölçümleri | **1366×768, 1600×900, 1920×1080, 1093×614**: yedi iz görünür, dış sayfa kaydırması yok |
| Mevcut çalışma alanı Chromium regresyonu | Geçti: arama, kaynak, medya/motion bırakma istekleri, dokuz menü/klavye, JSON/altyazı sekmeleri, resize/görünürlük/kayıt/sıfırlama; ayrıca 1650×900 ölçümü |
| Kısa gerçek render | Keyframe X/scale/rotation/opacity, monochrome, metin/fade, native final montaj, farklı renkli iki kaynakla Wipe, ilk/orta/son kare farkları ve 0,5×/1×/2× ses süresi geçti; en uzun final örneği 3,14 sn |
| Sözdizimi / paketler / diff | Python compile, JavaScript syntax, `pip check`, `git diff --check` geçti |

192 testlik komutun kapsamı: `test_advanced_editing`, `test_advanced_render`, `test_render_restart`, `test_naman_editor`, `test_render_diagnostics`, `test_render_view_never_draws`, `test_quality_performance`, `test_stock_media`, `test_hybrid_render`; ayrıca render/Claude/medya migration ve kaynak koruma kontrolleri. Ek iki test `test_channels::test_migration_puts_every_existing_project_in_a_default_channel` ve `test_smart_edit::test_preview_styles_new_versions_and_legacy_fingerprint_survive`.

Bu sonuçlar tüm depo testlerinin çalıştırıldığı anlamına gelmez. Windows/WebView2, GPU, canlı sağlayıcılar, kurulu harici motor ve gerçek uzun belgesel testi yapılmadı. Kullanıcı verilerinde yıkıcı işlem yapılmadı.

## GitHub teslimi

- [Geliştirme dalı](https://github.com/naman85331/video-ai-app/tree/feature/naman-advanced-editing)
- Aşama 1: `46fabc0` — sürümlü belge / kalıcılık / geçmiş.
- Aşama 2: `cd5c3b0` — ortak gerçek render / thumbnail / doğrulanmış yeniden başlatma.
- Aşama 3: `ff1be8f` — arayüz / monitör / işaretleyici / dosya bırakma / testler.
- Önizleme sağlamlaştırma: `abd9367` — son revizyon karesi gösterilmeden çözülür; migration testleri güncellenir.
- Son teslim commit'i bu raporu ve README bağlantısını içerir; [dalın commit listesi](https://github.com/naman85331/video-ai-app/commits/feature/naman-advanced-editing).

Dal GitHub'a gönderildi. **Draft PR oluşturulamadı:** `gh pr create --draft` işlemi `https://api.github.com/graphql` için `Forbidden` (403) yanıtı aldı. Ortamın kısıtlı ağ listesinde `github.com` bulunuyor, `api.github.com` bulunmuyor. Git aktarımı çalışıyor; API üzerinden PR açma engelli. Ana dal birleştirilmedi.

[Hazır PR açma ekranı](https://github.com/naman85331/video-ai-app/compare/main...feature/naman-advanced-editing?expand=1) · [Hazırlanan PR metni](ADVANCED_EDITING_PR.md). Bu bağlantı mevcut/açılmış PR olarak sunulmaz.
