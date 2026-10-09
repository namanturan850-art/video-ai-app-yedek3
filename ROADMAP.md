# 12-Part Roadmap

## Part 1 — Repository + Local App Skeleton
- FastAPI app
- SQLite initialization
- Turkish dashboard
- START_AI_VIDEO_STUDIO.bat
- health/diagnostics
- tests

## Part 2 — Settings + Secret Handling
- settings UI
- local secret/config storage
- `.gitignore`
- connection test placeholders

## Part 3 — Project Creation + Database
- create/list/open projects
- project folders
- status pipeline

## Part 4 — Script Providers
- provider interface
- Ollama integration
- optional OpenAI integration
- original-content prompt flow
- script preview/edit/approve

## Part 5 — Scene Planning
- split script into scenes
- visual query generation
- edit rules
- scene editor

## Part 6 — Pexels + Pixabay
- official API clients
- media search
- preview/select/download
- deduplication history
- local caching

## Part 7 — AI33 TTS
- provider interface already present
- only wire real API after verified docs are supplied
- voices/model discovery if documented
- long-text chunking if required by API
- audio merge
- timing metadata if supported

## Part 8 — Subtitles

Uygulandı: yerel gerçek ses süresi, yaklaşık ağırlıklı zamanlama, SRT/VTT, sürüm/editör/önizleme, sahne ve stok zamanlama handoff'u. [Windows kontrolü ve sınırlar](docs/SUBTITLES.md). Part 7 sahibi tarafından canlı Windows'ta doğrulandı; Part 8 gerçek ses süresi, altyazı ve korunmuş medya sahibi tarafından canlı Windows’ta doğrulandı.

- create SRT/VTT
- use exact TTS timestamps if available
- fallback timing strategy
- subtitle preview/edit

## Part 9 — FFmpeg Editing

Uygulandı: gerçek yerel FFmpeg render, mevcut Part 8 handoff, CPU/NVENC seçimi ve kontrollü fallback, görsel/video/altyazı/müzik, kalıcı işler ve video sürümleri. Sahibi Windows/Gyan FFmpeg 9.0.2 + RTX 5070/NVENC ile yaklaşık 193 saniyelik 1920×1080 çıktıyı, ses ve altyazıları canlı doğruladı. [Basit Windows kontrolü ve sınırlar](docs/RENDERING.md). **Part 10 başlamadı.**
- timeline model
- 1920x1080 normalization
- clips/images
- transitions
- Ken Burns
- narration
- music ducking
- subtitles
- render progress
- retry/logging

## Part 9.5 — Smart YouTube Editing

Uygulandı; önceki render Windows'ta doğrulandı. Son kalite düzeltmesi: Dengeli 50px kalın, Dinamik 52px kalın, Temel eski 48px normal altyazı; cue metni/zamanı korunur. Smart Edit v3 yumuşak nötr kamera sınırları, sabit geçiş tutamaçları, 30fps zaman tabanı ve geçişle çakışan punch bastırma kullanır. Dengeli yaklaşık 0,40sn / Dinamik 0,47sn seçilmiş geçişler; çoğu sınır temiz kesmedir. Yeni render sürümdür; eski v1/v2/stilsiz çıktılar ve kaynaklar korunur. SQLite 10 değişmedi. Gerçek hareketli FFmpeg kareleri ve uygulanan fallback sayaçları test edilir. [15 Windows adımı](docs/RENDERING.md#part-95-windows-kontrolü) ile sahibin kontrolü gerekir. **Part 10 başlamadı.**

### Part 6.5 — Smart Media Relevance (Part 10 öncesi kalite geçişi)

