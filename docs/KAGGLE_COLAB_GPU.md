# Free GPU routes (Kaggle / Colab / RunPod)

GitHub-hosted runners are CPU-only. Diffusion needs a GPU. This is how to get one
for free, and what actually fits in the VRAM you get.

## 1. What fits where

| Hardware | Session limit | Fits | Suggested engine |
|---|---|---|---|
| **Kaggle**: 2× T4 (16 GB each) | ~9 h (12 h with phone verification), 30 GPU h/week | Wan 2.2 **TI2V-5B** comfortably; 14B only quantised and slowly | `wan22_ti2v_5b` |
| **Colab free**: T4 16 GB | ~4 h, disconnects on idle | Wan 2.2 TI2V-5B | `wan22_ti2v_5b` |
| **Colab Pro**: L4 24 GB / A100 40 GB | longer | 14B FP8 (L4, tight) / 14B comfortably (A100) | `wan22_flf2v` |
| **RunPod / Lambda** (paid, ~$0.30–0.60/clip) | unlimited | 14B FP16 | `wan22_flf2v` |
| **Local RTX 3060 12 GB** | — | TI2V-5B (720p, 24 fps) | `wan22_ti2v_5b` |
| **Local RTX 4090 24 GB** | — | 14B FP8 + offload | `wan22_flf2v` |

Rule of thumb derived from the file sizes: one 14B expert at fp8 is ~14.3 GB, plus a
~6.7 GB umT5 text encoder. On 16 GB you must quantise (GGUF Q5) and offload; on 24 GB
fp8 fits with ~10 GB left for activations at 640×640.

## 2. Kaggle notebook (free, 30 GPU h/week)

```python
# Cell 1 — GPU check
!nvidia-smi --query-gpu=name,memory.total --format=csv

# Cell 2 — ComfyUI
!git clone --depth 1 https://github.com/comfyanonymous/ComfyUI
%cd ComfyUI
!pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
!pip install -q -r requirements.txt

# Cell 3 — Wan 2.2 TI2V-5B weights (≈18 GB download; use the Kaggle dataset cache to survive resets)
%cd /kaggle/working/ComfyUI
!mkdir -p models/diffusion_models models/text_encoders models/vae
!wget -q -P models/diffusion_models   https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors
!wget -q -P models/text_encoders      https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors
!wget -q -P models/vae                https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors

# Cell 4 — start ComfyUI in the background
!nohup python main.py --listen 0.0.0.0 --port 8188 > /kaggle/working/comfy.log 2>&1 &
```

Then, from this repo (same machine or via a tunnel):

```bash
export COMFYUI_URL=http://127.0.0.1:8188
export PYTHONPATH=.
python scripts/validate_comfy.py --graph wan22_ti2v_5b   # prove the node classes exist
python -m scripts.video_pipeline.cli run my-film --engine wan22_ti2v_5b --limit 2
```

`notebooks/kaggle_wan22_render.ipynb` packages this with the repo clone and the
validation gate built in — import it to Kaggle and run.

## 3. The interruption problem (this is the real one)

Kaggle/Colab sessions die: idle timeout, 9-hour cap, OOM. A 40-scene render will not
finish in one session. That is exactly why this pipeline keeps SQLite state per project.

**Survive a dead session:**

1. Keep the project folder on persistent storage (`/kaggle/working`, or a mounted
   dataset / Drive folder), not `/tmp`.
2. Upload the whole `projects/<slug>/` folder (including `state.db` and `clips/`) as a
   Kaggle dataset between sessions, or push it to a private HF dataset repo.
3. On the next session, restore the folder and run `resume`:

```bash
python -m scripts.video_pipeline.cli status my-film     # see what survived
python -m scripts.video_pipeline.cli resume my-film --engine wan22_ti2v_5b
```

Only scenes with `status != done`, a missing file, or a changed prompt hash re-render.

## 4. Cost reality check

| Route | Cost for a 3-minute film (~20 clips) | Notes |
|---|---|---|
| Kaggle T4, TI2V-5B | **$0** (inside the weekly quota) | ~7–15 min/clip at 720p; ~4 sessions |
| Colab free | **$0** | Shorter sessions; expect more interruptions |
| Local 4090, 14B FP8 | **$0** API, electricity | ~3–6 min/clip — the fastest sane option |
| RunPod A100, 14B FP16 | ~$6–12 | Best quality per hour |
| Gemini Omni (hosted) | ~$90 for 15 min @ 720p ($0.10/s) | No GPU needed; probe first |
| Nano Banana 2.1 keyframes | ~$1.40 (41 images × $0.0336) | 2 keyframes/scene + 1 sheet |

Images are cheap; video is the expensive part. Generate one keyframe pair per scene,
look at a contact sheet, **then** commit to the clip renders.

## 5. Preflight before you burn GPU hours

```bash
python scripts/validate_comfy.py --graph wan22_ti2v_5b   # node classes present?
python -m scripts.video_pipeline.cli engine probe --engine wan22_ti2v_5b
python -m scripts.video_pipeline.cli run my-film --engine wan22_ti2v_5b --limit 1   # one scene
python -m scripts.video_pipeline.cli verify my-film     # inspect before scaling up
```

If the smoke scene's seam dHash is above 12, fix the graph or the `start_frame_prompt`
*before* rendering nineteen more.
