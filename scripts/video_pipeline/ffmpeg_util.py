"""FFmpeg/FFprobe resolution, media probing, and the image fingerprints used as
continuity evidence.

Why this module exists:
  * The sandbox has **no system ffmpeg**, so every call resolves through
    env(FFMPEG_BIN) -> PATH -> imageio-ffmpeg.
  * The static ffmpeg build has **no ffprobe**, so `probe()` degrades to parsing
    `ffmpeg -i` stderr instead of raising.
  * Continuity is a *measured* property here, not a promise: dHash + luma.
"""

from __future__ import annotations

import functools
import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import FFmpegError, MediaError


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    env = os_environ("FFMPEG_BIN")
    if env:
        if not Path(env).exists():
            raise MediaError(f"FFMPEG_BIN points to a missing file: {env}")
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # pragma: no cover - depends on environment
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        raise MediaError(
            "ffmpeg not found",
            hint=(
                "install ffmpeg (apt-get install -y ffmpeg) OR `pip install imageio-ffmpeg`, "
                "OR set FFMPEG_BIN=/path/to/ffmpeg"
            ),
        ) from exc


@functools.lru_cache(maxsize=1)
def ffprobe_bin() -> str | None:
    env = os_environ("FFPROBE_BIN")
    if env and Path(env).exists():
        return env
    return shutil.which("ffprobe")


def os_environ(key: str) -> str | None:
    import os

    return os.environ.get(key)


# ---------------------------------------------------------------------------
# Process execution
# ---------------------------------------------------------------------------
def run_ffmpeg(
    args: list[str], *, check: bool = True, timeout: int = 1800, cwd: str | None = None
) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if check and proc.returncode != 0:
        raise FFmpegError(
            f"ffmpeg failed (exit {proc.returncode})",
            command=cmd,
            stderr=proc.stderr,
        )
    return proc


def run_capture(cmd: list[str], *, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise MediaError(
            f"command failed ({proc.returncode}): {' '.join(cmd[:4])} ...",
            hint=(proc.stderr or "").strip().splitlines()[-1] if proc.stderr else "",
        )
    return proc


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------
@dataclass
class MediaInfo:
    path: Path
    duration: float
    width: int = 0
    height: int = 0
    fps: float = 0.0
    vcodec: str = ""
    acodec: str = ""
    has_video: bool = False
    has_audio: bool = False
    size_bytes: int = 0

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "duration": round(self.duration, 3),
            "width": self.width,
            "height": self.height,
            "fps": round(self.fps, 3),
            "vcodec": self.vcodec,
            "acodec": self.acodec,
            "has_video": self.has_video,
            "has_audio": self.has_audio,
            "size_bytes": self.size_bytes,
        }


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_RE = re.compile(r"Stream #\d+:\d+.*?: Video:\s*([a-zA-Z0-9_\-]+)")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+.*?: Audio:\s*([a-zA-Z0-9_\-]+)")
_SIZE_RE = re.compile(r"(?<![\d.])(\d{2,5})x(\d{2,5})(?!\d)")
_FPS_RE = re.compile(r"([\d.]+)\s*fps")
_HZ_RE = re.compile(r"(\d+)\s*Hz")


