-- glade: SQLite schema
-- Initialize with: sqlite3 history.db < schema.sql

-- ── Active tables (used by current code) ────────────────────────────────────

-- Workspaces: terminal sessions managed via tmux + ttyd
CREATE TABLE IF NOT EXISTS workspaces (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    directory  TEXT DEFAULT '',
    color      TEXT DEFAULT '#89b4fa',
    sort_order INTEGER DEFAULT 0,
    last_active DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Snippets: named terminal commands, sent on tap
CREATE TABLE IF NOT EXISTS snippets (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    command    TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- UI settings: keyboard layout + anything else the web UI needs to persist
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── Legacy tables (from copilot-logging era, not used by current code) ──────
-- Session logs are now recorded via tmux pipe-pane to flat files in
-- ~/.glade/logs/{workspace-slug}/. These tables remain for backward compat
-- but no new data is written to them.

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    cwd TEXT,
    device TEXT
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    subcommand TEXT NOT NULL,
    prompt TEXT,
    response TEXT,
    cwd TEXT,
    exit_code INTEGER,
    duration_ms INTEGER,
    raw_log_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interactions_subcommand ON interactions(subcommand);
CREATE INDEX IF NOT EXISTS idx_interactions_prompt ON interactions(prompt);

CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
    prompt,
    response,
    content='interactions',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS interactions_ai AFTER INSERT ON interactions BEGIN
    INSERT INTO interactions_fts(rowid, prompt, response)
    VALUES (new.id, new.prompt, new.response);
END;

CREATE TRIGGER IF NOT EXISTS interactions_ad AFTER DELETE ON interactions BEGIN
    INSERT INTO interactions_fts(interactions_fts, rowid, prompt, response)
    VALUES('delete', old.id, old.prompt, old.response);
END;
