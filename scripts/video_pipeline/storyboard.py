"""Storyboard: the single source of truth for a video.

A storyboard is data, not prompts-in-a-script. It is validated before a single
GPU-second is spent, and hashed so the renderer can prove which version produced
which clip.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import StoryboardError

SCENE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,47}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,63}$")

MIN_TOTAL_SECONDS = 60.0      # below this it's a clip, not long-form
TARGET_TOTAL_SECONDS = 180.0  # 3 min
MAX_TOTAL_SECONDS = 900.0     # 15 min


@dataclass
class Scene:
    scene_id: str
    visual_prompt: str
    voiceover_text: str = ""
    camera_motion: str = "slow push in"
    duration: float | None = None          # requested seconds; None = derive from narration
    start_frame_prompt: str = ""
    end_frame_prompt: str = ""
    seed: int | None = None
    transition: str = "cut"                # cut | fade
    notes: str = ""

    def rendering_prompt(self, *, style_anchor: str = "", character_sheet: str = "") -> str:
        """Everything that must stay identical for this scene to be reproducible."""
        parts = [
            self.visual_prompt.strip(),
            f"Camera: {self.camera_motion.strip()}." if self.camera_motion.strip() else "",
            f"Style: {style_anchor.strip()}" if style_anchor.strip() else "",
            f"Character reference: {character_sheet.strip()}" if character_sheet.strip() else "",
        ]
        return "\n".join(p for p in parts if p)

    def prompt_hash(
        self, *, style_anchor: str = "", character_sheet: str = "",
        template_fingerprint: str | None = None,
    ) -> str:
        payload = {
            "visual_prompt": self.visual_prompt,
            "camera_motion": self.camera_motion,
            "start_frame_prompt": self.start_frame_prompt,
            "end_frame_prompt": self.end_frame_prompt,
            "seed": self.seed,
            "duration": self.duration,
            "style_anchor": style_anchor,
            "character_sheet": character_sheet,
            "voiceover_text": self.voiceover_text,
            "transition": self.transition,
            "prompt_template": template_fingerprint or prompt_template_fingerprint(),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def estimated_narration_seconds(self, words_per_minute: float = 150.0) -> float:
        words = max(1, len(self.voiceover_text.split()))
        return words / words_per_minute * 60.0


@dataclass
class Storyboard:
    title: str
    scenes: list[Scene]
    slug: str = ""
    logline: str = ""
    style_anchor: str = ""
    character_sheet_prompt: str = ""
    negative_prompt: str = ""
    voice: str = ""
    music: str = ""                     # optional path, relative to project root
    width: int = 1280
    height: int = 720
    fps: int = 24
    engine: str = ""                    # informational default; CLI overrides
    aspect_ratio: str = "16:9"
    language: str = "en"
    metadata: dict[str, Any] = field(default_factory=dict)

    # -- derived ----------------------------------------------------------
    @property
    def effective_slug(self) -> str:
        return self.slug or slugify(self.title)

    def scene_hashes(self, template_fingerprint: str | None = None) -> dict[str, str]:
        fingerprint = template_fingerprint or prompt_template_fingerprint()
        return {
            s.scene_id: s.prompt_hash(
                style_anchor=self.style_anchor,
                character_sheet=self.character_sheet_prompt,
                template_fingerprint=fingerprint,
            )
            for s in self.scenes
        }

    def storyboard_hash(self) -> str:
        payload = {
            "title": self.title,
            "style_anchor": self.style_anchor,
            "character_sheet_prompt": self.character_sheet_prompt,
            "negative_prompt": self.negative_prompt,
            "voice": self.voice,
            "format": [self.width, self.height, self.fps],
            "prompt_templates": prompt_template_fingerprint(),
            "scenes": self.scene_hashes(),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def registered_scenes(self, template_fingerprint: str | None = None) -> list[dict[str, Any]]:
        hashes = self.scene_hashes(template_fingerprint)
        return [
            {
                "scene_id": s.scene_id,
                "ordinal": index,
                "prompt_hash": hashes[s.scene_id],
                "seed": s.seed,
            }
            for index, s in enumerate(self.scenes)
        ]

    def estimated_duration(self, words_per_minute: float = 150.0) -> float:
        total = 0.0
        for scene in self.scenes:
            narration = scene.estimated_narration_seconds(words_per_minute)
            total += max(scene.duration or 0.0, narration)
        return round(total, 2)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["slug"] = self.effective_slug
        return data


def prompt_template_fingerprint() -> str:
    """Hash the prompt templates into the scene hash.

    Editing prompts/keyframe_pair.md changes every frame that follows, so it must
    invalidate renders exactly like editing a scene prompt does.
    """
    from .config import PROMPTS_DIR

    digest = hashlib.sha256()
    for name in ("character_sheet.md", "keyframe_pair.md", "style_anchor.md"):
        path = PROMPTS_DIR / name
        digest.update(path.read_bytes() if path.exists() else f"absent:{name}".encode())
    return digest.hexdigest()[:8]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "untitled")[:64]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_payload(data: dict[str, Any]) -> list[str]:
    """Explicit, dependency-free validation. Returns human-readable problems."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["storyboard must be a JSON object"]

    if not str(data.get("title", "")).strip():
        problems.append("title: required non-empty string")
    slug = data.get("slug")
    if slug is not None and not SLUG_RE.match(str(slug)):
        problems.append("slug: must be lowercase a-z, 0-9 and hyphens (<=64 chars)")

    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        problems.append("scenes: required non-empty array")
        return problems

    seen: set[str] = set()
    for index, raw in enumerate(scenes):
        where = f"scenes[{index}]"
        if not isinstance(raw, dict):
            problems.append(f"{where}: must be an object")
            continue
        scene_id = str(raw.get("scene_id", "")).strip()
        if not scene_id:
            problems.append(f"{where}.scene_id: required")
        elif not SCENE_ID_RE.match(scene_id):
            problems.append(f"{where}.scene_id: use letters, digits, _ or - (<=48 chars)")
        elif scene_id in seen:
            problems.append(f"{where}.scene_id: duplicate '{scene_id}'")
        else:
            seen.add(scene_id)

        if not str(raw.get("visual_prompt", "")).strip():
            problems.append(f"{where}.visual_prompt: required (this is what gets generated)")

        duration = raw.get("duration")
        if duration is not None:
            try:
                duration = float(duration)
            except (TypeError, ValueError):
                problems.append(f"{where}.duration: must be a number of seconds or null")
            else:
                if not (1.0 <= duration <= 60.0):
                    problems.append(f"{where}.duration: must be between 1 and 60 seconds")

        transition = raw.get("transition", "cut")
        if transition not in ("cut", "fade"):
            problems.append(f"{where}.transition: must be 'cut' or 'fade'")

        voiceover = raw.get("voiceover_text", "")
        if voiceover is not None and not isinstance(voiceover, str):
            problems.append(f"{where}.voiceover_text: must be a string")

    width, height = data.get("width", 1280), data.get("height", 720)
    for name, value in (("width", width), ("height", height)):
        if not isinstance(value, int) or value < 256 or value > 4096:
            problems.append(f"{name}: integer between 256 and 4096")
        elif value % 2:
            problems.append(f"{name}: must be even (H.264 yuv420p)")
    if isinstance(width, int) and isinstance(height, int) and width and height:
        if abs((width / height) - 16 / 9) > 0.02 and data.get("aspect_ratio", "16:9") == "16:9":
            problems.append("width/height: 16:9 requested but dimensions are not ~1.78")

    fps = data.get("fps", 24)
    if not isinstance(fps, int) or not (6 <= fps <= 60):
        problems.append("fps: integer between 6 and 60")

    return problems


