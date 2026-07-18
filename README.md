# Twitch VOD Local Clip Editor

A deliberately small localhost application for turning one authorized Twitch VOD interval into a previewable MP4 and, only after review, uploading it to your YouTube channel. It uses Next.js, FastAPI, SQLite, yt-dlp, FFmpeg, and the official YouTube Data API.

## Transcript-first Automatic VOD Analysis

Candidate generation uses the grounded pipeline `vod-topic-analysis-v1.1-grounded`. Spanish stream
fillers and accent-normalized variants are removed before TF-IDF/n-gram keyword extraction. Titles,
topic labels, summaries and proper nouns must be evidenced by the candidate's exact transcript span;
the parent topic transcript is never used to title a split candidate. Failed gates are written to
`rejected_candidates.json`, while accepted score details are written to `score_breakdowns.json`.
The UI shows opening sentences, distributed representative excerpts, closing sentences, grounding,
keyword quality, semantic coherence and penalties.

Candidate generation uses the grounded pipeline `vod-topic-analysis-v1.1-grounded`. Spanish stream
fillers and accent-normalized variants are removed before TF-IDF/n-gram keyword extraction. Titles,
topic labels, summaries and proper nouns must be evidenced by the candidate's exact transcript span;
the parent topic transcript is never used to title a split candidate. Failed gates are written to
`rejected_candidates.json`, while accepted score details are written to `score_breakdowns.json`.
The UI shows opening sentences, distributed representative excerpts, closing sentences, grounding,
keyword quality, semantic coherence and penalties.

Choose **Automatic VOD Analysis**, paste an authorized Twitch or YouTube VOD, keep IlloJuan selected,
and press **Analyze VOD**. It extracts audio only, analyzes up to two hours by default, transcribes
Spanish in resumable chunks, groups coherent topics, and returns editable clip cards. **Generate
Clip** reuses the established manual render, silence, Smart Vertical, subtitle, preview, and YouTube
pipeline.

```dotenv
VOD_TOPIC_ANALYSIS_MAX_SECONDS=7200
WHISPER_ANALYSIS_MODEL=medium
TRANSCRIPTION_CHUNK_SECONDS=1800
TRANSCRIPTION_OVERLAP_SECONDS=15
SEMANTIC_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

Models are cached under `data/models`. FastEmbed runs multilingual MiniLM locally through ONNX; no
paid API is required. The deterministic lexical fallback is recorded when the model is unavailable.
Stage caches live under `data/analysis/topic_cache` and job artifacts include `metadata.json`, audio,
raw/clean transcripts, semantic windows, topic blocks, and candidates.

```bash
# Fixture smoke: no network or models
PYTHONPATH=. python3 scripts/smoke_topic_analysis.py

# Revalidate a real completed transcript without downloading or running Whisper
PYTHONPATH=. python3 scripts/smoke_topic_analysis.py \
  --job-dir data/analysis/JOB_ID --output data/smoke_tests/topic-grounding

# Revalidate a real completed transcript without downloading or running Whisper
PYTHONPATH=. python3 scripts/smoke_topic_analysis.py \
  --job-dir data/analysis/JOB_ID --output data/smoke_tests/topic-grounding

# Existing local media: real Whisper
WHISPER_ANALYSIS_MODEL=small PYTHONPATH=. python3 scripts/smoke_topic_analysis.py \
  --audio data/work/JOB_ID/source_clip.mp4 --max-seconds 300 \
  --output data/smoke_tests/topic_audio
