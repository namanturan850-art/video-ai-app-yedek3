# Aşama 4 — Genel YouTube Senaryo Motoru

Güncel paket Almanca varsayılanını koruyarak İspanyolca, İngilizce, Fransızca ve Türkçe ekler; çeviri modu **Kendi Metnimi Seçili Dile Çevir** adını taşır. OpenAI Settings erişim testi artık gerçektir. Retention/hook/A-B/iddia araçları, görsel/kurgu hazırlığı, ücret koruması ve güncel tek Windows kontrol listesi: [Kararlılık ve Geliştirme Paketi](STABILITY_AND_ENHANCEMENTS.md). Aşağıdaki Aşama 4 test sayıları önceki doğrulama kaydıdır; güncel sonuç [STATUS](STATUS.md) içindedir.

Bu sistem yalnızca hikâye üretmez. Konuyu ve varsa kullanıcı tarafından verilen referans notlarını analiz eder; uygun içerik türünü, konsepti ve bölüm yapısını AI belirler. Belgesel, teknoloji karşılaştırması, liste, eğitim, haber/yorum, anlatı ve serbest içerik türleri aynı motoru kullanır. İçerik türü alanındaki örnekler sınırlama değildir.

## Windows'ta ilk gerçek Almanca senaryo — Gemini

1. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın. Siyah pencereyi açık bırakın.
2. Gemini Ayarlar'da zaten **Hazır** görünüyorsa mevcut anahtar ve modeli kullanın. Tekrar kurulum gerekmez. Değilse **Ayarlar → Gemini**: anahtarı **Kaydet**, **Modelleri Getir**, listeden model seçip **Kaydet**, **Bağlantıyı Test Et**.
3. **Yeni Proje** açın. Örneğin ad: **Otomobil karşılaştırması**; konu: **Elektrikli ve hibrit otomobiller: günlük kullanımda hangi ihtiyaçlara uygundur?** Hedef süreyi ilk deneme için **5 dakika**, motoru **Gemini** seçip **Proje Oluştur** deyin. Güncel fiyat/rakam kullanılacaksa doğrulanmış notlarınızı ekleyin.
4. Proje sayfasında **Senaryoyu Aç** deyin. Motor **Gemini**, hedef dil **Almanca**, mod **Konseptten Özgün Senaryo** olsun. İçerik türünü boş bırakın: **AI otomatik algılasın**. Süre projeden gelir.
5. İsterseniz hedef kitleye **Almanya'da günlük otomobil kullanıcıları**, ek talimatlara **Profesyonel ve anlaşılır anlat. Doğrulanmamış fiyat veya teknik rakam uydurma.** yazın. Referans notları ve kaynak metin isteğe bağlıdır.
6. **Analiz Et** deyip konsept ve önerilen yapıyı görün. Ardından **Senaryo Oluştur** deyin. Doğrudan Senaryo Oluştur da analiz ve planı otomatik yapar. İlerleme alanını takip edin; uzun senaryolar birçok API isteğiyle hazırlanır.
7. Taslak gelince okuyun. **Düzenle**, ardından **Kaydet** ile yeni sürüm oluşturabilirsiniz. Metin, kelime sayısı ve tahmini dakika gösterilir.
8. Son halini kontrol edip **Onayla** deyin ve onayı kabul edin. Uygulamayı kapatıp tekrar açtığınızda senaryo, sürümler ve onay kalır.

Üretim kesilirse tamamlanan bölümler korunur. Kota/bağlantı sorununu giderdikten sonra **Devam Et** deyin. Devam için aynı sağlayıcı ve model gerekir; farklı sağlayıcı/modelle başlamak için yeni üretim seçin. Otomatik ücretli yeniden deneme yapılmaz. Uygulama kapanırsa yeniden açılışta yarım iş hata/Devam Et durumunda görünür; kendiliğinden API çağrısı yapılmaz.

Senaryo ekranı metin üretir. Onaylanan metin artık ayrı **Görsel / Kurgu Planı** ekranında düzenlenebilir sahnelere dönüştürülebilir: [Aşama 5 rehberi](SCENE_PLANNING.md). Stok medya, seslendirme, altyazı, render ve yükleme henüz çalışmaz; **Aşama 6 başlatılmadı**.

## İki ayrı çalışma modu

