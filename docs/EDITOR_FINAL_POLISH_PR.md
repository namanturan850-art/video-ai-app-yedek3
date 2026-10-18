NAMAN'ın PR #92 ile gelen manuel kurgu davranışını koruyarak atomik grup işlemleri, Bezier/Ease/Hold eğrileri, animasyon saatini koruyan bölme ve kısa yerel Program proxyleri ekler. Motion kaynağındaki desteklenen nesneler düzenlenebilir; yerel kalite kontrolü ve ayrı onaylı/iptal edilebilir kapsamlı Gemini kare incelemesi raporları kaydedilir.

Proxy her dört saniyeyi isteğe bağlı hazırlar; desteklenmeyen veya yoğun grafiklerde örnek kare moduna döner. Ortak FFmpeg grafiği ve gerçek sentetik ses/video kontrolleri kullanılır. Yeni eğri/nesne alanları eski belgeler için varsayılanlıdır ve işlemler SQLite revizyon geçmişini korur.

Windows tanı aracı ve manuel CPU CI iş akışı eklendi. Gerçek Windows/WebView2/NVENC/OpenMontage ve canlı Gemini video girişi doğrulanmadı. Tam render checkpoint devamı eklenmedi; doğrulanmış yeniden başlatma korunur. Kısa proxy sesi ile tüm final miksinin loudnorm/compressor bağlam farkı açıkça belirtilir.

Doğrulama: geniş Python kapsamı 491 geçti / 3 atlandı; son fixture tekrarında 53 geçti; başlangıç/orta/son gerçek FFmpeg kare karşılaştırması ayrıca geçti; 65 JavaScript/DOM testi ve gerçek Chromium akışı geçti. 480 saniye/200 klip/503 kayıt sentetik ölçümünde düşük proxy 29,0 FPS; gerçek Windows sonucu değildir.

Ayrıntılı destek sınırları, ölçümler, test sonuçları ve Windows kontrol listesi: `docs/EDITOR_FINAL_POLISH_DELIVERY.md`.

Ücretli API, uzun render veya kullanıcı verisi silme işlemi yapılmadı. Bu PR taslaktır; main'e merge için kullanıcı onayı gerekir.
