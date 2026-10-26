"""Central configuration. Every model id, path and default lives here (not in call sites)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError


def _find_repo_root(start: Path | None = None) -> Path:
    """Walk up until we find the repo marker (.git or pyproject)."""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists() or (candidate / "scripts" / "video_pipeline").is_dir():
            return candidate
    return Path.cwd()


REPO_ROOT: Path = _find_repo_root(Path(__file__).parent)

PROMPTS_DIR = REPO_ROOT / "prompts"
REGISTRY_DIR = REPO_ROOT / "registry"
WORKFLOWS_DIR = REPO_ROOT / "workflows"
DATABASE_DIR = REPO_ROOT / "database"
SCHEMA_PATH = DATABASE_DIR / "schema.sql"
PROJECTS_DIR = Path(os.environ.get("PIPELINE_PROJECTS_DIR", REPO_ROOT / "projects"))

# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 24
AUDIO_RATE = 48000
AUDIO_CHANNELS = 2
DEFAULT_TRANSITION = "cut"  # cut | fade(0.25s) -- fades only where continuity fails

# ---------------------------------------------------------------------------
# Model ids (verified 2026-10-26 against registry/tools.json; see PLAN.md)
# ---------------------------------------------------------------------------
GEMINI_API_BASE = "https://generativelanguage.googleapis.com"
GEMINI_API_VERSION = "v1"
# Nano Banana 2.1 -- GA 2026-10-06, $0.0336/img @1K. NO free API tier for images.
DEFAULT_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-nano-banana-2.1")
# Nano Banana 2 is deprecated and shuts down 2026-10-29. Kept only to detect+refuse.
DEPRECATED_IMAGE_MODELS = {
    "gemini-3.1-flash-image": "2026-10-29",
    "gemini-2.5-flash-image": "unscheduled (legacy)",
}
IMAGE_MODEL_COSTS_USD = {  # per image, standard tier, 1K
    "gemini-nano-banana-2.1": 0.0336,
    "gemini-3.1-flash-lite-image": 0.0336,
    "gemini-3.1-flash-image": 0.067,
    "gemini-3-pro-image": 0.134,
    "gemini-2.5-flash-image": 0.039,
}

DEFAULT_VIDEO_MODEL = os.environ.get("GEMINI_VIDEO_MODEL", "gemini-omni-1.1-flash")
VIDEO_MODEL_COST_USD_PER_SECOND = 0.10  # 720p, standard

DEFAULT_TTS_VOICE = os.environ.get("PIPELINE_TTS_VOICE", "af_heart")  # Kokoro voice
DEFAULT_EDGE_VOICE = os.environ.get("PIPELINE_EDGE_VOICE", "en-US-AriaNeural")

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
KOKORO_TTS_URL = os.environ.get("KOKORO_TTS_URL", "http://127.0.0.1:8880")

# ---------------------------------------------------------------------------
# Scene timing policy (narration-first; models never decide our duration)
# ---------------------------------------------------------------------------
MIN_SCENE_SECONDS = 2.0
MAX_SCENE_SECONDS = 20.0
NARRATION_TAIL_PAD = 0.45       # breathing room after the last syllable
CAPTION_LEAD_IN = 0.12
CAPTION_TAIL = 0.25

# Continuity gate: max dHash hamming distance between consecutive boundary frames.
# 64-bit dHash; 12 ~= "same shot, minor compression noise". Above this we refuse to
# publish a visible jump.
MAX_BOUNDARY_DHASH = 12
NEAR_BLACK_LUMA = 10.0          # frames darker than this are cut/black -- never chain them

# Retry policy for hosted APIs (Gemini 429/5xx is routine, not exceptional).
HTTP_RETRIES = 4
HTTP_BACKOFF_BASE = 2.0
HTTP_TIMEOUT = 180


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (no dependency). Existing env vars always win."""
    env_path = path or REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_secret(name: str, *, required: bool = False) -> str | None:
    load_dotenv()
    value = os.environ.get(name)
    if required and not value:
        raise ConfigError(
            f"{name} is not set",
            hint=f"export {name}=... (or put it in .env; .env is git-ignored)",
        )
    return value


@dataclass(frozen=True)
class ProjectPaths:
    """All artefact locations for one project. Created lazily, never committed."""

    root: Path

    @property
    def slug(self) -> str:
        return self.root.name

    @property
    def storyboard(self) -> Path:
        return self.root / "storyboard.json"

    @property
    def state_db(self) -> Path:
        return self.root / "state.db"

    @property
    def keyframes(self) -> Path:
        return self.root / "keyframes"

    @property
    def clips(self) -> Path:
        return self.root / "clips"

    @property
    def audio(self) -> Path:
        return self.root / "audio"

    @property
    def segments(self) -> Path:
        return self.root / "segments"

    @property
    def subtitles(self) -> Path:
        return self.root / "subtitles"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def renders(self) -> Path:
        return self.root / "renders"

    def ensure(self) -> "ProjectPaths":
        for directory in (
            self.root, self.keyframes, self.clips, self.audio,
            self.segments, self.subtitles, self.logs, self.renders,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def all_dirs(self) -> list[Path]:
        return [
            self.keyframes, self.clips, self.audio,
            self.segments, self.subtitles, self.logs, self.renders,
        ]


def project_paths(slug_or_path: str) -> ProjectPaths:
    candidate = Path(slug_or_path)
    if candidate.is_absolute() or str(candidate).startswith("projects/"):
        root = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    else:
        root = PROJECTS_DIR / slug_or_path
    return ProjectPaths(root=root)
