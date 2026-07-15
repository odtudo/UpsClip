# Project Context — Twitch VOD Local Clip Editor

## Automatic VOD Analysis — visual OBS phase boundary

The UI has separate Manual and Automatic VOD Analysis modes. Manual jobs retain the established
SQLite `jobs` table and `JobProcessor` render pipeline. Automatic analysis uses a separate
`vod_analysis_jobs` table and modules under `services/vod_analysis`, while sharing the existing
single-worker executor so heavy work remains serialized.

Phase 2 adds real yt-dlp metadata and signed stream access, centered audio samples, mono 16 kHz PCM,
Silero VAD, audio statistics, conditional faster-whisper `tiny` probes, reduced visual samples, and
sparse YuNet/layout signals. The three-hour IlloJuan horizon is inspected as independent windows;
the application never creates a three-hour analysis WAV or video. Signed URLs are refreshed per
logical block and once on sample failure. Temporary samples are removed per window.

`coarse_timeline.json` is written atomically after each block under a configuration-keyed cache and
copied into the job directory. Completed windows survive an interrupted job and are reused by a new
job with the same key. SQLite exposes persistent completed/total-window progress and the current
source timestamp without exposing media URLs or paths.

Phase classification no longer infers streamer activity from Phase 2 signals. A separately
fingerprinted visual pass samples the OBS layout every two seconds and reuses Smart Vertical's exact
YuNet detector and scene classifier. `no_face`, `fullscreen_face`, `small_facecam`, and ambiguous
layouts map deterministically to waiting, talking, gameplay, and unknown. Audio, VAD, Whisper probes,
chapters, embeddings, and textual heuristics have no influence on that mapping.

Three consecutive samples are required by default to confirm a transition. Visual samples and
merged segments are persisted incrementally as `layout_timeline.json`; the backward-compatible
`phase_timeline.json` is derived from it and continues to expose talking blocks, the primary block,
and bounded Phase 4 selections to the API and UI. A changed visual fingerprint repeats only frame
sampling; the existing Phase 2 cache is retained.

The SQLite job records the strategy and whether coarse input is required. New visual jobs set
`visual_layout`/`false`, use an independent visual cache key, and never enter Phase 2 audio stages.
The Inspector returns normal queued, processing, completed and failed responses even before an
artifact exists. Coarse artifacts are optional legacy/future-semantic inputs, not visual prerequisites.

Phase 3 intentionally produces no deep transcript, topics, semantic embeddings, editorial scores,
titles, or real candidates. Those remain Phase 4+ responsibilities. Phase 1 fixtures and Twitch
candidate rendering remain available unchanged.

## VOD Inspector engineering layer

VOD Inspector is a validation UI/API over existing analysis jobs and artifacts. It does not alter
the visual classifier. It exposes the detected timeline, confidence, reason codes and warnings;
generates exact Twitch/YouTube timestamp links; accepts temporary manual ground-truth boundaries;
and computes signed/absolute transition errors, omissions, false detections and weighted confidence.

Inspector artifacts live only under `data/analysis/<job-id>`. Export uses a fixed filename allowlist
and contains sanitized metadata, coarse/layout/phase timelines, PNG visualization and Markdown reports.
When `VALIDATION_DEBUG=true`, raw scores, smoothed windows and transition graph are added. Cookies,
OAuth material, stream URLs, tokens and unrelated job files cannot enter the ZIP.

## Smart Vertical Layout

Vertical output includes a local Smart Vertical Layout stage after silence editing and before
faster-whisper. It detects stable visual scenes, samples faces, classifies `fullscreen_face`,
`small_facecam`, `no_face`, or `uncertain`, creates a versioned composition plan, and renders either a
single face-aware crop or a face-top/content-bottom layout at 1080×1920. It uses CPU OpenCV geometry
only—no identity recognition, cloud vision, dynamic zoom, pan, or frame-by-frame camera motion.
Conservative fallbacks preserve completion and surface warnings.

