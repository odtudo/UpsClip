# Implementation status

## 2026-07-15 — Visual OBS layout phase detector

- [x] Phase decisions use only video layout; Whisper, VAD, transcripts, audio, embeddings, LLMs and
  chapter signals do not contribute to classification.
- [x] The exact Smart Vertical YuNet detector and `classify_scene` infrastructure are reused; no
  second face detector was introduced.
- [x] Configurable two-second sparse sampling records timestamp, box, area ratio, position,
  confidence, layout, phase and reason codes.
- [x] Deterministic mapping: no face → waiting, fullscreen face → talking, small facecam → gameplay,
  and ambiguous/decode failure → unknown.
- [x] Configurable consecutive-sample hysteresis and merged median-confidence visual segments.
- [x] Incremental, resumable and separately fingerprinted `layout_timeline.json`; Phase 2 audio/VAD/
  probe cache remains intact for Phase 4.
- [x] Backward-compatible phase timeline, talking blocks, API, Automatic Analysis and VOD Inspector.
- [x] Inspector export includes the layout timeline; debug frames include boxes, classification,
  area, position and confidence.
- [x] Tests cover all four layouts, ambiguous frames, hysteresis, transitions, timeline and cache.

The older weighted Phase 3 module remains for old-job compatibility and historical tests, but new
real and fixture jobs do not call it. This detector identifies OBS layout, not streamer activity.
Phase 4 is still not implemented.

### Visual/coarse integration correction

- [x] Removed the runtime dependency from visual analysis and VOD Inspector to Phase 2.
- [x] Added explicit SQLite strategy and `requires_coarse_timeline` migration fields.
- [x] Visual cache key and directory no longer derive from the coarse cache key.
- [x] Polling returns HTTP 200 for queued, processing, completed and failed jobs.
- [x] Inspector reads `layout_timeline.json` first; coarse and legacy phase artifacts are optional.
- [x] Visual export requires metadata/layout/report artifacts and conditionally includes legacy files.
- [x] Existing visual jobs are migrated and old heuristic jobs remain readable.
- [x] Tests fail explicitly if the visual analyzer calls audio extraction, VAD or Whisper.

## 2026-07-15 — VOD Inspector

- [x] Third engineering-only UI mode reusing metadata, coarse analysis and the active visual detector.
- [x] Horizontal proportional phase timeline with confidence, reasons and warnings.
- [x] Exact per-segment Twitch and YouTube timestamp links.
- [x] Temporary local validation notes for primary/gameplay and talking blocks 2/3.
- [x] Automatic signed errors, MAE, maximum error, omissions, false detections and mean confidence.
- [x] Deterministic PNG timeline and Markdown summary/validation report.
- [x] Whitelist-only ZIP export with no credentials, cookies, tokens or unrelated files.
- [x] `VALIDATION_DEBUG` raw scores, smoothed windows and transition graph.
- [x] API, URL, metrics, notes, PNG, report and ZIP tests plus end-to-end fixture smoke.

The fixture smoke completed analysis, comparison and export. Its archive contained exactly the
expected metadata/coarse/layout/phase timelines, PNG, summaries and debug JSON files. Services were
then restored to real mode. This tool is intended to collect failure evidence across 10–20 real
IlloJuan VODs before changing the detector or starting Phase 4.

## 2026-07-15 — Automatic VOD Analysis Phase 3

- [x] Explainable per-window scoring for waiting/music, talking, gameplay and unknown.
- [x] Centralized, validated IlloJuan thresholds, weights and transition penalties.
- [x] Deterministic Viterbi smoothing, unknown-gap bridging and conservative microsegment merging.
- [x] Robust-confidence merged phase segments with transition and reason codes.
- [x] Detection of every talking segment, long/short relevance, primary initial block and end reason.
- [x] Bounded Phase 4 selection supporting later gameplay-to-talking returns.
- [x] Separately fingerprinted and atomically persisted `phase_timeline.json` cache.
- [x] Existing Phase 2 coarse cache reused without yt-dlp, FFmpeg, VAD or Whisper work.
- [x] Optional chapter hints, missing-signal warnings and non-fatal missing-primary behavior.
- [x] API additions are optional/backward compatible; automatic UI renders phases and talking blocks.
- [x] Long multistage fixtures, Phase 3 unit tests, fixture smoke and cached-real smoke.

