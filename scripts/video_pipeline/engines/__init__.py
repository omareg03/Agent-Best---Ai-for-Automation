"""Engine registry. Names map to graphs/backends, never to hardcoded call sites."""

from __future__ import annotations

from ..config import COMFYUI_URL
from ..errors import EngineError
from .base import VideoEngine, VideoRequest, VideoResult

# Public name -> (family, comfy graph template or None)
ENGINES: dict[str, dict[str, str]] = {
    "mock": {"family": "mock", "graph": ""},
    "wan22_flf2v": {"family": "comfy", "graph": "wan22_flf2v"},
    "wan22_ti2v_5b": {"family": "comfy", "graph": "wan22_ti2v_5b"},
    "framepack_long_i2v": {"family": "comfy", "graph": "framepack_long_i2v"},
    "comfy": {"family": "comfy", "graph": "wan22_flf2v"},
    "gemini_omni": {"family": "gemini", "graph": ""},
    "gemini": {"family": "gemini", "graph": ""},
}


def get_video_engine(name: str, *, comfy_url: str = COMFYUI_URL, acknowledge_unverified: bool = False) -> VideoEngine:
    config = ENGINES.get(name)
    if config is None:
        raise EngineError(
            f"unknown video engine '{name}'",
            hint="available: " + ", ".join(sorted(ENGINES)),
        )
    family = config["family"]
    if family == "mock":
        from .mock import MockVideoEngine

        return MockVideoEngine()
    if family == "comfy":
        from .comfy import ComfyVideoEngine

        return ComfyVideoEngine(config["graph"], base_url=comfy_url)
    from .gemini_omni import GeminiOmniEngine

    return GeminiOmniEngine(acknowledge_unverified=acknowledge_unverified)


__all__ = ["ENGINES", "VideoEngine", "VideoRequest", "VideoResult", "get_video_engine"]
