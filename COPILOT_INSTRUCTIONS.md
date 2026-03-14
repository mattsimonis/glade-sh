# Glade — AI Assistant Guide

Instructions for GitHub Copilot, Claude, and other AI systems working on this codebase.

---

## Quick Context

**Glade** is a self-hosted browser terminal. An always-on host runs Docker; any device connects via `https://glade.local`. The frontend is a single-file PWA (`web/index.html`, ~8200 lines). The backend is a stdlib Python API (`api/api.py`, ~1480 lines). Session logs are recorded via `tmux pipe-pane` to flat files.

GitHub integration is built in — `gh` CLI ships in the image, auth state persists via a named Docker volume (`gh-config`), and projects can be created directly from GitHub repos.

---

## Codebase Map

```
web/index.html              ← All UI: CSS + HTML + JS inline, no build step
api/api.py                  ← REST API: projects, snippets, logs, uploads, settings
entrypoint.sh               ← Container boot: mkdir, start API
Dockerfile                  ← Debian bookworm-slim + ttyd + zsh + packages.sh hook
docker-compose.yml          ← Two services: glade-ttyd + glade-web
Makefile                    ← Daily ops: up, down, restart, build, logs, shell
services/Caddyfile          ← caddy-proxy config (glade.local routes)
services/web.Caddyfile      ← Inner Caddy for glade-web (file server + API proxy)
config/zshrc                ← Personal Zsh config (gitignored; edit in place, no rebuild)
config/zshrc.example        ← Starter template (committed; plain prompt, tmux hooks, glade-wrap)
config/tmux.conf            ← Tmux config (Catppuccin Mocha status bar)
config/packages.sh          ← Personal build-time packages (gitignored)
config/packages.sh.example  ← Recipe examples: gh CLI, Oh My Zsh, Node.js, pip, Rust (committed)
db/schema.sql               ← SQLite schema (projects, snippets, settings)
install.sh                  ← Host-side installer (copies files, initialises DB, copies *.example → actual)
```

### Runtime data (not in repo, lives at `~/.glade/` on host)

```
db/history.db           ← SQLite: projects, snippets, settings
logs/{project-slug}/    ← Session log files (flat, one per tmux session)
uploads/                ← Pasted images
assets/fonts/           ← Custom font uploads (user-supplied via Settings)
```

---

## API Endpoints (api/api.py)

### Projects
- `GET /api/projects` — list all (with running status)
- `POST /api/projects` — create `{name, directory, color}`
- `GET /api/projects/:id` — get one
- `PUT /api/projects/:id` — update
- `DELETE /api/projects/:id` — delete + stop ttyd; accepts optional JSON body `{delete_dir: true}` to also remove the cloned directory from `~/.glade/projects/`
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
- `GET /api/settings/font` — `{family, url}` or `null`
- `PUT /api/settings/font` — save font config JSON
- `GET /api/settings/term-theme` — saved terminal theme (string name or full Base16 theme dict) or `null`
- `PUT /api/settings/term-theme` — save terminal theme; accepts a named string (`"mocha"`) or a full xterm.js theme object (used by Base16); stored as JSON and passed to ttyd's `-t theme=` arg at startup
- `POST /api/font` — upload font file → `{family, url}`
- `DELETE /api/font` — remove custom font + DB entry

> All settings `GET` endpoints return `200` with `null` body when no preference has been saved — not `404`. Callers guard with `if (cfg && cfg.url)` / `if (serverLayout)`. Do not regress this to 404.

### Session Logs
- `GET /api/logs` — list all log files (newest first)
- `GET /api/logs/:project/:file` — raw log content (`?tail=N`)
- `GET /api/logs/current/:project` — tail active session (last 200 lines)
- `GET /api/logs/search?q=term` — grep across all logs

### Uploads
- `POST /api/upload-image` — upload any file (base64, any MIME type) → `{path, url, filename, mime}`
- `GET /api/uploads` — list recent (last 10, includes `mime` field)
- `GET /api/uploads/:filename` — serve file