The only persisted real coarse timeline available for tuning covers two silent intro windows (60
seconds). Phase 3 correctly labels the whole interval as waiting/music, returns no talking blocks and
warns that no primary block exists. The multistage fixture yields waiting, talking, gameplay, talking,
gameplay; two 720-second talking blocks; `talking-001` as primary; and both blocks selected. This is
useful architectural verification but not evidence of phase accuracy over a complete real VOD.

Not implemented by design: full selected-block transcription, transcript cleaning, topic boundaries,
embeddings/LLM analysis, candidate construction, editorial scoring, diversity, titles or real
candidate generation. These begin in Phase 4.

## 2026-07-14 — Automatic VOD Analysis Phase 2

- [x] Real Twitch/YouTube metadata schema and yt-dlp inspection without media download.
- [x] Sanitized format summaries; temporary signed URLs never persisted or returned.
- [x] Validated 30-second windows, centered 10-second samples, partial final windows and 15-minute blocks.
- [x] Direct FFmpeg sampling to mono 16 kHz PCM with bounded subprocess timeout and no `shell=True`.
- [x] Block URL reuse, per-block refresh, one expiry retry and optional Twitch cookies under `DATA_DIR`.
- [x] Real faster-whisper Silero VAD regions and aggregate speech/silence/continuity metrics.
- [x] RMS, variance, peak, dynamic range, zero crossings, spectral flatness and music-oriented features.
- [x] Lazy single-load Spanish `tiny` Whisper probes gated by voice ratio and sustained speech.
- [x] Sparse reduced visual frames, difference/motion metrics, and reused Smart Vertical YuNet detector.
- [x] Versioned coarse timeline, atomic block persistence, per-job copy and cross-job window resume.
- [x] Persistent completed/total/current-timestamp progress in SQLite and frontend.
- [x] Phase 1 fixture preserved and expanded with an unclassified coarse signal timeline.
- [x] Simulated unit/integration smoke plus a real two-window Twitch Docker smoke.

The real smoke inspected VOD `2814270995`: metadata reported 12,522 seconds and valid audio/video
formats; two logical windows completed using 20 seconds of PCM and four reduced frames. VAD ran,
visual sampling/YuNet succeeded, cache reuse succeeded, and estimated requested media was 2.4 MB.
The sampled intro contained no Silero speech, so probes were correctly skipped instead of wasting
Whisper compute. Probe execution is independently covered with real faster-whisper and mocks.

Not implemented by design: final phase classification, temporal smoothing, definitive conversation
start/end, full relevant-block transcription, topics, semantic embeddings, scoring, diversity,
titles, or real candidates. These begin in Phase 3 and later phases.

## 2026-07-14 — Automatic VOD Analysis Phase 1

- [x] Existing manual/render/upload/history pipeline inspected and preserved.
- [x] Separate validated analysis schemas and future semantic-analyzer interface.
- [x] Centralized, validated built-in `illojuan` analysis profile with no scattered thresholds.
- [x] Twitch and YouTube source identity parsing.
- [x] Persistent `vod_analysis_jobs` SQLite table, restart failure state, progress, errors and result.
- [x] Versioned cache key covering source, profile, pipeline, Whisper, semantic backend and score.
- [x] `POST /vod-analysis`, `GET /vod-analysis/{id}`, and analysis profile listing.
- [x] Shared single-worker orchestration; worker contains no analysis algorithm.
- [x] Deterministic fixture covering music, conversation, gameplay, topics, good/bad signals,
  candidate scores, titles, summaries, warnings and reason codes.
- [x] JSON artifacts under persistent `data/analysis`; internal paths are not exposed.
- [x] Manual/Automatic frontend modes, polling, progress, cache indicator, editable candidates and
  Twitch candidate handoff to the existing render pipeline.
- [x] API/unit tests and fixture smoke added.

Not implemented by design in Phase 1: real metadata/audio download, audio cache, VAD, coarse
transcription, full conversation transcription, phase heuristics, visual transition detection,
topic segmentation, embeddings/LLM integration, real scoring/diversity/title generation, and
complete real-source candidate-to-render integration. These start in Phase 2 and later phases.

## 2026-07-14 — Smart Vertical Layout

