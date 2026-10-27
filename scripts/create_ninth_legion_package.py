#!/usr/bin/env python3
"""Build the source-checked 12-block Silent Evidence Ninth Legion package."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.normalize_video_packages import normalize, prepare_assets  # noqa: E402

OUT = Path("video_packages/silent-evidence-ninth-legion")
SOURCES = [
    "https://romaninscriptionsofbritain.org/inscriptions/665",
    "https://romaninscriptionsofbritain.org/instrumentum/2462",
    "https://www.cambridge.org/core/journals/britannia/article/what-happened-next-hadrians-wall-the-expeditio-britannica-and-the-fate-of-the-ninth-legion/2939F9DCC38AC465ED8D2D3B13A3A044",
    "https://www.cambridge.org/core/journals/britannia/article/abs/end-of-the-ninth-legion-war-in-britain-and-the-building-of-hadrians-wall/63F63650070022B9E59DE06BF18D8729",
]
NOTE = "Evidence note, checked 2026-10-26: RIB 665 dates the York building inscription to AD 107–108 and says the gate was built through Legion IX Hispana. RIB's tile-stamp catalogue places the Ninth's base at York from AD 71 until its probable departure toward the end of Trajan's reign, while noting stamped tiles at multiple sites. A 2025 Britannia/Cambridge article discusses possible Ninth detachments at Nijmegen in the early second century and last attested officers around AD 124; its broader Hadrianic-crisis connection is an interpretation, not proof of a specific defeat. The exact fate, battle, final headcount, and a 5,000-soldier disappearance are not established by these sources. Do not state that the entire legion was annihilated in Scotland."
BLOCKS = [
    (
        "hook",
        "The Ninth Legion's disappearance is a Roman mystery—not a confirmed massacre in Scotland.",
        "Aerial view of York's Roman-era stone fortress gate at dawn, modern buildings outside the frame.",
        "THE NINTH LEGION",
        "MYSTERY, NOT VERDICT",
        "Opening question",
    ),
    (
        "inscription",
        "At York, a stone inscription dated around one hundred seven to one hundred eight names the Ninth.",
        "Close-up of a weathered Roman stone building inscription in soft museum light.",
        "YORK INSCRIPTION",
        "AD 107–108",
        "Primary evidence",
    ),
    (
        "york",
        "It records Trajan's gate built by the agency of Legion Nine Hispana.",
        "Period reconstruction of Eboracum's stone gateway and legionary fortress buildings.",
        "RIB 665",
        "GATE BUILT BY LEGION IX",
        "York, Britannia",
    ),
    (
        "tiles",
        "Stamped roof tiles also trace the legion's long base at York and other British sites.",
        "Roman roof tiles stamped with legionary marks arranged on a dark archaeological table.",
        "LEGION IX TILES",
        "YORK • BRITAIN",
        "Material record",
    ),
    (
        "departure",
        "The inscriptions show presence. They do not describe a final battle or explain a disappearance.",
        "An archival table with dated Roman records and an open blank space at the end.",
        "RECORDS GO QUIET",
        "NO FINAL BATTLE REPORT",
        "Evidence limits",
    ),
    (
        "nijmegen",
        "Evidence from Nijmegen suggests a Ninth Legion detachment served on the Rhine in the early second century.",
        "A clean map linking York in Britain to Nijmegen on the Rhine frontier with a fine route line.",
        "YORK → NIJMEGEN",
        "A DETACHMENT?",
        "Early 2nd century",
    ),
    (
        "detachment",
        "That evidence does not prove the full legion, thousands strong, transferred as one unit.",
        "A small Roman detachment crossing a Rhine-region road, shown as a historically grounded reconstruction.",
        "PART OF A LEGION?",
        "NOT NECESSARILY ALL",
        "Interpretation",
    ),
    (
        "hadrian",
        "A 2025 study explores a possible security crisis during Hadrian's visit, but it remains an argument.",
        "Roman surveyors beside an early frontier construction site in northern Britain, overcast light.",
        "A POSSIBLE CRISIS",
        "SCHOLARLY INTERPRETATION",
        "AD 121–123",
    ),
    (
        "scotland",
        "No cited inscription proves five thousand Ninth Legion soldiers vanished in one Scottish ambush.",
        "Two restrained evidence panels showing northern Britain and the Rhine, with no battle depiction.",
        "NO PROVEN MASSACRE",
        "NO VERIFIED HEADCOUNT",
        "Myth check",
    ),
    (
        "evidence",
        "The evidence is fragments: inscriptions, tile stamps, and officers recorded into the 120s.",
        "Gloved archaeologist's hands examining a tile stamp and fragmentary inscription under raking light.",
        "STONE • TILE • NAMES",
        "LAST OFFICERS c. 124",
        "Evidence review",
    ),
    (
        "unknown",
        "After that, the trail fades. The surviving record cannot tell us exactly how the unit ended.",
        "A quiet Roman stone road disappearing into mist beyond the frontier landscape.",
        "THE FATE IS UNKNOWN",
        "ABSENCE IS NOT A STORY",
        "Conclusion",
    ),
    (
        "loop",
        "The Ninth Legion's disappearance is a Roman mystery—not a confirmed massacre in Scotland.",
        "Aerial view of York's Roman-era stone fortress gate at dawn, modern buildings outside the frame.",
        "THE NINTH LEGION",
        "WHAT HAPPENED?",
        "Loop to opening",
    ),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, (slug, narration, visual, title, detail, timeline) in enumerate(BLOCKS, 1):
        bid = f"block_{i:02d}_{slug}"
        blocks.append(
            {
                "id": bid,
                "duration_target_seconds": 5,
                "narration": narration,
                "visual_prompt": visual,
                "first_frame_prompt": "",
                "last_frame_prompt": "",
                "motion_prompt": "Five-second documentary movement: slow controlled push or pan across this scene; at t=2.5s apply a subtle 1.12x punch-in as an edit; settle the last frames.",
                "overlay_title": title,
                "overlay_detail": detail,
                "location": "Eboracum (Roman York), Britannia; selected evidence scenes reference Nijmegen, Germania Inferior",
                "timeline": timeline,
                "audio": f"audio/{bid}.wav",
                "clip": f"clips/{bid}.mp4",
                "seed": 59000 + i,
                "model_version": "RECORD_BEFORE_RENDER",
                "status": "planned",
                "source_notes": NOTE,
                "source_citations": SOURCES,
            }
        )
    storyboard = {
        "title": "The Ninth Legion: What the Evidence Says",
        "requested_title": "5,000 Roman Soldiers Marched Into Britain & Never Came Back",
        "slug": OUT.name,
        "channel": "Silent Evidence",
        "format": "YouTube Short",
        "target_duration_seconds": 60,
        "aspect_ratio": "9:16",
        "fps_master": 30,
        "audio_master": True,
        "visual_lock": "Vertical 9:16 photoreal documentary reconstruction; Roman York and northern Britain, with map references to Nijmegen; naturalistic 35mm perspective; soft dawn or museum raking light; stone gray, parchment ochre, muted bronze and subdued iron red. No supernatural imagery or invented archival objects.",
        "reference_sheet_prompt": "Nano Banana Pro reference sheet, photoreal 9:16 documentary style: (1) stone gateway and fortress of Eboracum (Roman York), (2) close-up of authentic-looking Roman tile stamps and a weathered inscribed stone (reconstruction, not a claimed artifact photograph), (3) clean map locating York and Nijmegen. Natural 35mm lens perspective, soft dawn and museum raking light, Roman stone gray, parchment ochre, muted bronze, subdued iron red. No readable fabricated inscriptions, no battle outcome, no modern landmarks.",
        "important_factual_note": NOTE,
        "source_citations": SOURCES,
        "blocks": blocks,
    }
    (OUT / "storyboard.json").write_text(
        json.dumps(storyboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    seo = {
        "channel": "Silent Evidence",
        "research_status": "Live primary-source and current scholarly check performed 2026-10-26. No paid vidIQ telemetry was available; all search volume, competition, Outlier, VPH, swipe and APV metrics remain UNVERIFIED.",
        "title_candidates": [
            {
                "title": "The Ninth Legion: What the Evidence Says",
                "characters": 40,
                "thumbnail_text": "FATE UNKNOWN",
            },
            {
                "title": "Rome's Lost Ninth: Britain or the Rhine?",
                "characters": 40,
                "thumbnail_text": "YORK 108",
            },
            {
                "title": "Did Rome's Ninth Legion Vanish in Scotland?",
                "characters": 43,
                "thumbnail_text": "TRACK THE EAGLE",
            },
        ],
        "long_tail_keywords": [
            {
                "phrase": "Ninth Legion disappearance evidence",
                "word_count": 4,
                "search_volume": "UNVERIFIED in vidIQ",
                "competition": "UNVERIFIED in vidIQ",
            },
            {
                "phrase": "Ninth Legion York inscription 108",
                "word_count": 5,
                "search_volume": "UNVERIFIED in vidIQ",
                "competition": "UNVERIFIED in vidIQ",
            },
            {
                "phrase": "Legio IX Hispana fate mystery",
                "word_count": 5,
                "search_volume": "UNVERIFIED in vidIQ",
                "competition": "UNVERIFIED in vidIQ",
            },
            {
                "phrase": "Roman Ninth Legion Nijmegen evidence",
                "word_count": 5,
                "search_volume": "UNVERIFIED in vidIQ",
                "competition": "UNVERIFIED in vidIQ",
            },
            {
                "phrase": "Ninth Legion lost battle myth",
                "word_count": 5,
                "search_volume": "UNVERIFIED in vidIQ",
                "competition": "UNVERIFIED in vidIQ",
            },
        ],
        "description": "",
        "chapters": [f"00:{i * 5:02d} {BLOCKS[i][4]}" for i in range(12)],
        "tags": [
            "Ninth Legion",
            "Legio IX Hispana",
            "Roman Britain",
            "York inscription",
            "RIB 665",
            "Roman history",
            "Ninth Legion mystery",
            "Hadrian's Wall",
            "Roman York",
            "Nijmegen archaeology",
            "ancient history",
            "history myth busting",
        ],
        "pinned_comments": [
            "The record is fragmentary, and no single fate is proven. Which clue should we examine next?",
            "If you have a primary inscription or scholarly source, share it here so we can check the evidence.",
        ],
        "measurement_targets": [
            "Outlier ≥3x: measure after posting; no forecast",
            "VPH: record at 1h, 6h and 24h",
            "Viewed vs swiped away and APV: measure in YouTube Studio; never guaranteed",
        ],
    }
    desc = (
        "Where did Rome’s Ninth Legion go? This 60-second evidence-led history Short revisits Legio IX Hispana without turning an unresolved record into a certain massacre story. A building inscription from York, dated AD 107–108, says Trajan’s gate was built through the agency of the Ninth Legion. Roman tile stamps trace the unit’s presence at York and other British sites. Evidence from Nijmegen suggests at least a detachment may have served on the Rhine frontier in the early second century—but it does not demonstrate that the complete legion moved there. A 2025 scholarly article considers whether events around Hadrian’s visit and a possible security crisis relate to the legion’s disappearance; that is a scholarly interpretation, not proof of a specific battle. The popular “5,000 soldiers vanished in Scotland” framing is not established by the cited inscriptions. The precise fate, final strength, and circumstances remain uncertain.\n\n"
        + "\n".join(seo["long_tail_keywords"][i]["phrase"] for i in range(5))
        + "\n\nChapters (Shorts beat map):\n"
        + "\n".join(seo["chapters"])
        + "\n\nPrimary and scholarly sources:\n"
        + "\n".join(SOURCES)
        + "\n\nWe distinguish primary evidence, scholarly interpretation, and unanswered questions. Reenactments are illustrative, not original archaeological footage. Subscribe to Silent Evidence for sourced historical mysteries."
    )
    while len(desc) < 2000:
        desc += "\n\nA missing name in a later document cannot by itself tell us whether a unit was destroyed, transferred, reorganized, or simply lost from the surviving record. This video does not present any one scenario as settled fact."
    seo["description"] = desc[:2490]
    seo["tags_csv"] = ", ".join(seo["tags"])
    seo["tags_character_count"] = len(seo["tags_csv"])
    (OUT / "youtube_seo.json").write_text(
        json.dumps(seo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT / "GLOBAL_VISUAL_VOICE_LOCK.md").write_text(
        "# Global visual and voice lock\n\n"
        + storyboard["visual_lock"]
        + "\n\n## Paid Nano Banana Pro reference prompt\n\n"
        + storyboard["reference_sheet_prompt"]
        + "\n",
        encoding="utf-8",
    )
    (OUT / "PRODUCTION_NOTES.md").write_text(
        "# Ninth Legion package production notes\n\n"
        + NOTE
        + "\n\nNo paid model, Manim renderer, or vidIQ account was accessed. Verify dateable claims against linked records before upload; label every reconstruction; do not claim a full-strength legion was annihilated in Scotland.\n\nAsset workflow: export keyframes to `assets/frames/frame_01.png`–`frame_12.png`, clips to `assets/clips/block_XX_*.mp4`, and narration WAVs to `audio/<block-id>.wav`; run `python scripts/validate_package.py video_packages/silent-evidence-ninth-legion`, then `python scripts/ingest_assets.py video_packages/silent-evidence-ninth-legion` before assembly.\n",
        encoding="utf-8",
    )
    normalize(OUT / "storyboard.json")
    prepare_assets(OUT)
    print(f"Created {OUT} with 12 blocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
