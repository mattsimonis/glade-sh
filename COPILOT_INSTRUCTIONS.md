# Roost — AI Assistant Guide

Instructions for GitHub Copilot, Claude, and other AI systems working on this codebase.

---

## Quick Context

**Roost** is a self-hosted browser terminal. One Mac Mini runs Docker; any device connects via `https://ai.home`. The frontend is a single-file PWA (`web/index.html`, ~4900 lines). The backend is a stdlib Python API (`api/api.py`, ~920 lines). Session logs are recorded via `tmux pipe-pane` to flat files.

Previously called "Copilot Sync" — now generalized. The repo directory is still `copilot-sync` but the project name is **Roost**.

---

## Codebase Map

```
web/index.html          ← All UI: CSS + HTML + JS inline, no build step
api/api.py              ← REST API: projects, snippets, logs, uploads, settings
entrypoint.sh           ← Container boot: mkdir, gh auth check, start API
Dockerfile              ← Debian bookworm-slim + ttyd + gh CLI + zsh
docker-compose.yml      ← Two services: roost-ttyd + roost-web
Makefile                ← Daily ops: up, down, restart, build, logs, shell
services/Caddyfile      ← caddy-proxy config (ai.home + casper.local routes)
services/web.Caddyfile  ← Inner Caddy for roost-web (file server + API proxy)
config/zshrc            ← Shell config baked into Docker image
config/tmux.conf        ← Tmux config (Catppuccin Mocha status bar)
db/schema.sql           ← SQLite schema (projects, snippets, settings)
install.sh              ← Host-side installer (optional, for non-Docker use)
```

### Runtime data (not in repo, lives at `~/.roost/` on host)

```
db/history.db           ← SQLite: projects, snippets, settings
logs/{project-slug}/    ← Session log files (flat, one per tmux session)
uploads/                ← Pasted images
assets/fonts/           ← Berkeley Mono Nerd Font (user-provided)
```

---

## API Endpoints (api/api.py)

### Projects
- `GET /api/projects` — list all (with running status)
- `POST /api/projects` — create `{name, directory, color}`
- `GET /api/projects/:id` — get one
- `PUT /api/projects/:id` — update
- `DELETE /api/projects/:id` — delete + stop ttyd
- `POST /api/projects/:id/start` — ensure tmux + ttyd running → `{port}`
- `POST /api/projects/:id/stop` — kill ttyd (keep tmux)
- `GET /api/projects/:id/shells` — list tmux windows
- `POST /api/projects/:id/shells` — new window → `{index}`
- `PUT /api/projects/:id/shells/:n/select` — switch active window
- `DELETE /api/projects/:id/shells/:n` — kill window
- `GET /api/projects/activity` — activity status for badge polling
- `PUT /api/projects/:id/viewed` — clear activity badge

### Snippets
- `GET /api/snippets` — list all
- `POST /api/snippets` — create `{name, command}`
- `PUT /api/snippets/:id` — update
- `DELETE /api/snippets/:id` — delete

### Settings
- `GET /api/settings/layout` — keyboard layout JSON
- `PUT /api/settings/layout` — save keyboard layout
- `GET /api/settings/compact-layout` — compact layout
- `PUT /api/settings/compact-layout` — save compact layout

### Session Logs
- `GET /api/logs` — list all log files (newest first)
- `GET /api/logs/:project/:file` — raw log content (`?tail=N`)
- `GET /api/logs/current/:project` — tail active session (last 200 lines)
- `GET /api/logs/search?q=term` — grep across all logs

### Uploads
- `POST /api/upload-image` — upload base64 image → `{path, url, filename}`
- `GET /api/uploads` — list recent (last 10)
- `GET /api/uploads/:filename` — serve file

### Other
- `GET /api/health` — `{"ok": true}`
- `GET /api/export` — export all interactions as JSON

---

## How Things Work

### Adding a new API endpoint

1. Write a `_method_name(self, ...)` method on the `Handler` class
2. Add routing in `do_GET()`, `do_POST()`, `do_PUT()`, or `do_DELETE()`
3. Return via `self.send_json(code, data)`
4. Update the docstring at the top of the file

### Updating the web UI

1. Edit `web/index.html` directly (everything is inline)
2. Refresh browser — changes are instant (bind-mounted from repo)
3. No build step, no transpilation, no bundler

### Deploy path

- `web/index.html` changes: `git pull` on Mac Mini, refresh browser
- `api/api.py` changes: `git pull && make restart`
- `Dockerfile`/`config/` changes: `git pull && make build`

### Session recording flow

