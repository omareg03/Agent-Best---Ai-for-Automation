#!/usr/bin/env python3
"""Validate ComfyUI graph templates -- offline (CI) or against a live server.

Offline mode proves structural correctness: valid JSON, every node has a
class_type, every __TOKEN__ the engine substitutes is actually present, and the
engine can render the template without leaving leftovers.

Online mode proves the thing offline cannot: that every node class in the graph
EXISTS on your ComfyUI build. Custom-node drift is the #1 cause of "it worked
last month" in ComfyUI pipelines, so this is the check that must run before a
paid or multi-hour render.

Usage:
    python scripts/validate_comfy.py --offline
    python scripts/validate_comfy.py --graph wan22_flf2v --comfy-url http://127.0.0.1:8188
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.video_pipeline.config import COMFYUI_URL, WORKFLOWS_DIR  # noqa: E402
from scripts.video_pipeline.engines.comfy import TOKENS, ComfyVideoEngine  # noqa: E402


def graph_files() -> list[Path]:
    return sorted((WORKFLOWS_DIR / "comfyui").glob("*.json"))


def validate_offline(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        raw = path.read_text(encoding="utf-8")
        graph = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON ({exc})"]

    if not isinstance(graph, dict) or not graph:
        return [f"{path.name}: must be a non-empty object of node_id -> node"]

    used_tokens: set[str] = set()
    for node_id, node in graph.items():
        if node_id.startswith("_"):
            continue  # file-level comments
        if not isinstance(node, dict):
            problems.append(f"{path.name}: node {node_id} is not an object")
            continue
        if not node.get("class_type"):
            problems.append(f"{path.name}: node {node_id} missing class_type")
        if "inputs" not in node:
            problems.append(f"{path.name}: node {node_id} missing inputs")
        for value in (node.get("inputs") or {}).values():
            if isinstance(value, str):
                used_tokens.update(token for token in TOKENS if token in value)
        # Linked inputs must point at an existing node.
        for key, value in (node.get("inputs") or {}).items():
            if isinstance(value, list) and value and isinstance(value[0], str):
                if value[0] not in graph:
                    problems.append(f"{path.name}: node {node_id}.{key} links to missing node {value[0]}")

    if "__PROMPT__" not in used_tokens:
        problems.append(f"{path.name}: never uses __PROMPT__ (the graph would ignore the shot)")
    if "__START_IMAGE__" not in used_tokens:
        problems.append(f"{path.name}: never uses __START_IMAGE__ (frame chaining impossible)")
    if "__SEED__" not in used_tokens:
        problems.append(f"{path.name}: never uses __SEED__ (renders would not be reproducible)")

    # The engine must be able to substitute the template end-to-end.
    try:
        engine = ComfyVideoEngine(path.stem)
        engine.build_graph(_fake_request(), start_name="start.png", end_name="end.png")
    except Exception as exc:  # noqa: BLE001 - any failure here is a real defect
        problems.append(f"{path.name}: token substitution failed -> {exc}")

    return problems


def _fake_request():
    from scripts.video_pipeline.engines.base import VideoRequest

    return VideoRequest(
        scene_id="validate",
        prompt="a validation frame",
        out_path=Path("/tmp/validate.mp4"),
        duration=5.0,
        start_frame=Path("/tmp/start.png"),
        end_frame=Path("/tmp/end.png"),
        negative_prompt="blurry",
        seed=1234,
        width=640,
        height=360,
        fps=16,
    )


def validate_online(graph_name: str, base_url: str) -> list[str]:
    engine = ComfyVideoEngine(graph_name, base_url=base_url)
    result = engine.health()
    if result.get("ok"):
        return []
    if "error" in result:
        return [f"{graph_name}: cannot reach ComfyUI at {base_url} -> {result['error']}"]
    missing = result.get("missing_node_classes") or []
    return [
        f"{graph_name}: {len(missing)} node class(es) missing from the server: {', '.join(missing)}",
        "  fix: install the matching custom node pack, or point --graph at a graph your build supports",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="structure + token checks only (no server)")
    parser.add_argument("--graph", default=None, help="validate a single graph against a live server")
    parser.add_argument("--comfy-url", default=COMFYUI_URL)
    args = parser.parse_args()

    targets = [WORKFLOWS_DIR / "comfyui" / f"{args.graph}.json"] if args.graph else graph_files()
    if not targets or not all(p.exists() for p in targets):
        print(f"no graph templates found under {WORKFLOWS_DIR / 'comfyui'}", file=sys.stderr)
        return 2

    failures = 0
    for path in targets:
        problems = validate_offline(path)
        if not args.offline or args.graph:
            problems += validate_online(path.stem, args.comfy_url)
        if problems:
            failures += 1
            print(f"FAIL  {path.stem}")
            for problem in problems:
                print(f"      {problem}")
        else:
            graph = json.loads(path.read_text(encoding="utf-8"))
            print(f"PASS  {path.stem}  ({len([k for k in graph if not k.startswith('_')])} nodes, tokens ok)")

    total = len(targets)
    print(f"\n{total - failures}/{total} graph template(s) valid")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
