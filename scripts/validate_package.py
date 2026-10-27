#!/usr/bin/env python3
"""Validate an Abacus/LLM video package before frame generation or assembly."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas/storyboard.schema.json"
REQUIRED_PROMPT_MARKERS = (
    "Nano Banana Pro",
    "photoreal",
    "vertical 9:16",
    "Location:",
    "Lens:",
    "Light:",
    "Palette:",
)
MOJIBAKE_MARKERS = ("\ufffd", "Ã", "Â", "â€™", "â€œ", "â€", "ï»¿")
DISCLAIMER_MARKERS = (
    "source says",
    "verify before publication",
    "legal access",
    "licensed sourced",
    "factual correction",
    "not survey-grade",
)


def _words(value: str) -> set[str]:
    return {word.casefold() for word in re.findall(r"[\w]+", value, flags=re.UNICODE)}


def validate(package: Path, schema_path: Path = DEFAULT_SCHEMA, *, require_assets: bool = False) -> list[str]:
    board_path = package / "storyboard.json" if package.is_dir() else package
    package_dir = board_path.parent
    problems: list[str] = []
    raw = board_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("storyboard.json has a UTF-8 BOM; save plain UTF-8")
    try:
        board = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return problems + [f"storyboard is not valid UTF-8 JSON: {exc}"]
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(
                board
            ),
            key=lambda e: list(map(str, e.path)),
        )
        for error in errors:
            location = ".".join(map(str, error.path)) or "$"
            problems.append(f"schema {location}: {error.message}")
    except ImportError:
        return problems + ["jsonschema is required; install repository requirements.txt"]
    except Exception as exc:
        return problems + [f"schema validation error: {exc}"]

    blocks = board.get("blocks", []) if isinstance(board, dict) else []
    ids = [block.get("id") for block in blocks if isinstance(block, dict)]
    if len(set(ids)) != len(ids):
        problems.append("block IDs must be unique")
    if len(blocks) == 12:
        for index, block in enumerate(blocks, 1):
            expected = f"block_{index:02d}_"
            if not str(block.get("id", "")).startswith(expected):
                problems.append(f"blocks[{index - 1}].id must start with {expected}")
            prompt = str(block.get("visual_prompt", ""))
            count = len(prompt.split())
            if count > 60:
                problems.append(f"{block.get('id')}: visual_prompt has {count} words (limit 60)")
            low = prompt.casefold()
            if any(marker in low for marker in DISCLAIMER_MARKERS):
                problems.append(
                    f"{block.get('id')}: disclaimer/source text must be in source_notes, not visual_prompt"
                )
            for field in ("first_frame_prompt", "last_frame_prompt"):
                keyframe = str(block.get(field, ""))
                missing = [
                    marker
                    for marker in REQUIRED_PROMPT_MARKERS
                    if marker.casefold() not in keyframe.casefold()
                ]
                if missing:
                    problems.append(f"{block.get('id')}.{field}: missing standalone prompt markers {missing}")
                if re.search(
                    r"preceding frame|previous frame|prior frame|same as the last frame", keyframe, re.I
                ):
                    problems.append(
                        f"{block.get('id')}.{field}: prompt assumes hidden preceding-frame context"
                    )
                location = str(block.get("location", "")).strip()
                if location and location.casefold() not in keyframe.casefold():
                    problems.append(
                        f"{block.get('id')}.{field}: standalone prompt omits the storyboard location"
                    )
            if not str(block.get("source_notes", "")).strip():
                problems.append(f"{block.get('id')}: source_notes must contain factual/context notes")
        if blocks[-1].get("last_frame_prompt") != blocks[0].get("first_frame_prompt"):
            problems.append(
                "block 12 last_frame_prompt must exactly match block 01 first_frame_prompt for the loop"
            )

    text = raw.decode("utf-8")
    for marker in MOJIBAKE_MARKERS:
        if marker in text:
            problems.append(f"storyboard contains possible UTF-8 mojibake marker {marker!r}")
            break

    seo_path = package_dir / "youtube_seo.json"
    if seo_path.is_file():
        try:
            seo_raw = seo_path.read_bytes()
            if seo_raw.startswith(b"\xef\xbb\xbf"):
                problems.append("youtube_seo.json has a UTF-8 BOM")
            seo_text = seo_raw.decode("utf-8")
            if any(marker in seo_text for marker in MOJIBAKE_MARKERS):
                problems.append("youtube_seo.json contains possible UTF-8 mojibake")
            seo = json.loads(seo_text)
            description = str(seo.get("description", ""))
            if not 2000 <= len(description) <= 2500:
                problems.append(f"SEO description length {len(description)} is outside 2000–2500")
            tags_csv = str(seo.get("tags_csv", ", ".join(seo.get("tags", []))))
            if len(tags_csv) >= 500:
                problems.append(f"SEO tags are {len(tags_csv)} characters (limit <500)")
            for item in seo.get("title_candidates", []):
                title = str(item.get("title", ""))
                thumbnail = str(item.get("thumbnail_text", ""))
                if len(title) >= 55:
                    problems.append(f"title is {len(title)} characters (must be <55): {title}")
                if item.get("characters") is not None and item["characters"] != len(title):
                    problems.append(f"title character count metadata is stale for {title!r}")
                shared = _words(title) & _words(thumbnail)
                if shared:
                    problems.append(
                        f"title/thumbnail share words {sorted(shared)}: {title!r} / {thumbnail!r}"
                    )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"youtube_seo.json is not UTF-8 JSON: {exc}")

    if require_assets:
        frames = package_dir / "assets" / "frames"
        clips = package_dir / "assets" / "clips"
        for index in range(1, 13):
            if not (frames / f"frame_{index:02d}.png").is_file():
                problems.append(f"missing asset frame {frames / f'frame_{index:02d}.png'}")
            if not list(clips.glob(f"block_{index:02d}_*.mp4")):
                problems.append(f"missing clip asset block_{index:02d}_*.mp4")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="package folder or storyboard.json")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--require-assets", action="store_true", help="fail if any of 12 frame/clip files are absent"
    )
    args = parser.parse_args()
    problems = validate(args.package, args.schema, require_assets=args.require_assets)
    if problems:
        print("PACKAGE INVALID")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"PACKAGE VALID: {args.package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
