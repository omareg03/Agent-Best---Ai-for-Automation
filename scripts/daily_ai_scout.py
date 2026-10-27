#!/usr/bin/env python3
"""Collect daily release/version signals from official GitHub/PyPI metadata.

Signals are candidate leads, not a verification of quality, licensing, runtime,
price, account access or model performance. The JSON report is intended as a CI
artifact for human review and must not silently rewrite the curated registry.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

GITHUB_REPOS = {
    "Wan2.2": "Wan-Video/Wan2.2",
    "FramePack": "lllyasviel/FramePack",
    "HunyuanVideo": "Tencent-Hunyuan/HunyuanVideo",
    "Kokoro": "hexgrad/kokoro",
    "WhisperX": "m-bain/whisperX",
    "Manim": "ManimCommunity/manim",
    "n8n": "n8n-io/n8n",
}
PYPI_PACKAGES = ["whisperx", "kokoro", "edge-tts", "manim", "imageio-ffmpeg"]


def get_json(url: str, token: str = "") -> tuple[Any | None, str | None]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ai-video-registry-scout/1.0"}
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8")), None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)


def collect() -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "")
    repos, packages = {}, {}
    for label, repo in GITHUB_REPOS.items():
        url = f"https://api.github.com/repos/{repo}/releases?per_page=5"
        data, error = get_json(url, token)
        if error:
            repos[label] = {"repo": repo, "error": error, "status": "unavailable"}
            continue
        releases = []
        for item in data if isinstance(data, list) else []:
            releases.append(
                {
                    "tag": item.get("tag_name"),
                    "name": item.get("name"),
                    "published_at": item.get("published_at"),
                    "html_url": item.get("html_url"),
                    "prerelease": item.get("prerelease", False),
                    "draft": item.get("draft", False),
                }
            )
        repos[label] = {"repo": repo, "releases": releases, "status": "candidate_metadata_only"}
    for package in PYPI_PACKAGES:
        data, error = get_json(f"https://pypi.org/pypi/{package}/json")
        if error:
            packages[package] = {"error": error, "status": "unavailable"}
            continue
        info = data.get("info", {}) if isinstance(data, dict) else {}
        packages[package] = {
            "version": info.get("version"),
            "project_url": info.get("project_url"),
            "summary": info.get("summary"),
            "status": "candidate_metadata_only",
        }
    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "Official GitHub releases and PyPI metadata only. Not a pricing, rights, quality, account-access or runtime verification.",
        "github": repos,
        "pypi": packages,
        "review_required": True,
        "next_step": "Human/agent checks official vendor docs, release notes, licence/terms, working installs and actual API/GPU behavior before updating registry/tools.json.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("scout-report.json"))
    args = p.parse_args()
    report = collect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote candidate metadata report: {args.output}")
    errors = sum(v.get("status") == "unavailable" for v in report["github"].values()) + sum(
        v.get("status") == "unavailable" for v in report["pypi"].values()
    )
    return 0 if errors < len(GITHUB_REPOS) + len(PYPI_PACKAGES) else 2


if __name__ == "__main__":
    raise SystemExit(main())
