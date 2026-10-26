#!/usr/bin/env python3
"""Rebuild the two researched, source-cited YouTube production packages."""

from __future__ import annotations

import json
from pathlib import Path

COMMON_NOTE = "A storyboard and SEO hypothesis package; no media has been rendered and no paid model/vidIQ account was accessed."
DATA = {
    "koh-chang-ghost-ship": {
        "title": "Koh Chang’s Ghost Ship: What Remains?",
        "requested_title": "The Mystery Ghost Ship Left to Rot in a Thai Jungle (Koh Chang Part 2 — Exact GPS Coordinates)",
        "channel": "Amazing Random Things",
        "slug": "koh-chang-galaxy-after-the-fire",
        "location": "Koh Chang Grand Lagoona, southern Koh Chang, Trat, Thailand",
        "coords": "11.9763° N, 102.3332° E (approximate public listing; confirm the pin before publication)",
        "note": "Important factual correction: The Galaxy ship-hotel was severely burned on 3 December 2024; a 2025 local update reports dismantling of its upper structure. Do not present the intact ship as currently standing. No current 2026 on-site inspection is available here; verify the present site, remnants and legal access before publication.",
        "lock": "Vertical 9:16 documentary travel mystery; humid Gulf of Thailand haze, emerald jungle, lagoon, weathered concrete and rust; naturalistic restrained teal/amber grade, slow stabilized camera. No supernatural apparitions, fabricated signage, trespassing, or invented present-day intact ship. Any intact Galaxy must be explicitly labeled archival reconstruction and matched to supplied licensed reference images.",
        "ref": "Create a documentary reference sheet for Koh Chang: (1) present-day southern Koh Chang lagoon and tropical shoreline, (2) a clearly labeled archival reconstruction of the former seven-deck Galaxy ship-hotel based only on supplied reference photographs, (3) a clean map panel locating Koh Chang, Trat, Thailand. Maintain realistic geography and muted emerald/teal/amber palette. No ghosts, logos, fabricated text, or implication the ship survives the 2024 fire. Use as consistent reference for all blocks.",
        "sources": [
            "https://iamkohchang.com/photos/various/galaxy-koh-chang-ghost-ship.html",
            "https://world.thaipbs.or.th/detail/koh-changs-haunted-ghost-ship-goes-up-in-flames/55670",
            "https://www.jertam.com/places/30391",
        ],
        "keywords": [
            "Koh Chang ghost ship history",
            "Galaxy Hotel Koh Chang Thailand",
            "abandoned ship Koh Chang location",
            "Koh Chang Grand Lagoona resort",
            "Thailand ghost ship fire 2024",
        ],
        "titles": [
            ("Koh Chang’s Ghost Ship: What Remains?", "SHIP GONE"),
            ("Thailand’s Jungle Ship That Vanished", "JUNGLE SECRET"),
            ("The Galaxy: Koh Chang’s Lost Ship", "FIRE CHANGED IT"),
        ],
        "tags": [
            "Koh Chang ghost ship",
            "Galaxy Hotel Koh Chang",
            "Koh Chang Thailand",
            "Grand Lagoona",
            "abandoned resort Thailand",
            "Thailand travel mystery",
            "Bang Bao Koh Chang",
            "ghost ship hotel",
            "Klong Kloi Beach",
            "travel documentary",
            "Thailand island travel",
            "ship hotel fire",
            "Trat province",
            "Koh Chang coordinates",
        ],
        "chapters": [
            "00:00 The lagoon clue",
            "00:05 Find Koh Chang",
            "00:10 The Galaxy",
            "00:15 The resort",
            "00:20 Closure",
            "00:25 The 2024 fire",
            "00:30 What remains",
            "00:35 Folklore vs fact",
            "00:40 Approximate map pin",
            "00:45 Visitor safety",
            "00:50 What disappeared",
            "00:55 Replay the clue",
        ],
        "cta": "Plan responsibly and confirm current access. Affiliate links: Airalo eSIM https://cutt.ly/air-alo | BikesBooking https://bikesbooking.tp.st/vwFzbqW5 | Travel https://amazing-a-r-t.com. Affiliate disclosure: the channel may earn a commission at no extra cost to you.",
        "blocks": [
            (
                "hook",
                "On Koh Chang, this ghost ship hotel once anchored a jungle lagoon. Now the Galaxy is gone.",
                "Aerial over tropical lagoon; reveal empty site, not intact ship.",
                "KOH CHANG • THAILAND",
                "11.9763, 102.3332*",
                "Present day",
            ),
            (
                "map",
                "Find the site near Bang Bao, on Koh Chang’s southern coast in Trat Province.",
                "Map zoom Thailand to Koh Chang and southern Bang Bao; pin marked approximate.",
                "SOUTHERN KOH CHANG",
                "APPROX. MAP PIN",
                "Location",
            ),
            (
                "name",
                "The vessel was called The Galaxy, part of the Koh Chang Grand Lagoona resort.",
                "Clearly labeled archival reconstruction of ship-hotel in lagoon.",
                "THE GALAXY",
                "ARCHIVAL RECONSTRUCTION",
                "Resort era",
            ),
            (
                "resort",
                "Guests once stayed aboard, surrounded by chalets, lagoons, and thick island jungle.",
                "Archival/reference photos of resort, use only licensed sourced images.",
                "GRAND LAGOONA",
                "SOUTHERN THAILAND",
                "Resort era",
            ),
            (
                "closure",
                "The attraction closed to guests years before a fire changed the story completely.",
                "Transition from faded archival image to fire aftermath; restrained documentary tone.",
                "CLOSED BEFORE FIRE",
                "TIMELINE MATTERS",
                "Before 2024",
            ),
            (
                "fire",
                "On December third, twenty twenty-four, a major fire engulfed the ship-hotel.",
                "Distant fire aftermath, no injuries or spectacle.",
                "3 DECEMBER 2024",
                "FIRE REPORTED",
                "2024",
            ),
            (
                "aftermath",
                "By mid twenty-twenty-five, the upper structure had been dismantled; sources report remnants remained.",
                "Present-day site only from verified footage; otherwise neutral shoreline, labeled illustrative.",
                "AFTERMATH",
                "VERIFY CURRENT SITE",
                "2025 update",
            ),
            (
                "rumors",
                "Stories of curses and accidents spread online, but dramatic closure claims remain disputed.",
                "Myth-versus-record cards; label unsupported claims folklore.",
                "FOLKLORE ≠ FACT",
                "CHECK SOURCES",
                "Evidence check",
            ),
            (
                "coordinates",
                "A public listing gives this approximate pin: eleven point nine seven six three, one zero two point three three three two.",
                "Crisp coordinate lock on map, explicitly approximate, not survey-grade.",
                "11.9763° N",
                "102.3332° E • APPROX.",
                "Map pin",
            ),
            (
                "access",
                "Do not enter fenced or damaged structures. Confirm legal access locally before visiting.",
                "Safe public viewpoint, no trespass or climbing.",
                "LOOK • DON’T TRESPASS",
                "CHECK ACCESS FIRST",
                "Visitor safety",
            ),
            (
                "payoff",
                "The real mystery: a floating-hotel dream became a jungle landmark, then disappeared in fire and salvage.",
                "Historic silhouette dissolves into present verified landscape.",
                "THE SITE REMAINS",
                "THE SHIP DOES NOT",
                "Conclusion",
            ),
            (
                "loop",
                "And that lagoon? It once held a seven-deck hotel ship. The Galaxy is gone.",
                "Match block 1 aerial exactly: empty site, jungle, warm haze.",
                "KOH CHANG • THAILAND",
                "WHAT REMAINS?",
                "Loop to opening",
            ),
        ],
    },
    "flannan-coat": {
        "title": "Flannan Isles: The Coat Left Behind",
        "requested_title": "Everything You Were Told About the 1900 Flannan Isles Lighthouse Was a Lie (The One Coat Left Behind)",
        "channel": "Silent Evidence",
        "slug": "flannan-isles-coat-myth-check",
        "location": "Eilean Mòr, Flannan Isles, Outer Hebrides, Scotland",
        "coords": "58°17.294′ N, 7°35.394′ W (Northern Lighthouse Board position)",
        "note": "The disappearance is documented; popular embellishments (half-eaten meal, overturned chair, lurid diary entries) are not supported by the primary NLB/National Records of Scotland account. The NLB says McArthur’s wearing coat was left behind; this is distinct from Ducat’s old waterproof coat being away and Marshall’s oilskins. Do not claim the coat proves the sequence of events.",
        "lock": "Vertical 9:16 evidence-led historical mystery; 1900 North Atlantic winter, Eilean Mòr, slate sea, restrained cold blue-gray and lantern amber; plausible Victorian lighthouse interiors. No supernatural figures, fake readable logbook, staged evidence presented as archival, or certainty about the disappearance’s exact sequence. Reenactments are explicitly labeled.",
        "ref": "Create a documentary reference sheet: (1) historically plausible white Victorian lighthouse/keeper station on rugged Eilean Mòr, (2) period wearing coat on plain hook, (3) map locating Flannan Isles west of Lewis in the Outer Hebrides. Cold Atlantic light, slate sea, warm lantern amber. No ghost, fake diary text, half-eaten meal, overturned chair or fabricated archival stamp. Label dramatizations as reconstruction; keep consistent across all blocks.",
        "sources": [
            "https://www.nlb.org.uk/history/flannan-isles/",
            "https://www.nlb.org.uk/lighthouses/flannan-islands/",
            "https://blog.nrscotland.gov.uk/2023/12/12/flannan-isles-lighthouse-keepers-the-disappearance/",
        ],
        "keywords": [
            "Flannan Isles lighthouse mystery 1900",
            "Donald McArthur coat left behind",
            "Flannan Isles primary source report",
            "Flannan lighthouse keepers disappeared",
            "Flannan Isles logbook myth debunked",
        ],
        "titles": [
            ("Flannan Isles: The Coat Left Behind", "THE COAT"),
            ("The 1900 Lighthouse Mystery, Rechecked", "REAL RECORDS"),
            ("What the Flannan Isles Records Say", "MYTH CHECK"),
        ],
        "tags": [
            "Flannan Isles mystery",
            "Flannan Isles lighthouse",
            "Donald McArthur",
            "James Ducat",
            "Thomas Marshall",
            "Northern Lighthouse Board",
            "1900 lighthouse mystery",
            "Outer Hebrides history",
            "lighthouse keepers vanished",
            "historical mystery explained",
            "coat left behind",
            "myth busting history",
            "Scottish history",
            "primary source investigation",
        ],
        "chapters": [
            "00:00 The coat clue",
            "00:05 Where it happened",
            "00:10 The keepers",
            "00:15 Hesperus arrives",
            "00:20 Clothing evidence",
            "00:25 West landing damage",
            "00:30 Official theory",
            "00:35 The popular myth",
            "00:40 The missing log",
            "00:45 What the coat means",
            "00:50 What remains unknown",
            "00:55 Recheck the clue",
        ],
        "cta": "Subscribe for evidence-led historical mysteries. This video distinguishes contemporary records from later retellings; the cause of the keepers’ disappearance remains unresolved.",
        "blocks": [
            (
                "hook",
                "At the Flannan Isles lighthouse in 1900, three keepers vanished. One coat became legend.",
                "Stormy aerial of Eilean Mòr lighthouse, period reconstruction.",
                "FLANNAN ISLES",
                "15 DECEMBER 1900",
                "Case opening",
            ),
            (
                "map",
                "The lighthouse stands on Eilean Mòr, west of Lewis in Scotland’s Outer Hebrides.",
                "Map zoom Scotland, Outer Hebrides, Lewis, then Eilean Mòr.",
                "58°17.294′ N",
                "7°35.394′ W",
                "Location",
            ),
            (
                "keepers",
                "James Ducat, Thomas Marshall, and Donald McArthur were on duty at the station.",
                "Three respectful illustrative silhouettes labeled names.",
                "DUCAT • MARSHALL",
                "McARTHUR",
                "The keepers",
            ),
            (
                "discovery",
                "The relief tender Hesperus reached the island on December twenty-sixth and found the station empty.",
                "Period tender approaches rugged landing in swell.",
                "26 DECEMBER 1900",
                "HESPERUS ARRIVES",
                "Discovery",
            ),
            (
                "coat",
                "Joseph Moore reported McArthur’s wearing coat left behind; Ducat and Marshall’s wet-weather gear was away.",
                "Illustrative close-up of period coat on hook, clearly labeled reconstruction.",
                "McARTHUR’S COAT",
                "LEFT AT STATION",
                "Clothing evidence",
            ),
            (
                "damage",
                "The official inquiry described damage at the west landing, including broken railings and missing equipment.",
                "Evidence diagram of west landing damage, no fabricated measurements.",
                "WEST LANDING",
                "DAMAGE RECORDED",
                "Physical evidence",
            ),
            (
                "theory",
                "Superintendent Robert Muirhead concluded a large sea likely swept the men away near the landing.",
                "Wave at rocky landing; overlay says Muirhead’s conclusion, not certainty.",
                "OFFICIAL THEORY",
                "NOT DIRECTLY WITNESSED",
                "1901 inquiry",
            ),
            (
                "myth",
                "The famous half-eaten meal, overturned chair, and dramatic diary entries are not established by primary accounts.",
                "Cards stamped unsupported in popular retellings; no fake handwritten documents.",
                "MEAL? CHAIR? DIARY?",
                "NOT IN PRIMARY ACCOUNT",
                "Myth check",
            ),
            (
                "log",
                "The Northern Lighthouse Board says it does not hold the original logbook; verify later quotations.",
                "Blank slate and archive folders, illustrative graphic.",
                "LOGBOOK NOT HELD",
                "VERIFY EVERY QUOTE",
                "Source check",
            ),
            (
                "meaning",
                "The coat is evidence about clothing and routine—not proof of a supernatural event or exact sequence.",
                "Evidence board separates known, inferred, unknown.",
                "KNOWN",
                "INFERRED",
                "Evidence boundary",
            ),
            (
                "unknown",
                "The three men were never found, and the exact sequence of events remains unknown.",
                "Wide North Atlantic at dusk, respectful lighthouse silhouette.",
                "NO BODIES FOUND",
                "SEQUENCE UNKNOWN",
                "Conclusion",
            ),
            (
                "loop",
                "Three keepers vanished. One coat stayed behind. What can that clue truly tell us?",
                "Match opening storm composition; return to coat silhouette.",
                "THE COAT",
                "THE RECORD",
                "Loop to opening",
            ),
        ],
    },
}


