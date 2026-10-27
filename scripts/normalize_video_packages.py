#!/usr/bin/env python3
"""Clean factual text from image prompts and make keyframes standalone.

Reproducible normalizer for the channel packages. Narrative source caveats stay in
source_notes/PRODUCTION_NOTES.md; image prompts describe pixels only.
"""

from __future__ import annotations

import json
from pathlib import Path

VISUALS = {
    "koh-chang-ghost-ship": {
        "block_01_hook": "Aerial view of a quiet tropical lagoon, jungle shoreline, and the cleared former ship-hotel site.",
        "block_02_map": "A clean cartographic map of Thailand, Koh Chang, and the southern Bang Bao coast with one simple location marker.",
        "block_03_name": "Archival-style reconstruction of a seven-deck landing ship converted into a lagoon hotel, framed by tropical forest.",
        "block_04_resort": "Vintage resort view of tropical chalets, still lagoon water, and dense island greenery beside a ship-shaped hotel.",
        "block_05_closure": "Faded archival resort photograph dissolving visually into a quiet, smoke-free shoreline after the fire.",
        "block_06_fire": "Distant documentary view of a ship-shaped hotel fire aftermath against a tropical lagoon, without people in frame.",
        "block_07_aftermath": "Present-day shoreline and lagoon landscape at the former resort site, dense tropical greenery in the background.",
        "block_08_comparison": "Underwater wide view of HTMS Chang, a different upright tank landing ship wreck on a sandy seabed with fish nearby.",
        "block_08_rumors": "A restrained evidence-board composition with a lagoon photograph, blank paper cards, and a neutral archival texture.",
        "block_09_coordinates": "Minimal map close-up with a single highlighted Koh Chang pin and spacious coordinate callout area.",
        "block_10_access": "A safe public beach viewpoint looking toward tropical coastal grounds, with no people entering structures.",
        "block_11_payoff": "The tropical lagoon and empty former ship-hotel site at dusk, shoreline framed by dark jungle.",
        "block_12_loop": "Aerial view of a quiet tropical lagoon, jungle shoreline, and the cleared former ship-hotel site.",
    },
    "flannan-coat": {
        "block_01_hook": "Aerial view of the white lighthouse on Eilean Mòr above a slate-blue North Atlantic sea.",
        "block_02_map": "A clean cartographic map of Scotland, the Outer Hebrides, Lewis, and Eilean Mòr with a highlighted island marker.",
        "block_03_keepers": "Three period-accurate Victorian lighthouse keepers shown as restrained silhouettes on a windswept island.",
        "block_04_discovery": "A small 1900s lighthouse tender approaching the rugged landing of Eilean Mòr in a heavy Atlantic swell.",
        "block_05_coat": "A plain Victorian waterproof coat hanging alone on a wooden hook inside a stone lighthouse passage.",
        "block_06_damage": "A weathered stone landing, bent iron railings, and rough Atlantic water below a steep island slope.",
        "block_07_theory": "A towering Atlantic wave washing over dark rocks beneath a distant lighthouse, viewed from a safe wide angle.",
        "block_08_myth": "Three blank archival-style evidence cards on a dark desk beside an empty slate and soft lantern light.",
        "block_09_log": "An empty writing slate and closed archive folders on a Victorian wooden desk in warm lamplight.",
        "block_10_meaning": "A carefully arranged evidence board with separate blank panels for known, inferred, and unresolved clues.",
        "block_11_unknown": "The white lighthouse as a small silhouette against an expansive cold North Atlantic horizon at dusk.",
        "block_12_loop": "Aerial view of the white lighthouse on Eilean Mòr above a slate-blue North Atlantic sea.",
    },
    "silent-evidence-ninth-legion": {
        "block_01_hook": "Aerial view of York's Roman-era stone fortress gate at dawn, with modern buildings kept out of frame.",
        "block_02_inscription": "Close-up of a weathered Roman stone building inscription in a museum-like neutral setting.",
        "block_03_york": "A period reconstruction of Eboracum's legionary fortress, stone gateway and orderly Roman military buildings.",
        "block_04_tiles": "Roman roof tiles stamped with legionary marks arranged on a dark archaeological work surface.",
        "block_05_departure": "A parchment-colored archive table with a sequence of dated Roman records ending in an open blank space.",
        "block_06_nijmegen": "A clean map linking York in Britain to Nijmegen on the Rhine frontier with a fine route line.",
        "block_07_detachment": "A small Roman legionary detachment crossing a Rhine-region road, shown as a historically grounded reconstruction.",
        "block_08_hadrian": "Roman surveyors and soldiers beside an early frontier construction site in northern Britain.",
        "block_09_scotland": "Two restrained evidence panels showing northern Britain and the Rhine, with no battle scene or outcome asserted.",
        "block_10_evidence": "Archaeologist's gloved hands examining a tile stamp and fragmentary inscription under soft raking light.",
        "block_11_unknown": "A quiet Roman stone road disappearing into mist beyond the frontier landscape.",
        "block_12_loop": "Aerial view of York's Roman-era stone fortress gate at dawn, with modern buildings kept out of frame.",
    },
}

