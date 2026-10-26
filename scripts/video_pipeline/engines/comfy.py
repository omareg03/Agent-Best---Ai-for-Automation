"""ComfyUI engine -- the free/open-weight path (Wan 2.2 FLF2V, TI2V-5B, FramePack).

Transport (stable ComfyUI HTTP API, unchanged for years):
  POST /upload/image            multipart, field name "image"
  POST /prompt                  {"prompt": <api-graph>, "client_id": <uuid>}
  GET  /history/{prompt_id}     -> outputs[node_id].gifs|videos|images[0]
  GET  /view?filename=&subfolder=&type=output
  GET  /object_info             -> used by validate_comfy.py to prove node classes exist

The API graph is a JSON template with __TOKENS__ (see workflows/comfyui/*.json).
Node class names are the one thing this repo cannot verify without a live ComfyUI,
so `health()` and scripts/validate_comfy.py diff the template against /object_info
before any money or GPU time is spent.
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from ..config import COMFYUI_URL, WORKFLOWS_DIR
from ..errors import EngineError
from ..ffmpeg_util import assert_artifact, probe, run_ffmpeg
from .base import VideoEngine, VideoRequest, VideoResult

TOKENS = (
    "__PROMPT__", "__NEGATIVE__", "__START_IMAGE__", "__END_IMAGE__",
    "__SEED__", "__FRAMES__", "__FPS__", "__WIDTH__", "__HEIGHT__",
    "__DURATION__", "__PREFIX__",
)


class ComfyClient:
    def __init__(self, base_url: str = COMFYUI_URL, *, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    # -- low level ---------------------------------------------------------
    def _request(self, path: str, *, data: bytes | None = None, headers: dict | None = None,
                 method: str = "GET") -> bytes:
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers or {}, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:600]
            raise EngineError(
                f"ComfyUI HTTP {exc.code} on {path}",
                hint=body,
                stage="video",
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EngineError(
                f"ComfyUI unreachable at {self.base_url}",
                hint=f"{exc}\nStart ComfyUI with --listen, or set COMFYUI_URL.",
                stage="video",
            ) from exc

    def object_info(self) -> dict:
        return json.loads(self._request("/object_info"))

    # -- files -------------------------------------------------------------
    def upload_image(self, path: Path) -> str:
        path = Path(path)
        boundary = f"----pipeline{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        body = bytearray()
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode()
        body += f"Content-Type: {mime}\r\n\r\n".encode()
        body += path.read_bytes()
        body += f"\r\n--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
        body += f"--{boundary}--\r\n".encode()
        raw = self._request(
            "/upload/image",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        payload = json.loads(raw)
        name = payload.get("name") or path.name
        subfolder = payload.get("subfolder") or ""
        return f"{subfolder}/{name}" if subfolder else name

    # -- execution ---------------------------------------------------------
    def queue(self, graph: dict) -> str:
        payload = json.dumps({"prompt": graph, "client_id": self.client_id}).encode()
        raw = self._request(
            "/prompt", data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        response = json.loads(raw)
        if "prompt_id" not in response:
            raise EngineError(
                "ComfyUI rejected the graph",
                hint=json.dumps(response.get("node_errors", response))[:800],
                stage="video",
            )
        return str(response["prompt_id"])

    def wait(self, prompt_id: str, *, poll: float = 2.0, timeout: float = 3600.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._request(f"/history/{prompt_id}")
            history = json.loads(raw)
            entry = history.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error" or status.get("completed") is False and status.get("status_str") == "error":
                    raise EngineError(
                        "ComfyUI execution error",
                        hint=json.dumps(status.get("messages", []))[:800],
                        stage="video",
                    )
                if entry.get("outputs"):
                    return entry
            time.sleep(poll)
        raise EngineError(
            f"ComfyUI did not finish {prompt_id} within {timeout:.0f}s",
            hint="check the ComfyUI console; large FLF2V renders on a T4 can exceed 10 min/clip",
            stage="video",
        )

    def download_output(self, entry: dict, out_path: Path) -> Path:
        for node_output in (entry.get("outputs") or {}).values():
            for key in ("gifs", "videos", "images", "video"):
                for item in node_output.get(key, []) or []:
                    filename = item.get("filename")
                    if not filename:
                        continue
                    query = urllib.parse.urlencode(
                        {
                            "filename": filename,
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output"),
                        }
                    )
                    data = self._request(f"/view?{query}")
                    if len(data) < 1024:
                        continue
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(data)
                    if out_path.suffix.lower() in (".webm", ".gif") or not out_path.suffix:
                        converted = out_path.with_suffix(".mp4")
                        run_ffmpeg(
                            ["-i", str(out_path), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(converted)]
                        )
                        out_path.unlink(missing_ok=True)
                        return assert_artifact(converted, kind="comfy clip")
                    return assert_artifact(out_path, kind="comfy clip")
        raise EngineError("ComfyUI finished but returned no video/images", stage="video")


class ComfyVideoEngine(VideoEngine):
    name = "comfy"
    supports_last_frame = True
    requires_gpu = True

    def __init__(self, graph_name: str = "wan22_flf2v", *, base_url: str = COMFYUI_URL,
                 output_timeout: float = 3600.0) -> None:
        self.graph_name = graph_name
        self.client = ComfyClient(base_url)
        self.output_timeout = output_timeout

    # -- graph templating --------------------------------------------------
    def _graph_path(self) -> Path:
        path = WORKFLOWS_DIR / "comfyui" / f"{self.graph_name}.json"
        if not path.exists():
            raise EngineError(
                f"ComfyUI graph template not found: {path}",
                hint="available: " + ", ".join(p.stem for p in (WORKFLOWS_DIR / 'comfyui').glob('*.json')),
            )
        return path

    def load_graph(self) -> str:
        return self._graph_path().read_text(encoding="utf-8")

    def build_graph(self, request: VideoRequest, *, start_name: str, end_name: str | None) -> dict:
        template = self.load_graph()
        frames = max(2, int(round(request.duration * request.fps)))
        replacements = {
            "__PROMPT__": json.dumps(request.prompt)[1:-1],
            "__NEGATIVE__": json.dumps(request.negative_prompt)[1:-1],
            "__START_IMAGE__": start_name,
            "__END_IMAGE__": end_name or start_name,
            "__SEED__": str(request.seed if request.seed is not None else 42),
            "__FRAMES__": str(frames),
            "__FPS__": str(request.fps),
            "__WIDTH__": str(request.width),
            "__HEIGHT__": str(request.height),
            "__DURATION__": f"{request.duration:.3f}",
            "__PREFIX__": f"{request.scene_id}_{uuid.uuid4().hex[:6]}",
        }
        rendered = template
        for token, value in replacements.items():
            rendered = rendered.replace(token, str(value))
        try:
            graph = json.loads(rendered)
        except json.JSONDecodeError as exc:
            raise EngineError(
                f"graph template {self.graph_name} is not valid JSON after token substitution",
                hint=f"{exc} (a token may have contained an unescaped quote)",
            ) from exc
        if "__" in rendered and any(token in rendered for token in TOKENS):
            leftover = [token for token in TOKENS if token in rendered]
            raise EngineError(f"unreplaced tokens in graph: {leftover}")
        return graph

    # -- engine API --------------------------------------------------------
    def generate(self, request: VideoRequest) -> VideoResult:
        if request.start_frame is None:
            raise EngineError("ComfyUI chaining requires a start frame")
        start_name = self.client.upload_image(Path(request.start_frame))
        end_name = self.client.upload_image(Path(request.end_frame)) if request.end_frame else None
        graph = self.build_graph(request, start_name=start_name, end_name=end_name)
        prompt_id = self.client.queue(graph)
        entry = self.client.wait(prompt_id, timeout=self.output_timeout)
        out = self.client.download_output(entry, Path(request.out_path))
        info = probe(out)
        return VideoResult(
            path=out,
            engine=self.name,
            model=self.graph_name,
            duration=info.duration,
            cost_usd=0.0,
            meta={"prompt_id": prompt_id, "graph": self.graph_name, "nodes": len(graph)},
        )

    def health(self) -> dict:
        try:
            info = self.client.object_info()
        except EngineError as exc:
            return {"engine": self.name, "ok": False, "error": str(exc)}
        template = json.loads(self.load_graph())
        missing = sorted(
            {
                node.get("class_type")
                for node in template.values()
                if isinstance(node, dict) and node.get("class_type") and node.get("class_type") not in info
            }
        )
        return {
            "engine": self.name,
            "ok": not missing,
            "graph": self.graph_name,
            "missing_node_classes": missing,
            "hint": "install the custom nodes / update the graph template" if missing else "",
            "node_count_available": len(info),
        }