### Shell State
- `GET /api/projects/:id/shell-idle` — `{idle: bool, command: str}` — checks `pane_current_command` in tmux; idle when shell is at prompt (bash/zsh/sh/fish)

### GitHub Auth
- `GET /api/github/auth/status` — `{connected, username, avatar_url}` (runs `gh auth status`)
- `POST /api/github/auth/start` — begin device flow → `{user_code, verification_uri}`; parses `gh auth login -w` stdout for the one-time code
- `DELETE /api/github/auth` — disconnect (deletes `~/.config/gh/hosts.yml` directly)

### GitHub Repos
- `GET /api/github/repos?q=` — list/search user repos → `[{nameWithOwner, name, description, isPrivate}]`

### Other
- `GET /api/health` — `{"ok": true, "build_date": "YYYYMMDDHHmmss"}`
- `GET /api/export` — export all interactions as JSON
- `POST /api/rebuild` — write `~/.glade/.rebuild-requested` trigger file → `{ok}`; host launchd watcher picks it up and runs `docker compose build`
- `GET /api/rebuild/log` — `{log, running}` — rebuild output log + running state

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

- `web/index.html` changes: `git pull` on host, refresh browser
- `api/api.py` changes: `git pull && make restart`
- `Dockerfile`/`config/` changes: `git pull && make build`

### Session recording flow

1. `ensure_project_running()` calls `create_tmux_session(sname, dir, slug)`
2. `create_tmux_session()` calls `start_pipe_pane(sname, slug)`
3. `start_pipe_pane()` runs: `tmux pipe-pane -o -t {session} 'cat >> ~/.glade/logs/{slug}/{ts}.log'`
4. Recording stops when the tmux pane exits

---

## Key Functions (api/api.py)

| Function | Purpose |
|---|---|
| `open_db()` | Returns SQLite connection (creates tables if needed) |
| `ensure_tables()` | Creates projects/snippets/settings/interactions tables |
| `strip_ansi(text)` | Remove ANSI escape codes from terminal output |
| `slugify(name)` | "My Project" → "my-project" (for log directory names) |
| `session_name(project_id)` | `"proj-" + project_id[:8]` (tmux session name) |
| `create_tmux_session()` | Create tmux session + start pipe-pane recording |
| `start_pipe_pane()` | Start `tmux pipe-pane` for a session |
| `ensure_project_running()` | Create tmux + spawn ttyd on a free port |
| `stop_project_proc()` | Kill ttyd process for a project |
| `_gh_available(self)` | Returns bool — is `gh` on PATH? |
| `_gh_auth_status(self)` | Run `gh auth status` → `{connected, username, avatar_url}` |
| `_gh_auth_start(self)` | Shell out `gh auth login -w`, parse device code + URL from output |
| `_gh_auth_disconnect(self)` | Delete `~/.config/gh/hosts.yml` to clear auth state |
| `_gh_repos(self, q)` | Run `gh repo list --json` and filter by query |
| `qs(self)` | Parse query string from request path → dict |

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
| `loadShellUrl(url)` | Clear iframe `onbeforeunload`, then navigate to url |
| `attachSwipeToDismiss(handleEl, sheetEl, closeFn, backdropEl)` | Wire swipe-down-to-dismiss on a bottom sheet |
| `startGhAuth(pendingSwitch)` | Begin GitHub device flow; shows modal with one-time code |
| `pollGhAuthStatus()` | Polls `/api/github/auth/status` every 3 s until connected |
| `renderGhConnected(status)` | Update Settings GitHub section (avatar, username, or "Not connected") |
| `setProjectSource(src)` | Toggle Local ↔ GitHub in project creation sheet; shows 🔒 on button when not connected |
| `searchGhRepos(q)` | Debounced repo search; renders autocomplete dropdown |
| `refreshGithubSettingsState()` | Fetches auth status; updates Settings UI and GitHub Repo button icon |
| `applyTermTheme(name, syncApp)` | Apply a named Catppuccin/Solarized/One Dark theme; clears any active Base16 scheme when `syncApp` is true (user-initiated); persisted in localStorage |
| `applyBase16Scheme(slug, syncApp)` | Apply a Base16 community scheme by slug; sets all 19 CSS vars on `:root` inline, applies xterm.js terminal colors, persists full theme dict to API; deselects Catppuccin swatches |
| `clearBase16Theme()` | Remove inline CSS var overrides from `:root` so Catppuccin class-driven theming resumes; clears `localStorage('base16Theme')` |
| `renderB16List(query)` | Render the Base16 scheme picker list (color dots, name, variant badge, active highlight); used in Settings; has `._markActive(slug)` sub-function |
| `confirmDeleteProject(p)` | Show two-step delete confirmation: "Delete project + directory" vs "Delete project only"; second prompt added after long-press/right-click context menu |
| `openFind()` | Open floating find-in-scrollback bar (Cmd+F); scans xterm.js buffer via `getLine()` |
| `looksLikeSecret(str)` | Detect credentials (GitHub PAT, OpenAI key, AWS AKIA, JWT, Slack, PEM) in pasted text |
| `applyCustomFont(cfg)` | Inject `@font-face` style tag (`id="custom-font-face"`) and set `--font-mono` CSS var; `applyCustomFont(null)` removes it and falls back to Commit Mono |
| `loadCustomFont()` | Fetch `/api/settings/font` on startup; call `applyCustomFont()` with the result |
| `doFontUpload(file)` | Validate, POST to `/api/font`, apply the returned config |
| `haptic(pattern)` | Unified haptic: iOS 18+ fires `label.click()` on hidden `input[switch]`; Android uses `navigator.vibrate`; array patterns fire one click per "on" segment with timed delays |

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
docker logs glade-ttyd --tail 50
docker exec glade-ttyd curl http://localhost:7683/api/health

