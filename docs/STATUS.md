# AI Video Studio — Durum

## 2026-10-07 — C) Gemini

Tamamlandı:
- İsteğe bağlı Gemini Ayarlar bölümü: web arayüzünden API anahtarı, mevcut şifreli yerel kasa, boş parola alanı ve yalnızca maskeli güvenli yanıtlar.
- Model alanı ve resmi Developer API'den alınan model listesi; sabit/tahmin edilen gerçek model kimliği yok.
- Kaydet, onaylı Temizle, Modelleri Getir ve salt okunur Bağlantıyı Test Et; Türkçe ilerleme, eksik ayar, erişim, kota ve ağ hata mesajları.
- `ScriptProvider` protokolü ve Gemini adaptörü: resmi `generateContent` çağrısı, özgün içerik talimatı, düşünce parçalarını dışlama, tamamlanmamış/engellenmiş çıktıyı reddetme ve olası anahtar yankısını maskeleme.
- Yalnızca resmi Google Gemini Developer API; web sitesi tarama/otomasyon veya Gemini Plus / Google AI Pro abonelik oturumu yok. API anahtarı yalnızca resmi HTTPS başlığında, yönlendirme takibi yok.
- Yeni Proje ve mevcut proje düzenleme ekranlarında Ollama / OpenAI / Gemini motor seçimi; seçim SQLite'ta kalıcıdır, anahtarlar projeye yazılmaz.
- Şema 1/2 → 3 güvenli yükseltme; eski projeler varsayılan Ollama ile korunur, yerel ayarlar ve dosyalar silinmez.
- Windows başlatıcısı ve mevcut Aşama 1–3 davranışları korunur; API anahtarı yokken uygulama açılır.
- Kullanım ve doğrulanmış resmi API sözleşmesi kaynakları: docs/GEMINI.md; README, Ayarlar ve Projeler rehberleri güncellendi.

Kapsam ve doğrulama:
- Gemini yalnızca sağlayıcı adaptörü/ayar/motor seçimi olarak eklendi. Uçtan uca Senaryo Oluştur ekranı ve diğer üretim aşamaları henüz yok; Ollama/OpenAI üretim adaptörleri bu değişiklikte eklenmedi.
- Tam test paketi: **215 geçti, 1 mevcut Windows DPAPI testi Linux nedeniyle atlandı; toplam 216 test, hata yok.** Gemini için 59 yeni test; gerçek anahtarlar yerine sentetik test verileri ve taklit Google API yanıtları kullanıldı.
- Testler: isteğe bağlı çevrimdışı başlangıç, şifreli kayıt, maskeleme, API/günlük/proje sızıntısı, doğrulama, kalıcılık, model listeleme/sayfalama, resmi istek sözleşmesi, erişim/kota/zaman aşımı/yönlendirme hataları, engellenmiş/eksik üretim, üç motor seçimi ve eski şema yükseltmesi.
- Chromium: anahtarsız açılış, maskeli kayıt, model listesi/seçimi, bağlantı testi, hata gövdesinin gizlenmesi, temizleme, üç motor, mevcut proje düzenleme, yeniden başlatmada kalıcılık ve mobil görünüm geçti; JavaScript hatası yok. Google API yanıtları taklit edildi.
- **Gerçek Google API anahtarıyla canlı bağlantı/üretim denenmedi.** Bu bulut ortamında Windows çift tıklama/DPAPI doğrulaması yapılamaz; önceki sürümlerin Windows testi sahibi tarafından tamamlanmıştır.

## 2026-10-07 — Aşama 3