- [x] Sampled grayscale scene detection with minimum durations and stable merging.
- [x] OpenCV 4.12 YuNet CPU detection with checksum-verified ONNX; Haar is fallback-only.
- [x] Rule classifier with temporal tracks, lateral columns, area, stability, ambiguity, hysteresis and reasons.
- [x] Face expansion/clamp/median, opposite content crops, duplicate warning and optional profile ROI.
- [x] Versioned `smart_vertical_v2_yunet` plan with fingerprint, timings, warnings and A/V render metrics.
- [x] Segment renderer and concat at H.264/AAC, yuv420p, SAR 1:1, 1080×1920; global fallback.
- [x] Backward-compatible SQLite columns for Smart flag/profile/plan/warnings/summary.
- [x] Safe `GET /profiles`, profile scripts, uploader matching, UI selector/summary/warnings/progress.
- [x] Transcription after definitive timeline/composition; ASS uses 1080×1920, 88 px, margin 240.
- [x] Persistent profile/smoke directories and UID 1000 non-root write permissions.

Verification: 45 backend tests and Ruff passed; ESLint, TypeScript and Next production build passed;
Compose config and both images built; API/web run and API is healthy; OpenCV 4.12.0,
faster-whisper, FFmpeg/ffprobe and libass verified inside API. Horizontal smoke passed (8.30 s,
preview HTTP 200). Docker Smart smoke passed with H.264/AAC, audio, yuv420p, SAR 1:1, 1080×1920,
six-second duration within 0.25 s, distinct non-black regions and burned ASS. Frames were inspected.

Real IlloJuan diagnosis and correction: job `f3e019e0-b3fe-4a56-a56b-d38e244c045e` contained a
1920×1080, 88.8 s edited timeline. The original analysis extracted 178 scene samples and 12 face
samples. Haar returned 21 boxes, but selected conflicting avatars/thumbnails instead of a stable
streamer track; the classifier produced one `uncertain` segment and no profile was resolved. The
160×90 scene metric peaked at 0.147484 while the old 0.30 threshold hid the real layout transition.

YuNet at 1280 px analyzed 24 frames across the corrected split and returned 146 total boxes, 112 over
the normal 0.55 threshold. The streamer track was present in 12/12 samples of each segment. The plan
now classifies 0.0–66.5 s as lateral `small_facecam` and 66.5–88.8 s as `fullscreen_face`; there are
no face-detection fallbacks. The real measured IlloJuan profile uses x=0, y=338, width=407,
height=380 with content ROI x=407, y=0, width=1513, height=1080. Visual inspection confirmed streamer
above content, readable burned captions, a correct fullscreen crop, no deformation, and no zoom.
An additional real-test defect was fixed by normalizing segment FPS/time bases before concat and
validating audio/video durations independently (final A/V delta 0.138651 s).

Remaining limitations: conservative border refinement, cancellation, and a visual profile editor are
not implemented; circular/transparent facecams and crowded calls may still need a profile.

## Real-service readiness

- [x] Persistent Twitch download, exact FFmpeg trim, edit, preview, and separate upload flow.
- [x] Public Twitch metadata inspection and section download require no Twitch API credentials.
- [x] Optional Netscape cookie file is accepted only from inside `DATA_DIR` and is never returned by the API.
- [x] Native-host Google Desktop OAuth authorization, refresh-token persistence, automatic refresh, and channel verification. Docker never runs the browser flow.
- [x] `GET /setup/status` reports dependencies, storage, SQLite, OAuth files/token usability, and optional cookies without paths or secret contents.
- [x] UI configuration panel and disabled YouTube upload until OAuth is usable.
- [x] Persistent Docker bind mount for database, videos, logs, cookies, OAuth client file, and token.
- [x] Missing/invalid credentials and restricted/deleted/login-required Twitch failures have user-facing messages.
- [x] Demo processing remains available.
- [x] Automatic zooms removed from API, SQLite, edit plans, FFmpeg, frontend, configuration, tests, and documentation.
- [x] Vertical output forces local faster-whisper transcription and burns large ASS captions into the final MP4; horizontal subtitles are optional.

## Variables actually used

