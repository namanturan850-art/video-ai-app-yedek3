# Lisanslar ve üçüncü taraf bileşenler

Bu sayfa, uygulamanın kullandığı dış bileşenlerin lisanslarını sade dille özetler. Hukuki tavsiye değildir; kesin koşullar için her bileşenin kendi lisans metnine bakın.

| Bileşen | Nerede | Lisans / koşul | Not |
|---|---|---|---|
| **OpenMontage** | Ayrı klasöre isteğe bağlı kurulur (`INSTALL_OPENMONTAGE.bat` veya Ayarlar → Motor Durumu → “Eksikleri kur”) | GNU AGPL v3 | Uygulamaya **gömülmez**, kaynak kodu kopyalanmaz. Kendi klasöründe, kendi lisans dosyalarıyla durur. Değiştirip başkalarına ağ üzerinden hizmet olarak sunarsanız AGPL kaynak paylaşımı ister; tek kişilik yerel kullanımda bu durum oluşmaz. |
| **Remotion** | OpenMontage kurulumuyla gelir | Remotion lisansı | Bireyler ve küçük ekipler için ücretsizdir; belirli büyüklüğün üzerindeki şirketler için ücretli şirket lisansı gerekebilir. Güncel koşullar: https://www.remotion.dev/docs/license |
| **Yazı tipleri** (Inter, Montserrat, Oswald, Bebas Neue, Lora) | `app/static/fonts/` | SIL Open Font License 1.1 | Lisans metinleri aynı klasörde (`OFL-*.txt`). Videolarda serbestçe kullanılabilir; yazı tipi dosyasının kendisi tek başına satılamaz. |
| **Ses efektleri** (click, rise, hit, whoosh) | `app/static/sfx/` | Bu proje tarafından üretildi | `tools/make_sfx.py` ile matematiksel olarak sentezlenir; dış kaynak yoktur. Kanal için yüklediğiniz efektlerin haklarından siz sorumlusunuz. |
| **Dünya haritası** (motion harita şablonu) | `app/motion/world_land.json` | Kamu malı (Natural Earth 1:110m) | Atıf zorunlu değildir. |
| **Pexels / Pixabay medyası** | İndirilen stok videolar/görseller | Her sitenin kendi lisansı | Ticari kullanım genelde serbesttir, atıf istenmez ama önerilir. YouTube sekmesi açıklamaya otomatik “stok kaynakları” bölümü ekler. Kişi/marka içeren görüntülerde ek dikkat gerekir. |
| **FFmpeg** | Bilgisayara ayrıca kurulur | LGPL/GPL (derlemeye göre) | Uygulamayla birlikte dağıtılmaz. |
| **Python paketleri** (FastAPI, Pillow, httpx …) | `.venv` | MIT / BSD / HPND vb. açık kaynak | `requirements.txt` içindeki sürümler. |

Gemini, Claude, AI33 gibi bulut hizmetlerinin kullanım koşulları ilgili hesabınızın sözleşmesine tabidir; uygulama bu hizmetlerin içeriğini değiştirmez.
