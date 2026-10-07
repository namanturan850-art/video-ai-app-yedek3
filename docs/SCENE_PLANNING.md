# Aşama 5 — Sahne / Görsel Planlama

Onaylı senaryo, mevcut **Görsel / Kurgu Planı** ekranında düzenlenebilir sahnelere dönüşür. Mevcut `ProductionService`, `VisualBlock`, senaryo işi/checkpoint altyapısı ve `ScriptProvider` kullanılır. Ayrı bir sahne planlama sistemi kurulmadı.

## Windows'ta çok basit deneme

1. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın ve bir projeyi açın. Siyah pencere açık kalsın.
2. **Senaryoyu Aç** ekranında kullanacağınız metni okuyup **Onayla** deyin. Henüz metin yoksa mevcut senaryo ekranından oluşturun.
3. Projeye dönüp **Görsel / Kurgu Planı** ekranını açın.
4. Planlama sağlayıcısı olarak **Ollama** seçin. Ayarlar'da daha önce çalışan yerel modeliniz kayıtlı olsun.
5. **Görsel / Kurgu Planını Hazırla** deyin; ilerleme bitene kadar bekleyin.
6. **Onaylı anlatım tam ve aynı sırayla kapsanıyor** mesajını ve sahnelerdeki anlatımı kontrol edin. Süreler **Tahmini zamanlama** olarak görünmelidir.
7. Bir sahnede **Düzenle** deyin, görsel niyetini değiştirip **Kaydet** deyin.
8. Başka bir sahnede **Bu sahneyi yeniden planla** deyin. Anlatım ve diğer sahneler aynı kalmalıdır.
9. Bir sahnede **Kilitle** deyin; görsel niyetini ve sorgularını hatırlayın.
10. Planı tekrar hazırlayıp onayı verin. Kilitli sahnenin içeriği ve kimliği korunmalıdır; eski plan sürümü listede kalır.
11. Uygulamanın siyah penceresini kapatın; aynı `.bat` dosyasına tekrar çift tıklayın.
12. Aynı proje ve plan ekranını açın. Aktif plan, düzenlemeler, kilit ve sürüm listesi korunmalıdır.

İsterseniz ayrıca **Sahneyi böl**, **Sonraki sahneyle birleştir**, **Yukarı taşı / Aşağı taşı** ve eski bir plan sürümünü seçmeyi deneyin. Bölmede anlamlı bir cümle sınırını siz seçersiniz; cümle sınırı yoksa kelime sınırı seçebilirsiniz. Birleştirmede ilk sahnenin görsel tasarımı kullanılır. **Yukarı/Aşağı taşı görsel tasarımı komşu sahneye taşır; onaylı anlatımın sırası değişmez.** Bu davranış proje sahibinin seçimidir.

## Onay, maliyet ve anlatımın korunması

- Güncel senaryo onaylı değilse **“Önce senaryo sürümünü onaylayın.”** görünür; sağlayıcıya planlama isteği gönderilmez.
- Bütün sahne anlatımlarının birleşimi, yalnızca boşluk normalizasyonuyla, onaylı senaryoya tam ve aynı sırayla eşit olmalıdır. Anlatımı uygulama kaynak metinden kurar; AI anlatım yazmaz. Eksik, yinelenen veya sırası bozuk parça referansları kaydedilmez; önceki plan korunur.
- Anlatım sahne editöründen değiştirilemez. Metni Senaryo ekranında değiştirirseniz eski plan **Eski plan** olur; yeni sürümü onaylayıp yeni plan hazırlayın. Proje dilini değiştirmek de eski planı işaretler. Eski plan görülebilir; düzenleme ve sonraki aşama devri engellenir.
- Gemini/OpenAI işlemi başlamadan API kotası/ücreti için açık onay alınır. Ollama'dan ücretli sağlayıcıya otomatik geçiş yoktur. Mevcut, Windows'ta doğrulanmış sağlayıcı adaptörleri değiştirilmedi.

