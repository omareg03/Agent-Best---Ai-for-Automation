# Contributing

## The one non-negotiable rule

**A change is not done until it has been executed.** This repo exists because
"it should work" pipelines do not. Before you open a PR:

```bash
make check        # compile + storyboard + graphs + registry + 34 tests
make selftest     # offline end-to-end with real FFmpeg (must be 26/26)
```

If your change touches rendering, also run the example film and verify it:

```bash
python -m scripts.video_pipeline.cli run example --engine mock
python -m scripts.video_pipeline.cli verify example
```

## Adding a tool to the registry

1. Read the **primary** source (vendor pricing page, licence text, model card, repo).
   Not a blog post about the vendor.
2. Add the entry to `registry/tools.json` with `verified_at: <today>`,
   `confidence: verified`, and a `source` URL.
3. If the tool contradicts common advice, add a `corrections` entry. That section is the
   most valuable part of the registry.
4. `python -m scripts.video_pipeline.cli registry refresh --github` (licence cross-check)
   then `registry render`, and commit both files together.

Never write `confidence: verified` for something you did not read. Use
`community` or `unverified` — the pipeline reads this field to decide what it may default to.

## Adding an engine

1. `scripts/video_pipeline/engines/your_engine.py`, subclassing `VideoEngine`.
2. Register it in `engines/__init__.py` (name → family).
3. Add a graph template under `workflows/comfyui/` if it wraps ComfyUI. Every graph must
   use `__PROMPT__`, `__START_IMAGE__` and `__SEED__` — `validate_comfy.py` enforces this.
4. **Honesty requirement:** if you could not execute a render (no GPU, no key, unknown wire
   format), mark it in the module docstring *and* gate it behind a probe, exactly like
   `gemini_omni.py`. Silent "it works" is the failure mode this repo was built to avoid.

## Changing prompts

Editing `prompts/*.md` changes `prompt_template_fingerprint()` and therefore invalidates
every scene's hash. That is intentional and asserted by a test. Update the test if you
change the mechanism, never the assertion.

## Code conventions

- Python 3.10+, standard library first. Runtime deps are `pillow`, `numpy`,
  `imageio-ffmpeg` — keep it that way.
- No network calls outside `keyframes.py`, `engines/gemini_omni.py`, `tts.py` and
  `registry_update.py`.
- Errors: raise the typed errors in `errors.py` with a `hint` that tells the operator what
  to do next. A stack trace with no next action is a bug.
- Never `print()` from library code; the CLI owns stdout, and `--json` must keep stdout
  parseable (logs go to stderr).

## Commits

```
feat(media): refuse to chain a near-black final frame
fix(media): FFmpeg 7 re-times setpts graphs to 25 fps -> set rate on the encoder
docs(registry): correct Kling free-tier claim (web-only, non-commercial)
test(captions): assert burned captions are legible mid-cue
```

State *why* in the body when the change looks arbitrary. Future-you will need it.