# API endpoints
curl http://localhost:7683/api/projects
curl http://localhost:7683/api/logs | python3 -m json.tool
curl http://localhost:7683/api/logs/search?q=docker

# Session logs on disk
ls -la ~/.glade/logs/
cat ~/.glade/logs/my-project/2026-03-10_03-43-00.log

# Live API requests
docker compose logs -f ttyd | grep "GET\|POST\|PUT\|DELETE"

# Shell into container
make shell
```

---

## Common Gotchas

1. **Volume mounts are bind mounts** — `api/api.py` and `web/` are mounted directly from the repo. Edit the repo, not container files.

2. **`make restart` vs `make build`** — `restart` picks up api.py changes (no rebuild). `build` is only for Dockerfile/config changes.

3. **Project slug → log directory** — Project "My App" becomes `my-app/` in `~/.glade/logs/`. The `slugify()` function handles this.

4. **Port pool is finite** — Only 10 project ports (7690–7699). `get_free_port()` finds the first unused one.

5. **Caddy-proxy is external** — It's a standalone container on the `shared_web` network. Its config lives in `services/Caddyfile` but must be copied into the actual caddy-proxy container's config.

6. **No build step for the frontend** — `web/index.html` is pure HTML/CSS/JS. No npm, no webpack, no transpilation.

7. **Legacy tables in schema** — `sessions` and `interactions` tables exist in `db/schema.sql` but are not used by current code. They're from the old copilot-logging era. Session logs now use flat files.

8. **The `bin/` and `lib/` directories are legacy** — `copilot-wrap`, `copilot-history`, and `logger.sh` are from the old architecture. The current system uses `tmux pipe-pane` + the web UI log viewer.

9. **iOS viewport math** — The PWA panel height is `31vh`, tuned for iOS Safari's viewport with keyboard open. Changing this requires testing on an actual iPhone.

10. **Two Caddyfiles** — `services/Caddyfile` is for the standalone caddy-proxy (routes glade.local traffic). `services/web.Caddyfile` is for the glade-web container (serves files, proxies API).

11. **`config/zshrc` and `config/packages.sh` are gitignored** — They are personal copies, never committed. `config/zshrc.example` and `config/packages.sh.example` are the committed templates. `install.sh` copies `*.example` → actual on first run if the actual doesn't exist.

12. **Personal directory mounts belong in `docker-compose.override.yml`** — This file is gitignored. Do not add volume mounts for personal directories (e.g. `~/Dev`) to `docker-compose.yml`.

13. **GitHub auth is isolated to a named Docker volume** — `gh-config` volume mounts to `/root/.config/gh` inside the container. Completely separate from the host's `~/.config/gh`. `_gh_auth_disconnect()` deletes `~/.config/gh/hosts.yml` directly — NOT `gh auth logout`, which is interactive when multiple accounts exist and hangs the request.

14. **GitHub projects clone to `~/.glade/projects/{slug}`** — Not `~/projects` or the bind-mounted dev dir. The `~/.glade/` volume is already mounted, so these repos persist across restarts without any extra config.

15. **`gh auth login -w` outputs to stderr** — The device flow one-time code and URL come from stderr (or mixed stdout/stderr). The `_gh_auth_start()` method reads both streams with a 20 s deadline. If the code line doesn't appear, it falls back to the default verification URL (`https://github.com/login/device`).

