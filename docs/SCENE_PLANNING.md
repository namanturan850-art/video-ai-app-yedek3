# Aşama 5 — Sahne / Görsel Planlama

Onaylı senaryo, mevcut **Görsel / Kurgu Planı** ekranında düzenlenebilir sahnelere dönüşür. Mevcut `ProductionService`, `VisualBlock`, senaryo işi/checkpoint altyapısı ve `ScriptProvider` kullanılır. Ayrı bir sahne planlama sistemi kurulmadı.

## Windows'ta çok basit deneme

1. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın ve bir projeyi açın. Siyah pencere açık kalsın.
2. **Senaryoyu Aç** ekranında kullanacağınız metni okuyup **Onayla** deyin. Henüz metin yoksa mevcut senaryo ekranından oluşturun.
3. Projeye dönüp **Görsel / Kurgu Planı** ekranını açın.
4. Planlama sağlayıcısı olarak **Ollama** seçin. Ayarlar'da daha önce çalışan yerel modeliniz kayıtlı olsun.
5. **Görsel / Kurgu Planını Hazırla** deyin; ilerleme bitene kadar bekleyin.
6. **Onaylı anlatım tam ve aynı sırayla kapsanıyor** mesajını ve sahnelerdeki anlatımı kontrol edin. Süreler **Tahmini zamanlama** olarak görünmelidir. Üç dakikalık metin artık beş uzun sahneye sıkışmamalı; 18 saniyeyi aşan istisnaların Türkçe gerekçesi olmalıdır.
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

Part 6.5 için **aynı mevcut** sahne planlama isteği isteğe bağlı `search_anchor`, `search_context`, `search_alternatives` döndürebilir. Çapa mevcut konunun/öznenin aynen ismidir; bağlam ve alternatifler verilmiş görsel bilgilerden alınır. Belirsiz bilgiler atlanır; bu alanlar eksik/geçersizse ek ücretli onarım çağrısı yapılmaz. Yedi kritik alan ve anlatım birimi doğrulaması değişmedi. Eski projeler yeniden üretilmez veya kendiliğinden yazılmaz; stok araması mevcut bilgilerden çapayı yerel çıkarır.

AI; anlam, konu değişimi, önemli bilgi, örnek, karşılaştırma, liste, duygusal geçiş ve bölüm sınırına göre sahneler önerir. Açılış için 3–7, ana içerik için 5–12 saniye yalnızca yönlendirmedir; sabit sahne süresi uygulanmaz. Belgesel, teknoloji, finans, liste, tarih, spor ve anlatı içerikleri kendi bağlamında planlanır; her konu hikâyeye çevrilmez.

Uygulama önce onaylı metni kimlikli, sıralı cümle/paragraf birimlerine ayırır. Kaynak kelimeler, noktalama ve boşluklar aynen saklanır. Çok uzun cümlede virgül, noktalı virgül, iki nokta veya uzun çizgiyle ayrılmış uygun ifadeler birim olabilir; güvenli noktalama yoksa zorla sabit kelime/saniye dilimleri oluşturulmaz. Böyle uzun bir sahne için süre uyarısı görülebilir.

Uzun metinler yaklaşık 600 kelimelik **API bağlam parçalarına**, birim sınırlarında ayrılır; tek bir büyük birim sınırı aşabilir. Bunlar tek sahne sayılmaz. AI, `scenes` içinde `unit_ids` listeleri ve görsel alanları döndürerek birimleri anlamlı sahnelere gruplar. Her kimlik yalnız bir kez, kaynak sırasıyla ve sahne içinde bitişik kullanılmalıdır. Uygulama her sahnenin anlatımını orijinal birimleri birleştirerek kurar; AI'nin fazladan eklediği kopya anlatım alanları kullanılmaz. Son üç sahnenin görsel özeti sonraki isteğe aktarılır; ilgili görsel çeşitlilik ve devamlılık teşvik edilir.

## Doğal tempo ve görsel çeşitlilik — 2026-10-08

Önceki kalite kontrolü uzun sahneyi yalnızca uyarıyordu; beş büyük AI grubunu daha küçük görsel değişimlere ayırmıyordu. Eksik kompozisyonlar da hep `medium` oluyordu. Yeni kalite adımı, kritik JSON/parça/görsel niyet/sorgu doğrulamasından sonra ve plan kaydedilmeden önce çalışır.

