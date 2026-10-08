# Seslendirme — Windows kontrolü

## Part 7 artık ne yapar?

Sahibinin canlı AI33 sonucu doğrulandı: **status=done, type=tts, metadata.audio_url**. Ücretli seslendirme adaptörü etkin (`contract_ready=true`). Güncel onaylı senaryo, kayıtlı API anahtarı, doğrulanmış ses ve geçerli hız varsa **Seslendirmeyi Oluştur** kullanılabilir. Her yeni ücretli görev için ayrıca kredi onayı gerekir.

Ayarlar'da **Önizlemeyi Dinle** hazır sağlayıcı örneğidir, ücretsizdir ve görev oluşturmaz. Projedeki **Kısa TTS Testi (kredi kullanır)** farklıdır: kısa dil örneği için yeni ücretli görev oluşturur; ayrı onay ister, tam anlatım yerine geçmez.

Yeni ayarlarda varsayılan sağlayıcı ElevenLabs. Kayıtlı diğer sağlayıcınız ve anahtar/ses/hız korunur. `.env`, kod veya terminal düzenlemeniz gerekmez. Güncellemede mevcut **data** klasörünü koruyun.

## Gerçek Windows testi — 19 basit adım

1. PR birleştirildikten sonra güncel sürümü alın. **data** klasörünü silmeyin.
2. AI Video Studio'yu siyah uygulama penceresiyle birlikte tamamen kapatın.
3. **START_AI_VIDEO_STUDIO.bat** dosyasına çift tıklayın; yeni siyah pencere açık kalsın.
4. **Ayarlar → AI33 / OpenSpeaker** bölümüne girin.
5. **ElevenLabs** seçili olduğunu kontrol edin. Sağlayıcı değiştiyse **Kaydet** deyin.
6. **Ses adına göre ara** alanına istediğiniz adın bir bölümünü yazın, **Sesleri Getir** deyin ve listeden sesi seçin.
7. **Kaydet** deyin. Anahtar alanı boş; kayıtlı anahtar yalnız maskeli görünmelidir.
8. Güncel senaryosu onaylı mevcut projenizi açın.
9. **Seslendirmeyi Aç** deyin.
10. **Seslendirmeyi Oluştur** düğmesinin etkin olduğunu kontrol edin. Etkin değilse anahtar, ses seçimi ve senaryo onayını Ayarlar/proje ekranından tamamlayın; hız 0,5–1,5 olmalı.
11. **Seslendirmeyi Oluştur** düğmesine bir kez basın.
12. Kredi uyarısını **bir kez** onaylayın.
13. Bekleyin; yeniden Oluştur'a basmayın. Görev oluşturuluyor → AI33 seslendirme hazırlıyor → Ses dosyası indiriliyor → Tamamlandı görünür.
14. Görev kimliğinin aynı kaldığını ve hesabınızda tek yeni görev oluştuğunu kontrol edin. Ağ/indirme hatasında **Devam Et** aynı görevi kullanır; yeni ücretli görev oluşturmaz.
15. Ses dosyasının yerelde hazır olduğunu kontrol edin.
16. Oynatıcıdan sesi dinleyin. **Ses Dosyasını Aç** yerel dosyayı açar. Varsa gerçek süre, ses adı/hız/kaynak senaryo/tarih görünür.
17. Uygulamayı tamamen kapatıp `.bat` dosyasıyla tekrar açın.
18. Projede tamamlanmış sesin ve sürümünün hâlâ durduğunu kontrol edin. Hata durumunda kayıtlı görev için **Devam Et** kullanın.
19. Mevcut Pixabay videoları, sahneler ve medya seçimlerinin değişmediğini kontrol edin.

**Bu test kredi kullanabilir.** Bulut doğrulamasında canlı ücretli API çağrısı yapılmadı. Otomatik testler ve gerçek FastAPI/Chromium denemeleri dış API yanıtlarını taklit eder. **Live provider test must be run by owner on Windows.**

