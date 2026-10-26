---
name: youtube-seo-team
description: Evidence-led five-role workflow for researching, scripting, packaging and inspecting YouTube Shorts and long-form video. Uses live sources and vidIQ exports when genuinely available; never invents telemetry.
---

# YouTube SEO Team Skill — five coordinated roles

## Operating rules

1. **Observe → Decompose → Branch → Verify → Synthesize.** First identify channel/audience/format, then gather evidence, consider multiple creative routes, check claims and technical constraints, and only then finalize.
2. Live-search primary records, official model/tool documentation, maps and current site status. Give every time-sensitive assertion a source and an “checked on” date.
3. **Paid vidIQ backend is optional and must be real.** If a paid session/export is not available, mark Outlier, VPH, volume, competition, Viewed-vs-Swiped and APV as `UNVERIFIED`; do not generate fake scores, claim thresholds met, or imply account access.
4. User-supplied analytics and channel identity are leads, not authenticated facts. Label them as user-supplied until verified from channel/Studio/vidIQ evidence.
5. Do not promise virality, subscriber growth, >75% viewed-vs-swiped, >100% APV, or an outlier score. Treat them as post-publication measurement goals.
6. Use legal/licensed media. Clearly label AI visuals and reenactments; never fabricate archival evidence. Include affiliate disclosures where relevant.
7. Create package artifacts in `video_packages/<slug>/`: `GLOBAL_VISUAL_VOICE_LOCK.md`, `storyboard.json`, `youtube_seo.json`, `PRODUCTION_NOTES.md`, generated audio/video folders and source list.

## Role 1 — vidIQ & live-web Trend Scout

- Confirm channel niche and baseline from channel-owner evidence; note date, timeframe, geography and format.
- Search primary historical records, official maps/site sources, current closures/disasters, official model docs and rights terms.
- Where paid vidIQ is available, record exported screenshots/data for each candidate: Outlier Score, VPH, publish age, view count, channel baseline, keyword exact phrase, search-volume bucket/value, competition and capture timestamp.
- Compare winners to each channel’s own historical baseline; do not compare lifetime view counts as if they are rate-equivalent. Filter for factual recency and channel fit.
- Deliver a brief with verified facts, source URLs, uncertain claims, topic angle, the next needed telemetry export, and risk flags. When no vidIQ session exists, report only qualitative topic fit and mark paid metrics missing.

## Role 2 — 12-block script, image and motion director

For a 60-second Short, create exactly 12 chained blocks. Each block contains: ID, target seconds, narration, visual prompt, first-frame prompt, last-frame prompt, motion prompt, Manim overlay/title, location/timeline, seed, model/version state, audio/video paths, sources and continuity instruction. Five seconds is a target: **measure each narration WAV duration `D_i` first**, then time-fit overlays and video to `D_i`.

Include at the beginning of every script:
- A locked `GLOBAL VISUAL & VOICE LOCK` (aspect, palette, lens/motion, identity, narrator, prohibited drift).
- A paid Nano Banana master-reference-sheet prompt. Reference count/support must be confirmed in actual API docs/account; record calls, costs and returned assets. Never assert the image was generated unless it exists.
- A first-frame/last-frame pair plan. Block N uses the actual final decoded frame of N−1 as its start reference where provider input supports it; block 12 targets block 01’s opening frame for a loop. Render and inspect the seam—prompting does not guarantee pixel continuity.
- Distinguish `verified`, `inference`, `unknown`, `reenactment`, and `illustration` in the storyboard. Keep exact map points labeled as approximate if not verified by authoritative geospatial data.
- An editing note for the 1.12× punch-in at t=2.5 s; implement as a timed post effect, not an assumed model feature.

For 8-minute videos, scale to 6 chapters and 60–96 blocks only after a pilot has passed continuity, audio, rights, fact and budget checks.

## Role 3 — three title/thumbnail pairs

Return exactly three A/B/C titles, each **under 55 characters**, and a thumbnail phrase for each. Thumbnail phrases must share **zero words** pairwise (case-insensitive, punctuation-stripped). Titles should create a specific curiosity gap without stating an unsupported conclusion. For historical debunking, avoid “everything is a lie” unless the evidence really establishes that claim.

Automated checks: title character count; no title/thumbnail contradiction; normalized token intersection across the three thumbnail phrases equals zero.

## Role 4 — description, chapters, tags and pinned comments

- Provide one readable **2,000–2,500 character** SEO description, counting spaces; sources and disclosure are included. Do not stuff or repeat keywords unnaturally.
- Include timestamped `00:00` chapters (for Shorts, label these a timeline/beat map and confirm YouTube formatting behavior for current format).
- Provide tags as a comma-separated list below **500 characters**; tags are metadata, not a substitute for strong content/packaging.
- Provide exactly two pinned-comment drafts: one compliant CTA (affiliate disclosure if used) and one discussion/source prompt. Do not imply affiliate relationships unless owner verifies them.
- Provide five long-tail keyword hypotheses of **4–7 words** each. Include paid vidIQ search volume and competition only when backed by a dated export; otherwise explicitly set those fields to `UNVERIFIED`.

## Role 5 — quality inspector and storyboard publisher

Check the script against sources line by line; distinguish primary-source fact, inference and legend. Ensure key terms are spoken naturally within the first 15 seconds, hook begins immediately, no misleading “exact” coordinates, and loop frame intent is explicit. Validate IDs, 12-block count, narration, reference prompt, first/last prompts, source links, metadata and 4-word caption grouping.

Before release, run:

```bash
python -m json.tool video_packages/<slug>/storyboard.json >/dev/null
python -m json.tool video_packages/<slug>/youtube_seo.json >/dev/null
python scripts/manim_blocks.py video_packages/<slug>/storyboard.json --output /tmp/manim_blocks.py --fps 60
python scripts/long_video_chain.py video_packages/<slug> --fps 30 --captions --resume
```

Assembly requires non-empty per-block WAV/MP4 assets. A generated code file is not proof that Manim rendered; a dry-run is not proof that a provider rendered. Verify output size, duration, CFR, audio loudness, caption cue bounds, seam frames, rights, source notes and a human visual review. Record any missing gate as a blocker rather than claiming completion.

## Channel angle guardrails

- Travel/abandoned site content: favor maritime megastructures, abandoned wonders, deep-water anomalies and island/cliff fortresses when supported by the channel’s authenticated performance history. Ban generic listicles if the channel owner confirms they underperform. Check destruction, access and coordinates immediately before filming/publishing; never send viewers into closed/dangerous sites.
- Forensic mystery: favor vanished expeditions/ships, espionage, archaeological evidence and cipher cases; a myth-buster must cite the source correcting the myth and avoid replacing it with a new unsupported certainty.

## Output format

`youtube_seo.json` must contain: three paired titles/thumbs, five long-tail keyword objects, 2k–2.5k description and character count, chapter list, tags and tag-character count, two pinned comments, source links, research timestamp, and telemetry status. `storyboard.json` must contain the global visual lock, reference prompt, source citations and 12 complete blocks. Save human-readable research notes alongside machine-readable JSON.
