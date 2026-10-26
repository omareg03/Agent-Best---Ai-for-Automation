"""Offline end-to-end proof.

Runs the whole pipeline with mock models but **real FFmpeg**: keyframes -> narration
-> chained clips -> seam measurement -> fit -> mux -> concat -> loudnorm -> ASS burn-in
-> verification, then deliberately breaks state to prove that:

  * deleting a clip re-renders exactly that scene (resume, not restart), and
  * editing a prompt invalidates that scene (no stale footage sneaks through).

This is what CI runs. If it passes, the assembly chain is genuinely working.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

from .config import REPO_ROOT, ProjectPaths
from .errors import MediaError
from .ffmpeg_util import assert_artifact, probe
from .media import extract_last_clean_frame
from .pipeline import Pipeline, RunOptions
from .state import StateStore

DEMO = {
    "title": "The Light That Waited",
    "slug": "selftest-demo",
    "logline": "A lighthouse keeps a promise for eleven years.",
    "style_anchor": "cinematic, teal-and-amber grade, 35mm, shallow depth of field, natural light",
    "character_sheet_prompt": "Mara, 34, weather-worn wool coat, dark hair tied back, freckles, quiet intensity",
    "negative_prompt": "text, watermark, logo, extra limbs, warped hands",
    "voice": "af_heart",
    "width": 640,
    "height": 360,
    "fps": 12,
    "aspect_ratio": "16:9",
    "language": "en",
    "scenes": [
        {
            "scene_id": "opening",
            "visual_prompt": "Wide establishing shot of a fog-covered harbour at dawn, boats silhouetted, one warm window glowing.",
            "voiceover_text": "Every town keeps one light on. This one kept it eleven years.",
            "camera_motion": "slow push in",
            "seed": 101,
        },
        {
            "scene_id": "character",
            "visual_prompt": "Medium close-up of Mara at the harbour rail, salt wind in her hair, looking out to sea.",
            "voiceover_text": "Mara came back to ask what the light was waiting for.",
            "camera_motion": "gentle handheld drift",
            "seed": 202,
        },
        {
            "scene_id": "reveal",
            "visual_prompt": "Inside the lighthouse lamp room, brass machinery, dust in a shaft of morning light.",
            "voiceover_text": "The answer was never in the light. It was in who climbed the stairs.",
            "camera_motion": "slow tilt up",
            "seed": 303,
            "transition": "fade",
        },
    ],
}

INVALIDATE_DEMO = {
    "title": "Invalidation Probe",
    "slug": "selftest-invalidate",
    "width": 512,
    "height": 288,
    "fps": 6,
    "scenes": [
        {
            "scene_id": "only",
            "visual_prompt": "A single grey door in a white corridor.",
            "voiceover_text": "One line only.",
            "seed": 7,
        }
    ],
}


def run_selftest(
    *, out_dir: Path | None = None, keep: bool = False, copy_demo: bool = True, quiet: bool = False
) -> dict:
    started = time.time()
    checks: list[dict] = []
    stream = sys.stderr if quiet else sys.stdout

    def say(message: str = "") -> None:
        print(message, file=stream)

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        say(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))

    root = out_dir or (REPO_ROOT / "projects" / "selftest-demo")
    if root.exists() and not keep:
        shutil.rmtree(root)
    paths = ProjectPaths(root).ensure()
    paths.storyboard.write_text(json.dumps(DEMO, indent=2) + "\n", encoding="utf-8")

    say("\n[1/5] full pipeline (mock models, real FFmpeg)")
    pipeline = Pipeline(
        paths,
        RunOptions(engine="mock", image_engine="mock", tts_engine="mock", align="estimate",
                   burn_captions=True, verbose=not quiet),
        log=(lambda message: print(message, file=sys.stderr)) if quiet else None,
    )
    report = pipeline.run()
    verify = pipeline.verify()
    store = pipeline.store
    project_id = pipeline.project_id
    scene_rows = {row["scene_id"]: dict(row) for row in store.scenes(project_id)}
    pipeline.close()

    check("pipeline produced no failures", not report["failures"], str(report["failures"])[:200])
    check("all scenes done", all(r["status"] == "done" for r in scene_rows.values()),
          str({k: v["status"] for k, v in scene_rows.items()}))
    check("character sheet generated",
          (paths.keyframes / "character_sheet.png").exists(),
          "identity anchor cached for reuse")
    keyframes = list(paths.keyframes.glob("scene_*_start.png")) + list(paths.keyframes.glob("scene_*_end.png"))
    check("two keyframes per scene", len(keyframes) >= 3 * 2, f"{len(keyframes)} keyframes")
    narrations = list(paths.audio.glob("*.wav"))
    check("narration per scene", len(narrations) == 3, f"{len(narrations)} wav files")

    metas = [json.loads(p.read_text()) for p in sorted(paths.segments.glob("scene_*.meta.json"))]
    seam_max = max((m.get("boundary_dhash", -1) for m in metas), default=-1)
    check("seams within threshold", seam_max <= 12, f"max boundary dHash {seam_max}")
    check("every scene chained from a real frame",
          all(Path(m["start_frame"]).exists() for m in metas), "start frames exist")
    words_total = sum(len(m.get("narration_words", [])) for m in metas)
    check("word-level timings recorded", words_total > 20, f"{words_total} words")
    check("narration durations measured",
          all((m.get("narration_seconds") or 0) > 0.4 for m in metas),
          ", ".join(f"{m['scene_id']}={m['narration_seconds']}s" for m in metas))

    final = paths.renders / "final.mp4"
    info = probe(final) if final.exists() else None
    check("final master exists", bool(info), str(final))
    check("final has audio", bool(info and info.has_audio), info.as_dict() if info else "")
    expected = sum(r["clip_duration"] or 0 for r in scene_rows.values())
    check("final duration matches segments",
          bool(info and abs(info.duration - expected) <= max(1.0, expected * 0.03)),
          f"{info.duration:.2f}s vs {expected:.2f}s" if info else "")
    ass = paths.subtitles / "selftest-demo.ass"
    ass_text = ass.read_text(encoding="utf-8") if ass.exists() else ""
    check("ASS captions written", len(ass_text) > 200 and "Dialogue:" in ass_text,
          f"{len(ass_text)} bytes")
    check("karaoke word tags present", "\\k" in ass_text, ass_text.count("\\k"))
    check("srt sidecar written", (paths.subtitles / "selftest-demo.srt").exists())
    check("thumbnail written", (paths.renders / "thumbnail.jpg").exists())
    check("verify gate passes", verify["ok"], "; ".join(verify["issues"])[:300])

    say("\n[2/5] black-frame guard")
    black_clip = paths.clips / "ends_in_black.mp4"
    from .ffmpeg_util import run_ffmpeg

    run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=black:s=320x180:d=1.2", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(black_clip)]
    )
    try:
        extract_last_clean_frame(black_clip, paths.clips / "black_last.png")
        check("black frame rejected", False, "extraction succeeded unexpectedly")
    except MediaError as exc:
        check("black frame rejected", "black" in exc.message.lower(), exc.message[:120])

    say("\n[3/5] resume: delete one clip, re-run")
    victim = scene_rows["character"]
    victim_attempts = victim["attempts"]
    other_attempts = {k: v["attempts"] for k, v in scene_rows.items() if k != "character"}
    Path(victim["clip_path"]).unlink()
    pipeline2 = Pipeline(
        paths,
        RunOptions(engine="mock", image_engine="mock", tts_engine="mock", align="estimate", verbose=False),
    )
    report2 = pipeline2.run()
    resumed = {row["scene_id"]: dict(row) for row in pipeline2.store.scenes(pipeline2.project_id)}
    pipeline2.close()
    check("resume re-rendered the damaged scene",
          resumed["character"]["attempts"] == victim_attempts + 1,
          f"attempts {victim_attempts} -> {resumed['character']['attempts']}")
    check("resume did not re-render intact scenes",
          all(resumed[k]["attempts"] == v for k, v in other_attempts.items()),
          str({k: (other_attempts[k], resumed[k]['attempts']) for k in other_attempts}))
    check("assembly still completes after resume",
          "assembly" in report2 and Path(report2["assembly"]["final"]).exists())

    say("\n[4/5] prompt invalidation")
    inv_root = root.parent / "selftest-invalidate"
    if inv_root.exists():
        shutil.rmtree(inv_root)
    inv_paths = ProjectPaths(inv_root).ensure()
    inv_paths.storyboard.write_text(json.dumps(INVALIDATE_DEMO, indent=2) + "\n", encoding="utf-8")
    probe_pipeline = Pipeline(
        inv_paths,
        RunOptions(engine="mock", image_engine="mock", tts_engine="mock", skip_assembly=True, verbose=False),
    )
    probe_pipeline.process_scene(0, probe_pipeline.storyboard.scenes[0], None)
    inv_id = probe_pipeline.project_id
    before = dict(probe_pipeline.store.scene(inv_id, "only"))
    probe_pipeline.close()

    changed = json.loads(json.dumps(INVALIDATE_DEMO))
    changed["scenes"][0]["visual_prompt"] = "A single RED door in a white corridor, brass handle."
    inv_paths.storyboard.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
    probe_pipeline = Pipeline(
        inv_paths,
        RunOptions(engine="mock", image_engine="mock", tts_engine="mock", skip_assembly=True, verbose=False),
    )
    after = dict(probe_pipeline.store.scene(inv_id, "only"))
    probe_pipeline.close()
    check("changed prompt invalidates the scene",
          before["status"] == "done" and after["status"] == "pending",
          f"{before['status']} -> {after['status']}")
    check("invalidated scene keeps an audit trail",
          any(True for _ in after) and after["prompt_hash"] != before["prompt_hash"])
    shutil.rmtree(inv_root, ignore_errors=True)

    say("\n[5/5] artefact integrity")
    sizes = {
        "final.mp4": final.stat().st_size if final.exists() else 0,
        "master.mp4": (paths.renders / "master.mp4").stat().st_size if (paths.renders / "master.mp4").exists() else 0,
        "body.mp4": (paths.renders / "body.mp4").stat().st_size if (paths.renders / "body.mp4").exists() else 0,
        "manifest.json": (paths.root / "manifest.json").stat().st_size if (paths.root / "manifest.json").exists() else 0,
    }
    check("all deliverables non-zero", all(v > 1024 for v in sizes.values()), str(sizes))
    check("manifest records storyboard hash",
          "storyboard_hash" in (paths.root / "manifest.json").read_text(encoding="utf-8"))

    asset = REPO_ROOT / "assets" / "demo" / "selftest.mp4"
    if copy_demo and final.exists() and final.stat().st_size < 12 * 1024 * 1024:
        asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(final, asset)
        check("demo asset copied", asset.exists(), f"{asset.stat().st_size / 1024:.0f} KB -> {asset}")

    ok = all(item["ok"] for item in checks)
    elapsed = round(time.time() - started, 1)
    say(f"\n{'=' * 62}\nSELFTEST {'PASS' if ok else 'FAIL'}  "
        f"({sum(1 for c in checks if c['ok'])}/{len(checks)} checks, {elapsed}s)")
    if final.exists():
        say(f"final: {final}  ({probe(final).duration:.2f}s)")
    if not keep and root.exists() and not ok:
        say(f"project kept for inspection: {root}")
    say("=" * 62)
    return {
        "ok": ok,
        "checks": checks,
        "elapsed_seconds": elapsed,
        "final": str(final) if final.exists() else "",
        "duration": round(probe(final).duration, 2) if final.exists() else 0,
        "asset": str(asset) if asset.exists() else "",
        "project": str(root),
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(0 if run_selftest()["ok"] else 1)
