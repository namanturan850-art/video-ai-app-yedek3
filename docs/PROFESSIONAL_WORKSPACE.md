# NAMAN Premiere Dark çalışma alanı

Bu sürüm mevcut FastAPI/SQLite düzenleyicisini kullanır. Yeni varsayılan tema koyu gri/mordur; daha önce kaydedilen turkuaz, mor, mavi, turuncu, açık tema ve özel vurgu tercihleri korunur. Tema video renklerini değiştirmez.

## Kullanım

1. Windows'ta `START_NAMAN.bat` dosyasını açın. Başlangıç ekranında gerçek kayıtlı projeler son güncelleme tarihine göre listelenir. Yeni Proje ve Proje Aç mevcut proje sistemine gider.
2. Projenizde **Kurgu** ekranını açın. Üstte Dosya, Düzen, Klip, Sekans, İşaretleyiciler, Grafikler ve Başlıklar, Görünüm, Pencere, Yardım menüleri vardır. İçe Aktar arşiv yükleme seçicisini; Dışa Aktar mevcut render ekranını açar. Üretim ve Ayarlar erişimi korunur.
3. Solda medya arayın, kaynak filtresini kullanın, içe aktarın veya bir öğeyi seçip gerçek yerel dosyasını önizleyin. Videonun kaynak başlangıç/bitiş kesitini kaydedebilirsiniz. Kaynak kesiti ile timeline süresi ayrıdır.
4. Bir video veya görseli **kilitsiz Görüntü yuvasına** sürükleyin. Hedef belirginleşir. Arşiv ses dosyası bir görüntü yuvasına atanamaz. Kilitli sahne/klip, eski revizyon ve yetersiz video süresi backend tarafından reddedilir. Yeni serbest katman oluşturulmaz; anlatım süresi korunur.
5. Motion sekmesi projedeki mevcut animasyonları gösterir. Birini seçerek sağda Motion veya JSON sekmesini açın. Aynı sahnenin aynı türdeki kilitsiz motion yuvaları arasında sıralama yapılabilir; diğer bırakmalar açıklanarak reddedilir. Yeni grafik oluşturmak için mevcut medya hazırlama veya manuel plan araçlarını kullanın.
6. Timeline klibini seçin. Sağdaki Özellikler/Düzenle sekmeleri zaman ve kaynak kesitini; Motion/JSON animasyon verisini; Metin mevcut altyazıyı açar. Ses sekmesi gerçek miks düzenleyicisini açar. Motorun desteklemediği dönüşüm/keyframe kontrolleri sunulmaz.
7. **⋯** menüsünden zaman kodu, ses miks, manuel AI/JSON ve isteğe bağlı örnek-kare kalite incelemesine erişin. Kalite incelemesi onay olmadan çağrı yapmaz. Motion oranı ve %25 hedefi alt durum çubuğunda görünür; ayrıntı ve eksik medya bağlantıları korunur.
8. Panel ayırıcılarını sürükleyin; timeline ayırıcısı klavyede yukarı/aşağı okları da kabul eder. Pencere menüsünden panelleri gizleyin/açın. Görünüm → Çalışma düzenini sıfırla ile geri dönün. Düzen bu bilgisayarın yerel tercihinde kalır.

Uygulanan zamanlama, medya atama, bölme/çoğaltma ve kilit işlemleri proje revizyonuna yazılır. **Ctrl+S**, açık zaman/altyazı formunu kaydeder; Motion/JSON sekmesinde seçili grafiğin doğrulama/yeniden hazırlama işlemini çalıştırır. Final MP4 için ayrıca render gerekir. Aktif ses/altyazı veya önizleme dosyası yoksa boş durum açıklanır; sahte medya üretilmez.

Kısayollar: Space oynat/duraklat; J geri sar; K duraklat; L oynat; sol/sağ ok bir kare; Ctrl+K böl; Ctrl+Z geri al; Ctrl+Shift+Z yinele. Metin, JSON ve form alanlarında yazarken bu kısayollar devreye girmez. Serbest silme ve kalıcı işaretleyiciler desteklenmez; işaretleyici menüsü bunu açıkça belirtir. Menüler Enter, oklar ve Escape ile kullanılabilir.

