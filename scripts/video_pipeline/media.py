"""Deterministic FFmpeg operations: fit, mux, concat, loudness, duck, burn-in.

Every function here is a pure media transform with an explicit contract. No model
calls, no network. This is the layer that makes an AI video *watchable*:

  * duration drift    -> fit_duration()      (narration decides length, not the model)
  * seams             -> extract_last_clean_frame() + continuity assertions
  * loudness chaos    -> loudnorm_two_pass() (EBU R128, -16 LUFS for web)
  * music masking VO  -> mix_music()         (sidechain ducking, not naive amix)
  * caption drift     -> burn_subtitles()    (ASS from word-level timings)
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from .config import AUDIO_CHANNELS, AUDIO_RATE, MAX_BOUNDARY_DHASH, NEAR_BLACK_LUMA
from .errors import MediaError, VerificationError
from .ffmpeg_util import (
    assert_artifact,
    boundary_distance,
    crop_filter,
    mean_luma,
    probe,
    run_ffmpeg,
    sha256_file,
    write_concat_file,
)

X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
MP4 = ["-movflags", "+faststart"]


def encode_args(fps: int) -> list[str]:
    """Encoder args with an EXPLICIT output rate.

    Verified on FFmpeg 7.0.2: a filtergraph ending in `setpts=PTS-STARTPTS`
    re-times the output to 25 fps even when `fps=12` precedes it. Relying on the
    filter alone silently ships the wrong cadence, so the rate is set on the
    encoder and then asserted.
    """
    return ["-r", str(int(fps)), *X264, *MP4]


def assert_format(path: str | Path, *, width: int, height: int, fps: int, tolerance: float = 0.6) -> None:
    info = probe(path)
    if (info.width, info.height) != (width, height):
        raise MediaError(f"{Path(path).name}: expected {width}x{height}, got {info.width}x{info.height}")
    if info.fps and abs(info.fps - fps) > tolerance:
        raise MediaError(f"{Path(path).name}: expected {fps} fps, got {info.fps:.2f} fps")
AAC = ["-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS)]


def _out_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Video fitting: the duration policy
# ---------------------------------------------------------------------------
def normalize_clip(
    src: str | Path, dst: str | Path, *, width: int, height: int, fps: int, drop_audio: bool = True
) -> Path:
    """Re-encode any input into the project's uniform video contract."""
    src, dst = Path(src), _out_png(Path(dst))
    vf = f"{crop_filter(width, height)},fps={fps},setpts=PTS-STARTPTS"
    args = ["-i", str(src), "-vf", vf, *encode_args(fps)]
    args += ["-an"] if drop_audio else ["-c:a", "aac"]
    run_ffmpeg([*args, str(dst)])
    return assert_artifact(dst, kind="normalized clip")


def fit_duration(
    src: str | Path,
    dst: str | Path,
    seconds: float,
    *,
    mode: str = "hold",
    width: int,
    height: int,
    fps: int,
) -> Path:
    """Force a clip to an exact duration without touching audio.

    mode='hold'      freeze the final frame (safest, invisible on slow shots)
    mode='pingpong'  play forward then backward (only for clips <= 8 s: reverse
                     buffers every frame in RAM)
    mode='trim'      only shorten; never pad
    """
    src, dst = Path(src), _out_png(Path(dst))
    info = probe(src)
    if info.duration <= 0:
        raise MediaError(f"cannot fit a zero-duration clip: {src}")
    seconds = max(0.5, round(float(seconds), 3))
    pad = max(0.0, seconds - info.duration)
    base = f"{crop_filter(width, height)},fps={fps}"

    if info.duration >= seconds - 0.02:
        vf = f"{base},trim=duration={seconds},setpts=PTS-STARTPTS"
        run_ffmpeg(["-i", str(src), "-vf", vf, *encode_args(fps), "-an", str(dst)])
    elif mode == "pingpong" and info.duration <= 8.0 and pad < 8.0:
        graph = (
            f"[0:v]{base},split=2[a][b];"
            f"[b]reverse[r];"
            f"[a][r]concat=n=2:v=1:a=0,trim=duration={seconds},setpts=PTS-STARTPTS[v]"
        )
        run_ffmpeg(
            ["-i", str(src), "-filter_complex", graph, "-map", "[v]", *encode_args(fps), "-an", str(dst)]
        )
    elif mode == "trim":
        vf = f"{base},trim=duration={seconds},setpts=PTS-STARTPTS"
        run_ffmpeg(["-i", str(src), "-vf", vf, *encode_args(fps), "-an", str(dst)])
    else:  # hold (default) -- also the fallback for trim/pingpong when padding is needed
        vf = (
            f"{base},tpad=stop_mode=clone:stop_duration={pad + 0.5:.3f},"
            f"trim=duration={seconds},setpts=PTS-STARTPTS"
        )
        run_ffmpeg(["-i", str(src), "-vf", vf, *encode_args(fps), "-an", str(dst)])

    assert_format(dst, width=width, height=height, fps=fps)
    result = probe(dst)
    if abs(result.duration - seconds) > 0.12:
        raise MediaError(
            f"fit_duration produced {result.duration:.2f}s, expected {seconds:.2f}s ({dst.name})"
        )
    return assert_artifact(dst, kind="fitted clip")


