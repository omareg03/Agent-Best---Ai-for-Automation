"""Unit + integration tests for the render pipeline.

These run in CI in under a minute. They deliberately test the parts that break in
production -- timing arithmetic, subtitle escaping, invalidation, resume, seam
measurement -- rather than the parts that are easy to test.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.video_pipeline import captions, media, storyboard as sb
from scripts.video_pipeline.align import estimate_word_timings, syllables
from scripts.video_pipeline.captions import Word, build_ass, build_srt, group_words_into_cues
from scripts.video_pipeline.config import ProjectPaths
from scripts.video_pipeline.ffmpeg_util import (
    boundary_distance,
    dhash,
    ffmpeg_bin,
    probe,
    run_ffmpeg,
    sha256_file,
)
from scripts.video_pipeline.state import StateStore


def ffmpeg_available() -> bool:
    try:
        ffmpeg_bin()
        return True
    except Exception:  # noqa: BLE001
        return False


class TestAlignment(unittest.TestCase):
    def test_syllables_never_zero(self):
        for word in ("a", "I", "rhythm", "...", "strength"):
            self.assertGreaterEqual(syllables(word), 1, word)

    def test_timings_are_monotonic_and_bounded(self):
        text = "Every town keeps one light on. This one kept it eleven years."
        duration = 4.4
        words = estimate_word_timings(text, duration)
        self.assertEqual(len(words), len(text.split()))
        for index, word in enumerate(words):
            self.assertLessEqual(word.start, word.end)
            self.assertLess(word.end, duration + 0.01, f"{word} exceeds audio duration")
            if index:
                self.assertGreaterEqual(word.start, words[index - 1].start)

    def test_punctuation_creates_a_pause(self):
        words = estimate_word_timings("Stop. Now.", 2.0)
        gap = words[1].start - words[0].end
        self.assertGreater(gap, 0.05, "a full stop should introduce a pause")

    def test_empty_text(self):
        self.assertEqual(estimate_word_timings("", 3.0), [])


class TestCaptions(unittest.TestCase):
    def test_cue_grouping_respects_limits(self):
        words = [Word(f"w{i}", i * 0.4, i * 0.4 + 0.35) for i in range(40)]
        cues = group_words_into_cues(words, max_words=7, max_chars=42)
        self.assertTrue(cues)
        for cue in cues:
            self.assertLessEqual(len(cue.words), 7)
            self.assertLessEqual(len(cue.text), 60)  # 42 + word overshoot allowance
        self.assertEqual(len([w for c in cues for w in c.words]), 40, "no words may be dropped")

    def test_ass_escapes_override_tags(self):
        word = Word("a{b}\\Nc", 0.0, 0.5)
        document = build_ass([captions.Cue(0, 0.5, word.text, [word])], width=1280, height=720)
        dialogue = [ln for ln in document.splitlines() if ln.startswith("Dialogue:")][0]
        body = dialogue.split(",,", 1)[-1]
        self.assertNotIn("{b}", body)
        self.assertIn("(b)", body)

    def test_ass_time_format(self):
        self.assertEqual(captions.ass_time(0), "0:00:00.00")
        self.assertEqual(captions.ass_time(61.5), "0:01:01.50")
        self.assertEqual(captions.ass_time(3661.25), "1:01:01.25")

    def test_srt_contains_indices_and_arrows(self):
        words = [Word("hello", 0.0, 0.4), Word("world", 0.4, 0.9)]
        srt = build_srt(group_words_into_cues(words))
        self.assertIn("-->", srt)
        self.assertTrue(srt.strip().startswith("1"))

    def test_wrapping_never_breaks_a_word(self):
        text = " ".join(["extraordinarily"] * 6)
        wrapped = captions.wrap_text(text, max_chars=20)
        for line in wrapped.splitlines():
            self.assertIn(line.strip(), text.split())


class TestStoryboardValidation(unittest.TestCase):
    def base(self) -> dict:
        return {
            "title": "T",
            "scenes": [{"scene_id": "a", "visual_prompt": "a shot"}],
        }

    def test_minimal_is_valid(self):
        self.assertEqual(sb.validate_payload(self.base()), [])

    def test_missing_title(self):
        payload = self.base()
        payload["title"] = "  "
        self.assertTrue(any("title" in p for p in sb.validate_payload(payload)))

    def test_duplicate_scene_ids(self):
        payload = self.base()
        payload["scenes"].append({"scene_id": "a", "visual_prompt": "another"})
        self.assertTrue(any("duplicate" in p for p in sb.validate_payload(payload)))

    def test_odd_width_rejected(self):
        payload = self.base()
        payload["width"] = 1281
        self.assertTrue(any("even" in p for p in sb.validate_payload(payload)))

    def test_bad_transition(self):
        payload = self.base()
        payload["scenes"][0]["transition"] = "wipe"
        self.assertTrue(any("transition" in p for p in sb.validate_payload(payload)))

    def test_hash_changes_with_prompt(self):
        a, b = self.base(), self.base()
        b["scenes"][0]["visual_prompt"] = "a different shot"
        sb_a, sb_b = _load(a), _load(b)
        self.assertNotEqual(sb_a.scene_hashes(), sb_b.scene_hashes())

    def test_hash_includes_prompt_templates(self):
        """Editing prompts/*.md must invalidate renders (fingerprint is in the hash)."""
        board = _load(self.base())
        fingerprint_a = sb.prompt_template_fingerprint()
        explicit = board.scenes[0].prompt_hash(template_fingerprint="deadbeef")
        implicit = board.scenes[0].prompt_hash(template_fingerprint=fingerprint_a)
        self.assertNotEqual(explicit, implicit)

    def test_duration_estimates_follow_narration(self):
        payload = self.base()
        payload["scenes"][0]["voiceover_text"] = " ".join(["word"] * 25)  # ~10s at 150wpm
        summary = sb.plan_summary(_load(payload))
        self.assertGreater(summary["scenes"][0]["narration_est_s"], 8)


def _load(payload: dict) -> sb.Storyboard:
    path = Path(tempfile.mkdtemp()) / "storyboard.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return sb.load(path)


class TestStateResume(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = StateStore(self.tmp / "state.db")
        self.pid = self.store.upsert_project("t", storyboard_hash="h")
        self.clip = self.tmp / "clip.mp4"
        self.clip.write_bytes(b"0" * 4096)
        self.narr = self.tmp / "n.wav"
        self.narr.write_bytes(b"0" * 4096)
        self.store.register_scenes(
            self.pid, [{"scene_id": "a", "ordinal": 0, "prompt_hash": "h1", "seed": 1}]
        )

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _finish(self, scene_id="a"):
        self.store.update_scene(
            self.pid, scene_id, status="done",
            clip_path=str(self.clip), narration_path=str(self.narr),
        )

    def test_done_scene_is_reusable(self):
        self._finish()
        row = self.store.scene(self.pid, "a")
        ok, reason = self.store.is_reusable(row, prompt_hash="h1", engine="mock")
        self.assertTrue(ok, reason)

    def test_missing_file_invalidates(self):
        self._finish()
        self.clip.unlink()
        row = self.store.scene(self.pid, "a")
        ok, reason = self.store.is_reusable(row, prompt_hash="h1", engine="mock")
        self.assertFalse(ok)
        self.assertIn("gone", reason)

    def test_prompt_change_invalidates_and_audits(self):
        self._finish()
        self.store.register_scenes(self.pid, [{"scene_id": "a", "ordinal": 0, "prompt_hash": "h2", "seed": 1}])
        row = self.store.scene(self.pid, "a")
        self.assertEqual(row["status"], "pending")
        kinds = {event["kind"] for event in self.store.events(self.pid)}
        self.assertIn("invalidate", kinds)

    def test_summary_counts(self):
        self._finish()
        summary = self.store.summary(self.pid)
        self.assertEqual(summary["by_status"], {"done": 1})
        self.assertEqual(summary["pending"], [])

    def test_failed_scene_records_error(self):
        self.store.fail_scene(self.pid, "a", "boom")
        row = self.store.scene(self.pid, "a")
        self.assertEqual(row["status"], "failed")
        self.assertIn("boom", row["last_error"])


@unittest.skipUnless(ffmpeg_available(), "ffmpeg not installed")
class TestMediaIntegration(unittest.TestCase):
    """Real encodes. Slow-ish but this is the layer that actually ships pixels."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _source(self, name="src.mp4", seconds=2.0, size="320x192") -> Path:
        path = self.tmp / name
        run_ffmpeg(
            ["-f", "lavfi", "-i", f"testsrc=size={size}:rate=12", "-t", str(seconds),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
        )
        return path

    def test_fit_duration_pads_and_trims(self):
        src = self._source()
        padded = media.fit_duration(src, self.tmp / "pad.mp4", 3.0, width=320, height=192, fps=12)
        self.assertAlmostEqual(probe(padded).duration, 3.0, delta=0.15)
        trimmed = media.fit_duration(src, self.tmp / "trim.mp4", 1.2, width=320, height=192, fps=12)
        self.assertAlmostEqual(probe(trimmed).duration, 1.2, delta=0.15)

    def test_explicit_frame_rate_is_preserved(self):
        """Regression: fps=12,setpts=PTS-STARTPTS silently produced 25 fps on FFmpeg 7."""
        src = self._source()
        out = media.fit_duration(src, self.tmp / "rate.mp4", 2.0, width=320, height=192, fps=12)
        self.assertAlmostEqual(probe(out).fps, 12, delta=0.6)

    def test_mux_audio_produces_exact_length(self):
        video = media.fit_duration(self._source(), self.tmp / "v.mp4", 2.0, width=320, height=192, fps=12)
        audio = media.silence(1.2, self.tmp / "a.wav")
        segment = media.mux_audio(video, audio, self.tmp / "seg.mp4", seconds=2.0)
        info = probe(segment)
        self.assertTrue(info.has_audio)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.25)

    def test_concat_matches_expected_duration(self):
        parts = []
        for index in range(2):
            video = media.fit_duration(self._source(f"s{index}.mp4"), self.tmp / f"v{index}.mp4",
                                       1.5, width=320, height=192, fps=12)
            audio = media.silence(1.5, self.tmp / f"a{index}.wav")
            parts.append(media.mux_audio(video, audio, self.tmp / f"seg{index}.mp4", seconds=1.5))
        body = media.concat_segments(parts, self.tmp / "body.mp4", fps=12, width=320, height=192,
                                     expected_duration=3.0)
        self.assertAlmostEqual(probe(body).duration, 3.0, delta=0.35)

    def test_last_frame_extraction_and_identity(self):
        src = self._source("chain.mp4")
        frame = media.extract_last_clean_frame(src, self.tmp / "last.png")
        self.assertTrue(frame.exists())
        self.assertEqual(boundary_distance(frame, frame), 0, "identical frames must be distance 0")

    def test_black_tail_is_refused(self):
        from scripts.video_pipeline.errors import MediaError

        black = self.tmp / "black.mp4"
        run_ffmpeg(["-f", "lavfi", "-i", "color=c=black:s=320x192:d=1.0",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(black)])
        with self.assertRaises(MediaError):
            media.extract_last_clean_frame(black, self.tmp / "x.png")

    def test_dhash_detects_mirrored_structure(self):
        """A left-to-right ramp and its mirror must differ in ~every bit."""
        from PIL import Image

        ramp = Image.new("L", (160, 90))
        ramp.putdata([(x * 255) // 160 for _y in range(90) for x in range(160)])
        ramp.save(self.tmp / "ramp.png")
        ramp.transpose(Image.FLIP_LEFT_RIGHT).save(self.tmp / "mirror.png")
        self.assertGreater(boundary_distance(self.tmp / "ramp.png", self.tmp / "mirror.png"), 32)

    def test_dhash_is_exposure_invariant(self):
        """Brightness shifts must NOT look like a continuity break (that is the point)."""
        from PIL import Image, ImageEnhance

        base = Image.new("L", (160, 90))
        base.putdata([((x * 13 + y * 7) % 256) for y in range(90) for x in range(160)])
        base.save(self.tmp / "base.png")
        ImageEnhance.Brightness(base).enhance(1.25).save(self.tmp / "brighter.png")
        self.assertLessEqual(boundary_distance(self.tmp / "base.png", self.tmp / "brighter.png"), 6)

    def test_burned_captions_are_legible_mid_cue(self):
        """Caption text must reach near-white at mid-cue on a dark background.

        Regression guard for two real bugs: a 40 ms sample landing inside the
        120 ms fade (looks broken, is not) and an ASS colour-order mistake (looks
        broken, is). Sampling at mid-cue makes the assertion meaningful.
        """
        from PIL import Image

        words = [Word("Caption", 0.0, 1.0), Word("legible", 1.0, 2.0)]
        cues = group_words_into_cues(words)
        ass_path = self.tmp / "legible.ass"
        ass_path.write_text(build_ass(cues, width=320, height=192), encoding="utf-8")

        out = self.tmp / "legible.mp4"
        run_ffmpeg(
            ["-f", "lavfi", "-i", "color=c=0x1a1a24:s=320x192:d=2:r=12",
             "-vf", "ass=legible.ass", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
            cwd=str(self.tmp),
        )
        frame = self.tmp / "legible.png"
        run_ffmpeg(["-ss", "1.0", "-i", str(out), "-frames:v", "1", str(frame)])
        band = Image.open(frame).convert("L").crop((0, int(192 * 0.75), 320, 192))
        self.assertGreater(max(band.getdata()), 200, "caption text is not bright enough to read")

    def test_hashing_is_stable(self):
        src = self._source("hash.mp4")
        self.assertEqual(sha256_file(src), sha256_file(src))
        self.assertEqual(len(sha256_file(src)), 64)


class TestPromptTemplates(unittest.TestCase):
    def test_templates_exist_and_render(self):
        from scripts.video_pipeline import keyframes

        board = _load(
            {
                "title": "T",
                "style_anchor": "35mm",
                "character_sheet_prompt": "Mara",
                "negative_prompt": "text",
                "scenes": [{"scene_id": "a", "visual_prompt": "a shot", "camera_motion": "push in"}],
            }
        )
        sheet = keyframes.character_sheet_prompt(board)
        frame = keyframes.keyframe_prompt(board, board.scenes[0], which="start")
        self.assertIn("Mara", sheet)
        self.assertIn("a shot", frame)
        self.assertNotIn("{", sheet.replace("{}", ""), "unsubstituted placeholder in character sheet")

    def test_broken_template_falls_back(self):
        from scripts.video_pipeline import keyframes

        # An unknown placeholder must not raise: renders cost money.
        prompt = keyframes._safe_format("bad {unknown_field}", "fallback text", title="x")
        self.assertEqual(prompt, "fallback text")


if __name__ == "__main__":
    unittest.main(verbosity=2)