def load(path: str | Path) -> Storyboard:
    p = Path(path)
    if not p.exists():
        raise StoryboardError(f"storyboard not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StoryboardError(
            f"invalid JSON in {p}: {exc.msg} (line {exc.lineno}, column {exc.colno})",
            hint="validate with: python -m scripts.video_pipeline.cli storyboard check <file>",
        ) from exc

    problems = validate_payload(data)
    if problems:
        raise StoryboardError(
            f"{len(problems)} storyboard problem(s):\n  - " + "\n  - ".join(problems),
            hint="see prompts/storyboard.schema.json for the contract",
        )

    scenes = [
        Scene(
            scene_id=str(raw["scene_id"]).strip(),
            visual_prompt=str(raw["visual_prompt"]).strip(),
            voiceover_text=str(raw.get("voiceover_text") or "").strip(),
            camera_motion=str(raw.get("camera_motion") or "slow push in").strip(),
            duration=float(raw["duration"]) if raw.get("duration") is not None else None,
            start_frame_prompt=str(raw.get("start_frame_prompt") or "").strip(),
            end_frame_prompt=str(raw.get("end_frame_prompt") or "").strip(),
            seed=raw.get("seed"),
            transition=str(raw.get("transition") or "cut"),
            notes=str(raw.get("notes") or ""),
        )
        for raw in data["scenes"]
    ]

    storyboard = Storyboard(
        title=str(data["title"]).strip(),
        scenes=scenes,
        slug=str(data.get("slug") or "").strip() or slugify(str(data["title"])),
        logline=str(data.get("logline") or ""),
        style_anchor=str(data.get("style_anchor") or ""),
        character_sheet_prompt=str(data.get("character_sheet_prompt") or ""),
        negative_prompt=str(data.get("negative_prompt") or ""),
        voice=str(data.get("voice") or ""),
        music=str(data.get("music") or ""),
        width=int(data.get("width", 1280)),
        height=int(data.get("height", 720)),
        fps=int(data.get("fps", 24)),
        engine=str(data.get("engine") or ""),
        aspect_ratio=str(data.get("aspect_ratio", "16:9")),
        language=str(data.get("language", "en")),
        metadata=dict(data.get("metadata") or {}),
    )
    return storyboard