- **Konseptten Özgün Senaryo:** proje konusu ve isteğe bağlı kaynaklardan yalnızca üst düzey konsept/format/yapı çıkarılır. Kaynak metin yalnızca analiz çağrısına gider; bölüm yazımı özgün konsept ve planla yapılır. Rakip senaryosunun doğrudan çevirisi veya hafif yeniden yazımı hedeflenmez.
- **Kendi Metnimi Seçili Dile Çevir:** kendi metninizi ayrı alana girin ve size ait olduğunu açıkça onaylayın. Beş hedef dil seçilebilir; üçüncü taraf referans alanları kullanılamaz. Parçalı çeviri anlamı, önemli ayrıntıları ve yaklaşık uzunluğu korumayı ister; proje süresini doldurmak için metni uzatmaz.

Projedeki YouTube URL'si indirilmez, transcript kazınmaz, içeriği görülmüş gibi davranılmaz. Kaynak yoksa yalnızca konu ve verdiğiniz notlarla çalışılır. URL'nin mevcut olması doğrulanmış içerik sağlamaz.

## Üretim, süre ve kontrol

`ContentAnalyzer → ConceptBlueprint → ScriptPlan → sıralı ScriptSection → kısa devamlılık özeti → birleştirme → kontrol → ScriptVersion`

AI, bölüm sayısını ve düzenini içeriğe göre seçer. Karakter/çatışma/zirve yalnızca uygun anlatı içeriğinde kullanılır; bilgi içerikleri kurguya dönüştürülmez. Blueprint ek soyut alanları destekler. Bölüm planı hedef uzunluk ve geçerli yapı açısından sunucuda kontrol edilir.

Varsayılan konuşma hızı **125–145 kelime/dakika**, ayarlanabilir aralık **80–220**. Örneğin 20 dakika yaklaşık **2.500–2.900 kelime** hedefler. Tahmini süre ortalama hızla hesaplanır; gerçek TTS süresi değildir. Editör, kayıt, rapor ve süre uyarıları aynı son metinden ve o sürümün kaydedilmiş konuşma hızından hesaplanır. Gelecek üretim için form hızını değiştirmek eski sürümün hedefini değiştirmez. Üç dakika için **375–435 kelime**; **385 kelime / 2,85 dakika** hedef aralığındadır ve süre uyarısı almaz.

Ollama özgün senaryosu birleştirildiğinde kelime sayısı minimum hedefin altındaysa **en fazla bir** kontrollü süre düzeltmesi denenir. Minimumun az altında olsa da deneme çalışır: **340 kelime / 375–435 hedef → yaklaşık 405 kelime** istenir. Hedef aralığın ortasıdır. Aynı konu, bilgiler, yapı, ton, dil, içerik türü ve yararlı mevcut içerik korunarak mevcut noktalar geliştirilmesi istenir; dolgu/tekrarlanan paragraf/reasoning istenmez. Deneme bilgisi API çağrısından önce kaydedilir; yeniden açma/Devam Et yeni bir süre düzeltmesi başlatmaz. Hatalı, uzamayan, aşırı uzun veya tekrarlanan paragraflı aday mevcut metnin yerine geçmez. Son metin hâlâ kısaysa **“⚠ Metin hedef süreden kısa.”** gösterilir. Hedefi veya AI içerik kalitesini tutturma garantisi yoktur; insan kontrolü gerekir. Sahiplik onaylı çevirilerde ve bulut sağlayıcılarında bu ek otomatik üretim çağrısı yapılmaz.

Son kontrolün normal kullanıcıya görünen sonucu sabit, kısa Türkçe mesajlardan oluşur. Ham Almanca/İngilizce blueprint incelemesi veya özel düşünme metni gösterilmez. Eski raporlar da API okunurken güvenli özetlenir; eski veritabanı satırı veya metin değiştirilmez.

Uzun metin tek dev istekle oluşturulmaz: bölüm başına hedef 20–900 kelime, genellikle 400–700; en çok 80 bölüm. Her bölüm hemen kaydedilir, sonra kısa bağlam özeti hazırlanır. Bağlam kontrolü kesilse bile o bölümün metni tekrar üretilmez. Son kontrol en çok sekizer bölümün özet ve başlangıç/bitiş parçalarıyla yapılır; tamamlanmış kontroller de devam işleminde korunur.