- **18 saniyeyi aşan grup** mevcut anlatım birimi sınırlarından bölünür. Açılışta yaklaşık 5, diğer bölümlerde yaklaşık 10 saniyeye en yakın uygun sınır seçilir. Kısa kuyruklardan kaçınılır. Her yeni parça aynı kaynak metinden kurulur; bir kelime, noktalama veya boşluk eklenmez/silinmez. AI'nin anlamlı grupları birleştirilmez; gerektiğinde yalnız içlerinden bölünür.
- Planın tahmini toplam süresi en az 30 saniye ve ortalama sahne süresi 15 saniyeden uzunsa fazla kaba kabul edilir; güvenli birim sınırları varsa 12–18 saniyelik gruplar da iyileştirilebilir. Kesin sahne sayısı veya sabit kelime dilimi yoktur. Hesap senaryo sürümünde kayıtlı konuşma hızını kullanır.
- Tek birim güvenle daha küçük anlatım birimlerine ayrılamıyorsa kelimeler kesilmez. Uzunluk uyarısında gerekçesi yazılır. **Kilitli sahneler** kullanıcının seçimiyle aynen korunur. **Bu sahneyi yeniden planla** tek sahnenin anlatım/sınır sözleşmesini korur; uzun bir sahneyi otomatik bölmek için tüm planı yeniden hazırlayın. Manuel değişiklikler veya eski planlar kendiliğinden yeniden yazılmaz.
- Bölünen parçaların görsel niyeti, amaç/duygu ve verilmiş bağlam bilgisi korunur. İkinci parçada önce mevcut geçerli alternatif sorgu kullanılır; uygun olduğunda aynı sorguya `close up`, `wide view`, `detail view` gibi yalnız çekim ifadeleri eklenebilir. 2–12 kelime ve farklı birincil/alternatif kuralları korunur. Yeni kişi/yer/olgu uydurulmaz; aynı vurgu yazısı her alt sahnede tekrarlanmaz.
- Eksik/geçersiz kompozisyonlar sahne sırası ve mevcut görsel niyetteki çekim ipuçlarına göre çeşitlendirilir. Genel bağlamda orta/geniş/yakın; açık detay niyetinde detay/yakın; manzara/ortamda ortam/geniş; grafik niyetinde grafik gibi uyumlu öneriler kullanılır. Açık geniş/orta çekim isteği varsa o ölçek korunur; bu tür tekrarlar uyarı olarak kalabilir. Rastgele kişi veya konum atanmaz. Geçerli AI önerileri kısa, bölünmeyen sahnede korunur; yeni alt parçalar ilgili çekim ölçeğiyle çeşitlenir. Dil/anlam ipuçları bir garanti değildir; görsel niyeti gözden geçirin.
- Sabit görselde hareket alanı yoksa dönüşümlü yavaş yaklaşma/kaydırma önerilir. Açıkça verilmiş `none` korunur; arka arkaya hareketsiz görseller uyarılır. Bunlar yalnız kurgu önerileridir; bu aşamada medya/render çalıştırılmaz.

Tamamlanan plan süre/sahne sayısı, kompozisyon ve sorgu tekrarları ile arka arkaya hareketsiz görseller için yeniden kontrol edilir. Güvenle giderilemeyen tekrarlar veya bölünemeyen uzun birimler uyarı olarak kalır. **Bu yerel iyileştirme ek AI veya ücretli API çağrısı yapmaz.** Mevcut tek metadata onarımı ve bulut maliyet onayı ayrı olarak korunur.

Taklit regresyon örneği: **405 kelime / 180 saniye / 5 AI grubu → 21 sahne; en uzun 12 saniye**, anlatımın her karakteri aynı. Bu bir sabit sahne sayısı veya canlı içerik kalitesi iddiası değildir. Gerçek metindeki cümle/ifade sınırları ve konuşma hızı sonucu değiştirir.

Ollama hâlâ bozuk JSON döndürebilir. Böyle bir yanıtta **`invalid_scene_schema:json`** gösterilir; geçerli Gemini planı, sürüm geçmişi ve yerel plan dosyaları korunur. Yeni kaliteli plan ancak bütün parçalar doğrulanıp tamamlandıktan sonra aktif olur.