Bağımsız medya yuvası olmayan plan katmanları sağ panelde açıklamayla salt okunur gösterilir. Bu katmanların metin/hareket değişikliği mevcut Manuel AI/JSON plan revizyonu üzerinden yapılır; çalışan bir slot düzenleyicisi varmış gibi kaydetme formu sunulmaz.

## Doğrulama ve sınırlar

- `scripts/workspace_browser_smoke.py` gerçek Chromium üzerinde 1366×768, 1600×900, 1920×1080, 1650×900 ve %125 ölçeklemeye yakın **1093×614 CSS piksel** boyutlarını kontrol eder. HTTP cevapları izole test verileridir; gerçek kullanıcı projesi veya canlı API kullanılmaz. Dış sayfa kaydırması, yedi izin görünürlüğü, 16:9 monitör yüzeyi, menü sınırları, sekmeler, arşiv arama, kaynak önizleme, medya bırakma isteği, resize ve panel tercihleri ölçülür. Ekran görüntüleri belirtilen çıktı klasörüne yazılır.
- `tests/test_workspace.py` gerçek geçici SQLite ve yerel medya dosyalarıyla upload, kilit/red, eski revizyon/red, medya atama, geri al/yinele, split geri al/yinele, anlatım/altyazı sürelerini koruma ve yeniden açılış kalıcılığını test eder. Varsayılan ve önceki kişisel tema da yeniden açılarak doğrulanır.
- İlgili mevcut testler arama önbelleği, coğrafi kapsam, CLIP bağlam/model/dosya kimliği, kullanım dışı sağlayıcılar, altyazı, açılış ve render görünümünün salt okunurluğunu kapsar. Kısa gerçek FFmpeg ses-miks testi 3,14 saniyelik yerel çıktı üretir.
- Gerçek Windows WebView2, fiziksel %125 Windows ölçeklemesi, GPU, kurulu OpenMontage/Remotion ve kullanıcının büyük medya arşivi bu Linux ortamında doğrulanamaz. Chromium testi bunların yerine geçtiği iddiasında bulunmaz. Ücretli sağlayıcı çağrısı veya 8–10 dakikalık render yapılmaz.

## Windows'ta kısa kontrol

1. Mevcut projenizi açın; medya, ses ve render dosyalarınızı silmeyin.
2. 1366×768 ve normal pencere boyutunda Kurgu'yu açın. Menüler ve yedi iz aynı anda görünmeli; dış sayfa kaymamalı.
3. Yerel arşivden bir öğeyi önizleyin. Kilitli yuvaya atamanın reddedildiğini; uygun kilitsiz yuvada atama/geri al/yinele çalıştığını kontrol edin.
4. Sesli projede oynat/duraklat/seek ve kare adımını deneyin. Altyazı, Motion, JSON ve Ses sekmelerini açın. Değişiklik istemiyorsanız kaydetmeyin.
5. Panelleri boyutlandırın, kapatıp açın; uygulamayı yeniden açınca düzenin korunduğunu ve Görünüm → Çalışma düzenini sıfırla işlemini kontrol edin.
6. Windows %125 ölçeklemede aynı kontrolü tekrarlayın. İsterseniz mevcut `.venv\Scripts\python scripts\webview2_editor_smoke.py PROJE_KIMLIGI VERI_KLASORU` aracıyla otomatik menü/yedi iz/pencere kaydırması kontrolünü çalıştırın. Bu araç proje düzenleme komutu göndermez.

## Teknik denetim: mevcut bağlar ve kalan doğrulamalar

