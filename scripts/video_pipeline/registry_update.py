"""Living AI tool registry: refresh, staleness gate, Markdown render.

Design position: a script **cannot** verify pricing pages or licences. Pretending
otherwise is how teams ship on a model that was deprecated last month. So:

  * `tools.json` is the source of truth, and every entry carries `verified_at`,
    `confidence` and `source` (a URL a human/agent actually read).
  * This script automates the parts that CAN be checked mechanically every 24 h:
    repo liveness (stars, last push, archived) and licence cross-check vs GitHub.
  * `staleness()` fails CI when a primary/fallback tool has not been re-verified
    inside the policy window -- that is the enforcement mechanism for the 24-hour
    protocol, not a cron that silently rewrites facts.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import REGISTRY_DIR
from .errors import PipelineError

TOOLS_PATH = REGISTRY_DIR / "tools.json"
HISTORY_PATH = REGISTRY_DIR / "history.jsonl"
MARKDOWN_PATH = REGISTRY_DIR.parent / "AI_TOOL_REGISTRY.md"

CATEGORY_LABELS = {
    "image": "Image & Character Anchors",
    "video": "Video & Long-Video Generation",
    "audio": "Voice, TTS & Audio",
    "alignment": "Alignment & Captions",
    "orchestration": "Orchestration & Assembly",
}
STATUS_ICON = {
    "current": "✅ current",
    "deprecated": "⛔ deprecated",
    "legacy": "🕰️ legacy",
    "experimental": "🧪 experimental",
    "retired": "🚫 retired",
}
ROLE_LABEL = {
    "primary": "**primary**",
    "primary-tts": "**primary**",
    "primary-align": "**primary**",
    "primary-engine": "**primary**",
    "low-vram": "low-VRAM",
    "hosted-fallback": "hosted fallback",
    "fallback": "fallback",
    "fallback-align": "fallback",
    "alternative": "alternative",
    "premium": "premium",
    "brand-voice": "brand voice",
    "manual-previz": "manual previz only",
    "research": "research only",
    "long-take": "long-take",
    "visual-orchestration": "visual orchestration",
    "assembly": "assembly",
    "scheduler": "scheduler",
    "avoid": "**avoid**",
    "optional-tts": "optional",
    "none": "-",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_registry(path: Path = TOOLS_PATH) -> dict[str, Any]:
    if not path.exists():
        raise PipelineError(f"registry not found: {path}", stage="registry")
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(data: dict[str, Any], path: Path = TOOLS_PATH) -> Path:
    data["generated_at"] = utcnow().isoformat(timespec="seconds")
    interval = int(data.get("policy", {}).get("refresh_interval_hours", 24))
    data["next_refresh_due"] = (utcnow() + timedelta(hours=interval)).isoformat(timespec="seconds")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def get_tool(data: dict[str, Any], tool_id: str) -> dict[str, Any] | None:
    return next((t for t in data.get("tools", []) if t.get("id") == tool_id), None)


# ---------------------------------------------------------------------------
# GitHub liveness refresh (the only facts a script can check safely)
# ---------------------------------------------------------------------------
def _github_get(repo: str, token: str | None, timeout: int = 20) -> dict[str, Any] | None:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "agent-best-registry/1.0",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise PipelineError(
                "GitHub API rate limit hit",
                stage="registry",
                hint="set GITHUB_TOKEN (60 req/h unauthenticated vs 5000 authenticated)",
            ) from exc
        if exc.code == 404:
            return None
        raise PipelineError(f"GitHub API error {exc.code} for {repo}", stage="registry") from exc
    except urllib.error.URLError as exc:
        raise PipelineError(f"GitHub unreachable: {exc}", stage="registry") from exc


def _norm_license(value: str) -> str:
    cleaned = value.lower().replace("-", "").replace(" ", "").replace("_", "")
    return cleaned.split("(")[0]


def refresh_github(data: dict[str, Any], *, token: str | None = None, sleep: float = 0.15) -> dict[str, Any]:
    """Update stars / last push / archived; cross-check the curated licence."""
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    checked = 0
    updated = 0
    warnings: list[str] = []
    for tool in data.get("tools", []):
        repo = tool.get("repo") or ""
        if not repo or "/" not in repo:
            continue
        payload = _github_get(repo, token)
        checked += 1
        if payload is None:
            warnings.append(f"{tool['id']}: repo {repo} not found (moved/renamed/private?)")
            tool["repo_status"] = "missing"
            continue
        before = (tool.get("stars"), tool.get("last_push"), tool.get("archived"))
        tool["stars"] = payload.get("stargazers_count")
        tool["last_push"] = payload.get("pushed_at")
        tool["archived"] = bool(payload.get("archived"))
        spdx = ((payload.get("license") or {}).get("spdx_id")) or ""
        tool["github_license"] = spdx
        curated = _norm_license(str(tool.get("license_id", "")))
        if spdx and spdx != "NOASSERTION" and curated and _norm_license(spdx) not in curated:
            warnings.append(
                f"{tool['id']}: curated licence '{tool.get('license_id')}' does not contain GitHub's '{spdx}'"
            )
            tool["license_check"] = f"mismatch: curated={tool.get('license_id')} github={spdx}"
        else:
            tool["license_check"] = "match"
        tool["repo_status"] = "ok"
        tool["github_checked_at"] = utcnow().isoformat(timespec="seconds")
        if before != (tool.get("stars"), tool.get("last_push"), tool.get("archived")):
            updated += 1
        time.sleep(sleep)

    data.setdefault("refresh_log", []).append(
        {
            "at": utcnow().isoformat(timespec="seconds"),
            "source": "github",
            "checked": checked,
            "updated": updated,
            "warnings": warnings,
        }
    )
    return {"checked": checked, "updated": updated, "warnings": warnings}


# ---------------------------------------------------------------------------
# Staleness gate
# ---------------------------------------------------------------------------
def staleness(data: dict[str, Any], *, today: datetime | None = None) -> list[dict[str, Any]]:
    today = today or utcnow()
    policy = data.get("policy", {})
    warn_days = int(policy.get("warn_after_days", 7))
    fail_days = int(policy.get("fail_after_days", 30))
    out: list[dict[str, Any]] = []
    for tool in data.get("tools", []):
        if tool.get("role") in ("manual-previz",) or tool.get("status") == "retired":
            continue
        try:
            verified = datetime.fromisoformat(str(tool.get("verified_at"))).replace(tzinfo=timezone.utc)
        except ValueError:
            out.append({"id": tool["id"], "age_days": None, "level": "fail", "reason": "invalid verified_at"})
            continue
        age = (today - verified).days
        level = "ok"
        if age >= fail_days:
            level = "fail"
        elif age >= warn_days:
            level = "warn"
        out.append(
            {
                "id": tool["id"],
                "age_days": age,
                "level": level,
                "primary": tool.get("role", "").startswith("primary"),
                "reason": f"{age}d since last human/agent verification",
            }
        )
    return sorted(out, key=lambda item: (item["level"] != "fail", item["level"] != "warn", -(item["age_days"] or 0)))


def staleness_gate(data: dict[str, Any], *, strict: bool = True) -> tuple[bool, list[str]]:
    findings = staleness(data)
    problems = [
        f"{item['id']}: {item['reason']}" for item in findings if item["level"] == "fail"
    ]
    warnings = [f"{item['id']}: {item['reason']}" for item in findings if item["level"] == "warn"]
    ok = not problems if strict else True
    return ok, problems + warnings


# ---------------------------------------------------------------------------
# Markdown render
# ---------------------------------------------------------------------------
def _days_until(date_str: str, *, today: datetime | None = None) -> int | None:
    if not date_str:
        return None
    today = today or utcnow()
    try:
        target = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (target - today).days


def _fmt_stars(value: Any) -> str:
    if value is None:
        return "—"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def render_markdown(data: dict[str, Any], *, history: list[dict[str, Any]] | None = None) -> str:
    now = utcnow()
    tools = data.get("tools", [])
    policy = data.get("policy", {})
    lines: list[str] = []
    add = lines.append

    add("# AI Tool Registry — Long-Video & Media Automation")
    add("")
    add("> **Auto-generated. Do not hand-edit.** Source of truth: [`registry/tools.json`](registry/tools.json).")
    add("> Regenerate: `python -m scripts.video_pipeline.cli registry render`")
    add(f"> Last refresh: **{now.strftime('%Y-%m-%d %H:%M UTC')}** · next due: **{data.get('next_refresh_due','—')}**")
    add("")

    verified = sum(1 for t in tools if t.get("confidence") == "verified")
    current = sum(1 for t in tools if t.get("status") == "current")
    add("## Status")
    add("")
    add(f"- **{len(tools)}** tools tracked · **{verified}** human/agent-verified · **{current}** currently usable")
    add(f"- Policy: refresh every **{policy.get('refresh_interval_hours', 24)} h**; "
        f"warn after **{policy.get('warn_after_days', 7)} d**; CI fails after **{policy.get('fail_after_days', 30)} d** without re-verification.")
    add(f"- Rule: *{policy.get('rule', '')}*")
    add("")

    # -- corrections -----------------------------------------------------
    corrections = data.get("corrections", [])
    if corrections:
        add("## ⚠️ Corrections to widely-repeated advice")
        add("")
        add("These claims are common in 2025-era tutorials and are **wrong today**. The registry records the correction so the pipeline never encodes folklore.")
        add("")
        for item in corrections:
            add(f"<details><summary><strong>{item['claim']}</strong> → {item['reality'].split('.')[0]}.</summary>")
            add("")
            add(item["reality"])
            add("")
            add(f"Source: <{item['source']}>")
            add("")
            add("</details>")
            add("")

    # -- deprecation watch ------------------------------------------------
    watch = [t for t in tools if t.get("deprecation_date")]
    if watch:
        add("## ⏳ Deprecation watch")
        add("")
        add("| Tool | Model ID | Shutdown | Days left | Action |")
        add("|---|---|---|---|---|")
        for tool in watch:
            days = _days_until(str(tool["deprecation_date"]))
            remaining = "**passed**" if days is not None and days < 0 else (f"{days}" if days is not None else "—")
            action = "🚫 do not start new work" if days is not None and days <= 7 else "plan migration"
            add(f"| {tool['name']} | `{tool.get('model_id','')}` | {tool['deprecation_date']} | {remaining} | {action} |")
        add("")

    # -- category tables ---------------------------------------------------
    for category, label in CATEGORY_LABELS.items():
        rows = [t for t in tools if t.get("category") == category]
        if not rows:
            continue
        rows.sort(key=lambda t: (t.get("role") != "primary", t.get("role") != "primary-tts", t.get("name", "")))
        add(f"## {label}")
        add("")
        add("| Tool | Model / ID | Licence | Cost | Hardware | Status | Role |")
        add("|---|---|---|---|---|---|---|")
        for tool in rows:
            add(
                f"| [{tool['name']}]({tool.get('source','')}) "
                f"| `{tool.get('model_id','')}` "
                f"| {tool.get('license_id','')} "
                f"| {tool.get('cost','')} "
                f"| {tool.get('hardware','')} "
                f"| {STATUS_ICON.get(tool.get('status',''), tool.get('status',''))} "
                f"| {ROLE_LABEL.get(tool.get('role',''), tool.get('role',''))} |"
            )
        add("")
        add("<details><summary>Notes, free-tier reality and verification dates</summary>")
        add("")
        for tool in rows:
            add(f"**{tool['name']}** — free tier: {tool.get('free_tier','—')}. "
                f"Commercial use: {tool.get('commercial_use','—')}. "
                f"Verified {tool.get('verified_at','—')} ({tool.get('confidence','—')}).")
            if tool.get("notes"):
                add(f"> {tool['notes']}")
            add("")
        add("</details>")
        add("")

    # -- provenance --------------------------------------------------------
    add("## Provenance & liveness")
    add("")
    add("| Tool | Source | Confidence | Verified | GitHub stars | Last push | Repo | Licence check |")
    add("|---|---|---|---|---|---|---|---|")
    for tool in sorted(tools, key=lambda t: (t.get("category", ""), t.get("name", ""))):
        add(
            f"| {tool['name']} | <{tool.get('source','')}> | {tool.get('confidence','—')} "
            f"| {tool.get('verified_at','—')} | {_fmt_stars(tool.get('stars'))} "
            f"| {(tool.get('last_push') or '—')[:10]} | {tool.get('repo') or '—'} "
            f"| {tool.get('license_check','not checked')} |"
        )
    add("")

    if history:
        add("## Recent refresh history")
        add("")
        add("| When | Source | Tools | Checked | Updated | Warnings |")
        add("|---|---|---|---|---|---|")
        for record in history[-10:][::-1]:
            add(
                f"| {record.get('at','')} | {record.get('source','')} | {record.get('tools','')} "
                f"| {record.get('checked','')} | {record.get('updated','')} | {record.get('warnings','')} |"
            )
        add("")

    add("---")
    add("")
    add("### How to update this file")
    add("")
    add("1. Read the primary source (vendor pricing/licence page, model card, repo).")
    add("2. Edit the entry in `registry/tools.json`; set `verified_at` to today and `confidence` to `verified`.")
    add("3. `python -m scripts.video_pipeline.cli registry refresh --github` (liveness + licence cross-check).")
    add("4. `python -m scripts.video_pipeline.cli registry render` and commit with the source links in the message.")
    add("")
    add("CI runs the staleness gate daily; a stale primary tool fails the build rather than silently rotting.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
def append_history(record: dict[str, Any]) -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_history(limit: int = 30) -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def update(*, github: bool = True, token: str | None = None, render: bool = True,
           record: bool = True, source: str = "manual") -> dict[str, Any]:
    data = load_registry()
    result: dict[str, Any] = {"tools": len(data.get("tools", []))}
    if github:
        result["github"] = refresh_github(data, token=token)
    ok, problems = staleness_gate(data, strict=True)
    result["stale_ok"] = ok
    result["stale_problems"] = problems
    save_registry(data)
    if render:
        markdown = render_markdown(data, history=read_history())
        MARKDOWN_PATH.write_text(markdown, encoding="utf-8")
        result["markdown"] = str(MARKDOWN_PATH)
        result["bytes"] = MARKDOWN_PATH.stat().st_size
    if record:
        append_history(
            {
                "at": utcnow().isoformat(timespec="seconds"),
                "source": source,
                "tools": result["tools"],
                "checked": result.get("github", {}).get("checked", 0),
                "updated": result.get("github", {}).get("updated", 0),
                "warnings": len(result.get("github", {}).get("warnings", [])),
            }
        )
    return result


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(update(source="direct"), indent=2))
