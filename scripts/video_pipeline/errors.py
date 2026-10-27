"""Typed errors so every failure carries its stage, evidence and a next action."""

from __future__ import annotations


class PipelineError(RuntimeError):
    """Base error for the render pipeline."""

    def __init__(self, message: str, *, stage: str = "unknown", hint: str = "") -> None:
        self.stage = stage
        self.hint = hint
        self.message = message
        super().__init__(self.render())

    def render(self) -> str:
        parts = [f"[{self.stage}] {self.message}"]
        if self.hint:
            parts.append(f"  hint: {self.hint}")
        return "\n".join(parts)


class ConfigError(PipelineError):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message, stage="config", hint=hint)


class MediaError(PipelineError):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message, stage="media", hint=hint)


class FFmpegError(MediaError):
    def __init__(self, message: str, *, command: list[str] | None = None, stderr: str = "") -> None:
        self.command = command or []
        self.stderr = stderr
        hint = ""
        if stderr:
            tail = "\n".join(stderr.strip().splitlines()[-12:])
            hint = "ffmpeg said:\n" + tail
        super().__init__(message, hint=hint)


class StoryboardError(PipelineError):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message, stage="storyboard", hint=hint)


class EngineError(PipelineError):
    def __init__(self, message: str, hint: str = "", stage: str = "engine") -> None:
        super().__init__(message, stage=stage, hint=hint)


class VerificationError(PipelineError):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message, stage="verify", hint=hint)