## Planlama ve kalite

AI; anlam, konu değişimi, önemli bilgi, örnek, karşılaştırma, liste, duygusal geçiş ve bölüm sınırına göre sahneler önerir. Açılış için 3–7, ana içerik için 5–12 saniye yalnızca yönlendirmedir; sabit sahne süresi uygulanmaz. Belgesel, teknoloji, finans, liste, tarih, spor ve anlatı içerikleri kendi bağlamında planlanır; her konu hikâyeye çevrilmez.

Uygulama önce onaylı metni kimlikli, sıralı cümle/paragraf birimlerine ayırır. Kaynak kelimeler, noktalama ve boşluklar aynen saklanır. Çok uzun cümlede virgül, noktalı virgül, iki nokta veya uzun çizgiyle ayrılmış uygun ifadeler birim olabilir; güvenli noktalama yoksa zorla sabit kelime/saniye dilimleri oluşturulmaz. Böyle uzun bir sahne için süre uyarısı görülebilir.

Uzun metinler yaklaşık 600 kelimelik **API bağlam parçalarına**, birim sınırlarında ayrılır; tek bir büyük birim sınırı aşabilir. Bunlar tek sahne sayılmaz. AI, `scenes` içinde `unit_ids` listeleri ve görsel alanları döndürerek birimleri anlamlı sahnelere gruplar. Her kimlik yalnız bir kez, kaynak sırasıyla ve sahne içinde bitişik kullanılmalıdır. Uygulama her sahnenin anlatımını orijinal birimleri birleştirerek kurar; AI'nin fazladan eklediği kopya anlatım alanları kullanılmaz. Son üç sahnenin görsel özeti sonraki isteğe aktarılır; ilgili görsel çeşitlilik ve devamlılık teşvik edilir.

## Windows'taki 0% hatası ve yeniden deneme

Önceki sözleşme AI'den kaynak anlatımı harfi harfine geri yazmasını istiyordu. Küçük bir kelime/noktalama değişikliği bile kapsam doğrulamasını geçemiyordu; görsel alan hataları da aynı genel mesajla gösteriliyordu. Yeni akışta anlatımın sahibi uygulamadır. Kapsam kontrolü gevşetilmedi; parça referansları kesin olarak doğrulanır.

Güncel sürümü açıp mevcut onaylı projenizde **Görsel / Kurgu Planı → Ollama → Görsel / Kurgu Planını Hazırla** deyin. Anlatımın tam kapsandığı mesajını kontrol edin. Ardından bir sahneyi yeniden planlayıp anlatımın değişmediğini, bir sahneyi kilitleyip toplu yenilemede korunduğunu deneyin. Mevcut eski planlar/senaryolar/ayarlar korunur. Önceki sürümde 0%'ta kalmış bir iş de **Plan İşlemine Devam Et** ile kaynak birimlerine dönüştürülerek sürdürülebilir.

Anlaşılır parça kapsamı varsa ama görsel alanlar hatalıysa **bütün plan işi için en fazla bir** metadata düzeltme çağrısı yapılabilir. Bu çağrı aynı sağlayıcı/modeli ve aynı parça gruplarını kullanır; anlatım değişmez. Ham hatalı yanıt tekrar istenmez veya arayüze verilmez.

- **Ollama:** tek düzeltme otomatik yapılabilir.
- **Gemini/OpenAI:** ilk hata sonrası durur. **Plan İşlemine Devam Et** düğmesi ikinci çağrının ek kotası/ücreti için ayrı onay ister. İptal ederseniz ikinci çağrı yapılmaz. İlk plan maliyet onayı bu ikinci çağrı için yeterli sayılmaz.
- Eksik/yinelenen/sırası bozuk kimlikler veya anlaşılmayan JSON otomatik onarılmaz. Tek düzeltme başarısızsa önceki plan ve tamamlanan parçalar kalır. Yeniden açılış/Devam Et kullanılmış düzeltme hakkını sıfırlamaz; isterseniz açık onayla yeni bir plan işi başlatabilirsiniz.