16. **`make build` stamps the build date** — `BUILD_DATE=$(shell date +%Y%m%d%H%M%S)` is passed as a Docker `--build-arg` and baked into `GLADE_BUILD_DATE` env var in the image. The `/api/health` response includes `build_date`. Since the app auto-updates via git pull (not rebuild), this only changes when `make build` is run explicitly.

17. **`navigator.vibrate` is Android-only** — iOS 18+ haptic is now supported via the WebKit `<input type="checkbox" switch>` trick. `haptic()` detects iOS via userAgent (`/iPhone|iPad|iPod/i`) and calls `label.click()` on a hidden switch input injected into the body on page load. `navigator.vibrate` is still used on Android. Older browsers/iOS: silent no-op.

18. **`input[type=checkbox][switch]` haptic trick** — `_hapticIsIOS` detects iOS via userAgent. A hidden `input[switch]` + `label` pair is injected into the body on page load. `label.click()` triggers iOS 18+ WebKit haptic even with `display:none`. This is the same technique used in production PWAs.

19. **Terminal iframe keyboard forwarding** — when the terminal iframe has focus, keydown fires on `iframe.contentWindow`, not the parent. A capture-phase listener on `iframe.contentWindow` forwards Meta / Ctrl+` / Escape combos to the parent via synthetic `KeyboardEvent`. Does not call `preventDefault`, so the terminal still receives keys normally.

20. **Terminal themes: named + Base16** — `applyTermTheme(name)` stores a named string in `localStorage('termTheme')`; six built-in named themes: Catppuccin Mocha (default), Frappé, Macchiato, Latte, Solarized Dark, One Dark. `applyBase16Scheme(slug)` stores the full xterm.js theme dict in `localStorage('base16Theme')` and a string slug in `currentB16Scheme`. On reconnect, `setConnectionState('connected')` prefers `base16Theme` over `termTheme`. The two pickers are mutually exclusive: picking a named theme calls `clearBase16Theme()`; picking a Base16 scheme deselects named swatches.

21. **Paste guard on multiline input** — pasting text with newlines shows a confirm dialog with line count before sending. Smart paste also detects secrets (PAT, OpenAI key, AWS AKIA, JWT, PEM, Slack token) and offers bracketed paste (concealed mode) via `looksLikeSecret()`.

22. **Shell-idle polling uses `pane_current_command`** — `GET /api/projects/:id/shell-idle` queries tmux `#{pane_current_command}`. Returns `{idle: true}` when the command is one of the known shell names (bash, zsh, sh, fish, -bash, -zsh). Used by the "Notify when done" feature.

