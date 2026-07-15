from dataclasses import dataclass

from apps.api.app.services.subtitles import _caption_groups, write_ass


@dataclass
class Word:
    start: float
    end: float
    word: str


def test_caption_groups_are_short_and_timed() -> None:
    captions = _caption_groups(
        [
            Word(index * 0.3, (index + 1) * 0.3, word)
            for index, word in enumerate("These captions stay short and readable on a mobile screen".split())
        ]
    )
    assert len(captions) >= 2
    assert all(len(caption.text) <= 32 for caption in captions)
    assert all(caption.end > caption.start for caption in captions)


def test_vertical_ass_uses_large_bottom_safe_style(tmp_path) -> None:
    destination = tmp_path / "captions.ass"
    captions = _caption_groups([Word(0.0, 1.0, "Readable"), Word(1.0, 2.0, "caption")])
    write_ass(captions, destination, vertical=True)
    content = destination.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert "DejaVu Sans,88" in content
    assert ",240,1" in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.00" in content