Horizontal output bypasses this subsystem. Vertical Smart can be disabled for simple crop; automatic
vertical subtitles remain enabled. Optional structured profiles live under `data/profiles` and can be
selected manually or matched from normalized Twitch uploader metadata.

## 1. Project goal

Build a personal-use web application that runs locally and allows the user to:

1. Paste the URL of a Twitch VOD.
2. Enter a start timestamp and an end timestamp.
3. Download only the relevant section of the VOD, or download a slightly larger section and trim it precisely.
4. Produce an edited video from that section.
5. Apply simple automatic editing:
   - remove or shorten long silences;
   - normalize audio;
   - generate large burned-in subtitles automatically for vertical clips.
6. Preview the rendered video locally.
7. Upload the final result to the user's own YouTube channel.
8. Keep a local history of processing jobs.

This project is exclusively for personal use. It does not need production-grade scaling, multi-user support, cloud deployment, complex permissions, distributed queues, Kubernetes, microservices, or enterprise architecture.

The priority is:

1. Reliability.
2. Simplicity.
3. Understandable code.
4. Easy local execution.
5. Easy future modification.

---

## 2. Expected user flow

The main page should contain:

- Twitch VOD URL.
- Start timestamp.
- End timestamp.
- Output format:
  - Horizontal 16:9.
  - Vertical 9:16, optional for later.
- Editing options:
  - Remove or shorten long silences.
  - Normalize audio.
  - Generate subtitles automatically for vertical output and optionally for horizontal output.
- YouTube metadata:
  - Title.
  - Description.
  - Tags.
  - Privacy: private, unlisted, or public.
- Button to process the video.

After submission, the UI should show a job with progress states such as:

1. Queued.
2. Reading VOD metadata.
3. Downloading.
4. Trimming.
5. Analyzing audio.
6. Generating edit plan.
7. Rendering.
8. Ready for preview.
9. Uploading to YouTube.
10. Completed.
11. Failed.

The user must be able to preview the output before uploading it.

YouTube upload should default to `private`.

---

## 3. Recommended architecture

Use a small monorepo or a simple repository with two applications.

### Frontend

Use:

- Next.js.
- TypeScript.
- Tailwind CSS.
- Native HTML5 video player.
- Simple polling for job progress.

Do not add Redux, complex state management, a design system, authentication, or unnecessary abstraction.

### Backend

Use:

- Python.
- FastAPI.
- yt-dlp.
- FFmpeg and ffprobe.
- SQLite.
- SQLAlchemy or SQLModel.
- Pydantic settings.
- Optional faster-whisper for subtitles and speech timestamps.

The backend can execute jobs using:

- FastAPI BackgroundTasks for the first MVP, or
- a simple in-process worker thread.

Do not add Celery, Redis, RabbitMQ, Kafka, or external job infrastructure.

### Local storage

Use local directories:

```text
data/
├── downloads/
├── work/
├── rendered/
├── subtitles/
├── thumbnails/
├── credentials/
└── logs/
```

Use SQLite for job metadata:

```text
data/app.db
```

---

## 4. Suggested repository structure

```text
twitch-vod-editor/
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── package.json
│   └── api/
│       ├── app/
│       │   ├── main.py
│       │   ├── config.py
│       │   ├── database.py
│       │   ├── models.py
│       │   ├── schemas.py
│       │   ├── routes/
│       │   ├── services/
│       │   │   ├── downloader.py
│       │   │   ├── ffmpeg.py
│       │   │   ├── silence.py
│       │   │   ├── edit_plan.py
│       │   │   ├── renderer.py
│       │   │   ├── subtitles.py
│       │   │   └── youtube.py
│       │   └── workers/
│       │       └── jobs.py
│       ├── tests/
│       ├── requirements.txt
│       └── .env.example
├── data/
│   └── .gitkeep
├── scripts/
│   ├── check_dependencies.py
│   └── dev.sh
├── docker-compose.yml
├── README.md
├── CONTEXT.md
└── .gitignore
```

The exact structure can be simplified if Codex finds a clearer alternative, but frontend and backend responsibilities should remain separated.

