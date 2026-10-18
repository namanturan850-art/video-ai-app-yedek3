# Manuel Plan / AI paketi teslimi

18 Ekim 2026. Taban: `origin/fix/manual-plan-transition-handles`, `d82df82`.
Düzeltme dalı: `fix/manual-package-safe-import`.

## Kullanım

1. Kurgu → **Manuel Plan / AI paketi** açılır. Yerel görev paketi projeyi değiştirmeden görüntülenir.
2. **Paketi Hazırla**, yalnız paylaşım ve kota/ücret onayı verilince mevcut Gemini sağlayıcısını çağırır. Gemini kurgu uygulamaz; dış AI için talimat üretir.
3. **Paketi kopyala**, talimatlar ve bütün bağlamı tek JSON olarak kopyalar: senaryo/sahne saatleri, sıfır tabanlı altyazı cümleleri, seslendirme kimliği/süresi/hash bilgisi, gerçek arşiv kimlikleri/süreleri, haritalar, mevcut kurgu, kilitler, kaynak giriş noktaları ve geçiş kapasitesi. Ses dosyasının kendisi gönderilmez; anahtar ve yerel dosya yolları pakete eklenmez.
4. Dış AI cevabı yapıştırılır veya **Dosyadan yükle (.json)** seçilir. Birden fazla mesajdaki tam JSON nesneleri birleştirilebilir. Parçaların `schema`/`base` bilgileri aynı olmalıdır. Yinelenen JSON alanları, bozuk/eksik parçalar, sonsuz sayılar veya farklı projeye ait temel plan reddedilir; sözdizimi tahminle düzeltilmez.
5. **Cevabı içe aktar**, her öneriyi mevcut gerçek doğrulayıcıyla kontrol ederek yalnız taslak kaydeder. Hatalı işlemin bölümü, sıra numarası, sahnesi, zamanı, aslı ve düzeltme seçenekleri saklanır. Diğer geçerli öneriler kaybolmaz. **Düzeltme mesajını kopyala** veya **Cevabı düzelt ve yeniden doğrula** kullanılabilir.
6. Gerçek JPEG taslak önizlemesi incelenir. Yalnız seçili öneriler, **Seçilen önerileri onayla** ile kurguya kaydedilir. Hatalı işlemler uygulamaya katılmaz; kayıtlı taslakta kalır. Daha sonra yalnız düzeltilen öneriler de içe aktarılabilir.

Kısa kaynak geçişlerinin önceki onay akışı korunur: uygun kısa geçiş/siyaha geçiş/hard cut yalnız kullanıcının tekil düzeltme onayıyla taslağa eklenir; timeline uygulama onayı ayrıca gerekir. Kamera ile desteklenmeyen kesim aynı kayıttaysa geçerli kamera bölümü saklanır ve bu durum açıkça açıklanır. Düzeltme mesajı yalnız geçiş önerisini tekrar göndermeyi tarif eder.

## Destek kapsamı

- NAMAN'ın beş bölümü ve mevcut animasyon şablonları korunur. Kamera aralıkları, mevcut yuva sınırındaki geçişler, harita/infografik, metin/vurgu mevcut önizleme ve render yolunu kullanır.
- İsteğe bağlı `sahneler[].media`, yalnız projenin gerçek arşivindeki `provider/media_id/sha256` kimliğidir. `source_start` kaynak başlangıcıdır. Seçim bağımsız görüntü kesiti olarak taslakta gösterilir; temel medya silinmez veya yeniden atanmaz. Pan/zoom bu kesitte uygulanabilir. Hash, süre, sahne ve yuva kilitleri doğrulanır. Bu ek kesitte geçiş desteklenmez; mevcut yuva için ayrı geçiş önerisi gerekir.
- Güvenli ZADIAQ dönüşümü: `cumleler/no + dosya/kaynak_bas` yalnız tek sahneye sığan gerçek cümle saatleri ve tek/tam arşiv dosya eşleşmesiyle görüntü kesitine; basit `tur=veri` kartı NAMAN `stat` şablonuna; ses/stil içermeyen basit `ekran` metni NAMAN vurgusuna dönüşür. Belirsiz dosya veya benzer medya seçilmez.
- ZADIAQ'ın özel harita/şema nesne motoru, ekran görüntüsü katman formatı, sözcük animasyonları ve otomatik ses efektleri taşınmadı. Bunlar sessizce sadeleştirilmez; özgün işlem saklanır ve NAMAN `template/data` veya `text/effect` biçimi istenir. Kullanıcı NAMAN biçimindeki geçerli harita/infografik/yazıları normal şekilde içe aktarabilir.
- Cümle grubu birden fazla NAMAN sahnesine taşıyorsa tahmini bölme yapılmaz; gerçek sahne aralıklarıyla ayrı öneri istenir. Mevcut yuva içindeki yeni kesimler için önce Kurgu'da klip bölünmelidir.
- Mevcut medya, seslendirme, altyazılar ve manuel düzenlemeler korunur. Kaynak/kilit/revizyon değişmiş taslak uygulanmaz; eski kayıtlar taşınmaz veya silinmez. Timeline, medya arama ve render motoru değiştirilmedi. Yeni bağımlılık yok.

