from __future__ import annotations

import json
from pathlib import Path

from scripts.auto_captions_4word import cues, write
from scripts.manim_blocks import generate
from scripts.pipeline_runner_api import ASSEMBLY_PROJECTS, PIPELINE_PROJECTS, build_command
from scripts.video_pipeline.ffmpeg_util import ffmpeg_bin, run_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def test_captions_never_exceed_four_words_and_stay_in_bounds(tmp_path):
    out = cues("one two three four five six seven eight nine".split(), 2.0, 4.0)
    assert all(len(item.text.split()) <= 4 for item in out)
    assert out[0].start == 2.0
    assert abs(out[-1].end - 6.0) < 1e-8
    target = tmp_path / "captions.ass"
    write(target, out)
    assert "PlayResX: 1080" in target.read_text()
    assert len([ln for ln in target.read_text().splitlines() if ln.startswith("Dialogue:")]) == len(out)


def test_manim_generator_makes_12_valid_scene_classes(tmp_path):
    board = ROOT / "video_packages/koh-chang-ghost-ship/storyboard.json"
    output = generate(board, tmp_path / "blocks.py")
    text = output.read_text()
    assert all(f"class Block{i:02d}(Scene)" in text for i in range(1, 13))
    compile(text, str(output), "exec")


def test_video_packages_have_complete_seo_and_chain_contract():
    dirs = [ROOT / "video_packages/koh-chang-ghost-ship", ROOT / "video_packages/flannan-coat"]
    for directory in dirs:
        board = json.loads((directory / "storyboard.json").read_text())
        seo = json.loads((directory / "youtube_seo.json").read_text())
        assert len(board["blocks"]) == 12
        assert len(seo["title_candidates"]) == 3
        assert all(item["characters"] < 55 for item in seo["title_candidates"])
        assert 2000 <= len(seo["description"]) <= 2500
        assert len(seo["tags_csv"]) < 500
        assert len(seo["pinned_comments"]) == 2
        assert len(seo["long_tail_keywords"]) == 5
        assert all(4 <= item["word_count"] <= 7 for item in seo["long_tail_keywords"])
        thumbs = [set(item["thumbnail_text"].lower().split()) for item in seo["title_candidates"]]
        assert not (thumbs[0] & thumbs[1] or thumbs[0] & thumbs[2] or thumbs[1] & thumbs[2])
        assert "UNVERIFIED" in seo["research_status"]
        for block in board["blocks"]:
            assert block["first_frame_prompt"] and block["last_frame_prompt"] and block["motion_prompt"]
            assert block["seed"] > 0
            assert block["audio"].endswith(".wav") and block["clip"].endswith(".mp4")
        assert board["blocks"][-1]["continuity"]


def test_manim_uses_measured_wav_duration_when_available(tmp_path):
    try:
        ffmpeg_bin()
    except Exception:
        import pytest

        pytest.skip("ffmpeg not installed")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    board_path = tmp_path / "storyboard.json"
    board_path.write_text(
        json.dumps({"blocks": [{"id": "b01", "audio": "audio/b01.wav", "duration_target_seconds": 5}]})
    )
    wav = audio_dir / "b01.wav"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "1.25",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ]
    )
    generated = generate(board_path, tmp_path / "measured.py", audio_dir=audio_dir).read_text()
    assert "self.wait(1.250000)" in generated


def test_n8n_workflow_is_valid_json_and_uses_allowlist_validation():
    workflow = json.loads((ROOT / "workflows/n8n_long_video_pipeline.json").read_text())
    names = {node["name"] for node in workflow["nodes"]}
    assert "Validate and constrain request" in names
    assert "Daily registry scout" in names
    code = next(
        node["parameters"]["jsCode"]
        for node in workflow["nodes"]
        if node["name"] == "Validate and constrain request"
    )
    assert "allowed" in code and "engine is not allowlisted" in code


def test_runner_command_uses_allowlists_and_never_a_shell():
    assert PIPELINE_PROJECTS == {"example"}
    assert "flannan-coat" in ASSEMBLY_PROJECTS
    cmd = build_command("example", "mock", resume=True, dry_run=False)
    assert "shell" not in cmd
    assert "scripts.video_pipeline.cli" in cmd
    try:
        build_command("../../etc/passwd", "mock", resume=True, dry_run=False)
    except ValueError as exc:
        assert "allowlisted" in str(exc)
    else:
        raise AssertionError("path traversal slug accepted")
    try:
        build_command("example", "arbitrary-shell", resume=True, dry_run=False)
    except ValueError as exc:
        assert "engine" in str(exc)
    else:
        raise AssertionError("unallowlisted engine accepted")
