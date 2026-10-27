# Runbook

Operational procedures. Every command is copy-pasteable from the repo root.

## 0. Prerequisites

```bash
# FFmpeg WITH libass (burned captions) and ffprobe. imageio-ffmpeg is not enough.
sudo apt-get install -y ffmpeg fonts-dejavu-core     # Debian/Ubuntu
brew install ffmpeg                                  # macOS

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.
python -m scripts.video_pipeline.cli selftest        # proves your machine can run this
```

`selftest` must print `SELFTEST PASS (26/26 checks)`. If it does not, nothing else will.

## 1. Start a film

```bash
python -m scripts.video_pipeline.cli init my-film --title "My Film"
# edit projects/my-film/storyboard.json  (see prompts/director_system.md for the contract)
python -m scripts.video_pipeline.cli storyboard check projects/my-film/storyboard.json
python -m scripts.video_pipeline.cli plan my-film --engine wan22_flf2v
```

`plan` prints estimated runtime and API cost **before** anything is generated. Read it.
A 20-second estimate means you wrote a trailer, not a long-form film.

## 2. Choose your engines

| Situation | Command |
|---|---|
| No GPU, no key, just checking the plumbing | `run my-film --engine mock` |
| RTX 3090/4090 (24 GB) or better | `run my-film --engine wan22_flf2v` |
| 8-12 GB (3060, Kaggle T4, laptop) | `run my-film --engine wan22_ti2v_5b` |
| One 60-120 s unbroken take | `run my-film --engine framepack_long_i2v` |
| No GPU but a Google API budget | `run my-film --engine gemini_omni --ack-experimental` |

Start ComfyUI first (`python main.py --listen 0.0.0.0 --port 8188`) and validate:

```bash
python -m scripts.video_pipeline.cli engine probe --engine wan22_flf2v
python scripts/validate_comfy.py --graph wan22_flf2v
```

`missing_node_classes` in that output means stop: your graph expects nodes your
ComfyUI build does not have, and a render will fail mid-way (after paying for it).

## 3. Render, interrupt, resume

```bash
python -m scripts.video_pipeline.cli run my-film --engine wan22_flf2v
# ... Ctrl-C, laptop sleeps, cloud box dies ...
python -m scripts.video_pipeline.cli resume my-film --engine wan22_flf2v
```

Resume semantics: a scene is skipped only if `status=done` **and** its file exists
**and** its prompt hash still matches. Everything else re-renders.

Inspect what happened:

```bash
python -m scripts.video_pipeline.cli status my-film --events 40
```

## 4. Iterate on one shot

```bash
# 1. edit that scene's prompt in the storyboard
# 2. the hash changes -> only that scene re-renders
python -m scripts.video_pipeline.cli run my-film --engine wan22_flf2v
```

Editing `prompts/*.md` invalidates **every** scene (the fingerprint is in the hash).
That is intentional: silently mixing footage from two different prompt styles is worse
than a re-render.

## 5. Verify before you publish

```bash
python -m scripts.video_pipeline.cli verify my-film
```

Checks: every scene `done`, artefacts exist and are non-trivial, no seam above
dHash 12, no duration drift > 0.3 s, final has audio, resolution and frame rate match.
Exit code 1 = do not publish.

## 6. Known failure signatures

| Message | Cause | Fix |
|---|---|---|
| `ffmpeg not found` | no system ffmpeg | `apt-get install ffmpeg` or `pip install imageio-ffmpeg` |
| `this ffmpeg build has no libass` | imageio-ffmpeg static build | install system ffmpeg |
| `continuity break: boundary dHash N > 12` | engine ignored the start frame | use `wan22_flf2v`, strengthen `start_frame_prompt`, or `--allow-seam` to degrade to a fade |
| `ends in black (max luma …)` | clip fades to black | make `end_frame_prompt` bright and populated |
| `ComfyUI rejected the graph` | node mismatch / missing model file | `validate_comfy.py`, check filenames in `workflows/comfyui/*.json` |
| `edge-tts … returns HTTP 403` | version < 7.3.1 (Sec-MS-GEC rotation) | `pip install -U 'edge-tts>=7.3.1'` or use Kokoro/mock |
| `Kokoro TTS unreachable` | server not running | start Kokoro-FastAPI, or `--tts mock` |
| `Gemini … 429` | quota | the client backs off 4x; reduce concurrency or `--limit` |
| `scene X is not done` during assembly | partial render | `resume` first — assembly never ships a hole |

## 7. Cost control

- `--limit N` renders N scenes and stops. Use it after every prompt change.
- `plan` before `run`. Images = `scenes × 2 + 1`; video = seconds × $/s for hosted engines.
- Local engines cost $0 in API fees; the cost is GPU-hours. `wan22_ti2v_5b` on a free
  Kaggle T4 is the cheapest real-footage route (`docs/KAGGLE_COLAB_GPU.md`).
- Every render writes `cost_usd` per scene into `state.db` — `status` totals it.

## 8. Publishing

`projects/<slug>/renders/final.mp4` (captions burned) and `subtitles/<slug>.srt`
(sidecar for accessibility). Upload `manifest.json` with it: it records the storyboard
hash, engine, model, seed, seam distances and ffmpeg version, which is what you need
when someone asks how a frame was made.
