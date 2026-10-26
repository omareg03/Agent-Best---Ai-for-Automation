"""Engine contract. The orchestrator must never know which backend it is talking to."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VideoRequest:
    scene_id: str
    prompt: str
    out_path: Path
    duration: float
    start_frame: Path | None = None     # mandatory for chaining
    end_frame: Path | None = None       # enables FLF2V (first-last-frame-to-video)
    negative_prompt: str = ""
    seed: int | None = None
    width: int = 1280
    height: int = 720
    fps: int = 24
    camera_motion: str = ""


@dataclass
class VideoResult:
    path: Path
    engine: str
    model: str
    duration: float
    cost_usd: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


class VideoEngine:
    name = "base"
    supports_last_frame = False
    requires_gpu = False

    def generate(self, request: VideoRequest) -> VideoResult:  # pragma: no cover - interface
        raise NotImplementedError

    def capabilities(self) -> dict[str, Any]:
        return {
            "engine": self.name,
            "supports_last_frame": self.supports_last_frame,
            "requires_gpu": self.requires_gpu,
        }

    def health(self) -> dict[str, Any]:
        return {"engine": self.name, "ok": True}
