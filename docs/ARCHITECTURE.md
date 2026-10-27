# Architecture

> Read `PLAN.md` first for *why*. This document is *how*, with the invariants that
> the code actually enforces.

## 1. The five failure domains

Long-form AI video does not fail because a model is bad. It fails in five specific,
independent ways — and each has exactly one mechanism in this repo:

| Failure | Symptom | Mechanism | Where |
|---|---|---|---|
| Identity drift | The character is a different person in shot 12 | Reference sheet → 2 keyframes/scene, conditioned on it | `keyframes.py` |
| Temporal seams | A visible jump at every cut | FLF2V chaining from the *extracted last clean frame* + measured dHash gate | `media.py`, `pipeline.py` |
| Duration mismatch | Narration runs 7.4 s over a 5.0 s clip | Narration first, then fit the clip (`tpad`/ping-pong/trim) | `pipeline.py` |
| Unresumable renders | Box dies at scene 31/44, restart from zero | SQLite state + prompt-hash invalidation | `state.py` |
| Staleness | The model you integrated is deprecated | Registry with provenance + staleness gate | `registry/tools.json` |

## 2. Data flow

```
storyboard.json                     (source of truth, versioned, reviewed in git)
      │
      ├── validate ────────────────► storyboard.validate_payload()   [no GPU spent]
      ├── hash ────────────────────► scene.prompt_hash()  (includes prompt templates)
      │
      ▼
┌───────────────────────────── Pipeline.run() ─────────────────────────────┐
│                                                                          │
│  Stage A  character_sheet.png  ──►  scene_NN_start.png                    │
│           (once, cached)            scene_NN_end.png                      │
│           GeminiImageClient | MockImageClient  ← identical interface      │
│                                                                          │
│  Stage B  narration.wav  (TTS first: duration is now a measured fact)     │
│                   │                                                      │
│                   ├─ target = max(narration + 0.45, requested, 2.0)       │
│                   ▼                                                      │
│           VideoEngine.generate(start=previous_last, end=end_keyframe)     │
│                   │                                                      │
│                   ├─ check_boundary(chain_start, clip)  → dHash ≤ 12     │
│                   ├─ fit_duration(clip, target)         → exact length   │
│                   └─ mux_audio(fitted, narration)       → segment.mp4    │
│                              │                                           │
│                              └─► extract_last_clean_frame() ──► next scene│
│                                                                          │
│  Stage C  concat ─► loudnorm ─► [music duck] ─► burn ASS ─► final.mp4    │
│                                                                          │
│  State    every transition written to state.db (scenes + append-only events)│
└──────────────────────────────────────────────────────────────────────────┘
```

## 3. Invariants the code enforces (not just documents)

1. **A scene is reusable only if `status='done'` AND the artefact exists AND
   `prompt_hash` matches.** Anything else re-renders. `state.is_reusable()`.
2. **The prompt template fingerprint is part of the hash.** Editing
   `prompts/keyframe_pair.md` invalidates every scene. `storyboard.prompt_template_fingerprint()`.
3. **A failed scene never anchors the next one.** On failure `previous_last = None`,
   so the next scene starts from its own keyframe rather than stale footage.
4. **A near-black final frame is refused.** Chaining it would produce a black flash;
   `extract_last_clean_frame()` raises instead. Threshold: luma ≥ 10.
5. **Assembly refuses to run on a partial film.** One non-`done` scene aborts with a
   resume hint rather than shipping a hole.
6. **Frame rate is set on the encoder and asserted.** FFmpeg 7 re-times a graph
   ending in `setpts=PTS-STARTPTS` to 25 fps; `encode_args()` + `assert_format()` stop it.
7. **Every subtitle cue fits inside the measured audio.** The estimator clamps to
   `duration` rather than expanding to a nominal WPM.
8. **Money is spent only after a probe.** `GeminiOmniEngine` refuses to generate until
   `probe()` has passed (or the caller passes `--ack-experimental`).

## 4. Engine abstraction

```
VideoEngine (engines/base.py)
├── MockVideoEngine        offline, FFmpeg+Pillow, honours first/last frame
├── ComfyVideoEngine       open weights; graph templates swapped by name
│     ├── wan22_flf2v      primary  (16-24 GB, Apache-2.0)
│     ├── wan22_ti2v_5b    low VRAM (8-12 GB, Apache-2.0)
│     └── framepack_long_i2v  legacy 60-120 s takes (6 GB, unmaintained)
└── GeminiOmniEngine       hosted fallback, probe-gated, ~$0.10/s
```

Adding an engine = one file + one registry entry. No orchestrator change.

## 5. State model

```sql
projects(id, slug, storyboard_hash, fps, width, height, engine …)
scenes(project_id, scene_id, ordinal, prompt_hash, status, seed,
       keyframe_*_sha, clip_path, clip_sha, clip_duration,
       narration_*, cost_usd, attempts, last_error …)
events(project_id, scene_id, kind, detail, created_at)   -- append-only audit
renders(project_id, kind, path, sha256, bytes, duration)
```

`scenes.status`: `pending → keyframes → video → audio → done` (or `failed`).
The `attempts` counter is the resume evidence: after deleting one clip, exactly one
scene's attempts increments (asserted in `selftest`).

## 6. Where compute runs

| Job | Runs on | Why |
|---|---|---|
| Diffusion (Stages A/B) | GPU box: local RTX, free Kaggle T4, Colab, RunPod | GitHub runners have no GPU |
| Assembly (Stage C) + verify | GitHub-hosted Actions (CPU) | deterministic, cheap, needs libass |
| Registry refresh | GitHub Actions cron | needs `GITHUB_TOKEN`, not a GPU |
| Interactive orchestration | n8n self-hosted | non-engineers drive the same CLI |

State is uploaded as an artefact even when a GPU job fails, so the next run resumes.

## 7. Extension points

| Want to… | Do this |
|---|---|
| Add a model | new engine in `scripts/video_pipeline/engines/`, register in `__init__.py` |
| Change look | edit `prompts/style_anchor.md` (invalidates renders, deliberately) |
| Change pacing | `config.py`: `NARRATION_TAIL_PAD`, `MIN/MAX_SCENE_SECONDS` |
| Add a caption style | `captions.build_ass()` (ASS is the only format that carries word timing) |
| Swap the database | `state.py` is the only module that speaks SQL (SQLite → Postgres is a port, not a rewrite) |
| Publish automatically | `.github/workflows/render-assembly.yml` → add an upload step |