def apply_edge_fades(src: str | Path, dst: str | Path, *, fade: float = 0.25, fps: int = 24) -> Path:
    """Dip-to-black transition. Used only where continuity *cannot* be guaranteed."""
    src, dst = Path(src), _out_png(Path(dst))
    duration = probe(src).duration
    fade = min(fade, max(0.05, duration / 4))
    vf = f"fade=t=in:st=0:d={fade:.2f},fade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.2f}"
    run_ffmpeg(["-i", str(src), "-vf", vf, *encode_args(fps), "-an", str(dst)])
    return assert_artifact(dst, kind="faded clip")


# ---------------------------------------------------------------------------
# Audio muxing
# ---------------------------------------------------------------------------
def mux_audio(
    video: str | Path, audio: str | Path, dst: str | Path, *, seconds: float, fade_out: float = 0.15
) -> Path:
    """Attach narration to a fitted clip, padded/trimmed to exactly `seconds`."""
    video, audio, dst = Path(video), Path(audio), _out_png(Path(dst))
    seconds = round(float(seconds), 3)
    af = (
        f"aresample={AUDIO_RATE},"
        f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"apad=whole_dur={seconds},atrim=0:{seconds}"
    )
    if fade_out > 0 and seconds > fade_out * 2:
        af += f",afade=t=out:st={seconds - fade_out:.3f}:d={fade_out:.2f}"
    args = [
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", *AAC, "-af", af,
        "-t", f"{seconds:.3f}", "-shortest", *MP4, str(dst),
    ]
    run_ffmpeg(args)
    info = probe(dst)
    if not info.has_audio:
        raise MediaError(f"segment has no audio track after mux: {dst}")
    if abs(info.duration - seconds) > 0.25:
        raise MediaError(f"segment is {info.duration:.2f}s, expected {seconds:.2f}s ({dst.name})")
    return assert_artifact(dst, kind="scene segment")


def silence(seconds: float, dst: str | Path) -> Path:
    """Silent track in the container the caller asked for.

    AAC inside a .wav is not a WAV: the output has no RIFF payload and fails
    downstream muxing. Match the codec to the extension.
    """
    dst = _out_png(Path(dst))
    if dst.suffix.lower() == ".wav":
        codec = ["-c:a", "pcm_s16le", "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS)]
    else:
        codec = list(AAC)
    run_ffmpeg(
        [
            "-f", "lavfi", "-i",
            f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
            "-t", f"{max(0.2, seconds):.3f}", *codec, str(dst),
        ]
    )
    return assert_artifact(dst, kind="silence")


# ---------------------------------------------------------------------------
# Concatenation
# ---------------------------------------------------------------------------
def concat_segments(
    segments: list[Path],
    dst: str | Path,
    *,
    fps: int,
    width: int,
    height: int,
    expected_duration: float | None = None,
) -> Path:
    """Join scene segments. Stream-copy first (fast); re-encode only if it drifts."""
    if not segments:
        raise MediaError("no segments to concatenate")
    dst = _out_png(Path(dst))
    list_file = dst.parent / f".{dst.stem}_concat.txt"
    write_concat_file(segments, list_file)

    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", *MP4, str(dst)])
    ok = True
    try:
        info = probe(dst)
        if info.duration <= 0:
            ok = False
        elif expected_duration is not None:
            ok = abs(info.duration - expected_duration) <= max(0.75, expected_duration * 0.02)
    except MediaError:
        ok = False

    if not ok:
        # Deterministic fallback: full re-encode through the concat filter.
        run_ffmpeg(
            [
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-vf", f"{crop_filter(width, height)},fps={fps}", *encode_args(fps), *AAC, str(dst),
            ]
        )
    list_file.unlink(missing_ok=True)
    return assert_artifact(dst, kind="concatenated body")


# ---------------------------------------------------------------------------
# Loudness + music
# ---------------------------------------------------------------------------
_LOUDNORM_RE = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.DOTALL)


