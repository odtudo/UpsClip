import sqlite3

from apps.api.app.database import JobStore


def test_legacy_zoom_column_is_removed_without_losing_jobs(test_settings) -> None:
    test_settings.ensure_directories()
    plan_path = test_settings.data_dir / "work" / "legacy" / "edit_plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text('{"segments": [], "zooms": [{"scale": 1.07}]}', encoding="utf-8")
    with sqlite3.connect(test_settings.database_path) as connection:
        connection.execute(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                automatic_zooms INTEGER NOT NULL DEFAULT 1,
                source_url TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO jobs (id, automatic_zooms, source_url) VALUES (?, ?, ?)",
            ("legacy", 1, "https://www.twitch.tv/videos/1"),
        )

    store = JobStore(test_settings)
    store.initialize()

    with sqlite3.connect(test_settings.database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        legacy = connection.execute("SELECT id, source_url FROM jobs WHERE id = 'legacy'").fetchone()
    assert "automatic_zooms" not in columns
    assert "smart_vertical_layout" in columns
    assert "composition_plan_path" in columns
    assert legacy == ("legacy", "https://www.twitch.tv/videos/1")
    assert "zooms" not in plan_path.read_text(encoding="utf-8")
