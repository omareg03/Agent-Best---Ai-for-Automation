# PLAN.md — Sequential Thinking Trace

> This is the *deliberation artifact* for this repository. It records how the system was
> designed, which options were rejected and why, and what is verified vs. assumed.
> Protocol: **Observe → Decompose → Branch → Verify → Synthesize**.
> Compiled: **2026-10-26** (all tool facts verified live on this date; see `registry/`).

---

## 0. Observe — what actually exists

| Observation | Evidence | Consequence |
|---|---|---|
| Repo was an empty shell | `README.md` = 33 bytes, `git log` = 1 commit | Greenfield: full architecture is ours to define |
| Sandbox has **no ffmpeg, no SQLite CLI, no fonts beyond DejaVu** | `command -v ffmpeg` → missing | Pipeline must *resolve* FFmpeg (env → PATH → `imageio-ffmpeg`), never hardcode it |
| Sandbox has **no GPU, no model weights, no API keys** | n/a | Every remote adapter needs a **deterministic offline mock** or the repo cannot be tested. A pipeline you can't run is a slide deck |
| `pip` is PEP-668 externally managed | install attempt | Use a venv; keep runtime deps tiny so CI is fast |
| Python 3.11, Node 22, `gh`/`git` authenticated | `--version` | CI + n8n JSON + GitHub Actions are all first-class targets |

## 1. Decompose — the irreducible problem

Long-form AI video is not "one big generation". It is **five independent failure domains**:

1. **Identity drift** — the character changes face/wardrobe between shots.
2. **Temporal seams** — clips cut with a visible jump at boundaries.
3. **Duration mismatch** — narration is 7.4 s, the model emits 5.0 s.
4. **Resumability** — a 12-minute render dies at scene 31/44 and restarts from zero.
5. **Staleness** — the model you integrated last month is deprecated today.

Each gets an explicit mechanism below. A pipeline that does not address all five is a demo.

## 2. Branch — options considered, and the decision

### 2.1 Image anchor (character consistency)

| Option | Cost / access | Verdict |
|---|---|---|
| **Nano Banana 2.1** (`gemini-nano-banana-2.1`), up to 14 reference images | **No free Gemini API tier for image output.** $0.0336/1K, $0.0168 batch | ✅ **Primary** — best price/consistency; free *consumer* routes exist (Gemini app, AI Mode 25 img/24h, Flow 50 credits/day) but they are not automatable |
| Nano Banana 2 (`gemini-3.1-flash-image`) | $0.067/1K | ❌ **Deprecated, shutdown 2026-10-29** — 3 days after this plan. Do not build new work on it |
| SDXL / FLUX local | Free, needs ≥12 GB VRAM | ✅ Documented fallback for zero-budget/offline; weaker identity retention |
| Imagen 4 | Paid, no reference-image identity control | ❌ Loses the whole point |

**Decision:** adapter interface + `gemini-nano-banana-2.1` default, **reference-sheet-first** workflow
(master character sheet → 2 keyframes/scene conditioned on it). Model ID lives in config, not code.

### 2.2 Video engine

| Option | Min VRAM | Native len | License | Verdict |
|---|---|---|---|---|
| **Wan 2.2 FLF2V / I2V-A14B** | 16–24 GB (FP8/GGUF) | 81 fr @16 fps | **Apache-2.0** | ✅ **Primary** — true first/last-frame conditioning solves seams *by construction* |
| **Wan 2.2 TI2V-5B** | ~8–12 GB | 121 fr @24 fps | **Apache-2.0** | ✅ Low-VRAM primary (Kaggle T4×2 / 8 GB) |
| **Gemini Omni 1.1 Flash** (`gemini-omni-1.1-flash`) | hosted | 3–10 s, extend to 40 s | paid API, ~$0.10/s 720p | ✅ **Hosted fallback** — has first/last-frame control + native audio; *no free API tier* |
| LTX-2.5 | 12–32 GB (distilled/FP8) | 20 s, native audio | LTX Community (<$10M ARR free) | ⚠️ Strong but **not Apache** — enterprise must check the ceiling |
| HunyuanVideo 1.5 | 14 GB w/ offload | 5–10 s | Tencent Community — **excludes EU/UK/South Korea** | ⚠️ Jurisdiction-blocked for many users; document, don't default |
| FramePack (13B) | **6 GB** | **up to 120 s** | Apache-2.0 | ⚠️ **Legacy / unmaintained** (repo effectively abandoned). Keep as a documented long-take option, never the default |
| Kling / Hailuo free web tiers | — | 5–6 s | **No commercial use, watermark, no API on free** | ❌ Cannot be automated legitimately; listed as manual previz only |

**Decision:** one `ComfyUIEngine` that swaps **graphs** (`wan22_flf2v`, `wan22_ti2v_5b`, `framepack_long_i2v`)
+ one `GeminiOmniEngine` HTTP adapter + `MockEngine` for CI. **No engine is hardcoded into the orchestrator.**

> The charter's "Kling/Hailuo free daily tiers" and "free Nano Banana API" claims are **factually stale**.
> Kling's free tier is 66 credits/day, web-only, watermark, non-commercial. Hailuo replaced daily credits with a
> one-time 3-day welcome grant. Gemini image API has **no** free tier. The registry records these corrections
> rather than repeating them.

### 2.3 TTS