def loudnorm_two_pass(
    src: str | Path, dst: str | Path, *, target_i: float = -16.0, tp: float = -1.5, lra: float = 11.0
) -> Path:
    """EBU R128 two-pass normalisation. Platforms punish inconsistent loudness."""
    src, dst = Path(src), _out_png(Path(dst))
    measure = run_ffmpeg(
        [
            "-i", str(src), "-map", "0:a:0",
            "-af", f"loudnorm=I={target_i}:TP={tp}:LRA={lra}:print_format=json",
            "-f", "null", "-",
        ],
        check=False,
    )
    stderr = measure.stderr or ""
    match = _LOUDNORM_RE.search(stderr)
    if not match:
        # Single-pass fallback keeps the pipeline moving and says so.
        run_ffmpeg(
            ["-i", str(src), "-map", "0:v?", "-map", "0:a:0", "-c:v", "copy",
             "-af", f"loudnorm=I={target_i}:TP={tp}:LRA={lra}", *AAC, *MP4, str(dst)]
        )
        return assert_artifact(dst, kind="normalised master")

    stats = json.loads(match.group(0))
    af = (
        f"loudnorm=I={target_i}:TP={tp}:LRA={lra}"
        f":measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
        f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}:linear=true:print_format=summary"
    )
    run_ffmpeg(
        ["-i", str(src), "-map", "0:v?", "-map", "0:a:0", "-c:v", "copy", "-af", af, *AAC, *MP4, str(dst)]
    )
    return assert_artifact(dst, kind="normalised master")


def mix_music(
    video: str | Path,
    music: str | Path,
    dst: str | Path,
    *,
    music_gain_db: float = -17.0,
    duck: bool = True,
) -> Path:
    """Bed music under narration with sidechain ducking (voice always wins)."""
    video, music, dst = Path(video), Path(music), _out_png(Path(dst))
    if not Path(music).exists():
        raise MediaError(f"music file not found: {music}")
    seconds = probe(video).duration
    fmt = (
        f"aformat=sample_fmts=fltp:sample_rates={AUDIO_RATE}:"
        f"channel_layouts=stereo"
    )
    if duck:
        graph = (
            f"[1:a]{fmt},volume={music_gain_db}dB[bg];"
            f"[0:a]{fmt}[vo];"
            f"[bg][vo]sidechaincompress=threshold=0.02:ratio=8:attack=5:release=350:makeup=1[duck];"
            f"[vo][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
        )
    else:
        graph = (
            f"[1:a]{fmt},volume={music_gain_db}dB[bg];"
            f"[0:a]{fmt}[vo];[vo][bg]amix=inputs=2:duration=first:normalize=0[a]"
        )
    run_ffmpeg(
        [
            "-i", str(video), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex", graph, "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", *AAC, "-t", f"{seconds:.3f}", *MP4, str(dst),
        ]
    )
    return assert_artifact(dst, kind="music-mixed master")


# ---------------------------------------------------------------------------
# Subtitles
# ---------------------------------------------------------------------------
def burn_subtitles(
    src: str | Path, subs: str | Path, dst: str | Path, *,
    fonts_dir: str | Path | None = None, fps: int | None = None,
) -> Path:
    """Burn an ASS file. Runs with cwd=subtitle dir to dodge filtergraph escaping bugs."""
    src, subs, dst = Path(src).resolve(), Path(subs).resolve(), Path(dst).resolve()
    if not subs.exists():
        raise MediaError(f"subtitle file not found: {subs}")
    filter_expr = f"ass={subs.name}"
    if fonts_dir:
        filter_expr += f":fontsdir={Path(fonts_dir).name}"
    rate = ["-r", str(int(fps))] if fps else []
    proc = run_ffmpeg(
        ["-i", str(src), "-vf", filter_expr, *X264, *rate, "-c:a", "copy", *MP4, str(dst)],
        check=False,
        cwd=str(subs.parent),
    )
    if proc.returncode != 0:
        stderr = proc.stderr or ""
        if "No such filter" in stderr and "ass" in stderr:
            raise MediaError(
                "this ffmpeg build has no libass -> cannot burn subtitles",
                hint="install a full ffmpeg (apt-get install -y ffmpeg) or ship the .ass/.srt as a sidecar",
            )
        raise MediaError("subtitle burn-in failed", hint=stderr.strip().splitlines()[-1] if stderr else "")
    return assert_artifact(dst, kind="subtitled master")


