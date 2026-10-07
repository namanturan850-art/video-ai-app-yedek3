# Kararlılık ve Geliştirme Paketi

Bu paket mevcut proje, senaryo, Gemini/OpenAI anahtarları ve Windows başlatıcısını korur. Önce hata düzeltmeleri test edildi, ardından dil/kalite araçları, son olarak görsel/kurgu hazırlığı eklendi. `.env` veya kaynak kod düzenlemeniz gerekmez.

## Düzeltilen nedenler ve sınırlar

- **OpenAI testi yer tutucuydu.** Şimdi resmi `GET /v1/models/{model}` ile anahtar/model erişimi kontrol edilir. Üretim veya ücretli uzun test yapılmaz. Bu kontrol üretim kotası, bakiye veya Chat Completions uyumluluğunu garanti etmez; bunlar gerçek üretim yanıtında ayrıca değerlendirilir.
- **OpenAI kapalı tercihi açıkça anlaşılmıyordu.** Etkinleştir seçimi, eksik anahtar/model ve erişim sorunları ayrı Türkçe mesajlara sahiptir. Anahtar girmek seçimi kendiliğinden açmaz; kullanıcının kapalı tercihi korunur.
- **Kasa hataları tek genel mesajda birleşiyordu.** DPAPI/Fernet, izin, geçici dosya, atomik değiştirme ve kilit sorunları güvenli kategorilerle ayrılır. Dosya tanıtıcısı değiştirme öncesi kapalıdır; Windows paylaşım/kilit kodları 32/33 için en çok üç deneme (0,1 ve 0,2 saniyelik bekleme) yapılır. Kalıcı hatada eski kasa/anahtar korunur, sıfırlanmaz.
- **Gerçek Windows'taki belirli kaydetme hatasının nedeni bu Linux ortamında doğrudan gözlenemedi.** DPAPI kaldırılmadı veya koruması düşürülmedi. Aynı kullanıcı hesabındaki gerçek Windows kasa akışı için ayrı test hazırlandı; Windows gerektirdiğinden burada atlanır. Taklit kilit ve yazma hatalarıyla kayıtların korunduğu doğrulandı.
- **Gemini 429 hizmetin kota/hız sınırıdır.** Uygulamanın kapalı olduğu anlamına gelmez. Çalışan model keşfi ve Settings süreleri korunur. Tamamlanan bölümler/parçalar ve önceki sürümler saklanır. `Retry-After` dikkate alınır; bildirilmezse 30 saniye, en çok 120 saniye bekleme uygulanır. Otomatik ücretli tekrar veya sessiz sağlayıcı değişimi yapılmaz. Hesabın API kotası bu kodla artırılamaz.
- **OpenAI hata ayrımı:** kapalı sağlayıcı, anahtar yok/reddedildi, model yok/geçersiz, bakiye/kota, hız sınırı, zaman aşımı, internet/proxy ve sunucu/yanıt hatası. Sadece bilinen hata kodları okunur; ham yanıt geri verilmez.
- Güvenli tanılama sağlayıcı, işlem, kategori ve süre içerir. Anahtar, Authorization, istek metni, tam sağlayıcı yanıtı veya stack trace loglanmaz. Sızıntı kontrolleri diğer sağlayıcılarda kayıtlı anahtarları da kapsar.

## Çalışan özellikler

