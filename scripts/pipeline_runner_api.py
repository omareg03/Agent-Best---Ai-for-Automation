#!/usr/bin/env python3
"""Small authenticated HTTP bridge for a self-hosted n8n instance.

Only allowlisted project slugs and engines are accepted. Commands are passed as
argument arrays (never through a shell). Protect this service behind a private
Docker network/firewall or TLS reverse proxy; a bearer token is mandatory.
"""

from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
ENGINES = {"mock", "comfy", "wan22_flf2v", "wan22_ti2v_5b"}
PIPELINE_PROJECTS = {"example"}
ASSEMBLY_PROJECTS = {"koh-chang-ghost-ship", "flannan-coat"}
MAX_BODY_BYTES = 1_000_000
MAX_RESPONSE_CHARS = 12_000
JOB_LOCK = threading.Lock()  # avoid concurrent GPU jobs / registry writes from webhook retries


def build_command(project_slug: str, engine: str, *, resume: bool, dry_run: bool) -> list[str]:
    """Build a safe argv command for one preconfigured project/package."""
    if project_slug in PIPELINE_PROJECTS:
        if engine not in ENGINES:
            raise ValueError("engine is not allowlisted")
        command = [
            PYTHON,
            "-m",
            "scripts.video_pipeline.cli",
            "plan" if dry_run else ("resume" if resume else "run"),
            project_slug,
            "--engine",
            engine,
            "--json",
        ]
        if dry_run:
            return command
        return command
    if project_slug in ASSEMBLY_PROJECTS:
        package = ROOT / "video_packages" / project_slug
        if not (package / "storyboard.json").is_file():
            raise ValueError("allowlisted package storyboard is missing")
        command = [
            PYTHON,
            "scripts/long_video_chain.py",
            str(package),
            "--fps",
            "30",
            "--captions",
            "--db",
            str(ROOT / "registry/pipeline_state.db"),
        ]
        if resume:
            command.append("--resume")
        if dry_run:
            missing = []
            board = json.loads((package / "storyboard.json").read_text(encoding="utf-8"))
            for block in board["blocks"]:
                for key, default in (
                    ("audio", f"audio/{block['id']}.wav"),
                    ("clip", f"clips/{block['id']}.mp4"),
                ):
                    item = package / block.get(key, default)
                    if not item.is_file() or item.stat().st_size == 0:
                        missing.append(str(item.relative_to(ROOT)))
            return ["DRY_RUN", *missing]
        return command
    raise ValueError("project_slug is not allowlisted")


def execute(command: list[str], *, timeout: int = 4 * 60 * 60) -> dict[str, Any]:
    if command and command[0] == "DRY_RUN":
        return {"ok": len(command) == 1, "dry_run": True, "missing_assets": command[1:]}
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-MAX_RESPONSE_CHARS:],
        "stderr_tail": (proc.stderr or "")[-MAX_RESPONSE_CHARS:],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "PipelineRunner/1.0"

    def _reply(self, code: int, payload: dict[str, Any]) -> None:
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        expected = os.environ.get("PIPELINE_RUNNER_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        return len(expected) >= 32 and hmac.compare_digest(supplied, f"Bearer {expected}")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._reply(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > MAX_BODY_BYTES:
                self._reply(413, {"ok": False, "error": "request body missing or exceeds 1 MB"})
                return
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(body, dict):
                self._reply(400, {"ok": False, "error": "JSON object required"})
                return
            if self.path == "/v1/registry/refresh":
                with JOB_LOCK:
                    result = execute(
                        [PYTHON, "-m", "scripts.video_pipeline.cli", "registry", "refresh", "--source", "n8n"]
                    )
                self._reply(200 if result["ok"] else 500, result)
                return
            if self.path != "/v1/render":
                self._reply(404, {"ok": False, "error": "unknown endpoint"})
                return
            slug = str(body.get("project_slug", ""))
            engine = str(body.get("engine", "mock"))
            resume = body.get("resume") is not False
            dry_run = body.get("dry_run") is True
            command = build_command(slug, engine, resume=resume, dry_run=dry_run)
            with JOB_LOCK:
                result = execute(command)
            result.update({"project_slug": slug, "request_id": str(body.get("request_id", ""))[:96]})
            self._reply(200 if result["ok"] else 500, result)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._reply(400, {"ok": False, "error": str(exc)})
        except subprocess.TimeoutExpired:
            self._reply(
                504,
                {
                    "ok": False,
                    "error": "pipeline job exceeded the four-hour server timeout; inspect SQLite state before retrying",
                },
            )
        except Exception as exc:  # return no stack traces or secrets to callers
            self._reply(500, {"ok": False, "error": f"runner failure: {type(exc).__name__}"})

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep operational logs, but never echo request headers (especially bearer tokens).
        sys.stderr.write(f"pipeline-runner {self.client_address[0]} {fmt % args}\n")


def main() -> int:
    token = os.environ.get("PIPELINE_RUNNER_TOKEN", "")
    if len(token) < 32:
        print("Set PIPELINE_RUNNER_TOKEN to a random secret of at least 32 characters.", file=sys.stderr)
        return 2
    host = os.environ.get("PIPELINE_RUNNER_HOST", "0.0.0.0")
    port = int(os.environ.get("PIPELINE_RUNNER_PORT", "8095"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Pipeline runner listening on {host}:{port}; keep it on a private network.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
