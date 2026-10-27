"""Orchestrator: storyboard -> keyframes -> clips -> segments -> master.

Three rules are enforced here, in code rather than in documentation:

1. NARRATION FIRST. We synth the voice, measure it, and only then decide how long
   the clip must be. Models do not get to dictate pacing.
2. CHAIN BY FRAME, PROVE BY HASH. Scene N's clip starts on scene N-1's extracted
   last clean frame, and the seam is measured (dHash). A visible jump fails the run.
3. DONE MEANS REUSABLE, PROMPT MEANS RE-RENDER. Resume skips a scene only when the
   artefact exists *and* its prompt hash still matches.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import __version__
from . import align as align_mod
from . import keyframes as keyframe_mod
from . import media
from . import storyboard as sb
from .config import (
    CAPTION_TAIL,
    COMFYUI_URL,
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MAX_SCENE_SECONDS,
    MIN_SCENE_SECONDS,
    NARRATION_TAIL_PAD,
    ProjectPaths,
)
from .engines import get_video_engine
from .errors import EngineError, PipelineError, VerificationError
from .ffmpeg_util import assert_artifact, ffmpeg_bin, probe, sha256_file
from .state import StateStore, utcnow
from .tts import get_tts_engine


@dataclass
class RunOptions:
    engine: str = "mock"
    image_engine: str = ""          # "" -> auto
    tts_engine: str = ""            # "" -> auto
    align: str = "auto"
    limit: int | None = None
    force: bool = False
    fit_mode: str = "hold"          # hold | pingpong | trim
    burn_captions: bool = True
    music: str | None = None
    comfy_url: str = COMFYUI_URL
    acknowledge_unverified: bool = False
    allow_seam: bool = False        # degrade a broken shoulder to a fade instead of failing
    keep_going: bool = False
    skip_assembly: bool = False
    verbose: bool = True


class Pipeline:
    def __init__(self, paths: ProjectPaths, options: RunOptions, *, log: Callable[[str], None] | None = None):
        self.paths = paths.ensure()
        self.options = options
        self._emit = log or (print if options.verbose else (lambda *_: None))
        if not paths.storyboard.exists():
            raise PipelineError(
                f"storyboard missing: {paths.storyboard}",
                stage="prepare",
                hint="create one with: python -m scripts.video_pipeline.cli init --slug my-film",
            )
        self.storyboard = sb.load(paths.storyboard)
        self.width = self.storyboard.width or DEFAULT_WIDTH
        self.height = self.storyboard.height or DEFAULT_HEIGHT
        self.fps = self.storyboard.fps or DEFAULT_FPS

        self.image_engine_name = options.image_engine or ("mock" if options.engine == "mock" else "gemini")
        self.tts_engine_name = options.tts_engine or ("mock" if options.engine == "mock" else "kokoro")

        self.store = StateStore(self.paths.state_db)
        self.project_id = self.store.upsert_project(
            self.storyboard.effective_slug,
            title=self.storyboard.title,
            storyboard_path=str(self.paths.storyboard),
            storyboard_hash=self.storyboard.storyboard_hash(),
            fps=self.fps,
            width=self.width,
            height=self.height,
            engine=options.engine,
        )
        self.store.register_scenes(self.project_id, self.storyboard.registered_scenes())

        self.engine = get_video_engine(
            options.engine,
            comfy_url=options.comfy_url,
            acknowledge_unverified=options.acknowledge_unverified,
        )
        self.image_client = keyframe_mod.get_image_client(
            self.image_engine_name, aspect_ratio=self.storyboard.aspect_ratio
        )
        self.tts = get_tts_engine(self.tts_engine_name)

    # -- logging -----------------------------------------------------------
    def log(self, message: str) -> None:
        self._emit(f"[{time.strftime('%H:%M:%S')}] {message}")

    def close(self) -> None:
        self.store.close()

    # -- helpers -----------------------------------------------------------
    def _scene_paths(self, scene: sb.Scene, index: int) -> dict[str, Path]:
        stem = f"scene_{index:02d}_{scene.scene_id}"
        return {
            "stem": Path(stem),
            "start": self.paths.keyframes / f"{stem}_start.png",
            "end": self.paths.keyframes / f"{stem}_end.png",
            "last": self.paths.keyframes / f"{stem}_last.png",
            "raw_clip": self.paths.clips / f"{stem}.mp4",
            "fit_clip": self.paths.segments / f"{stem}_video.mp4",
            "segment": self.paths.segments / f"{stem}.mp4",
            "narration": self.paths.audio / f"{stem}.wav",
            "meta": self.paths.segments / f"{stem}.meta.json",
        }

    def _character_sheet(self) -> Path | None:
        path = self.paths.keyframes / "character_sheet.png"
        if path.exists() and not self.options.force:
            return path
        prompt = keyframe_mod.character_sheet_prompt(self.storyboard)
        if not prompt.strip():
            return None
        self.log("Stage A: generating master character/environment sheet (identity lock)")
        try:
            result = self.image_client.generate(
                prompt, path, seed=1, size=(self.width, self.height), stage_label="character sheet"
            )
        except EngineError as exc:
            self.log(f"  character sheet unavailable ({exc.message}); continuing without identity lock")
            self.store.record_event(self.project_id, None, "keyframe", f"character sheet failed: {exc.message}")
            return None
        self.store.record_event(
            self.project_id, None, "keyframe",
            f"character sheet {result.model} cost=${result.cost_usd:.4f}",
        )
        return path

    def _target_duration(self, scene: sb.Scene, narration_seconds: float) -> float:
        requested = scene.duration or 0.0
        narrated = narration_seconds + NARRATION_TAIL_PAD if narration_seconds else 0.0
        target = max(requested, narrated, MIN_SCENE_SECONDS)
        return round(min(target, MAX_SCENE_SECONDS), 3)

    def _last_frame(self, row: Any, index: int) -> Path | None:
        """The frame the next scene must start on."""
        if not row or not row["clip_path"]:
            return None
        segment = Path(row["clip_path"])
        if not segment.exists():
            return None
        scene = self.storyboard.scenes[index]
        cached = self._scene_paths(scene, index)["last"]
        if cached.exists() and not self.options.force:
            return cached
        return media.extract_last_clean_frame(segment, cached)

    # -- per-scene ---------------------------------------------------------
    def process_scene(self, index: int, scene: sb.Scene, previous_last: Path | None) -> dict[str, Any]:
        paths = self._scene_paths(scene, index)
        prompt_hash = scene.prompt_hash(
            style_anchor=self.storyboard.style_anchor,
            character_sheet=self.storyboard.character_sheet_prompt,
        )
        keyframe_prompt = keyframe_mod.keyframe_prompt(self.storyboard, scene, which="start")
        end_prompt = keyframe_mod.keyframe_prompt(self.storyboard, scene, which="end")
        row = self.store.scene(self.project_id, scene.scene_id)

        reusable, reason = (
            self.store.is_reusable(row, prompt_hash=prompt_hash, engine=self.options.engine)
            if row and not self.options.force
            else (False, "forced" if self.options.force else "new")
        )
        if reusable:
            self.log(f"scene {index + 1:02d} {scene.scene_id}: reuse ({reason})")
            meta_file = paths["meta"]
            if meta_file.exists():
                return json.loads(meta_file.read_text(encoding="utf-8"))
            return {"scene_id": scene.scene_id, "reused": True, "segment": str(row["clip_path"])}
        if not reusable and row is not None:
            self.store.record_event(self.project_id, scene.scene_id, "resume", f"re-render: {reason}")

        self.log(f"scene {index + 1:02d} {scene.scene_id}: rendering ({reason})")
        self.store.begin_scene(self.project_id, scene.scene_id, engine=self.options.engine, model=self.engine.name)
        cost = 0.0
        try:
            # ---- Stage A: keyframes -------------------------------------
            reference = self._character_sheet()
            keep_start = paths["start"].exists() and not self.options.force
            if not keep_start:
                result = self.image_client.generate(
                    keyframe_prompt, paths["start"],
                    references=[reference] if reference else None,
                    seed=scene.seed or index + 10,
                    size=(self.width, self.height),
                    stage_label=f"{scene.scene_id} start",
                )
                cost += result.cost_usd
            if not (paths["end"].exists() and not self.options.force):
                result = self.image_client.generate(
                    end_prompt, paths["end"],
                    references=[reference, paths["start"]] if reference else [paths["start"]],
                    seed=(scene.seed or index + 10) + 1,
                    size=(self.width, self.height),
                    stage_label=f"{scene.scene_id} end",
                )
                cost += result.cost_usd

            # Chaining is authoritative: the previous clip's real last frame wins
            # over the imagined start frame, otherwise every seam is a gamble.
            chain_start = previous_last if previous_last and previous_last.exists() else paths["start"]
            self.store.update_scene(
                self.project_id, scene.scene_id,
                keyframe_start=str(paths["start"]),
                keyframe_start_sha=sha256_file(paths["start"]),
                keyframe_end=str(paths["end"]),
                keyframe_end_sha=sha256_file(paths["end"]),
            )

            # ---- Stage B: narration (before video: durations must be known) ----
            narration_words: list[align_mod.Word] = []
            if scene.voiceover_text.strip():
                tts_result = self.tts.synthesize(
                    scene.voiceover_text, paths["narration"],
                    voice=self.storyboard.voice, seed=index,
                )
                narration_seconds = tts_result.duration
                narration_words = tts_result.words
                words_method = "engine" if tts_result.exact_timings else "estimate"
                if self.options.align != "estimate" and not tts_result.exact_timings:
                    refined, method = align_mod.align(
                        paths["narration"], scene.voiceover_text, narration_seconds,
                        method=self.options.align, language=self.storyboard.language,
                    )
                    narration_words, words_method = refined, method
                cost += tts_result.cost_usd
            else:
                narration_seconds = scene.duration or 3.0
                media.silence(narration_seconds, paths["narration"])
                words_method = "none"

            target = self._target_duration(scene, narration_seconds)
            self.store.update_scene(
                self.project_id, scene.scene_id,
                narration_path=str(paths["narration"]),
                narration_sha=sha256_file(paths["narration"]),
                narration_duration=round(narration_seconds, 3),
            )

            # ---- Stage B: video -----------------------------------------
            self.store.set_status(self.project_id, scene.scene_id, "video")
            request = self.engine_request(scene, index, paths, chain_start, target)
            video = self.engine.generate(request)
            cost += video.cost_usd

            boundary = -1
            try:
                boundary, _ = media.check_boundary(
                    chain_start, video.path, label=f"scene {scene.scene_id}"
                )
            except VerificationError as exc:
                if not self.options.allow_seam:
                    raise
                self.log(f"  WARNING: seam too large, degrading to fade ({exc.message})")

            fitted = media.fit_duration(
                video.path, paths["fit_clip"], target,
                mode=self.options.fit_mode, width=self.width, height=self.height, fps=self.fps,
            )
            if boundary > 12 or scene.transition == "fade":
                fitted = media.apply_edge_fades(fitted, paths["fit_clip"].with_suffix(".faded.mp4"), fps=self.fps)

            # ---- Stage C: audio attach ----------------------------------
            self.store.set_status(self.project_id, scene.scene_id, "audio")
            segment = media.mux_audio(fitted, paths["narration"], paths["segment"], seconds=target)
            last_frame = media.extract_last_clean_frame(segment, paths["last"])

            segment_info = probe(segment)
            self.store.update_scene(
                self.project_id, scene.scene_id,
                status="done",
                clip_path=str(segment),
                clip_sha=sha256_file(segment),
                clip_duration=round(segment_info.duration, 3),
                cost_usd=round(cost, 4),
                finished_at=utcnow(),
            )
            self.store.record_event(
                self.project_id, scene.scene_id, "video",
                f"{self.options.engine} {target:.2f}s seam_dHash={boundary} cost=${cost:.4f}",
            )

            meta = {
                "scene_id": scene.scene_id,
                "index": index,
                "engine": self.options.engine,
                "model": video.model,
                "target_seconds": target,
                "narration_seconds": round(narration_seconds, 3),
                "narration_words": [w.__dict__ for w in narration_words],
                "words_method": words_method,
                "boundary_dhash": boundary,
                "engine_meta": video.meta,
                "cost_usd": round(cost, 4),
                "segment": str(segment),
                "clip_sha": sha256_file(segment),
                "start_frame": str(chain_start),
                "last_frame": str(last_frame),
                "fitted": str(fitted),
                "raw_clip": str(video.path),
                "created_at": utcnow(),
            }
            paths["meta"].write_text(json.dumps(meta, indent=2), encoding="utf-8")
            return meta

        except Exception as exc:  # noqa: BLE001 - state must survive any backend failure
            message = exc.render() if isinstance(exc, PipelineError) else f"{type(exc).__name__}: {exc}"
            self.store.fail_scene(self.project_id, scene.scene_id, message)
            self.store.record_event(self.project_id, scene.scene_id, "error", message)
            self.log(f"  FAILED scene {scene.scene_id}: {message.splitlines()[0]}")
            raise

    def engine_request(self, scene: sb.Scene, index: int, paths: dict[str, Path], chain_start: Path, target: float):
        from .engines import VideoRequest

        return VideoRequest(
            scene_id=scene.scene_id,
            prompt=scene.rendering_prompt(
                style_anchor=self.storyboard.style_anchor,
                character_sheet=self.storyboard.character_sheet_prompt,
            ),
            out_path=paths["raw_clip"],
            duration=target,
            start_frame=chain_start,
            end_frame=paths["end"],
            negative_prompt=self.storyboard.negative_prompt,
            seed=scene.seed or index + 10,
            width=self.width,
            height=self.height,
            fps=self.fps,
            camera_motion=scene.camera_motion,
        )

    # -- full run ----------------------------------------------------------
    def run(self) -> dict[str, Any]:
        started = time.time()
        self.log(
            f"project '{self.storyboard.title}' | {len(self.storyboard.scenes)} scenes | "
            f"engine={self.options.engine} images={self.image_engine_name} tts={self.tts_engine_name} "
            f"| {self.width}x{self.height}@{self.fps}"
        )
        failures: list[dict[str, str]] = []
        previous_last: Path | None = None
        processed = 0
        for index, scene in enumerate(self.storyboard.scenes):
            if self.options.limit is not None and processed >= self.options.limit:
                self.log(f"stopping after --limit {self.options.limit} scene(s)")
                break
            try:
                self.process_scene(index, scene, previous_last)
                processed += 1
            except Exception as exc:  # noqa: BLE001
                message = exc.render() if isinstance(exc, PipelineError) else str(exc)
                failures.append({"scene_id": scene.scene_id, "error": message})
                # A failed scene must not become the anchor for the next one:
                # chaining from the wrong frame is worse than a clean cut.
                previous_last = None
                if not self.options.keep_going:
                    break
            row = self.store.scene(self.project_id, scene.scene_id)
            if row and row["status"] == "done":
                previous_last = self._last_frame(row, index)

        report: dict[str, Any] = {
            "project": self.storyboard.effective_slug,
            "engine": self.options.engine,
            "scenes_processed": processed,
            "failures": failures,
            "state": self.store.summary(self.project_id),
            "elapsed_seconds": round(time.time() - started, 1),
        }
        if not failures and not self.options.skip_assembly:
            report["assembly"] = self.assemble()
        elif failures:
            self.log("assembly skipped: fix the failed scenes, then re-run (state is saved)")
        report["manifest"] = str(self.write_manifest(report))
        return report

    # -- assembly ----------------------------------------------------------
    def assemble(self) -> dict[str, Any]:
        self.log("Stage C: assembling master")
        rows = {row["scene_id"]: row for row in self.store.scenes(self.project_id)}
        segments: list[Path] = []
        expected = 0.0
        for index, scene in enumerate(self.storyboard.scenes):
            row = rows.get(scene.scene_id)
            if not row or row["status"] != "done" or not row["clip_path"]:
                raise PipelineError(
                    f"cannot assemble: scene '{scene.scene_id}' is not done",
                    stage="assemble",
                    hint="run `resume` first; assembly never ships a partial film",
                )
            segment = Path(row["clip_path"])
            assert_artifact(segment, kind=f"segment {scene.scene_id}")
            segments.append(segment)
            expected += probe(segment).duration

        body = media.concat_segments(
            segments, self.paths.renders / "body.mp4",
            fps=self.fps, width=self.width, height=self.height, expected_duration=expected,
        )
        self.store.record_render(self.project_id, "body", body, sha256_file(body), body.stat().st_size, probe(body).duration)
        self.log(f"  body: {probe(body).duration:.2f}s from {len(segments)} segments")

        master_src = body
        music = self.options.music or self.storyboard.music
        if music:
            music_path = Path(music)
            if not music_path.is_absolute():
                music_path = self.paths.root / music_path
            if music_path.exists():
                with_music = media.mix_music(body, music_path, self.paths.renders / "body_music.mp4")
                master_src = with_music
                self.log("  music bed mixed with sidechain ducking")
            else:
                self.log(f"  music not found ({music_path}); continuing without it")

        master = media.loudnorm_two_pass(master_src, self.paths.renders / "master.mp4")
        self.store.record_render(self.project_id, "master", master, sha256_file(master), master.stat().st_size, probe(master).duration)

        captions = self._build_global_captions(rows, segments)
        if self.options.burn_captions and captions.get("ass"):
            final = media.burn_subtitles(master, Path(captions["ass"]), self.paths.renders / "final.mp4", fps=self.fps)
        else:
            final = master
        thumb = media.thumbnail(final, self.paths.renders / "thumbnail.jpg")

        self.store.record_render(self.project_id, "final", final, sha256_file(final), final.stat().st_size, probe(final).duration)
        self.store.record_event(self.project_id, None, "assemble", f"final {probe(final).duration:.2f}s")
        self.log(f"  final: {final} ({probe(final).duration:.2f}s)")
        return {
            "final": str(final),
            "master": str(master),
            "thumbnail": str(thumb),
            "duration": round(probe(final).duration, 3),
            "captions": captions,
        }

    def _build_global_captions(self, rows: dict[str, Any], segments: list[Path]) -> dict[str, Any]:
        from .captions import Word, write_captions

        words: list[Word] = []
        cursor = 0.0
        method = "none"
        for index, scene in enumerate(self.storyboard.scenes):
            paths = self._scene_paths(scene, index)
            duration = probe(segments[index]).duration
            meta = json.loads(paths["meta"].read_text(encoding="utf-8")) if paths["meta"].exists() else {}
            scene_words = [
                Word(text=item["text"], start=item["start"] + cursor, end=item["end"] + cursor)
                for item in meta.get("narration_words", [])
            ]
            if scene_words:
                words.extend(scene_words)
                method = meta.get("words_method", method)
            cursor += duration

        full_text = " ".join(s.voiceover_text for s in self.storyboard.scenes if s.voiceover_text)
        if not words and not full_text:
            return {"method": "none", "ass": "", "srt": "", "cues": 0}
        result = write_captions(
            words,
            out_dir=self.paths.subtitles,
            stem=self.storyboard.effective_slug,
            width=self.width,
            height=self.height,
            fallback_text=full_text,
            total_duration=cursor,
        )
        self.log(f"  captions: {result['cues']} cues ({method}, {len(words)} words)")
        return {
            "method": method,
            "ass": str(result["ass"]),
            "srt": str(result["srt"]),
            "cues": result["cues"],
        }

    # -- manifest + verification -------------------------------------------
    def write_manifest(self, report: dict[str, Any]) -> Path:
        rows = [dict(row) for row in self.store.scenes(self.project_id)]
        manifest = {
            "pipeline_version": __version__,
            "generated_at": utcnow(),
            "storyboard_hash": self.storyboard.storyboard_hash(),
            "title": self.storyboard.title,
            "slug": self.storyboard.effective_slug,
            "format": {"width": self.width, "height": self.height, "fps": self.fps},
            "engine": self.options.engine,
            "image_engine": self.image_engine_name,
            "tts_engine": self.tts_engine_name,
            "ffmpeg": ffmpeg_version(),
            "scenes": rows,
            "summary": self.store.summary(self.project_id),
            "run": report,
        }
        path = self.paths.root / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        return path

    def verify(self) -> dict[str, Any]:
        """Post-render gate. This is what CI runs before publishing."""
        issues: list[str] = []
        rows = {row["scene_id"]: row for row in self.store.scenes(self.project_id)}
        if not rows:
            issues.append("no scenes registered -- run the pipeline first")

        boundary_max = 0
        for index, scene in enumerate(self.storyboard.scenes):
            row = rows.get(scene.scene_id)
            label = scene.scene_id
            if row is None:
                issues.append(f"{label}: not registered")
                continue
            if row["status"] != "done":
                issues.append(f"{label}: status={row['status']} ({row['last_error'] or 'no error recorded'})")
                continue
            for column in ("clip_path", "narration_path"):
                value = row[column]
                if not value or not Path(value).exists():
                    issues.append(f"{label}: {column} missing")
                elif Path(value).stat().st_size < 1024:
                    issues.append(f"{label}: {column} is suspiciously small")
            paths = self._scene_paths(scene, index)
            if paths["meta"].exists():
                meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
                boundary_max = max(boundary_max, int(meta.get("boundary_dhash") or 0))
                if (meta.get("boundary_dhash") or 0) > 12:
                    issues.append(
                        f"{label}: seam dHash {meta['boundary_dhash']} exceeds 12 (visible jump)"
                    )
                if abs((meta.get("target_seconds") or 0) - (row["clip_duration"] or 0)) > 0.3:
                    issues.append(f"{label}: duration drift > 0.3s")
            else:
                issues.append(f"{label}: metadata missing (was it produced by an older version?)")

        final = self.paths.renders / "final.mp4"
        if not final.exists():
            issues.append("renders/final.mp4 missing")
        else:
            info = probe(final)
            total = sum(row["clip_duration"] or 0 for row in rows.values())
            if not info.has_audio:
                issues.append("final.mp4 has no audio track")
            if total and abs(info.duration - total) > max(1.0, total * 0.02):
                issues.append(f"final duration {info.duration:.1f}s != segments {total:.1f}s")
            if (info.width, info.height) != (self.width, self.height):
                issues.append(f"final is {info.width}x{info.height}, expected {self.width}x{self.height}")
            if info.fps and abs(info.fps - self.fps) > 0.6:
                issues.append(f"final is {info.fps:.1f} fps, expected {self.fps}")
            if info.duration < 60 and len(rows) > 6:
                issues.append("final is shorter than expected for a long-form render")

        captions = self.paths.subtitles / f"{self.storyboard.effective_slug}.ass"
        if self.options.burn_captions and captions.exists() and captions.stat().st_size < 120:
            issues.append("ASS subtitle file is suspiciously small")

        return {
            "ok": not issues,
            "issues": issues,
            "scenes": len(rows),
            "max_boundary_dhash": boundary_max,
            "final": str(final) if final.exists() else "",
            "final_duration": round(probe(final).duration, 2) if final.exists() else 0,
        }


def ffmpeg_version() -> str:
    try:
        import subprocess

        out = subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, text=True, timeout=20)
        return (out.stdout or "").splitlines()[0] if out.stdout else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"
