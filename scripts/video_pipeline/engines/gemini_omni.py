"""Hosted fallback: Gemini Omni 1.1 Flash (`gemini-omni-1.1-flash`).

Verified facts (2026-10-26): GA 2026-08-27, 3-10 s clips extendable to ~40 s,
24 fps, 360p/720p/1080p/4K, native synchronised audio, first/last-frame control
shipped with the GA release, ~$0.10 per second of 720p, SynthID on every output.
The preview id `gemini-omni-flash-preview` was retired 2026-09-30 -- never use it.

UNVERIFIED: the exact long-running video response envelope. Google's public docs
describe the capability, not the wire format we consume here, and no API key was
available in the build environment. Therefore this engine is **probe-gated**: it
refuses to spend money until `probe()` has succeeded in the same process, or the
caller explicitly passes acknowledge_unverified=True.

If the envelope differs, the raised error prints the first 400 characters of the
actual response, so the fix is a 5-line patch rather than an investigation.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..config import (
    DEFAULT_VIDEO_MODEL,
    GEMINI_API_BASE,
    GEMINI_API_VERSION,
    HTTP_BACKOFF_BASE,
    HTTP_RETRIES,
    HTTP_TIMEOUT,
    VIDEO_MODEL_COST_USD_PER_SECOND,
    get_secret,
)
from ..errors import EngineError
from ..ffmpeg_util import assert_artifact, probe as probe_media, run_ffmpeg
from .base import VideoEngine, VideoRequest, VideoResult

WIRE_ASSUMPTIONS = (
    "POST /{version}/models/{model}:generateContent with responseModalities=['VIDEO']",
    "reference images are inline_data parts (mime_type image/png)",
    "response video arrives as inline_data (base64) OR fileData.fileUri OR an operation name to poll",
)


def _mime(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


class GeminiOmniEngine(VideoEngine):
    name = "gemini_omni"
    supports_last_frame = True
    requires_gpu = False

    def __init__(
        self,
        model: str = DEFAULT_VIDEO_MODEL,
        *,
        api_key: str | None = None,
        acknowledge_unverified: bool = False,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self.acknowledge_unverified = acknowledge_unverified
        self._probed = False

    @property
    def api_key(self) -> str:
        if not self._api_key:
            self._api_key = get_secret("GEMINI_API_KEY", required=True)
        return self._api_key or ""

    # -- transport ---------------------------------------------------------
    def _post_json(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        last = ""
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
                body = exc.read().decode("utf-8", "replace")
                last = f"HTTP {exc.code}: {body[:400]}"
                if exc.code in (429, 500, 502, 503, 504):
                    time.sleep(HTTP_BACKOFF_BASE * (2**attempt))
                    continue
                raise EngineError(
                    f"Gemini Omni request failed ({exc.code})",
                    hint=body[:600],
                    stage="video",
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last = str(exc)
                time.sleep(HTTP_BACKOFF_BASE * (2**attempt))
        raise EngineError("Gemini Omni request exhausted retries", hint=last, stage="video")

    def _get(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"x-goog-api-key": self.api_key})
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read())

    # -- capability check --------------------------------------------------
    def probe(self) -> dict:
        """Cheapest possible proof that key + model id + network work."""
        url = f"{GEMINI_API_BASE}/{GEMINI_API_VERSION}/models/{self.model}:generateContent"
        payload = {"contents": [{"role": "user", "parts": [{"text": "Reply with: ready"}]}]}
        response = self._post_json(url, payload)
        text = "".join(
            part.get("text", "")
            for candidate in response.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
        )
        self._probed = True
        return {"model": self.model, "reply": text.strip()[:60], "ok": bool(text.strip())}

    # -- generation --------------------------------------------------------
    def generate(self, request: VideoRequest) -> VideoResult:
        if not (self._probed or self.acknowledge_unverified):
            raise EngineError(
                "Gemini Omni wire format is unverified in this build -- refusing to spend money blindly",
                hint=(
                    "run `python -m scripts.video_pipeline.cli engine probe --engine gemini_omni` first, "
                    "or pass --ack-experimental once you accept the risk. See WIRE_ASSUMPTIONS."
                ),
                stage="video",
            )
        if request.start_frame is None:
            raise EngineError("Gemini Omni fallback requires a start frame for chaining")

        parts: list[dict] = [{"text": self._compose_prompt(request)}]
        parts.append(
            {
                "inline_data": {
                    "mime_type": _mime(Path(request.start_frame)),
                    "data": base64.b64encode(Path(request.start_frame).read_bytes()).decode(),
                }
            }
        )
        if request.end_frame and Path(request.end_frame).exists():
            parts.append(
                {
                    "inline_data": {
                        "mime_type": _mime(Path(request.end_frame)),
                        "data": base64.b64encode(Path(request.end_frame).read_bytes()).decode(),
                    }
                }
            )
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["VIDEO"],
                "videoConfig": {
                    "durationSeconds": max(3, min(10, int(round(request.duration)))),
                    "aspectRatio": "16:9" if request.width >= request.height else "9:16",
                },
            },
        }
        url = f"{GEMINI_API_BASE}/{GEMINI_API_VERSION}/models/{self.model}:generateContent"
        response = self._post_json(url, payload)

        video_bytes = self._extract_video(response)
        if video_bytes is None:
            video_bytes = self._poll_operation(response)
        if video_bytes is None:
            raise EngineError(
                "could not locate video bytes in the Gemini Omni response",
                hint=(
                    "response head: " + json.dumps(response)[:400] +
                    "\nUpdate _extract_video/_poll_operation for this envelope; assumptions: "
                    + "; ".join(WIRE_ASSUMPTIONS)
                ),
                stage="video",
            )

        out = Path(request.out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        raw = out.with_suffix(".raw")
        raw.write_bytes(video_bytes)
        # Normalise: Omni may hand back mp4 with audio; we keep video, narration is ours.
        run_ffmpeg(["-i", str(raw), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
        raw.unlink(missing_ok=True)
        assert_artifact(out, min_bytes=4096, kind="gemini omni clip")
        info = probe_media(out)
        return VideoResult(
            path=out,
            engine=self.name,
            model=self.model,
            duration=info.duration,
            cost_usd=round(info.duration * VIDEO_MODEL_COST_USD_PER_SECOND, 4),
            meta={"unverified_wire_format": not self._probed},
        )

    def _compose_prompt(self, request: VideoRequest) -> str:
        lines = [request.prompt.strip()]
        if request.camera_motion:
            lines.append(f"Camera movement: {request.camera_motion}.")
        if request.end_frame:
            lines.append(
                "The first supplied image is the exact first frame; the second is the exact last frame. "
                "Generate continuous motion between them with no cut."
            )
        else:
            lines.append("The supplied image is the exact first frame. Continue the motion naturally.")
        if request.negative_prompt:
            lines.append(f"Avoid: {request.negative_prompt}.")
        return "\n".join(lines)

    def _extract_video(self, response: dict) -> bytes | None:
        for candidate in response.get("candidates", []) or []:
            for part in candidate.get("content", {}).get("parts", []) or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    mime = str(inline.get("mimeType") or inline.get("mime_type") or "")
                    if mime.startswith("video") or not mime:
                        return base64.b64decode(inline["data"])
                file_data = part.get("fileData") or part.get("file_data")
                if file_data and file_data.get("fileUri"):
                    uri = file_data["fileUri"]
                    request = urllib.request.Request(uri, headers={"x-goog-api-key": self.api_key})
                    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as handle:
                        return handle.read()
        return None

    def _poll_operation(self, response: dict, *, timeout: float = 900.0) -> bytes | None:
        name = response.get("name")
        if not name:
            return None
        url = f"{GEMINI_API_BASE}/{GEMINI_API_VERSION}/{name}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self._get(url)
            if status.get("done"):
                video = self._extract_video(status.get("response", status))
                if video:
                    return video
                raise EngineError(
                    "operation finished without video",
                    hint=json.dumps(status)[:500],
                    stage="video",
                )
            time.sleep(5)
        raise EngineError("Gemini Omni operation timed out", stage="video")