Hata mesajının yanında güvenli **Tanı** kategorisi gösterilir: `narration_units_missing`, `narration_units_duplicate`, `narration_units_out_of_order`, `invalid_scene_schema`, `invalid_stock_queries`, `invalid_overlay`, `invalid_media_type`, `invalid_transition`, `invalid_composition`. Günlükler işlem/sağlayıcı/güvenli kategori/süre içerir; ham sağlayıcı yanıtı, reasoning ve sırlar içermez.

Her sahnede bir İngilizce birincil sorgu ve 2–5 farklı alternatif istenir. Sorgular kısa, anlamlı arama terimleri olmalıdır; cümle veya anlatımın kopyası olmamalıdır. Uygulama sorgu uzunluğu/biçimi ve aynı sahnedeki tekrarları doğrular. İngilizce olma, hedef dilde overlay ve içerikle anlam ilişkisi AI talimatlarıyla yönlendirilir; otomatik dil/anlam doğrulama garantisi yoktur. Kullanıcı sorguları ve görsel niyeti inceleyip düzeltebilir.

Vurgu yazısı isteğe bağlıdır, proje dilinde istenir ve en fazla 12 kelime/150 karakterdir; tüm anlatımı tekrarlayamaz. Medya türü, kompozisyon, geçiş ve hareket yalnızca öneridir; dosya üretmez.

Çok az sahne, 2 saniyeden kısa veya 20 saniyeden uzun sahne, tekrar eden sorgu/görsel fikir/kompozisyon/konum/özne, görsel çeşitlilik eksikliği ve arka arkaya çok fazla sabit görsel için Türkçe uyarı gösterilir. Bu eşikler uyarıdır; anlamlı uzun çekimler zorla bölünmez. Eksik veya sırası bozuk anlatım ise kayıt/devretme hatasıdır. Gelecekteki medya/TTS/müzik eksikleri ayrı, açılır bir hazırlık listesinde kalır.

## Kilitler, zamanlama ve sürümler

Kilitli sahne düzenlenemez, bölünemez, birleştirilemez, taşınamaz veya tek başına yeniden planlanamaz. Toplu planlamada aynı onaylı senaryoya ait kilitli sahneler aynen kopyalanır; bunlar için AI isteği yapılmaz. Kilitli sahneler arasındaki anlatım yeniden planlanabilir. Önceki sahnelerin sayısı değişirse gösterilen sahne numarası güncellenir; kilitli sahne kimliği ve içeriği korunur. Yeni senaryoda eski kilitler taşınmaz; eski sürüm içinde saklanır.

Tahminler gerçek anlatım kelime sayısı ve kaynak senaryo sürümünde kayıtlı konuşma hızı aralığının ortalamasından hesaplanır. **Gerçek TTS zamanlaması değildir.** Mevcut `attach_timing` bağlantısı gerçek zaman damgalarını daha sonra ekleyebilir; tahmin alanları ayrıca korunur. Kilitli gerçek zamanlama ile yeniden tahmin edilen sahneler bir aradaysa planın `timing_source` değeri `mixed` olur; her sahnenin kaynağı ayrıdır.

AI üretimi, tek sahne üretimi, manuel düzenleme, bölme/birleştirme/taşıma ve kilitleme yeni plan sürümü oluşturur. Eski sürümler, kaynak senaryo, sağlayıcı/model ve oluşturulma tarihiyle saklanır. Sürüm seçimi onay ister ve **Aktif plan** uygulama yeniden açıldığında geri gelir. Mevcut müzik/medya/zamanlama hazırlık bağlantıları aktif planın revizyonunu günceller. Eski tarayıcı sekmesi veya başarısız işten devam, daha yeni bir planı sessizce ezemez.

