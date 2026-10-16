# Medya hazırlama devam çalışması — 16 Ekim 2026

Kullanıcı canlı/ücretli API ve gerçek ölçüm testlerini açıkça onayladı. Bu işler için yeniden onay beklenmiyor. Devam eden Windows işi ve mevcut verileri koruma şartı sürüyor.

## GitHub başlangıcı

PR #81 bu çalışma başında GitHub'da birleştirilmiş olarak bulundu (16 Ekim 2026, 17.19 TSİ; GitHub `merged_at`: `2026-10-16T14:19:00Z`). Bu devam çalışması birleştirme yapmadı. Güncel main `94dd80a59db4799b14355ee2fe78cb41dbfe84ff` ile önceki geliştirme dalının dosya ağaçları aynı: `9659b1f5c04ebef4facf81659c310e67a6be081c`. Bu nedenle `improve/media-preparation-followup` dalı güncel main üzerinden açıldı; önceki optimizasyonlar tekrar yazılmadı.

Yeni [PR #82](https://github.com/naman85331/video-ai-app/pull/82) taslaktır. Kod düzeltmeleri: [`964a6bf`](https://github.com/naman85331/video-ai-app/commit/964a6bf14a96960467b42a43db08910614423e85) (paralel kota beklemesi), [`4086653`](https://github.com/naman85331/video-ai-app/commit/4086653) (eksik puanla yeniden değerlendirme). Mısır sorgusu beklentisi `af20528` ile güncellendi; test ve rapor devam commit'leri PR geçmişindedir. Bu çalışma main'e birleştirme veya Windows'a dağıtım yapmadı.

## Değişen dosyalar

- `app/stock/search_session.py`: eşzamanlı Retry-After koruması.
- `app/stock/director_media.py`: puanlanmayan adayları güvenli biçimde atlayarak devam etme.
- `tests/test_media_preparation_performance.py`: altı yeni kota/sıralama regresyonu.
- `tests/test_fast_media.py`, `tests/test_era_mode.py`, `tests/test_gemini_chain.py`: özel yer adı, Modern dönem ve kalite öncelikli kota sonrası devam beklentileri.
- `docs/STATUS.md`, `docs/MEDIA_PREPARATION_PERFORMANCE_20261016.md`, bu rapor: güncel test sonuçları, erişim koşulları ve kalan işler.

## Ek düzeltmeler

Sağlayıcı başına iki paralel istekte, bir istek 429 döndükten sonra diğerinin başarılı yanıtı bekleme kaydını silebiliyordu. Diğer isteğin timeout olması ise 120 saniyelik Retry-After süresini 2 saniyeye indirebiliyordu. Her iki durum olaylarla sıralanan deterministik testlerle eski kodda yeniden üretildi (2 başarısız).

`app/stock/search_session.py` artık başarılı isteğin yalnız başladığında gördüğü hata durumunu temizlemesine izin verir. Hata güncellemesi kilit altında yapılır; yeni hata daha uzun olan mevcut beklemeyi kısaltamaz. Sağlayıcı sınırı, kalite eşikleri ve medya seçimleri değiştirilmedi. İki yeni regresyon ve mevcut bekleme/paralellik testleri birlikte 4/4 geçti (0,73 sn).

Geniş taramada ikinci gerçek hata bulundu: Gemini kotası sıfırlandıktan sonraki yeniden değerlendirmede, görsel bütçesi nedeniyle henüz puanlanmayan adaylar `order()` içinde doğrudan sözlük erişimiyle sıralanıyordu. İş `KeyError` ile duruyordu. Aynı entegrasyon hatası değişikliksiz `cab809c` üzerinde de yeniden üretildi. Kaynak testi yalnız buluttaki sentetik projelerde yapıldı; gerçek proje veritabanına erişilmedi.

`app/stock/director_media.py` artık eksik, NaN veya 0–10 aralığı dışındaki puanları sıralamadan eler. Puan/AI onayı uydurulmaz, ücretli görsel istek bütçesi veya 7/10 eşiği artırılmaz/gevşetilmez. Dört yeni regresyon eski kodda başarısız olarak üretildi. Düzeltmeden sonra performans regresyon paketi ve kota sonrası devam entegrasyonu birlikte **52/52 geçti** (57,61 sn).

## Ek testler

- **Son kodla toplu doğrulama: 188/188 geçti** (342,98 sn). Performans, kalite, dönem/coğrafya, stok seçimi/kilit/resume, Magnific, Wikimedia ve stok frontend paketleri; ayrıca kota sıfırlaması, model zinciri sonrası seçim koruması ve Modern sahne kontrolleri birlikte çalıştırıldı. Dış bağlantılar `AVS_OFFLINE_TESTS=1` ile yasaktı. Bu sonuç son iki kod düzeltmesini ve üç test beklentisi güncellemesini kapsar; aşağıdaki ham tam tarama sonucunun yerine geçmez.
- Düzeltme sonrası `test_media_preparation_performance.py`, `test_magnific_integration.py`, `test_wikimedia.py`: **67 geçti** (106,76 sn), dış bağlantılar yasaklandı.
- `test_windows_live_fixes.py`, `test_media_recovery.py`, `test_short_clips_openmontage.py`: **122 geçti, 2 atlandı** (216,73 sn). Bu koşum düzeltmeden önce başladı; gerçek Windows veya gerçek GPU testi değildir. Atlananlar ayrı kurulu OpenMontage gerektirir.
- Geniş JavaScript paketi hem eski `cab809c` kopyasında hem devam dalında tekrar çalıştırıldı: **45 geçti, 16 başarısız**. Sebep `document.createTextNode` eksik DOM sahtesi; performans değişikliklerinden bağımsız oldukları tekrar doğrulandı ve kapsam dışında bırakıldı.
- İlk seri geniş Python denemesinde **300 geçti** (424,84 sn); ardından bütün paket dört işçiyle yeniden başlatıldı. Seri koşum önceki iki adaptif render dosyasını hariç tutuyordu; tam paket sonucu olarak sunulmaz.
- Python compile, JavaScript sözdizimi ve `git diff --check` kontrolleri geçti. Buluta özgü selector çözümü yine yalnız `/workspace/work/` altında tutuldu. Paralel test için pytest-xdist yalnız bulut sanal ortamına kuruldu; uygulama bağımlılıklarına eklenmedi.

## Tam Python taraması ve başarısızlıkların ayrılması

İkinci sıralama düzeltmesi ve beklenti güncellemelerinden önce tüm **2.122 test** dört işçiyle çalıştırıldı: **2.095 geçti, 20 başarısız, 7 atlandı** (3.809,07 sn). Bu süre bütün test paketinin duvar süresidir; bir videonun medya hazırlama süresi değildir. Ham JUnit çıktısı bulut çalışma alanında tutuldu; iç test proje yolları ve olası hassas tanı çıktıları GitHub'a yüklenmedi. Tam tarama son düzeltmelerden sonra baştan tekrarlanmadı; ilgili kontroller ayrı çalıştırıldı. Paketlerdeki sayılar örtüşür, toplanmaz.

| İlk taramadaki başarısızlık | Doğrulama / sonuç |
|---|---|
| Kota sonrası tekrar değerlendirme `KeyError` (1) | Eski sürümde de üretildi; gerçek hata düzeltildi. Son 52 testlik paket geçti. |
| Kaynak değişiminde önceki çıktı koruması, adaptive portre render, Gemini ilk yanıt süresi (3) | Daha az yük altında seri **3/3 geçti** (130,63 sn); uygulama zaman aşımı/eşikleri değiştirilmedi. |
| Gemini dakika kotası, Mont Saint-Michel, iki medya çevirisi, Fransızca relief (5) | Ayrı seri koşumda **5/5 geçti** (252,69 sn). En yavaş test 85,15 sn; ilk paralel koşumdaki 120 sn harness sınırına takıldılar. |
| Yerel port/HTTP başlatıcı (3) | İlk koşumda socket oluşturma sandbox tarafından engellendi. Güncel commit'in ayrı `git archive` kopyasında, loopback erişimi verilmiş komutta tüm başlatıcı paketi **5/5 geçti** (2,46 sn). Kopyanın kendi boş `data/` klasörü kullanıldı; mevcut veriler kullanılmadı. |
| Mısır sorgusunda eski adjective beklentisi (1) | Özel adın korunması amaçlanan davranış: `old Egypt temple`. Test uyarlandı; sorgu/yerel plan **8/8 geçti**. Eski sürümün kendi eski beklentileri **7/7 geçti**. |
| Modern sahnede aynı Python nesnesi beklentisi (1) | Modern mod dönemi sabitlerken coğrafya sahneye göre değişebilir. Test dönem/decade, girişin değişmemesi ve dönem kuralları üzerinden doğrular; modern/coğrafya kontrolleri **2/2 geçti**. |
| Altyazı font override ve görünüm menüsü (4) | `test_quality_polish.py` içindeki balanced/dynamic caption, `test_pro_edit.py` içindeki emphasis ve one-click-look testleri değişikliksiz `cab809c` üzerinde de aynı şekilde başarısız: fs48/fs50, varsayılan Graphic stili ve 6/7 görünüm sayısı. Medya performansı dışındaki eski beklentiler kaydedildi, uygulama stilleri değiştirilmedi. |
| Node altyazı test sarmalayıcısı (1) | Eski sürümde de `# pass 3` yerine izole çocuk süreç `# pass 1` raporu nedeniyle başarısız. Gerçek üç JS alt testi `--test-isolation=none` ile **3/3 geçti**. Uygulama hatası olarak sayılmaz. |
| Gemini zincirinde koşulsuz motion yasağı (1) | Eski sürümde de aynı assertion başarısız. Test artık stok yokluğuna bağlı gerekçeli kartı, yatay stok korumasını, AI erişilemezliğinin gerekçe olmamasını ve ertesi gün seçimlerin korunmasını kontrol eder. Zincir ve Modern kontrolleri **2/2 geçti** (41,54 sn); zincirin kota sıfırlaması sonrası kısmı da çalıştı. |

Yedi atlama: iki gerçek Windows DPAPI kontrolü, ayrı OpenMontage/Remotion kurulumu gerektiren üç kontrol ve ek veri gerektiren iki marker örneği. Bu atlamalar başarılı test olarak sayılmadı.

15 dakikalık sentetik 1080p FFmpeg çıktı testi **geçti** (591,15 sn). Ses/görüntü akışları, 900 saniyelik süre, tam çözümleme ve son kare doğrulandı. Kaynaklar sentetikti; gerçek stok araması, CLIP modeli, GPU veya Windows kullanılmadı. Bu 591,15 saniye medya hazırlama ölçümü değildir.

## Canlı test erişimi: gözlenen engeller

- Yönetilen ortam gözlemleri güncel ve ağ politikası uygulanıyor; izinli alan adları arasında `api.magnific.com` ve `commons.wikimedia.org` yok. Hazır secret/runtime variable/outbound identity listeleri boş. Gizli dosyalar okunmadı, anahtar değeri istenmedi veya loglanmadı.
- İlk Wikimedia GET denemesinde proxy bağlantısı kurulamadı. Ağ erişimi eklenmiş komutta ikinci anahtarsız GET denemesi proxy aşamasında `CONNECT tunnel failed, response 403` verdi; sağlayıcı HTTP durum kodu alınamadı (`000`). Bu, Wikimedia'nın gerçek API yanıtı değildir ve Windows'taki invalid_response hatasını açıklamaz. Politika etrafından dolaşılmadı.
- Magnific'e anahtarsız test gönderilmedi; gerçek hesap erişimini açıklamayacak bir 401 üretmek yerine anahtar/ağ bağlantısının eksikliği kaydedildi. Premium indirme ve üretim API çağrısı yapılmadı, ücret doğuran işlem başlatılmadı.
- Ortam Linux; `/dev/nvidia0` yok, torch kurulu değil, `OPENMONTAGE_TEST_ROOT` tanımlı değil. Windows bağlantısı bulunmuyor. Windows/NTFS, gerçek CLIP/GPU ve kurulu harici OpenMontage uyumluluğu doğrulanmış sayılmaz.

## Freepik sözleşmesi için yeni belge bulgusu

Erişilebilir resmî `freepik-company/ai-agents-hackathon` deposunun `a76399f4dd410d7fc13adbed7c9cad5de8fd6e2c` sürümündeki [arama örneği](https://github.com/freepik-company/ai-agents-hackathon/blob/a76399f4dd410d7fc13adbed7c9cad5de8fd6e2c/stock/1_search/videos/python/1_beautiful_landscape.py), `https://api.freepik.com/v1/videos` ve `x-freepik-api-key` kullanıyor. [İndirme örneği](https://github.com/freepik-company/ai-agents-hackathon/blob/a76399f4dd410d7fc13adbed7c9cad5de8fd6e2c/stock/2_download/videos/python/1_search_and_download.py) aynı kök ve header ile `GET /v1/videos/{id}/download`, `data.url` gösteriyor.

Mevcut uygulama ise `api.magnific.com` ve `x-magnific-api-key` kullanıyor. Bu fark, hesabın gerçekten hangi API sözleşmesine sahip olduğunun kontrol edilmesi gerektiğine dair yeni bir belge bulgusudur; eski örneğin güncel Magnific hesabında geçerli olduğunu veya 64 sıfır sonucun kök nedenini kanıtlamaz. Anahtar farklı origin'e otomatik gönderilmedi ve mevcut sağlayıcı tahminle değiştirilmedi. Erişim kurulumunda hesabın Freepik mi Magnific mi olduğu güvenli bağlantı metadata'sıyla belirlenmeli; yalnız doğrulanmış origin/header ile sınırlı arama yapılmalıdır. Freepik doğrulanırsa `api.freepik.com` ağ izni de gerekir.

Kullanıcı devam eden çalışma sırasında anahtarın **Magnific API** panelinden alındığını doğruladı. Bu hesap için Freepik origin'ine geçilmez; Magnific erişimi ve güncel sözleşmesi doğrulanmalıdır. Anahtarın kendisi paylaşılmadı.

## Erişim sağlandığında uygulanacak test

İlk tanı aşaması, en fazla altı Magnific araması ve altı Wikimedia araması; ilk sayfa, özgün indirme olmadan. Genel `nature landscape`, coğrafya içeren `Tijuana city` ve `Catatumbo lightning` sorguları kullanılır; Wikimedia'da görsel/video türleri ayrı denenir. Başarısızlıkta tekrar yağmuru yapılmaz; 429 ve izin hatalarında durulur. Yanıttan HTTP durumu, içerik türü, şema alan adları, ham/normalize/elenen adetler ve hata kategorisi kaydedilir. Anahtarlar, imzalı URL'ler ve ham gizli yanıtlar rapora/GitHub'a yazılmaz. Belgelenmiş sözleşme ve gerçek şema karşılaştırılır; API alanları tahmin edilmez.

Gerçek performans için mevcut projeleri kullanmadan ayrı test depolaması/veritabanı ve aynı 10/15 dakikalık örnekler gerekir. Eski/yeni sürüm aynı makine, model, sağlayıcı ve sabit aday kümesinde karşılaştırılır; soğuk ve sıcak önbellek ayrılır. Uçtan uca duvar süresi, aşama süreleri, yuva sayısı, gerçek API istekleri, CLIP paketleri, bellek ve tamamlanmayan seçimler ölçülür. Değişen canlı adayların etkisi ayrıca raporlanır. Coğrafya/konu uyumu, bulanıklık/yön, lisans ve motion geçerliliği aynı örneklerde denetlenir; eşiklerin değişmemesi tek başına gerçek kalite kanıtı sayılmaz. Windows testleri ancak devam eden iş bitmişken, ayrı test kurulumunda yapılabilir.

Gerçek 10–15 dakika medya hazırlama süresi bu ortamda ölçülemedi. Önceki %41,4 sonucu sentetiktir; 30–45 dakika hedefi hâlâ doğrulanmamıştır. Eksik olan onay değil, güvenli API/ağ bağlantısı ve uygun test makinesidir.
