# Stok Medya — Aşama 6 + 6.5 + V4

Güncel ve **Hazır** sahne planını açın: **Proje → Görsel / Kurgu Planı**. Her sahnenin altında **Medya Yuvaları** görünür. Bir sahne birden fazla video veya görsel taşıyabilir. Onaylı anlatım ve plan sürümleri değiştirilmez.

## Media Relevance V4 — Bağlamsal görüntü ve hızlı arama

**Eksik yuvaların takılmasının kod nedeni:** Özel isimli sahnelerde (ör. *Bermuda Üçgeni*) yalnız açıklamasında o isim geçen medya kabul ediliyordu. Pexels/Pixabay bu isimleri neredeyse hiç etiketlemediği için “fırtınada gemi”, “eski harita ve pusula” gibi tam istenen görüntüler bile reddediliyordu; birkaç isimli klip kullanıldıktan sonra kalan yuvalar her denemede boş kalıyordu. Ayrıca sahnede hem gemi hem uçak geçtiğinde sahne yalnız “havacılık” sayılıp bütün gemi görüntüleri reddediliyordu.

**Şimdi:**

- Sahnenin bağlamından **en az iki somut kavram** (gemi + okyanus, harita + pusula, uçak + okyanus…) içeren ve konu dışı bir özne (köpek, yemek, şehir…) taşımayan medya **İlgili** sayılır ve ekranda **“bağlamsal görüntü — olayın kendisi değil”** diye işaretlenir.
- Tek ve genel bir kavram (yalnız “deniz”, “plaj”, “şehir”) **hâlâ reddedilir**. Köpek / berber / trende oturan yolcu gibi ilgisiz görüntüler uçak-navigasyon sahnelerine atanmaz (testlerle sabitlendi).
- Adında gerçekten “Bermuda Triangle” geçen medya her zaman bağlamsal görüntüden üstte sıralanır.
- Arama sırasında her sorguda bütün planın yeniden doğrulanıp diske yazılması kaldırıldı (plan en fazla 2 sn'de bir doğrulanır, ilerleme saniyede bir yazılır, kayıt dosyası iş sonunda yansıtılır). Sağlayıcı beklemesi hariç iç yük ~10 kat azaldı.
- Sahne planı istemi artık kameranın çekebileceği somut İngilizce sorgular ister (ör. “pilot hands cockpit instruments”); soyut kavram, diyagram veya tek başına isim sorgusu istemez.

Bu bir metadata (etiket) değerlendirmesidir; görüntünün gerçek içeriğini kesin olarak görmez. CLIP görsel kontrolü yalnız ayrıca kurulduğunda çalışır.

### Eksik Medyaları Akıllı Tamamla — tek basışta bitirme

Sahibin ekranında görülen durum: düğmeye her basışta 44 → 47 → 51 → 52 ilerliyor, sonra 3 alan ve 2,8 sn açık kalıyordu.

- **Neden 1:** bir basış en fazla 48 arama / 16 indirme / alan başına 8 arama yapıp duruyordu. **Şimdi** tek basış, ilerleme oldukça en fazla 3 tur döner (iş başına 120 arama, alan başına 12, 40 indirme — Pexels'in saatlik 200 istek sınırının altında). Önceden denenmiş sorgu/sayfa tekrar istenmez.
- **Neden 2:** akıllı kurgu bir boşluğu yalnız aynı sahnedeki *tek* komşu klibe, toplam 7,5 sn'yi aşmadan ekleyebiliyordu; sahnenin tamamı boşsa hiç kapatamıyordu. **Şimdi** sırayla:
  1. aynı sahnede birleştirme sınırı video 10 sn / görsel 9 sn (uzun çekim render'da punch-in ile bölünüp hareket ettiği için sabit görünmez),
  2. tek komşuya sığmayan boşluk **iki komşu arasında paylaştırılır**,
  3. son çare olarak kısa boşluk (≤ 6 sn) **komşu çekimin kesintisiz devamıyla** kapatılır: aynı çekim kaynağın kaldığı yerinden sürer, sınırda belirgin yakın kadraja geçilir ve araya geçiş efekti konmaz. Bu aynı klibin ayrı bir tekrarı değildir; kilitli medya bu amaçla kullanılmaz, kaynağın gerçek süresi aşılmaz. Ekranda “X sn, komşu çekimin kesintisiz devamıyla kapatıldı” diye açıkça yazılır.
- İlgisiz medya, siyah ekran veya gizli tekrar hâlâ yoktur. Ses ve altyazı zamanları değişmez.

## Media Relevance V3

Güncel davranış: **özne → görsel bağlam → stil** ayrı değerlendirilir. Belgesel, röportaj, vintage, eski, siyah/beyaz, sinematik, arşiv, yakın/geniş çekim gibi beş dildeki format terimleri tek başına özne olamaz. Kayıtlı `search_anchor` körü körüne kullanılmaz: gerçek entity/konum, ana sorgunun güçlü kavramları ve görsel amaç önceliklidir; çelişen veya boş stil çapası reddedilir. Mürettebat/kokpit gibi yerel kavramlar İngilizce 2–5 kelimelik aramaya dönüşür. Bilinmeyen özel isimler çevrilmez.

Yerel özgüllük: `named_specific`, `domain_specific`, `generic_visual`. İsimli/alanı özgül sahnelerde otomatik seçim **İlgili/Çok ilgili** gerekir. Aircraft/cockpit/crew yerine gün batımı/okyanus veya modern ilgisiz kişi seçilmez. Gerçek genel okyanus/orman görselinde uyumlu metadata için Genel bağlantılı hâlâ kabul edilebilir. Metadata değerlendirmesi görsel tanıma/AI güven yüzdesi değildir.

**Otomatik tekrar kesin engellenir:** `(provider, media_type, media_id)`, sorgu/fragment taşıyan takip bilgileri olmadan normalize edilmiş kaynak/sayfa/CDN yolu ve mevcut SHA-256 byte özeti. İş başlamadan diğer yuvalar rezerve edilir, her seçim hemen rezervasyona girer; proje başına tek aktif iş yarışı önler. İndirme sonrası aynı byte içeriği fark edilirse başka aday denenir. Kullanılmış en iyi adaya geri dönülmez. Benzersiz ilgili aday yoksa **Uygun ve kullanılmamış stok medya bulunamadı.** Dosya/arşiv silinmez. Algılayıcı perceptual benzerlik iddiasında bulunmaz.

Açık yeniden aramada eski kilitsiz tekrarların ilk uygun ataması korunabilir; sonraki atamalar benzersiz aday bulur veya boş kalır. Kilitler korunur; iki kilitli tekrar için **Aynı medya birden fazla kilitli alanda kullanılıyor.** görünür. Elle tekrar ancak açık onayla yapılabilir. Her yuvada **Tekrar durumu: Benzersiz / Daha önce kullanılmış / Manuel tekrar kullanım** gösterilir.

Benzersiz ilgili video → benzersiz ilgili görsel → gerçekten genel sahnede uygun genel medya. 16 puanlık video toleransı ve yaklaşık %80–95 yumuşak hedef korunur; ilgisiz veya tekrarlanan video oran uğruna seçilmez. %100 uygun video geçerlidir. Eski seçimleri görüntülemek dosyaları değiştirmez; açık **Alakaya Göre Medyayı Yeniden Ara** V3 politikasını uygular.

Canlı sağlayıcı sonuçları bulutta taklit edilir. **Live provider test must be run by owner on Windows.**

## Part 6.5 — Önceki kalite geçişinin temeli

Eski projeyi açmak mevcut stok seçimlerini değiştirmez. **Alakaya Göre Medyayı Yeniden Ara** açık onayla yeni aramayı başlatır. Kilitler korunur. Önceki seçimler `stock/selection-<kimlik>.json` olarak saklanır; seçim sürümü artar. Önceki indirilen dosyalar, senaryo, seslendirme, altyazılar ve videolar silinmez. HTTP/indirme hatasında eski seçim korunur. Başarılı arama yalnız zayıf sonuç bulursa zayıf eski atama boşaltılabilir; dosyası ve arşivdeki kaydı kalır. Planı/senaryoyu yeniden oluşturmak gerekmez.

Her sahnenin **Ana konu** çapası mevcut özne → konum → sorgu → görsel amaç → aynen anlatım terimlerinden çıkarılır. Gelecekteki sahne çağrısında isteğe bağlı `search_anchor`, `search_context`, `search_alternatives`, `provider_query` aynı mevcut istek içinde dönebilir; yeni LLM çağrısı yoktur. Çok sözcüklü özel isimler korunur. Beş dildeki genel/görsel terimler yalnız yerel karşılaştırmada normalleştirilir; özel isimler çevrilmez veya uydurulmaz.

| Arama kademesi | Sıra |
| --- | --- |
| 1 | Doğrudan konu ve özgül ana sorgu |
| 2 | Konu + verilmiş görsel bağlam |
| 3 | Yakın, verilmiş veya uyumlu bağlam |
| 4 | Son çare olarak konuyla uyumlu genel B-roll |

**Arama sırası:** doğrudan/yakın bağlamda **İlgili/Çok ilgili VIDEO** (kademe 1–3) → ilgili IMAGE (1–3) → genel ama uyumlu VIDEO → genel uyumlu IMAGE. İlgili video bulunduğunda puanı birkaç fazla görsel için arama sürdürülmez. Birlikte değerlendirilen kabul edilebilir video/görsel için deterministik video toleransı **16 puan**; genel video güçlü konu görselini bastıramaz. V3 önce kullanılan adayları çıkarır; kalan ilgili adaylar arasında video toleransı uygulanır. Kullanılmış video yerine benzersiz ilgili görsel seçilebilir. Uygun video varken gereksiz arka arkaya görsel birikmesi böyle önlenir. Yaklaşık %80–95 video hedefi yumuşaktır: yeterli ilgili video varsa %100 de kabul edilir; ilgisiz video veya zorunlu görsel kotası yok. UI gerçek Video/Görsel sayısını ve seçilmiş yuvaların video oranını gösterir. Uygun video yoksa görsel ve dürüst uyarı korunur.

**Taze metadata kapısı:** her seçim/sıralama ve salt okunur durum görüntülemesi güncel sahne profili + gerçek sağlayıcı açıklamasından yeniden hesaplanır. Pixabay `tags`, Pexels image `alt`, Pexels video mevcut slug/açıklama metadata'sı kullanılır. Eski `relevance_score`/`relevance_label`, query_used, kademe ve çözünürlük uygunluk kanıtı değildir. Teknik boyut/süre/CDN kapıları ayrıca aynen korunur. Açılış etiketi günceller, kayıtlı seçimi veya tarihçeyi yeniden yazmaz. Küçük broad-domain kapısı aviation/rail/animal/food/urban/marine/mountain/forest/beach/vehicle/technology uyumsuzluklarına bakar; büyük ontoloji yok. Kokpit için gerçek aircraft/cockpit/aviation veya başka alanla çelişmeyen navigation+instrument kanıtı gerekir. Sıradan narration/yanlış alternatif sözleri köpek veya tren etiketlerini İlgili yapamaz. Ortak electric gibi betimleyici veya kısmi yer adı, eksik aircraft/car/subway öznesi olmadan konu kapısını aşamaz.

**Sağlayıcı sorgusu:** UI/orijinal sahne sorgusu korunur; ayrı `provider_query` resmî sağlayıcıya gönderilen kısa 2–6 İngilizce kavramı gösterir. Eski çok dilli alanlar yerel sözlük/İngilizce çapa ile sadeleşir, örneğin `aircraft cockpit navigation computer`. Bermuda Triangle/Titanic/Mount Everest/Tokyo gibi özel isimler çevrilmez veya uydurulmaz. Bilinmeyen isim aynen korunabilir; bu genel bir çeviri API'si değildir. Gelecek planın aynı mevcut AI çağrısında isteğe bağlı provider_query vardır; alan eksik/geçersizse ekstra onarım/ücretli istek yok. Aynı iki sağlayıcı, en fazla altı farklı sorgu ve 24 saatlik cache korunur.

Yuvada/medyada `search_tier`, `query_used`, `provider_query`, `relevance_score`, `relevance_label` saklanır. Bantlar: **Çok ilgili** ≥60, **İlgili** ≥25, **Genel bağlantılı** ≥12, **Zayıf eşleşme** <12. Arama kademesi yalnız provenance'tır. Zayıf sonuç otomatik indirilmez; güvenli adaylar elle seçilebilir. Puan metadata eşleşmesidir, AI güven yüzdesi/görsel tanıma değildir. Cloud vision ve AI görsel üretimi eklenmedi.

Sahibin örneği A=cockpit/airplane/navigation/instrument VIDEO, B=train passenger VIDEO, C=dog grass VIDEO, D=cockpit display IMAGE: A önce seçilir; A yoksa D, B/C'yi geçer; B/C Zayıf eşleşmedir. Bermuda `Bermuda Triangle ocean mystery` > `Atlantic ocean ship waves` >>> `city skyline buildings` regresyonu devam eder. Yalnız ilgisiz medya varsa yuva boş kalır. [15 Windows kontrol adımı](RENDERING.md#part-95-windows-kontrolü). Gerçek görüntü görünümü/sağlayıcı sonuçları sahibi tarafından önizlenmelidir.

## Çok basit Windows denemesi

Önce `START_AI_VIDEO_STUDIO.bat` dosyasına çift tıklayın. Siyah pencere açık kalsın. Güncelleme yaparken mevcut `data` klasörünü koruyun.

1. **Ayarlar → Pexels**: API anahtarını girin; **Kaydet → Bağlantıyı Test Et**.
2. **Ayarlar → Pixabay**: API anahtarını girin; **Kaydet → Bağlantıyı Test Et**. Anahtarlar resmî API hesaplarından alınır; web aboneliği gerekmez. İki sağlayıcıdan yalnız birini de kullanabilirsiniz.
3. Güncel, onaylı senaryo ve **Hazır** sahne planı olan projenizi açın.
4. **Görsel / Kurgu Planı → Medyayı Otomatik Bul** düğmesine basın. İlerleme mesajını bekleyin.
5. Uzun sahnelerin altında birden fazla **Medya** yuvası olduğunu kontrol edin.
6. Seçilenlerin video/görsel, süre, çözünürlük ve arama bilgilerini inceleyin. Anlatıma uygunluğu kendiniz kontrol edin.
7. Seçilen dosyalar otomatik olarak `data/projects/<proje-kimliği>/stock` içine indirilir; klasörü elle hazırlamayın.
8. Bir yuvada **Değiştir** deyin; adaylardan **Bu Medyayı Seç** ile başka medya seçin. Aday yoksa **Yeniden Ara** deyin.
9. Seçtiğiniz bir medyada **Kilitle** düğmesine basın. Değiştirmek için önce **Kilidi Aç** gerekir.
10. **Eksik Medyaları Tamamla** deyin. Tamamlanmış ve kilitli seçimler korunur. İnternet/API/indirme hatasında **Devam Et** ile aynı işi sürdürün.
11. Siyah uygulama penceresini kapatın; aynı `.bat` dosyasına tekrar çift tıklayın.
12. Aynı proje ve planı açın. İndirilen dosyalar, seçimler ve kilitler korunmuş olmalıdır.

**Önizle** seçilen yerel videoyu/görseli açar. Aday listesi küçük sağlayıcı önizlemelerini gösterir; tüm adaylar indirilmez. **Kaynak Bilgisi** altında sağlayıcı, içerik kimliği, oluşturan kişi, kaynak sayfası ve indirme tarihi bulunur. Aynı medyayı elle tekrar seçerseniz açık tekrar onayı istenir. **Kaldır** yalnız yuva atamasını kaldırır; proje önbelleğindeki dosyayı silmez.

**“Önce güncel Görsel / Kurgu Planını hazırlayın.”** görünüyorsa senaryonun güncel sürümünü onaylayıp plan hazırlayın. Üretim sürerken projeyi silmek engellenir. Bir medya işi sırasında aktif planı değiştirirseniz eski iş yeni plana atama yapmaz; indirilen dosyalar önbellekte kalır. Güncel planda **Eksik Medyaları Tamamla** kullanın.

## Mevcut görselleri Pixabay videolarıyla yeniden deneme

Güncellenmiş uygulamayı aynı `data` klasörüyle açın. Projeyi/senaryoyu/sahne planını yeniden oluşturmayın; mevcut 37 dosyayı silmeyin.

1. **Görsel / Kurgu Planı** sayfasında toplam yuva, video, görsel ve eksik sayaçlarını kontrol edin. Video tercihli çok yuvalı planda hiç video yoksa açık uyarı görünür.
2. Kilitsiz bir görselde **Video ile değiştirmeyi dene** deyin. Yalnız video aranır; mevcut görsel ve dosyası yerinde kalır.
3. **Arama Tanısı** bölümünü açın. Örneğin **Pixabay video: 12 sonuç → 8 kullanılabilir → 4 uygun aday**; çözünürlük/süre/uygunluk/geçersiz bilgi/güvensiz adres elenmeleri ayrı sayılır.
4. Video adayını inceleyip **Bu Medyayı Seç** deyin. Yalnız başarılı indirmeden sonra yuva değişir. Hata veya aday bulunamaması eski görseli kaldırmaz. Eski görsel dosyası indirme sonrasında da korunur.
5. İsterseniz **Uygun görselleri videoyla değiştir** deyin ve onaylayın. Bu işlem yalnız **video tercihli ve kilitsiz** mevcut görsel yuvalarını tarar. Görsel tercihli yuvaları korur; onlarda tekli düğmeyle açık seçim yapabilirsiniz. Kilitler korunur.
6. Video/görsel sayaçlarını ve **Önizle** sonucunu kontrol edin. Uygulamayı kapatıp yeniden açın; seçimler aynı kalmalıdır.

**Kısa video toleransı (sn)** 0–1,5 arasında seçilebilir; varsayılan 1,25 saniye. Ayar bu plan için saklanır. İzin verilen eksiklik ayrıca yuva süresinin en fazla %20'sidir; örneğin 8 saniyelik yuvada 7,2 saniye kabul edilir, 2 saniye reddedilir. Kısa klipte **Video yuva süresinden biraz kısa**, `trim_needed=false`; gerçek uzatma/esnetme/kesme yapılmaz. Daha uzun klipte yalnız sonraki aşamalar için kesme işareti vardır.

24 saatlik eski arama önbelleği silinmez: içindeki videolar yeni filtrelerle değerlendirilir. Eski kayıt ham sonuç sayısını tutmadığı için **ham sayaç yok** gösterilebilir; bu sıfır sonuç demek değildir. Yeni önbellek normalleştirme sayaçlarını saklar. Önbellekte gerçekten boş video sonucu varsa aynı sorgu 24 saat dolana kadar boş kalır; **Arama Tanısı** önbellek kullanımını belirtir. Yeni bir API çağrısı yapıldığı izlenimi verilmez.

## Resmî API sözleşmeleri

Aşağıdaki iki resmî belge **2026-10-08** tarihinde doğrudan açılarak doğrulandı. Uç noktalar, istek alanları ve yanıt alanları bu belgelerden alınmıştır; sağlayıcı web siteleri kazınmaz.

| Sağlayıcı | Belge | Kullanılan arama sözleşmesi |
| --- | --- | --- |
| Pexels | https://www.pexels.com/api/documentation/ | `GET https://api.pexels.com/v1/videos/search` ve `/v1/search`; `Authorization: <API anahtarı>`; `query`, `per_page=12`, `orientation=landscape` |
| Pixabay | https://pixabay.com/api/docs/ | `GET https://pixabay.com/api/videos/` ve `/api/`; `key`, URL kodlanmış `q` (en fazla 100 karakter), `per_page=12`, `safesearch=true`; fotoğraflarda `image_type=photo`, `orientation=horizontal` |

Pexels'in güncel belgesi eski `/videos/` adreslerini kullanım dışı bırakılacak olarak işaretler; uygulama **`/v1/videos/`** kullanır. [Resmî Pexels JavaScript SDK](https://github.com/pexels/pexels-javascript) da kimlik doğrulama ve kaynak şemasının ek doğrulamasında incelendi; eski SDK adresi uygulanmadı.

Pexels `video_files` içinden MP4 çözünürlük varyantı; fotoğraflarda `src.large2x` (belgelenmiş 1880×1300 sınıfı), `src.medium`, `alt`, fotoğrafçı ve sayfa bilgileri okunur. Orijinal çözünürlük ayrıca saklanır. Pixabay `hits`, `videos` varyantlarının `url/width/height/thumbnail`, `duration`, `tags`, `pageURL`, `user/user_id`; görsellerde `largeImageURL`, varsa yetkili hesaba verilen `fullHDURL`, `previewURL` ve orijinal boyutlar kullanılır. `fullHDURL` zorunlu varsayılmaz. Pixabay fotoğrafının ölçekli boyutu orijinal en-boy oranıyla hesaplanır. Bunlar sağlayıcı metadata değerleridir; render veya FFmpeg ile doğrulama yapıldığı iddia edilmez.

Pixabay belge gereği arama yanıtları **24 saat** önbelleklenir. Proje araması önbelleği sağlayıcı/tür/sorgu bazındadır; boş sonuçlar da saklanır. Ayarlar bağlantı testi, son 24 saat içindeki başarılı aynı-anahtar testini açık önbellek mesajıyla kullanır; yeni anahtar kaydı bu sonucu sıfırlar. Toplu/systematik kaynak indirme yoktur: yalnız projenin seçtiği adaylar indirilir. Sonuçlarda kaynak sağlayıcı/sayfa gösterilir. API'nin sağladığı kaynak bilgisi saklanır; otomatik lisans uygunluğu iddiası yapılmaz.

## Seçim ve güvenli kayıt

- Var olan Part 5 handoff tek sahne kaynağıdır. Sahneler bölünmez, anlatım değiştirilmez. Medya yuvaları tahmini süre ve yakın cümle/anlatım birimi sınırlarıyla hazırlanır; normal çekim değişimi yaklaşık 4–8 saniye hedefler. Olağan kısa/orta/uzun sahneler 1/1–2/2–4 yuva taşıyabilir; çok uzun sahne daha fazlasını taşıyabilir. Dokuz adet 20 saniyelik örnek sahne yaklaşık 27 medya yuvası oluşturur; bu sabit kota değildir.
- Önce verilmiş İngilizce birincil/alternatif sorgular kullanılır; sonraki yuvalar mevcut ilgili alternatiflerle çeşitlenir. Yeni kişi/yer/olgu eklenmez.
- Konu kademeleri içinde Pexels/Pixabay video ve görsel denenir. Alaka türden önce gelir; video-only düğmeleri açık seçim olarak korunur. Güçlü uygun sonuç bulununca ek sorgu/API çağrıları durur. Bir sağlayıcı hatası aynı aramada tekrar tekrar denenmez; diğer sağlayıcı kullanılabilir.
- Çözünürlük, yatay kadraj, yuva için yeterli video süresi ve ağırlıklı açıklama/etiket uygunluğu değerlendirilir. Pixabay video etiketleri de aynı alaka kapısından geçer; tam sorgu eşleşmesi zorunlu değildir, gerçek bağlam eşleşmesi kabul edilir. Video minimum 960×540 ve MP4 olmalıdır; 4K bulunmaması geçerli 720p/1080p klibi elemez. 1080p sınıfı yeterli varyant varken dev 4K dosya tercih edilmez. Daha düşük çözünürlük/tekrar/durağan görsel serisi uyarılır. Görüntü içeriği otomatik görsel tanımayla doğrulanmaz; açıklaması olmayan sonuç otomatik doğrulanmış uygunluk sayılmaz.
- Tekrar kimliği `provider + media_type + media_id` (aynı sayısal kimlikteki fotoğraf ve video farklı kaynaklardır); engelleme sadece mevcut proje içindir. Başka projeler aynı kaynağı kullanabilir. Alternatif kalmazsa tekrar uyarılır; elle seçimde onay gerekir. İndirme önbelleği proje/sağlayıcı/kimlik/tür bazındadır; aynı dosya hash/boyut kontrolünden sonra yeniden kullanılır.
- Kilitli görsel arama/tamamlama/plan yenilemesinde korunur. Aynı onaylı senaryoda sahne sınırı değişirse kilitli zaman aralığı yeni sahnelere aktarılır; sınır kilitli aralığın içinden geçerse aynı yerel dosya iki kilitli yuvada paylaşılır ve kesme kontrolü uyarılır. Yeni senaryo sürümünde eski seçimler eski plan kayıtlarında kalır; yeni planda kendiliğinden kullanılmaz.
- Stok tabloları şema 7'de eklendi; mevcut SQLite **şema 10** bu kalite geçişinde değişmez. Yuvalar ayrıca `stock/media_slots.json` ve plan kimlikli JSON olarak saklanır; SQLite esas kayıttır. İş ilerlemesi SQLite'ta checkpoint olarak tutulur; yeniden açılışta kesilen iş **Devam Et** durumuna geçer. Tamamlanmış yuvalar yeniden indirilmez.
- HTTPS ve belgelerde görülen sağlayıcı/CDN adresleri dışında istek veya yönlendirme kabul edilmez. Ham uzak dosya adı kullanılmaz. Dosya tipi, MP4/görsel imzası, HTTP sonucu ve boyut sınırları kontrol edilir. Sınırlar video 250 MB, görsel 20 MB; HTTP ağ hatasında en fazla iki deneme. Geçici dosya, `fsync` ve atomik yeniden adlandırma; başarısız geçici indirme temizlenir. Tanınmayan CDN yönlendirmesi güvenli hata üretir, otomatik geniş izin verilmez.
- Anahtarlar mevcut şifreli yerel kasadadır. API yanıtları/proje JSON'u/günlükler anahtar içeremez. Özellikle Pixabay anahtarı URL parametresi olduğundan stok HTTP debug/URL günlükleri filtrelenir. Tanı günlüğü işlem/sağlayıcı/güvenli kategori/süre ve arama türü/güvenli sorgu/sayaçları içerir; adres veya gizli bilgi biçimindeki sorgular gizlenir; ham API hatası veya Authorization başlığı yoktur.

## Sonraki aşamaya devir ve kapsam

`GET /api/projects/{id}/production/stock/handoff` her yuva için sahne/yuva kimliği, tahmini başlangıç/bitiş, yuva süresi, kaynak türü/yerel yolu/süresi/çözünürlüğü/sağlayıcı/kimlik, kilit, `trim_needed` ve `coverage_warning` verir. `ready` yalnız bütün yerel atamalar geçerliyse doğrudur; eksikler açıkça boş alan/status taşır. Uzun klip gerçekten kesilmez; `rendered=false`.

Stok yoksa **Uygun stok medya bulunamadı / AI görsel gerekebilir** görünür. Hazır ImageProvider mimarisi korunur, gerçek AI görsel çağrısı yapılmaz. Part 7–9.5 ses/altyazı/render kendi mevcut ekranlarında kullanılabilir; stok yeniden araması bunları çalıştırmaz. **Part 10 ve YouTube yükleme başlamadı.**

## Doğrulama

Otomatik testler dış API/indirme yanıtlarını taklit eder. Gerçek FastAPI + Chromium kontrolü, masaüstü/mobil arayüz ve yeniden başlatma akışını çalıştırır; onun dış API/medya yanıtları da taklittir. Gerçek medya içeriğinin uygunluğu, gerçek anahtar erişimi/kota/CDN koşulları ve Windows DPAPI Linux testlerinin kanıtladığı şeyler değildir.

**Live provider test must be run by owner on Windows.** Yukarıdaki 12 adımı gerçek Pexels/Pixabay API anahtarlarıyla çalıştırın. Anahtarları sohbetten paylaşmayın.

## Part 9.7 — Kısa, farklı ve yatay medya

**Eksik Kısa Videoları Bul** düğmesi açık onaydan sonra eski seçimleri arşivler; kilitsiz uzun alanları yerel olarak daha kısa alanlara böler. Sahne/anlatım sırası, onaylı kelimeler, ses ve altyazılar korunur. Kilitli uzun medya yerinde kalır. Bu ilk yeniden planlama bir kez yapılır; tekrar aramalar aynı kısa yuvaları kullanır. Eski dosyalar silinmez. Açılışta otomatik yeniden seçim yapılmaz.

Hedef ortalama yaklaşık 3–4sn, olağan aralık yaklaşık 2,8–4,5sn; uygun anlatım/cue sınırları nedeniyle bazı kesitler 2,5–5,5sn olabilir. Kesit sayısı sabit değildir. 193sn / 24 sahne / 37 eski alanlı regresyon örneği **48 alan, yaklaşık 4,02sn ortalama** üretir. Yeterli benzersiz ilgili aday yoksa alan boş kalır; medya kopyalanarak sayı doldurulmaz.

Otomatik VIDEO için **width > height**, en az **1280×720**; 1920×1080 / yaklaşık 16:9 tercih edilir. Pexels resmî `orientation=landscape` filtresi; Pixabay video API'sinde belgelenmemiş orientation parametresi gönderilmez, dönen gerçek boyutlar yerel filtrelenir. Kare/dikey videolar otomatik elenir. Manuel/eski dikey kaynak uyarıyla görünür. İlgili görseller de kullanılabilir; dikey/kare görseller doğal oranlarıyla çerçevelenir veya uyumlu kartta gösterilir.

Eşit alakalı adaylar arasında 4–12sn (özellikle 4–9sn) yatay kaynak tercih edilir. İlgili 20–30sn kaynak reddedilmez: örneğin kaynak 22sn, kullanılan kesit 3,7sn olabilir. Yeni kısa yuvalarda kaynak kullanılan süreyi karşılamalıdır; normal yeni B-roll döngülenmez/hızlandırılmaz. Eski kısa kaynak toleransı ve oynatılabilirliği korunur. Kaynak dosya değişmez; kesme yalnız render çıktısı içindir.

Özet: video/görsel/benzersiz medya, eksik alan, ortalama/en uzun kullanım, dikey video sayısı. Kartta kaynak/kullanılan süre ayrı; yatay/16:9 ve tekrar durumu. Yaklaşık %80–95 video yumuşak hedeftir; %100 ilgili video geçerlidir, ilgisiz video veya tekrar hedef uğruna seçilmez. Yerel Pexels/Pixabay isteği artık belgelenmiş `per_page=40` ile daha geniş benzersiz aday havuzu alır; API/CDN doğrulama ve 24 saat önbellek korunur.

İsteğe bağlı ayrı [OpenMontage arama adaptörü](OPENMONTAGE_INTEGRATION.md): Hızlı doğrudan arama / ayrıca kurulursa Semantik CLIP. Açık kaynak arşivler ve ancak açık onayla mevcut Pexels/Pixabay anahtarları; doğrulanmış yatay MP4 adayları mevcut proje stok önbelleğine alınır. Diğer kapsayıcılar bu sürümde otomatik içe alınmaz. Lisans/kaynak bilgisi korunur; bulunurluk ve alaka garanti edilmez. Arama yalnız açık medya işlemiyle çalışır, render sırasında indirme yapılmaz.

Önbellekteki OpenMontage dosyası eksik/değişmişse açık **Yeniden Ara** eski arama önbelleğini kullanmak yerine taze aday ister. Yeni UUID dosyası kaydedilir; eski dosyalar ve render sürümleri silinmez. Render bu onarımı veya dış indirmeyi kendiliğinden başlatmaz.


## Part 9.8 Akıllı Kurtarma

**Eksik Medyaları Akıllı Tamamla** eski geçerli seçimleri değiştirmez. Kilitli süre/seçim aynı kalır; geçersiz kilitli dosya/yanlış görsel açık engeldir. Önce arşiv oluşturulur, gerçek dosya SHA/ffprobe/tek kare decode kontrolü yapılır. Yalnız eksik veya geçersiz kilitsiz alanlarda arama yapılır; anlatım/altyazı/sahne üretimi yoktur.

Kod denetimi: Part 9.7 kısa kesitler yeni dosya sayısını artırırken proje çapında ID/URL/SHA benzersizliği korunuyordu. Arama en fazla altı sorgunun ilk sayfasını, 24 saat önbellekle tekrar deniyordu. Ham handoff tek eksikte `ready=false` kalıyordu. Bunlar mimari nedenlerdir; sahibin özel 13 alanının bireysel nedenleri bulutta bilinmez.

Her yuva için kanıtlı Türkçe nedenler: `no_provider_results`, `all_candidates_irrelevant`, `all_candidates_duplicates`, `portrait_or_resolution_rejected`, `download_failed`, `provider_rate_limited`, `query_exhausted`, `no_visual_match`, `locked_or_stale_selection`. Ham HTTP yanıtı, gizli/CDN URL veya anahtar yoktur. Sonuç sayısı olmayan eski kayıt, arama tüketildi diye işaretlenmez.

Kalıcı `recovery_attempts` sorgu+sağlayıcı+tür+sayfa kimliğini izler. Başarılı eski ilk-sayfa kanıtları da aktarılır. Mevcut konudan en fazla 10 sorgu, Pexels/Pixabay belgelenmiş `page=1..3`, önce video; etkin ayrı OpenMontage ile desteklenen açık kaynak araması denenir. Geçiş başına 8 istek/yuva, 48 istek/proje ve 16 aday indirme denemesi; aday listesi 80 ile sınırlıdır. 429 sağlayıcıyı o geçişte durdurur; ağ/anahtar sorunu kalıcı boş sonuç sayılmaz. Sonraki geçiş gerçekten yeni kanıtları dener; başarılı bütün seçenekler tüketilince aynı arama dönmez. Teknik/alaka/tekrar filtreleri gevşetilmez. Gerçek kaynak süresi aralığa yetmiyorsa `source_too_short` gösterilir; otomatik döngüyle kapatılmaz. Video dosyası mevcut güvenli 250 MB, görsel 20 MB sınırındadır; indirilen dosyalar önbellekte korunur.

### Gerçek kare analizi

Ayrı OpenMontage ortamında açık onayla **openai/clip-vit-base-patch32** kurulursa ve **Yerel semantik kare analizi** etkinse gerçek indirilmiş videonun %20/%50/%80 kareleri FFmpeg ile çıkarılır. Upstream `lib.clip_embedder.embed_images/embed_texts/model_info` kullanılır. En fazla dört aday bir süreçte, kareler batch olarak; CPU en fazla dört thread. Uygun CUDA varsa GPU, başarısız CUDA'da aynı yerel ağırlıklarla bir CPU tekrarı. Kaynak SHA + descriptor + model SHA sürümü sonuç cache'ine; kaynak SHA + model sürümü kare embedding cache'ine bağlanır. Geçici kareler temizlenir; üst model cache'i 5000 dosya ile sınırlıdır. Açılış/arama hiçbir model indirmez.

Yanlış özne bulgusu metadata'yı geçersiz kılar; yeterli görsel eşleşme yalnız bağlamsal destek sağlar. Puanlar kesinlik yüzdesi değildir. Model yoksa **Kurulum gerekli**, işlem hatasında **Hata**, yalnız hazır modelde analiz. Belirsiz/model-yok sonucunda metadata/elle kontrol korunur; otomatik görsel doğrulama uydurulmaz.

`footage_role` için `direct_factual`, `contextual_broll`, `illustrative` ayrımı korunur. Yerel benzerlik otomatik olarak yalnız **contextual_broll** verir; olay/kişi/konumun doğrudan gerçek görüntüsü olduğu iddia edilmez. Tarihî doğruluk ve kullanım lisansı kaynak sayfasından kullanıcı tarafından incelenmelidir. Yeni sahne isteği aynı mevcut AI çağrısında isteğe bağlı kısa İngilizce `semantic_descriptor` üretir; eski planlar mevcut çok dilli konu/query/intent normalizasyonunu kullanır. Yeni ücretli çağrı yoktur.

### Ham alanlar ve etkili zaman çizelgesi

Kurtarma sonunda `stock/recovery-<UUID>.json` eklenir. Ham seçim/timing değiştirilmez. Aynı semantik sahnede bitişik boş, kilitsiz aralık uygun kaynağa kesintisiz eklenebilir: gerçek kaynak süresi yeterli olmalı, video toplamı en fazla 7,5 sn, görsel 7 sn. Aynı dosya ayrı yeni kesit olarak tekrarlanmaz. Kilitli aralık/ankraj taşınmaz; başka sahneden dolgu alınmaz. Nadir kısa sayısal kart yalnız mevcut cue ve anlatımdaki aynen metinden, 2–7 sn ve toplam sesin en fazla %20'si kadar; **Uyarlanabilir YouTube** gerektirir. Uygun kaynak yoksa kalan süre açık engeldir.

55 ham alan / 42 geçerli kaynak / 13 boş örneğinde uygun yerleşimle 42 kesintisiz etkin kesit ve 193 sn kapsama mümkündür; sabit sayı veya her proje için garanti değildir. Ekran `raw_stock_slots/selected_stock_assets/unresolved_raw_slots` ile `effective_render_segments/effective_covered_duration/effective_uncovered_duration/render_ready` değerlerini ayrı gösterir. Render ayrıca gerçek ses/altyazı/kaynak/motor/FFmpeg hazır olmasını ister. Kaynak, kilit veya zaman değişirse kurtarma planı güncel değildir; düğmeyi yeniden kullanın.

**Live provider test must be run by owner on Windows. Live semantic visual test must be run by owner on Windows.** CLIP ağırlıkları bu bulut çalışmasında indirilmedi; görsel sınıflandırma regresyonları taklit edilmiş kanıt sözleşmesidir. [17 basit Windows adımı](RENDERING.md#part-98-windows-kontrolü).