---

## 5. Core backend entities

Create a `Job` model with fields similar to:

- `id`
- `source_url`
- `start_seconds`
- `end_seconds`
- `status`
- `progress`
- `current_step`
- `error_message`
- `download_path`
- `source_clip_path`
- `rendered_path`
- `subtitle_path`
- `youtube_video_id`
- `youtube_url`
- `created_at`
- `updated_at`

Possible job statuses:

```text
queued
downloading
trimming
analyzing
rendering
ready
uploading
completed
failed
cancelled
```

---

## 6. API endpoints

Implement a minimal API.

### Health

```http
GET /health
```

### Create job

```http
POST /jobs
```

Example request:

```json
{
  "source_url": "https://www.twitch.tv/videos/123456789",
  "start": "00:10:00",
  "end": "00:22:35",
  "remove_silences": true,
  "normalize_audio": true,
  "generate_subtitles": false,
  "output_format": "horizontal"
}
```

### Job status

```http
GET /jobs/{job_id}
```

### List jobs

```http
GET /jobs
```

### Preview or serve rendered video

```http
GET /jobs/{job_id}/video
```

### Upload to YouTube

```http
POST /jobs/{job_id}/youtube
```

Example request:

```json
{
  "title": "Video title",
  "description": "Video description",
  "tags": ["twitch", "gaming"],
  "privacy_status": "private"
}
```

### Delete local job files

```http
DELETE /jobs/{job_id}
```

---

## 7. Timestamp handling

Accept:

- `MM:SS`
- `HH:MM:SS`

Convert timestamps to integer seconds in the backend.

Validate:

- URL is present.
- Start is valid.
- End is valid.
- End is greater than start.
- Duration is below a configurable maximum.
- Initial default maximum duration: 30 minutes.

Keep the maximum configurable through `.env`.

---

## 8. Twitch VOD download strategy

Use yt-dlp.

The preferred flow is:

1. Validate that the URL can be inspected by yt-dlp.
2. Request a section slightly larger than the requested range.
3. Add a configurable margin, for example 5 seconds before and after.
4. Download that section.
5. Use FFmpeg to trim it precisely.

Example conceptual command:

```bash
yt-dlp   --download-sections "*00:09:55-00:22:40"   --force-keyframes-at-cuts   -o "data/downloads/%(id)s.%(ext)s"   "<VOD_URL>"
```

Then trim accurately with FFmpeg.

The code must use subprocess argument lists rather than unsafe shell string concatenation.

Capture stdout, stderr, exit code, and useful error messages.

Do not implement support for bypassing access controls, DRM, subscriber-only content without authorization, deleted content, or private VODs the user cannot legally access.

---

## 9. Editing strategy

The MVP should not attempt to understand storytelling or edit like a human professional.

Use simple, deterministic rules.

### 9.1 Silence handling

Analyze audio using FFmpeg `silencedetect`.

Initial configurable rules:

- Ignore silences shorter than 1.2 seconds.
- For silences between 1.2 and 2.5 seconds, shorten them rather than removing all of them.
- For silences longer than 2.5 seconds, remove most of the silence while preserving a small padding around speech.
- Preserve approximately 0.15 to 0.30 seconds around cuts to avoid unnatural transitions.

Generate an edit decision list containing intervals to keep.

Do not overwrite source files.

Store editing decisions in an edit-plan JSON file, for example:

```json
{
  "source_duration": 755.0,
  "segments": [
    {
      "source_start": 0.0,
      "source_end": 32.4,
      "output_start": 0.0
    }
  ]
}
```

This makes debugging and future manual editing easier.

### 9.2 Audio normalization

Use a safe FFmpeg loudness normalization workflow.

Prefer EBU R128 `loudnorm`.

Avoid clipping.

### 9.3 Subtitles

- Use faster-whisper locally without paid APIs.
- Generate persistent `.ass` subtitle files.
- Burn large, outlined, bottom-safe captions into every vertical video.
- Enable subtitles automatically for vertical output without a separate checkbox.
- Keep subtitles optional and disabled by default for horizontal output.

