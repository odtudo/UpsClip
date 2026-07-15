def parse_timestamp(value: str) -> int:
    value = value.strip()
    parts = value.split(":")
    if len(parts) not in {2, 3} or not all(part.isdigit() for part in parts):
        raise ValueError("Use MM:SS or HH:MM:SS (seconds must have two digits)")
    if len(parts[-1]) != 2 or int(parts[-1]) > 59:
        raise ValueError("Use MM:SS or HH:MM:SS (seconds must have two digits)")
    if len(parts) == 2:
        if not parts[0]:
            raise ValueError("Use MM:SS or HH:MM:SS (seconds must have two digits)")
        minutes, seconds = (int(part) for part in parts)
        return minutes * 60 + seconds
    if len(parts[1]) != 2 or int(parts[1]) > 59 or not parts[0]:
        raise ValueError("Use MM:SS or HH:MM:SS (seconds must have two digits)")
    hours, minutes, seconds = (int(part) for part in parts)
    return hours * 3600 + minutes * 60 + seconds


def validate_interval(start: str, end: str, maximum_seconds: int) -> tuple[int, int]:
    start_seconds = parse_timestamp(start)
    end_seconds = parse_timestamp(end)
    if end_seconds <= start_seconds:
        raise ValueError("End timestamp must be after start timestamp")
    if end_seconds - start_seconds > maximum_seconds:
        raise ValueError(f"Clip duration exceeds the {maximum_seconds // 60}-minute limit")
    return start_seconds, end_seconds


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
