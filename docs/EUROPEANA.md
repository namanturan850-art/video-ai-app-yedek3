# Europeana — görsel kaynağı

**Ayarlar → Europeana** bölümüne anahtarınızı kaydedin. Kaynak, anahtar varsa
Medyayı Tamamla akışına katılır; anahtar olmadan diğer kaynaklar çalışır.
Anahtar şifreli yerel kasada tutulur. Kod veya `.env` düzenlemek gerekmez.

- Arama: `https://api.europeana.eu/record/v2/search.json`, yalnız `X-Api-Key`
  başlığı; `wskey` kullanılmaz. `query`, `reusability=open`, `media=true`,
  `rows=24` ve yinelenen `qf=IMAGE_ASPECTRATIO:landscape`,
  `qf=IMAGE_SIZE:large` parametreleri gönderilir.
- İlk sürüm yalnız görseldir. Video araması ağ isteği yapmadan boş döner;
  video süresi veya boyutu uydurulmaz. Belgelenmeyen sayfalama parametreleri
  eklenmez; yalnız ilk sonuç sayfası aranır.
- `success`, `itemsCount`, `totalResults`, `items`, `error` denetlenir.
  `edmIsShownBy`, `edmPreview`, `rights`, `title`, `dataProvider` hem metin hem
  liste kabul eder. Diğer türler güvenli biçimde elenir.
- Kaynak sayfası için `guid`, yazar için `dcCreator` kullanılır. Müze adı
  (`dataProvider`) yazar yerine kullanılmaz. CC BY / BY-SA için yazar
  bulunamıyorsa sonuç kullanılmaz.
- Her sonuçta `archive_licence()` ile CC0, Public Domain Mark, CC BY veya
  CC BY-SA denetlenir. Eksik, bilinmeyen, NC/ND veya çelişkili lisanslar elenir.
  Lisans URL kontrolü sonuna kadar doğrulanır; izin verilen lisans yoluyla
  başlayıp başka metin içeren adresler kabul edilmez.
- Görsel boyutları müzenin gerçek dosya başlığından okunur (en çok 256 KiB).
  Türü/boyutu okunamayan dosyalar atlanır. Dosya başlığı isteği en çok 15 sn
  zaman aşımıyla çalışır; tam indirme mevcut 20 MB, MIME ve imza sınırlarını
  korur. Müze isteklerine API anahtarı gönderilmez.
- Müze HTTPS alanları DNS ile her istek/yönlendirme öncesi kontrol edilir;
  tüm DNS yanıtları genel adres olmalıdır. IP ile yazılan adresler, özel,
  yerel, link-local, multicast adresler ve başarısız DNS reddedilir. Diğer
  sağlayıcıların sabit alan adı listeleri korunur.
- Önizlemeler yalnız `api.europeana.eu` alanından kabul edilir. Harici
  `edmPreview` önizleme olarak kullanılmaz. Önizleme yönlendirmeleri izlenmez.
- Yazar, başlık, lisans ve Europeana bağlantısı YouTube açıklamasındaki
  Görsel kaynakları bölümüne eklenir; yinelenen dosyalar tekilleştirilir.

## Doğrulama sınırı

Canlı Search API yanıtı bu ortamda incelenemedi: 21 Ekim 2026 tekrarında
Europeana isteği ağ geçidinden 403 aldı; kullanılabilir anahtar da yok.
Testler açıkça sentetik fikstür kullanır; canlı API doğrulaması sayılmaz.
Özellikle `guid`/`dcCreator` eşlemesi ve müze dosyalarına erişim gerçek
anahtarla ayrıca doğrulanmalıdır. Bağlantıyı Test Et yalnız sorgunun kabul
edildiğini doğrular; sıfır aday, kullanılabilir dosya bulunduğu anlamına gelmez.

Bulut ağ politikasında `api.europeana.eu` ve sonuçlarda kullanılan müze dosya
sunucularına izin gerekir. Uygulamanın DNS kontrolü ağ politikasını değiştirmez.

Test: `.venv/bin/python -m pytest tests/test_europeana.py -q`.
Bu dosya Windows smoke iş akışının pytest satırına da dahildir.