---

## 10. Rendering

Use FFmpeg.

Recommended default output:

- Container: MP4.
- Video codec: H.264 using `libx264`.
- Audio codec: AAC.
- Pixel format: `yuv420p`.
- Frame rate: preserve source when possible.
- Fast start: `-movflags +faststart`.
- Default quality: CRF around 20–23.
- Encoding preset: `medium` or `fast`, configurable.

The renderer should:

1. Combine kept segments.
2. Normalize audio.
3. Transcribe the assembled video when subtitles are enabled.
4. Burn styled subtitles into vertical output and optionally into horizontal output.
5. Save the final video to `data/rendered`.

Do not destructively modify the downloaded source.

---

## 11. YouTube upload

Use the official YouTube Data API with OAuth 2.0.

Requirements:

- Local OAuth login.
- Store credentials only under `data/credentials`.
- Add credential files and token files to `.gitignore`.
- Use resumable upload.
- Default privacy to `private`.
- Do not automatically upload immediately after rendering.
- Require the user to preview and press an upload button.
- Return the YouTube video ID and URL when available.

The README must explain how to:

1. Create a Google Cloud project.
2. Enable YouTube Data API v3.
3. Create Desktop App OAuth credentials.
4. Download the client secrets JSON.
5. Put it in the expected local credentials directory.
6. Complete the first local authorization.

Never commit OAuth secrets or tokens.

---

## 12. Frontend requirements

Keep the UI simple.

### Main page

Include:

- VOD URL input.
- Start timestamp.
- End timestamp.
- Editing checkboxes.
- Output format selector.
- Submit button.
- Validation messages.

### Jobs area

Show:

- Status.
- Progress percentage.
- Current step.
- Error message when present.
- Source URL.
- Requested interval.
- Created time.
- Preview button.
- Upload to YouTube button.
- Delete button.

Poll active jobs every 2 seconds.

### Preview page or panel

Show:

- HTML5 video player.
- Final duration.
- File size.
- Button to upload.
- YouTube metadata form.
- Upload status.

Do not spend excessive time on visual polish. A clean, usable interface is enough.

---

## 13. Docker and local execution

Provide Docker Compose for convenience, but also document native execution.

The system may depend on:

- Node.js.
- Python.
- FFmpeg.
- yt-dlp.

Docker Compose should start:

- Web frontend.
- FastAPI backend.

Mount the local `data/` directory into the API container.

Do not add Nginx unless strictly necessary.

For Linux host compatibility, make sure generated files are writable by the host user when practical.

---

## 14. Configuration

Create `.env.example`.

Suggested variables:

```dotenv
API_HOST=0.0.0.0
API_PORT=8000
WEB_PORT=3000
DATA_DIR=./data
DATABASE_URL=sqlite:///./data/app.db
CORS_ORIGINS=http://localhost:3000
MAX_CLIP_DURATION_SECONDS=1800
DOWNLOAD_MARGIN_SECONDS=5
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe
YTDLP_PATH=yt-dlp
VIDEO_CRF=22
VIDEO_PRESET=fast
SILENCE_MIN_SECONDS=1.2
SILENCE_REMOVE_AFTER_SECONDS=2.5
SILENCE_PADDING_SECONDS=0.2
WHISPER_MODEL=small
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto
WHISPER_LANGUAGE=auto
YOUTUBE_CLIENT_SECRETS_PATH=./data/credentials/client_secret.json
YOUTUBE_TOKEN_PATH=./data/credentials/token.json
```

---

## 15. Error handling

Provide readable errors for:

- Unsupported or invalid URL.
- VOD unavailable.
- yt-dlp failure.
- FFmpeg missing.
- FFmpeg rendering failure.
- Invalid timestamps.
- End timestamp beyond source duration.
- Insufficient disk space when detectable.
- YouTube OAuth not configured.
- YouTube upload failure.

Store technical logs locally, but show concise errors in the UI.

