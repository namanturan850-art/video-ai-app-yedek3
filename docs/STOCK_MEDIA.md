# Stok Medya — Aşama 6

Güncel ve **Hazır** sahne planını açın: **Proje → Görsel / Kurgu Planı**. Her sahnenin altında **Medya Yuvaları** görünür. Bir sahne birden fazla video veya görsel taşıyabilir. Onaylı anlatım ve plan sürümleri değiştirilmez.

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
- Öncelik ilgili Pexels video → Pixabay video → Pexels fotoğraf → Pixabay görsel. Her türde sorgu sırası birincil, alternatiflerdir. Kullanılmamış uygun sonuç bulununca ek sorgu/API çağrıları durur. Bir sağlayıcı hatası aynı aramada tekrar tekrar denenmez; diğer sağlayıcı kullanılabilir.
- Çözünürlük, yatay kadraj, yuva için yeterli video süresi ve açıklama/etiket sözcükleri değerlendirilir. Pixabay videoda arama sıralaması temel uygunluktur: sorgu sözcüklerini tekrarlamayan geniş etiketler reddetme sebebi değildir; eşleşen etiketler puanı artırır. Pexels ve Pixabay görsellerinde mevcut metadata uygunluk kontrolü korunur. Video minimum 960×540 ve MP4 olmalıdır; 4K bulunmaması geçerli 720p/1080p klibi elemez. 1080p sınıfı yeterli varyant varken dev 4K dosya tercih edilmez. Daha düşük çözünürlük/tekrar/durağan görsel serisi uyarılır. Görüntü içeriği, kamera açısı veya temizliği otomatik görsel tanımayla doğrulanmaz; özellikle açıklaması sınırlı videolar sahibinin incelemesini gerektirir.
- Tekrar kimliği `provider + media_type + media_id` (aynı sayısal kimlikteki fotoğraf ve video farklı kaynaklardır); engelleme sadece mevcut proje içindir. Başka projeler aynı kaynağı kullanabilir. Alternatif kalmazsa tekrar uyarılır; elle seçimde onay gerekir. İndirme önbelleği proje/sağlayıcı/kimlik/tür bazındadır; aynı dosya hash/boyut kontrolünden sonra yeniden kullanılır.
- Kilitli görsel arama/tamamlama/plan yenilemesinde korunur. Aynı onaylı senaryoda sahne sınırı değişirse kilitli zaman aralığı yeni sahnelere aktarılır; sınır kilitli aralığın içinden geçerse aynı yerel dosya iki kilitli yuvada paylaşılır ve kesme kontrolü uyarılır. Yeni senaryo sürümünde eski seçimler eski plan kayıtlarında kalır; yeni planda kendiliğinden kullanılmaz.
- SQLite **şema 7**, ek tablolarla eski planları/ayarları/senaryoları korur. Yuvalar ayrıca `stock/media_slots.json` ve plan kimlikli JSON olarak saklanır; SQLite esas kayıttır. İş ilerlemesi SQLite'ta checkpoint olarak tutulur; yeniden açılışta kesilen iş **Devam Et** durumuna geçer. Tamamlanmış yuvalar yeniden indirilmez.
- HTTPS ve belgelerde görülen sağlayıcı/CDN adresleri dışında istek veya yönlendirme kabul edilmez. Ham uzak dosya adı kullanılmaz. Dosya tipi, MP4/görsel imzası, HTTP sonucu ve boyut sınırları kontrol edilir. Sınırlar video 250 MB, görsel 20 MB; HTTP ağ hatasında en fazla iki deneme. Geçici dosya, `fsync` ve atomik yeniden adlandırma; başarısız geçici indirme temizlenir. Tanınmayan CDN yönlendirmesi güvenli hata üretir, otomatik geniş izin verilmez.
- Anahtarlar mevcut şifreli yerel kasadadır. API yanıtları/proje JSON'u/günlükler anahtar içeremez. Özellikle Pixabay anahtarı URL parametresi olduğundan stok HTTP debug/URL günlükleri filtrelenir. Tanı günlüğü işlem/sağlayıcı/güvenli kategori/süre ve arama türü/güvenli sorgu/sayaçları içerir; adres veya gizli bilgi biçimindeki sorgular gizlenir; ham API hatası veya Authorization başlığı yoktur.

## Sonraki aşamaya devir ve kapsam

`GET /api/projects/{id}/production/stock/handoff` her yuva için sahne/yuva kimliği, tahmini başlangıç/bitiş, yuva süresi, kaynak türü/yerel yolu/süresi/çözünürlüğü/sağlayıcı/kimlik, kilit, `trim_needed` ve `coverage_warning` verir. `ready` yalnız bütün yerel atamalar geçerliyse doğrudur; eksikler açıkça boş alan/status taşır. Uzun klip gerçekten kesilmez; `rendered=false`.

Stok yoksa **AI görsel gerekebilir** görünür. Hazır ImageProvider mimarisi korunur, gerçek AI görsel çağrısı yapılmaz. **Part 7 / AI33, altyazı, FFmpeg render, müzik işleme veya YouTube yükleme uygulanmadı.**

## Doğrulama

Otomatik testler dış API/indirme yanıtlarını taklit eder. Gerçek FastAPI + Chromium kontrolü, masaüstü/mobil arayüz ve yeniden başlatma akışını çalıştırır; onun dış API/medya yanıtları da taklittir. Gerçek medya içeriğinin uygunluğu, gerçek anahtar erişimi/kota/CDN koşulları ve Windows DPAPI Linux testlerinin kanıtladığı şeyler değildir.

**Live provider test must be run by owner on Windows.** Yukarıdaki 12 adımı gerçek Pexels/Pixabay API anahtarlarıyla çalıştırın. Anahtarları sohbetten paylaşmayın.