## Ses listesini rahat kullanın

Önce ad araması kullanın: örneğin **Bill → Sesleri Getir**. İlk 30 eşleşme gösterilir. **Daha Fazla Ses Yükle** sonraki 30'u ekler; yinelenen kimlik gösterilmez. **Önceki/Sonraki Sayfa** tek sayfayı gösterir. Sağlayıcı/arama değişince sayfa 1'den başlar; farklı sağlayıcılar karışmaz.

**Tüm Sesleri Getir** isteğe bağlıdır; yavaşlatma uyarısından sonra sıralı en fazla 10 sayfa/300 ses yükler, boş sayfada durur. Kendiliğinden çalışmaz. Yükleme sırasında diğer Ayarlar bölümleri kullanılabilir; hata olursa düğmeler geri açılır. Önceki büyük liste yeniden açılışta tamamen çizilmez; kayıtlı sesiniz korunur.

**Önizlemeyi Dinle** varsa önce bu ücretsiz hazır örneği kullanabilirsiniz. Anahtar/Authorization/çerez/referrer örnek adresine gönderilmez. Ses bilgileri eksik olabilir; bu listeyi bozmaz.

## Hata ve devam etme

- **Anahtar reddedildi:** Ayarlar'dan doğru AI33 anahtarını kaydedin; sonra aynı görev için Devam Et kullanın.
- **İstek sınırı/zaman aşımı/bağlantı veya indirme hatası:** görevin kimliği korunur. Bir süre bekleyip **Devam Et** deyin.
- **Görev kimliği alınamadı:** uygulama otomatik ücretli tekrar yapmaz. Hesabınızın mevcut görevlerini inceleyin; tekrar ödeme onaylamadan destek isteyin.
- **Yanıt biçimi farklı:** mevcut görev/yerel sesler korunur. **Mevcut Görevi İncele** veya **Görev Geçmişini İncele** ile yalnız güvenli sonucu paylaşın. Anahtar, özel URL ve ham yanıt paylaşmayın.
- **Ses süresi daha sonra hesaplanacak:** dosya yine oynatılabilir; FFmpeg/ffprobe olmaması tamamlanmış sesi silmez.

Tanılama salt okunur GET kullanır, yeni ücretli görev oluşturmaz. Alan adları/türleri ile güvenli durum/tür değerlerini gösterir. Canlı TTS sözleşmesi artık doğrulandı; bu ekran runtime'da adaptör veya ücretli kilit ayarı değiştirmez.

## Sürümler ve kaynak metin

Tam anlatım yalnız güncel onaylı senaryoyu kullanır; sahne notu/overlay/stok sorgusu kullanılmaz. Senaryo değiştirilirse mevcut ses **Eski senaryo sürümüne ait** olarak işaretlenir; otomatik ücretli üretim yapılmaz.

**Yeniden Oluştur**, “Yeni AI33 görevi oluşturulacak ve ek kredi kullanabilir. Mevcut seslendirme korunacak.” uyarısıyla yeni görev/sürüm oluşturur. Önceki dosya silinmez. **Kısa TTS Testi (kredi kullanır)** ayrı kısa örnektir; aktif tam anlatımı değiştirmez. Tamamlanmış eski sürümler aktif seçilebilir.

Ses dosyaları: **data/projects/<proje-kimliği>/voice/**. Oynatma yalnız uygulamanın yerel dosya yoludur; özel sağlayıcı indirme URL'si gösterilmez. Şifreli anahtar SQLite'a yazılmaz; mevcut şema 8/kasa/proje/senaryo/sahne/stok dosyaları korunur.

Part 8 için yerel ses kimliği/yolu/gerçek süre (ölçülemediyse boş), kaynak senaryo, ses/hız/dil ve hazır durumu sunulur. Transcript yoktur, altyazı/sahne senkronu yapılmaz. **Part 8 başlatılmadı.** [Kesin API sözleşmesi](../AI33_INTEGRATION_NOTES.md).