def save(storyboard: Storyboard, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(storyboard.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def plan_summary(storyboard: Storyboard, *, words_per_minute: float = 150.0) -> dict[str, Any]:
    """Pre-flight report: durations, clip count, cost estimate. No generation."""
    rows = []
    total = 0.0
    for index, scene in enumerate(storyboard.scenes):
        narration = scene.estimated_narration_seconds(words_per_minute)
        target = max(scene.duration or 0.0, narration + 0.45)
        total += target
        rows.append(
            {
                "index": index + 1,
                "scene_id": scene.scene_id,
                "narration_est_s": round(narration, 2),
                "clip_target_s": round(target, 2),
                "words": len(scene.voiceover_text.split()),
                "hash": scene.prompt_hash(
                    style_anchor=storyboard.style_anchor,
                    character_sheet=storyboard.character_sheet_prompt,
                ),
            }
        )
    warnings = []
    if total < MIN_TOTAL_SECONDS:
        warnings.append(f"total ~{total:.0f}s is shorter than the long-form floor ({MIN_TOTAL_SECONDS:.0f}s)")
    if total > MAX_TOTAL_SECONDS:
        warnings.append(f"total ~{total:.0f}s exceeds the 15-minute ceiling; split into parts")
    return {
        "title": storyboard.title,
        "slug": storyboard.effective_slug,
        "scenes": rows,
        "scene_count": len(rows),
        "estimated_total_seconds": round(total, 2),
        "estimated_total_minutes": round(total / 60.0, 2),
        "warnings": warnings,
        "storyboard_hash": storyboard.storyboard_hash(),
    }
