# NAMAN 2.0 — Stok medya kurtarma teslim raporu

18 Ekim 2026. Taban: `3e827cf4da32550bf5eb83156828e6835a41432c` (main, PR #90–#93 dahil). Dal: `fix/naman-stock-media-recovery`. Main'e merge yapılmaz.

## Kök nedenler ve uygulanan çözüm

| Sorun | Kanıtlanan neden | Değişiklik |
|---|---|---|
| São Paulo Üniversitesi → şehir görüntüsü | Kurumun içindeki yer adı, görsel özne ve sahne coğrafyası olarak kullanılabiliyordu. | Araştırma atfı ile ayrı görsel konu birlikte bulunduğunda kurum adı görsel sorgudan/coğrafyadan çıkarılır. Özgün anlatım korunur; açık kullanıcı görsel notu önceliklidir. |
| Göl akıntısı → şelale | Sözlük suyu büyük ölçüde deniz kavramına indirgerken göl, akıntı, rüzgâr ve şelaleyi ayırmıyordu. | Ayrı çok dilli kavramlar; açık şelale/şehir/diğer özne çelişkisi metadata, yerel sıralama ve CLIP onayından önce engellenir. |
| Göl/yıldırım aramasının yalnız gece yansımasına bağlanması | Cümleye bağlı arama ile eski plan sorguları arasında olay/özne önceliği yoktu. | Anlatımda gerçekten bulunan kavramlardan olay → nesne/çevre → bağlam sorguları türetilir. Yeni ülke, şehir, tarih veya gece bilgisi eklenmez. Sabit Venezuela sorguları yoktur. Bilinmeyen konularda mevcut plan korunur. |
| CLIP 4–5 puanın kolayca onaylanması | Bulan sorgunun kelimeleri de medyanın kendi içeriğine kanıt sayılabiliyordu. | Arama provenance'ı uygunluk kanıtı sayılmaz. Kararsız CLIP ancak güçlü bağımsız metadata veya doğrudan adlandırılmış arşiv desteğiyle aşılabilir; açıklama kaydedilir. Açık konu çelişkisi CLIP 9/10 olsa da elenir. |
| Aynı boş yuvanın aynı aramaları yapması | Oturum önbelleği vardı; yuva bazında kalıcı başarısız deneme kaydı yoktu. | SQLite stok planında sağlayıcı/tür/sorgu/sayfa/sonuç/önbellek/hata/zaman ve bağlam izi tutulur. Aynı başarısız deneme 1 saat atlanır; bağlam/dönem değişimi ve süre aşımı yeniden denemeye izin verir. Sağlayıcı hataları kalıcı başarısız sorgu sayılmaz. Sonuçsuz olduğu kanıtlanan sayfanın sonraki sayfaları gereksiz çağrılmaz. |
| Hiç görsel seçilememesi | Video ağırlıklı ek sayfa araması, eksik kanıt ve teknik/tekrar elemesi birlikte etkiliydi. | Yerel arşiv önce; ardından ilgili video, alternatif video, ilgili görsel ve izinli ek sayfalar. Görseller aynı kalite/uygunluk/tekrar kontrolünden geçer. Yalnız sayı doldurmak için seçim yapılmaz. |
| `undefined: missing` | `sources_only` adımının label alanı eksikti; UI bilinmeyen değerleri doğrudan yazıyordu. | Backend label, Türkçe missing açıklaması ve bilinmeyen aşama/sonuç için güvenli UI varsayılanı. |
| Tanılama Windows'ta inmiyor | pywebview 6.1 kaynak kodunda `ALLOW_DOWNLOADS=False`; WebView2 indirmeyi iptal ediyor. | `ALLOW_DOWNLOADS=True`; mevcut WebView2 SaveFileDialog etkin. JSON önce doğrulanır; tarayıcı indirmesi, destekli tarayıcıda dosya seçici, kopyalama ve seçilebilir metin alternatifi eklenir. |

## Davranış ve korunan sınırlar

- Varsayılan Manuel Kurgu değişmedi. Manuel hazırlama, ayarlı ücretli sağlayıcı bulunsa bile otomatik bulut çevirisi çağırmaz; kayıtlı çevirileri okuyabilir. Yeni çeviri açık düğme isteğine bırakılır. Kaynak hazırlama; kart, motion, komşu kliple otomatik birleştirme veya şerit üretmez. İnfografik yalnız önerilir; açık **Motion'a Çevir** işlemi çalışmaya devam eder. Mevcut manuel timeline belgesi değiştirilmez.
- Kilitli seçim, kullanıcı kaynakları ve sağlam indirilmiş dosyalar korunur. Kilitli medyanın metadata'sı da sayfa açılışında değiştirilmez; güncel uygunluk göstergesi ayrı hesaplanır. İçerik hash'i, aynı videonun yakın sahnelerde kullanılması, dosya süresi/kalitesi ve lisans kontrolleri kaldırılmadı.
- Pixabay/Wikimedia ve önceden yapılandırılıp hazır durumdaki OpenMontage desteklenir. Pexels, OpenMontage'ın yeni kaynak çağrılarında da seçilmez. Freepik/Magnific veya ücretli görsel üretimi eklenmedi.
- Arama bütçesi yuva başına 24, iş başına 120 farklı sağlayıcı/tür/sorgu/sayfa geçişidir; önbellekli çağrılar ağ isteği diye sayılmaz. Bu sınırlar, bütün alternatiflerin tek tıklamada tüketileceği anlamına gelmez: denenmeyen alternatifler **bütçe** olarak gösterilir ve sonraki denemede ilerlenir. Sağlayıcı cooldown/429 koruması sürer.
- Boş sonuç önbelleği 5 dakika; dolu sonuçların mevcut 24 saatlik süresi korunur. Bir yuvanın son 300 gerçek arama kaydı ve son 5 çalışma özeti saklanır. Panelde son 100 kayıt gösterilir; JSON saklanan kayıtların tamamını içerir. Sınırsız tarihçe garantisi verilmez.
- Eksik tanısı bağımsız kaydırmalı açılır bölümdedir. Benzersiz genel yuva numarası, zaman, anlatım, görsel amaç/konu, sorgular, sağlayıcılar, video/görsel sonuçları, eleme, CLIP, önbellek ve hata bilgisi gösterilir. Tek yuvada **Yalnız yeni alternatifleri ara** kullanılabilir.
- Coğrafya sayacı son işte reddedilen tekil adayları sayar; eksik yuva sayısı değildir. Teknik eleme tablosu aday geçişlerini sayar; aynı adayı farklı sorgularda yeniden görmüş olabilir. Bu kapsam UI'da belirtilir.
- Tanı dosyası seçili projenin yuva cümlelerini ve arama kanıtını içerir; tam senaryo dosyası, ses dosyası, yerel medya yolu, indirme URL'si ve anahtar içermez. Mevcut SecretGuard son yanıtı ayrıca doğrular. Uygulama genelindeki Gemini model/hata zamanları yalnız model tanısıdır; istek içerikleri dışa verilmez.
- Dosya seçicide kaydedilen dosya adı ve kullanıcının seçtiği klasör bilgisi gösterilir. Tarayıcı/WebView2 akışında “indirildi” diye doğrulanmamış başarı yazılmaz; native kaydetme penceresi veya tarayıcının İndirilenler bölümü konumu gösterir. JavaScript'e keyfi yerel dosya okuma/yazma köprüsü açılmaz.

## Test kanıtları

İlgili dosyalarda **478 benzersiz Python senaryosu** seçildi. Parçalı regresyon koşuları ve hata düzeltmelerinden sonraki odaklı tekrarlar birlikte değerlendirildiğinde **476 başarılı, 2 atlanan** senaryo vardır. Örtüşen tekrarlar bu toplama ikinci kez eklenmedi.

Doğrulanan gruplar:

| Grup | Sonuç |
|---|---|
| Stok API/dosya koruma/medya testleri | 80 geçti; sonradan eklenen 2 bütçe/ücretli çeviri yasağı senaryosu da geçti |
| Semantik uygunluk, sorgu, önbellek ve performans | 203 geçti |
| Son etkilenen alanların tekrarı | 15 geçti; ayrıca çeviri/yardım grubu ile 17 geçti (diğer gruplarla örtüşür) |
| Gerçek FFmpeg kalite/render dosyası | 16 geçti |
| Legacy tamamlama/marker/görsel kontrol | 69 ilk koşuda geçti; CLIP uyarısındaki 1 hata düzeltildi ve ilgili senaryo son 15 testlik tekrarda geçti |
| Tüm JavaScript/DOM dosyaları | 70 geçti |
| Gerçek Chromium smoke | Geçti; 0 JS hatası |

Diğer uyumluluk grubunda 119 test geçti, 2 test atlandı. İki font karşılaştırması temiz `main` arşivinde de aynı biçimde başarısızdı; üretim altyazı koduna dokunulmadı. Test artık profilin bilerek değiştirdiği `fs` boyutunu metin/zaman karşılaştırmasından ayırır; stil kontrolleri ayrı kalır. Düzeltme sonrası ilgili dosyanın 16 testi yeniden geçti. Bu gruplar örtüşür; sayıları toplanmaz. İki atlama ayrı kurulu harici OpenMontage checkout gerektiren isteğe bağlı smoke testleridir. Kurulu motor veya Windows varmış gibi başarı yazılmadı. CLIP bulunmadığı bilgisinin legacy yolda yanlışlıkla silinmesi de düzeltildi; düşük puanlı CLIP kontrolü ile hiç model kontrolü yapılmamış kaynak artık ayrı açıklanır.

- Gerçek API/SQLite/indirme ve PNG çözme: 32 yuva, 3 benzersiz uygun görsel, 29 eksik, **0 motion**. Test kitaplığında başka uygun benzersiz kaynak yoktur; 32/32 zorlanmadı. Aynı başarılı dosyalar ikinci çalıştırmada tekrar indirilmedi; kilitli seçim ve manuel belge korundu. Tek yuvanın yeniden aramasında önceki başarısız denemelerin atlandığı doğrulandı.
- Sağlayıcılar HTTP/fabrika sahte yanıtlarıdır; canlı Pixabay/Wikimedia başarısı veya kullanıcının gerçek projesinin 32/32 dolacağı iddia edilmez. API anahtarları sentetiktir, ücretli çağrı yapılmadı.
- Gerçek Chromium: 32 yuvalı tanı JSON'u indirildi; panoya yazılıp geri okundu; pano izni reddinde seçilebilir JSON sunuldu. HTTP hatası, kaydetme iptali, kaydetme adaptörünün write/close akışı ve yabancı origin için 403 doğrulandı. JavaScript hatası yok. Ölçüm: `stock-recovery-metrics.json`; görsel: `stock-recovery.png`.
- CLIP karar testleri gerçek model ağırlığı çalıştırmaz; kontrollü puanlarla çelişki/kararsızlık/doğru arşiv politikası sınanır. Gerçek görüntü kalitesi, FFmpeg ve render regresyonları ilgili test grubundadır.
- Eski yaratıcı tamamlama/marker testleri açıkça legacy proje kurar; üretimde yeni varsayılan Manuel mod değiştirilmemiştir. Yeni 32 yuva testi ve mevcut manual-first testleri kaynak hazırlama ayrımını ayrıca denetler.

## Windows/WebView2 açık doğrulaması

Bu Linux ortamında fiziksel Windows ve native SaveFileDialog doğrulanmadı. Python masaüstü testi indirme ayarını ve sunucu kapanışını doğrular; Chromium testleri native Windows doğrulaması yerine geçmez.

Windows smoke adımları:

1. NAMAN'ı normal başlatıcıdan açın; bir projenin Üretim/medya bölümünde **Tanılama dosyası indir** seçin.
2. WebView2'nin **Farklı Kaydet** penceresinde yazılabilir bir klasör ve `.json` adı seçin. Dosyanın seçtiğiniz klasörde oluştuğunu, JSON olarak açıldığını kontrol edin. Penceredeki konumu doğrulayın.
3. Kaydetmeyi iptal edin; uygulama/timeline kapanmamalı veya değişmemeli. WebView2 iptali web sayfasına bildirmezse UI yalnız “indirme iletildi” durumunda kalabilir; bu bir kaydedildi bildirimi değildir.
4. **Tanıyı Kopyala** ile bir metin düzenleyiciye yapıştırın. Pano engelleniyorsa sunulan seçili metni Ctrl+C ile kopyalayın.
5. Yalnız yeni alternatifleri tek boş yuvada aratın; kilitli kaynakları ve Manuel Kurgu belgesini karşılaştırın. Uygun kaynak yoksa boşluk ve gerekçesi kalmalıdır.

## Yayın

Kodun ilk iki commit'i `24eb760` ve `4341e35` GitHub'a gönderildi; son doğrulama düzeltmeleri ve bu rapor aynı dala son teslim commit'iyle eklenir. Dal: [fix/naman-stock-media-recovery](https://github.com/naman85331/video-ai-app/tree/fix/naman-stock-media-recovery).

Draft PR oluşturma hem `gh pr create --draft` (GraphQL) hem GitHub REST `POST /repos/naman85331/video-ai-app/pulls` ile denendi; ortam ikisinde de **403 Forbidden** döndürdü. **PR oluşturulamadı.** Git push çalışıyor; bu hata kodun gönderilmediği anlamına gelmez. Main'e merge yapılmadı.

[Hazır karşılaştırma / PR formu](https://github.com/naman85331/video-ai-app/compare/main...fix/naman-stock-media-recovery?expand=1)

Hazır PR başlığı: **fix: NAMAN stok medya kurtarma ve tanılama**

Hazır açıklama:

> Medya araması kaynak kurumu görsel konuyla karıştırabiliyor ve boş yuvalarda aynı başarısız sorguları tekrarlıyordu. Görsel konu/atfı ayrılır; açık konu çelişkileri engellenir; yerel arşiv, video ve görsel alternatifleri kalıcı, bütçeli arama kanıtıyla denenir. Düşük CLIP puanı ancak güçlü bağımsız metadata ile aşılabilir. Kilitli medya ve mevcut dosyalar korunur.
>
> Manuel kaynak hazırlama yaratıcı öğe üretmez. Eksik yuva tanısı, JSON indir/kopyala ve WebView2 native kaydetme desteği eklenir. Pexels etkinleştirilmez. Test ayrıntıları ve Windows açık doğrulaması `docs/STOCK_MEDIA_RECOVERY_DELIVERY.md` içindedir. Main'e merge için kullanıcı onayı gerekir.