| Option | License | Verdict |
|---|---|---|
| **Kokoro-82M** | Apache-2.0, CPU-viable, 54 voices | ✅ **Default** — commercial-safe, no network, no watermark |
| **Chatterbox / Turbo** | MIT, zero-shot cloning | ✅ When a specific brand voice is required (output watermarked) |
| Edge-TTS | LGPL client, MS service | ⚠️ **Broke 2026-10-12** (Sec-MS-GEC DRM rotation → HTTP 403); fixed in **7.3.0/7.3.1**. Also 403s from GitHub-hosted runners. Pin `>=7.3.1` or don't use in CI |
| F5-TTS | code MIT / **weights CC-BY-NC** | ❌ Non-commercial weights — excluded from the default path |
| Fish Audio S2 Pro | Research license | ❌ Commercial use requires a paid license |

### 2.4 Alignment & assembly
- **WhisperX 3.8.x** (wav2vec2 forced alignment, ±~50 ms) for word timing; `whisperx==3.8.3` was yanked → pin `>=3.8.4`.
  Fallback: deterministic estimator from known narration text (we generate the text, so we always *have* the transcript).
- **FFmpeg** for everything deterministic: `concat`, `tpad`, `loudnorm` (two-pass), `sidechaincompress`, `ass`.
- No Premiere-style GUI step. Everything reproducible from a storyboard hash.

### 2.5 Orchestration
- **GitHub Actions** = free scheduler/compute for assembly + daily registry refresh.
- **n8n self-hosted** = the same pipeline, visual, for non-engineers. Note the **Sustainable Use License**
  (fine for internal use; a commercial license is needed if *others* build workflows through your instance)
  and **n8n 3.0 (Oct 2026): Docker-only, Function/Cron nodes removed** → our workflows use `code` + `scheduleTrigger`.
- State in **SQLite** (WAL) so a dead runner resumes exactly where it stopped.

## 3. Verify — what is proven vs. assumed

| Claim | How verified | Status |
|---|---|---|
| `gemini-nano-banana-2.1` exists, is the current default; 2.1 GA 2026-10-06 | Primary Google docs + pricing table | ✅ Verified |
| REST shape `POST /v1/models/{id}:generateContent`, `x-goog-api-key`, `contents[].parts[]`, `generationConfig.responseModalities` | Primary Google docs (curl sample, fetched 2026-10-26) | ✅ Verified |
| Gemini image API has **no** free output tier | Google pricing page rows | ✅ Verified |
| `gemini-omni-1.1-flash` GA 2026-08-27; 3–10 s clips, 40 s extensions, 24 fps, 360p–4K | Multiple 2026 sources | ✅ Verified (secondary sources) |
| Wan 2.2 = Apache-2.0; 14B @16 fps/81 frames, 5B @24 fps/121 frames | Wan2.2 repo + ComfyUI guides | ✅ Verified |
| FramePack: 6 GB, 120 s, unmaintained | Repo + discussion "project has been abandoned" | ✅ Verified |
| WhisperX `3.8.3` yanked, use `>=3.8.4` | PyPI release history | ✅ Verified |
| edge-tts <7.3.0 broken since 2026-10-12 | Multiple issue/PR reports with dates | ✅ Verified |
| **Exact ComfyUI node class names for Wan 2.2 FLF2V** | **Cannot verify without a live ComfyUI** | ⚠️ **Assumed + self-validating** (`scripts/validate_comfy.py` diffs graphs against `/object_info`) |
| **Gemini Omni long-running video endpoint shape** | Docs describe capability, not the wire format we use | ⚠️ **Assumed + probe-gated** (`pipeline comfy`/`probe` must pass before a paid render) |
| Live image/video generation in this sandbox | No GPU, no API key | ❌ **Not executed** — CI path is `engine=mock`, and the mock is deterministic |

**Rule adopted:** *any* capability that could not be executed in this environment is marked in code and docs
with the exact reason, plus the command that proves or disproves it on a real box. No silent "it works".

## 4. Synthesize — the architecture that follows

```
storyboard.json ──validate──► plan (durations, cost, 3–15 min budget)
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        ▼                          ▼                           ▼
  Stage A: images           Stage B: video              Stage C: audio/assembly
  reference sheet           ComfyUI FLF2V chain         Kokoro/Edge TTS per scene
  2 keyframes / scene  →    last clean frame  ──►       WhisperX word timings
  (identity lock)           next clip's frame 0         FFmpeg: fit → concat →
                                                        loudnorm → duck → burn ASS
        └────────────── SQLite state (resume from exact failed clip) ──────────┘
                                   │
                     GitHub Actions (free) / n8n (visual)
```

**Continuity has two independent guarantees**, because one is never enough:
1. *By construction* — clip N+1's first frame **is** clip N's extracted last frame (FLF2V).
2. *By measurement* — dHash distance between boundary frames is asserted under a threshold;
   a violation fails the render instead of shipping a visible jump.

**Duration has an explicit policy**, because models don't care about your script:
narration is generated *first*, the clip is then fitted to it (`tpad` hold / ping-pong / trim),
so audio never gets stretched and captions never drift.

**Resume has an invalidation rule**: a scene is reusable only if `status=done` **and** the file exists
**and** its `prompt_hash` still matches the storyboard. Change the prompt → that scene and everything
downstream re-renders. Nothing silently mixes stale footage with new footage.

---

### Non-goals (deliberate)
- Not a ComfyUI replacement, not a model trainer, not a video editor UI.
- No scraping of consumer free tiers (ToS violations + watermark + non-commercial terms).
- No secrets in the repo: `.env` is ignored, workflows use GitHub secrets.

### Known limits
- GitHub-hosted runners are CPU-only: they assemble, schedule and refresh the registry. **Diffusion happens
  on a GPU box** (local / Kaggle / Colab / RunPod) that reports back into the same state DB.
- `projects/**/renders` are **artifacts, not git objects** (see `.gitignore`).
