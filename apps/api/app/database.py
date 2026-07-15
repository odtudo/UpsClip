import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .config import Settings

JSON_FIELDS = {"tags", "layout_warnings", "layout_summary"}
BOOL_FIELDS = {"remove_silences", "normalize_audio", "generate_subtitles", "demo", "smart_vertical_layout"}


class JobStore:
    def __init__(self, settings: Settings):
        self.path = settings.database_path
        self.data_dir = settings.data_dir

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    start_seconds INTEGER NOT NULL,
                    end_seconds INTEGER NOT NULL,
                    remove_silences INTEGER NOT NULL DEFAULT 1,
                    normalize_audio INTEGER NOT NULL DEFAULT 1,
                    generate_subtitles INTEGER NOT NULL DEFAULT 0,
                    output_format TEXT NOT NULL DEFAULT 'horizontal',
                    smart_vertical_layout INTEGER NOT NULL DEFAULT 1,
                    streamer_profile TEXT NOT NULL DEFAULT 'auto',
                    resolved_streamer_profile TEXT,
                    composition_plan_path TEXT,
                    layout_warnings TEXT NOT NULL DEFAULT '[]',
                    layout_summary TEXT NOT NULL DEFAULT '{}',
                    demo INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    current_step TEXT NOT NULL,
                    error_message TEXT,
                    completed_windows INTEGER NOT NULL DEFAULT 0,
                    total_windows INTEGER NOT NULL DEFAULT 0,
                    current_timestamp REAL NOT NULL DEFAULT 0,
                    download_path TEXT,
                    source_clip_path TEXT,
                    rendered_path TEXT,
                    subtitle_path TEXT,
                    edit_plan_path TEXT,
                    source_title TEXT,
                    rendered_duration REAL,
                    rendered_size INTEGER,
                    youtube_title TEXT,
                    youtube_description TEXT,
                    tags TEXT NOT NULL DEFAULT '[]',
                    privacy_status TEXT NOT NULL DEFAULT 'private',
                    youtube_video_id TEXT,
                    youtube_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "automatic_zooms" in columns:
                connection.execute("ALTER TABLE jobs DROP COLUMN automatic_zooms")
                columns.remove("automatic_zooms")
            additions = {
                "smart_vertical_layout": "INTEGER NOT NULL DEFAULT 1",
                "streamer_profile": "TEXT NOT NULL DEFAULT 'auto'",
                "resolved_streamer_profile": "TEXT",
                "composition_plan_path": "TEXT",
                "layout_warnings": "TEXT NOT NULL DEFAULT '[]'",
                "layout_summary": "TEXT NOT NULL DEFAULT '{}'",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        self._migrate_legacy_edit_plans()

    def _migrate_legacy_edit_plans(self) -> None:
        for path in (self.data_dir / "work").glob("*/edit_plan.json"):
            try:
                plan = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(plan, dict) and "zooms" in plan:
                plan.pop("zooms")
                path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        for field in JSON_FIELDS:
            fallback = "{}" if field == "layout_summary" else "[]"
            result[field] = json.loads(result.get(field) or fallback)
        for field in BOOL_FIELDS:
            result[field] = bool(result.get(field))
        return result

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        record = {
            **values,
            "status": "queued",
            "progress": 0,
            "current_step": "Queued",
            "tags": json.dumps(values.get("tags", [])),
            "layout_warnings": json.dumps(values.get("layout_warnings", [])),
            "layout_summary": json.dumps(values.get("layout_summary", {})),
            "created_at": now,
            "updated_at": now,
        }
        columns = ", ".join(record)
        placeholders = ", ".join("?" for _ in record)
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",  # noqa: S608 - internal columns
                list(record.values()),
            )
        created = self.get(values["id"])
        assert created is not None
        return created

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._decode(row)

    def list(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [decoded for row in rows if (decoded := self._decode(row)) is not None]

    def update(self, job_id: str, **values: Any) -> dict[str, Any] | None:
        if not values:
            return self.get(job_id)
        values["updated_at"] = datetime.now(UTC).isoformat()
        for field in JSON_FIELDS:
            if field in values:
                values[field] = json.dumps(values[field])
        assignments = ", ".join(f"{field} = ?" for field in values)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ?",  # noqa: S608 - internal fields
                [*values.values(), job_id],
            )
        return self.get(job_id)

    def delete(self, job_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cursor.rowcount > 0

    def fail_interrupted_jobs(self) -> None:
        now = datetime.now(UTC).isoformat()
        message = "Processing was interrupted by an application restart. Create a new job to retry."
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', progress = 0, current_step = 'Interrupted',
                    error_message = ?,
                    updated_at = ?
                WHERE status IN (
                    'queued', 'inspecting', 'downloading', 'trimming',
                    'analyzing', 'detecting_scenes', 'analyzing_layouts', 'composing',
                    'transcribing', 'rendering', 'finalizing', 'uploading'
                )
                """,
                (message, now),
            )


class VodAnalysisStore:
    """Persistent state for automatic analysis, separate from render jobs."""

    def __init__(self, settings: Settings):
        self.path = settings.database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vod_analysis_jobs (
                    id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    source_platform TEXT NOT NULL,
                    source_vod_id TEXT NOT NULL,
                    streamer_profile TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    fixture_mode INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    cached INTEGER NOT NULL DEFAULT 0,
                    warnings TEXT NOT NULL DEFAULT '[]',
                    result TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_vod_analysis_cache ON vod_analysis_jobs(cache_key, status)"
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(vod_analysis_jobs)")}
            additions = {
                "completed_windows": "INTEGER NOT NULL DEFAULT 0",
                "total_windows": "INTEGER NOT NULL DEFAULT 0",
                "current_timestamp": "REAL NOT NULL DEFAULT 0",
                "phase_detection_strategy": "TEXT NOT NULL DEFAULT 'legacy_heuristic'",
                "requires_coarse_timeline": "INTEGER NOT NULL DEFAULT 1",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE vod_analysis_jobs ADD COLUMN {name} {definition}")
            connection.execute(
                """UPDATE vod_analysis_jobs
                   SET phase_detection_strategy = 'visual_layout', requires_coarse_timeline = 0
                   WHERE pipeline_version LIKE 'vod-analysis-visual-layout.%'"""
            )
            connection.execute(
                """UPDATE vod_analysis_jobs
                   SET phase_detection_strategy = 'profile_layout_match', requires_coarse_timeline = 0
                   WHERE pipeline_version LIKE 'vod-analysis-profile-layout.%'"""
            )

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        value["fixture_mode"] = bool(value["fixture_mode"])
        value["cached"] = bool(value["cached"])
        value["requires_coarse_timeline"] = bool(value.get("requires_coarse_timeline", True))
        value["warnings"] = json.loads(value.get("warnings") or "[]")
        value["result"] = json.loads(value["result"]) if value.get("result") else None
        return value

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        record = {
            **values,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "cached": int(bool(values.get("cached", False))),
            "fixture_mode": int(bool(values.get("fixture_mode", False))),
            "phase_detection_strategy": values.get("phase_detection_strategy", "profile_layout_match"),
            "requires_coarse_timeline": int(bool(values.get("requires_coarse_timeline", False))),
            "warnings": json.dumps(values.get("warnings", [])),
            "result": json.dumps(values["result"]) if values.get("result") is not None else None,
            "created_at": now,
            "updated_at": now,
        }
        columns = ", ".join(record)
        placeholders = ", ".join("?" for _ in record)
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO vod_analysis_jobs ({columns}) VALUES ({placeholders})",  # noqa: S608
                list(record.values()),
            )
        created = self.get(values["id"])
        assert created is not None
        return created

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM vod_analysis_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._decode(row)

    def find_cached(self, cache_key: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT * FROM vod_analysis_jobs
                   WHERE cache_key = ? AND status = 'completed' AND result IS NOT NULL
                   ORDER BY updated_at DESC LIMIT 1""",
                (cache_key,),
            ).fetchone()
        return self._decode(row)

    def update(self, job_id: str, **values: Any) -> dict[str, Any] | None:
        if not values:
            return self.get(job_id)
        values["updated_at"] = datetime.now(UTC).isoformat()
        for field in ("warnings", "result"):
            if field in values:
                values[field] = json.dumps(values[field])
        assignments = ", ".join(f"{field} = ?" for field in values)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE vod_analysis_jobs SET {assignments} WHERE id = ?",  # noqa: S608
                [*values.values(), job_id],
            )
        return self.get(job_id)

    def fail_interrupted_jobs(self) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.execute(
                """UPDATE vod_analysis_jobs
                   SET status = 'failed', stage = 'interrupted',
                       error_message = 'Analysis was interrupted by an application restart.',
                       updated_at = ?
                   WHERE status IN ('queued', 'processing')""",
                (now,),
            )


def safe_data_path(path: str | Path, data_dir: Path) -> Path:
    candidate = Path(path).resolve()
    root = data_dir.resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("Path is outside the application data directory")
    return candidate
