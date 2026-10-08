# Seslendirme — Windows kontrolü

## Bu taslakta ne kullanılabilir?

Ayarlar → **AI33 / OpenSpeaker** ekranında anahtar kaydetme/maskeleme, sağlayıcı ve hız, salt okunur bağlantı testi çalıştırılabilir. Eski kayıtlar korunur. Projede **Seslendirmeyi Aç** bağlantısı ve Seslendirme ekranı vardır.

**Part 7 henüz birleştirmeye hazır değildir.** Herkese açık API belgesi ses kaydının ve tamamlanan görevin alanlarını tanımlamıyor. Görev oluşturma örneği alındı; ses listesi ve görev sonucu örnekleri hâlâ gerekli. Bu yüzden Sesleri Getir güvenli belge tanısı gösterir; **Ses Önizle / Oluştur / Yeniden Oluştur kapalıdır ve kredi harcanmaz**. Bilinmeyen alanlar tahmin edilmedi. Ayrıntı: [doğrulanan ve eksik API sözleşmeleri](../AI33_INTEGRATION_NOTES.md).

## Şimdi yapılabilecek basit kontrol

1. Güncelleme sırasında mevcut **data** klasörünü koruyun. Programı kapatıp yeni uygulama dosyalarını aynı klasöre koyun.
2. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın. Siyah pencere açık kalsın.
3. **Ayarlar → AI33 / OpenSpeaker** bölümünü açın.
4. API anahtarını yazın ve **Kaydet** deyin. Alan boşalmalı; kayıtlı anahtar yalnız maskeli görünmelidir.
5. **Bağlantıyı Test Et** deyin. Bu işlem ses üretmez, kredi harcamaz. Başarılı HTTP/JSON okuması bağlantıyı gösterir; kredi sayısı bilinmiyorsa bunun mesajı görünür.
6. Ses sağlayıcısını seçip **Kaydet → Sesleri Getir** deyin. Bu taslakta resmî yanıt alanları eksik olduğundan güvenli tanı beklenir. Anahtar, başlık veya özel URL görünmemelidir.
7. Mevcut projenizi açıp **Seslendirmeyi Aç** deyin. Güncel onaylı senaryo/dil/karakter sayısı görünmeli; onay yoksa “Önce senaryo sürümünü onaylayın.” görünmelidir.
8. Programı kapatıp yeniden açın. Projeler, onaylı senaryolar, sahneler, eski stok dosyaları ve maskeli ayarlar durmalıdır.

Gerçek anahtarı, **data/secrets** klasörünü veya özel ses indirme URL'sini paylaşmayın. Belge eksikliği bağlantı anahtarınızın bozuk olduğu anlamına gelmez. Teknik bilgisi olmayan kullanıcının kod, .env veya terminal düzenlemesi gerekmez.

## Yanıt sözleşmeleri doğrulanıp kilit açıldıktan sonra canlı ses kontrolü

Aşağıdaki adımlar **bu taslakta henüz başlatılamaz**; bir sonraki belgeli düzeltmenin canlı kabul listesidir:

1. Ayarlar → AI33 / OpenSpeaker → anahtarı **Kaydet → Bağlantıyı Test Et**.
2. Sağlayıcıyı seçin → **Kaydet → Sesleri Getir**. İsterseniz arama/sayfa kullanın.
3. Listeden sesi seçin; hızı **1,0** bırakın → **Kaydet**.
4. Güncel senaryosu onaylı projenizde **Seslendirmeyi Aç** deyin.
5. İsterseniz **Ses Önizle** ile kısa ücretli örneği onaylayıp dinleyin. Önizleme tam anlatım yerine geçmez.
6. **Seslendirmeyi Oluştur** deyin; kredi kullanımı uyarısını kabul edin.
7. Görev kimliği ve durum görünür. Hazırlanırken bekleyin; tekrar Oluştur'a basmayın.
8. Tamamlandığında ses oynatıcısından dinleyin veya **Ses Dosyasını Aç** deyin. Biliniyorsa gerçek ses süresi gösterilir.
9. Programı yeniden açın. Ses sürümü/dosyası korunmalıdır. Yarım görev varsa **Devam Et** yalnız aynı görev kimliğini izlemelidir; sağlayıcı hesabında ikinci görev açılmamalıdır.
10. İsterseniz **Yeniden Oluştur** uyarısını onaylayın: ek kredi kullanır, yeni sürüm oluşturur ve eski dosyayı korur. Başarısız üretim eski aktif sesi kaldırmaz.
11. Senaryoyu değiştirirseniz eski seste **Eski senaryo sürümüne ait** uyarısı beklenir; kendiliğinden yeni görev açılmaz.

**Live provider test must be run by owner on Windows.** Bulut testlerindeki dış API ve ses dosyası yanıtları taklittir. Chromium kontrolünde gerçek FastAPI, şifreli kasa, SQLite, yerel WAV oynatma ve yeniden açılış sınandı; bu OpenSpeaker canlı entegrasyonunun çalıştığını kanıtlamaz.

## Kayıtlar ve sonraki aşama

Ses dosyaları: **data/projects/&lt;proje-kimliği&gt;/voice/**. İsimler uygulama tarafından güvenli biçimde oluşturulur. Önizlemeler ve sürümler farklı dosyalardır; mevcut stok/sahne dosyaları değişmez. SQLite şema 8'de sürüm, iş, uzak görev kimliği, hız/ses seçimi, kaynak metin izi ve aktif seçim tutulur; API anahtarı tutulmaz.

Hazırlanan handoff: yerel ses yolu, süre, kaynak senaryo/seslendirme kimlikleri, ses, hız, hedef dil, readiness ve zamanlama kaynağı. Doğrulanmış transcript olmadığı için `transcript=null`; sahne süreleri tahmini kalır. **Part 8 başlatılmadı:** altyazı, gerçek kelime/sahne zamanlaması, video render, müzik ve YouTube yükleme yoktur.
