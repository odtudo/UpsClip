from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class SilenceInterval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def generate_edit_plan(
    source_duration: float,
    silences: Iterable[SilenceInterval],
    *,
    remove_silences: bool,
    minimum_silence: float = 1.2,
    remove_after: float = 2.5,
    padding: float = 0.2,
) -> dict:
    removals: list[tuple[float, float]] = []
    if remove_silences:
        for silence in sorted(silences, key=lambda item: item.start):
            start = max(0.0, silence.start)
            end = min(source_duration, silence.end)
            duration = end - start
            if duration < minimum_silence:
                continue
            retained = padding * 2 if duration > remove_after else max(padding * 2, 0.8)
            remove_duration = duration - retained
            if remove_duration <= 0.05:
                continue
            cut_start = start + retained / 2
            cut_end = end - retained / 2
            if removals and cut_start <= removals[-1][1]:
                removals[-1] = (removals[-1][0], max(removals[-1][1], cut_end))
            else:
                removals.append((cut_start, cut_end))

    segments: list[dict[str, float]] = []
    cursor = 0.0
    output_cursor = 0.0
    for cut_start, cut_end in removals:
        if cut_start > cursor + 0.01:
            segments.append(
                {
                    "source_start": round(cursor, 3),
                    "source_end": round(cut_start, 3),
                    "output_start": round(output_cursor, 3),
                }
            )
            output_cursor += cut_start - cursor
        cursor = max(cursor, cut_end)
    if cursor < source_duration - 0.01:
        segments.append(
            {
                "source_start": round(cursor, 3),
                "source_end": round(source_duration, 3),
                "output_start": round(output_cursor, 3),
            }
        )
    if not segments and source_duration > 0:
        segments = [{"source_start": 0.0, "source_end": round(source_duration, 3), "output_start": 0.0}]

    output_duration = sum(item["source_end"] - item["source_start"] for item in segments)
    return {
        "source_duration": round(source_duration, 3),
        "output_duration": round(output_duration, 3),
        "silences": [asdict(item) for item in silences],
        "removed_intervals": [
            {"source_start": round(start, 3), "source_end": round(end, 3)} for start, end in removals
        ],
        "segments": segments,
    }
