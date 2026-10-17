# NAMAN ZADIAQ arayüzü ve premium sağlayıcı kaldırma raporu

Tarih: 2026-10-17

## Arayüz

Sağlanan ZADIAQ paketindeki `arayuz/index.html`, `arayuz/stil.css` ve
`arayuz/uygulama.js` düzeni mevcut tek-sayfa FastAPI arayüzüne uyarlandı.
Uygulama açılışında koyu NAMAN kabuğu, proje seçici ve Üretim / Kurgu / Ayarlar
navigasyonu görünür. Kurgu ekranında yedi iz, gerçek ses elementi, ortak oynatma
zamanı, ileri/geri sarma, sığdırma, sahne alanları, medya yeniden seçimi ve klip
aralığı kontrolleri bulunur.

## Freepik ve Magnific

Yeni işlemlerde sağlayıcı tamamen devre dışıdır: istemci dosyası, ayar modeli,
ayar ekranı, bağlantı testi, arama fabrikası, premium fallback, CDN izinleri ve
indirme yolu kaldırıldı. Eski şifreli ayarlardaki bölüm ilk güvenli açılışta
diğer ayarlara dokunmadan silinir.

Tarihsel `provider=magnific` medya kaydı şemada yalnız geriye dönük okuma için
kalır. Yerel dosya ve hash geçerliyse eski proje bunu görüntüleyebilir/render
edebilir. Dosya yoksa hiçbir ağ isteği yapılmaz ve sağlayıcının kaldırıldığı
bildirilir.

Yeni otomatik sıra: doğrulanmış proje-yerel arşiv → Pixabay → Wikimedia Commons
→ motion/harita/infografik. Yerel adaylar da mevcut teknik, dönem/coğrafya,
kilit ve 7/10 onay kurallarından geçer.

## Doğrulama sınırları

Saf NAMAN ve sağlayıcı kaldırma testleri 10/10 geçti. Geniş çevrimdışı pakette
ilk 41 test geçti; sonraki ağır medya/FFmpeg testi 240 saniyelik ortam sınırında
tamamlanmadı. Chromium bu kapsayıcıda yerel port ve headless profil soketi
açamadığı için ekran görüntüsü üretilemedi. Windows, GPU, ücretli Gemini ve
8–10 dakikalık gerçek render çalıştırılmadı.
