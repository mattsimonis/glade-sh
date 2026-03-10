# Session Log — Design

Replace the copilot-focused history tab with a general-purpose session log.
Every terminal session is recorded automatically via tmux `pipe-pane`.
Users can browse past sessions and view current scrollback from the history panel.

---

## Capture

tmux `pipe-pane` streams all raw terminal output to flat files.

**When:** On every tmux session spawn (project or main shell).

**How:**
```bash
tmux pipe-pane -o -t {session} 'cat >> ~/.roost/logs/{slug}/{timestamp}.log'
```

**Where:** `~/.roost/logs/{project-slug}/{YYYY-MM-DD_HH-MM-SS}.log`

- Main shell logs go to `~/.roost/logs/_main/`
- One file per session lifetime — tmux closes the pipe when the pane exits
- Raw output including ANSI escape sequences (preserves full fidelity)
- No daemon, no extra process — tmux handles it natively

---

## API Endpoints

### `GET /api/logs`

List all log files grouped by project, newest first.

```json
[
  {
    "project": "copilot-sync",
    "file": "2026-03-10_14-22-01.log",
    "size": 48210,
    "mtime": "2026-03-10T14:22:01Z",
    "active": true
  }
]
```

`active: true` when the tmux session is still running (file is being written to).

### `GET /api/logs/{project}/{file}`

Return raw log content. Response is `text/plain`.
Optional query param `?tail=N` returns only the last N lines.

### `GET /api/logs/current/{project}`

Tail the active session's latest log file (last 200 lines).
Returns `text/plain`. If no active session, returns 404.

### `GET /api/logs/search?q=term`

Runs `grep -ril` across `~/.roost/logs/`. Returns matching files with line excerpts:

```json
[
  {
    "project": "copilot-sync",
    "file": "2026-03-10_14-22-01.log",
    "matches": [
      { "line": 142, "text": "docker compose up -d" }
    ]
  }
]
```

ANSI codes stripped from search results and excerpts.

---

## UI — History Panel

The history tab (clock icon, third nav position) has two views stacked inside `#pv-history`.

### Session List (default)

Scrollable list of past sessions, newest first. Each card:

- **Project name** (or "Main Shell" for `_main`)
- **Time** — relative ("2h ago", "yesterday")
- **Duration** — from file timestamps ("14m", "2h 31m")
- **Preview** — first non-empty output line, ANSI-stripped, truncated
- **Active badge** — green dot if session is still running

Tap a card → switches to log viewer for that session.

### Log Viewer

- **Back button** (top-left) → returns to session list
- **Search bar** (top) — client-side filter, highlights matching lines
- **Scrollable text** — ANSI-stripped plain text in a monospaced `<div>`
- Same font as terminal (Berkeley Mono), rendered as static text
- Internal scroll within the 31vh panel height

### Current Session Shortcut

When a project is active and the user taps the history tab:
- Opens directly to that project's live log viewer
- Polls `GET /api/logs/current/{project}` every 3 seconds for live tail
- "Live" indicator (pulsing green dot) in the viewer header
- Back button still available to see the full session list

---

## ANSI Stripping

Done client-side with a regex before rendering. The API serves raw content.
This keeps the logs at full fidelity on disk while the UI shows readable text.

```javascript
function stripAnsi(str) {
    return str.replace(/\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b[()][0-9A-B]/g, '');
}
```

---

## Files Changed

### Server

| File | Change |
|---|---|
| `entrypoint.sh` | Create `~/.roost/logs/` on startup |
| `api/api.py` | Add `pipe-pane` call when spawning tmux sessions |
| `api/api.py` | New endpoints: `/api/logs`, `/api/logs/{project}/{file}`, `/api/logs/current/{project}`, `/api/logs/search` |

### Client

| File | Change |
|---|---|
| `web/index.html` | Replace `renderSessions()` with `renderHistory()` (session list) |
| `web/index.html` | New `renderLogViewer(project, file)` (scrollable text + search) |
| `web/index.html` | Current-session shortcut logic on history tab open |
| `web/index.html` | Update empty state text |
| `web/index.html` | `stripAnsi()` utility function |

### Removed / Deprecated

| Item | Action |
|---|---|
| `/api/sessions` endpoint | Remove from api.py |
| `copilot-history` CLI | Remove from README; bin/copilot-history can stay for now |
| `sessions` + `interactions` DB tables | Leave in schema, stop using. Drop in a future cleanup. |
| References to "copilot" in history UI | Replace with "session" language |

---

## What Stays the Same

- Nav bar layout, panel slider, keyboard tab, snippets tab
- SQLite for snippets and settings
- Panel height (31vh) and slide animation
- All existing API endpoints unrelated to history