Tamamlandı:
- Türkçe Yeni Proje formu: ad, konu, isteğe bağlı YouTube referansı, dil (varsayılan Almanca), hedef dakika, stil, minimum/maksimum sahne saniyesi, altyazı/müzik/küçük resim tercihleri.
- Alan doğrulaması, Türkçe alan hataları, kayıt sırasında ilerleme ve oluşturulan projeye yönlendirme.
- SQLite proje kaydı; benzersiz UUID, güvenli metaveri güncelleme ve UTC created_at/updated_at zamanları.
- Her proje için script, scenes, stock, voice, subtitles, music, render ve logs klasörleri.
- Projeler listesi: isim, konu, dil, hedef süre, Türkçe durum, oluşturulma/güncelleme tarihleri; açma ve açık Türkçe onayla silme.
- Yalnızca seçilen proje kaydı/klasörü silinir; eksik klasörler güvenle ele alınır. Sembolik bağlantı ve Windows reparse/junction denetimleri başka konuma silme yapılmasını engeller.
- Taslak/Hazır/İşleniyor/Tamamlandı/Hata durumları için veritabanı desteği. Yeni projeler Taslak; bu aşamada üretim durum geçişi yok.
- Detay ekranında dokuz üretim aşaması yalnızca Bekliyor / Hazır değil yer tutucusu.
- Eski şema 1'den 2'ye işlemsel, eklemeli yükseltme; mevcut tablolar, şifreli ayarlar ve yerel dosyalar korunur. Proje tablosunda API anahtarı alanı yoktur.
- Mevcut Windows başlatıcısı değiştirilmedi. Kullanım ve API açıklamaları docs/PROJECTS.md ve README'de.

Kapsam dışında:
- Referans analizi/indirme, senaryo üretimi, Ollama/OpenAI üretimi, stok medya, AI33, render, altyazı üretimi ve YouTube yükleme yok. **Aşama 4 başlatılmadı.**

Doğrulama:
- Aşama 1 ve 2 sahibi tarafından birleştirilip gerçek Windows bilgisayarında test edildi.
- Tam test paketi: **156 geçti, 1 mevcut Windows DPAPI testi Linux nedeniyle atlandı**. Aşama 1–2 testleri de dahil; hata yok.
- Chromium: eski şema yükseltme, Türkçe hatalar, oluşturma/yönlendirme, sekiz klasör, dokuz yer tutucu, düzenleme, listeleme, silme onayı/iptali, diğer projeyi koruma, yeniden başlatmada proje/ayar kalıcılığı, metinlerin güvenli gösterimi, ağ hatasında yeniden deneme ve mobil görünüm geçti. JavaScript hatası yok.
- Aşama 3 bu Linux makinesinde doğrulandı; yeni proje akışının gerçek Windows testi henüz burada yapılamadı.

## 2026-10-07 — Aşama 2 (geçmiş kayıt)

Tamamlandı:
- Türkçe Ayarlar: Genel, Ollama, OpenAI (isteğe bağlı), Pexels, Pixabay, AI33, FFmpeg ve YouTube (Daha sonra).
- Kaydet, onaylı Temizle ve desteklenen bölümlerde Bağlantıyı Test Et; ilerleme ve Türkçe hata mesajları.
- Web arayüzünden API anahtarı girişi; kayıttan sonra boş parola alanı ve yalnızca maskeli durum.
- Fernet ile şifrelenmiş yerel kasa; Windows'ta şifreleme anahtarı kullanıcı hesabına bağlı DPAPI ile korunur. POSIX'te özel dosya/klasör izinleri.
- Atomik kayıt, bölüm bazlı güncelleme, boş anahtarda mevcut değeri koruma, yeniden açılışta kalıcılık.
- Güvenli ayar API'leri; doğrulama hatalarında girilen anahtarların geri dönmemesi; köken/Host kontrolü ve önbelleğe alınmayan yanıtlar.
- Resmi API belgesi doğrulanarak yalnızca Ollama yerel model listesi bağlantı kontrolü. Model üretimi/indirme yok.
- FFmpeg otomatik durum/yol algılama ve sürüm komutuyla kontrol; FFmpeg veya API anahtarı yokken uygulama açılır.
- Yerel kasanın Git tarafından yok sayılması; başlangıç düzeyinde kullanım ve saklama dokümantasyonu.

