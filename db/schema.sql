-- roost: SQLite schema for session and interaction history
-- Initialize with: sqlite3 history.db < schema.sql

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,    -- UUID
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    cwd TEXT,                           -- Working directory at session start
    device TEXT                         -- Tailscale hostname / device identifier
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    subcommand TEXT NOT NULL,           -- 'suggest', 'explain', 'git', etc.
    prompt TEXT,                        -- User's input/question
    response TEXT,                      -- Copilot's output
    cwd TEXT,                           -- Working directory at time of interaction
    exit_code INTEGER,
    duration_ms INTEGER,               -- How long the interaction took
    raw_log_path TEXT                   -- Path to full terminal capture if saved
);

CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_interactions_subcommand ON interactions(subcommand);
CREATE INDEX IF NOT EXISTS idx_interactions_prompt ON interactions(prompt);

-- Full-text search on prompts and responses
CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
    prompt,
    response,
    content='interactions',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS interactions_ai AFTER INSERT ON interactions BEGIN
    INSERT INTO interactions_fts(rowid, prompt, response)
    VALUES (new.id, new.prompt, new.response);
END;

CREATE TRIGGER IF NOT EXISTS interactions_ad AFTER DELETE ON interactions BEGIN
    INSERT INTO interactions_fts(interactions_fts, rowid, prompt, response)
    VALUES('delete', old.id, old.prompt, old.response);
END;

-- UI settings: keyboard layout + anything else the web UI needs to persist
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Snippets: named terminal commands, sent on tap
CREATE TABLE IF NOT EXISTS snippets (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    command    TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