23. **`config/zshrc` COPY must come _after_ the `packages.sh` RUN step in the Dockerfile** — `packages.sh` installs Oh My Zsh, which unconditionally writes a fresh default `.zshrc` (via `install.sh --unattended`). A `COPY config/zshrc` placed _before_ the `RUN packages.sh` step gets silently overwritten every build. The COPY must be the last config step. This bit us once — don't reorder it.

24. **`~/.glade/config/zshrc.local` is the right place for shell customisation** — sourced at the end of the container's `.zshrc` (on the host volume, so no rebuild needed). Use it for `PROMPT`, `RPROMPT`, `alias`, extra `source` lines. Changes take effect in the next new shell. `config/zshrc` sets `ZSH_THEME=""` — no theme — so no `precmd` hook will silently override `PROMPT`. If you reinstate a theme, make sure it doesn't register a precmd that resets PROMPT after `zshrc.local` runs.

25. **New shell double-prompt is architectural, not a bug — and is hidden** — ttyd connects at 80×24 (default pty size). FitAddon detects the real viewport and sends a resize → SIGWINCH → tmux redraws → zsh redraws → stray prompt line. Fix: hide the terminal iframe at `opacity:0` on load (preserves layout so FitAddon measures correctly), send Ctrl+L via `terminalInstance.input('\x0c', true)` once xterm.js is ready, then fade in (`opacity:1` with a 150ms CSS transition). If retries are exhausted, reveal unconditionally. This is wired in the `iframe load` handler — do not simplify it away.

26. **iOS cross-frame `instanceof WebSocket` always fails — use `terminalInstance.input()`** — WebKit enforces strict realm separation: a WebSocket created inside an iframe has a different constructor than `window.WebSocket` in the parent frame. Duck-typing also fails because ttyd bundles its WebSocket in webpack module scope, never on `window`. The only reliable path to inject input from the parent frame is `terminalInstance.input(str, true)` (found via `findTerminal()`). This is the same path used by the iOS keyboard relay. Never go back to `findWebSockets()` for this purpose.

27. **Rebuild button: poll immediately, POST is fire-and-forget** — `POST /api/rebuild` writes the trigger file and returns 200. Start `setInterval(pollRebuildLog, 2000)` immediately when the button is clicked — do not wait for the POST to resolve. Add an `AbortController` with an 8s timeout to the POST so a stale connection (common on iOS Safari) can't leave the button stuck on "Triggered…". When the poll's `catch` fires with `wasBuilding=true`, the container is restarting after `docker compose up -d` — show "Restarting…" and re-queue the poll after 4s rather than stopping it.

28. **`_onThemeLoad` must resolve the active theme, not assume Catppuccin** — `_onThemeLoad` runs on every iframe `load` event. It applies the terminal theme to `options.theme` and injects the `glade-theme-bg` style tag (which prevents the xterm viewport from flashing the wrong background on first paint). It checks `currentB16Scheme` first and derives colors via `_b16term()`; falls back to `TERM_THEMES[currentTermTheme]`. Do not simplify this back to only checking `TERM_THEMES` — that was the exact bug that caused the stale background color on theme switch.

29. **Deleting a project does not auto-delete the cloned directory** — `DELETE /api/projects/:id` only removes the DB record and kills ttyd by default. Pass `{delete_dir: true}` in the JSON body to also `shutil.rmtree` the `directory` field from the DB. The API resolves `os.path.realpath()` on both `PROJECTS_DIR` and the target path before deleting — it will refuse to delete anything outside `~/.glade/projects/`. If the directory is not removed, re-creating a GitHub project from the same repo will increment the clone path counter (`my-project-2`, `-3`, etc.).

30. **Smart GitHub repo input: two modes** — In the new-project sheet, the repo input field has two behaviors. Typing plain text debounces a `/api/github/repos?q=` search and shows a dropdown. Typing `owner/repo` or a GitHub URL (contains `/` or `github.com`) hides the dropdown and skips the search; on blur it auto-fills the project name from the repo slug. Do not revert to auto-open-on-focus — it caused noise on every tap.
