# n8n + GitHub Actions orchestration

## Why both

| | GitHub Actions | n8n (self-hosted) |
|---|---|---|
| Best at | scheduled work, CI gates, reproducible pipelines | visual editing, webhooks, non-engineers |
| Cost | free on public repos (CPU only) | free self-hosted, unlimited executions |
| Weakness | no GPU, awkward for interactive editing | you operate it; licence has a boundary |

Neither duplicates the other: both call **the same CLI**, so there is exactly one
implementation of the pipeline.

## n8n licence boundary (read this before shipping)

n8n is **source-available under the Sustainable Use License, not OSI open source.**
The practical line, as documented by n8n in October 2026:

- ✅ Allowed: run it for your own company, build and run workflows for clients on your
  instance, charge for that work — as long as **your clients cannot open the editor or
  change workflow logic**.
- ❌ Not allowed: host n8n as a service where clients build workflows themselves, or let
  external end users configure workflows through your product (that needs an Enterprise
  licence, even if they never see the n8n UI).
- ⚠️ **n8n 3.0 (October 2026)**: Docker-only installs (npm/npx dropped), and the legacy
  Function, Function Item and Cron nodes are removed. The workflows here use `code` and
  `scheduleTrigger`, so they are 3.x-ready.

## Import

```bash
# UI: Workflows → Import from File
workflows/n8n/00-registry-daily.json      # 24h registry refresh + staleness gate
workflows/n8n/01-storyboard-render.json   # webhook: storyboard JSON -> render -> verify
```

Environment for the n8n container:

```yaml
PIPELINE_REPO=/opt/agent-best          # path to this repo inside the container
DEFAULT_ENGINE=wan22_flf2v
GITHUB_TOKEN=ghp_...                    # 60 -> 5000 requests/hour for registry refresh
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/...   # optional
EXECUTIONS_TIMEOUT=14400                # 4h: a 15-minute film takes hours to diffuse
```

`executeCommand` nodes run inside the n8n container: mount the repo and give it Python,
FFmpeg and the pipeline's dependencies, or point the command at an SSH call to the GPU box.

## Workflow 00 — registry refresh (daily)

```
scheduleTrigger (24h) → executeCommand: cli registry refresh --github
                     → executeCommand: cli registry check
                     → code: summarise pass/fail
                     → IF stale → HTTP POST alert
```

What the script does — and deliberately does **not** do:

- ✅ Refreshes mechanically checkable facts: stars, last push date, archived flag, and a
  cross-check of the curated licence against the repo's SPDX id.
- ❌ Does **not** invent prices, licences or benchmarks. Those require reading the primary
  source; the script only records `verified_at` and fails when it goes stale.

That split is the point: automation for liveness, human/agent verification for facts.

## Workflow 01 — render webhook

```bash
curl -X POST http://localhost:5678/webhook/render \
  -H 'Content-Type: application/json' \
  -d @projects/example/storyboard.json
```

```
webhook → code:validate (+ build commands) → IF valid
        ├─ true  → write storyboard → plan → run (resumable) → verify → parse → respond
        └─ false → respond 400
```

The response is machine-readable, and it tells the caller how to recover:

```json
{
  "ok": false,
  "status": 500,
  "project": "my-film",
  "scenesProcessed": 7,
  "issues": ["scene 08: status=failed (ComfyUI rejected the graph)"],
  "resumeHint": "Re-POST the same storyboard — finished scenes are reused."
}
```

That `resumeHint` is the whole design in one field: a failed webhook call is not a
disaster, because the seventh scene's neighbours are already rendered and paid for.

## GitHub Actions

| Workflow | Trigger | Purpose |
|---|---|---|
| `ci.yml` | every push / PR | compile, 34 tests, graph validation, registry drift check, staleness gate, offline end-to-end, artefact upload |
| `registry-refresh.yml` | daily 06:17 UTC | liveness + licence refresh, auto-commit, opens/updates a staleness issue |
| `render-assembly.yml` | manual | CPU assembly + verification; mock or uploaded artefacts |
| `gpu-render.yml` | manual | self-hosted GPU runner; uploads `state.db` **even on failure** |

### Registering the GPU runner

```bash
# on the GPU box (RTX / RunPod pod / workstation)
./config.sh --url https://github.com/<owner>/<repo> --token <RUNNER_TOKEN> \
            --labels self-hosted,linux,gpu,comfyui
./run.sh
```

`gpu-render.yml` targets `runs-on: [self-hosted, linux, gpu, comfyui]` and uses a
`gpu-render` environment, so you can require manual approval before burning hours.

## Secrets

| Name | Used by | Notes |
|---|---|---|
| `GEMINI_API_KEY` | keyframes, Gemini Omni | no free tier for image output |
| `COMFYUI_URL` | ComfyUI engines | must be reachable **from the runner**, not from your laptop |
| `GITHUB_TOKEN` | registry refresh | provided automatically inside Actions |

Never commit `.env` — it is git-ignored, and `.env.example` documents every variable.