def make(folder: str, d: dict) -> None:
    base = Path("video_packages") / folder
    base.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, (key, voice, visual, overlay, detail, timeline) in enumerate(d["blocks"], 1):
        coords = (
            d["coords"]
            if folder.startswith("koh") and i in (2, 9)
            else (d["coords"] if folder.startswith("flannan") and i == 2 else "")
        )
        bid = f"block_{i:02d}_{key}"
        blocks.append(
            {
                "id": bid,
                "duration_target_seconds": 5,
                "narration": voice,
                "visual_prompt": d["lock"] + " Shot: " + visual + " " + d["note"],
                "first_frame_prompt": f"Block {i:02d} first frame: {visual} Match the exact preceding final frame, location, lens direction, weather and grade. No unprovided text.",
                "last_frame_prompt": f"Block {i:02d} final frame: {visual} Settle on stable composition matching next block first keyframe; block 12 must match block 01 opening. No morphing or unsupported details.",
                "motion_prompt": f"Five-second documentary shot: {visual} slow controlled motion. At t=2.5s apply subtle 1.12x punch-in as post effect, not model instruction. Last 8 frames settle for chaining.",
                "overlay_title": overlay,
                "overlay_detail": detail,
                "coordinates": coords,
                "location": d["location"],
                "timeline": timeline,
                "elevation_m": 101 if folder == "flannan-coat" and i == 2 else None,
                "audio": f"audio/{bid}.wav",
                "clip": f"clips/{bid}.mp4",
                "seed": 46000 + i,
                "model_version": "RECORD_BEFORE_RENDER",
                "status": "planned",
                "continuity": "Previous block last frame is required as first-frame reference; block 12 targets block 01 for loop.",
                "source_notes": d["note"],
            }
        )
    doc = {
        "title": d["title"],
        "requested_title": d["requested_title"],
        "slug": d["slug"],
        "channel": d["channel"],
        "format": "YouTube Short",
        "target_duration_seconds": 60,
        "aspect_ratio": "9:16",
        "fps_master": 30,
        "audio_master": True,
        "visual_lock": d["lock"],
        "reference_sheet_prompt": d["ref"],
        "important_factual_note": d["note"],
        "source_citations": d["sources"],
        "blocks": blocks,
    }
    (base / "storyboard.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    title_info = [{"title": t, "characters": len(t), "thumbnail_text": thumb} for t, thumb in d["titles"]]
    keywords = [
        {
            "phrase": k,
            "word_count": len(k.split()),
            "search_volume": "NOT VERIFIED in vidIQ",
            "competition": "NOT VERIFIED (<40 target pending)",
            "basis": "topic hypothesis only",
        }
        for k in d["keywords"]
    ]
    intro = (
        "A source-led check of the 1900 Flannan Isles lighthouse disappearance. We compare Joseph Moore’s contemporary account and the Northern Lighthouse Board investigation with the later details repeated in popular versions. McArthur’s wearing coat was left at the station; that fact does not prove what happened next. The official inquiry proposed that a large sea swept the men away near the west landing, but no one witnessed the disappearance. The original lighthouse logbook is not held by the Northern Lighthouse Board, so dramatic quotations need careful sourcing. This is a mystery with a documented record and genuine limits—not a solved supernatural story.\n\n"
        if folder.startswith("flannan")
        else "The Galaxy at Koh Chang Grand Lagoona became one of Thailand’s most memorable abandoned-site stories—but the familiar image of the intact ghost ship is now history. The ship-hotel was severely damaged by fire on 3 December 2024, and its upper structure was dismantled in 2025. This travel-history Short follows the location, resort story, fire, and what sources say remains. The map pin shown is approximate, not survey-grade; confirm the location and current access before visiting. Do not trespass or enter damaged structures.\n\n"
    )
    desc = (
        d["title"]
        + "\n\n"
        + intro
        + "\n".join(d["keywords"])
        + "\n\nChapters (Shorts timeline):\n"
        + "\n".join(d["chapters"])
        + "\n\nSources and further reading:\n"
        + "\n".join(d["sources"])
        + "\n\n"
        + d["cta"]
        + "\n\nHistorical reenactments and AI-generated visuals, if used, must be clearly labeled and never presented as original archival evidence. We welcome sourced corrections: share a primary document, archival reference, or current on-location update so claims can be checked.\n"
    )
    while len(desc) < 2000:
        desc += "\nWe distinguish documented fact, source-based inference, and uncertainty; a compelling story should never require invented evidence. "
    desc = desc[:2490]
    seo = {
        "channel": d["channel"],
        "requested_title_not_used": d["requested_title"],
        "research_status": "NO vidIQ paid account telemetry or authenticated export was available. Outlier score, VPH, keyword volume/competition, swipe rate, APV and scorecard values are UNVERIFIED. Do not claim thresholds are achieved.",
        "channel_stats_status": "Subscriber counts and sample-video views in the request are user-provided and unauthenticated.",
        "title_candidates": title_info,
        "long_tail_keywords": keywords,
        "description": desc,
        "chapters": d["chapters"],
        "tags": d["tags"],
        "tags_csv": ", ".join(d["tags"]),
        "tags_character_count": len(", ".join(d["tags"])),
        "pinned_comments": [
            d["cta"],
            "What source or question should we investigate next? Please include a link; unsourced claims are not evidence.",
        ],
        "measurement_targets": [
            "vidIQ outlier ≥3x: measure after upload, cannot forecast",
            "VPH: record at 1h, 6h and 24h against channel baseline",
            "Viewed vs swiped away >75% in first 1.5s: Studio measurement, not guaranteed",
            "APV >100%: possible with replay loop, measure after publication",
            "Keyword volume and competition <40: not checked in paid vidIQ; paste export before claiming",
        ],
    }
    (base / "youtube_seo.json").write_text(
        json.dumps(seo, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    (base / "GLOBAL_VISUAL_VOICE_LOCK.md").write_text(
        "# GLOBAL VISUAL & VOICE LOCK\n\n"
        + d["lock"]
        + "\n\n## Paid Nano Banana master reference sheet prompt\n\n"
        + d["ref"]
        + "\n\nUse up to 14 reference images only if the selected paid endpoint/account actually supports it. Log model/version, job ID, source images, and cost. No image generation was run for this package.\n",
        encoding="utf8",
    )
    notes = f"""# Production notes — {d["slug"]}\n\n## Factual guardrail\n\nThe owner-supplied working title was revised for factual accuracy: `{d["requested_title"]}` is retained only as a brief, not the publish title. Suggested publish title: **{d["title"]}**.\n\n{d["note"]}\n\n## Honest execution status\n\n{COMMON_NOTE} No Nano Banana, video API, Manim renderer, WhisperX alignment, n8n instance, or paid vidIQ telemetry was invoked.\n\n## Workflow\n\n1. Verify source links and map pin/access status immediately before upload.\n2. Record exact model/version, seed, prompt, job id and output hash for each generated asset.\n3. Generate narration WAVs first and measure actual duration `D_i`; Manim and clip fit follow those WAV durations, not the five-second target.\n4. Pass previous clip’s final decoded frame as next clip’s first-frame reference, where the provider supports both endpoints. Validate API behavior before relying on it. Set block 12 final target to block 01 first frame; a loop is an edit goal, not guaranteed seamless by prompt alone.\n5. Generate crisp map/timeline overlays with `python scripts/manim_blocks.py video_packages/{folder}/storyboard.json --output video_packages/{folder}/manim_blocks_generated.py --fps 60 --audio-dir video_packages/{folder}/audio`. Render with `manim -pqh --fps 60 ... Block01` after installing Manim.\n6. Put media at `audio/<block-id>.wav` and `clips/<block-id>.mp4`; assemble using `python scripts/long_video_chain.py video_packages/{folder} --fps 30 --captions --resume`.\n7. Review captions/timing, audio loudness, legal access, facts, rights and disclosures before publishing.\n"""
    (base / "PRODUCTION_NOTES.md").write_text(notes, encoding="utf8")


if __name__ == "__main__":
    for folder, data in DATA.items():
        make(folder, data)
    print("Built 2 packages (24 blocks).")
