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

Uygulandı ve render sahibi tarafından Windows'ta doğrulandı: Temel / Dengeli / Dinamik, yerel Smart Edit Plan, stok videolarda da hareket, sahne geçişleri, uzun klipte farklı kadrajlar, exact vurgu ve planlanan/uygulanan sayımlar. Kalite düzeltmesinde normal Part 9 altyazı stili üç profilde aynen geri geldi; vurgu ayrı ve geçişten bağımsız. Dengeli %4,5–5 / Dinamik %7–8 hareket; yaklaşık 0,43/0,53sn seçilmiş geçişler, yakın kadraj korunur. Eski v1/stilsiz renderlar ve kaynak zamanları/dosyaları korunur; yeni plan v2. SQLite 10 değişmedi. Gerçek FFmpeg piksel ve fallback testleri var. Yeni kalite görünümü [16 basit Windows adımıyla](docs/RENDERING.md#part-95-windows-kontrolü) kontrol edilmelidir. **Part 10 başlamadı.**

### Part 6.5 — Smart Media Relevance (Part 10 öncesi kalite geçişi)

Mevcut sahneden yerel konu çapası, dört sorgu kademesi, çok dilli ağırlıklı metadata alakası, Pixabay video etiket kapısı ve ilgili görsel fallback. Zayıf sonuç otomatik seçilmez. Yeni ücretli sağlayıcı/LLM çağrısı yok; gelecek sahne ipuçları aynı mevcut isteğe dahil. **Alakaya Göre Medyayı Yeniden Ara** açık onayla yeni seçim sürümü/arşiv oluşturur; eski dosyalar, kilitler, senaryo/TTS/altyazı korunur. [Alaka kuralları](docs/STOCK_MEDIA.md#part-65--konuya-uygun-medya). Canlı stok kalite kontrolünü sahibi Windows'ta yapmalıdır.

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