# ---------------------------------------------------------------------------
# Frame extraction: the seam killer
# ---------------------------------------------------------------------------
def _extract_window(clip: Path, directory: Path, *, window: float, fps: int = 10, limit: int = 10) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    duration = probe(clip).duration
    start = max(0.0, duration - window)
    run_ffmpeg(
        [
            "-ss", f"{start:.3f}", "-i", str(clip),
            "-vf", f"fps={fps}", "-frames:v", str(limit), "-q:v", "2",
            str(directory / "f_%03d.png"),
        ],
        check=False,
    )
    return sorted(directory.glob("f_*.png"))


def extract_last_clean_frame(clip: str | Path, out_png: str | Path, *, window: float = 0.9) -> Path:
    """Extract a *usable* last frame for keyframe chaining.

    Naive `-sseof -0.04` fails in the real world: clips often end on a fade or a
    black frame, and chaining that frame destroys the next shot. We sample a short
    tail, discard near-black frames, and take the last surviving one.
    """
    clip, out = Path(clip), _out_png(Path(out_png))
    if not clip.exists():
        raise MediaError(f"cannot extract a frame from missing clip: {clip}")
    with tempfile.TemporaryDirectory(prefix="lastframe_") as tmp:
        tmpdir = Path(tmp)
        candidates = _extract_window(clip, tmpdir / "a", window=window)
        if not candidates:
            candidates = _extract_window(clip, tmpdir / "b", window=max(window * 3, 2.5), fps=6, limit=12)
        if not candidates:
            raise MediaError(
                f"no frames decodable from {clip.name}",
                hint="the clip is corrupt or shorter than one frame; re-render it",
            )
        usable = [f for f in candidates if mean_luma(f) >= NEAR_BLACK_LUMA]
        if not usable:
            darkest = max(candidates, key=mean_luma)
            luma = mean_luma(darkest)
            raise MediaError(
                f"{clip.name} ends in black (max luma {luma:.1f} < {NEAR_BLACK_LUMA})",
                hint="chaining this frame would produce a black flash; add a fade-to-scene in the prompt",
            )
        chosen = usable[-1]
        shutil.copyfile(chosen, out)
    return assert_artifact(out, kind="last clean frame")


def extract_first_frame(clip: str | Path, out_png: str | Path) -> Path:
    clip, out = Path(clip), _out_png(Path(out_png))
    run_ffmpeg(["-i", str(clip), "-frames:v", "1", "-q:v", "2", str(out)])
    return assert_artifact(out, kind="first frame")


def check_boundary(
    start_frame: str | Path,
    clip: str | Path,
    *,
    max_distance: int = MAX_BOUNDARY_DHASH,
    label: str = "",
) -> tuple[int, bool]:
    """Measure the seam between the frame we conditioned on and the clip's frame 0."""
    with tempfile.TemporaryDirectory(prefix="boundary_") as tmp:
        first = extract_first_frame(clip, Path(tmp) / "first.png")
        distance = boundary_distance(start_frame, first)
    ok = distance <= max_distance
    if not ok:
        raise VerificationError(
            f"continuity break{' at ' + label if label else ''}: boundary dHash {distance} > {max_distance}",
            hint=(
                "the engine ignored the first-frame conditioning. Either switch to a FLF2V graph, "
                "or re-run this scene with a stronger start-frame prompt"
            ),
        )
    return distance, ok


# ---------------------------------------------------------------------------
# Extras
# ---------------------------------------------------------------------------
def thumbnail(src: str | Path, dst: str | Path, *, at_ratio: float = 0.08) -> Path:
    src, dst = Path(src), _out_png(Path(dst))
    position = max(0.0, probe(src).duration * at_ratio)
    run_ffmpeg(["-ss", f"{position:.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dst)])
    return assert_artifact(dst, kind="thumbnail", min_bytes=512)


def file_fingerprint(path: str | Path) -> dict[str, object]:
    info = probe(path)
    return {"sha256": sha256_file(path), **info.as_dict()}
