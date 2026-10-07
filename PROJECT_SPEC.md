# AI Video Studio — Product Specification

## 1. Target user
A YouTube creator who understands YouTube content but has no software-development knowledge.

## 2. Main workflow
1. Open the app locally.
2. Enter:
   - a topic, and optionally a reference URL,
   - target language (initially German),
   - desired video duration,
   - content style,
   - voice selection,
   - scene-change frequency.
3. The system analyzes only high-level reference concepts.
4. It creates a fully new German script.
5. It splits the script into timed scenes.
6. It generates English stock-search queries for each scene.
7. It searches Pexels first, Pixabay second.
8. It avoids recently reused stock assets when possible.
9. It creates narration using AI33.pro.
10. It creates subtitle timing from provider timing data if available; otherwise use a safe fallback pipeline later.
11. FFmpeg assembles video, images, narration, subtitles, transitions, and background music.
12. The app outputs a 1920x1080 MP4 and project metadata.
13. User previews and approves manually.
14. YouTube upload is an optional later phase.

## 3. Main screens

### Dashboard
- New Project
- Existing Projects
- Settings
- Logs/Diagnostics

### New Project
Fields:
- Project name
- Topic
- Optional reference URL
- Language: German initially
- Target duration
- Script engine
- TTS engine
- Voice
- Stock sources
- Scene duration min/max
- Subtitles on/off
- Background music on/off
- Thumbnail idea on/off

Button:
- Create Project

### Project page
Pipeline stages:
- Concept
- Script
- Scene Plan
- Stock Search
- Voice
- Subtitles
- Render
- Metadata
- Export

Each stage:
- status
- progress
- retry button
- readable error if failed

### Settings
Sections:
- General
- Ollama
- OpenAI optional
- Pexels
- Pixabay
- AI33
- FFmpeg
- YouTube later

Secrets should be stored only locally and ignored by Git.

## 4. Data model

### Project
- id
- name
- topic
- reference_url
- language
- target_duration_minutes
- status
- created_at
- updated_at

### Script
- project_id
- version
- text
- provider
- estimated_duration
- created_at

### Scene
- project_id
- order
- narration_text
- expected_duration
- visual_type
- search_queries
- transition
- motion
- mood

### MediaAsset
- project_id
- scene_id
- source
- external_id
- source_url
- local_path
- width
- height
- duration
- used_at

### VoiceTrack
- project_id
- provider
- voice_id
- local_path
- duration
- timing_json_path optional

### Render
- project_id
- output_path
- width
- height
- duration
- status
- log_path

## 5. Storage layout

data/
  app.db
  projects/
    <project-id>/
      script/
      scenes/
      stock/
      voice/
      subtitles/
      music/
      render/
      logs/

## 6. Free-first components

### FFmpeg
Use for:
- normalization
- trimming
- scale/crop to 1920x1080
- image motion / Ken Burns
- concatenation
- crossfades where practical
- narration mixing
- background music ducking
- subtitle burn-in or selectable subtitle file
- final H.264/AAC MP4

### Pexels
Official API only.
Do not scrape.
Download only selected media.
Cache external IDs to reduce repeats.

### Pixabay
Official API only.
Use as fallback after Pexels.

### Ollama
Default free/local script-provider option.
The user may select an installed local model.
Do not hardcode a model name that may not exist.

### AI33.pro
Primary intended TTS service.
IMPORTANT: API endpoint, auth scheme, request payload, model/voice IDs and response schema are NOT defined in this repository.
Implement:
- provider interface,
- settings fields,
- mock/test mode,
- a clearly isolated adapter module,
- documentation explaining which verified API information is still required.
Do not fabricate the integration.

## 7. Paid/optional components
The product must work as far as possible without monthly subscriptions.
Optional:
- OpenAI API for higher-quality writing
- future YouTube API integration
- future other TTS providers

## 8. Safety and originality guardrail
Reference inputs are for concept analysis, not reproduction.
If a user pastes a transcript, the pipeline should summarize abstract story mechanics first and generate a new outline before writing the new script.

## 9. UX
All user-facing UI text should initially be Turkish.
Generated story content can be German.
The interface should be clean and simple, with large buttons and minimal jargon.

## 10. Logging
Never expose raw secrets in logs.
Keep local logs per project.
Include a Diagnostics page that reports:
- Python version
- FFmpeg found/not found
- database status
- configured providers
- writable data directory
without printing API keys.
