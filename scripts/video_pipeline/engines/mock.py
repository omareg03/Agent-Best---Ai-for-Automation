"""Offline engine: turns keyframes into a moving clip with FFmpeg + Pillow.

Why it exists: continuity, resume, captioning and assembly are the parts that
actually break in production, and none of them need a GPU to be tested. The mock
honours first/last-frame semantics (it interpolates and crops toward `end_frame`),
so `extract_last_clean_frame -> next clip` is exercised for real.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..errors import EngineError
from ..ffmpeg_util import assert_artifact, ffmpeg_bin, probe
from .base import VideoEngine, VideoRequest, VideoResult


class MockVideoEngine(VideoEngine):
    name = "mock"
    supports_last_frame = True
    requires_gpu = False

    def generate(self, request: VideoRequest) -> VideoResult:
        try:
            from PIL import Image, ImageDraw
        except ImportError as exc:  # pragma: no cover
            raise EngineError("Pillow is required for the mock engine", hint="pip install pillow") from exc

        width = request.width - (request.width % 2)
        height = request.height - (request.height % 2)
        fps = max(6, request.fps)
        frames = max(2, int(round(request.duration * fps)))
        out = Path(request.out_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if request.start_frame is None:
            raise EngineError("mock engine needs a start frame (chaining is the whole point)")

        start = Image.open(request.start_frame).convert("RGB").resize((width, height), Image.LANCZOS)
        end = None
        if request.end_frame and Path(request.end_frame).exists():
            end = Image.open(request.end_frame).convert("RGB").resize((width, height), Image.LANCZOS)

        # Pre-upscale so the push-in crop never samples below native resolution.
        zoom_canvas = start.resize((int(width * 1.12), int(height * 1.12)), Image.LANCZOS)

        command = [
            ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
        ]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdin is not None
        try:
            for index in range(frames):
                progress = index / max(1, frames - 1)
                frame = self._frame(zoom_canvas, start, end, progress, width, height, request, Image, ImageDraw)
                process.stdin.write(frame.tobytes())
            process.stdin.close()
            stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
            if process.wait() != 0:
                raise EngineError("mock encoder failed", hint=stderr[-600:], stage="video")
        finally:
            if process.poll() is None:
                process.kill()

        assert_artifact(out, min_bytes=4096, kind="mock clip")
        info = probe(out)
        return VideoResult(
            path=out,
            engine=self.name,
            model="ffmpeg-pillow-mock",
            duration=info.duration,
            cost_usd=0.0,
            meta={"frames": frames, "fps": fps, "interpolated_to_end": end is not None},
        )

    def _frame(self, canvas, start, end, progress, width, height, request, Image, ImageDraw):
        # Push-in: crop a shrinking window from the upscaled canvas.
        zoom = 1.0 - 0.07 * progress
        crop_w = int(canvas.width * zoom)
        crop_h = int(canvas.height * zoom)
        left = (canvas.width - crop_w) // 2
        top = int((canvas.height - crop_h) * (0.35 + 0.2 * progress))
        frame = canvas.crop((left, top, left + crop_w, top + crop_h)).resize((width, height), Image.BILINEAR)

        if end is not None:
            frame = Image.blend(frame, end, min(0.95, progress * 0.97))

        # Moving light sweep: guarantees temporal change even on a static start frame,
        # and keeps dHash boundaries non-degenerate.
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        band_x = int(-width * 0.3 + progress * width * 1.6)
        draw.polygon(
            [(band_x, 0), (band_x + width * 0.16, 0), (band_x + width * 0.05, height), (band_x - width * 0.11, height)],
            fill=(255, 255, 255, 16),
        )
        frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")

        # Debug label: top-left, clear of both the caption band and the keyframe tag.
        draw = ImageDraw.Draw(frame)
        draw.text((8, 8), f"{request.scene_id} {progress * 100:3.0f}%", fill=(210, 210, 210))
        return frame