```

VOD Inspector and visual/coarse timelines remain engineering tools, not automatic-analysis
prerequisites. Whisper names, mixed topics, reactions, music, and editorial boundaries remain
imperfect; edit the suggested title and timestamps before rendering when needed.

## What it does

- Accepts Twitch VOD URLs and `MM:SS` or `HH:MM:SS` intervals (30-minute default maximum).
- Inspects the VOD, downloads the requested section with margins, and performs an exact re-encoded trim.
- Detects silences and writes a readable `edit_plan.json`; medium pauses are shortened and most long pauses are removed with speech padding.
- Applies EBU R128 loudness normalization and deterministic silence shortening without automatic zooms.
- Automatically transcribes vertical clips locally with faster-whisper and burns large, outlined, bottom-safe captions into the MP4.
- Renders H.264/AAC MP4 with `yuv420p` and fast-start, then serves it to the local HTML5 player.
- Stores job history and progress in `data/app.db` across restarts.
- Uploads with OAuth 2.0/resumable upload only after a separate preview/upload action; privacy defaults to `private`.
- Includes a demo mode that creates a real test video locally with FFmpeg and never contacts Twitch.

Vertical output is 1080×1920, uses Smart Vertical Layout by default, and always includes burned-in subtitles. Smart can be disabled to use the simple center crop. Horizontal subtitles remain optional and disabled by default. The default `small` Whisper model is downloaded once into persistent `data/models/` on first use.

## Smart Vertical Layout

After silence editing fixes the final timeline, the API samples scene changes and faces locally,
creates `data/work/{job_id}/composition_plan.json`, and renders each stable segment:

- `fullscreen_face`: one stable face-aware crop; no split and no zoom.
- `small_facecam`: stable corner, overlay, or lateral-column webcam above a geometrically selected content crop.
- `no_face` / `uncertain`: safe center crop with a persisted, visible warning.

The CPU-only OpenCV detector does not identify people, store embeddings, call a vision API, or track
faces frame by frame. Horizontal jobs and vertical jobs with Smart disabled never initialize it.
Transcription occurs only after silence editing and composition, so captions match the final timeline.
The UI shows scene counts, resolved profile, fallbacks and warnings. Complete Smart failure falls back
to simple vertical crop and retains a technical warning.

### Streamer profiles

Profiles are optional JSON files in `data/profiles/`. Auto can match a profile id to normalized Twitch
uploader metadata. Explicit ids are validated and cannot contain paths. Measure a screenshot rather
than guessing coordinates:

```bash
./scripts/create_streamer_profile.py \
  --id illojuan --display-name IlloJuan \
  --source-width 1920 --source-height 1080 \
  --facecam-x 20 --facecam-y 20 --facecam-width 430 --facecam-height 315 \
  --position top_left