Backend settings: `API_HOST`, `API_PORT`, `DATA_DIR`, `DATABASE_URL`, `CORS_ORIGINS`, `MAX_CLIP_DURATION_SECONDS`, `DOWNLOAD_MARGIN_SECONDS`, `FFMPEG_PATH`, `FFPROBE_PATH`, `YTDLP_PATH`, `VIDEO_CRF`, `VIDEO_PRESET`, `SILENCE_MIN_SECONDS`, `SILENCE_REMOVE_AFTER_SECONDS`, `SILENCE_PADDING_SECONDS`, `WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `WHISPER_LANGUAGE`, `YOUTUBE_CLIENT_SECRETS_PATH`, `YOUTUBE_TOKEN_PATH`, `TWITCH_COOKIES_PATH`, `DEMO_MODE`, and `LOG_LEVEL`.

Smart settings also consumed: `SMART_VERTICAL_LAYOUT_DEFAULT`, `SCENE_DETECTION_ENABLED`,
`SCENE_CHANGE_THRESHOLD`, `SCENE_MIN_DURATION_SECONDS`, `SCENE_SAMPLE_FPS`,
`FACE_DETECTION_SAMPLE_FPS`, `FACE_ANALYSIS_MAX_WIDTH`, `FACE_DETECTOR_MODEL_PATH`,
`FACE_DETECTOR_SCORE_THRESHOLD`, `FACE_DETECTOR_PROFILE_THRESHOLD`,
`FACE_DETECTOR_NMS_THRESHOLD`, `FACE_DETECTOR_TOP_K`, `FACE_DETECTOR_HAAR_FALLBACK`,
`FACE_LAYOUT_MIN_CONFIDENCE`, `FULLSCREEN_FACE_AREA_THRESHOLD`,
`FACECAM_MAX_FACE_AREA_THRESHOLD`, `FACE_STABILITY_POSITION_TOLERANCE`,
`FACE_STABILITY_SIZE_TOLERANCE`, `LAYOUT_MIN_SEGMENT_SECONDS`, `LAYOUT_MERGE_IOU_THRESHOLD`,
`LAYOUT_MERGE_CENTER_DISTANCE_RATIO`, all four `FACEBOX_EXPAND_*` values,
`VERTICAL_FACECAM_HEIGHT_RATIO`, `VERTICAL_OUTPUT_WIDTH`, `VERTICAL_OUTPUT_HEIGHT`,
`VERTICAL_DIVIDER_HEIGHT`, and `SMART_LAYOUT_DEBUG`.

Compose/frontend settings: `WEB_PORT`, `LOCAL_UID`, `LOCAL_GID`, and build-time `NEXT_PUBLIC_API_URL`. Compose deliberately overrides native host paths with `/data`, `sqlite:////data/app.db`, `/data/credentials/client_secret.json`, `/data/credentials/token.json`, and `/data/credentials/twitch_cookies.txt`.

No Twitch Client ID or Client Secret is used or required.

## Persistent paths

- Host OAuth client: `data/credentials/client_secret.json`
- Host reusable token: `data/credentials/token.json` (written mode `0600`)
- Optional host Twitch cookies: `data/credentials/twitch_cookies.txt`
- Container equivalents: `/data/credentials/client_secret.json`, `/data/credentials/token.json`, `/data/credentials/twitch_cookies.txt`
- SQLite: `data/app.db` on host, `/data/app.db` in the API container
- Generated files: `data/downloads`, `data/work`, `data/rendered`, `data/subtitles`, `data/models`, `data/thumbnails`, and `data/logs`

## Exact commands

```bash
cp .env.example .env
./scripts/setup_local.sh
docker compose up --build
cp ~/Downloads/client_secret_*.json data/credentials/client_secret.json
./scripts/youtube_auth.sh
# The wrapper restarts a running API; otherwise:
docker compose restart api
./scripts/run_real_test.sh
./scripts/test_twitch_url.sh 'https://www.twitch.tv/videos/REAL_VOD_ID'
```

## Verification performed (2026-07-14)

