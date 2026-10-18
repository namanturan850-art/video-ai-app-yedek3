# NAMAN 2.0: manuel kurgu, güvenli silme ve onaylı taslaklar

Yeni projelerde medya hazırlama yalnız kaynak sağlar; yaratıcı kararlar Manuel Kurgu'da kullanıcıya aittir. Temel medya kaldırılınca kaynak ve anlatım saati korunur, boş yuva gerçek siyah kareye dönüşür. Yedi izdeki ek nesneler, altyazı sürümleri ve ses düzenlemeleri kalıcı model, ortak Undo/Redo ve gerçek Program/FFmpeg çıktısına bağlanır.

Otomatik/AI JSON önerileri yalnız açık komutla ayrı taslak oluşturur; fark/çakışma ve kaydetmeden örnek kare önizlemesinden sonra seçili nesneler onaylanır. Gemini örnek-kare paylaşımı ve maliyeti ayrı açık onay gerektirir; kayıtlı bulgular video sürümü kapsamında yönetilir. Müzik paneli tema kontrastı, monitör altı oynatma kontrolleri ve dikey timeline araçları düzeltilir.

PR #90/#91 korunur; SQLite 15→16 eklemelidir. Eski projeler okumada dönüştürülmez. Ücretli servis, uzun kullanıcı renderı ve kullanıcı dosyası silme yapılmadı.

Doğrulama: geniş Python paketi **454 geçti / 3 atlandı**; son manuel paket **26**, kalite/performans **73**, eski stok kabul paketi **17**, çalışma alanı/frontend/masaüstü birim paketi **5**, DOM paketi **7** testle geçti. Hedefli tekrarlar örtüşür; sayılar toplam değildir. Gerçek yerel API/SQLite/Chromium akışı, beş viewport ve **4 saniyelik 1080p/30 fps native FFmpeg çıktı** doğrulandı. Windows WebView2/NVENC ve canlı Gemini/Mapbox bu Linux ortamında doğrulanmadı. Ayrıntı ve sınırlar: [Türkçe teslim raporu](MANUAL_FIRST_DELIVERY.md).

**Draft olarak incelenmeli. Kullanıcı ayrıca açıkça onaylamadan main'e merge edilmemeli.**
