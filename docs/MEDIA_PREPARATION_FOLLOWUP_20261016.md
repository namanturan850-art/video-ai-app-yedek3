# Medya hazırlama devam çalışması — 16 Ekim 2026

Kullanıcı canlı/ücretli API ve gerçek ölçüm testlerini açıkça onayladı. Bu işler için yeniden onay beklenmiyor. Devam eden Windows işi ve mevcut verileri koruma şartı sürüyor.

## GitHub başlangıcı

PR #81 bu çalışma başında GitHub'da birleştirilmiş olarak bulundu (`merged_at`: 2026-10-16T14:19:00Z). Bu devam çalışması birleştirme yapmadı. Güncel main `94dd80a59db4799b14355ee2fe78cb41dbfe84ff` ile önceki geliştirme dalının dosya ağaçları aynı: `9659b1f5c04ebef4facf81659c310e67a6be081c`. Bu nedenle `improve/media-preparation-followup` dalı güncel main üzerinden açıldı; önceki optimizasyonlar tekrar yazılmadı.

## Ek düzeltme

Sağlayıcı başına iki paralel istekte, bir istek 429 döndükten sonra diğerinin başarılı yanıtı bekleme kaydını silebiliyordu. Diğer isteğin timeout olması ise 120 saniyelik Retry-After süresini 2 saniyeye indirebiliyordu. Her iki durum olaylarla sıralanan deterministik testlerle eski kodda yeniden üretildi (2 başarısız).

`app/stock/search_session.py` artık başarılı isteğin yalnız başladığında gördüğü hata durumunu temizlemesine izin verir. Hata güncellemesi kilit altında yapılır; yeni hata daha uzun olan mevcut beklemeyi kısaltamaz. Sağlayıcı sınırı, kalite eşikleri ve medya seçimleri değiştirilmedi. İki yeni regresyon ve mevcut bekleme/paralellik testleri birlikte 4/4 geçti (0,73 sn).

## Ek testler

- Düzeltme sonrası `test_media_preparation_performance.py`, `test_magnific_integration.py`, `test_wikimedia.py`: **67 geçti** (106,76 sn), dış bağlantılar yasaklandı.
- `test_windows_live_fixes.py`, `test_media_recovery.py`, `test_short_clips_openmontage.py`: **122 geçti, 2 atlandı** (216,73 sn). Bu koşum düzeltmeden önce başladı; gerçek Windows veya gerçek GPU testi değildir. Atlananlar ayrı kurulu OpenMontage gerektirir.
- Geniş JavaScript paketi hem eski `cab809c` kopyasında hem devam dalında tekrar çalıştırıldı: **45 geçti, 16 başarısız**. Sebep `document.createTextNode` eksik DOM sahtesi; performans değişikliklerinden bağımsız oldukları tekrar doğrulandı ve kapsam dışında bırakıldı.
- İlk seri geniş Python denemesinde **300 geçti** (424,84 sn); ardından bütün paket dört işçiyle yeniden başlatıldı. Seri koşum önceki iki adaptif render dosyasını hariç tutuyordu; tam paket sonucu olarak sunulmaz.
- Python compile, JavaScript sözdizimi ve `git diff --check` kontrolleri geçti. Buluta özgü selector çözümü yine yalnız `/workspace/work/` altında tutuldu. Paralel test için pytest-xdist yalnız bulut sanal ortamına kuruldu; uygulama bağımlılıklarına eklenmedi.

## Canlı test erişimi: gözlenen engeller

- Yönetilen ortam gözlemleri güncel ve ağ politikası uygulanıyor; izinli alan adları arasında `api.magnific.com` ve `commons.wikimedia.org` yok. Hazır secret/runtime variable/outbound identity listeleri boş. Gizli dosyalar okunmadı, anahtar değeri istenmedi veya loglanmadı.
- İlk Wikimedia GET denemesinde proxy bağlantısı kurulamadı. Ağ erişimi eklenmiş komutta ikinci anahtarsız GET denemesi proxy aşamasında `CONNECT tunnel failed, response 403` verdi; sağlayıcı HTTP durum kodu alınamadı (`000`). Bu, Wikimedia'nın gerçek API yanıtı değildir ve Windows'taki invalid_response hatasını açıklamaz. Politika etrafından dolaşılmadı.
- Magnific'e anahtarsız test gönderilmedi; gerçek hesap erişimini açıklamayacak bir 401 üretmek yerine anahtar/ağ bağlantısının eksikliği kaydedildi. Premium indirme ve üretim API çağrısı yapılmadı, ücret doğuran işlem başlatılmadı.
- Ortam Linux; `/dev/nvidia0` yok, torch kurulu değil, `OPENMONTAGE_TEST_ROOT` tanımlı değil. Windows bağlantısı bulunmuyor. Windows/NTFS, gerçek CLIP/GPU ve kurulu harici OpenMontage uyumluluğu doğrulanmış sayılmaz.