def probe(path: str | Path) -> MediaInfo:
    """Duration/dimensions/codecs. Works with ffprobe, or without it."""
    p = Path(path)
    if not p.exists():
        raise MediaError(f"cannot probe missing file: {p}")
    if p.stat().st_size == 0:
        raise MediaError(f"cannot probe zero-byte file: {p}")

    info = MediaInfo(path=p, duration=0.0, size_bytes=p.stat().st_size)
    probe_bin = ffprobe_bin()
    stderr = ""

    if probe_bin:
        proc = run_capture(
            [
                probe_bin, "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
                "-of", "default=noprint_wrappers=1", str(p),
            ],
            check=False,
        )
        text = proc.stdout
        for line in text.splitlines():
            key, _, value = line.partition("=")
            if key == "duration":
                try:
                    info.duration = float(value)
                except ValueError:
                    pass
            elif key == "codec_name" and not info.vcodec and value:
                info.vcodec = value
            elif key == "width" and value.isdigit():
                info.width = int(value)
            elif key == "height" and value.isdigit():
                info.height = int(value)
            elif key == "r_frame_rate" and "/" in value:
                num, _, den = value.partition("/")
                try:
                    info.fps = float(num) / float(den or 1)
                except (ValueError, ZeroDivisionError):
                    pass
        info.has_video = info.width > 0 and info.height > 0
        info.has_audio = "codec_type=audio" in text
        if info.has_video and not info.vcodec:
            info.vcodec = "unknown"
        if info.duration > 0:
            return info
    else:
        proc = run_ffmpeg(["-i", str(p)], check=False)
        stderr = proc.stderr or ""

    if not stderr:  # ffprobe existed but gave nothing useful -> fall back
        stderr = (run_ffmpeg(["-i", str(p)], check=False).stderr or "")

    match = _DUR_RE.search(stderr)
    if match:
        hours, minutes, seconds = match.groups()
        info.duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    video_line = next((ln for ln in stderr.splitlines() if "Video:" in ln), "")
    if video_line:
        info.has_video = True
        codec = _VIDEO_RE.search(video_line)
        info.vcodec = codec.group(1) if codec else "unknown"
        dims = _SIZE_RE.search(video_line)
        if dims:
            info.width, info.height = int(dims.group(1)), int(dims.group(2))
        fps = _FPS_RE.search(video_line)
        if fps:
            try:
                info.fps = float(fps.group(1))
            except ValueError:
                pass
    info.has_audio = any("Audio:" in ln for ln in stderr.splitlines())
    if info.has_audio:
        audio_line = next(ln for ln in stderr.splitlines() if "Audio:" in ln)
        codec = _AUDIO_RE.search(audio_line)
        info.acodec = codec.group(1) if codec else "unknown"
    return info


def duration_of(path: str | Path) -> float:
    return probe(path).duration


# ---------------------------------------------------------------------------
# Artefact hygiene
# ---------------------------------------------------------------------------
def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def assert_artifact(path: str | Path, *, min_bytes: int = 1024, kind: str = "artifact") -> Path:
    """The verification gate: a render is not 'done' until this passes."""
    p = Path(path)
    if not p.exists():
        raise MediaError(f"{kind} missing: {p}")
    size = p.stat().st_size
    if size < min_bytes:
        raise MediaError(f"{kind} suspiciously small ({size} bytes < {min_bytes}): {p}")
    return p


def human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


# ---------------------------------------------------------------------------
# Frame fingerprints (continuity evidence)
# ---------------------------------------------------------------------------
def _pil_image(path: str | Path):
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise MediaError(
            "Pillow is required for continuity checks",
            hint="pip install pillow",
        ) from exc
    image = Image.open(path)
    return image.convert("L")


def _pixel_values(image) -> list[int]:
    """Pillow 12 deprecated getdata(); Pillow 14 removes it. Support both."""
    getter = getattr(image, "get_flattened_data", None)
    return list(getter() if callable(getter) else image.getdata())


def mean_luma(path: str | Path) -> float:
    """0-255 average brightness. Used to reject black/cut frames from chaining."""
    image = _pil_image(path)
    pixels = _pixel_values(image)
    if not pixels:
        return 0.0
    return sum(pixels) / len(pixels)


def dhash(path: str | Path, hash_size: int = 8) -> int:
    """Difference hash as an int (64 bits at hash_size=8). Stable across re-encodes."""
    image = _pil_image(path).resize((hash_size + 1, hash_size), resample=1)  # Resampling.LANCZOS
    pixels = _pixel_values(image)
    width = hash_size + 1
    bits = 0
    index = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * width + col]
            right = pixels[row * width + col + 1]
            bits |= (1 if left > right else 0) << index
            index += 1
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def boundary_distance(start_frame: str | Path, end_frame: str | Path) -> int:
    """dHash distance between two boundary frames (0 = identical)."""
    return hamming(dhash(start_frame), dhash(end_frame))


# ---------------------------------------------------------------------------
# concat demuxer helpers
# ---------------------------------------------------------------------------
def _concat_escape(path: Path) -> str:
    # ffmpeg concat demuxer: single-quoted, embedded quote -> '\''
    return "'" + str(path.resolve()).replace("'", "'\\''") + "'"


def write_concat_file(paths: list[Path], out_file: Path) -> Path:
    if not paths:
        raise MediaError("cannot build a concat list from zero files")
    for p in paths:
        if not p.exists():
            raise MediaError(f"segment listed for concat does not exist: {p}")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    lines = ["ffconcat version 1.0"]
    lines += [f"file {_concat_escape(p)}" for p in paths]
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_file


def even(n: int) -> int:
    """H.264/yuv420p requires even dimensions."""
    return n - (n % 2)


def crop_filter(width: int, height: int) -> str:
    """Cover-fit any input into WxH without distortion (letterbox-free)."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
