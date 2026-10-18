# Manuel Plan — aynı sahnede birden fazla zaman aralığı

Temel dal: `feature/naman-simple-workflow` (`7d0a0c3`). Düzeltme dalı: `fix/manual-plan-interval-import`.

## Sorun ve düzeltme

İçe aktarıcı, her `sahneler` önerisini `start/end` değerlerini kullanmadan sahnenin bütün görüntü yuvalarına uyguluyordu. Geçişleri de öneri bitişi yerine sahne sonuna ekliyordu. Benzersiz `object_id` değerleri, aynı `slot_id` için çoğalan adjustment/transition kayıtlarını önlemiyordu.

- Kamera önerileri yalnız kendi zaman aralığıyla kesişen görüntü yuvalarına bağlanır. Birden fazla aralık tek yuva adjustment'ında, yerel zamanlı keyframe'lerle birleşir. Aralıklar arasındaki boşluklarda hareket uygulanmaz; yuva sınırını aşan hareketin ilerleyişi korunur.
- Geçiş önerisi kendi `end` noktasındaki bitişik yuvalara bağlanır. Aynı sınırdaki aynı geçiş tek kayda birleşir ve taslak değişikliklerinde açıklanır. Farklı geçişler çakışma hatası verir.
- Çakışan kamera önerileri sahne, saniye, yuva ve öneri kimlikleriyle bildirilir. Manuel kamera ayarının üzerine yazılmaz. Diğer özelliklerdeki mevcut manuel dönüşüm/efekt/keyframe'ler korunabilir ve aynı adjustment içine güvenli biçimde eklenir.
- Önizleme ve onay, mevcut adjustment'ı ikinci kez eklemek yerine doğrulanmış birleşik kaydı kullanır. Kısmi onay, eski taslağın reddi, yeniden açma ve geri alma korunur.
- Taslak oluşturulduktan sonra görüntü yuvaları, kesitler, medya kaynakları veya kilitler değişirse önizleme/onay için yeni taslak gerekir.
- `/manual/validate`, manuel modda içe aktarıcıyla aynı aralık denetimlerini yapar; doğrulama draft kaydı veya timeline revizyonu oluşturmaz. Cevabı içe aktarma taslak oluşturur; uygulama yalnız açık onayla yapılır.
- Gemini paketine tahmini stok saatleri dışında **gerçek editör yuva saatleri** ve desteklenen işlem/sınır kuralları eklenmiştir.
- Arayüz, medya dosyaları, görüntü sırası, kilitler, temel altyazı ve seslendirme değiştirilmez. Şema/veritabanı geçişi ve ücretli servis çağrısı yoktur.

## Kesim sınırı

Mevcut render motorunda transition kaydı, bitişik iki **mevcut** ana görüntü yuvasının sınırına aittir. Bir öneri mevcut yuvanın içindeki yeni bir kesimi veya son videonun bitişinde geçişi istiyorsa bu düzeltme onu başka saniyeye taşımaz, sessizce atlamaz veya mevcut görüntüleri kendiliğinden bölmez. Sahne/saniye belirten hata verir; Kurgu'da önce klibi bölmek veya paketteki mevcut yuva sınırını kullanmak gerekir. Aynı sahnede birden fazla mevcut kesim ve geçiş desteklenir. Kamera hareketleri yuva içindeki kısmi aralıkları da destekler.

## Testler ve dosya durumu

- 119 farklı Python testi geçti. Gruplar: mevcut editör/manuel kurgu/paket testleri 95 passed; render/polish/projeksiyon grubu 53 passed; yeni aralık grubu 18 passed. Gruplar örtüşür; toplam 119 test ayrıca collection ile doğrulandı.
- Yeni regresyonlar: 16 `sahneler` kaydı / 6 `scene_id`, benzersiz `object_id`; aynı yuvada birden fazla hareket, bitişik ve aralıklı hareketler, iki yuvayı aşan hareket, aynı sahnedeki birden fazla geçiş/kesim, geçiş tekrarı/çakışması, manuel ayar/kilit koruması, salt okunur doğrulama, onay/kısmi onay/eski taslak ve undo.
- Gerçek HTTP/SQLite/FFmpeg testi: doğrulama → JSON cevap → taslak → JPEG önizleme → açık onay → 4 saniyelik yerel final render. Kamera aralıkları uygulanırken temel görüntü/altyazı/medya revizyonu korunur.
- `NAMAN_2_0_Kurgu_Plani(1).json` bu oturumda ekli değildi; workspace/attachments içinde bulunamadı. Gerçek dosyanın işlendiği iddia edilmez. `tests/fixtures/manual_plan_16_intervals_6_scenes.json` yalnız kullanıcının tarif ettiği yapıyı yeniden üreten, anonim ve sentetik regresyondur. Gerçek dosyaya karşı birebir test için dosyanın eklenmesi gerekir.
- UI dosyasında değişiklik yok. Python derleme ve `git diff --check` geçti. Canlı Gemini ve uzun/kullanıcı projesi renderı yapılmadı.