## Kaynak ve lisans incelemesi

Kullanıcının `ZADIAQ_Manuel_Plan_Kodlari.zip` dosyasındaki dört dosya okundu; içerik çalıştırılmadı:

| Dosya | İncelenen yaklaşım | NAMAN uyarlaması |
|---|---|---|
| `studio_manuel.py` | Bağlamlı tek görev, parçalı cevap birleştirme, hata/düzeltme mesajı | Mevcut paket genişletildi; bağımsız, sıkı ayrıştırıcı ve işlem bazında taslak doğrulaması yazıldı. |
| `manuel_pencere.js` | Paket → kopyala → cevap/dosya → düzeltme | Yalnız mevcut Manuel Plan penceresi ve taslak hata alanı düzenlendi. |
| `manuel_api.py` | Paket ve içe aktarma bağlantısı | Mevcut FastAPI yollarına bağlandı; doğrudan uygulama yerine taslak/onay korundu. |
| `KILAVUZ.md` | Mimari farkları ve lisans notu | Bağımlı ZADIAQ motorları aktarılmadı. |

ZIP'te LICENSE/COPYING, bağımlılık manifesti veya kilit dosyası yok. Kılavuz, daha büyük kaynak paketin `OKU_BENI.txt` dosyasında OpenMontage için **AGPL-3.0** yazdığını belirtiyor; o dosya bu ZIP'te yok. Bu nedenle üç kesitin ayrı lisans izinleri bu ZIP üzerinden doğrulanamıyor. Bu değişiklikte kaynak dosyalar/kod gövdeleri kopyalanmadı; incelenen iş akışı NAMAN servisleriyle bağımsız uygulandı. Mevcut kaynak bildirimleri ve OpenMontage sınırları korundu; yeni lisans izni varsayılmadı.

ZIP'in Python kodu standart kütüphane yanında `studio_plan`, `studio_sahne`, `studio_efekt`, `studio_core` modüllerine; API kesiti ZADIAQ oturum/dekoratör işlevlerine; JS kesiti ZADIAQ arayüz yardımcılarına bağımlı. Bu bağımlılıklar ZIP'te yok ve kurulmadı/ithal edilmedi. NAMAN'ın FastAPI/SQLite/Pillow/FFmpeg ve mevcut Gemini sağlayıcısı kullanılmaya devam ediyor.

## Doğrulama

Testler yalnız geçici SQLite projeleri ve sentetik medya üzerinde çalışır; kullanıcı dosyaları kullanılmaz. Gemini yanıtı sağlayıcı taklidiyle test edilir. Gerçek ücretli Gemini veya Windows çalıştırması yapılmadı.

- Paket → taklit Gemini talimatı → parçalı JSON → salt okunur doğrulama/taslak → gerçek JPEG önizleme → açık onay → **4 saniyelik gerçek CPU/FFmpeg render** başarılı. Aynı projede arşiv videosu/kamera, harita, infografik, metin ve vurgu uygulandı; hatalı zaman önerisi saklandı.
- Chromium: gerçek `.json` yükleme, paket/düzeltme panosu, Gemini onayını iptal etme, kısmi uygulamayı iptal etme, cevap düzenleme, yeniden doğrulama ve yalnız seçilen öğeyi kaydetme başarılı. Harici ağ isteği ve tarayıcı çalışma hatası yok.
- Önceki kısa geçiş Chromium akışı da başarılı: tekil düzeltme onayı, seçilmeyen öneriyi koruma ve gerçek JPEG.
- Son regresyon: **164 passed**; ek koruma testi **1 passed**; toplam **165 farklı Python testi**. Son parçalayıcı/hata mesajı kontrolü **14 passed** (örtüşen tekrar). Frontend **70 passed**; derleme, JS sözdizimi ve diff kontrolleri başarılı. GitHub teslim sonucu `docs/STATUS.md` içinde kaydedilir.

## GitHub teslimi

Kod commit'i **`7912a9f`**, `fix/manual-package-safe-import` dalına gönderildi. Draft PR başlığı ve açıklaması hazırlandı; ancak oluşturma isteği hem GraphQL hem REST üzerinden **Forbidden** ile reddedildi. Bu ortam PR oluşturamadı; bir PR numarası yok. Main birleştirmesi yapılmadı.

[Gönderilen değişiklikler / PR oluşturma ekranı](https://github.com/naman85331/video-ai-app/compare/fix/manual-plan-transition-handles...fix/manual-package-safe-import?expand=1)

Önerilen PR başlığı: **Manuel Plan: geçerli önerileri koruyan güvenli paket ve içe aktarma**. Taban `fix/manual-plan-transition-handles`; kaynak `fix/manual-package-safe-import`; inceleme durumu draft olmalıdır. Bu rapordaki kullanım/destek kapsamı/doğrulama bölümleri inceleme açıklamasını oluşturur.
