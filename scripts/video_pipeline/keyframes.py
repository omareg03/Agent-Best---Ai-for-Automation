"""Stage A -- identity lock.

Order matters: a master character/environment sheet is generated FIRST, then every
scene's start/end keyframe is generated with that sheet attached as a reference
image. Nano Banana 2.1 accepts up to 14 reference images; two or three are enough
for face + wardrobe + palette.

Wire format verified 2026-10-26 against Google's primary docs:
  POST {base}/{version}/models/{model}:generateContent
  header x-goog-api-key
  body {contents:[{role,parts:[{text},{inline_data:{mime_type,data}}]}],
        generationConfig:{responseModalities:["TEXT","IMAGE"], imageConfig:{...}}}
Images come back as inline_data parts (base64) -> decoded, magic-checked, hashed.

`MockImageClient` renders deterministic PNGs with Pillow so the whole pipeline
(including "the next clip starts on the previous last frame") is testable offline.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import (
    DEFAULT_IMAGE_MODEL,
    GEMINI_API_BASE,
    GEMINI_API_VERSION,
    HTTP_BACKOFF_BASE,
    HTTP_RETRIES,
    HTTP_TIMEOUT,
    IMAGE_MODEL_COSTS_USD,
    get_secret,
)
from .errors import EngineError
from .ffmpeg_util import assert_artifact

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


@dataclass
class KeyframeResult:
    path: Path
    model: str
    prompt_hash: str
    cost_usd: float
    reference_images: list[str]


# ---------------------------------------------------------------------------
# Gemini / Nano Banana
# ---------------------------------------------------------------------------
class GeminiImageClient:
    name = "gemini"

    def __init__(self, model: str = DEFAULT_IMAGE_MODEL, *, aspect_ratio: str = "16:9",
                 image_size: str = "1K", api_key: str | None = None) -> None:
        self.model = model
        self.aspect_ratio = aspect_ratio
        self.image_size = image_size
        self._api_key = api_key
        self._send_response_modalities = True  # dropped automatically if the API 400s

    # -- transport --------------------------------------------------------
    @property
    def api_key(self) -> str:
        if not self._api_key:
            self._api_key = get_secret("GEMINI_API_KEY", required=True)
        return self._api_key or ""

    def _payload(self, prompt: str, references: list[Path]) -> dict:
        parts: list[dict] = [{"text": prompt}]
        for ref in references:
            mime = "image/png" if ref.suffix.lower() == ".png" else "image/jpeg"
            parts.append(
                {
                    "inline_data": {
                        "mime_type": mime,
                        "data": base64.b64encode(ref.read_bytes()).decode("ascii"),
                    }
                }
            )
        config: dict = {}
        if self._send_response_modalities:
            config["responseModalities"] = ["TEXT", "IMAGE"]
        config["imageConfig"] = {"aspectRatio": self.aspect_ratio, "imageSize": self.image_size}
        return {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}

    def _post(self, payload: dict) -> dict:
        url = (
            f"{GEMINI_API_BASE}/{GEMINI_API_VERSION}/models/{self.model}:generateContent"
        )
        data = json.dumps(payload).encode()
        last_error = ""
        for attempt in range(HTTP_RETRIES):
            request = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:800]
                last_error = f"HTTP {exc.code}: {body}"
                if exc.code in (400, 404) and self._send_response_modalities and "responseModalities" in body:
                    # Some image models reject the legacy modality flag; retry without it.
                    self._send_response_modalities = False
                    payload = {**payload}
                    payload["generationConfig"] = {
                        k: v for k, v in payload["generationConfig"].items() if k != "responseModalities"
                    }
                    continue
                if exc.code in (429, 500, 502, 503, 504):
                    time.sleep(HTTP_BACKOFF_BASE * (2**attempt))
                    continue
                raise EngineError(
                    f"Gemini image request failed ({exc.code})",
                    hint=body,
                    stage="keyframes",
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc)
                time.sleep(HTTP_BACKOFF_BASE * (2**attempt))
        raise EngineError(
            f"Gemini image request exhausted {HTTP_RETRIES} attempts",
            hint=last_error,
            stage="keyframes",
        )

    # -- public -----------------------------------------------------------
    def generate(self, prompt: str, out_path: Path, *, references: list[Path] | None = None,
                 seed: int | None = None, size: tuple[int, int] | None = None,
                 stage_label: str = "") -> KeyframeResult:
        # `size` / `stage_label` are mock-only hints; the real API controls output
        # through generationConfig.imageConfig (aspect ratio + 1K/2K/4K).
        del size, stage_label
        if self.model in ("gemini-3.1-flash-image",):
            raise EngineError(
                "gemini-3.1-flash-image (Nano Banana 2) shuts down 2026-10-29 -- refusing to "
                "start new work on it",
                hint="set GEMINI_IMAGE_MODEL=gemini-nano-banana-2.1",
                stage="keyframes",
            )
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_hash = hashlib.sha256(f"{self.model}|{prompt}|{seed}".encode()).hexdigest()[:16]
        response = self._post(self._payload(prompt, references or []))

        candidates = response.get("candidates") or []
        if not candidates:
            feedback = response.get("promptFeedback", {})
            raise EngineError(
                "Gemini returned no candidates (likely a safety block)",
                hint=json.dumps(feedback)[:400] or "rephrase the prompt",
                stage="keyframes",
            )
        image_bytes = None
        text_note = ""
        for part in candidates[0].get("content", {}).get("parts", []) or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                image_bytes = base64.b64decode(inline["data"])
                break
            if part.get("text"):
                text_note += str(part["text"])[:200]
        if not image_bytes:
            raise EngineError(
                "Gemini response contained no image",
                hint=text_note or "model returned text only; check that the model id supports image output",
                stage="keyframes",
            )
        if not (image_bytes.startswith(PNG_MAGIC) or image_bytes.startswith(JPEG_MAGIC)):
            raise EngineError(
                "decoded payload is not a PNG/JPEG",
                hint=f"first bytes: {image_bytes[:12]!r}",
                stage="keyframes",
            )
        out_path.write_bytes(image_bytes)
        assert_artifact(out_path, min_bytes=2048, kind="keyframe")
        return KeyframeResult(
            path=out_path,
            model=self.model,
            prompt_hash=prompt_hash,
            cost_usd=IMAGE_MODEL_COSTS_USD.get(self.model, 0.0336),
            reference_images=[str(p) for p in (references or [])],
        )

    def probe(self) -> dict:
        """One cheap text-only call: proves key, model id and network path."""
        payload = {"contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ready"}]}]}
        response = self._post(payload)
        text = ""
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                text += part.get("text", "")
        return {"model": self.model, "reply": text.strip()[:80], "ok": bool(text.strip())}


# ---------------------------------------------------------------------------
# Mock: deterministic, dependency-light
# ---------------------------------------------------------------------------
def _palette(seed: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    digest = hashlib.sha256(str(seed).encode()).digest()
    top = (40 + digest[0] % 120, 40 + digest[1] % 120, 60 + digest[2] % 130)
    bottom = (digest[3] % 90, digest[4] % 90, 20 + digest[5] % 90)
    return top, bottom


class MockImageClient:
    """Deterministic 'character sheet' + keyframe painter.

    The point is not beauty: it is that frame N+1 provably derives from frame N,
    so continuity measurement and resume logic can be tested without a GPU.
    """

    name = "mock"

    def __init__(self, model: str = "mock-painter", *, aspect_ratio: str = "16:9") -> None:
        self.model = model
        self.aspect_ratio = aspect_ratio

    def generate(self, prompt: str, out_path: Path, *, references: list[Path] | None = None,
                 seed: int | None = None, size: tuple[int, int] = (1280, 720),
                 stage_label: str = "") -> KeyframeResult:
        from PIL import Image, ImageDraw, ImageFilter

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        width, height = size
        seed_value = seed if seed is not None else int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)

        top, bottom = _palette(seed_value)
        image = Image.new("RGB", (width, height), top)
        draw = ImageDraw.Draw(image)
        for y in range(height):  # vertical gradient
            ratio = y / max(1, height - 1)
            colour = tuple(int(top[i] * (1 - ratio) + bottom[i] * ratio) for i in range(3))
            draw.line([(0, y), (width, y)], fill=colour)

        # Environment: horizon + receding light band (gives dHash something stable).
        horizon = int(height * 0.62)
        draw.rectangle([0, horizon, width, height], fill=(max(0, bottom[0] - 12), max(0, bottom[1] - 10), max(0, bottom[2] - 8)))
        for index in range(6):
            y = horizon + int(index * height * 0.05)
            draw.line([(0, y), (width, y)], fill=(min(255, bottom[0] + 18), min(255, bottom[1] + 22), min(255, bottom[2] + 26)), width=2)

        # The "character": a stable silhouette whose position shifts per shot.
        body_x = int(width * (0.38 + (seed_value % 7) * 0.03))
        body_y = int(height * 0.30)
        body_w, body_h = int(width * 0.10), int(height * 0.34)
        draw.rounded_rectangle(
            [body_x, body_y + body_h * 0.32, body_x + body_w, body_y + body_h],
            radius=int(body_w * 0.22), fill=(238, 232, 220),
        )
        radius = int(body_w * 0.42)
        draw.ellipse(
            [body_x + body_w // 2 - radius, body_y, body_x + body_w // 2 + radius, body_y + radius * 2],
            fill=(232, 205, 178),
        )
        draw.ellipse(
            [body_x + body_w // 2 - radius, body_y, body_x + body_w // 2 + radius, body_y + radius],
            fill=(48, 38, 34),
        )

        if references:
            # Blend a reference strip so "identity lock" has a visible effect.
            try:
                ref = Image.open(references[0]).convert("RGB").resize((width // 5, height // 5))
                image.paste(ref, (width - width // 5 - 12, 12))
                draw.rectangle(
                    [width - width // 5 - 14, 10, width - 10, 12 + height // 5],
                    outline=(255, 214, 120), width=2,
                )
            except Exception:  # noqa: BLE001 - a missing/broken reference must not stop a mock render
                pass

        image = image.filter(ImageFilter.GaussianBlur(radius=0.6))
        draw = ImageDraw.Draw(image)
        label = stage_label or prompt.strip().splitlines()[0][:56]
        draw.text((18, 16), label, fill=(255, 255, 255))
        draw.text((18, height - 26), f"mock | seed {seed_value}", fill=(220, 220, 220))

        image.save(out_path, format="PNG")
        assert_artifact(out_path, min_bytes=2048, kind="mock keyframe")
        return KeyframeResult(
            path=out_path,
            model=self.model,
            prompt_hash=hashlib.sha256(f"{prompt}|{seed_value}".encode()).hexdigest()[:16],
            cost_usd=0.0,
            reference_images=[str(p) for p in (references or [])],
        )


def get_image_client(engine: str, *, model: str = DEFAULT_IMAGE_MODEL, aspect_ratio: str = "16:9"):
    if engine == "mock":
        return MockImageClient(aspect_ratio=aspect_ratio)
    if engine == "gemini":
        return GeminiImageClient(model=model, aspect_ratio=aspect_ratio)
    raise EngineError(f"unknown image engine '{engine}' (choose: gemini, mock)")


# ---------------------------------------------------------------------------
# Prompt assembly (uses prompts/ templates so the wording is reviewable in git)
# ---------------------------------------------------------------------------
_FALLBACK_CHARACTER_SHEET = (
    "Production character reference sheet for {title}. Subject: {character_sheet_prompt}. "
    "Neutral seamless background, even lighting. Show full-body front, three-quarter, profile "
    "and a head-and-shoulders close-up with an identical face, hairstyle, wardrobe and body "
    "proportions in every view. No text, no borders, no labels. Style: {style_anchor}. "
    "Avoid: {negative_prompt}."
)

_FALLBACK_KEYFRAME = (
    "A single cinematic still: the {which} keyframe of scene {scene_id}. {visual_prompt} "
    "{frame_prompt}. Camera: {camera_motion}. Style: {style_anchor}. "
    "Character reference: {character_sheet}. Reproduce the reference character exactly. "
    "Avoid: {negative_prompt}."
)


def _safe_format(template: str, fallback: str, **values: object) -> str:
    """Templates are user-editable; a stray brace must not break a paid render."""
    for candidate in (template, fallback):
        if not candidate:
            continue
        try:
            return candidate.format(**values)
        except (KeyError, IndexError, ValueError):
            continue
    return fallback


def load_prompt_template(name: str) -> str:
    from .config import PROMPTS_DIR

    path = PROMPTS_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def character_sheet_prompt(storyboard) -> str:
    return _safe_format(
        load_prompt_template("character_sheet.md"),
        _FALLBACK_CHARACTER_SHEET,
        title=storyboard.title,
        character_sheet_prompt=storyboard.character_sheet_prompt or "a consistent lead character",
        style_anchor=storyboard.style_anchor or "cinematic, natural light, 35mm",
        negative_prompt=storyboard.negative_prompt or "no text, no watermark",
    )


def keyframe_prompt(storyboard, scene, *, which: str = "start") -> str:
    base = scene.visual_prompt
    extra = scene.start_frame_prompt if which == "start" else scene.end_frame_prompt
    return _safe_format(
        load_prompt_template("keyframe_pair.md"),
        _FALLBACK_KEYFRAME,
        scene_id=scene.scene_id,
        visual_prompt=base,
        frame_prompt=extra or ("opening composition" if which == "start" else "closing composition"),
        camera_motion=scene.camera_motion,
        style_anchor=storyboard.style_anchor or "cinematic, natural light, 35mm",
        character_sheet=storyboard.character_sheet_prompt or "the reference character",
        negative_prompt=storyboard.negative_prompt or "no text, no watermark, no extra limbs",
        which=which,
    )