| Özellik | Durum |
| --- | --- |
| Gemini/OpenAI/Ollama Settings, şifreli kalıcılık ve üç senaryo sağlayıcısı | Çalışıyor; dış API sözleşmeleri taklit yanıtlarla test edildi |
| Proje ve Senaryo Hedef Dil | Almanca (`de`, varsayılan), İspanyolca (`es`), İngilizce (`en`), Fransızca (`fr`), Türkçe (`tr`) |
| Genel senaryo/çeviri | Seçilen dil kullanılır; Almanca zorunluluğu kaldırıldı; sahiplik onayı sürer |
| Retention Analizi | İlk 10–30 saniye, hook, yavaşlık, tekrar, geçiş, yoğunluk, tempo, bölüm uzunluğu, merak, vaat karşılığı ve bitiş: Güçlü/Orta/Geliştirilebilir |
| Seçilen retention/hook önerilerini uygulama | Yeni taslak sürüm oluşturur; onaylı sürümü değiştirmek açık onay ister; eski metin korunur |
| Üç açılış hooku | İsteğe bağlı seçim; içeriğe uygun, sahte vaat içermemesi talimatlandırılır |
| A/B alternatifleri | Açılış, başlık, küçük resim yazısı, giriş, CTA ve açıklama için 2–3 seçenek; seçimler ayrı saklanır |
| İddia / Bilgi İncelemesi | Tarih, fiyat, istatistik, sağlık/bilim/tarih/finans/teknik iddialar işaretlenir; doğrulanmış sayılmaz; gelecekte kaynak ekleme alanı hazır |
| Görsel/kurgu planlama | Güncel onaylı senaryodan anlamsal B-roll, alternatif İngilizce sorgular, amaç/duygu/görsel niyet, tür, hedef dilde vurgu yazısı, kompozisyon, önem ve geçiş/hareket önerileri |
| Çeşitlilik ve zamanlama kontrolü | Medya kimliği tekrarını engelleyen kayıt arayüzü; benzer kompozisyon/sabit görsel uyarıları; kelimeye dayalı süreler, gerçek metne eşleşen TTS zamanlaması için veri/API desteği |
| Render öncesi kontrol | Eksik medya/ses/altyazı, eski/onaysız senaryo, uzun blok, tekrar/kompozisyon, dil/çözünürlük, görsel hata, müzik/lisans/ses seviyesi uyarıları |

Analiz ve üretim AI çağrıları arka plandadır. Parçalı kalite analizleri kesilirse tamamlanan parçalar korunur; **Devam Et** ile sürdürülür. Öneriler geçerli senaryo sürümüne bağlıdır; başka sürüme sessizce uygulanmaz. A/B seçimlerini kaydetmek senaryo metnini değiştirmez. İçerik türleri serbesttir; sistem hikâye veya küçük bir kategori listesiyle sınırlanmaz.

## Hazırlanan, henüz çalıştırılmayan özellikler

- Pexels → Pixabay → yerel görsel → izinli bulut sırası. Stok arama/indirme henüz bağlı değildir; sorgular gerçek medya bulunmuş gibi gösterilmez. StockProvider arayüzü hazırdır.
- ImageProvider: yerel GPU/ComfyUI, resmi Gemini ve resmi OpenAI adaptörleri. Settings ve bağlantı/model listesi kontrolleri çalışır. Bulut görsel istek/yanıt adaptörleri taklit API ile doğrulandı; **arayüzden/otomatik gerçek görsel üretimi çalıştırılmaz**.
- ComfyUI bağlantısı ve kurulu checkpoint listesi alınabilir. RTX 5070'yi yerel backend yönetir; uygulama CUDA/driver/model indirmez. Workflow adı/lisans tercihi kaydedilir; API workflow grafiğinin çalıştırma eşlemesi sonraki aşamadadır. Modelin ticari YouTube lisansını kullanıcı kontrol eder.
- Google'ın model listesi erişilebilir modelleri döndürür; `generateContent` desteklemek görsel çıkışı desteklediğini kanıtlamaz. Görsel yeteneği seçilen modelin resmi belgesinde kontrol edilmelidir. Model adı tahmin edilmez. OpenAI'de erişilebilir resmi görsel model adı kullanıcı tarafından kaydedilir. Mevcut şifreli anahtarlar yeniden kullanılır; web Pro aboneliği API erişimi sağlamaz.
- Hard cut/crossfade/fade, zoom/pan/Ken Burns/overlay/vurgu ve geçişsiz kurgu **öneridir**; FFmpeg uygulanmaz. Her blok tek sabit süreye zorlanmaz.
- Yerel lisanslı müzik adı, duygu, ses seviyesi, fade, ducking ve bölüm değişimi tercihleri kaydedilir. Müzik dosyası henüz içe aktarılmaz veya işlenmez; ticari müzik indirilmez.
- TTSProvider ve RenderProvider arayüzleri hazırdır. Seslendirme, gerçek altyazı üretimi, sesle kurgu, render ve yükleme çalıştırılmaz. AI33 belgeleri hâlâ gerekli. Gerçek TTS zamanları sonradan sağlandığında blok metnine/sırasına eşleştirilebilir; bugün tahminler gerçek ses süresi olarak gösterilmez.

