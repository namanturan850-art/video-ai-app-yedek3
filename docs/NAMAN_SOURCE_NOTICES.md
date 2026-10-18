# NAMAN kaynak bildirimleri

Bu entegrasyon, kullanıcı tarafından sağlanan `NAMAN_Studio_Kaynak_Paketi.zip`
içindeki ZADIAQ kurgu arayüzünün zaman çizelgesi, önizleme ve bileşen
sözleşmelerinden uyarlanmıştır. Kaynaktaki kod doğrudan ayrı bir sunucu olarak
çalıştırılmamış; mevcut FastAPI, SQLite, stock, subtitle ve motion servislerine
adaptör olarak bağlanmıştır.

- Arayüz yaklaşımı: `NAMAN/arayuz/index.html`, `uygulama.js`, `stil.css`
- Önizleme/zamanlama yaklaşımı: `sahne_onizleme.js`, `sahneMotoru.ts`
- Manuel plan ve arşiv yaklaşımı: `studio_manuel.py`, `studio_core.py`, `studio_izle.py`
- Harita/infografik/vurgu yaklaşımı: `StudioSahne.tsx`, `StudioGrafik.tsx`,
  `StudioKart.tsx`, `StudioVurgu.tsx`, `studioHarita.ts`

Paketin OpenMontage/Remotion kökenli bileşenleri AGPL-3.0 koşullarına tabidir.
Bu depoda zaten bulunan OpenMontage köprüsünün lisans sınırları korunmuştur.
Paketli fontlar kopyalanmamıştır; mevcut depodaki OFL fontlar ve lisans metinleri
kullanılmaya devam eder. NAMAN logosu kullanıcı tarafından sağlanan dosyanın
değiştirilmemiş kopyasıdır.

## 18 Ekim 2026 — Manuel Plan referans incelemesi

`ZADIAQ_Manuel_Plan_Kodlari.zip` içindeki `studio_manuel.py`,
`manuel_pencere.js`, `manuel_api.py` ve `KILAVUZ.md` referans olarak incelendi.
Bu düzeltmede bu dosyaların kod gövdeleri veya bağımlı ZADIAQ motorları
kopyalanmadı. Paket/cevap/düzeltme akışı mevcut NAMAN servisleriyle bağımsız
uygulandı. ZIP'te ayrı lisans metni yok; kılavuzun daha büyük paketteki
OpenMontage AGPL-3.0 notu, bu üç kesitin lisansını tek başına doğrulamıyor.
İnceleme, bağımlılıklar ve güvenli dönüşüm sınırları:
[Manuel paket teslimi](MANUAL_PACKAGE_DELIVERY.md).