- Full repository documentation, configuration, Dockerfiles, scripts, backend, frontend, and tests inspected before changes.
- `python3 -m compileall -q apps/api scripts`: passed.
- `ruff check apps/api scripts`: passed.
- Backend pytest suite including setup-status and credential-path tests: passed.
- Next.js type check, ESLint, and production Docker build: passed.
- `docker compose config`: passed; API host port 8000 and web host port 3000 resolve correctly.
- API and web Docker images: built successfully.
- Docker API health check: healthy; FFmpeg, ffprobe, and yt-dlp all reported available.
- `GET /setup/status`: correctly reported writable data/SQLite and absent OAuth files/token without revealing paths or contents.
- Frontend `/`: HTTP success on port 3000.
- `/data` and `/data/app.db`: writable as the configured non-root UID/GID 1000 in the API container.
- Missing-secret OAuth invocation: failed safely with the exact placement instruction and no secret output.
- Container smoke demo: passed; a 12-second generated clip was edited to 8.30 seconds and preview returned HTTP 200.
- Secret scan of the supplied working tree: no credential/token/cookie contents found; `.gitignore` covers environment files, OAuth files, cookies, SQLite, temporary files, and video outputs.
- Zoom-removal migration: passed against a legacy SQLite table and legacy `edit_plan.json` while preserving the job row.
- Backend suite after vertical-caption changes: **31 passed**; Ruff passed.
- Frontend TypeScript, ESLint, native Next.js build, and Docker production build: passed.
- `faster-whisper==1.2.1` imported successfully in the non-root API container.
- FFmpeg `ass`, `subtitles`, and `flite` filters: available in the API image.
- Historical subtitle-only smoke originally validated 720×1280; Smart Vertical now supersedes it with the documented **1080×1920** Docker smoke and representative frames.
- Whisper automatic device selection: selected CPU in the current Docker environment; the persistent model cache is under `data/models`.
- API and frontend remain healthy on ports 8000 and 3000 after the database migration.
- Real IlloJuan reprocess: plan 2 segments (lateral facecam + fullscreen), 24 frames analyzed,
  146 YuNet boxes/112 accepted, planning 31.032 s, H.264/AAC 1080×1920 final inspected visually.
- Real verification artifacts: `data/smoke_tests/real_illojuan_fix/`; debug frames and complete
  detection records: `data/work/f3e019e0-b3fe-4a56-a56b-d38e244c045e/smart_vertical_debug/`.

## External/manual boundaries

- A real YouTube upload cannot be asserted until the user supplies a Google **Desktop app OAuth client JSON**, consents, and chooses a channel-owning account.
- The corrected Smart layout was validated against the locally available real public IlloJuan VOD interval; other streamer overlays still require their own representative validation.
- Cookie export is optional and manual only when Twitch itself requires the user's session; access controls, subscriptions, deleted content, and DRM are not bypassed.
- The supplied workspace has no `.git` directory, so current files and ignore rules were scanned, but Git commit history could not be audited here.

## VOD layout-profile detector (2026-07-15)

- Phase authority changed from generic face size/position to deterministic IlloJuan OBS profile matching.
- Profile and reference hashing independently invalidate `layout_timeline.json` cache entries.
- Enabled measured layouts: `full_camera_room`, `gameplay_left`, and `gameplay_small_left`; unmeasured right/large variants are deliberately absent.
- Per-frame artifacts now contain layout ID, best/second score, margin, reference, component signals,
  background-region scores, reason codes, and warnings. Inspector exposes segment-level matching data.
- Scoring uses HSV histograms, difference hashes, edge-map comparison, stable regions, expected face
  geometry, and temporal stability. Valid unmatched frames fall back to WAITING; invalid/ambiguous frames
  become UNKNOWN. Three consecutive layout IDs confirm transitions.
- Pipeline `vod-analysis-profile-layout.2` preserves a known phase when two close layouts map to that
  same phase, while cross-phase ties remain UNKNOWN; the decision is explicitly reason-coded.
- Creation/validation utilities and `scripts/smoke_visual_layout_profiles.py` were added. Docker/YuNet
  smoke: full camera TALKING 0.890; gameplay-left GAMEPLAY 0.891; gameplay-small-left GAMEPLAY 0.916;
  person-containing unmatched content WAITING (best rejected score 0.656).
- Audio, VAD, probes, coarse timeline, Smart Vertical output, and all legacy artifacts remain intact.
- Full real VOD `2814270995` validation completed for the configured first 10,800 seconds: 5,400 samples,
  no warnings/errors, 1,024 s WAITING, 3,692 s TALKING, 6,078 s GAMEPLAY, and 6 s UNKNOWN. The initial
  timeline is WAITING 00:00–10:12, TALKING 10:12–28:46; persistent small-facecam gameplay starts after
  01:23:46. Job `a5fa7b4f-c72c-4748-ba55-1e86dc5f8c04` and its independent cache/export were verified.
- Remaining validation boundary: enable other gameplay variants only after collecting rights-cleared real
  screenshots. Brief unmatched intervals inside gameplay remain visible as WAITING rather than being
  force-filled; they need additional references only after visual review confirms a stable OBS layout.
