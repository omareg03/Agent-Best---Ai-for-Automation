# AI Tool Registry — YouTube Video Production Stack

**Research checked:** 2026-10-26 (live web search; individual claims linked below). **Refresh:** daily scout workflow is a reminder/metadata workflow, not a guarantee of a complete quality review. **Execution status:** no external paid accounts, model APIs, GPU, Manim renderer, n8n instance, or vidIQ telemetry were available in this workspace.

> Prices, availability, quotas, model IDs, rights and terms change. Confirm vendor documentation and the actual account/region before committing money or publishing. “Paid” is not inferred from a model name.

## Production stack and evidence

| Stage | Tool / model | Use | Access / cost / caveat | Evidence |
|---|---|---|---|---|
| Still image / references | Nano Banana 2.1 (`gemini-nano-banana-2.1`) | Paid keyframes, character/location reference sheets | Paid API; Google pricing currently equates a 1K image to about $0.0336; no promise of an account entitlement or free API image output | [Google Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing), [model documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/nano-banana-2-1) |
| Still image / premium | Nano Banana Pro (`gemini-3-pro-image`) | Paid premium still generation | Verify current model availability and pricing in the account; do not infer entitlement from this registry | [Google pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Video | Gemini Omni 1.1 Flash (`gemini-omni-1.1-flash`) | Paid image/video generation or editing where API supports requested controls | Google describes paid-tier GA availability; official pricing translates 720p output to roughly $0.10/s. First/last-frame behavior must be verified against the live endpoint; prompts do not guarantee boundary identity | [Google pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Video | Veo 3.1 | Paid video generation candidate | Pricing, lengths, boundary control and regional/API access are account-specific; verify current docs before integrating | [Google AI developer docs](https://ai.google.dev/gemini-api/docs) |
| Local video | Wan 2.1 / Wan 2.2 FLF2V | Open-weight/local or ComfyUI workflows | GPU memory, weights, nodes and licence/terms depend on model variant; run live graph `/object_info` validation. The repo's graphs are templates, not evidence of completed GPU execution | [Wan project releases](https://github.com/Wan-Video/Wan2.2) |
| Local video | FramePack | Long video experiments | Experimental/maintenance-sensitive; GPU-dependent, not assumed production-ready | [upstream repository](https://github.com/lllyasviel/FramePack) |
| Local video | HunyuanVideo | Local generation alternative | Review current Tencent community licence, geographic and commercial restrictions before use | [HunyuanVideo repository](https://github.com/Tencent/HunyuanVideo) |
| Crisp overlays | Manim Community Edition | Maps, coordinates, elevation/timelines and captions | Open-source Python animation engine; local CPU/GPU/time costs remain. `manim -pqh` is a render quality preset, not a guarantee of 1080p60 unless configured and tested | [Manim docs](https://docs.manim.community/en/stable/) |
| Speech | Kokoro-82M | Local TTS option | Check current voice package, language/voice, model and commercial terms; this repo has not executed a Kokoro server | [Kokoro repository](https://github.com/hexgrad/kokoro) |
| Speech | Edge-TTS | Hosted Edge voice access | Network-dependent and not a stable production guarantee; pin a tested version, run a live request, and maintain a local fallback | [edge-tts repository](https://github.com/rany2/edge-tts) |
| Alignment | WhisperX | Word-level transcription/forced alignment | GPU often preferred; pin a tested release, verify language/alignment model and timestamps. Do not treat estimated timings as forced alignment | [WhisperX repository](https://github.com/m-bain/whisperX) |
| Assembly | FFmpeg | CFR normalization, audio mastering, frame extraction, concat and ASS captions | This project resolves FFmpeg through PATH or `imageio-ffmpeg`; filter availability varies by binary. The chain script validates non-empty outputs but real media still must be reviewed | [FFmpeg documentation](https://ffmpeg.org/documentation.html) |
| Orchestration | n8n self-hosted | Webhooks/schedules and pipeline calls | License is Sustainable Use License (source-available; not OSI-approved open source); deployment and commercial-use terms must be reviewed. n8n 3.x node behavior must be validated on the installed version | [n8n license](https://github.com/n8n-io/n8n/blob/master/LICENSE.md), [n8n docs](https://docs.n8n.io/) |
| CI / scout | GitHub Actions | Daily registry refresh, tests and assembly | Hosted runner capacity/quotas depend on repository visibility and current GitHub plans; GPU is not assumed on hosted runners | [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) |
| SEO telemetry | vidIQ (paid account desired by owner) | Keyword volume/competition, outlier and VPH review | **Not connected or queried here. No metrics are claimed.** Paid plans/features vary. Capture account-exported numbers immediately before upload | [vidIQ Outliers help](https://support.vidiq.com/en/articles/9660010-outliers), [Keyword Research help](https://support.vidiq.com/en/articles/9421214-keywords-research), [features by plan](https://support.vidiq.com/en/articles/13928456-features-credits-by-plan) |

## Tool-side telemetry interpretation

vidIQ documents Outlier Score as a relative-performance measure and exposes VPH in its research/extension tools; its keyword screen displays volume and competition/overall score. The exact proposed thresholds (3×, 75% viewed-vs-swiped, 100% APV, keyword competition <40) are **targets, not promises**. A scout can record a timestamped export but cannot truthfully manufacture live paid account data. Channel subscriber counts, video views and “proven winners” quoted in the user request are user-provided and not authenticated in this repository.

## Research snapshot and fact-risk notes

- The Northern Lighthouse Board’s Flannan Isles page records that the keepers’ last logbook entries were Dec 13, with later slate notes; the station was found empty by the *Hesperus* on Dec 26, 1900. Its account describes McArthur’s “wearing coat” left behind, and different weather gear worn/away for the other men. Do not conflate the garments or claim this solves the disappearance: [NLB history](https://www.nlb.org.uk/history/flannan-isles/).
- NLB lists the lighthouse position as **58°17.294′N, 007°35.394′W**, elevation 101 m: [NLB lighthouse record](https://www.nlb.org.uk/lighthouses/flannan-islands/).
- National Records of Scotland summarizes the 1900 disappearance, NLB report and clothing evidence: [NRS blog](https://blog.nrscotland.gov.uk/2023/12/12/flannan-isles-lighthouse-keepers-the-disappearance/).
- The Koh Chang Galaxy story is time-sensitive: local reporting documents the **Dec 3, 2024 fire** and the local Koh Chang site documents the aftermath/dismantling: [Thai PBS World](https://world.thaipbs.or.th/detail/koh-changs-haunted-ghost-ship-goes-up-in-flames/55670), [I am Koh Chang update](https://iamkohchang.com/photos/various/galaxy-koh-chang-ghost-ship.html). It is inaccurate to portray the intact ship as still standing.
- The approximate Koh Chang coordinate in this package is sourced to a public place listing (**11.9763, 102.3332**), not an official survey/control point: [Jertam listing](https://www.jertam.com/places/30391). Verify against a current map/satellite and on-location footage before calling it exact GPS.

## Verification contract

For every planned/rendered asset, record prompt, seed, provider/model version, job ID, source/reference hashes, first/last frame SHA-256, measured audio duration, render status and output hash in SQLite. “Verified” means a reproducible request or test was actually run; registry text is not proof that an account, endpoint, quota, license or rendered artifact is live.