./scripts/validate_streamer_profile.py data/profiles/illojuan.json
```

The coordinates above only demonstrate the command. Replace them with measurements from the actual
overlay. Regions scale proportionally at other resolutions. A profile may optionally define
`vertical.content_region_of_interest` as `{x,y,width,height}` to bias the lower crop.

### Tuning, performance, and limitations

All consumed settings are documented in `.env.example`: scene thresholds/sample rates, face
thresholds/stability, box expansion, segment merging, output dimensions, split ratio and divider.
Smart analysis samples reduced frames (never the full video in memory) and adds CPU/render time plus
temporary segment storage. Start with 30–60 seconds and disable Smart for faster simple cropping.

OpenCV YuNet is the primary CPU detector. Its small ONNX model is downloaded once during the Docker
build (or by `./scripts/download_face_model.sh` for native use), verified by SHA-256, and never
downloaded per job. Haar remains an optional last-resort fallback only when YuNet returns no boxes.
Analysis preserves up to 1280 px width and remaps boxes to source coordinates. Lateral columns are
supported without requiring the face to sit in a top/bottom corner. Tiny/occluded cameras,
transparent/circular overlays, moving webcams and crowded calls remain difficult; fallback always
produces a warning rather than inventing a webcam. With `SMART_LAYOUT_DEBUG=true`, analyzed raw frames,
all YuNet scores/boxes, accepted/discarded reasons, final facecam regions and content crops are saved
under `data/work/{job_id}/smart_vertical_debug/`.

The bundled model is OpenCV Zoo's `face_detection_yunet_2023mar.onnx`; provenance, license, checksum,
and installation details are recorded in `docs/YUNET_MODEL.md`.

### Smart verification

```bash
./scripts/smoke_smart_vertical.sh
./scripts/smoke_horizontal.sh
docker compose logs -f api
```

Artifacts are written to `data/smoke_tests/smart_vertical/latest/`: final MP4, plan, ASS, and
`fullscreen.png`, `facecam_split.png`, `no_face.png`, `subtitles.png`, `transition.png`. Inspect a real
job plan with:

```bash
python -m json.tool data/work/JOB_ID/composition_plan.json
```

## Quick start

Requirements: Docker Engine with the Compose plugin.

```bash
./start.sh
```

The script creates `.env` from `.env.example` when needed, prepares the persistent `data/`
directories, starts the API and web containers in the background, and waits for both services.
Existing images are reused. To rebuild the images explicitly:

```bash
./start.sh --build
```

Use `./start.sh --help` for logs, status, restart, stop, and clean options. The clean option removes
only this project's containers and networks; persistent files in `data/` are preserved.

If your host account does not use UID/GID 1000, set `LOCAL_UID=$(id -u)` and `LOCAL_GID=$(id -g)` in `.env` first. The API container runs with those IDs so generated media remains writable by the host account.

Open <http://localhost:3000>. The API is at <http://localhost:8000>; check it with:

```bash
curl http://localhost:8000/health
```

The backend image includes FFmpeg, ffprobe, and yt-dlp. `./data` is bind-mounted to `/data`, so the database, media, edit plans, logs, and OAuth files remain on the host. Stop with `docker compose down`; do not add `-v` if you want to keep local data.

## Automatic VOD Analysis — coarse signals and visual OBS phases

The creation screen has separate **Manual** and **Automatic VOD Analysis** modes. Manual rendering
is unchanged. Real automatic analysis obtains yt-dlp metadata and preserves the Phase 2 audio/VAD/
probe signal timeline for later topic analysis. Stream phases are now decided exclusively from the
OBS layout sampled from video. It deliberately does not transcribe full blocks, segment topics, or
propose real candidates yet.

The default three-hour horizon is divided into 30-second logical windows. FFmpeg reads only the
central 10 seconds of audio as mono 16 kHz PCM and two 320-pixel frames per window. It reads directly
from signed media URLs selected from yt-dlp metadata; it does not save a three-hour WAV or video.
URLs are reused for a 15-minute logical block, refreshed before the next block, and refreshed once
immediately after a failed sample to handle expiry. Temporary WAV/JPEG samples are removed after
each window.

Silero VAD, audio statistics and conditional faster-whisper probes still run in Phase 2, but none of
them participates in phase classification. The visual detector reuses the exact YuNet detector and
`classify_scene` implementation from Smart Vertical Layout. It samples a reduced frame every two
seconds by default and records timestamp, face box, area ratio, position, confidence and one of
`no_face`, `fullscreen_face`, `small_facecam`, or `unknown`. The deterministic mapping is
`no_face` → waiting, `fullscreen_face` → talking, `small_facecam` → gameplay, and ambiguous frames
→ unknown. No Whisper, VAD, audio heuristic, transcript, embedding, LLM, or chapter text is used.

Temporal hysteresis requires three consecutive samples by default before accepting a layout change;
the accepted transition is backfilled to the first confirming sample. A single missed or ambiguous
frame therefore cannot flip the phase. Adjacent accepted samples are merged into visual segments
with median confidence. The interval and confirmation count are configured with
`LAYOUT_SAMPLE_SECONDS` and `LAYOUT_TRANSITION_CONFIRMATION`.

Every talking segment remains visible. Segments at least 600 seconds long become relevant talking
blocks; the first qualifying block is normally `primary_talking_block_id`. All qualifying blocks can
be selected for future deep transcription, limited to six blocks and four total hours for safety.
Short sustained blocks remain in the timeline with low priority. A missing primary block is a warning,
not a fatal error. Gameplay→talking→gameplay and later conversation returns are supported.

At the observed Twitch bitrates used by the real smoke, the default sampling represents about
70–150 MB of requested media per analyzed hour, rather than downloading roughly one hour of full
source media. This is an estimate based on selected stream bitrates because FFmpeg does not expose
HTTP transfer bytes reliably; HLS segment/GOP boundaries may raise actual traffic.

Incremental coarse cache files live at `data/analysis/cache/<cache-key>/coarse_timeline.json`; each
job also gets `metadata.json` and `coarse_timeline.json`. A separate visual fingerprint covers VOD,
profile, visual pipeline version, sample interval, confirmation count, detector version, YuNet score
threshold and the shared Smart Vertical layout thresholds. Completed frame samples are persisted per
fetch block in `layout_timeline.json` and resume at the next missing sample. `phase_timeline.json` is
derived from that artifact. Changing visual settings never repeats Phase 2 audio, VAD, or probes. No
media URL, cookie, token, or internal path is returned by the API.

Visual jobs are explicitly recorded with `phase_detection_strategy=visual_layout` and
`requires_coarse_timeline=false`. Their primary cache directory is keyed only by the VOD and visual
detector configuration. They run metadata → visual stream → layout frames → YuNet → hysteresis →
layout/phase timeline directly; audio extraction, VAD and Whisper are not invoked. An older
`coarse_timeline.json` can still be read and exported, but is optional and cannot block Inspector
polling, notes or visual export. Legacy heuristic jobs remain readable with their original artifacts.

Visual jobs are explicitly recorded with `phase_detection_strategy=visual_layout` and
`requires_coarse_timeline=false`. Their primary cache directory is keyed only by the VOD and visual
detector configuration. They run metadata → visual stream → layout frames → YuNet → hysteresis →
layout/phase timeline directly; audio extraction, VAD and Whisper are not invoked. An older
`coarse_timeline.json` can still be read and exported, but is optional and cannot block Inspector
polling, notes or visual export. Legacy heuristic jobs remain readable with their original artifacts.

Useful configuration is documented in `.env.example`. For a short smoke, temporarily set
`VOD_ANALYSIS_MAX_SECONDS=60` and `VOD_ANALYSIS_FETCH_BLOCK_SECONDS=60`. Development fixtures remain
available with `VOD_ANALYSIS_FIXTURE_MODE=true` and now include a coarse music/silence/conversation/
gameplay signal timeline without assigning final phases.

```bash
python scripts/smoke_vod_analysis_fixture.py
python scripts/smoke_vod_analysis_coarse.py \
  'https://www.twitch.tv/videos/REAL_VOD_ID' \
  --api http://localhost:8000