## Ücret koruması

**Ayarlar → Görsel Üretimi → Ücretli AI kullanımı** varsayılan **KAPALI**:

- Ücretli API'yi otomatik kullanma.
- Ücretli kullanım öncesi sor.
- Ücretli fallback'e izin ver — arayüz ayrıca açık onay ister.

Bu tercihler gelecekteki görsel çalıştırma seçimini hazırlar; bugün otomatik image dispatch yoktur. Varsayılan planda ücretli fallback seçilemez. Yerel model ancak etkin/lisansı onaylanmış/model ve workflow tercihi verilmişse adaydır. Stok varsa öncelik stoktur. İlgisiz görüntü yalnızca çeşitlilik için önerilmez.

Senaryo, çeviri, retention, hook, A/B, iddia incelemesi, öneri uygulama ve görsel **planlama** Gemini/OpenAI ile API kotası veya ücret kullanabilir; düğmeye basınca işlem için açıklamalı onay gösterilir. Kalite/planlama API'si de onay bayrağı ister. Gemini'nin ücretsiz API kotası sınırlı olabilir. Ollama yereldir, ücretli API gerektirmez; donanım/elektrik kullanır. Bağlantı/model listesi testleri içerik üretmez. Hiçbir hata başka ücretli sağlayıcıya sessiz geçmez.

## Bir Windows kontrol listesi — kod/komut gerektirmez

1. **Açılış ve Ayarlar:** `START_AI_VIDEO_STUDIO.bat` dosyasına çift tıklayın. Siyah pencereyi açık bırakın. Mevcut projelerinizin listede olduğunu görün.
2. **Gemini:** Ayarlar'da mevcut maskeli anahtar/model korunmalı. **Modelleri Getir → model seç → Kaydet → Bağlantıyı Test Et**; Hazır beklenir. Anahtarı yeniden girmeniz gerekmez.
3. **OpenAI:** **Etkinleştir** seçimini açın, API anahtarı ve erişilebilir Chat Completions modelini girip **Kaydet → Bağlantıyı Test Et**. Alan boşalmalı, yalnızca maske görünmeli. Uygulamayı kapatıp yeniden açın: hem Gemini hem OpenAI kalmalı. OpenAI anahtarını güncelleyip Kaydet deyin; sonra yalnızca OpenAI **Temizle** deyin. Gemini aynı kalmalı. İsterseniz OpenAI'yi tekrar kaydedin. Test erişim kontrolüdür; bakiye üretim sırasında ayrıca kontrol edilir.
4. **Ollama (kuruluysa):** Ollama'yı açın. Ayarlar'da yerel adresi ve kurulu modelin tam adını kaydedip test edin. Kullanmayacaksanız boş bırakabilirsiniz; NVIDIA kullanımını Ollama yönetir.
5. **Senaryo:** yeni veya mevcut projede **Senaryoyu Aç**, hazır sağlayıcıyı seçin. İlk deneme 1–5 dakika olsun. **Analiz Et → Senaryo Oluştur**; bulut maliyet uyarısını okuyun. Kota hatasında uygulamayı silmeyin: bekleyip **Devam Et** deyin. Farklı sağlayıcıyla yeni üretim yapılabilir; önceki sürüm korunur.
6. **Dil:** Yeni Proje'de örneğin **İspanyolca**, Senaryo'da aynı dili kontrol edin. Bir kısa üretim deneyin. **Kendi Metnimi Seçili Dile Çevir** için yalnızca kendi metninizi yapıştırıp sahiplik onayı verin. Çıktının seçilen dilde olduğunu okuyarak kontrol edin.
7. **Retention:** oluşturulmuş metinde **Retention Analizi**. Sonuç başlığını açıp puan/önerileri görün. Bir öneriyi seçip **Seçilenleri yeni sürüme uygula** deyin; yeni sürüm oluşmalı, eski sürüm kalmalı. Onaylı metni değiştirirken ayrıca onay sorulmalı.
8. **Hook / A/B / iddialar:** **3 Açılış Hooku**, **A/B Alternatifleri**, **İddia / Bilgi İncelemesi** düğmelerini deneyin. Bir hook seçip uygulanmasını isteyebilirsiniz. A/B'de seçip **Alternatif seçimlerini kaydet** deyin; mevcut metin değişmemeli. İddialar doğrulanmış olarak gösterilmemeli.
9. **Görsel ayarları:** Ayarlar → **Görsel Üretimi**. Ücretli kullanım KAPALI olmalı. ComfyUI kuruluysa yerel sağlayıcıyı açıp **Kaydet → Yerel Modelleri Getir → model seç**; ticari lisansı kontrol edip onaylayın, Kaydet ve test edin. Kurulu değilse bağlantı hatası normaldir. Gemini görsel modeli için ayrı resmi liste/test, OpenAI için ayrı görsel model alanı vardır. Bu işlemler gerçek görsel üretmez.
10. **Ücretli fallback ve plan:** varsayılan KAPALI tercihini koruyun. Senaryonun son halini **Onayla**. Projeye dönüp **Görsel / Kurgu Planı ve Kalite Kontrolü** açın. Hazır sağlayıcı seçip planı hazırlayın. B-roll, vurgu ve sürelerin öneri/tahmin olduğunu; eksik medya/ses uyarılarını görün. Müzik tercihi kaydedilebilir, dosya işleme henüz yoktur. Render/yükleme düğmesi yoktur.
11. **Yeniden açılış:** kapatıp tekrar aynı `.bat` dosyasına çift tıklayın. Projeler, senaryo sürümleri/onay, kalite sonuçları, görsel plan ve ayarlar kalmalı. Üretim ortasında kapanmışsa otomatik ücretli devam değil, açık **Devam Et** olmalı.