AI talimatları doğal Almanca, TTS uyumu, özgün açıklamalar, tutarlı terimler ve doğal izleyici ilgisi ister. Yerel denetim uzun referans ifade eşleşmelerini engeller (15 kelimelik normalize edilmiş eşleşme); tekrarlanan uzun paragrafları işaretler. Bu denetimler kapsamlı intihal tespiti veya bağımsız bilgi doğrulaması değildir. Kontrol metnin her cümlesini yeniden yazmaz. Özellikle sağlık/finans/haber konularında bilgileri, dili, tekrarları ve kullanım haklarını insan kontrol etmelidir. AI'nin Almanca kalitesi veya doğruluğu otomatik olarak garanti edilmez.

## Sürümler ve onay

Her üretim ve manuel **Kaydet** yeni sürümdür: önceki metin değiştirilmez. Sağlayıcı, güvenli model adı, dil, içerik türü, zamanlar, kelime/süre ve onay durumu saklanır. Önceki sürüm seçilebilir. Onaylı güncel sürümün yerine yeni üretim/kayıt/sürüm seçimi için açık onay gerekir; eski onaylı sürüm yine saklanır. Eşzamanlı eski editör kaydı sessizce üzerine yazmaz.

Gelecekteki aşamalar için yalnızca güncel **Onaylandı** sürümünü veren sunucu kontrolü hazırlanmıştır. Başka bir eski sürüm onaylı olsa bile güncel taslak bu kontrolden geçmez. Henüz hiçbir sonraki aşama çalıştırılmaz.

## Yerel kayıt ve güvenlik

SQLite şema sürümü **6**. Sürüm 1/2/3/4/5'ten yükseltme eklemeli ve işlemseldir; projeler, dosyalar ve mevcut şifreli ayarlar korunur. Senaryo tabloları `script_versions`, `script_state`, `script_jobs`; kalite/görsel hazırlık tabloları `script_artifacts`, `project_production`; Aşama 5 plan geçmişi `scene_plan_versions`. Proje silinince yalnızca o projenin bağlı kayıtları silinir. Üretim sürerken proje silme engellenir.

Okunabilir dosyalar `data/projects/<project-id>/script/` altında:

```text
concept_blueprint.json
script_plan.json
generation_progress.json
job_<job-id>.json
script_v1.txt
script_v1.json
script_v2.txt
script_v2.json
current_script.json
```

SQLite devam/yeniden açılış için esas kaynaktır. Bölüm ilerlemesi dosya yansıtmasından önce SQLite'a kaydedilir; dosya yazma hatası tamamlanan bölümü kaybettirmez. Dosyalar geçici dosya ve atomik değiştirme ile yazılır. İşlemin tamamlanması ile sürüm bağlantısı birlikte kaydedilir; kesinti aynı metni ikinci sürüm olarak yeniden eklemez. Proje klasörü dışına çıkan sembolik bağlantı/junction kullanımı engellenir.

API anahtarları mevcut şifreli yerel kasada kalır. Tarayıcıya, SQLite senaryo tablolarına, okunabilir dosyalara, istemlere veya günlüklere eklenmez. Tüm kayıtlı anahtarların girdiye yapıştırılması reddedilir; olası sağlayıcı yankıları temizlenir. Ham sağlayıcı hata gövdeleri ve stack trace yerine sabit Türkçe mesajlar gösterilir. Güvenli günlük yalnızca işlem, sonuç, hata kategorisi ve süre içerir. Yerel `data/` ve günlükler Git dışında kalır. Anahtarların girişi yalnızca **Ayarlar** ekranındandır.

## Sağlayıcılar ve doğrulanmış API'ler

Tüm sağlayıcılar aynı `ScriptProvider.generate_script(prompt)` sözleşmesini kullanır. Motor sağlayıcıdan bağımsızdır; fabrika açık seçim yapar, hatada sessizce başka sağlayıcıya geçmez. Hiçbir sağlayıcı uygulamayı açmak için zorunlu değildir.

