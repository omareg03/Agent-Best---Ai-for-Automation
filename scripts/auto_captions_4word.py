#!/usr/bin/env python3
"""Generate centered ASS captions with no more than four words per cue.

Timing is deterministically estimated from the known narration span, weighted by
word count. For publish-ready subtitles, replace estimates with WhisperX forced
alignment and still retain the four-word grouping policy.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def _ass_time(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, centis = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{centis:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ")


def cues(words: list[str], start: float, duration: float, max_words: int = 4) -> list[Cue]:
    if max_words < 1 or max_words > 4:
        raise ValueError("max_words must be in 1..4")
    words = [w.strip() for w in words if w.strip()]
    if not words or duration <= 0:
        return []
    groups = [words[i : i + max_words] for i in range(0, len(words), max_words)]
    # Weighted by words, so longer groups occupy proportionally more time.
    weights = [len(group) for group in groups]
    total_weight = sum(weights)
    out: list[Cue] = []
    cursor = start
    for i, (group, weight) in enumerate(zip(groups, weights, strict=True)):
        end = start + duration if i == len(groups) - 1 else cursor + duration * weight / total_weight
        out.append(Cue(cursor, end, " ".join(group)))
        cursor = end
    return out


def write(path: Path, all_cues: list[Cue], *, width: int = 1080, height: int = 1920) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H00FFFFFF,&H0000FFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,5,1,5,48,48,240,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cue in all_cues:
        if cue.end <= cue.start:
            continue
        lines.append(
            f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Default,,0,0,0,,{_escape(cue.text)}\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("text", help="caption text")
    p.add_argument("--duration", required=True, type=float)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--start", type=float, default=0.0)
    a = p.parse_args()
    write(a.output, cues(a.text.split(), a.start, a.duration))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
