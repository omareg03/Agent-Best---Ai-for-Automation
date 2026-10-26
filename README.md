# Agent-Best — AI for Automation

**A production pipeline for long-form AI video: 3–15 minute films that don't drift, don't jump at the cuts, and don't restart from zero when a render dies.**

Most "AI video" repos give you a prompt and a 5-second clip. A 12-minute film is 40–90 clips, and at that length five things break: the character changes face, every cut is visible, narration never matches clip length, one crash costs the whole render, and the model you integrated is deprecated by the time you ship. This repo is built around those five failures.

```bash
git clone https://github.com/omareg03/Agent-Best---Ai-for-Automation && cd Agent-Best---Ai-for-Automation
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && export PYTHONPATH=.
python -m scripts.video_pipeline.cli selftest      # 26 checks, ~8s, no GPU, no API key
```

```
SELFTEST PASS  (26/26 checks, 8.3s)
final: projects/selftest-demo/renders/final.mp4  (13.92s)
```

That command renders a real film end-to-end on your machine with **mock models and real FFmpeg** — keyframes, narration, chained clips, seam measurement, concat, loudness normalisation, burned karaoke captions — and then deliberately deletes a clip and edits a prompt to prove that resume and invalidation work. Demo output: [`assets/demo/selftest.mp4`](assets/demo/selftest.mp4).

---

## Proof before claims

Every number below came from a run in this repo, not an estimate.

| Claim | Evidence |
|---|---|
| Offline end-to-end works on a CPU-only box | `selftest` → **26/26 checks**, 8.3 s |
| A full long-form film renders | `projects/example`: **12 scenes → 109.65 s master**, verify PASS |
| Continuity is measured, not assumed | max boundary dHash across 12 chained scenes: **7** (threshold 12) |
| Resume is surgical | after deleting 1 clip: that scene re-rendered, the other 11 untouched |
| Prompt edits invalidate stale footage | `done → pending` on prompt change (asserted) |
| Unit + integration coverage | **34 tests pass** in ~1 s |
| FFmpeg behaviour is verified, not assumed | 7.0.2 static; `libass`, `loudnorm`, `sidechaincompress`, `tpad` all exercised |

```bash
python -m scripts.video_pipeline.cli plan example --engine wan22_flf2v
python -m scripts.video_pipeline.cli run  example --engine wan22_flf2v
python -m scripts.video_pipeline.cli resume example --engine wan22_flf2v
python -m scripts.video_pipeline.cli verify example
```

---

## The five failure domains (and the mechanism for each)

| # | Failure | What it looks like | Mechanism in this repo |
|---|---|---|---|
| 1 | **Identity drift** | Shot 12 is a different person | Master character sheet generated once → every keyframe conditioned on it (`keyframes.py`) |
| 2 | **Temporal seams** | A visible jump at every cut | Clip N+1 starts on clip N's **extracted last clean frame** (FLF2V), then the seam is *measured* with dHash and fails the run above threshold |
| 3 | **Duration mismatch** | 7.4 s of narration over a 5.0 s clip | Narration is generated **first**; the clip is fitted to it (`tpad` hold / ping-pong / trim) |
| 4 | **Unresumable renders** | Box dies at scene 31/44, start over | SQLite state + prompt-hash invalidation → re-render exactly one clip |
| 5 | **Staleness** | The model is deprecated a week later | `AI_TOOL_REGISTRY.md` with provenance, deprecation watch, and a CI staleness gate |

### Why frame chaining actually eliminates seams

```text
Scene 1 ──► clip_01.mp4 ──► extract last clean frame ──┐
                                                        │ (mandatory first frame)
Scene 2 ◄── keyframe_end (imagined) ◄─────────────────┘ clip_02.mp4 ──► …
```

Two independent guarantees, because one is never enough:

1. **By construction** — with Wan 2.2 FLF2V, the first frame of the next clip *is* the last frame of the previous one.
2. **By measurement** — `check_boundary()` compares dHash of the conditioning frame against frame 0 of the result. Distance > 12 → `VerificationError`, the scene is marked failed, and the film is not published with a visible jump.