## Windows'taki 0% hatası ve yeniden deneme

Önceki sözleşme AI'den kaynak anlatımı harfi harfine geri yazmasını istiyordu. Küçük bir kelime/noktalama değişikliği bile kapsam doğrulamasını geçemiyordu; görsel alan hataları da aynı genel mesajla gösteriliyordu. Yeni akışta anlatımın sahibi uygulamadır. Kapsam kontrolü gevşetilmedi; parça referansları kesin olarak doğrulanır.

Güncel sürümü açıp mevcut onaylı projenizde **Görsel / Kurgu Planı → Ollama → Görsel / Kurgu Planını Hazırla** deyin. Anlatımın tam kapsandığı mesajını kontrol edin. Ardından bir sahneyi yeniden planlayıp anlatımın değişmediğini, bir sahneyi kilitleyip toplu yenilemede korunduğunu deneyin. Mevcut eski planlar/senaryolar/ayarlar korunur. Önceki sürümde 0%'ta kalmış bir iş de **Plan İşlemine Devam Et** ile kaynak birimlerine dönüştürülerek sürdürülebilir. Ancak o işin tek düzeltme denemesi zaten kullanılmışsa yeniden deneme için **Görsel / Kurgu Planını Hazırla** ile yeni bir plan işi başlatın; senaryoyu yeniden üretmeniz gerekmez.

Anlaşılır parça kapsamı varsa ama görsel alanlar hatalıysa **bütün plan işi için en fazla bir** metadata düzeltme çağrısı yapılabilir. Bu çağrı aynı sağlayıcı/modeli ve aynı parça gruplarını kullanır; anlatım değişmez. Ham hatalı yanıt tekrar istenmez veya arayüze verilmez.

Düzeltme istemi kısadır: sabit parça grupları, güvenli hata kategorisi/alanı, anlamı korumak için kaynak birimler ve yedi alanlı küçük JSON örneği. Önceki hatalı JSON ve büyük açıklama yeniden gönderilmez.

- **Ollama:** tek düzeltme otomatik yapılabilir.
- **Gemini/OpenAI:** ilk hata sonrası durur. **Plan İşlemine Devam Et** düğmesi ikinci çağrının ek kotası/ücreti için ayrı onay ister. İptal ederseniz ikinci çağrı yapılmaz. İlk plan maliyet onayı bu ikinci çağrı için yeterli sayılmaz.
- Eksik/yinelenen/sırası bozuk kimlikler veya anlaşılmayan JSON otomatik onarılmaz. Tek düzeltme başarısızsa önceki plan ve tamamlanan parçalar kalır. Yeniden açılış/Devam Et kullanılmış düzeltme hakkını sıfırlamaz; isterseniz açık onayla yeni bir plan işi başlatabilirsiniz.

Hata mesajının yanında güvenli **Tanı** kategorisi ve başarısız kritik alan gösterilir: örneğin `invalid_scene_schema:visual_intent`, `invalid_stock_queries:stock_query`, `invalid_media_type:media_type` veya `invalid_scene_schema:json`. Türkçe mesaj alanı da söyler: **“AI sahne planında 'görsel niyet' alanını eksik döndürdü.”** Parça kapsamı hataları `narration_units_missing`, `narration_units_duplicate` veya `narration_units_out_of_order` olarak kalır. Günlükler işlem/sağlayıcı/güvenli kategori/alan/süre içerir; ham sağlayıcı yanıtı, reasoning ve sırlar içermez.

## Küçük AI sözleşmesi ve güvenli tamamlama — 2026-10-08

Kalan Windows `invalid_scene_schema` hatasının kod katmanındaki nedeni, AI çıktısının bütün kurgu alanlarıyla birlikte doğrudan katı `VisualBlock` doğrulamasından geçirilmesiydi. Eksik geçiş/hareket/kompozisyon/önem veya geçersiz bir ikincil alan, geçerli parça gruplarına sahip planı da düşürüyordu. Genel hata hangi alanın sorunlu olduğunu göstermiyordu; sahibin o yanıtında eksik olan kesin alan ham yanıt olmadan belirlenemez. Artık anlatım kapsamı doğrulandıktan sonra kritik görsel bilgiler doğrulanır, ardından ikincil alanlar güvenle tamamlanır.

