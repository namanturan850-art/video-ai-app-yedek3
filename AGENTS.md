# Repository instructions for Codex

## User profile
The owner of this repository is a complete beginner in software development.
Do not require the user to manually edit code, run complicated shell commands, understand package managers, or debug stack traces.

## Product principle
Build a Windows-friendly, local-first application named **AI Video Studio**.
The user should eventually launch it by double-clicking `START_AI_VIDEO_STUDIO.bat`.

## Development style
1. Work in small, testable milestones.
2. Do not implement the entire product in one uncontrolled pass.
3. After each milestone, run the relevant tests/lint/smoke checks.
4. Keep a simple changelog in `docs/STATUS.md`.
5. If a third-party API is not documented in the repository, do not invent endpoints, request fields, authentication methods, model IDs, or response schemas.
6. Add provider abstractions so unknown APIs can be wired later without rewriting the application.
7. Prefer mature, free/open-source dependencies.
8. Avoid unnecessary frameworks and infrastructure.
9. Keep the first version single-user and local-only.
10. Never put API keys in source files. `.env`, local secret files, and runtime-entered secrets must be ignored by Git.
11. Every error shown to the user should be plain Turkish, with an actionable explanation.
12. Every major background operation should show progress/status in the UI.

## Technical baseline
Prefer:
- Python 3.12+
- FastAPI backend
- SQLite database
- Plain HTML/CSS/JavaScript frontend served by FastAPI (no Node build step unless clearly necessary)
- FFmpeg for video/audio editing
- pytest for backend tests
- httpx for HTTP APIs
- pydantic/pydantic-settings for config
- pathlib for file paths

## Windows usability
The project should include:
- `START_AI_VIDEO_STUDIO.bat`
- `INSTALL_WINDOWS.bat` if needed
- automatic creation/use of `.venv`
- a preflight check for Python and FFmpeg
- a browser auto-open to the local UI
- clear error messages when a dependency is missing

## Architecture rules
Use modular provider interfaces:
- `ScriptProvider`
- `StockProvider`
- `TTSProvider`
- `RenderProvider`
- `YouTubeProvider`

Initial providers:
- Script: Ollama (free/local) + optional OpenAI provider stub/config
- Stock: Pexels + Pixabay
- TTS: AI33 provider adapter, but only implement real network calls after verified API docs exist
- Render: FFmpeg
- YouTube: manual-export first; API upload later

## Content originality
The system may analyze public reference material only for abstract attributes such as:
- genre
- target audience
- hook type
- pacing
- emotional arc
- topic
- structure

The system must create:
- new characters
- new wording
- new scenes
- new event sequence
- new conflicts
- new ending
- new visual plan

Do not build a feature whose purpose is to reproduce, download, translate, or lightly paraphrase a competitor's full copyrighted video/script.

## Definition of done for each milestone
- feature works locally,
- tests pass,
- no secrets are committed,
- beginner-facing instructions are updated,
- `docs/STATUS.md` says what works and what is still mocked,
- no undocumented API behavior is invented.