Güncel sahne + gerçek metadata ile taze alaka; eski puan/etiket ve query_used/kademe/çözünürlük kanıt değildir. Küçük konu/bağlam kapısı aviation/rail/animal/food/urban/marine/mountain/forest/beach/vehicle/technology uyumsuzluklarını engeller. Eski çok dilli sorgular yerel İngilizce 2–6 kavrama sadeleşir; özel isimler korunur. İsteğe bağlı provider_query gelecek Part 5 planında aynı mevcut çağrıdan gelir; ekstra ücretli çağrı yok. İlgili video → ilgili görsel → uyumlu genel video → uyumlu genel görsel; iki kabul edilebilir aday arasında en fazla 16 puan farkta video tercih edilir. Yaklaşık %75–90 video yumuşak hedef, kota değildir. Açık onaylı yeniden arama/arşivler/kilitler/eski dosyalar korunur. [Alaka kuralları](docs/STOCK_MEDIA.md#part-65--konuya-uygun-medya). Canlı stok/Windows kalite kontrolünü sahibi yapmalıdır.

## Part 9.6 — Adaptive Edit Engine + Media Relevance V3

- Yeni render varsayılanı **Uyarlanabilir YouTube**; içerik işaretlerinden yerel deterministik düzenler, tema ve yön seçimi.
- B-roll çoğunlukta; yalnız exact-source kısa cue/önceden onaylı vurgu metni, doğrulanmış sayı/tarih/konum. Aynı semantik sahnenin zaten indirilen ikinci medyası kullanılabilir.
- Varyasyon seed'i ve altyazı modu render metadata JSON'unda; **Yeni Kurgu Varyasyonu** yerel önizlemeyi değiştirir. Part 8 ana saat, eski sürümler ve Smart Edit v3 geçiş güvenliği korunur.
- Stil/format yerine gerçek özne; özgül sahnelerde İlgili/Çok ilgili kapısı; proje çapında kimlik/adres/byte-hash tekrar engeli. Benzersiz ilgili video önce; yoksa ilgili görsel veya boş yuva.
- [Windows kontrolü](docs/RENDERING.md#part-96-windows-kontrolü) ve [V3 medya](docs/STOCK_MEDIA.md#media-relevance-v3). Canlı Windows/sağlayıcı/NVENC doğrulaması sahibi tarafından yapılmalı. **Part 10 başlamadı.**

## Part 10 — Metadata + Thumbnail Planning
- German title suggestions
- description
- tags/keywords where useful
- thumbnail prompt/text idea
- no automatic image generation required in initial milestone

## Part 11 — Export + Optional YouTube
- manual export folder first
- optional YouTube OAuth/upload after core app is stable
- always require manual approval before publish

## Part 12 — Packaging + Beginner Experience
- one-click launcher
- dependency checks
- Windows installation helper
- robust diagnostics
- backup/restore project database
- full smoke test
- beginner README

## Part 9.7 — Short Clip Pipeline + OpenMontage Integration

- Yaklaşık 2,8–4,5 saniyelik, anlamlı anlatım sınırlarına yakın değişken görsel kesitler; mevcut uzun kilitsiz alanların açık onaylı yerel bölünmesi. Yeni LLM/TTS çağrısı yok.
- Otomatik yatay video/minimum 1280×720; alaka önce, ilgili kısa kaynak tercihi, uzun kaynakta deterministik yerel kesit. Kimlik/URL/SHA-256 tekrar koruması.
- Render hazırlık bayrakları, eksik/güncel olmayan/dosya sayaçları ve açık Türkçe engeller; eksik kaynakla tahmini plan/varyasyon geri bildirimi.
- Varsayılan Yerel Adaptif / FFmpeg / NVENC korunur; OpenMontage ayrı, isteğe bağlı, sabit sürümlü süreç/ortam. Arama, isteğe bağlı CLIP, kesme ve Remotion kompozisyon adaptörleri; açık seçimde hata gizlenmez.
- [Sözleşme, lisans ve doğrulama sınırları](docs/OPENMONTAGE_INTEGRATION.md). Uygulamanın lisansı değişmedi; upstream kaynak kopyalanmadı.
- Part 10 kapsam dışı; mevcut projeler, anahtarlar ve eski video sürümleri korunur.
