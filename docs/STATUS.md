# AI Video Studio — Durum

## 2026-10-07 — Aşama 2

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
