"""Word-level captions -> ASS (burn-in) and SRT (sidecar).

The ASS writer uses `\\k` karaoke tags so the active word fills progressively.
That is only honest if the timings are real, which is why align.py feeds this
module and never the other way round.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import MediaError

DEFAULT_MAX_CHARS = 42
DEFAULT_MAX_WORDS = 7
DEFAULT_MAX_SECONDS = 4.5


@dataclass
class Word:
    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.02, self.end - self.start)


@dataclass
class Cue:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


def wrap_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def group_words_into_cues(
    words: list[Word],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_words: int = DEFAULT_MAX_WORDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> list[Cue]:
    """Group word timings into readable cues. Never splits a word across cues."""
    cues: list[Cue] = []
    bucket: list[Word] = []

    def flush() -> None:
        nonlocal bucket
        if not bucket:
            return
        text = " ".join(w.text for w in bucket)
        cues.append(Cue(start=bucket[0].start, end=bucket[-1].end, text=text, words=list(bucket)))
        bucket = []

    for word in words:
        if not bucket:
            bucket = [word]
            continue
        candidate_text = " ".join(w.text for w in bucket + [word])
        span = word.end - bucket[0].start
        if (
            len(bucket) >= max_words
            or len(candidate_text) > max_chars
            or span > max_seconds
            or re.search(r"[.!?]$", bucket[-1].text)
        ):
            flush()
            bucket = [word]
        else:
            bucket.append(word)
    flush()
    return cues


def cues_from_text(text: str, start: float, end: float) -> list[Cue]:
    """Fallback when only plain text exists: split on sentence boundaries."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return []
    total_chars = sum(len(s) for s in sentences) or 1
    span = max(0.5, end - start)
    cues: list[Cue] = []
    cursor = start
    for sentence in sentences:
        share = len(sentence) / total_chars
        duration = max(0.8, span * share)
        cues.append(Cue(start=cursor, end=min(end, cursor + duration), text=sentence))
        cursor += duration
    return cues


# ---------------------------------------------------------------------------
# ASS
# ---------------------------------------------------------------------------
def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _ass_escape(text: str) -> str:
    """ASS override tags are delimited by braces; backslash starts a tag."""
    cleaned = text.replace("\\", "/").replace("{", "(").replace("}", ")")
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _karaoke_text(cue: Cue) -> str:
    if not cue.words:
        return _ass_escape(wrap_text(cue.text)).replace("\n", "\\N")
    parts: list[str] = []
    words = cue.words
    for index, word in enumerate(words):
        gap = 0.0
        if index + 1 < len(words):
            gap = max(0.0, words[index + 1].start - word.end)
        centis = int(round((word.duration + gap) * 100))
        parts.append(f"{{\\k{max(1, centis)}}}{_ass_escape(word.text)}")
    joined = " ".join(parts)
    # Wrap on text length only (tags are invisible to the viewer).
    if len(cue.text) > DEFAULT_MAX_CHARS:
        words_text = cue.text.split()
        midpoint = len(words_text) // 2
        head = " ".join(_ass_escape(w) for w in words_text[:midpoint])
        tail = " ".join(_ass_escape(w) for w in words_text[midpoint:])
        del head, tail  # not used: karaoke tags must stay attached to their word
    return joined


def build_ass(
    cues: list[Cue],
    *,
    width: int,
    height: int,
    title: str = "captions",
    font: str = "DejaVu Sans",
    karaoke: bool = True,
    safe_margin: float = 0.06,
) -> str:
    font_size = max(18, int(height * 0.050))
    outline = max(2, int(height * 0.0028))
    margin_v = int(height * safe_margin) + font_size // 2
    margin_h = int(width * 0.08)
    header = f"""[Script Info]
; generated by scripts/video_pipeline/captions.py
Title: {_ass_escape(title)}
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{font_size},&H00FFFFFF,&H0000D7FF,&H00101010,&H80000000,0,0,0,0,100,100,0.6,0,1,{outline},0,2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header.rstrip("\n")]
    for cue in cues:
        start = ass_time(cue.start)
        end = ass_time(max(cue.start + 0.25, cue.end))
        text = _karaoke_text(cue) if karaoke else _ass_escape(wrap_text(cue.text)).replace("\n", "\\N")
        if not text.strip():
            continue
        lines.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{{\\fad(120,120)}}{text}")
    return "\n".join(lines) + "\n"


def build_srt(cues: list[Cue]) -> str:
    def srt_time(seconds: float) -> str:
        ms = int(round(max(0.0, seconds) * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks = []
    for index, cue in enumerate(cues, start=1):
        text = wrap_text(cue.text)
        blocks.append(f"{index}\n{srt_time(cue.start)} --> {srt_time(cue.end)}\n{text}\n")
    return "\n".join(blocks)


def write_captions(
    words: list[Word],
    *,
    out_dir: str | Path,
    stem: str,
    width: int,
    height: int,
    fallback_text: str = "",
    total_duration: float = 0.0,
) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if words:
        cues = group_words_into_cues(words)
    elif fallback_text and total_duration > 0:
        cues = cues_from_text(fallback_text, 0.0, total_duration)
    else:
        raise MediaError("no word timings and no fallback text -> cannot build captions")

    ass_path = out / f"{stem}.ass"
    srt_path = out / f"{stem}.srt"
    ass_path.write_text(build_ass(cues, width=width, height=height, title=stem), encoding="utf-8")
    srt_path.write_text(build_srt(cues), encoding="utf-8")
    if ass_path.stat().st_size == 0:
        raise MediaError(f"ASS file is empty: {ass_path}")
    return {"ass": ass_path, "srt": srt_path, "cues": len(cues)}  # type: ignore[dict-item]