python scripts/smoke_vod_analysis_phases.py
python scripts/smoke_vod_analysis_phases.py \
  data/analysis/cache/CACHE_KEY/coarse_timeline.json \
  --metadata data/analysis/JOB_ID/metadata.json \
  --output /tmp/phase_timeline.json
```

Current limitations: events shorter than the sampling/hysteresis horizon can be suppressed; HLS
seeks can fetch complete segments; signed URLs can expire; missed or false face detections affect the
layout directly; a large face shown during non-chat content maps to talking; a small facecam maps to
gameplay even during sustained speech; and OBS scenes that do not follow IlloJuan's normal geometry
remain unknown. This detects OBS layout, not streamer activity. Phase 4 must deeply transcribe only
the selected talking blocks and perform topic segmentation.

## VOD Inspector

**VOD Inspector** is an engineering-only mode for trying to falsify the current phase detector on
real IlloJuan VODs. It runs metadata → preserved coarse analysis → visual layout detection;
it does not run deep Whisper, topic segmentation, candidates, titles, editorial scoring, or renders.

The inspector shows a proportional colored timeline and every merged segment with timestamps,
duration, confidence, reason codes, warnings, and an **Open on Twitch/YouTube** link at its exact
start. Twitch links use `?t=1h42m30s`; YouTube links preserve the video query and add `t=<seconds>`.

Optional Validation Notes accept ground-truth boundaries for the primary conversation, first
gameplay interval, and second/third talking blocks. Comparison metrics include signed transition
errors, mean/max absolute error, omitted phases, false detections and duration-weighted confidence.
Notes are a local JSON artifact for the inspection job and are not part of SQLite job history.

**Export Validation Report** creates a whitelist-only ZIP containing metadata, coarse, layout and
phase timelines, a real PNG timeline, Markdown summary and validation report. With
`VALIDATION_DEBUG=true`, it additionally includes raw scores, smoothed windows and the transition
graph. Credentials, cookies, tokens, temporary media and unrelated files are never included.

Smoke test using fixture mode:

```bash
VOD_ANALYSIS_FIXTURE_MODE=true VALIDATION_DEBUG=true docker compose up -d --force-recreate api
python scripts/smoke_vod_inspector.py --api http://localhost:8000
docker compose up -d --force-recreate api web
```

For real validation, leave fixture mode disabled, open **VOD Inspector**, paste an authorized VOD,
inspect segments using their direct links, enter any measured ground truth, then export the report.
The tool reports disagreement; it does not claim that the detector is accurate.

## Real Twitch and YouTube setup

These are the only manual steps required for a real test.

1. Prepare and start the project:

   ```bash
   cp .env.example .env
   ./scripts/setup_local.sh
   docker compose up --build
   ```

2. In Google Cloud, enable **YouTube Data API v3**, configure the OAuth consent screen, and create an **OAuth client ID → Desktop app**. Download its JSON, then copy it without changing its contents:

   ```bash
   cp ~/Downloads/client_secret_*.json data/credentials/client_secret.json
   ```

3. From the Kali graphical desktop session, authorize the Google account that owns your YouTube channel. The command runs natively on the host, creates `.venv` with only the OAuth dependencies when needed, and keeps port 8080 open until the localhost callback completes. When invoked as root, it runs the graphical step as user `kali`:

   ```bash
   ./scripts/youtube_auth.sh
   ```

   The wrapper verifies `data/credentials/token.json` and automatically runs `docker compose restart api` when the API is active. If Compose is unavailable, it prints that exact restart command.

4. Check readiness and inspect one public Twitch VOD without downloading it:

   ```bash
   ./scripts/run_real_test.sh
   ./scripts/test_twitch_url.sh 'https://www.twitch.tv/videos/REAL_VOD_ID'
   ```

Public Twitch VODs require no Twitch API key. If yt-dlp says a VOD requires a session, export only your own Netscape-format Twitch cookies to `data/credentials/twitch_cookies.txt`; the configured path is already ignored and mounted. The application does not bypass deleted, subscriber-only, private, DRM-protected, or otherwise restricted content.

## Native Linux/Kali setup

Install system dependencies (package names shown for Debian/Kali):

```bash
sudo apt update
sudo apt install -y python3-venv ffmpeg nodejs npm
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements-dev.txt
npm --prefix apps/web install
cp .env.example .env
```

Check everything:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/check_dependencies.py
ffmpeg -version
ffprobe -version
.venv/bin/yt-dlp --version
```

