"""SQLite state store: the reason a dead render resumes instead of restarting."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import SCHEMA_PATH
from .errors import PipelineError


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA_VERSION = 1

# Statuses, in pipeline order. Resume skips anything at/after 'done'.
STAGES = ("pending", "keyframes", "video", "audio", "done")


class StateStore:
    """Thin, explicit wrapper. One connection per instance, WAL for concurrent CI jobs."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 30000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._apply_schema()
        self._migrate()

    # -- lifecycle ---------------------------------------------------------
    def _apply_schema(self) -> None:
        if not SCHEMA_PATH.exists():
            raise PipelineError(
                f"schema not found: {SCHEMA_PATH}",
                stage="state",
                hint="the repository is incomplete; database/schema.sql is required",
            )
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.conn.commit()

    def _migrate(self) -> None:
        row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        current = row["v"] if row and row["v"] is not None else 0
        if current < SCHEMA_VERSION:
            self.conn.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utcnow()),
            )
            self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.commit()
        finally:
            self.conn.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- projects ----------------------------------------------------------
    def upsert_project(
        self,
        slug: str,
        *,
        title: str = "",
        storyboard_path: str = "",
        storyboard_hash: str = "",
        fps: int = 24,
        width: int = 1280,
        height: int = 720,
        engine: str = "",
    ) -> int:
        now = utcnow()
        row = self.conn.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()
        if row:
            self.conn.execute(
                """UPDATE projects SET title=?, storyboard_path=?, storyboard_hash=?,
                       fps=?, width=?, height=?, engine=?, updated_at=? WHERE id=?""",
                (title, storyboard_path, storyboard_hash, fps, width, height, engine, now, row["id"]),
            )
            self.conn.commit()
            return int(row["id"])
        cur = self.conn.execute(
            """INSERT INTO projects(slug, title, storyboard_path, storyboard_hash, fps, width,
                                    height, engine, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (slug, title, storyboard_path, storyboard_hash, fps, width, height, engine, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # -- scenes ------------------------------------------------------------
    def register_scenes(self, project_id: int, scenes: list[dict[str, Any]]) -> None:
        """Insert-or-refresh scene rows. A changed prompt_hash resets a finished scene.

        This is the invalidation rule: editing scene 12's prompt re-renders scene 12
        (and the caller decides about downstream), but never silently keeps stale footage.
        """
        now = utcnow()
        for scene in scenes:
            row = self.conn.execute(
                "SELECT id, prompt_hash, status FROM scenes WHERE project_id=? AND scene_id=?",
                (project_id, scene["scene_id"]),
            ).fetchone()
            if row is None:
                self.conn.execute(
                    """INSERT INTO scenes(project_id, scene_id, ordinal, prompt_hash, seed,
                                          status, updated_at)
                       VALUES (?,?,?,?,?, 'pending', ?)""",
                    (
                        project_id, scene["scene_id"], scene["ordinal"],
                        scene["prompt_hash"], scene.get("seed"), now,
                    ),
                )
            else:
                changed = row["prompt_hash"] != scene["prompt_hash"]
                self.conn.execute(
                    """UPDATE scenes SET ordinal=?, prompt_hash=?, seed=?, updated_at=?
                       WHERE id=?""",
                    (scene["ordinal"], scene["prompt_hash"], scene.get("seed"), now, row["id"]),
                )
                if changed and row["status"] == "done":
                    self.conn.execute(
                        """UPDATE scenes SET status='pending', clip_path=NULL, clip_sha=NULL,
                               keyframe_start=NULL, keyframe_end=NULL,
                               narration_path=NULL, narration_sha=NULL, finished_at=NULL
                           WHERE id=?""",
                        (row["id"],),
                    )
                    self.record_event(
                        project_id, scene["scene_id"], "invalidate",
                        "prompt changed -> scene queued for re-render",
                    )
        self.conn.commit()

    def scene(self, project_id: int, scene_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM scenes WHERE project_id=? AND scene_id=?", (project_id, scene_id)
        ).fetchone()

    def scenes(self, project_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM scenes WHERE project_id=? ORDER BY ordinal", (project_id,)
            ).fetchall()
        )

    def begin_scene(self, project_id: int, scene_id: str, *, engine: str, model: str) -> None:
        self.conn.execute(
            """UPDATE scenes SET status='keyframes', engine=?, model=?, attempts=attempts+1,
                   started_at=COALESCE(started_at, ?), updated_at=?, last_error=NULL
               WHERE project_id=? AND scene_id=?""",
            (engine, model, utcnow(), utcnow(), project_id, scene_id),
        )
        self.conn.commit()

    def set_status(self, project_id: int, scene_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE scenes SET status=?, updated_at=? WHERE project_id=? AND scene_id=?",
            (status, utcnow(), project_id, scene_id),
        )
        self.conn.commit()

    def update_scene(self, project_id: int, scene_id: str, **fields: Any) -> None:
        if not fields:
            return
        allowed = {
            "engine", "model", "seed", "keyframe_start", "keyframe_start_sha",
            "keyframe_end", "keyframe_end_sha", "clip_path", "clip_sha", "clip_duration",
            "narration_path", "narration_sha", "narration_duration", "cost_usd",
            "status", "last_error", "finished_at",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise PipelineError(f"unknown scene fields: {sorted(unknown)}", stage="state")
        fields["updated_at"] = utcnow()
        assignments = ", ".join(f"{key}=?" for key in fields)
        values = list(fields.values()) + [project_id, scene_id]
        self.conn.execute(
            f"UPDATE scenes SET {assignments} WHERE project_id=? AND scene_id=?",
            values,
        )
        self.conn.commit()

    def fail_scene(self, project_id: int, scene_id: str, error: str) -> None:
        self.conn.execute(
            """UPDATE scenes SET status='failed', last_error=?, updated_at=?
               WHERE project_id=? AND scene_id=?""",
            (error[:4000], utcnow(), project_id, scene_id),
        )
        self.conn.commit()

    def is_reusable(self, row: sqlite3.Row, *, prompt_hash: str, engine: str) -> tuple[bool, str]:
        """A done scene is only reusable if its artefacts still exist and still match."""
        if row["status"] != "done":
            return False, f"status={row['status']}"
        if row["prompt_hash"] != prompt_hash:
            return False, "prompt changed"
        if engine and row["engine"] and row["engine"] != engine:
            return False, f"engine changed ({row['engine']} -> {engine})"
        for column in ("clip_path", "narration_path"):
            value = row[column]
            if not value:
                return False, f"{column} missing"
            path = Path(value)
            if not path.exists() or path.stat().st_size == 0:
                return False, f"{column} file gone"
        return True, "ok"

    # -- audit -------------------------------------------------------------
    def record_event(self, project_id: int | None, scene_id: str | None, kind: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO events(project_id, scene_id, kind, detail, created_at) VALUES (?,?,?,?,?)",
            (project_id, scene_id, kind, detail[:4000], utcnow()),
        )
        self.conn.commit()

    def events(self, project_id: int, limit: int = 50) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        )

    def record_render(
        self, project_id: int, kind: str, path: str | Path, sha256: str, size: int, duration: float | None
    ) -> None:
        self.conn.execute(
            """INSERT INTO renders(project_id, kind, path, sha256, bytes, duration, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (project_id, kind, str(path), sha256, size, duration, utcnow()),
        )
        self.conn.commit()

    # -- reporting ---------------------------------------------------------
    def summary(self, project_id: int) -> dict[str, Any]:
        rows = self.scenes(project_id)
        by_status: dict[str, int] = {}
        seconds = 0.0
        cost = 0.0
        for row in rows:
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
            seconds += row["clip_duration"] or 0.0
            cost += row["cost_usd"] or 0.0
        return {
            "scenes": len(rows),
            "by_status": by_status,
            "rendered_seconds": round(seconds, 2),
            "cost_usd": round(cost, 4),
            "pending": [r["scene_id"] for r in rows if r["status"] != "done"],
        }

    def to_json(self, project_id: int) -> str:
        project = self.conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        payload = {
            "project": dict(project) if project else None,
            "scenes": [dict(r) for r in self.scenes(project_id)],
            "events": [dict(r) for r in self.events(project_id, limit=200)],
            "summary": self.summary(project_id),
        }
        return json.dumps(payload, indent=2)


@contextmanager
def open_state(db_path: str | Path) -> Iterator[StateStore]:
    store = StateStore(db_path)
    try:
        yield store
    finally:
        store.close()
