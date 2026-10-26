-- ---------------------------------------------------------------------------
-- Long-form render state (SQLite, WAL).
--
-- Design goal: a 15-minute video is 40-90 clips. If the box dies at clip 61,
-- `resume` must regenerate exactly one clip, not sixty-one.
--
-- Invariant: a scene is reusable only when status='done'
--            AND the artifact exists AND prompt_hash matches the storyboard.
-- ---------------------------------------------------------------------------

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT    NOT NULL UNIQUE,
    title           TEXT,
    storyboard_path TEXT,
    storyboard_hash TEXT,
    fps             INTEGER NOT NULL DEFAULT 24,
    width           INTEGER NOT NULL DEFAULT 1280,
    height          INTEGER NOT NULL DEFAULT 720,
    engine          TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id        INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_id          TEXT    NOT NULL,
    ordinal           INTEGER NOT NULL,
    prompt_hash       TEXT    NOT NULL,
    engine            TEXT,
    model             TEXT,
    seed              INTEGER,
    -- pending -> keyframes -> video -> audio -> done | failed | skipped
    status            TEXT    NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','keyframes','video','audio','done','failed','skipped')),
    keyframe_start    TEXT,
    keyframe_start_sha TEXT,
    keyframe_end      TEXT,
    keyframe_end_sha  TEXT,
    clip_path         TEXT,
    clip_sha          TEXT,
    clip_duration     REAL,
    narration_path    TEXT,
    narration_sha     TEXT,
    narration_duration REAL,
    cost_usd          REAL    NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    started_at        TEXT,
    finished_at       TEXT,
    updated_at        TEXT,
    UNIQUE (project_id, scene_id)
);

CREATE INDEX IF NOT EXISTS idx_scenes_project_status ON scenes(project_id, status);
CREATE INDEX IF NOT EXISTS idx_scenes_project_ordinal ON scenes(project_id, ordinal);

-- Append-only audit trail. Never updated, only inserted.
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    scene_id    TEXT,
    kind        TEXT NOT NULL,   -- plan|keyframe|video|tts|align|assemble|resume|verify|error|registry
    detail      TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS renders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,   -- body|final|subtitles|manifest
    path        TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    bytes       INTEGER NOT NULL,
    duration    REAL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_renders_project ON renders(project_id, kind);

-- Compact history of registry refreshes (also mirrored to registry/history.jsonl).
CREATE TABLE IF NOT EXISTS registry_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at         TEXT NOT NULL,
    source         TEXT NOT NULL,          -- cron|manual|ci
    tools_tracked  INTEGER,
    tools_updated  INTEGER,
    stale_tools    TEXT,                   -- comma separated names
    notes          TEXT
);