Because yt-dlp is installed inside `.venv`, either run the combined development script or set `YTDLP_PATH=.venv/bin/yt-dlp` in `.env`:

```bash
sed -i 's|YTDLP_PATH=yt-dlp|YTDLP_PATH=.venv/bin/yt-dlp|' .env
chmod +x scripts/dev.sh
./scripts/dev.sh
```

Alternatively, use two terminals from the repository root:

```bash
.venv/bin/uvicorn apps.api.app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
npm --prefix apps/web run dev -- --port 3000
```

Native services bind to localhost by default. Configure ports, duration limits, margins, silence thresholds, Whisper model/device/language, paths, and encoder quality in `.env`; all available keys are documented in `.env.example`.

## YouTube OAuth details

Rendering and preview work normally when YouTube credentials are absent. The UI returns a readable setup error if upload is attempted without authorization.

1. Open Google Cloud Console and create or select a project.
2. In **APIs & Services → Library**, enable **YouTube Data API v3**.
3. Configure the OAuth consent screen. For an app in testing, add your own Google account as a test user.
4. In **Credentials**, create an **OAuth client ID** with application type **Desktop app**.
5. Download the JSON and save it as `data/credentials/client_secret.json`.
6. From the repository root, authorize once:

   ```bash
   ./scripts/youtube_auth.sh
   ```

   The command never runs OAuth inside Docker. It uses `.venv/bin/python`, creating `.venv` and installing `scripts/requirements-youtube-auth.txt` if needed. Run it from the Kali graphical session so the host browser and `DISPLAY`/Wayland session are available. Approve access with the channel-owning account and let the browser return to the temporary localhost callback on port 8080. It also verifies that the account exposes a YouTube channel.
7. The refresh token is saved with mode `0600` to `data/credentials/token.json`. The wrapper verifies the file and restarts a running API automatically; otherwise run `docker compose restart api` after starting Compose.

Both credential files are under the ignored `data/` tree and must never be committed or shared. OAuth always runs natively on the host; Docker only reads and refreshes the resulting bind-mounted token. If no graphical browser is available, start a Kali desktop session and rerun the wrapper. Uploads consume API quota and retries may consume more. Upload visibility defaults to `private`; deliberately choose another value in the preview form if desired.

## Processing flow and files

Each job moves through inspection, download, precise trim, silence analysis, plan generation, render, and `ready`. YouTube upload is a separate queued action. A restart keeps finished/failed history and marks an interrupted in-process job failed so it is never silently stuck.

