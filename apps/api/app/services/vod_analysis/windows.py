from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisWindow:
    index: int
    start: float
    end: float
    sample_start: float
    sample_end: float
    block_index: int


def generate_windows(
    duration: float,
    *,
    max_seconds: float,
    window_seconds: int,
    sample_seconds: float,
    block_seconds: int,
) -> list[AnalysisWindow]:
    if duration <= 0 or max_seconds <= 0:
        raise ValueError("Analysis duration must be positive")
    if not 10 <= window_seconds <= 300:
        raise ValueError("Window size must be between 10 and 300 seconds")
    if sample_seconds <= 0 or sample_seconds > window_seconds:
        raise ValueError("Audio sample must fit inside its logical window")
    if block_seconds < window_seconds:
        raise ValueError("Fetch block must contain at least one window")
    end_limit = min(float(duration), float(max_seconds))
    windows = []
    start = 0.0
    index = 0
    while start < end_limit:
        end = min(end_limit, start + window_seconds)
        actual_sample = min(sample_seconds, end - start)
        sample_start = start + max(0.0, (end - start - actual_sample) / 2)
        windows.append(
            AnalysisWindow(
                index=index,
                start=round(start, 3),
                end=round(end, 3),
                sample_start=round(sample_start, 3),
                sample_end=round(sample_start + actual_sample, 3),
                block_index=int(start // block_seconds),
            )
        )
        start = end
        index += 1
    return windows


def group_windows_by_block(windows: list[AnalysisWindow]) -> list[list[AnalysisWindow]]:
    blocks: list[list[AnalysisWindow]] = []
    for window in windows:
        if not blocks or blocks[-1][0].block_index != window.block_index:
            blocks.append([])
        blocks[-1].append(window)
    return blocks