A failed job should remain visible so the user can inspect what happened.

---

## 16. Security constraints

Although the application is local:

- Never pass user input directly into a shell.
- Validate paths.
- Prevent path traversal.
- Restrict served video paths to the data directory.
- Never expose credentials through API responses.
- Keep secrets out of Git.
- Validate YouTube privacy values.
- Do not create arbitrary file-read endpoints.

No login system is required because the application is intended for localhost use only.

Bind services to localhost by default when running natively.

---

## 17. Testing

Add lightweight but meaningful tests.

At minimum:

- Timestamp parsing.
- Start/end validation.
- Edit-plan generation from silence intervals.
- Safe path handling.
- Job API creation and status retrieval.
- Mocked subprocess failure handling.

Do not attempt exhaustive test coverage.

Include a sample development mode that can create a fake job without downloading a real VOD, so the UI can be tested quickly.

---

## 18. Development phases

Codex should build the project in this order:

### Phase 1 — Repository and basic UI

- Create frontend and backend.
- Health endpoint.
- SQLite job model.
- Job creation form.
- Job progress polling.
- Docker Compose.
- README.

### Phase 2 — Download and precise trimming

- yt-dlp inspection.
- Section download with margins.
- FFmpeg precise trim.
- Rendered video serving.
- Preview in frontend.

### Phase 3 — Simple editing

- Silence analysis.
- Edit-plan JSON.
- Cut and concatenate.
- Audio normalization.

### Phase 4 — YouTube

- OAuth setup.
- Metadata form.
- Resumable private upload.
- Save resulting video ID and URL.

### Phase 5 — Optional improvements

Only after the main workflow works:

- Manual timeline editing.
- Streamer profiles and facecam regions.
- Thumbnail generation.

---

## 19. Definition of done

The MVP is complete when the user can:

1. Start the project locally.
2. Open the web interface.
3. Paste a public or authorized Twitch VOD URL.
4. Enter start and end timestamps.
5. Start a processing job.
6. See progress and errors.
7. Obtain a precisely trimmed MP4.
8. Optionally remove or shorten long silences.
9. Automatically burn readable subtitles into vertical output.
10. Preview the final MP4.
11. Enter YouTube metadata.
12. Upload it privately to the user's own channel.
13. See the resulting YouTube link.
14. Restart the application without losing job history.

---

## 20. Non-goals

Do not implement these in the initial project:

- Multi-user accounts.
- Cloud deployment.
- Subscription billing.
- Team collaboration.
- Distributed processing.
- Kubernetes.
- Redis or Celery.
- Automatic public publishing without review.
- AI-based narrative understanding.
- Automatic copyright circumvention.
- Support for every video platform.
- Mobile application.
- Advanced professional timeline editor.
- Perfect facial or emotion recognition.
- Production-grade scalability.

The objective is a useful, understandable, local personal tool, not a startup platform.

---

## 21. Current OBS profile phase authority

The current automatic phase strategy is `profile_layout_match`. It samples frames every two seconds,
reuses Smart Vertical's YuNet detector, and compares each valid frame against the streamer-specific
profile at `data/profiles/illojuan_visual.json`. Classification is based on known scene structure and
stable reference regions; face geometry is secondary. Unmatched valid content, including photos or
videos containing large faces, is WAITING. UNKNOWN is reserved for technical failure, insufficient
quality, ambiguity, and transitions. Hysteresis operates on layout IDs, then derives phases.
Close scores across different phases remain UNKNOWN; close scores between two known gameplay variants
keep GAMEPLAY and record `same_phase_layout_tie_resolved`.

Enabled evidence-backed layouts are `full_camera_room`, `gameplay_left`, and
`gameplay_small_left`. Right and large variants are supported but deliberately absent until real
screenshots supply measured coordinates and references. Cache identity includes the profile JSON and
hashes of enabled images.
Legacy phase/layout artifacts remain readable, and coarse audio/VAD/Whisper data is retained for the
future deep analysis of TALKING blocks; it is not phase input.