Naive chaining (`ffmpeg -sseof -0.04`) fails in practice because clips often end on a fade or black frame. `extract_last_clean_frame()` samples a short tail, rejects near-black frames (luma < 10) and takes the last surviving one — the black-frame guard is covered by a test.

---

## Engine matrix

| Engine | VRAM | Clip length | Licence | Role |
|---|---|---|---|---|
| `wan22_flf2v` | 16–24 GB (FP8/GGUF) | 81 frames @ 16 fps | **Apache-2.0** | **Primary** — true first/last-frame conditioning |
| `wan22_ti2v_5b` | 8–12 GB | 121 frames @ 24 fps | **Apache-2.0** | Low-VRAM (Kaggle T4, RTX 3060, laptop) |
| `framepack_long_i2v` | 6 GB | 60–120 s single take | Apache-2.0 | Legacy; upstream is unmaintained — pin your models |
| `gemini_omni` | hosted | 3–10 s → 40 s | Paid API (~$0.10/s) | Hosted fallback, **probe-gated** (see limitations) |
| `mock` | none | any | — | CI / offline proof, real FFmpeg, honours first/last frame |

Engines are swappable by name: `--engine wan22_ti2v_5b`. The orchestrator has no knowledge of any specific backend.

---

## Verified facts, and the folklore this repo rejects

Live-verified **2026-10-26**; full table with sources in [`AI_TOOL_REGISTRY.md`](AI_TOOL_REGISTRY.md).

| Widely repeated claim | Reality |
|---|---|
| "Nano Banana has a free API tier" | **No free tier for API image output.** $0.0336 per 1K image (Nano Banana 2.1, GA 2026-10-06). Free access exists only in consumer surfaces that can't be automated |
| "Use `gemini-3.1-flash-image`" | **Nano Banana 2 shuts down 2026-10-29.** The pipeline refuses to start new work on it |
| "Kling/Hailuo free daily tiers are automatable" | Kling: 66 credits/day, **web only**, watermarked, **non-commercial**. Hailuo: one-time welcome grant, no recurring daily credits |
| "FramePack is state of the art" | Still the cheapest path to 120 s takes on 6 GB, but upstream is **unmaintained** → legacy, not default |
| "edge-tts just works" | **Broke on 2026-10-12** (Sec-MS-GEC rotation → HTTP 403 on every request). Needs ≥ 7.3.1, and it 403s from GitHub runners, so it is not a CI engine |
| "Open weights = Apache-2.0" | HunyuanVideo 1.5's licence **excludes the EU, UK and South Korea**. LTX-2.x is free only below $10M revenue. F5-TTS weights are CC-BY-NC. n8n is source-available, not open source |

The registry is enforced, not decorative: `registry check` fails CI when a tool goes 30 days without re-verification, and a daily Action opens an issue instead of silently rotting.

---

## Architecture

```text
storyboard.json ──validate──► plan (durations, scene count, cost — before any GPU time)
                                   │
      ┌────────────────────────────┼─────────────────────────────┐
      ▼                            ▼                             ▼
 Stage A: identity          Stage B: video                Stage C: audio/assembly
 character sheet            FLF2V chain from the          Kokoro/Edge/mock TTS
 2 keyframes / scene   →    previous last clean frame →   word-level timings
 (Nano Banana refs)         seam measured, not hoped      concat → loudnorm →
                                                          duck music → burn ASS
      └──────────────── SQLite state: resume from the exact failed clip ────────┘
                                   │
             GitHub Actions (assemble + schedule) · n8n (visual) · GPU box (diffuse)
```

Full detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · deliberation trace: [`PLAN.md`](PLAN.md)

### Invariants enforced by code (not documentation)

- A scene is reusable **only** if `status='done'` **and** the file exists **and** the prompt hash matches.
- Editing a prompt **template** invalidates every scene (fingerprint is part of the hash) — no silent mixing of two styles.
- A failed scene **never** anchors the next one (chaining from stale footage is worse than a clean cut).
- Assembly **refuses** to run on a partial film.
- Frame rate is set on the encoder **and asserted** — FFmpeg 7 silently re-times a graph ending in `setpts=PTS-STARTPTS` to 25 fps.
- Caption cues are clamped inside the **measured** audio duration.
- Money is spent only after a successful `probe()`.