```text
data/
├── app.db
├── downloads/<job-id>/
├── work/<job-id>/source_clip.mp4
├── work/<job-id>/edit_plan.json
├── rendered/<job-id>.mp4
├── subtitles/<job-id>.ass
├── models/                       # persistent faster-whisper model cache
├── credentials/                 # ignored secrets/tokens
└── logs/api.log
```

Technical command output is captured and condensed into readable job errors. Full application exceptions are logged locally. Job deletion is blocked while work is active and only removes validated paths under `data/`.

Optional authenticated Twitch access uses only `data/credentials/twitch_cookies.txt`. The backend refuses cookie paths outside `DATA_DIR` and never returns credentials or tokens through the API.

## Tests and checks

```bash
.venv/bin/pytest apps/api/tests -q
.venv/bin/ruff check apps/api scripts
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web run build
docker compose config
PYTHONPATH=. .venv/bin/python scripts/smoke_demo.py
SMOKE_WHISPER_MODEL=tiny .venv/bin/python scripts/smoke_vertical_subtitles.py
.venv/bin/python scripts/check_real_setup.py
```

To exercise the complete render path without a Twitch download, keep **Demo processing** checked and submit the default 12-second interval. Demo output is capped at 30 seconds.

## Known limitations

- Twitch playback/access rules still apply. The application does not bypass subscriber restrictions, deleted/private content, DRM, or authorization.
- Twitch/yt-dlp behavior can change; update the pinned yt-dlp release when extractors require it.
- Loudness normalization uses a reliable single-pass `loudnorm` filter, not a slower measured two-pass workflow.
- The first subtitled render downloads the configured faster-whisper model and therefore requires internet access and additional time. `WHISPER_DEVICE=auto` selects CUDA when CTranslate2 can see it and otherwise CPU; `WHISPER_COMPUTE_TYPE=auto` selects `float16` for CUDA or `int8` for CPU. Docker uses CPU unless GPU access is explicitly configured.
- Smart vertical uses geometric face/layout heuristics rather than semantic gameplay understanding. Captions use short word groups rather than per-word animation.
- The in-process worker handles one media/upload job at a time. Restarting during work marks that job failed; submit a new job to retry.
- The app is designed only for trusted personal localhost use and has no user authentication.

## IlloJuan visual layout profiles

VOD Inspector and Automatic VOD Analysis now classify OBS scenes with the local profile
`data/profiles/illojuan_visual.json`. YuNet from Smart Vertical verifies faces only inside the expected
regions; a face elsewhere is not authoritative. Matching combines face position (15–18%), face size
(10%), stable-background similarity (27–30%), reference similarity (35%), and temporal stability
(10%). The enabled measured layouts are `full_camera_room` (TALKING, threshold 0.70) and
`gameplay_left` and `gameplay_small_left` (GAMEPLAY, threshold 0.68). The schema and creation tool accept right/large variants,
but none are included until real references provide measured coordinates. A valid frame below every threshold is `waiting_unmatched`; corrupt,
low-quality, or nearly tied frames are UNKNOWN. Three equal layout IDs confirm a transition by default.
If the two closest layouts are both known variants of the same phase, the phase remains valid and the
best layout ID is retained with `same_phase_layout_tie_resolved`; a cross-phase tie remains UNKNOWN.
If the two closest layouts are both known variants of the same phase, the phase remains valid and the
best layout ID is retained with `same_phase_layout_tie_resolved`; a cross-phase tie remains UNKNOWN.