1. `ensure_project_running()` calls `create_tmux_session(sname, dir, slug)`
2. `create_tmux_session()` calls `start_pipe_pane(sname, slug)`
3. `start_pipe_pane()` runs: `tmux pipe-pane -o -t {session} 'cat >> ~/.roost/logs/{slug}/{ts}.log'`
4. Recording stops when the tmux pane exits

---

## Key Functions (api/api.py)

| Function | Purpose |
|---|---|
| `open_db()` | Returns SQLite connection (creates tables if needed) |
| `ensure_tables()` | Creates projects/snippets/settings/interactions tables |
| `strip_ansi(text)` | Remove ANSI escape codes from terminal output |
| `slugify(name)` | "My Project" → "my-project" (for log directory names) |
| `session_name(project_id)` | "roost-{id}" (tmux session name) |
| `create_tmux_session()` | Create tmux session + start pipe-pane recording |
| `start_pipe_pane()` | Start `tmux pipe-pane` for a session |
| `ensure_project_running()` | Create tmux + spawn ttyd on a free port |
| `stop_project_proc()` | Kill ttyd process for a project |
| `get_free_port()` | Find available port in 7690–7699 range |

---

## Key Functions (web/index.html)

| Function | Purpose |
|---|---|
| `renderHistory()` | Fetch and display session log list |
| `openLogViewer(project, file, name, active)` | Open log viewer with search + live tail |
| `stripAnsi(str)` | Client-side ANSI code removal |
| `sendString(str)` | Inject text into ttyd terminal via WebSocket |
| `attachHandlers()` | Set up custom keyboard with key-repeat logic |
| `renderShortcutBar()` | Arrow keys + Enter buttons above keyboard |
| `startProject(id)` / `stopProject(id)` | Project lifecycle from UI |

---

## ANSI Stripping Regex

Both client and server use the same pattern:

```
\x1b\[[0-9;?]*[a-zA-Z]       ← CSI sequences (SGR, cursor, modes incl. ?2004h)
\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)  ← OSC sequences (BEL or ST terminated)
\x1b[()][0-9A-B]              ← Charset switching
\x1b[>=]                      ← Mode changes
[\x00-\x08\x0e-\x1f]         ← Low control characters (except \t, \n, \r)
```

This was refined twice to handle bracketed paste mode (`\x1b[?2004h`) and OSC sequences terminated by `\x1b\\` instead of just `\x07`.

---

## Debugging

```bash
# Container health
docker logs roost-ttyd --tail 50
docker exec roost-ttyd curl http://localhost:7683/api/health

# API endpoints
curl http://localhost:7683/api/projects
curl http://localhost:7683/api/logs | python3 -m json.tool
curl http://localhost:7683/api/logs/search?q=docker

# Session logs on disk
ls -la ~/.roost/logs/
cat ~/.roost/logs/my-project/2026-03-10_03-43-00.log

# Live API requests
docker compose logs -f ttyd | grep "GET\|POST\|PUT\|DELETE"

# Shell into container
make shell
```

---

## Common Gotchas

1. **Volume mounts are bind mounts** — `api/api.py` and `web/` are mounted directly from the repo. Edit the repo, not container files.

2. **`make restart` vs `make build`** — `restart` picks up api.py changes (no rebuild). `build` is only for Dockerfile/config changes.

3. **Project slug → log directory** — Project "My App" becomes `my-app/` in `~/.roost/logs/`. The `slugify()` function handles this.

4. **Port pool is finite** — Only 10 project ports (7690–7699). `get_free_port()` finds the first unused one.

5. **Caddy-proxy is external** — It's a standalone container on the `shared_web` network. Its config lives in `services/Caddyfile` but must be copied into the actual caddy-proxy container's config.

6. **No build step for the frontend** — `web/index.html` is pure HTML/CSS/JS. No npm, no webpack, no transpilation.

7. **Legacy tables in schema** — `sessions` and `interactions` tables exist in `db/schema.sql` but are not used by current code. They're from the old copilot-logging era. Session logs now use flat files.

8. **The `bin/` and `lib/` directories are legacy** — `copilot-wrap`, `copilot-history`, and `logger.sh` are from the old architecture. The current system uses `tmux pipe-pane` + the web UI log viewer.

9. **iOS viewport math** — The PWA panel height is `31vh`, tuned for iOS Safari's viewport with keyboard open. Changing this requires testing on an actual iPhone.

10. **Two Caddyfiles** — `services/Caddyfile` is for the standalone caddy-proxy (routes ai.home traffic). `services/web.Caddyfile` is for the roost-web container (serves files, proxies API).
