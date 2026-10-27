#!/usr/bin/env python3
"""Audio-master, resumable block assembler for short/long-form video.

Inputs: package/storyboard.json with blocks [{id, narration, video, ...}]. For each
block, provide audio/<id>.wav and clips/<id>.mp4 (or configure paths in the JSON).
Audio duration is authoritative: video is fitted to each WAV duration, then each
clip is normalized to CFR, yuv420p, and a common canvas before concatenation.

This is an assembly engine, not an AI-generation API client. It never claims a
provider render happened; generated source media must be supplied by the operator.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.video_pipeline.ffmpeg_util import ffmpeg_bin, ffprobe_bin, run_ffmpeg  # noqa: E402

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS renders (
  package TEXT NOT NULL, block_id TEXT NOT NULL, audio_path TEXT NOT NULL,
  video_path TEXT NOT NULL, audio_sha256 TEXT NOT NULL, video_sha256 TEXT NOT NULL,
  prompt TEXT NOT NULL DEFAULT '', seed INTEGER, model_version TEXT NOT NULL DEFAULT 'unknown',
  start_frame_hash TEXT NOT NULL DEFAULT '', end_frame_hash TEXT NOT NULL DEFAULT '',
  duration REAL NOT NULL, status TEXT NOT NULL, output_path TEXT,
  error TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(package, block_id)
);
CREATE TABLE IF NOT EXISTS assemblies (
  package TEXT PRIMARY KEY, status TEXT NOT NULL, output_path TEXT,
  options_json TEXT NOT NULL, error TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def sha(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_duration(path: Path) -> float:
    probe = ffprobe_bin()
    if probe:
        p = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
        )
        if p.returncode == 0:
            try:
                return float(p.stdout.strip())
            except ValueError:
                pass
    p = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    import re

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    if not m:
        raise RuntimeError(f"Could not read duration for {path}: {p.stderr[-1200:]}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def init_db(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(DB_SCHEMA)
    # Additive migration for databases created by early versions of this script.
    present = {row[1] for row in con.execute("PRAGMA table_info(renders)")}
    migrations = {
        "prompt": "TEXT NOT NULL DEFAULT ''",
        "seed": "INTEGER",
        "model_version": "TEXT NOT NULL DEFAULT 'unknown'",
        "start_frame_hash": "TEXT NOT NULL DEFAULT ''",
        "end_frame_hash": "TEXT NOT NULL DEFAULT ''",
    }
    for name, declaration in migrations.items():
        if name not in present:
            con.execute(f"ALTER TABLE renders ADD COLUMN {name} {declaration}")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def load_spec(spec_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = json.loads(spec_path.read_text(encoding="utf-8"))
    blocks = doc.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("storyboard JSON needs a non-empty 'blocks' array")
    seen: set[str] = set()
    for i, block in enumerate(blocks, 1):
        bid = str(block.get("id", f"block_{i:02d}"))
        if bid in seen:
            raise ValueError(f"duplicate block id: {bid}")
        seen.add(bid)
        block["id"] = bid
    return doc, blocks


def frame_hashes(video: Path, scratch: Path, block_id: str) -> tuple[str, str]:
    """Hash decoded boundary frames for provenance and seam review."""
    first = scratch / f"{block_id}_first.jpg"
    last = scratch / f"{block_id}_last.jpg"
    run_ffmpeg(["-i", str(video), "-frames:v", "1", "-q:v", "2", str(first)])
    # Repeatedly update one image while decoding the last three seconds; the final
    # file is the final decoded frame, rather than a guessed timestamp sample.
    run_ffmpeg(["-sseof", "-3", "-i", str(video), "-update", "1", "-q:v", "2", str(last)])
    return sha(first), sha(last)


def fit_block(
    video: Path,
    audio: Path,
    target: Path,
    *,
    width: int,
    height: int,
    fps: int,
    drop_first: bool,
    duration: float,
) -> None:
    # setpts before fps and output -r avoids ffmpeg builds that silently reset CFR.
    trim = "trim=start_frame=1," if drop_first else ""
    punch = ""
    # A smooth zoom-in beginning at t=2.5s and returning to baseline by 3.5s;
    # omit it for short, narration-driven blocks that cannot fit the reset window.
    if duration >= 3.5:
        start, peak, finish = round(2.5 * fps), round(3.0 * fps), round(3.5 * fps)
        z = (
            f"if(between(on\\,{start}\\,{peak})\\,1+0.12*(on-{start})/{peak - start}\\,"
            f"if(between(on\\,{peak + 1}\\,{finish})\\,1.12-0.12*(on-{peak})/{finish - peak}\\,1))"
        )
        punch = f",zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps}"
    vf = (
        f"{trim}setpts=PTS-STARTPTS,"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}{punch},tpad=stop_mode=clone:stop_duration={duration:.6f},"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS"
    )
    run_ffmpeg(
        [
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            vf,
            "-r",
            str(fps),
            "-frames:v",
            str(max(1, round(duration * fps))),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )


def concat_audio(wavs: list[Path], output: Path, *, target_duration: float) -> None:
    # WAV inputs must have a consistent format for concat demuxer. Normalize each into PCM first.
    with tempfile.TemporaryDirectory(prefix="audio-master-") as tmp:
        normalized: list[Path] = []
        for i, wav in enumerate(wavs):
            p = Path(tmp) / f"a{i:03d}.wav"
            run_ffmpeg(["-i", str(wav), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(p)])
            normalized.append(p)
        listing = Path(tmp) / "audio.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in normalized), encoding="utf-8")
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-vn",
                "-af",
                "loudnorm=I=-14:TP=-1.5:LRA=11",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-t",
                f"{target_duration:.6f}",
                str(output),
            ]
        )


def assemble(
    package_dir: Path,
    *,
    output: Path,
    fps: int,
    width: int,
    height: int,
    db_path: Path,
    captions: bool,
    resume: bool,
) -> dict[str, Any]:
    from scripts.validate_package import validate

    package_issues = validate(package_dir)
    if package_issues:
        raise ValueError(
            "package validation failed before assembly:\n"
            + "\n".join(f"- {issue}" for issue in package_issues)
        )
    spec_path = package_dir / "storyboard.json"
    spec, blocks = load_spec(spec_path)
    scratch = package_dir / ".chain_work"
    scratch.mkdir(parents=True, exist_ok=True)
    con = init_db(db_path)
    package = str(package_dir.resolve())
    con.execute(
        "INSERT INTO assemblies(package,status,options_json) VALUES(?,?,?) ON CONFLICT(package) DO UPDATE SET status=excluded.status, options_json=excluded.options_json, error=NULL, updated_at=CURRENT_TIMESTAMP",
        (
            package,
            "running",
            json.dumps({"fps": fps, "width": width, "height": height, "captions": captions}),
        ),
    )
    con.commit()
    try:
        prepared: list[Path] = []
        wav_paths: list[Path] = []
        durations: list[float] = []
        for i, block in enumerate(blocks):
            bid = block["id"]
            audio = package_dir / block.get("audio", f"audio/{bid}.wav")
            video = package_dir / block.get("clip", f"clips/{bid}.mp4")
            if not audio.is_file() or audio.stat().st_size == 0:
                raise FileNotFoundError(f"missing/non-empty TTS WAV for {bid}: {audio}")
            if not video.is_file() or video.stat().st_size == 0:
                raise FileNotFoundError(f"missing/non-empty video clip for {bid}: {video}")
            dur = probe_duration(audio)
            if dur <= 0.05:
                raise ValueError(f"invalid WAV duration {dur:.3f}s for {bid}")
            durations.append(dur)
            wav_paths.append(audio)
            target = scratch / f"{i:03d}_{bid}.mp4"
            ah, vh = sha(audio), sha(video)
            start_hash, end_hash = frame_hashes(video, scratch, bid)
            prompt = str(block.get("visual_prompt", "")) + "\\n" + str(block.get("motion_prompt", ""))
            seed = int(block["seed"]) if block.get("seed") is not None else None
            model_version = str(block.get("model_version", "unknown"))
            row = con.execute(
                "SELECT audio_sha256,video_sha256,status,output_path FROM renders WHERE package=? AND block_id=?",
                (package, bid),
            ).fetchone()
            reusable = (
                resume
                and row
                and row[0] == ah
                and row[1] == vh
                and row[2] == "done"
                and row[3]
                and Path(row[3]).is_file()
            )
            if reusable:
                target = Path(row[3])
                con.execute(
                    "UPDATE renders SET prompt=?,seed=?,model_version=?,start_frame_hash=?,end_frame_hash=?,updated_at=CURRENT_TIMESTAMP WHERE package=? AND block_id=?",
                    (prompt, seed, model_version, start_hash, end_hash, package, bid),
                )
                con.commit()
            else:
                con.execute(
                    "INSERT INTO renders(package,block_id,audio_path,video_path,audio_sha256,video_sha256,prompt,seed,model_version,start_frame_hash,end_frame_hash,duration,status,output_path,error,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'running',?,NULL,CURRENT_TIMESTAMP) ON CONFLICT(package,block_id) DO UPDATE SET audio_path=excluded.audio_path,video_path=excluded.video_path,audio_sha256=excluded.audio_sha256,video_sha256=excluded.video_sha256,prompt=excluded.prompt,seed=excluded.seed,model_version=excluded.model_version,start_frame_hash=excluded.start_frame_hash,end_frame_hash=excluded.end_frame_hash,duration=excluded.duration,status='running',output_path=excluded.output_path,error=NULL,updated_at=CURRENT_TIMESTAMP",
                    (
                        package,
                        bid,
                        str(audio),
                        str(video),
                        ah,
                        vh,
                        prompt,
                        seed,
                        model_version,
                        start_hash,
                        end_hash,
                        dur,
                        str(target),
                    ),
                )
                con.commit()
                try:
                    fit_block(
                        video,
                        audio,
                        target,
                        width=width,
                        height=height,
                        fps=fps,
                        drop_first=i > 0,
                        duration=dur,
                    )
                    if target.stat().st_size == 0:
                        raise RuntimeError("normalized clip is zero bytes")
                    con.execute(
                        "UPDATE renders SET status='done', output_path=?, error=NULL, updated_at=CURRENT_TIMESTAMP WHERE package=? AND block_id=?",
                        (str(target), package, bid),
                    )
                    con.commit()
                except Exception as exc:
                    con.execute(
                        "UPDATE renders SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE package=? AND block_id=?",
                        (str(exc), package, bid),
                    )
                    con.commit()
                    raise
            prepared.append(target)
        concat_list = scratch / "video.txt"
        concat_list.write_text(
            "".join(f"file '{p.resolve().as_posix()}'\n" for p in prepared), encoding="utf-8"
        )
        silent = scratch / "joined_silent.mp4"
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-an",
                "-c:v",
                "copy",
                "-movflags",
                "+faststart",
                str(silent),
            ]
        )
        total = sum(durations)
        joined_audio = scratch / "master_audio.m4a"
        concat_audio(wav_paths, joined_audio, target_duration=total)
        output.parent.mkdir(parents=True, exist_ok=True)
        if captions:
            from scripts.auto_captions_4word import cues, write

            entries = []
            cursor = 0.0
            for block, dur in zip(blocks, durations, strict=True):
                words = str(block.get("narration", "")).split()
                entries.extend(cues(words, cursor, dur))
                cursor += dur
            ass = package_dir / "captions.ass"
            write(ass, entries, width=width, height=height)
            escaped_ass = ass.as_posix().replace(":", "\\\\:")
            vf = f"subtitles='{escaped_ass}'"
            run_ffmpeg(
                [
                    "-i",
                    str(silent),
                    "-i",
                    str(joined_audio),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-vf",
                    vf,
                    "-r",
                    str(fps),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(output),
                ]
            )
        else:
            run_ffmpeg(
                [
                    "-i",
                    str(silent),
                    "-i",
                    str(joined_audio),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(output),
                ]
            )
        if not output.is_file() or output.stat().st_size < 1024:
            raise RuntimeError(f"final output absent or suspiciously small: {output}")
        result = {
            "ok": True,
            "output": str(output),
            "duration_seconds": round(total, 3),
            "blocks": len(blocks),
            "fps": fps,
            "resolution": f"{width}x{height}",
            "audio_master": True,
            "captions_burned": captions,
        }
        con.execute(
            "UPDATE assemblies SET status='done', output_path=?, error=NULL, updated_at=CURRENT_TIMESTAMP WHERE package=?",
            (str(output), package),
        )
        con.commit()
        return result
    except Exception as exc:
        con.execute(
            "UPDATE assemblies SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE package=?",
            (str(exc), package),
        )
        con.commit()
        raise
    finally:
        con.close()


def extract_last_frame(video: Path, image: Path) -> None:
    """Write the last decoded frame from the final three seconds (not a guessed timestamp)."""
    image.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-sseof", "-3", "-i", str(video), "-update", "1", "-q:v", "1", str(image)])
    if not image.exists() or image.stat().st_size == 0:
        raise RuntimeError(f"last-frame extraction failed: {image}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "package",
        type=Path,
        nargs="?",
        help="directory containing storyboard.json, audio/, clips/ (not needed with --extract-last-frame)",
    )
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--fps", type=int, choices=(30, 60), default=30)
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--db", type=Path, default=ROOT / "registry/pipeline_state.db")
    p.add_argument("--captions", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--extract-last-frame", nargs=2, metavar=("VIDEO", "IMAGE"))
    args = p.parse_args()
    try:
        if args.extract_last_frame:
            extract_last_frame(Path(args.extract_last_frame[0]), Path(args.extract_last_frame[1]))
            print(json.dumps({"ok": True, "last_frame": args.extract_last_frame[1]}))
            return 0
        if args.package is None:
            p.error("package directory is required unless --extract-last-frame is used")
        output = args.output or args.package / "renders/final.mp4"
        print(
            json.dumps(
                assemble(
                    args.package,
                    output=output,
                    fps=args.fps,
                    width=args.width,
                    height=args.height,
                    db_path=args.db,
                    captions=args.captions,
                    resume=args.resume,
                ),
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
