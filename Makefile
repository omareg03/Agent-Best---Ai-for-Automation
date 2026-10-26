# Convenience wrapper. Every target maps to the same CLI that CI runs.
# Nothing here is required: `python -m scripts.video_pipeline.cli ...` is the interface.

PY ?= python3
PIPELINE := $(PY) -m scripts.video_pipeline.cli
PROJECT ?= example

export PYTHONPATH := .

.PHONY: help install test selftest check plan render resume verify status registry graphs clean

help:            ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:         ## install runtime dependencies
	$(PY) -m pip install -r requirements.txt

install-gpu:     ## install GPU extras (whisperx, kokoro)
	$(PY) -m pip install -r requirements-gpu.txt

test:            ## unit + integration tests
	$(PY) -m pytest tests -v

selftest:        ## offline end-to-end proof (mock models, real FFmpeg)
	$(PIPELINE) selftest

check:           ## everything CI runs, minus the render
	$(PY) -m compileall -q scripts tests
	$(PIPELINE) storyboard check projects/$(PROJECT)/storyboard.json
	$(PY) scripts/validate_comfy.py --offline
	$(PIPELINE) registry render && $(PIPELINE) registry check
	$(PY) -m pytest tests -q

plan:            ## pre-flight: duration + cost, no generation
	$(PIPELINE) plan $(PROJECT)

render:          ## real render with the open-weight engine
	$(PIPELINE) run $(PROJECT) --engine wan22_flf2v

smoke:           ## one scene, mock engine, ~2 seconds
	$(PIPELINE) run $(PROJECT) --engine mock --limit 1 --no-captions

resume:          ## continue an interrupted render
	$(PIPELINE) resume $(PROJECT) --engine wan22_flf2v

verify:          ## post-render gate
	$(PIPELINE) verify $(PROJECT)

status:          ## state + audit events
	$(PIPELINE) status $(PROJECT)

registry:        ## refresh liveness + re-render the registry markdown
	$(PIPELINE) registry refresh --github
	$(PIPELINE) registry render

graphs:          ## validate ComfyUI graph templates against a live server
	$(PY) scripts/validate_comfy.py

clean:           ## remove generated media (keeps storyboards)
	find projects -mindepth 2 -maxdepth 2 -type d \
	  \( -name renders -o -name clips -o -name segments -o -name keyframes -o -name audio -o -name subtitles -o -name logs \) \
	  -exec rm -rf {} +
	find projects -name 'state.db*' -delete
	find projects -name 'manifest.json' -delete
