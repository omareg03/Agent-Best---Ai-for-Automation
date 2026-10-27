# YouTube package, runner API and n8n setup

## Important execution boundary

The two `video_packages/` directories provide complete creative/SEO source packages. They are **not rendered videos**. Before the assembler can run, every package block needs a measured narration WAV under `audio/` and a generated/source MP4 under `clips/`. This repository does not call paid Nano Banana, Gemini video, Veo, or vidIQ accounts on your behalf.

## Generate overlays after the WAV masters

The storyboard target is five seconds per block, but narration is authoritative. Generate the 12 audio masters, measure their true durations, then generate scene source with those durations:

```bash
python scripts/manim_blocks.py video_packages/flannan-coat/storyboard.json \
  --audio-dir video_packages/flannan-coat/audio \
  --output video_packages/flannan-coat/manim_blocks_generated.py --fps 60
```

The generated scene's `self.wait(D_i)` is measured from each WAV via FFmpeg. To render a scene, install Manim and run e.g. `manim -pqh --fps 60 video_packages/flannan-coat/manim_blocks_generated.py Block02`. The Manim code includes crisp source labels, locator markers, timeline overlays and the 101 m lighthouse elevation gauge. The overlays are not a surveyed basemap; all map pins and sources need human verification.

## Assemble the supplied blocks

```bash
python scripts/long_video_chain.py video_packages/flannan-coat --fps 30 --captions --resume
python scripts/long_video_chain.py video_packages/koh-chang-ghost-ship --fps 30 --captions --resume
```

The engine checks all inputs, uses each WAV duration as `D_i`, removes the first video frame on blocks 02–12, applies a centered 1.12× punch-in from 2.5 to 3.5 seconds where the measured clip is long enough, normalizes to CFR 30 or 60 fps and `yuv420p`, concatenates audio, applies `loudnorm=I=-14:TP=-1.5:LRA=11`, generates <=4-word ASS caption cues, and records source prompt/seed/model label/input hashes/frame hashes/status in SQLite. Resume reuses an assembled block only when its media inputs still match. Inspect the final video and seams manually before upload.

## Run the private runner bridge for n8n

`workflows/n8n_long_video_pipeline.json` calls a scoped HTTP runner rather than putting user data into a shell command. The runner accepts only fixed project slugs and engine names, passes argv arrays to subprocesses, limits request size, serializes jobs and requires a bearer token.

Build the optional runner image with `docker build -f Dockerfile.runner -t local/video-pipeline-runner .`. On a private Docker network shared with n8n, run it with a locally generated secret (do not commit or share the value):

```bash
export PIPELINE_RUNNER_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker run --rm --name pipeline-runner --network YOUR_PRIVATE_N8N_NETWORK \\
  -e PIPELINE_RUNNER_TOKEN -e PIPELINE_RUNNER_HOST=0.0.0.0 \\
  -e PIPELINE_RUNNER_PORT=8095 \\
  -e COMFYUI_URL=http://comfyui:8188 \\
  local/video-pipeline-runner
```

For local non-Docker development, the equivalent is `PIPELINE_RUNNER_TOKEN=<local-secret> PYTHONPATH=. python scripts/pipeline_runner_api.py`.

Expose this endpoint only on a private Docker network or behind an authenticated TLS reverse proxy and firewall. Do not publish port 8095 directly to the public Internet. Place n8n and the runner on the same private network using the DNS name `pipeline-runner`, then import the JSON. In both HTTP Request nodes, replace the example Authorization header with a **credential stored in n8n**, not a literal repository secret. Set n8n's HTTP timeout and execution timeout to at least four hours for a full render. Protect the n8n webhook itself with its own authentication/rate limiting.

`POST /v1/render` accepts `project_slug`, `engine`, `resume`, `dry_run`, and optional `request_id`. For a video package, `dry_run: true` reports which supplied media files are missing; it does not generate them. `POST /v1/registry/refresh` runs the repository's curated registry refresh. This API has not been deployed to a live n8n instance here; import, credentials, network policy and one dry-run must be exercised by the operator before production.

## vidIQ and publishing

`youtube_seo.json` intentionally marks all paid vidIQ metrics unverified. Paste a dated export before representing search volume, competition, Outlier, VPH, swipe rate or APV as measured. Performance targets cannot be guaranteed. Fact-check map coordinates, current site condition/access, historical claims, media rights and affiliate disclosures before upload.
