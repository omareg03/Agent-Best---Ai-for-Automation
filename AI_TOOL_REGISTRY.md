# AI Tool Registry — Long-Video & Media Automation

> **Auto-generated. Do not hand-edit.** Source of truth: [`registry/tools.json`](registry/tools.json).
> Regenerate: `python -m scripts.video_pipeline.cli registry render`
> Last refresh: **2026-10-27 01:02 UTC** · next due: **2026-10-27T06:00:00+00:00**

## Status

- **23** tools tracked · **20** human/agent-verified · **21** currently usable
- Policy: refresh every **24 h**; warn after **7 d**; CI fails after **30 d** without re-verification.
- Rule: *A tool may only be used by the pipeline if confidence=verified and status=current. Anything else must be marked experimental in code and in docs.*

## ⚠️ Corrections to widely-repeated advice

These claims are common in 2025-era tutorials and are **wrong today**. The registry records the correction so the pipeline never encodes folklore.

<details><summary><strong>"Nano Banana has a free API tier"</strong> → False as of 2026-10-26.</summary>

False as of 2026-10-26. Google's pricing rows show no free tier for image OUTPUT on gemini-nano-banana-2.1, gemini-3.1-flash-image, gemini-3.1-flash-lite-image or gemini-3-pro-image. Free access exists only in consumer surfaces (Gemini app, AI Mode 25 images/24h, Flow 50 credits/day), which are not automatable.

Source: <https://ai.google.dev/gemini-api/docs/pricing>

</details>

<details><summary><strong>"Kling and Hailuo have free daily tiers you can automate"</strong> → False.</summary>

False. Kling's free tier is 66 credits/day on the web app only (no API), watermarked, explicitly non-commercial, single queue. Hailuo replaced recurring daily credits with a one-time welcome grant that expires in ~3 days; its API 'free tier' is a rate limit (5 req/min legacy, 2 concurrent H3), not free clips.

Source: <https://aireiter.com/blog/kling-ai-free-tier-2026>

</details>

<details><summary><strong>"FramePack is the state of the art for long video"</strong> → It is still the cheapest path to 120 s single takes on 6 GB, but the upstream repo is effectively unmaintained (public discussion: 'project has been abandoned').</summary>

It is still the cheapest path to 120 s single takes on 6 GB, but the upstream repo is effectively unmaintained (public discussion: 'project has been abandoned'). Treat it as a legacy option, not the default.

Source: <https://github.com/lllyasviel/FramePack/discussions>

</details>

<details><summary><strong>"edge-tts just works"</strong> → It broke on 2026-10-12: Microsoft rotated the Sec-MS-GEC token and every release before 7.</summary>

It broke on 2026-10-12: Microsoft rotated the Sec-MS-GEC token and every release before 7.3.0 returns HTTP 403 on all requests. 7.3.0/7.3.1 (2026-10-13) fixed the handshake. It also 403s from GitHub-hosted runners, so it is not a CI engine.

Source: <https://github.com/rany2/edge-tts/issues/490>

</details>

<details><summary><strong>"Open weights means Apache-2.0"</strong> → No.</summary>

No. HunyuanVideo 1.5 is under a Tencent community licence that explicitly does not apply in the EU, UK or South Korea. LTX-2.x is free only below $10M annual revenue. F5-TTS weights are CC-BY-NC, Fish Audio S2 is research-only, n8n is source-available (Sustainable Use License) not open source. Licence is a first-class field in this registry.

Source: <https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5>

</details>

## ⏳ Deprecation watch

| Tool | Model ID | Shutdown | Days left | Action |
|---|---|---|---|---|
| Nano Banana 2 | `gemini-3.1-flash-image` | 2026-10-29 | 1 | 🚫 do not start new work |

## Image & Character Anchors

