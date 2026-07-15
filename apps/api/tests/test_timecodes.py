import pytest

from apps.api.app.timecodes import parse_timestamp, validate_interval


@pytest.mark.parametrize(
    ("value", "expected"),
    [("00:00", 0), ("12:34", 754), ("01:02:03", 3723), ("100:00", 6000)],
)
def test_parse_timestamp(value: str, expected: int) -> None:
    assert parse_timestamp(value) == expected


@pytest.mark.parametrize("value", ["", "10", "1:2", "12:60", "00:00:60", "words"])
def test_invalid_timestamp(value: str) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(value)


def test_end_must_follow_start() -> None:
    with pytest.raises(ValueError, match="after start"):
        validate_interval("01:00", "00:59", 120)


def test_maximum_duration() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        validate_interval("00:00", "02:01", 120)
