# Medya hazırlama performansı — 16 Ekim 2026

Dal: `improve/media-preparation-speed-quality`. Başlangıç: güncel `main`, `cab809cea55aaca59556af7ed730f25e05181176` (PR #80 dahil). Bu çalışma yalnız bulutta yapıldı. Windows’taki iş, projeler, senaryolar, medya, kilitler ve veritabanı kullanılmadı/değiştirilmedi. Ana dala birleştirme ve dağıtım yapılmadı.

## Kök nedenler ve değişiklikler

- Arama önbelleği anahtarı büyük/küçük harf ve boşluk farklarını ayrı tutuyordu; eşzamanlı önbellek kaçırmaları aynı API isteğini tekrarlayabiliyordu. Sorgu + sağlayıcı + tür + sayfa + ayar kimliği ile paylaşım eklendi. 24 saatlik SQLite önbelleği ve eski anahtarlar korunur; iş belleğinde en fazla 512 sonuç tutulur. Yakın anlamlı fakat farklı sorgular körlemesine birleştirilmez.
- Her işin bağımsız aday kopyaları vardır: bir cümleye ait değerlendirme diğerinin adayına yazılmaz. Sağlayıcı başına en fazla iki okuma; 429’da HTTP Retry-After, geçici hatalarda artan bekleme; başarısız sağlayıcı aynı işte tekrar zorlanmaz. Devam Et yeni denemeye izin verir. Açıkça boş sağlayıcı listesi ücretsiz kaynaklara yanlışlıkla geri dönmez. Ham sonuç sıfırsa veya doğrulanmış son sayfaya gelindiyse sonraki sayfalar denenmez. Uygun ve kalite kontrolünden geçen seçimde mevcut erken durma korunur.
- CLIP modeli zaten kalıcı worker içinde bir kez yükleniyor ve model sürümü + kare hash’i ile embedding önbelleği kullanıyordu. Bunlar yeniden yazılmadı. Artık bir aday grubunun eksik kare vektörleri birlikte hazırlanır; inference en fazla 24 kare/metinlik paketlere ayrılır. 4096 vektörlük mevcut sınır korunur. Metin boşlukları normalize edilir; cümle sırası/bağlamı korunur. Karar önbelleği farklı anlatım/kurallar/model, kare adresi veya indirilmiş dosya hash’i için ayrı kalır. Eşikler gevşetilmedi.
- Önizlemelerin tekrar okunması, küçültülmesi, base64’e çevrilmesi ve başarısız örnek kare indirmeleri iş içinde 32 MB / 512 kayıtlık önbellekle azaltıldı. Anahtar medya kimliği + önizleme adresleri + örnek adresi + süredir. Aynı kimlikte önizleme değişirse eski kare kullanılmaz.
- İspanyolca `solo` → GeoNames `Surakarta`, `para` → `Belém` eşleştirmesi yerel sözlükle yeniden üretildi. İşlev kelimeleri yer adı aramasından önce temizlenir. `Pero` elenir. Tam yer adı, kelime kökü çevirisinden önce korunur. Sahne Tijuana/Monterrey diyorsa başka ülke/şehir arama ve CLIP açıklamasına taşınmaz. Amerika kıtası otomatik olarak ABD sayılmaz. Sahnenin kendi coğrafyası video çoğunluğundan önce gelir; Modern seçimi coğrafyayı bastırmaz. Maracaibo/Catatumbo örnekleri kapsandı. Bilinmeyen yerler için ülke uydurulmaz.
- Hash kontrolü kaldırılmadı. Dosya ilk kullanımda SHA-256 ile doğrulanır; aynı işlemde dosya yolu/kimliği/boyutu/mtime/ctime ve beklenen hash değişmedikçe sonuç paylaşılır. Okuma zamanı (atime) değişikliği yanlış yeniden indirmeye neden olmaz. Yeniden başlatmada tekrar hash alınır. Kalite kontrolü dosya imzası + hash + gerçek segment başlangıcı + tür + kontrol sürümüne bağlıdır; ayrı segment ayrıca kontrol edilir.
- Motion çıktısının mevcut şablon/veri/süre/motor sürümü içerik anahtarı korundu. Aynı içerik aynı klasörde eşzamanlı istenirse ilk render paylaşılır; bekleyen iptal edilebilir. Mevcut Remotion → FFmpeg/Pillow geri dönüşü ve `motion-v6` korundu.
- Uyarlanabilir tempo yalnız yeni projelerin ilk medya planlarında kullanılır. Kayıtlı planlar aynı handoff ile aynen döner; eski aralıklar, kilitler ve tamamlanmış seçimler yeniden oluşturulmaz. Konuşma hızı, cümle sınırları, sayısal/özel ad yoğunluğu, önem, yönetmen çekim sayısı ve motion/işaret ihtiyacı dikkate alınır. 180–220 bir hedef örneğidir; sınır veya garanti değildir.
- Ekran ve tanı dosyası: arama, CLIP, judging, indirme+kontrol, motion süreleri; arama/önizleme/karar/vektör/kalite/motion önbelleği, benzersiz sorgular, başarılı sağlayıcı aramaları, API hataları, kalan yuvalar ve aktif geçen süre. CLIP, judging içinde yer alır. Aşama süreleri toplanmaz; paralel aramalarda birikimli değerler gerçek duvar süresinden farklıdır. Yeni ölçümlerde gizli URL/API anahtarı yoktur.

## Freepik / Magnific ve Wikimedia: kanıtın sınırı

Magnific’in gerçek işteki 64 sıfır sonucunun nedeni **kanıtlanmış değildir**: bu oturumda gerçek yanıt gövdesi, izin/kota bilgisi veya hesap erişimi alınmadı. Mevcut `/v1/videos`, parametre ve header sözleşmesi değiştirilmedi; yeni API şeması tahmin edilmedi. Sentetik testler gerçek boş listeyi, tüm sonuçların AI/önizlemesiz olarak elenmesini, tüm öğelerin bozuk şema yüzünden okunamamasını, 401/403 ve 429’u ayrı gösteriyor. Önceden tamamen bozuk öğeler sessizce boş sonuç olabiliyordu; şimdi `invalid_response` olur. Özet sayılar tanı dosyasına eklenir. API boş sonucu tek başına yanlış sorgu kanıtı değildir.

Wikimedia’da maxlag/kota, API hata nesnesi ve bozuk liste şeması boş sonuç sayılmaz. Lisans/yönlendirme/medya türü yüzünden elenenler hata ile karıştırılmaz. Devam eden Windows işinin `invalid_response` kök nedeni canlı yanıt olmadan belirlenemez. Mevcut Premium anahtar koruması ve lisans güvenlik kontrolleri korunur.

## Sentetik 15 dakika karşılaştırması

Aynı `tools/benchmark_media_preparation.py`, başlangıç commit’inin ayrı kopyasında ve geliştirme kodunda üçer kez çalıştırıldı. Her deneme 900 saniyelik bir video iş yükünü **temsil eder**, 15 dakika video render etmez. Sağlayıcı ve embedding işlevleri sahte, medya dosyaları geçicidir. Ölçüm gerçek geçen `perf_counter` süresidir; aşama toplamı değildir.

| Ölçüt | Önce | Sonra |
|---|---:|---:|
| Medyan geçen süre | 2,8531 sn | 1,6717 sn |
| Üç koşum | 2,8690 / 2,7378 / 2,8531 sn | 1,6717 / 1,5925 / 1,6734 sn |
| Arama katmanına gelen istek | 834 | 834 |
| Benzersiz normalize sorgu | 40 | 40 |
| Alt arama katmanı okuması | 834 | 40 |
| Sahte sağlayıcı araması | 80 | 40 |
| Önizleme hazırlama | 3702 | 240 |
| CLIP değerlendirme | 617 | 617 |
| Görüntü embedding paketi | 240 | 40 |
| Metin embedding paketi | 140 | 140 |
| Kalite doğrulama | 61 | 61 |
| Sentetik uygunluk beklentisi | 617/617 | 617/617 |
| Yeni 900 sn örnek plan | 240 yuva | 210 yuva |

Sahte sağlayıcı 2 ms/arama, görüntü embedding 2 ms/paket gecikmesi kullanır. Sentetik medyan süre azalışı %41,4’dır; gerçek GPU/CPU, internet, stok bulunabilirliği veya görsel doğruluğu için hız/kalite garantisi değildir. `main` zaten bazı tekrarları önbelleğe aldığı için “834 gerçek API çağrısı 40’a indi” denmez. Kalite doğrulama sayısında ek kazanç iddia edilmez; aynı segment zaten önbellekleniyordu. Karar sayısı korunur, pahalı hazırlık paylaşılır. Motion render bu mikro ölçümde karşılaştırılmadı; ayrı eşzamanlılık testi vardır. Ham sonuçlar `MEDIA_PREPARATION_BENCHMARK_20261016.json` dosyasındadır.

## Test durumu

- Son hedefli Python paketi: **176 geçti** (303,29 sn). Son ek parse/medya değişimi/önbellek kontrolleriyle **48 geçti** (12,98 sn); bunların 45’i yeni regresyon, 3’ü mevcut karar önbelleği testidir. Paketler örtüşür: **179 benzersiz hedefli test** kapsanır; 176 + 48 diye toplanmaz.
- Temel paket: `test_media_preparation_performance.py`, `test_quality_performance.py`, `test_setting_check.py`, `test_stock_media.py`, `test_magnific_integration.py`, `test_wikimedia.py`, `test_stock_frontend.py`. Kilitler, resume, eski sorgu önbelleği, TTL, eşzamanlı işler, 429, şema hataları, model/kare değişimi ve eski planın aynen korunması kapsandı.
- İlk testlerde görülen atime kaynaklı yeniden indirme düzeltildi ve kilit/seçim/resume regresyonları tekrar geçti. Yeni bir testin Güney Amerika’yı da yer saymaması gerektiğini varsayan hatalı beklentisi düzeltildi: Güney Amerika geçerli yer olarak korunur, “America” tek başına ABD’ye dönüşmez. Son koşumlarda bu hatalar yoktur.

- Medya/altyazı/ayar/metrik JavaScript işlevleri: **45 geçti** (`node --test --test-isolation=none ...`). `node --check app/static/stock.js` ve Python compile kontrolü geçti.
- Geniş frontend paketi: **45 geçti, 16 başarısız**. Aynı 16 hata değişikliksiz `cab809c` üzerinde de yeniden üretildi: render/smart-edit DOM test sahtelerinde `document.createTextNode` eksik. Bu dalın performans koduna ait değiller; kapsam dışı test yardımcıları değiştirilmedi.
- `test_fast_media` içindeki üç CLIP/fallback regresyonu hem önce hem sonra **3/3 geçti**. Bunlar gerçek model yerine sahte skorlayıcı kullanır.
- Tam Python paketi denemesinde ücretsiz kısa FFmpeg kamera/layout/ses-kaynak koruma kontrollerinden **43 geçti**; uzun render ağırlıklı geniş tarama sonlandırılıp ilgili medya testlerine odaklanıldı. **Tüm 2100+ test geçti iddiası yoktur.**
- Bu bulut sandbox’ında asyncio’nun thread-safe uyandırması bağımsız örnekte takıldı. Yalnız `/workspace/work/pytest_runtime.py` test başlatıcısında EpollSelector bekleme aralığı 20 ms ile sınırlandı; uygulamaya/test deposuna eklenmedi. Normal Node izole test çalıştırıcısı alt testleri raporlamadığı için doğrudan `--test-isolation=none` ile de çalıştırıldı. Bu nedenle Python frontend sarmalayıcısının beklediği `# pass 3` çıktısı normal modda ortam kaynaklı başarısız olabiliyor.

## Açık kalan doğrulamalar

Gerçek 10–15 dakika video hazırlama süresi, gerçek CLIP/GPU hız ve bellek ölçümü, canlı Magnific/Wikimedia yanıt şeması/kota/lisans davranışı, gerçek Premium indirme, Windows/NTFS üzerinde davranış ve kurulu OpenMontage/Remotion ile uçtan uca render henüz doğrulanmadı. Bunlar tamamlandı diye raporlanmaz. Ücretli/canlı/üretim testleri ayrıca ön onay gerektirir; bu oturumda yapılmadı. **30–45 dakika hedefi henüz gerçek ölçümle doğrulanmadı.**

Kullanım hakkı kesilirse tamamlanmış GitHub commit’leri korunur; bu rapor kalan işleri gösterir. Otomatik devam mekanizması kurulmadı. Çalışan Windows işi için güncelleme, yeniden başlatma, migrasyon veya `git pull` talimatı verilmez.