| Tool | Model / ID | Licence | Cost | Hardware | Status | Role |
|---|---|---|---|---|---|---|
| [Nano Banana 2.1 (Gemini 3.1 Flash Image successor)](https://ai.google.dev/gemini-api/docs/pricing) | `gemini-nano-banana-2.1` | Proprietary API | $0.0336 / 1K image ($0.0168 batch); 2K $0.0504; 4K $0.113 | hosted | ✅ current | **primary** |
| [FLUX.1 (local)](https://github.com/black-forest-labs/flux) | `flux1-schnell / flux1-dev` | Apache-2.0 (schnell) / non-commercial (dev) | $0 (local) | 12-24 GB VRAM | ✅ current | fallback |
| [Nano Banana 2](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image) | `gemini-3.1-flash-image` | Proprietary API | $0.045 (0.5K) / $0.067 (1K) / $0.101 (2K) / $0.151 (4K) | hosted | ⛔ deprecated | **avoid** |
| [Nano Banana Pro](https://ai.google.dev/gemini-api/docs/pricing) | `gemini-3-pro-image` | Proprietary API | $0.134 / 1K-2K; $0.24 / 4K | hosted | ✅ current | premium |

<details><summary>Notes, free-tier reality and verification dates</summary>

**Nano Banana 2.1 (Gemini 3.1 Flash Image successor)** — free tier: None for API image output. Commercial use: Yes (paid). Verified 2026-10-26 (verified).
> GA 2026-10-06. Up to 14 reference images -> this is the identity-lock workhorse. SynthID watermark on every output. Consumer app access is free but not scriptable.

**FLUX.1 (local)** — free tier: Fully free when self-hosted (electricity only). Commercial use: schnell yes / dev no. Verified 2026-10-26 (unverified).
> Offline fallback when no API budget exists. Weaker identity retention than Nano Banana references; needs IP-Adapter/InstantID for faces. Licence differs per checkpoint -- check before shipping.

**Nano Banana 2** — free tier: None. Commercial use: Yes (paid). Verified 2026-10-26 (verified).
> Shutdown 2026-10-29. The pipeline refuses to start new work on it (keyframes.py hard guard).

**Nano Banana Pro** — free tier: None. Commercial use: Yes (paid). Verified 2026-10-26 (verified).
> Highest fidelity text rendering and brand consistency. Use only for hero shots: 4x the price of 2.1.

</details>

## Video & Long-Video Generation

| Tool | Model / ID | Licence | Cost | Hardware | Status | Role |
|---|---|---|---|---|---|---|
| [Wan 2.2 FLF2V / I2V-A14B](https://github.com/Wan-Video/Wan2.2) | `wan2.2-i2v-a14b (FLF2V via ComfyUI Wan22 14B FLF2V template)` | Apache-2.0 | $0.00 (own GPU) / ~$0.30-0.60 per clip on rented A100 | 16-24 GB VRAM FP8/GGUF; ~40 GB FP16 | ✅ current | **primary** |
| [FramePack](https://github.com/lllyasviel/FramePack) | `FramePackI2V_HY (13B)` | Apache-2.0 | $0.00 (own GPU) | 6 GB VRAM | 🕰️ legacy | long-take |
| [Gemini Omni 1.1 Flash](https://ai.google.dev/gemini-api/docs/pricing) | `gemini-omni-1.1-flash` | Proprietary API | ~$0.10 / second of 720p | hosted | ✅ current | hosted fallback |
| [Hailuo / MiniMax H3 (free tier)](https://aireiter.com/blog/hailuo-ai-pricing) | `minimax-h3` | Proprietary ToU | $0.28-0.56 / clip paid | hosted | ✅ current | manual previz only |
| [HunyuanVideo 1.5](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5) | `hunyuanvideo-1.5 (8.3B)` | Tencent Hunyuan Community License | $0.00 (own GPU) | 14 GB with offloading; 24 GB comfortable | ✅ current | alternative |
| [Kling 3.0 (free web tier)](https://aireiter.com/blog/kling-ai-free-tier-2026) | `kling-3.0` | Proprietary ToU | $0 (web only) | hosted | ✅ current | manual previz only |
| [LTX-2.5](https://pinggy.io/blog/best_video_generation_ai_models/) | `ltx-2.5 (22B)` | LTX-2 Community License (<$10M ARR) | $0.00 (own GPU) | 12 GB (distilled/FP8) - 80 GB (full) | ✅ current | alternative |
| [Wan 2.2 TI2V-5B](https://github.com/Wan-Video/Wan2.2) | `wan2.2-ti2v-5b` | Apache-2.0 | $0.00 (own GPU) | 8-12 GB VRAM (720p, 24 fps) | ✅ current | low-VRAM |

<details><summary>Notes, free-tier reality and verification dates</summary>

**Wan 2.2 FLF2V / I2V-A14B** — free tier: Fully free self-hosted. Commercial use: Yes. Verified 2026-10-26 (verified).
> First-last-frame-to-video: seams are solved by construction. 81 frames @ 16 fps default for 14B. MoE: 27B total, 14B active.

**FramePack** — free tier: Fully free self-hosted. Commercial use: Yes. Verified 2026-10-26 (verified).
> 60-120 s single takes at 30 fps on 6 GB via constant-size frame context. Upstream is effectively unmaintained; use the ComfyUI wrapper (kijai) and pin your model files. Not the default.

**Gemini Omni 1.1 Flash** — free tier: None (paid API). Consumer surfaces: YouTube Shorts Remix, Google AI plans. Commercial use: Yes (paid). Verified 2026-10-26 (verified).
> GA 2026-08-27. 3-10 s clips, extensions to ~40 s, 24 fps, 360p-4K, native synchronised audio, first/last-frame control. Preview id gemini-omni-flash-preview retired 2026-09-30. Wire format unverified in this repo -> probe-gated engine.

**Hailuo / MiniMax H3 (free tier)** — free tier: One-time welcome credits expiring in ~3 days (daily credits removed). Commercial use: No on free tier. Verified 2026-10-26 (verified).
> API 'free tier' is a rate limit (5 req/min legacy Hailuo, 2 concurrent H3), not free clips. 6 s @ 768p, watermarked.

**HunyuanVideo 1.5** — free tier: Free self-hosted. Commercial use: Yes below 100M MAU -- BUT licence does not apply in EU / UK / South Korea. Verified 2026-10-26 (verified).
> 8.3B, 1080p via super-resolution, ~75 s per render on a 4090 with the step-distilled checkpoint. Jurisdiction restriction is disqualifying for many teams -- hence not the default.

**Kling 3.0 (free web tier)** — free tier: ~66 credits/day (no rollover), 720p, watermarked, single queue. Commercial use: No on free tier. Verified 2026-10-26 (verified).
> No API on the free plan and no commercial rights: cannot be legally automated into a production pipeline. Listed for human previz only.

**LTX-2.5** — free tier: Free to self-host below $10M annual revenue. Commercial use: Yes below revenue ceiling; paid licence above. Verified 2026-10-26 (verified).
> Released 2026-08-11. Up to 4K/50 fps WITH synchronised audio in one pass -- the only open-weight family here that gives you sound for free. Not Apache: enterprise must read the ceiling.

**Wan 2.2 TI2V-5B** — free tier: Fully free self-hosted. Commercial use: Yes. Verified 2026-10-26 (verified).
> 121 frames @ 24 fps. The variant that fits a free Kaggle T4 / 8 GB laptop. One 16x16x4 VAE covers text- and image-to-video.

</details>

## Voice, TTS & Audio

| Tool | Model / ID | Licence | Cost | Hardware | Status | Role |
|---|---|---|---|---|---|---|
| [Kokoro-82M](https://www.cartesia.ai/learn/open-source-tts) | `kokoro-82M-v1.0` | Apache-2.0 | $0.00 | CPU or ~2-3 GB VRAM; ~90 MB quantised | ✅ current | **primary** |
| [Chatterbox / Chatterbox Turbo](https://www.tryspeakeasy.io/blog/open-source-text-to-speech-2026) | `chatterbox-turbo (350M) / chatterbox-multilingual (500M)` | MIT | $0.00 | ~4-8 GB VRAM | ✅ current | brand voice |
| [F5-TTS](https://www.codesota.com/guides/tts-models) | `F5-TTS v1 Base` | MIT (code) / CC-BY-NC-4.0 (weights) | $0.00 | ~4 GB VRAM | ✅ current | research only |
| [Fish Audio S2 Pro](https://pinggy.io/blog/best_open_source_self_hosted_text_to_speech_models/) | `fish-audio-s2-pro (~4.4B)` | Fish Audio Research License | Commercial licence required | 12-24 GB VRAM | ✅ current | research only |
| [edge-tts](https://github.com/rany2/edge-tts/issues/490) | `en-US-AriaNeural et al.` | LGPL-3.0 client; Microsoft service ToU | $0.00 | CPU | ✅ current | optional |

<details><summary>Notes, free-tier reality and verification dates</summary>

**Kokoro-82M** — free tier: Fully free, runs on CPU. Commercial use: Yes. Verified 2026-10-26 (verified).
> 54 voices, 8 languages, ~1060 Elo, no voice cloning. Apache-2.0 is why it is the default: the entire pipeline stays commercially shippable.

**Chatterbox / Chatterbox Turbo** — free tier: Fully free self-hosted. Commercial use: Yes (output carries an imperceptible watermark). Verified 2026-10-26 (verified).
> The permissive-licence option when you need zero-shot cloning (~5-10 s reference). MIT code AND weights -- unlike F5-TTS.

**F5-TTS** — free tier: Free for research / non-commercial. Commercial use: NO (weights are non-commercial). Verified 2026-10-26 (verified).
> Excellent cloning, but the weights licence forbids commercial use. Excluded from the default pipeline for that reason alone.

**Fish Audio S2 Pro** — free tier: Research / non-commercial only. Commercial use: NO without a paid licence. Verified 2026-10-26 (verified).
> Top of several 2026 blind-test leaderboards (1116 Elo) and 80+ languages -- but the 'now open-source' marketing conflicts with the actual weights licence. Read it before you ship.

**edge-tts** — free tier: Free (unofficial use of the Edge read-aloud service). Commercial use: Unclear -- service, not a licence grant. Verified 2026-10-26 (verified).
> MUST be >= 7.3.1: Microsoft rotated Sec-MS-GEC on 2026-10-12 and every earlier release 403s. Also 403s from GitHub-hosted runners. Never the CI default; never for a client deliverable without review.

</details>

## Alignment & Captions

| Tool | Model / ID | Licence | Cost | Hardware | Status | Role |
|---|---|---|---|---|---|---|
| [WhisperX](https://pypi.org/project/whisperx/) | `whisperx 3.8.x (wav2vec2 forced alignment)` | BSD-2-Clause | $0.00 | CPU works; GPU 30-100x faster | ✅ current | **primary** |
| [faster-whisper](https://awesomeosai.com/self-hosted/speech-to-text) | `CTranslate2 Whisper large-v3` | MIT | $0.00 | 2-4 GB VRAM or CPU | ✅ current | fallback |

<details><summary>Notes, free-tier reality and verification dates</summary>

**WhisperX** — free tier: Fully free. Commercial use: Yes. Verified 2026-10-26 (verified).
> Pin >=3.8.4: 3.8.2 and 3.8.3 were yanked (missing word timestamps for digits/symbols). Alignment is a separate wav2vec2 stage -- ASR timestamps alone drift hundreds of ms.

**faster-whisper** — free tier: Fully free. Commercial use: Yes. Verified 2026-10-26 (community).
> Still the engine inside WhisperX. Upstream is quiet (last release 1.2.1, Oct 2025) but the CTranslate2 runtime underneath is active. Word timestamps are approximate (+/-100-500 ms) -- align, don't trust.

</details>

## Orchestration & Assembly

| Tool | Model / ID | Licence | Cost | Hardware | Status | Role |
|---|---|---|---|---|---|---|
| [ComfyUI](https://docs.comfy.org) | `comfyui` | GPL-3.0 | $0.00 | GPU; CPU possible but impractical | ✅ current | **primary** |
| [FFmpeg](https://ffmpeg.org) | `ffmpeg 7.x` | LGPL-2.1+ (or GPL-2.0+ depending on build flags) | $0.00 | CPU | ✅ current | assembly |
| [GitHub Actions](https://docs.github.com/en/actions) | `ubuntu-latest runners` | GitHub ToS | $0.00 on public repos | CPU only (no GPU) | ✅ current | scheduler |
| [n8n (self-hosted Community)](https://docs.n8n.io/n8n-community-license/community-license/license-faq) | `n8n` | Sustainable Use License (source-available, NOT OSI open source) | $0.00 self-hosted | Docker; 1-2 GB RAM | ✅ current | visual orchestration |

<details><summary>Notes, free-tier reality and verification dates</summary>

**ComfyUI** — free tier: Fully free self-hosted. Commercial use: Yes (GPL: obligations attach if you distribute). Verified 2026-10-26 (community).
> Ships Wan 2.2 14B FLF2V and 5B templates. Our graphs are tokenised API exports; validate node classes against /object_info before rendering (scripts/validate_comfy.py).

**FFmpeg** — free tier: Fully free. Commercial use: Yes (respect the build's licence). Verified 2026-10-26 (verified).
> Verified in this repo against 7.0.2 static: libass, loudnorm, sidechaincompress, tpad, freezedetect all present. Needs libass to burn ASS.

**GitHub Actions** — free tier: Unlimited for public repos; 2000 min/month private. Commercial use: Yes. Verified 2026-10-26 (verified).
> Perfect for assembly, registry refresh and cron. Not for diffusion. Artifacts expire (90 days default) -- keep state in the DB + artifact, not in git.

**n8n (self-hosted Community)** — free tier: Free self-hosted, unlimited executions, no node cap. Commercial use: Yes for internal use / client work where only you edit workflows; a commercial licence is required if outsiders build workflows through your instance. Verified 2026-10-26 (verified).
> n8n 3.0 (Oct 2026) is Docker-only and removes the Function/Cron nodes -> our workflows use Code + Schedule Trigger. Git version control is an Enterprise feature.

</details>

## Provenance & liveness

| Tool | Source | Confidence | Verified | GitHub stars | Last push | Repo | Licence check |
|---|---|---|---|---|---|---|---|
| WhisperX | <https://pypi.org/project/whisperx/> | verified | 2026-10-26 | — | — | m-bain/whisperx | not checked |
| faster-whisper | <https://awesomeosai.com/self-hosted/speech-to-text> | community | 2026-10-26 | — | — | SYSTRAN/faster-whisper | not checked |
| Chatterbox / Chatterbox Turbo | <https://www.tryspeakeasy.io/blog/open-source-text-to-speech-2026> | verified | 2026-10-26 | — | — | resemble-ai/chatterbox | not checked |
| F5-TTS | <https://www.codesota.com/guides/tts-models> | verified | 2026-10-26 | — | — | SWivid/F5-TTS | not checked |
| Fish Audio S2 Pro | <https://pinggy.io/blog/best_open_source_self_hosted_text_to_speech_models/> | verified | 2026-10-26 | — | — | — | not checked |
| Kokoro-82M | <https://www.cartesia.ai/learn/open-source-tts> | verified | 2026-10-26 | — | — | hexgrad/kokoro | not checked |
| edge-tts | <https://github.com/rany2/edge-tts/issues/490> | verified | 2026-10-26 | — | — | rany2/edge-tts | not checked |
| FLUX.1 (local) | <https://github.com/black-forest-labs/flux> | unverified | 2026-10-26 | — | — | black-forest-labs/flux | not checked |
| Nano Banana 2 | <https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image> | verified | 2026-10-26 | — | — | — | not checked |
| Nano Banana 2.1 (Gemini 3.1 Flash Image successor) | <https://ai.google.dev/gemini-api/docs/pricing> | verified | 2026-10-26 | — | — | — | not checked |
| Nano Banana Pro | <https://ai.google.dev/gemini-api/docs/pricing> | verified | 2026-10-26 | — | — | — | not checked |
| ComfyUI | <https://docs.comfy.org> | community | 2026-10-26 | — | — | comfyanonymous/ComfyUI | not checked |
| FFmpeg | <https://ffmpeg.org> | verified | 2026-10-26 | — | — | FFmpeg/FFmpeg | not checked |
| GitHub Actions | <https://docs.github.com/en/actions> | verified | 2026-10-26 | — | — | — | not checked |
| n8n (self-hosted Community) | <https://docs.n8n.io/n8n-community-license/community-license/license-faq> | verified | 2026-10-26 | — | — | n8n-io/n8n | not checked |
| FramePack | <https://github.com/lllyasviel/FramePack> | verified | 2026-10-26 | — | — | lllyasviel/FramePack | not checked |
| Gemini Omni 1.1 Flash | <https://ai.google.dev/gemini-api/docs/pricing> | verified | 2026-10-26 | — | — | — | not checked |
| Hailuo / MiniMax H3 (free tier) | <https://aireiter.com/blog/hailuo-ai-pricing> | verified | 2026-10-26 | — | — | — | not checked |
| HunyuanVideo 1.5 | <https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5> | verified | 2026-10-26 | — | — | Tencent-Hunyuan/HunyuanVideo-1.5 | not checked |
| Kling 3.0 (free web tier) | <https://aireiter.com/blog/kling-ai-free-tier-2026> | verified | 2026-10-26 | — | — | — | not checked |
| LTX-2.5 | <https://pinggy.io/blog/best_video_generation_ai_models/> | verified | 2026-10-26 | — | — | Lightricks/LTX-Video | not checked |
| Wan 2.2 FLF2V / I2V-A14B | <https://github.com/Wan-Video/Wan2.2> | verified | 2026-10-26 | — | — | Wan-Video/Wan2.2 | not checked |
| Wan 2.2 TI2V-5B | <https://github.com/Wan-Video/Wan2.2> | verified | 2026-10-26 | — | — | Wan-Video/Wan2.2 | not checked |

---

### How to update this file

1. Read the primary source (vendor pricing/licence page, model card, repo).
2. Edit the entry in `registry/tools.json`; set `verified_at` to today and `confidence` to `verified`.
3. `python -m scripts.video_pipeline.cli registry refresh --github` (liveness + licence cross-check).
4. `python -m scripts.video_pipeline.cli registry render` and commit with the source links in the message.

CI runs the staleness gate daily; a stale primary tool fails the build rather than silently rotting.