| Sağlayıcı | Kullanım ve sözleşme |
| --- | --- |
| Gemini | Mevcut Ayarlar anahtarı ve keşfedilip kaydedilmiş model kullanılır. Resmi Developer API `POST /v1beta/models/{model}:generateContent`, `x-goog-api-key`; ayrıntılar [Gemini](GEMINI.md). Model keşfi ve Settings bağlantı akışı korunmuştur. |
| Ollama | Ayarlar'da yerel base URL ve kurulu model. Resmi `POST /api/generate`: `model`, `prompt`, `system`, `stream:false`, üst seviye `think:false`; yalnızca son `response`, `done:true`, varsa tamamlanma nedeni. Ayrı thinking kullanılmaz. Yalnızca loopback; yönlendirme ve ortam proxy'si kullanılmaz. Model yükleme/indirme yok. |
| OpenAI | Ayarlar'da isteğe bağlı kullanımı açın, API anahtarı ve hesabınızda erişilebilir Chat Completions modelini kaydedin. Resmi `https://api.openai.com/v1/chat/completions`; `Authorization: Bearer`; `model`, `messages`, `stream:false`. `choices[].message.content` ve `finish_reason:stop` kontrol edilir; reddedilmiş/eksik sonuç kabul edilmez. Model adı tahmin edilmez. |

Metin üretiminde HTTP zaman aşımı **120 saniye/işlem**; toplam uzun üretim çok daha uzun sürebilir. Tarayıcı uzun dış API isteğini beklemez: arka plan işini başlatıp kısa yerel durum sorguları yapar. Settings'in mevcut Gemini 60 saniyelik arayüz / 50 saniyelik model sorgusu değişmemiştir. OpenAI Settings artık gerçek salt okunur model erişim testi kullanır; üretim kota/bakiyesini garanti etmez. API kullanımı hizmet kotası/ücretine tabidir; web aboneliği API anahtarı yerine geçmez.

2026-10-07 tarihinde doğrulanan kaynaklar:

- [Ollama resmi API — Generate a completion](https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-completion)
- [OpenAI resmi SDK — Chat Completions isteği](https://github.com/openai/openai-python/blob/main/src/openai/resources/chat/completions/completions.py)
- [OpenAI resmi SDK — resmi adres ve Authorization](https://github.com/openai/openai-python/blob/main/src/openai/_client.py)
- [OpenAI resmi yanıt tipi — choices/finish_reason/message](https://github.com/openai/openai-python/blob/main/src/openai/types/chat/chat_completion.py)
- [Google resmi API/SDK kaynakları](GEMINI.md#doğrulanan-resmi-api-sözleşmesi)

## Backend

`/api/projects/{id}/script` altında:

- `GET`: güncel metin, sürüm listesi, güvenli son iş/ilerleme ve süre bilgisi.
- `POST /analyze`, `POST /generate`: HTTP 202; arka plan işi oluşturur.
- `POST /jobs/{job-id}/resume`: hatalı/kesilmiş işi tamamlanmış bölümlerden sürdürür.
- `POST /versions`: manuel metni yeni sürüm olarak kaydeder.
- `POST /versions/{version-id}/select`: güncel sürümü seçer.
- `POST /versions/{version-id}/approve`: açık onayla güncel sürümü onaylar.
- `GET /approved`: yalnızca güncel onaylı sürüm; taslakta HTTP 409.

Değişiklik istekleri `X-AI-Video-Studio: projects`, aynı köken ve yerel Host kontrolü kullanır; yanıtlar `no-store`. Bir projede aynı anda bir üretim işi çalışır. Aktif iş sırasında sürüm değiştirme/kayıt/onay engellenir; başka projeler ve yerel sağlık servisi çalışır.

## Doğrulama ve kalan gerçek test

- Tam pytest: **309 test; 308 geçti, 0 başarısız, 1 Windows DPAPI testi Linux'ta atlandı.** Bunun içinde Aşama 4 için **69 yeni test**, önceki işlevlerin regresyonları ve 19 JavaScript Settings kontrolünü çalıştıran test vardır.
- Gemini/Ollama/OpenAI HTTP yanıtları taklit edilerek sözleşme, hata, özgünlük, sızıntı, uzun üretim, devam, sürümler, onay, kalıcılık, yükseltme ve çeviri doğrulandı.
- Chromium + gerçek yerel FastAPI: 20 dakikalık taklit üretim, kota sonrası devam, editör/sürümler/onay koruması, sağlayıcı değiştirme, çeviri, yeniden açılış ve mobil görünüm geçti; JavaScript hatası yok.
- Sahibi mevcut Gemini Settings bağlantısını ve Aşama 1–3'ü gerçek Windows'ta doğruladı. **Bu yeni Part 4 akışı canlı API anahtarıyla veya gerçek Windows'ta bu bulut ortamında denenmedi.** Yukarıdaki ilk gerçek Gemini senaryosu adımları kalan manuel doğrulamadır; gerçek Almanca kalite/uzunluk da çıktıda kontrol edilmelidir.
