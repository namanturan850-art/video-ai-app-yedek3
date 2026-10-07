# AI33.pro Integration Notes

AI33.pro is the intended primary TTS provider.

## Current rule
Do not guess or reverse-engineer undocumented API behavior.

Before real integration, obtain verified documentation for:
- base API URL
- API version
- authentication header / token format
- endpoint for text-to-speech
- endpoint for listing providers/models/voices, if available
- request fields
- maximum text length
- async job/polling behavior, if any
- output/download response
- rate limits
- error schema
- timestamp/alignment support, if any

## Adapter contract to prepare
The codebase should eventually expose a common TTS interface such as:
- list_voices()
- synthesize(text, voice, options)
- get_job_status(job_id) if needed
- download_audio(...)
- get_timing(...) if supported

Until the verified API docs are supplied, use mock mode and keep the UI fields disabled or marked "API belgeleri gerekli".