Bilerek kapalı / sonraki aşamalar:
- AI33 bilgileri kaydedilebilir; **AI33 API belgeleri gerekli**. Gerçek test ve seslendirme yok.
- OpenAI/Pexels/Pixabay bağlantı testleri belgelenmiş sözleşme sağlanana kadar açıklamalı yer tutucudur; hiçbir gerçek çağrı yapılmaz.
- Yeni Proje, Projeler, senaryo, stok arama, seslendirme, altyazı, render ve YouTube yükleme geliştirilmedi. **Aşama 3 başlatılmadı.**

Doğrulama:
- Aşama 1 sahibi tarafından gerçek Windows bilgisayarında doğrulandı; çift tıklama başlatıcısı çalışıyor.
- Tam test paketi: **75 geçti, 1 Windows DPAPI testi Linux nedeniyle atlandı**; Aşama 1 testleri de dahil.
- Gerçek Chromium tarayıcısında sekiz bölüm, kaydetme/maskeleme, yeniden yükleme, temizleme, doğrulama, ağ hatası/yeniden deneme ve mobil görünüm geçti; JavaScript hatası yok.
- Ollama bağlantısı belgelenmiş yanıtı sunan yerel test sunucusuyla, FFmpeg bağlantısı gerçek çalıştırılabilir dosyayla doğrulandı.
- Windows başlatıcısının güncellenen bağımlılık kurulum akışı Linux üzerinde tekrar çalıştırılıp doğrulandı.
- Aşama 2'nin gerçek Windows DPAPI testi Windows gerektirir; Linux'ta açıkça atlanır.

## 2026-10-07 — Aşama 1 (geçmiş kayıt)

Tamamlandı:
- Python 3.12+ ve FastAPI ile yerel uygulama iskeleti.
- Türkçe, mobil ekranlara uyumlu ana sayfa: Yeni Proje, Projeler, Ayarlar, Tanılama.
- İlk açılışta SQLite veritabanı oluşturma; tekrar açılışta mevcut verileri koruma.
- `/api/health` ve güvenli `/api/diagnostics` uçları.
- Uygulama/Python sürümü, işletim sistemi, veritabanı, FFmpeg ve veri klasörü yazma kontrolü.
- FFmpeg yokken de açılış; Tanılama ekranında açıklama.
- Windows çift tıklama başlatıcısı: Python kontrolü, otomatik `.venv` ve bileşen kurulumu, hazır olunca tarayıcı açma, Türkçe hata ve ilerleme mesajları.
- Yerel veri, günlük ve gizli dosyaları Git dışında tutma.
- Yeni başlayanlar için Windows kullanım açıklamaları.

Yer tutucular:
- Yeni Proje, Projeler ve Ayarlar ekranları yalnızca açıklama gösterir.
- Hiçbir sağlayıcı bağlı değildir; sahte başarılı API işlemleri yoktur.

Kapsam dışında / henüz yapılmadı:
- Ayar veya anahtar kaydetme, proje oluşturma, senaryo, stok medya, AI33 seslendirme, altyazı, render ve YouTube yükleme.
- AI33 API davranışı uydurulmadı; mevcut entegrasyon notları geçerlidir.

Doğrulama:
- Backend, gerçek yerel HTTP sunucusu ve başlatıcı davranışları için 18 pytest testi: tamamı geçti; uyarı yok.
- Chromium tarayıcısında ana sayfa, yer tutucular, Tanılama, yenileme, bağlantı hatası/iyileşmesi ve mobil görünüm doğrulandı; JavaScript hatası yok.
- Sıfırdan `.venv` oluşturma ve kurulum ile tekrar açılış doğrulandı. Gerçek başlatıcı iki kez açılıp sağlıklı HTTP yanıtı alındı.
- Linux bulut makinesinde çalıştırıldı. Windows `.bat` dosyasının gerçek çift tıklama testi Windows makinesi gerektirir; bu makinede yapılamaz.

Aşama 1 tamamlandıktan sonra proje Aşama 2 geliştirmesine hazırdır. Aşama 2 başlatılmadı.