---

## Repository layout

```text
prompts/        director system prompt, storyboard schema, style & caption guides,
                character-sheet and keyframe templates (editing these invalidates renders)
workflows/
  comfyui/      tokenised API graphs: Wan 2.2 FLF2V, TI2V-5B, FramePack long-take
  n8n/          importable workflows: 24h registry refresh, storyboard→render webhook
scripts/
  video_pipeline/   the package (config, state, media, captions, align, tts,
                    keyframes, engines/, pipeline, selftest, registry_update)
  validate_comfy.py graph validator (offline structure + live /object_info diff)
database/       SQLite schema (projects, scenes, append-only events, renders)
registry/       tools.json (source of truth), history.jsonl
.github/workflows/  ci · registry-refresh (daily) · render-assembly (CPU) · gpu-render
docs/           ARCHITECTURE · RUNBOOK · KAGGLE_COLAB_GPU · N8N_AND_AUTOMATION
tests/          34 tests: timing arithmetic, subtitle escaping, resume, seams, encodes
projects/       example film (12 scenes) + your projects (artefacts git-ignored)
```

---

## Automation: GitHub Actions + n8n + SQLite

| Layer | What it does | Where |
|---|---|---|
| **CI** | compile, tests, graph validation, registry render-drift check, staleness gate, offline end-to-end, uploads the rendered film as an artefact | `.github/workflows/ci.yml` |
| **Registry** | daily 06:17 UTC liveness + licence cross-check; commits the refresh; opens an issue when something is overdue | `registry-refresh.yml` |
| **Assembly** | deterministic half of the pipeline on CPU runners (no GPU needed) | `render-assembly.yml` |
| **GPU render** | self-hosted runner on your GPU box; state uploaded **even on failure** so the next run resumes | `gpu-render.yml` |
| **n8n** | visual orchestration for non-engineers, calling the same CLI — no second implementation | `workflows/n8n/` |

SQLite (WAL) holds every scene's prompt hash, seed, model, keyframe hashes, clip hash, cost and error, plus an append-only events log. That is what makes "resume from the exact failed clip" a fact rather than a hope.

---

## Honest limitations

A pipeline that hides its unknowns is a liability. These are explicit:

1. **No GPU in the build environment.** The open-weight path (`wan22_*`, `framepack`) was validated structurally — graphs parse, tokens substitute, node names come from ComfyUI's published templates — but **no Wan render was executed here**. `python scripts/validate_comfy.py --graph wan22_flf2v` diffs every node class against your server's `/object_info` before you spend GPU time. That check is the contract.
2. **Gemini Omni's wire format is unverified.** Google documents the capability, not the exact response envelope, and no API key existed here. The engine is therefore **probe-gated**: it refuses to generate until `probe()` succeeds, and on an unexpected envelope it prints the first 400 characters of the real response so the fix is a 5-line patch instead of an investigation.
3. **The mock engine produces abstract placeholder footage**, not photoreal video. Its purpose is that timings, chaining, captions and resume are *real* — which is where pipelines actually fail.
4. **No lip-sync.** Nothing in the free/self-hosted open-weight tier does reliable mouth-sync; writing scenes that need it will disappoint you.
5. **GitHub-hosted runners cannot diffuse.** They assemble, schedule and verify. Diffusion needs a GPU box — see [`docs/KAGGLE_COLAB_GPU.md`](docs/KAGGLE_COLAB_GPU.md).

## Licence

Code in this repo: **MIT** (see `LICENSE`). **Model weights are not covered by that licence** — and they differ sharply: Wan 2.2 is Apache-2.0, HunyuanVideo 1.5 excludes the EU/UK/South Korea, LTX-2.x requires a paid licence above $10M revenue, F5-TTS weights are non-commercial. The registry records the licence of every tool for exactly this reason. Check before you ship commercially.
