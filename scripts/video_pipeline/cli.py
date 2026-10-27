"""Command line interface.

  python -m scripts.video_pipeline.cli init my-film
  python -m scripts.video_pipeline.cli storyboard check projects/my-film/storyboard.json
  python -m scripts.video_pipeline.cli plan my-film
  python -m scripts.video_pipeline.cli run my-film --engine wan22_flf2v
  python -m scripts.video_pipeline.cli resume my-film
  python -m scripts.video_pipeline.cli verify my-film
  python -m scripts.video_pipeline.cli selftest
  python -m scripts.video_pipeline.cli registry refresh --github
  python -m scripts.video_pipeline.cli engine probe --engine comfy
  python -m scripts.video_pipeline.cli comfy validate --graph wan22_flf2v
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import (
    COMFYUI_URL,
    DEFAULT_IMAGE_MODEL,
    IMAGE_MODEL_COSTS_USD,
    VIDEO_MODEL_COST_USD_PER_SECOND,
    project_paths,
)
from .engines import ENGINES, get_video_engine
from .errors import PipelineError
from .pipeline import Pipeline, RunOptions
from .state import StateStore
from .storyboard import plan_summary, validate_payload
from . import storyboard as sb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--engine", default="mock", choices=sorted(ENGINES), help="video engine (default: mock)")
    parser.add_argument("--images", default="", choices=["", "mock", "gemini"], help="keyframe engine (default: auto)")
    parser.add_argument("--tts", default="", choices=["", "mock", "kokoro", "edge"], help="narration engine (default: auto)")
    parser.add_argument("--align", default="auto", choices=["auto", "whisperx", "estimate"])
    parser.add_argument("--limit", type=int, default=None, help="render at most N scenes (smoke test)")
    parser.add_argument("--force", action="store_true", help="re-render everything, ignore state")
    parser.add_argument("--fit", dest="fit_mode", default="hold", choices=["hold", "pingpong", "trim"])
    parser.add_argument("--no-captions", action="store_true", help="do not burn subtitles")
    parser.add_argument("--music", default=None, help="music bed (ducked under narration)")
    parser.add_argument("--comfy-url", default=None, help="ComfyUI base URL")
    parser.add_argument("--ack-experimental", action="store_true", help="allow unverified wire formats (Gemini Omni)")
    parser.add_argument("--allow-seam", action="store_true", help="degrade a broken shoulder to a fade instead of failing")
    parser.add_argument("--keep-going", action="store_true", help="continue after a failed scene")
    parser.add_argument("--no-assembly", action="store_true", help="render scenes only")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")


def _options_from(args: argparse.Namespace, *, force_engine: str | None = None) -> RunOptions:
    return RunOptions(
        engine=force_engine or args.engine,
        image_engine=args.images,
        tts_engine=args.tts,
        align=args.align,
        limit=args.limit,
        force=args.force,
        fit_mode=args.fit_mode,
        burn_captions=not args.no_captions,
        music=args.music,
        comfy_url=args.comfy_url or COMFYUI_URL,
        acknowledge_unverified=args.ack_experimental,
        allow_seam=args.allow_seam,
        keep_going=args.keep_going,
        skip_assembly=args.no_assembly,
        verbose=not args.quiet,
    )


TEMPLATE_SCENES = [
    {
        "scene_id": "opening",
        "visual_prompt": "Wide establishing shot of a fog-covered coastal town at dawn, fishing boats silhouetted, cold blue light with a single warm window glowing.",
        "voiceover_text": "Every town keeps one light on for the people who leave. This one kept it for eleven years.",
        "camera_motion": "slow push in, 35mm",
        "duration": None,
        "seed": 101,
        "transition": "cut",
    },
    {
        "scene_id": "character",
        "visual_prompt": "Medium close-up of a woman in her thirties in a wool coat, salt wind in her hair, standing at the harbour rail looking out to sea.",
        "voiceover_text": "Mara came back to find out what the light was waiting for.",
        "camera_motion": "gentle handheld drift",
        "duration": None,
        "seed": 202,
        "transition": "cut",
    },
    {
        "scene_id": "reveal",
        "visual_prompt": "Interior of the lighthouse lamp room, brass machinery, dust in a shaft of morning light, the same woman reaching toward the lens.",
        "voiceover_text": "The answer was never in the light. It was in who still climbed the stairs.",
        "camera_motion": "slow tilt up",
        "duration": None,
        "seed": 303,
        "transition": "fade",
    },
]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_init(args: argparse.Namespace) -> int:
    slug = args.slug
    paths = project_paths(slug)
    if paths.storyboard.exists() and not args.force:
        raise PipelineError(
            f"{paths.storyboard} already exists",
            stage="init",
            hint="pass --force to overwrite, or choose another slug",
        )
    payload = {
        "title": args.title or slug.replace("-", " ").title(),
        "slug": slug,
        "logline": "One sentence that sells the film.",
        "style_anchor": "cinematic, teal-and-amber grade, 35mm, shallow depth of field, natural light",
        "character_sheet_prompt": "Mara, 34, weather-worn wool coat, dark hair tied back, freckles, quiet intensity",
        "negative_prompt": "text, watermark, logo, extra limbs, warped hands, low detail",
        "voice": "af_heart",
        "music": "",
        "width": 1280,
        "height": 720,
        "fps": 24,
        "aspect_ratio": "16:9",
        "language": "en",
        "engine": "wan22_flf2v",
        "scenes": TEMPLATE_SCENES,
    }
    problems = validate_payload(payload)
    if problems:
        raise PipelineError("internal template failed validation: " + "; ".join(problems), stage="init")
    paths.ensure()
    paths.storyboard.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"created {paths.storyboard}")
    print("\nNext:")
    print(f"  1. edit the scenes (visual_prompt + voiceover_text)")
    print(f"  2. python -m scripts.video_pipeline.cli storyboard check {paths.storyboard}")
    print(f"  3. python -m scripts.video_pipeline.cli run {slug} --engine mock    # free smoke test")
    print(f"  4. python -m scripts.video_pipeline.cli run {slug} --engine wan22_flf2v  # real render")
    return 0


def cmd_storyboard_check(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = validate_payload(data)
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    storyboard = sb.load(path)
    summary = plan_summary(storyboard)
    if args.json:
        _print_json(summary)
        return 0
    print(f"OK  {storyboard.title}  ({summary['scene_count']} scenes, ~{summary['estimated_total_minutes']} min)")
    print(f"    storyboard hash: {summary['storyboard_hash']}")
    for row in summary["scenes"]:
        print(
            f"    {row['index']:02d} {row['scene_id']:<18} "
            f"narration≈{row['narration_est_s']:5.1f}s  clip≈{row['clip_target_s']:5.1f}s  "
            f"{row['words']:3d} words  {row['hash']}"
        )
    for warning in summary["warnings"]:
        print(f"    ! {warning}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    paths = project_paths(args.project)
    storyboard = sb.load(paths.storyboard)
    summary = plan_summary(storyboard)
    image_engine = args.images or ("gemini" if args.engine != "mock" else "mock")
    images = len(storyboard.scenes) * 2 + 1
    per_image = IMAGE_MODEL_COSTS_USD.get(DEFAULT_IMAGE_MODEL, 0.0336) if image_engine == "gemini" else 0.0
    seconds = summary["estimated_total_seconds"]
    video_cost = seconds * VIDEO_MODEL_COST_USD_PER_SECOND if args.engine in ("gemini", "gemini_omni") else 0.0
    cost = {
        "engine": args.engine,
        "image_engine": image_engine,
        "images": images,
        "image_cost_usd": round(images * per_image, 3),
        "video_cost_usd": round(video_cost, 3),
        "total_usd": round(images * per_image + video_cost, 3),
        "note": "local/open-weight engines cost $0 in API fees; GPU time is not included",
    }
    payload = {**summary, "cost_estimate": cost}
    if args.json:
        _print_json(payload)
        return 0
    print(f"{storyboard.title}  (~{summary['estimated_total_minutes']} min, {summary['scene_count']} scenes)")
    print(f"estimated API spend at engine '{args.engine}': ${cost['total_usd']:.2f} "
          f"({images} images + {seconds:.0f}s video)")
    for row in summary["scenes"]:
        print(f"  {row['index']:02d} {row['scene_id']:<18} clip≈{row['clip_target_s']:5.1f}s")
    for warning in summary["warnings"]:
        print(f"  ! {warning}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    paths = project_paths(args.project)
    options = _options_from(args)
    # Machine-readable mode: progress goes to stderr so stdout stays parseable.
    sink = (lambda message: print(message, file=sys.stderr)) if args.json else None
    pipeline = Pipeline(paths, options, log=sink)
    try:
        report = pipeline.run()
        result = pipeline.verify() if not report.get("failures") else {"ok": False, "skipped": True}
    finally:
        pipeline.close()
    if args.json:
        _print_json({"run": report, "verify": result})
    else:
        print()
        print(f"project : {report['project']}")
        print(f"scenes  : {report['scenes_processed']} processed, {len(report['failures'])} failed")
        print(f"state   : {report['state']['by_status']}")
        print(f"cost    : ${report['state']['cost_usd']:.4f}")
        if "assembly" in report:
            print(f"final   : {report['assembly']['final']} ({report['assembly']['duration']}s)")
        print(f"manifest: {report['manifest']}")
        print(f"verify  : {'PASS' if result.get('ok') else 'FAIL'}")
        for issue in result.get("issues", []):
            print(f"  - {issue}")
    return 0 if result.get("ok") else 1


def cmd_resume(args: argparse.Namespace) -> int:
    return cmd_run(args)


def cmd_verify(args: argparse.Namespace) -> int:
    paths = project_paths(args.project)
    options = RunOptions(engine="mock", burn_captions=not args.no_captions, verbose=False)
    pipeline = Pipeline(paths, options, log=lambda *_: None)
    try:
        result = pipeline.verify()
    finally:
        pipeline.close()
    if args.json:
        _print_json(result)
    else:
        print(f"{'PASS' if result['ok'] else 'FAIL'}  {result['scenes']} scenes, "
              f"max boundary dHash {result['max_boundary_dhash']}, final {result['final_duration']}s")
        for issue in result["issues"]:
            print(f"  - {issue}")
    return 0 if result["ok"] else 1


def cmd_status(args: argparse.Namespace) -> int:
    paths = project_paths(args.project)
    if not paths.state_db.exists():
        raise PipelineError(f"no state database at {paths.state_db}", stage="status", hint="render something first")
    store = StateStore(paths.state_db)
    try:
        project = store.conn.execute(
            "SELECT * FROM projects WHERE slug=?", (args.project.rstrip("/").split("/")[-1],)
        ).fetchone()
        if project is None:
            raise PipelineError(f"project not found in state db: {args.project}", stage="status")
        summary = store.summary(int(project["id"]))
        events = [dict(row) for row in store.events(int(project["id"]), limit=args.events)]
    finally:
        store.close()
    if args.json:
        _print_json({"summary": summary, "events": events})
        return 0
    print(f"scenes    : {summary['scenes']}  {summary['by_status']}")
    print(f"rendered  : {summary['rendered_seconds']}s  cost ${summary['cost_usd']}")
    if summary["pending"]:
        print(f"pending   : {', '.join(summary['pending'])}")
    print("\nrecent events:")
    for event in events:
        print(f"  {event['created_at']}  {event['kind']:<10} {event['scene_id'] or '-':<18} {event['detail']}")
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    from .selftest import run_selftest

    result = run_selftest(
        out_dir=Path(args.out) if args.out else None,
        keep=args.keep,
        copy_demo=not args.no_asset,
        quiet=args.json,
    )
    if args.json:
        _print_json(result)
    return 0 if result["ok"] else 1


def cmd_registry(args: argparse.Namespace) -> int:
    from . import registry_update as reg

    if args.action == "render":
        data = reg.load_registry()
        markdown = reg.render_markdown(data, history=reg.read_history())
        reg.MARKDOWN_PATH.write_text(markdown, encoding="utf-8")
        print(f"rendered {reg.MARKDOWN_PATH} ({len(markdown)} bytes)")
        return 0
    if args.action == "check":
        data = reg.load_registry()
        ok, messages = reg.staleness_gate(data, strict=True)
        findings = reg.staleness(data)
        for finding in findings:
            if finding["level"] != "ok":
                print(f"  {finding['level'].upper():<4} {finding['id']:<24} {finding['reason']}")
        print("PASS" if ok else f"FAIL: {len(messages)} stale tool(s)")
        return 0 if ok else 1
    if args.action == "refresh":
        result = reg.update(github=not args.no_github, token=args.token, source=args.source)
        _print_json(result)
        return 0 if result["stale_ok"] else 1
    if args.action == "show":
        data = reg.load_registry()
        rows = [t for t in data["tools"] if not args.category or t["category"] == args.category]
        for tool in rows:
            print(f"{tool['category']:<13} {tool['name']:<30} {tool['license_id']:<45} {tool['status']}")
        return 0
    raise PipelineError(f"unknown registry action: {args.action}", stage="registry")


def cmd_engine(args: argparse.Namespace) -> int:
    if args.action == "list":
        for name, config in sorted(ENGINES.items()):
            print(f"{name:<20} family={config['family']:<8} graph={config['graph'] or '-'}")
        return 0
    if args.action == "probe":
        if args.engine in ("comfy", "wan22_flf2v", "wan22_ti2v_5b", "framepack_long_i2v"):
            engine = get_video_engine(args.engine, comfy_url=args.comfy_url or COMFYUI_URL)
            result = engine.health()
        elif args.engine in ("gemini", "gemini_omni"):
            from .engines.gemini_omni import GeminiOmniEngine

            result = GeminiOmniEngine().probe()
        else:
            engine = get_video_engine(args.engine)
            result = engine.capabilities()
        _print_json(result)
        return 0 if result.get("ok", True) else 1
    raise PipelineError(f"unknown engine action: {args.action}", stage="engine")


def cmd_comfy(args: argparse.Namespace) -> int:
    if args.action == "graphs":
        from .config import WORKFLOWS_DIR

        for path in sorted((WORKFLOWS_DIR / "comfyui").glob("*.json")):
            print(path.stem)
        return 0
    if args.action == "validate":
        from .engines.comfy import ComfyVideoEngine

        engine = ComfyVideoEngine(args.graph, base_url=args.comfy_url or COMFYUI_URL)
        if args.offline:
            graph = json.loads(engine.load_graph())
            tokens = [t for t in ("__PROMPT__", "__START_IMAGE__") if t not in engine.load_graph()]
            print(f"{args.graph}: {len(graph)} nodes, valid JSON, missing tokens: {tokens or 'none'}")
            return 0
        result = engine.health()
        _print_json(result)
        return 0 if result["ok"] else 1
    raise PipelineError(f"unknown comfy action: {args.action}", stage="comfy")


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Long-form AI video pipeline: keyframe chaining, deterministic assembly, resumable state.",
    )
    parser.add_argument("--version", action="version", version=f"pipeline {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a project storyboard")
    init.add_argument("slug")
    init.add_argument("--title")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    check = sub.add_parser("storyboard", help="validate / inspect a storyboard")
    check.add_argument("action", choices=["check"])
    check.add_argument("file")
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_storyboard_check)

    plan = sub.add_parser("plan", help="pre-flight: durations, scene count, cost estimate")
    plan.add_argument("project")
    plan.add_argument("--engine", default="mock", choices=sorted(ENGINES))
    plan.add_argument("--images", default="", choices=["", "mock", "gemini"])
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", help="render the film (resumable)")
    run.add_argument("project")
    _add_run_options(run)
    run.set_defaults(func=cmd_run)

    resume = sub.add_parser("resume", help="continue an interrupted render")
    resume.add_argument("project")
    _add_run_options(resume)
    resume.set_defaults(func=cmd_resume)

    verify = sub.add_parser("verify", help="post-render gate: files, seams, durations, audio")
    verify.add_argument("project")
    verify.add_argument("--no-captions", action="store_true")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=cmd_verify)

    status = sub.add_parser("status", help="state + audit events")
    status.add_argument("project")
    status.add_argument("--events", type=int, default=20)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    selftest = sub.add_parser("selftest", help="offline end-to-end proof (mock engines, real FFmpeg)")
    selftest.add_argument("--out", default=None)
    selftest.add_argument("--keep", action="store_true", help="keep the project directory")
    selftest.add_argument("--no-asset", action="store_true", help="do not copy the demo into assets/demo")
    selftest.add_argument("--json", action="store_true")
    selftest.set_defaults(func=cmd_selftest)

    registry = sub.add_parser("registry", help="living AI tool registry")
    registry.add_argument("action", choices=["refresh", "render", "check", "show"])
    registry.add_argument("--no-github", action="store_true")
    registry.add_argument("--token", default=None)
    registry.add_argument("--source", default="cli")
    registry.add_argument("--category", default=None)
    registry.set_defaults(func=cmd_registry)

    engine = sub.add_parser("engine", help="inspect / probe video engines")
    engine.add_argument("action", choices=["list", "probe"])
    engine.add_argument("--engine", default="mock", choices=sorted(ENGINES))
    engine.add_argument("--comfy-url", default=None)
    engine.set_defaults(func=cmd_engine)

    comfy = sub.add_parser("comfy", help="ComfyUI graph validation")
    comfy.add_argument("action", choices=["validate", "graphs"])
    comfy.add_argument("--graph", default="wan22_flf2v")
    comfy.add_argument("--comfy-url", default=None)
    comfy.add_argument("--offline", action="store_true")
    comfy.set_defaults(func=cmd_comfy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except PipelineError as exc:
        print(exc.render(), file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("\ninterrupted -- state is saved, run `resume`", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
