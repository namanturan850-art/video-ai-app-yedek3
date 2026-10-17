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