References live under `data/profiles/illojuan/`. They are local profile assets, never credentials. Any
profile JSON or reference-byte change changes the visual cache key. Validate and smoke-test with:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_visual_layout_profile.py data/profiles/illojuan_visual.json
PYTHONPATH=. .venv/bin/python scripts/smoke_visual_layout_profiles.py
```

Add a measured layout with `scripts/create_visual_layout_profile.py --help`. Coordinates must be
measured on a real screenshot; do not guess them. To add lighting/wardrobe variants to an existing
layout, place the image below the profile directory, append it to `reference_images`, increment the
profile version, validate, and rerun the smoke. Stable regions should exclude face, body, chat, alerts,
and dynamic game/video content. Background or overlay redesigns need new references or a new layout.

Known limits include OBS redesigns, moving/cropped webcams, lighting changes outside the references,
occluded faces, visually similar rooms, transition frames, and layouts not yet profiled. The matcher
does not identify IlloJuan; it recognizes measured scene structure. Audio/VAD/Whisper coarse artifacts
remain available for later semantic analysis but never decide these visual phases.

## Main implementation files

- Backend API and lifecycle: `apps/api/app/main.py`
- Job persistence: `apps/api/app/database.py`
- Background orchestration: `apps/api/app/worker.py`
- yt-dlp/FFmpeg processing: `apps/api/app/services/media.py`
- Silence-to-segment decisions: `apps/api/app/services/edit_plan.py`
- Local transcription and ASS styling: `apps/api/app/services/subtitles.py`
- YouTube OAuth/upload: `apps/api/app/services/youtube.py`
- Frontend page and components: `apps/web/app/page.tsx`, `apps/web/components/`
- Configuration: `apps/api/app/config.py`, `.env.example`

## Clipping Studio interface

The primary web interface is now a dark, desktop-first clipping studio with three persistent navigation
areas: **Home**, **Jobs**, and **Settings**. Home starts one of two explicit workflows:

- **Vertical Clip:** Source → Raw Preview → Edit → Render → Review → Publish.
- **Long-form Clip:** Source → Analyze → Candidates → Raw Preview → Edit → Render → Review → Publish.

Both workflows use the same typed editor. The vertical preset enables Smart Vertical, subtitles,
silence shortening, normalization, and 9:16 output. The horizontal preset preserves the source layout,
keeps Smart Vertical disabled, and uses conservative long-form defaults. Candidate selection creates a
clean raw preview first; it never silently starts the final edit.

Raw previews are ordinary persisted media jobs marked `job_kind=raw_preview`. Final renders reference
that job with `source_job_id`, so the worker reuses the already trimmed source interval instead of
downloading it again. `workflow_type` and `project_id` let the Jobs page reconstruct the correct route
after navigation or refresh. Small, non-sensitive draft settings are mirrored in browser storage; media,
backend state, credentials, and authoritative job progress remain server-side.

Existing API routes remain authoritative: `POST/GET /jobs` for previews and renders,
`POST/GET /vod-analysis` for long-form discovery, `GET /jobs/{id}/video` for playback/download,
`POST /jobs/{id}/youtube` for publishing, and `/setup/status` for local capabilities. The additive
`GET /vod-analyses` endpoint exposes persisted analysis jobs to the Jobs page. VOD Inspector remains
available under `/inspector` as an engineering tool and is not part of either user workflow.

Frontend verification commands:

```bash
npm --prefix apps/web test
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

## Clipping Studio interface

The primary web interface is now a dark, desktop-first clipping studio with three persistent navigation
areas: **Home**, **Jobs**, and **Settings**. Home starts one of two explicit workflows:

- **Vertical Clip:** Source → Raw Preview → Edit → Render → Review → Publish.
- **Long-form Clip:** Source → Analyze → Candidates → Raw Preview → Edit → Render → Review → Publish.

Both workflows use the same typed editor. The vertical preset enables Smart Vertical, subtitles,
silence shortening, normalization, and 9:16 output. The horizontal preset preserves the source layout,
keeps Smart Vertical disabled, and uses conservative long-form defaults. Candidate selection creates a
clean raw preview first; it never silently starts the final edit.

Raw previews are ordinary persisted media jobs marked `job_kind=raw_preview`. Final renders reference
that job with `source_job_id`, so the worker reuses the already trimmed source interval instead of
downloading it again. `workflow_type` and `project_id` let the Jobs page reconstruct the correct route
after navigation or refresh. Small, non-sensitive draft settings are mirrored in browser storage; media,
backend state, credentials, and authoritative job progress remain server-side.

Existing API routes remain authoritative: `POST/GET /jobs` for previews and renders,
`POST/GET /vod-analysis` for long-form discovery, `GET /jobs/{id}/video` for playback/download,
`POST /jobs/{id}/youtube` for publishing, and `/setup/status` for local capabilities. The additive
`GET /vod-analyses` endpoint exposes persisted analysis jobs to the Jobs page. VOD Inspector remains
available under `/inspector` as an engineering tool and is not part of either user workflow.

Frontend verification commands:

```bash
npm --prefix apps/web test
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```
