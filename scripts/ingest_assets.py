#!/usr/bin/env python3
"""Map Abacus Studio assets to storyboard blocks and create frame-based fallbacks."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.long_video_chain import probe_duration  # noqa: E402
from scripts.validate_package import validate  # noqa: E402
from scripts.video_pipeline.ffmpeg_util import run_ffmpeg  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_intake (
  package_slug TEXT NOT NULL, block_id TEXT NOT NULL,
  frame_path TEXT, frame_sha256 TEXT, clip_path TEXT, clip_sha256 TEXT,
  status TEXT NOT NULL CHECK(status IN ('planned','keyframed','clipped','failed')),
  error TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(package_slug, block_id)
);
CREATE TABLE IF NOT EXISTS asset_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, package_slug TEXT NOT NULL,
  block_id TEXT NOT NULL, old_status TEXT, new_status TEXT NOT NULL,
  frame_sha256 TEXT, clip_sha256 TEXT, detail TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def extract_first_frame(clip: Path, frame: Path) -> None:
    frame.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-i", str(clip), "-frames:v", "1", "-update", "1", "-compression_level", "6", str(frame)])
    if not frame.is_file() or frame.stat().st_size == 0:
        raise RuntimeError(f"frame extraction failed for {clip}")


def make_ken_burns(
    frame: Path, clip: Path, duration: float, *, width: int = 1080, height: int = 1920, fps: int = 30
) -> None:
    if duration <= 0:
        raise ValueError("fallback duration must be positive")
    clip.parent.mkdir(parents=True, exist_ok=True)
    zoom = "min(zoom+0.0005,1.08)"
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s={width}x{height}:fps={fps},setsar=1,format=yuv420p"
    )
    run_ffmpeg(
        [
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-i",
            str(frame),
            "-t",
            f"{duration:.6f}",
            "-vf",
            vf,
            "-r",
            str(fps),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(clip),
        ]
    )
    if not clip.is_file() or clip.stat().st_size < 1024:
        raise RuntimeError(f"Ken Burns fallback missing/too small: {clip}")


def _valid_png(path: Path) -> None:
    try:
        from PIL import Image

        with Image.open(path) as img:
            img.verify()
    except ImportError as exc:
        raise RuntimeError("Pillow is required to validate PNG assets; install requirements.txt") from exc
    except Exception as exc:
        raise ValueError(f"invalid PNG frame {path}: {exc}") from exc


def _record(
    con: sqlite3.Connection,
    package_slug: str,
    block_id: str,
    *,
    frame: Path | None,
    clip: Path | None,
    status: str,
    error: str | None = None,
    detail: str = "",
) -> None:
    fhash = sha256(frame) if frame and frame.exists() else None
    chash = sha256(clip) if clip and clip.exists() else None
    old = con.execute(
        "SELECT status FROM asset_intake WHERE package_slug=? AND block_id=?", (package_slug, block_id)
    ).fetchone()
    old_status = old[0] if old else None
    con.execute(
        "INSERT INTO asset_intake(package_slug,block_id,frame_path,frame_sha256,clip_path,clip_sha256,status,error,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(package_slug,block_id) DO UPDATE SET "
        "frame_path=excluded.frame_path,frame_sha256=excluded.frame_sha256,clip_path=excluded.clip_path,"
        "clip_sha256=excluded.clip_sha256,status=excluded.status,error=excluded.error,updated_at=CURRENT_TIMESTAMP",
        (
            package_slug,
            block_id,
            str(frame) if frame else None,
            fhash,
            str(clip) if clip else None,
            chash,
            status,
            error,
        ),
    )
    if old_status != status:
        con.execute(
            "INSERT INTO asset_events(package_slug,block_id,old_status,new_status,frame_sha256,clip_sha256,detail) VALUES(?,?,?,?,?,?,?)",
            (package_slug, block_id, old_status, status, fhash, chash, detail),
        )


def ingest(package: Path, *, db_path: Path | None = None, fallback: bool = True) -> dict[str, Any]:
    package = package.resolve()
    problems = validate(package)
    if problems:
        raise ValueError("package validation failed:\n" + "\n".join(f"- {p}" for p in problems))
    storyboard_path = package / "storyboard.json"
    board = json.loads(storyboard_path.read_text(encoding="utf-8"))
    package_slug = board["slug"]
    frame_dir = package / "assets" / "frames"
    clip_dir = package / "assets" / "clips"
    frame_dir.mkdir(parents=True, exist_ok=True)
    clip_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_path or ROOT / "registry" / "pipeline_state.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    result: dict[str, Any] = {"package": package_slug, "blocks": [], "fallback_clips": 0, "missing_audio": []}
    modified = False
    try:
        for index, block in enumerate(board["blocks"], 1):
            bid = block["id"]
            audio = package / block.get("audio", f"audio/{bid}.wav")
            has_audio = audio.is_file() and audio.stat().st_size > 0
            if not has_audio:
                result["missing_audio"].append(bid)
            frame = frame_dir / f"frame_{index:02d}.png"
            candidates = sorted(clip_dir.glob(f"block_{index:02d}_*.mp4"))
            if len(candidates) > 1:
                raise ValueError(f"multiple clip assets map to {bid}: {candidates}")
            clip = candidates[0] if candidates else None
            if clip is not None and (not clip.is_file() or clip.stat().st_size == 0):
                raise ValueError(f"clip file is empty: {clip}")
            if frame.is_file():
                _valid_png(frame)
            elif clip is not None:
                extract_first_frame(clip, frame)
                _valid_png(frame)
                modified = True
            else:
                block["status"] = "planned"
                _record(
                    con,
                    package_slug,
                    bid,
                    frame=None,
                    clip=None,
                    status="planned",
                    detail="no frame or clip found",
                )
                result["blocks"].append({"id": bid, "status": "planned"})
                continue

            previous = con.execute(
                "SELECT status FROM asset_intake WHERE package_slug=? AND block_id=?", (package_slug, bid)
            ).fetchone()
            already_clipped = bool(previous and previous[0] == "clipped" and clip is not None)
            if not already_clipped:
                _record(
                    con,
                    package_slug,
                    bid,
                    frame=frame,
                    clip=None,
                    status="keyframed",
                    detail="frame present or extracted",
                )
            block["keyframe"] = frame.relative_to(package).as_posix()
            block["status"] = "clipped" if already_clipped else "keyframed"
            modified = True
            if clip is None and fallback:
                if has_audio:
                    duration = probe_duration(audio)
                else:
                    duration = float(block.get("duration_target_seconds", 5.0))
                clip = clip_dir / f"block_{index:02d}_{bid.removeprefix(f'block_{index:02d}_')}.mp4"
                make_ken_burns(frame, clip, duration)
                result["fallback_clips"] += 1
            if clip is not None:
                _record(
                    con,
                    package_slug,
                    bid,
                    frame=frame,
                    clip=clip,
                    status="clipped",
                    detail="source or Ken Burns fallback clip",
                )
                block["clip"] = clip.relative_to(package).as_posix()
                block["status"] = "clipped"
                modified = True
            result["blocks"].append(
                {
                    "id": bid,
                    "status": block["status"],
                    "frame_sha256": sha256(frame),
                    "clip_sha256": sha256(clip) if clip else None,
                }
            )
        if modified:
            storyboard_path.write_text(
                json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    result["ready_for_assembly"] = not result["missing_audio"] and all(
        item["status"] == "clipped" for item in result["blocks"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument(
        "--no-fallback", action="store_true", help="record keyframes without making missing clips"
    )
    args = parser.parse_args()
    try:
        report = ingest(args.package, db_path=args.db, fallback=not args.no_fallback)
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        print(f"ASSET INTAKE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
