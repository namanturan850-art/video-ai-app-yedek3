# First Codex Task

Read `AGENTS.md`, `PROJECT_SPEC.md`, and `ROADMAP.md`.

Implement **only Part 1 — Repository + Local App Skeleton**. Do not start later parts yet.

## Required result
Create a working Windows-friendly local application called **AI Video Studio** using:
- Python 3.12+
- FastAPI
- SQLite
- plain HTML/CSS/JavaScript served locally
- pytest

The owner is a complete beginner.

### Build
1. Create a clean Python project structure.
2. Add dependency files.
3. Create a FastAPI server.
4. Create a Turkish dashboard with cards:
   - Yeni Proje
   - Projeler
   - Ayarlar
   - Tanılama
5. For Part 1, those pages may be placeholders except Diagnostics.
6. Initialize SQLite automatically.
7. Add `/api/health`.
8. Add a Diagnostics page that safely displays:
   - app version
   - Python version
   - operating system
   - SQLite status
   - FFmpeg found / not found
   - data directory writable / not writable
9. Create `START_AI_VIDEO_STUDIO.bat` that:
   - finds Python,
   - creates `.venv` if missing,
   - installs dependencies if needed,
   - starts the server,
   - opens the browser automatically.
10. If Python is missing, show a beginner-readable Turkish message.
11. If FFmpeg is missing, the app must still start and Diagnostics should explain that rendering will not work until FFmpeg is installed.
12. Create `docs/STATUS.md`.
13. Create tests for health endpoint and database initialization.
14. Add/update `.gitignore` so `.env`, virtualenv, local database, project media, logs, and secrets are never committed.
15. Run tests before finishing.

## Do not
- Do not connect AI33 yet.
- Do not invent AI33 endpoints.
- Do not implement Pexels/Pixabay yet.
- Do not implement video rendering yet.
- Do not implement YouTube yet.
- Do not add Docker unless it is truly necessary.
- Do not require Node.js.

## Completion report
When finished, report:
- files created,
- tests run and result,
- exact beginner steps to run on Windows,
- anything that is still missing,
- whether the repository is ready for Part 2.
