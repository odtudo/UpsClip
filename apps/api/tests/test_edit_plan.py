from apps.api.app.services.edit_plan import SilenceInterval, generate_edit_plan


def test_edit_plan_ignores_short_and_shortens_long_silences() -> None:
    plan = generate_edit_plan(
        20.0,
        [SilenceInterval(2.0, 2.8), SilenceInterval(5.0, 7.0), SilenceInterval(12.0, 16.0)],
        remove_silences=True,
        minimum_silence=1.2,
        remove_after=2.5,
        padding=0.2,
    )

    assert len(plan["removed_intervals"]) == 2
    assert plan["output_duration"] < 20.0
    assert plan["segments"][0]["source_start"] == 0.0
    assert "zooms" not in plan


def test_disabled_edits_keep_whole_clip() -> None:
    plan = generate_edit_plan(
        10.0,
        [SilenceInterval(2.0, 8.0)],
        remove_silences=False,
    )
    assert plan["segments"] == [{"source_start": 0.0, "source_end": 10.0, "output_start": 0.0}]