AI'den yalnızca `unit_ids`, `purpose`, `mood`, `visual_intent`, `stock_query`, `alternative_stock_queries` ve `media_type` istenir. `overlay_text`, `entities`, `location`, `action`, `shot_suggestion` isteğe bağlıdır. Eksik veya geçersiz ikincil alanlar aşağıdaki sabit değerlerle tamamlanır; geçerli gönderilmiş değerler korunur.

| Alan | Güvenli varsayılan |
| --- | --- |
| `overlay_text`, `location`, `action`, `shot_suggestion`, `notes` | Boş metin `""` |
| `entities` | Boş liste `[]` |
| `importance` | `50` |
| `transition` | `none` |
| `motion` | Video için `none`; sabit görsel için kalite adımında yavaş yaklaşma/kaydırma |
| `composition` | Kalite adımında mevcut niyet ve komşularla uyumlu çekim ölçeği |

Bu değerler kişi, yer, olay, tarih veya istatistik üretmez. Eksik/geçersiz görsel niyet, amaç/duygu, kullanılamayan stok sorguları, bozuk JSON ve bütün anlatım referansı hataları kayıt engeli olmaya devam eder. İkincil alanın temizlenmesi gerekiyorsa sabit Türkçe, kritik olmayan bir kalite uyarısı gösterilir; yalnızca alanın hiç gönderilmemesi uyarı gerektirmez.

Medya türü içeride yalnız `stock_video`, `stock_image`, `ai_image`, `motion_graphic`, `user_media` olabilir. Bilinen tam eşdeğerler (`video`, `stock video`, `image`, `stock image`, `ai image`, `motion graphic`, `user media`) bu değerlere çevrilir. Medya alanı eksikse `stock_video` kullanılır; gönderilmiş bilinmeyen bir tür tahmin edilmez ve reddedilir.

Her sahnede bir İngilizce birincil sorgu ve **1–5 farklı geçerli alternatif** yeterlidir. Baş/son boşluklar, yinelenen boşluklar ve sondaki noktalama temizlenir: `Florida panther habitat.` → `Florida panther habitat`. Boş/kullanılamayan birincil sorgu, paragraf biçimi ve aynı sahnedeki birincil/alternatif tekrarları reddedilir. Kullanılamayan alternatifler çıkarılabilir; en az bir geçerli alternatif kalmalıdır. Tek alternatif varsa ikinci sorgu veya yeni olgu uydurulmaz. İngilizce olma, hedef dilde overlay ve içerikle anlam ilişkisi AI talimatlarıyla yönlendirilir; otomatik dil/anlam doğrulama garantisi yoktur. Kullanıcı sorguları ve görsel niyeti inceleyip düzeltebilir.

Vurgu yazısı isteğe bağlıdır, proje dilinde istenir ve en fazla 12 kelime/150 karakterdir; tüm anlatımı tekrarlayamaz. AI'nin uzun veya anlatımı kopyalayan vurgu yazısı boşaltılır ve uyarı gösterilir; plan kaydedilebilir. Manuel editör geçersiz değerleri Türkçe mesajla düzeltmenizi ister. Medya türü, kompozisyon, geçiş ve hareket yalnızca öneridir; dosya üretmez.

Qwen 3.5 istemi kısa açık örnek ve **“Return JSON only. Do not explain.”** talimatıyla biter. Mevcut native Ollama adaptöründe `think=false`, `stream=false` korunur; doğrulanmamış yeni `format`/şema parametresi eklenmedi. Gemini/OpenAI adaptörleri ve maliyet onayları değiştirilmedi. Normalize edilen sahneler mevcut handoff'ta bütün alanları içerir.

Çok az sahne, 2 saniyeden kısa veya 18 saniyeden uzun sahne, tekrar eden sorgu/görsel fikir/kompozisyon/konum/özne, görsel çeşitlilik eksikliği ve arka arkaya çok fazla hareketsiz görsel için Türkçe uyarı gösterilir. Yeni planlarda uzun/kaba gruplar güvenli birim sınırında yerel olarak iyileştirilir; sınırı olmayan birim veya kilit zorla kesilmez. Eksik veya sırası bozuk anlatım ise kayıt/devretme hatasıdır. Gelecekteki medya/TTS/müzik eksikleri ayrı, açılır bir hazırlık listesinde kalır.

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
