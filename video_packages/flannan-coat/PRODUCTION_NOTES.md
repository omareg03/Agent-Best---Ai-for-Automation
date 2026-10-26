# Production notes — flannan-isles-coat-myth-check

## Factual guardrail

The owner-supplied working title was revised for factual accuracy: `Everything You Were Told About the 1900 Flannan Isles Lighthouse Was a Lie (The One Coat Left Behind)` is retained only as a brief, not the publish title. Suggested publish title: **Flannan Isles: The Coat Left Behind**.

The disappearance is documented; popular embellishments (half-eaten meal, overturned chair, lurid diary entries) are not supported by the primary NLB/National Records of Scotland account. The NLB says McArthur’s wearing coat was left behind; this is distinct from Ducat’s old waterproof coat being away and Marshall’s oilskins. Do not claim the coat proves the sequence of events.

## Honest execution status

A storyboard and SEO hypothesis package; no media has been rendered and no paid model/vidIQ account was accessed. No Nano Banana, video API, Manim renderer, WhisperX alignment, n8n instance, or paid vidIQ telemetry was invoked.

## Workflow

1. Verify source links and map pin/access status immediately before upload.
2. Record exact model/version, seed, prompt, job id and output hash for each generated asset.
3. Generate narration WAVs first and measure actual duration `D_i`; Manim and clip fit follow those WAV durations, not the five-second target.
4. Pass previous clip’s final decoded frame as next clip’s first-frame reference, where the provider supports both endpoints. Validate API behavior before relying on it. Set block 12 final target to block 01 first frame; a loop is an edit goal, not guaranteed seamless by prompt alone.
5. Generate crisp map/timeline overlays with `python scripts/manim_blocks.py video_packages/flannan-coat/storyboard.json --output video_packages/flannan-coat/manim_blocks_generated.py --fps 60 --audio-dir video_packages/flannan-coat/audio`. Render with `manim -pqh --fps 60 ... Block01` after installing Manim.
6. Put media at `audio/<block-id>.wav` and `clips/<block-id>.mp4`; assemble using `python scripts/long_video_chain.py video_packages/flannan-coat --fps 30 --captions --resume`.
7. Review captions/timing, audio loudness, legal access, facts, rights and disclosures before publishing.
