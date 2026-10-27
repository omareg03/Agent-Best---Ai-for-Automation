#!/usr/bin/env python3
"""Create crisp 1080x1920 Manim overlay scenes from a package storyboard.

Requires Manim Community Edition only for rendering. This utility emits Python
source; it does not download assets or execute Manim. Run the generated scene with
`manim -pqh --fps 60 <generated.py> Block01` (or a specific block scene).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def safe(value: object, fallback: str = "") -> str:
    s = re.sub(r"\s+", " ", str(value or fallback)).strip()
    return s.replace("\\", "\\\\").replace('"', '\\"')


def generate(
    spec_path: Path,
    output: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 60,
    audio_dir: Path | None = None,
) -> Path:
    doc = json.loads(spec_path.read_text(encoding="utf-8"))
    blocks = doc.get("blocks", [])
    if not blocks:
        raise ValueError("storyboard has no blocks")
    scenes = []
    for i, block in enumerate(blocks, 1):
        bid = safe(block.get("id", f"block_{i:02d}"))
        title = safe(block.get("overlay_title") or block.get("title") or bid.replace("_", " ").title())
        detail = safe(block.get("overlay_detail") or block.get("location") or "")
        coord = safe(block.get("coordinates") or "")
        timecode = safe(block.get("timeline") or "")
        duration = float(block.get("duration_target_seconds", 5.0))
        if audio_dir is not None:
            from scripts.long_video_chain import probe_duration

            audio = audio_dir / block.get("audio", f"audio/{bid}.wav").split("audio/", 1)[-1]
            if not audio.is_file():
                raise FileNotFoundError(f"missing measured narration WAV for {bid}: {audio}")
            duration = probe_duration(audio)
        if duration <= 0:
            raise ValueError(f"invalid block duration for {bid}: {duration}")
        marker_code = (
            """        locator = VGroup(Circle(radius=0.18, color=YELLOW, stroke_width=3), Dot(color=YELLOW)).to_corner(UR, buff=0.35)
        self.add(locator)"""
            if coord
            else ""
        )
        gauge_code = ""
        if block.get("elevation_m") is not None:
            meters = float(block["elevation_m"])
            fill_h = min(2.4, max(0.05, 2.4 * meters / 150.0))
            gauge_code = f'''        gauge = Rectangle(width=0.24, height=2.5, color=WHITE, stroke_width=2).to_edge(LEFT, buff=0.55)
        fill = Rectangle(width=0.16, height={fill_h:.3f}, stroke_width=0, fill_color=YELLOW, fill_opacity=1).align_to(gauge, DOWN).move_to(gauge.get_bottom() + UP * {fill_h / 2:.3f})
        gauge_label = Text("{meters:g} m", font_size=24, color=YELLOW).next_to(gauge, RIGHT, buff=0.12)
        self.add(gauge, fill, gauge_label)'''
        scenes.append(f'''class Block{i:02d}(Scene):
    def construct(self):
        title = Text("{title}", font_size=42, weight=BOLD, color=WHITE).move_to(UP * 5.1)
        rule = Line(LEFT * 3.45, RIGHT * 3.45, color=YELLOW, stroke_width=4).next_to(title, DOWN, buff=0.18)
        detail = Text("{detail}", font_size=30, color=WHITE).next_to(rule, DOWN, buff=0.22)
        coord = Text("{coord}", font_size=28, color=YELLOW).next_to(detail, DOWN, buff=0.12)
        timeline = Text("{timecode}", font_size=26, color=WHITE).to_edge(DOWN, buff=0.75)
        bg = Rectangle(width=7.4, height=2.3, fill_color=BLACK, fill_opacity=0.76, stroke_opacity=0).move_to(UP * 4.5)
        self.add(bg, title, rule, detail, coord, timeline)
{marker_code}
{gauge_code}
        self.wait({duration:.6f})
''')
    source = f'''"""Generated factual overlay scenes. Verify all dates/coordinates against cited sources."""
from manim import *
import os

config.pixel_width = {width}
config.pixel_height = {height}
config.frame_rate = {fps}
config.frame_height = 14.0
config.background_color = "#14202A"

''' + "\n".join(scenes)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(source, encoding="utf-8")
    return output


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("storyboard", type=Path)
    p.add_argument("--output", type=Path, default=Path("manim_blocks_generated.py"))
    p.add_argument("--fps", type=int, choices=(30, 60), default=60)
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument(
        "--audio-dir",
        type=Path,
        default=None,
        help="directory holding per-block measured WAV files; binds each Manim scene to its actual audio duration",
    )
    a = p.parse_args()
    print(generate(a.storyboard, a.output, width=a.width, height=a.height, fps=a.fps, audio_dir=a.audio_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