| Alan | Kod ve mevcut bağ | Kanıt / kalan |
| --- | --- | --- |
| Büyük arşiv | `EditorService.archive` dosya kimliğini metadata'dan okur; hatalı kaydı atlar. Workspace kartları 60'lık dilimlerle çizilir; video küçük resmi yerine doğru tür ikonu kullanılır; video yalnız seçilince yüklenir. | Arşiv bozulma/açılış testleri ve Chromium; kullanıcının büyük arşivinde süre ölçümü bekliyor. |
| Açılış donması | `editor.js`: zaman çizelgesi önce, arşiv bağımsız; timeout/retry; waveform çizimi editörü yeniden kurmaz; observer'lar önceki render'da kapatılır. | DOM açılış/hata testleri; gerçek WebView2 kontrolü bekliyor. |
| Gerçek önizleme | Projeye özel slot/archive endpoint'leri ve anlatım URL'si; kaynak/plan yüzeyleri; dosya hatası/eksik aralık açıklaması. | Chromium + yerel upload API testleri; Windows codec davranışı bekliyor. |
| Tekrarlı arama | `StockService._cache_search`, `SearchSession`, `director_media.search`: normalleştirilmiş sayfa/sağlayıcı anahtarları ve paylaşılan uçuşlar. | Performans regresyon paketi; canlı sağlayıcı hızı ölçülmedi. |
| CLIP önbelleği | `PreviewCache`, `VerdictCache`, bağlam ve medya/model kimlikleri; değiştirilmiş medya eski kararı kullanmaz. | İlgili önbellek/batch/coğrafya testleri; büyük model indirilmedi. |
| Kaynak önceliği | `director_media.try_local_archive` önce yerel; aktif ağ sağlayıcıları Pixabay/Commons; tarihsel sahnelerde Commons önceliği korunur; sonra uygun yerel motion. | Kaynak kodu denetimi ve sağlayıcı regresyonları; canlı çağrı yok. |
| Coğrafya/tarih | Bağlı sahne sorgusu, tarihsel/modern filtreler, zorunlu/yasak içerik ve semantik değerlendirme. | Catatumbo/ülke/kıta/kapsam testleri; her medya için doğruluk garantisi verilmez. |
| Kaynak/timeline ayrımı | `update_timeline`, `assign`: kaynak aralığı doğrulaması, komşu sınırları ve sahne ses süresi korunur. | DOM trim/seek ve gerçek SQLite testleri. |
| Kalıcılık/geçmiş | Atama ve klip işlemleri `editor_revisions`; geçmiş aktif plan ve beklenen sahne snapshot'ıyla sınırlandırılır, split üyeliği ve medya geri yüklenir. | Gerçek yeniden açılış, atama/split undo-redo ve eski revizyon testleri. |
| Önizleme/final | Aynı slot seçimi/kaynak kesiti; kaydedilmiş ses ayarları FFmpeg zincirine bağlanır. | Mevcut 3,14 sn ses-miks çıktı testi; her motion türünün piksel eşitliği iddia edilmez. |
| Windows | Mevcut `START_NAMAN.bat`, pywebview ve güncellenen `webview2_editor_smoke.py`. | Linux'ta gerçek Windows çalıştırılmadı; kısa kontrol yukarıda. |
| OpenMontage/Remotion | Mevcut bridge/provider sabit motoru, ayrı kurulum/hazırlık denetimi ve yerel job bağlantısı korunur. | Kod bağı incelendi; motor/model kurulmadı, Windows/GPU çalıştırılmadı. |
| Kesilmiş render | `RenderService` kesilen işi `render_interrupted` yapar; önceki aktif çıktı korunur, yeniden render istenir. | Kod denetimi; tam kaldığı kareden kusursuz devam desteği yok, yeni mimari yazılmadı. |

Kaynaklar ve lisans kayıtları korunur. Freepik/Magnific veya kapalı Pexels yeniden etkinleştirilmez. Harita düzenlemesi mevcut `motion_edit` içinde `local_only=True` kullanır. GPU/uzun render/harici motor ve büyük gerçek arşiv ölçümleri ayrı doğrulama işleridir.