STYLE = {
    "koh-chang-ghost-ship": {
        "location": "Koh Chang, Trat Province, Thailand",
        "lens": "24mm documentary lens, eye-level or aerial as appropriate",
        "light": "humid late-afternoon tropical light with soft haze",
        "palette": "emerald jungle, lagoon teal, muted amber highlights, natural contrast",
    },
    "flannan-coat": {
        "location": "Eilean Mòr, Flannan Isles, Outer Hebrides, Scotland",
        "lens": "35mm documentary lens, natural perspective",
        "light": "cold overcast North Atlantic daylight with a restrained lantern glow",
        "palette": "slate blue-gray sea, weathered white stone, muted lantern amber",
    },
    "silent-evidence-ninth-legion": {
        "location": "Eboracum (Roman York), Britannia; map scenes also show Nijmegen, Germania Inferior",
        "lens": "35mm documentary lens, natural perspective",
        "light": "soft dawn or museum raking light, historically plausible and restrained",
        "palette": "Roman stone gray, parchment ochre, muted bronze, subdued iron red",
    },
}


def prepare_assets(package_dir: Path) -> None:
    frames = package_dir / "assets" / "frames"
    clips = package_dir / "assets" / "clips"
    frames.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    (frames / ".gitkeep").write_text("", encoding="utf-8")
    (clips / ".gitkeep").write_text("", encoding="utf-8")
    (package_dir / "assets" / "README.md").write_text(
        "# Asset intake convention\n\n"
        "Place one generated/reference keyframe per storyboard block at `frames/frame_01.png` through `frame_12.png`. "
        "Place optional generated video at `clips/block_01_<block-suffix>.mp4` through `block_12_<block-suffix>.mp4`. "
        "The intake tool can synthesize a Ken Burns fallback clip from each available frame. Do not commit empty/fake media; `.gitkeep` only preserves the folders.\n\n"
        "Run `python scripts/ingest_assets.py <package-dir>` after adding files. PNG/MP4 assets are covered by Git LFS patterns in the repository `.gitattributes`.\n",
        encoding="utf-8",
    )


def normalize(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    folder = path.parent.name
    style = STYLE[folder]
    shots = VISUALS[folder]
    blocks = doc["blocks"]
    for block in blocks:
        block_id = block["id"]
        scene = shots.get(block_id)
        if not scene:
            raise ValueError(f"No visual-only scene description for {folder}/{block_id}")
        block["visual_prompt"] = scene
        block["source_notes"] = " ".join(
            value for value in (doc.get("important_factual_note", ""), block.get("source_notes", "")) if value
        )
        loc = block.get("location") or style["location"]
        if block_id == "block_08_comparison":
            loc = "HTMS Chang wreck site off Koh Chang, Trat Province, Thailand"
            block["location"] = loc
        camera = block.get("camera_motion", "")
        start_composition = f"{scene} Opening composition, stable framing."
        if camera:
            start_composition = f"{scene} Opening composition: {camera}."
        block["first_frame_prompt"] = (
            f"Nano Banana Pro, photoreal documentary still, vertical 9:16. Location: {loc}. "
            f"Subject and composition: {start_composition} Lens: {style['lens']}. "
            f"Light: {style['light']}. Palette: {style['palette']}. Naturalistic detail, no typography, no watermark."
        )
        block["last_frame_prompt"] = (
            f"Nano Banana Pro, photoreal documentary still, vertical 9:16. Location: {loc}. "
            f"Subject and composition: {scene} Closing composition, gently tighter framing with a settled camera. "
            f"Lens: {style['lens']}. Light: {style['light']}. Palette: {style['palette']}. "
            "Naturalistic detail, no typography, no watermark."
        )
        block["continuity"] = (
            "Frame-chain metadata: when generating video, pass the previous clip's decoded final frame as a separate reference image if the selected endpoint supports it. This prompt is standalone and does not assume hidden context."
        )
    # Enforce the loop by making the final target image prompt byte-for-byte equal
    # to block 01's opening prompt. Both are self-contained generation prompts.
    blocks[-1]["last_frame_prompt"] = blocks[0]["first_frame_prompt"]
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages", nargs="*", default=["video_packages/koh-chang-ghost-ship", "video_packages/flannan-coat"]
    )
    args = parser.parse_args()
    for package in args.packages:
        package_dir = Path(package)
        normalize(package_dir / "storyboard.json")
        prepare_assets(package_dir)
    print(f"Normalized {len(args.packages)} storyboard(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
