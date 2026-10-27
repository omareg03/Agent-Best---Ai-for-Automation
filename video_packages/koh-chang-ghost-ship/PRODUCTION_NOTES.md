# Production notes — koh-chang-galaxy-after-the-fire

## Factual guardrail

The owner-supplied working title was revised for factual accuracy: `The Mystery Ghost Ship Left to Rot in a Thai Jungle (Koh Chang Part 2 — Exact GPS Coordinates)` is retained only as a brief, not the publish title. Suggested publish title: **Koh Chang’s Ghost Ship: What Remains?**.

Important factual correction: The Galaxy ship-hotel was severely burned on 3 December 2024; a 2025 local update reports dismantling of its upper structure. Do not present the intact ship as currently standing. No current 2026 on-site inspection is available here; verify the present site, remnants and legal access before publication. HTMS Chang is a different ship: the US Naval History and Heritage Command dates the former LST-898's laying down to 15 October 1944 and commissioning to 29 December 1944; NavSource identifies it as ex-USS Lincoln County, 328 ft/100 m overall. PADI lists HTMS Chang as intentionally scuttled on 22 November 2012 to form an artificial reef, about 30 m to the seabed with a stated maximum depth of 34 m. Some dive listings report 117 m length; use the naval 328 ft specification and label dive depths approximate because local references differ. Never say HTMS Chang was sunk during WWII.

## Honest execution status

A storyboard and SEO hypothesis package; no media has been rendered and no paid model/vidIQ account was accessed. No Nano Banana, video API, Manim renderer, WhisperX alignment, n8n instance, or paid vidIQ telemetry was invoked.

## Workflow

1. Verify source links and map pin/access status immediately before upload.
2. Record exact model/version, seed, prompt, job id and output hash for each generated asset.
3. Generate narration WAVs first and measure actual duration `D_i`; Manim and clip fit follow those WAV durations, not the five-second target.
4. Pass previous clip’s final decoded frame as next clip’s first-frame reference, where the provider supports both endpoints. Validate API behavior before relying on it. Set block 12 final target to block 01 first frame; a loop is an edit goal, not guaranteed seamless by prompt alone.
5. Generate crisp map/timeline overlays with `python scripts/manim_blocks.py video_packages/koh-chang-ghost-ship/storyboard.json --output video_packages/koh-chang-ghost-ship/manim_blocks_generated.py --fps 60 --audio-dir video_packages/koh-chang-ghost-ship/audio`. Render with `manim -pqh --fps 60 ... Block01` after installing Manim.
6. Put narration masters at `audio/<block-id>.wav` and keyframes/clips under `assets/frames/frame_XX.png` and `assets/clips/block_XX_*.mp4`; run `python scripts/ingest_assets.py video_packages/koh-chang-ghost-ship` before assembling with `python scripts/long_video_chain.py video_packages/koh-chang-ghost-ship --fps 30 --captions --resume`.
7. Review captions/timing, audio loudness, legal access, facts, rights and disclosures before publishing.