Gerçek Windows kasa/ComfyUI/RTX ve canlı API kalite testleri bu Linux ortamında yapılamadı. Bu liste kalan gerçek cihaz doğrulamasıdır; mevcut verilerinizi silmeyin. AI'nin dil, bilgi, özgünlük ve öneri kalitesini onaylamadan önce kontrol edin. Claim Review araştırma yapmaz, retention puanları izlenme garantisi değildir.

## Teknik doğrulama ve sözleşmeler

SQLite şema **5**, eski 1/2/3/4'ten işlemsel eklemeli yükseltme: sürüm bağlı `script_artifacts` ve `project_production`. Eski proje/senaryo/ayar verileri ve zamanlar korunur. Kalite sonuçları ve görsel plan okunabilir JSON olarak script klasörüne de yazılır. Senaryo sürümleri değişmez; aktif iş sırasında kayıt/silme/medya tercihlerini değiştirme engellenir. Önceki onaylı senaryonun görsel planı sürüm değişirse eski olarak işaretlenir.

Doğrulanmış kaynaklar (2026-10-07):

- [OpenAI resmi Models kaynağı — GET /models/{model}](https://github.com/openai/openai-python/blob/main/src/openai/resources/models.py)
- [OpenAI resmi Chat Completions sözleşmesi](https://github.com/openai/openai-python/blob/main/src/openai/resources/chat/completions/completions.py)
- [OpenAI resmi Images — POST /images/generations, model/prompt/n, b64_json yanıtı](https://github.com/openai/openai-python/blob/main/src/openai/resources/images.py)
- [Google resmi GenerativeService — responseModalities, IMAGE](https://github.com/googleapis/googleapis/blob/master/google/ai/generativelanguage/v1beta/generative_service.proto)
- [Google resmi Content/Part — inlineData/mimeType/data](https://github.com/googleapis/googleapis/blob/master/google/ai/generativelanguage/v1beta/content.proto)
- [ComfyUI resmi server — GET /system_stats, /object_info/{node_class}](https://github.com/Comfy-Org/ComfyUI/blob/master/server.py)
- [ComfyUI resmi düğüm tanımı — CheckpointLoaderSimple/ckpt_name](https://github.com/Comfy-Org/ComfyUI/blob/master/nodes.py)
- Mevcut [Gemini](GEMINI.md) ve [Senaryo](SCRIPT_ENGINE.md) resmi kaynakları korunur.

Harici API'ler taklit edildi; gerçek anahtar veya ödeme kullanılmadı. Test sonuçları ve tarayıcı doğrulaması [STATUS](STATUS.md) içinde günceldir. Uygulamanın açılışı için Node, GPU veya API anahtarı gerekmez.