## Yerel kayıt ve güvenli yükseltme

SQLite şema **6**, mevcut şema 5 planlarını `scene_plan_versions` geçmişine aktarır. Eski planda sağlayıcı/model kaydı olmadığından `legacy` / boş model gösterilir; değer tahmin edilmez. Mevcut projeler, senaryolar, dosyalar ve şifreli kasa silinmez. Eski okunabilir plan dosyası korunur; sonraki plan kaydında yeni aynalar da yazılır.

SQLite esas kayıttır. Okunabilir JSON aynaları:

- `data/projects/<proje-id>/scenes/plan_v<N>.json`
- `data/projects/<proje-id>/scenes/active_plan.json`
- Mevcut uyumluluk dosyası: `data/projects/<proje-id>/script/visual_plan.json`

JSON yazımı mevcut atomik ve proje klasör sınırlarını kontrol eden yardımcısını kullanır. AI işi veritabanına kaydedildikten sonra JSON yazımı kesilirse **Plan İşlemine Devam Et** aynaları onarır; yeni AI isteği veya ikinci plan sürümü oluşturmaz. Proje verileri/yerel sırlar Git dışında kalır. Sırlar sahne alanlarına kaydedilemez; ham sağlayıcı yanıtı, özel reasoning veya API anahtarı hata mesajına verilmez.

## Part 6 için veri sözleşmesi

`GET /api/projects/{project_id}/production/handoff`, yalnızca güncel onaylı senaryoyu tam ve sıralı kapsayan aktif planı döndürür. `contract_version: 1`; proje/plan/senaryo kimlikleri, sürüm, dil, çözünürlük ve kaynak önceliği vardır. Her `scenes` girdisi:

| Alanlar | Kullanım |
| --- | --- |
| `scene_id`, `order`, `narration_text` | Kalıcı sahne kimliği, sıralama ve eksiksiz anlatım |
| `start_estimate`, `end_estimate`, `estimated_duration` | Açıkça tahmini zamanlama |
| `start`, `end`, `timing_source` | Güncel zamanlama; `estimated`, `tts` veya plan düzeyinde `mixed` |
| `purpose`, `mood`, `importance`, `visual_intent` | Görsel anlam ve öncelik |
| `preferred_media_type` | `stock_video`, `stock_image`, `ai_image`, `motion_graphic`, `user_media` |
| `primary_stock_query`, `alternative_stock_queries`, `stock_query_language` | Birincil/alternatif sorgular; İngilizce hedefi |
| `entities`, `location`, `action`, `composition`, `shot_suggestion` | Bağlama uygun arama/seçim bilgisi |
| `transition`, `motion` | Kurgu önerileri |
| `overlay_text`, `overlay_language`, `notes`, `locked` | Kısa hedef dil yazısı, kullanıcı notları ve kilit |
| `media` | Yeni planda `null`; mevcut hazırlık bağlantısından eklenen metaveri dosyanın varlığını kanıtlamaz |

Eski `id`, `narration`, `media_type`, `stock_query` alanları mevcut blok sözleşmesinin esas alanlarıdır; yeni adlar bunlarla eşlenir. İkinci bir bağımsız veri modeli yoktur.

**Part 6 başlatılmadı:** Pexels/Pixabay arama, önizleme, seçim, indirme, tekrar önleme ve izinli AI görsel fallback çalıştırması sonraki aşamadır. AI33 seslendirme, altyazı ve FFmpeg render da bu aşamada çalıştırılmaz.

Otomatik testler ve gerçek FastAPI/Chromium arayüz kontrollerinde dış AI yanıtları taklit edildi. Sahibi önceki Gemini/Ollama entegrasyonunu gerçek Windows'ta doğruladı. **Yeni Part 5 planlarının canlı sağlayıcıyla içerik kalitesi ve Windows denemesi yukarıdaki adımlarla sahibi tarafından yapılmalıdır.**