## Freepik sözleşmesi için yeni belge bulgusu

Erişilebilir resmî `freepik-company/ai-agents-hackathon` deposunun `a76399f4dd410d7fc13adbed7c9cad5de8fd6e2c` sürümündeki [arama örneği](https://github.com/freepik-company/ai-agents-hackathon/blob/a76399f4dd410d7fc13adbed7c9cad5de8fd6e2c/stock/1_search/videos/python/1_beautiful_landscape.py), `https://api.freepik.com/v1/videos` ve `x-freepik-api-key` kullanıyor. [İndirme örneği](https://github.com/freepik-company/ai-agents-hackathon/blob/a76399f4dd410d7fc13adbed7c9cad5de8fd6e2c/stock/2_download/videos/python/1_search_and_download.py) aynı kök ve header ile `GET /v1/videos/{id}/download`, `data.url` gösteriyor.

Mevcut uygulama ise `api.magnific.com` ve `x-magnific-api-key` kullanıyor. Bu fark, hesabın gerçekten hangi API sözleşmesine sahip olduğunun kontrol edilmesi gerektiğine dair yeni bir belge bulgusudur; eski örneğin güncel Magnific hesabında geçerli olduğunu veya 64 sıfır sonucun kök nedenini kanıtlamaz. Anahtar farklı origin'e otomatik gönderilmedi ve mevcut sağlayıcı tahminle değiştirilmedi. Erişim kurulumunda hesabın Freepik mi Magnific mi olduğu güvenli bağlantı metadata'sıyla belirlenmeli; yalnız doğrulanmış origin/header ile sınırlı arama yapılmalıdır. Freepik doğrulanırsa `api.freepik.com` ağ izni de gerekir.

## Erişim sağlandığında uygulanacak test

İlk tanı aşaması, en fazla altı Magnific araması ve altı Wikimedia araması; ilk sayfa, özgün indirme olmadan. Genel `nature landscape`, coğrafya içeren `Tijuana city` ve `Catatumbo lightning` sorguları kullanılır; Wikimedia'da görsel/video türleri ayrı denenir. Başarısızlıkta tekrar yağmuru yapılmaz; 429 ve izin hatalarında durulur. Yanıttan HTTP durumu, içerik türü, şema alan adları, ham/normalize/elenen adetler ve hata kategorisi kaydedilir. Anahtarlar, imzalı URL'ler ve ham gizli yanıtlar rapora/GitHub'a yazılmaz. Belgelenmiş sözleşme ve gerçek şema karşılaştırılır; API alanları tahmin edilmez.

Gerçek performans için mevcut projeleri kullanmadan ayrı test depolaması/veritabanı ve aynı 10/15 dakikalık örnekler gerekir. Eski/yeni sürüm aynı makine, model, sağlayıcı ve sabit aday kümesinde karşılaştırılır; soğuk ve sıcak önbellek ayrılır. Uçtan uca duvar süresi, aşama süreleri, yuva sayısı, gerçek API istekleri, CLIP paketleri, bellek ve tamamlanmayan seçimler ölçülür. Değişen canlı adayların etkisi ayrıca raporlanır. Coğrafya/konu uyumu, bulanıklık/yön, lisans ve motion geçerliliği aynı örneklerde denetlenir; eşiklerin değişmemesi tek başına gerçek kalite kanıtı sayılmaz. Windows testleri ancak devam eden iş bitmişken, ayrı test kurulumunda yapılabilir.

Gerçek 10–15 dakika medya hazırlama süresi bu ortamda ölçülemedi. Önceki %41,4 sonucu sentetiktir; 30–45 dakika hedefi hâlâ doğrulanmamıştır. Eksik olan onay değil, güvenli API/ağ bağlantısı ve uygun test makinesidir.
