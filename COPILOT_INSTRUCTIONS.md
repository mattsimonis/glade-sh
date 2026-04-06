# Glade — AI Assistant Guide

Instructions for GitHub Copilot, Claude, and other AI systems working on this codebase.

---

## Quick Context

**Glade** is a self-hosted browser terminal. An always-on host runs Docker; any device connects via `https://glade.home`. The frontend is a single-file PWA (`web/index.html`, ~8500 lines). The backend is a stdlib Python API (`api/api.py`, ~1510 lines). Session logs are recorded via `tmux pipe-pane` to flat files.

GitHub integration is built in — `gh` CLI ships in the image, GitHub auth state persists via a named Docker volume (`gh-config`), Copilot CLI auth/sessions persist via `~/.glade/config/github-copilot/`, and Claude auth/sessions persist via `~/.glade/config/claude/`. Workspaces can be created directly from GitHub repos.

---

## Codebase Map

```
web/index.html              ← All UI: CSS + HTML + JS inline, no build step
api/api.py                  ← REST API: workspaces, snippets, logs, uploads, settings
entrypoint.sh               ← Container boot: mkdir, clone/pull repo, update poller, API supervisor loop
Dockerfile                  ← Debian bookworm-slim + ttyd + zsh + packages.sh hook
docker-compose.yml          ← Two services: glade-ttyd + glade-web
Makefile                    ← Daily ops: up, down, restart, build, logs, shell
services/Caddyfile          ← caddy-proxy config (glade.home routes)
services/web.Caddyfile      ← Inner Caddy for glade-web (file server + API proxy)
config/zshrc                ← Zsh config baked into the image (tracked in git; gitignore entry exists but file was committed first)
config/zshrc.example        ← Starter template (committed; plain prompt, tmux hooks, glade-wrap)
config/tmux.conf            ← Tmux config (Catppuccin Mocha status bar)
config/packages.sh          ← Build-time packages (gitignored, not in repo; authoritative copy lives at ~/.glade/config/packages.sh — rebuild-watcher seeds this path before every build; auto-copied from packages.sh.example by make setup/build only if the file is completely absent)
config/packages.sh.example  ← Recipe examples: gh CLI, Oh My Zsh, Node.js, pip, Rust (committed)
db/schema.sql               ← SQLite schema (workspaces, snippets, settings)
install.sh                  ← Host-side installer (copies files, initialises DB, copies *.example → actual)
```

### Runtime data (not in repo, lives at `~/.glade/` on host)

```
db/history.db             ← SQLite: workspaces, snippets, settings
logs/{slug}/              ← Session log files (flat, one per tmux session)
uploads/                  ← Pasted images
assets/fonts/             ← Custom font uploads (user-supplied via Settings)
config/github-copilot/    ← Copilot CLI auth + sessions (bind-mounted to /root/.config/github-copilot)
config/claude/            ← Claude CLI auth + sessions (bind-mounted to /root/.claude)
config/zsh_history        ← Persisted zsh history (HISTFILE); survives container rebuilds
config/packages.sh        ← Authoritative packages config (edit here, not in repo; rebuild-watcher copies it to ~/Dev/glade/config/packages.sh before every docker compose build)
scripts/rebuild-watcher.sh ← Host-side rebuild script (triggered by .rebuild-requested; seeds packages.sh, git-pulls, docker compose build+up)
```

---

## API Endpoints (api/api.py)

### Workspaces
- `GET /api/workspaces` — list all (with running status)
- `POST /api/workspaces` — create `{name, directory, color}`
- `GET /api/workspaces/:id` — get one
- `PUT /api/workspaces/:id` — update
- `DELETE /api/workspaces/:id` — delete + stop ttyd; accepts optional JSON body `{delete_dir: true}` to also remove the cloned directory from `~/.glade/projects/`
- `POST /api/workspaces/:id/start` — ensure tmux + ttyd running → `{port}`
- `POST /api/workspaces/:id/stop` — kill ttyd (keep tmux)
- `GET /api/workspaces/:id/shells` — list tmux windows
- `POST /api/workspaces/:id/shells` — new window → `{index}`
- `PUT /api/workspaces/:id/shells/:n/select` — switch active window *(no-op: tab switching is now client-side)*
- `DELETE /api/workspaces/:id/shells/:n` — kill window
- `GET /api/workspaces/activity` — activity status for badge polling
- `PUT /api/workspaces/:id/viewed` — clear activity badge

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
- `GET /api/logs/:workspace/:file` — raw log content (`?tail=N`)
- `GET /api/logs/current/:workspace` — tail active session (last 200 lines)
- `GET /api/logs/search?q=term` — grep across all logs

### Uploads
- `POST /api/upload-image` — upload any file (base64, any MIME type) → `{path, url, filename, mime}`
- `GET /api/uploads` — list recent (last 10, includes `mime` field)
- `GET /api/uploads/:filename` — serve file

### Shell State
- `GET /api/workspaces/:id/shell-idle` — `{idle: bool, command: str}` — checks `pane_current_command` in tmux; idle when shell is at prompt (bash/zsh/sh/fish)

### GitHub Auth
- `GET /api/github/auth/status` — `{connected, username, avatar_url}` (runs `gh auth status`)
- `POST /api/github/auth/start` — begin device flow → `{user_code, verification_uri}`; parses `gh auth login -w` stdout for the one-time code
- `DELETE /api/github/auth` — disconnect (deletes `~/.config/gh/hosts.yml` directly)

### GitHub Repos
- `GET /api/github/repos?q=` — list/search user repos → `[{nameWithOwner, name, description, isPrivate}]`

### Other
- `GET /api/health` — `{"ok": true, "update_pending": false, "image_update_pending": false, "build_date": "YYYYMMDDHHmmss"}`
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

1. `ensure_workspace_running()` calls `create_tmux_session(sname, dir, slug)`
2. `create_tmux_session()` calls `start_pipe_pane(sname, slug)`
3. `start_pipe_pane()` runs: `tmux pipe-pane -o -t {session} 'cat >> ~/.glade/logs/{slug}/{ts}.log'`
4. Recording stops when the tmux pane exits

---

## Key Functions (api/api.py)

| Function | Purpose |
|---|---|
| `open_db()` | Returns SQLite connection (creates tables if needed) |
| `ensure_tables()` | Creates workspaces/snippets/settings/interactions tables |
| `strip_ansi(text)` | Remove ANSI escape codes from terminal output |
| `slugify(name)` | "My Workspace" → "my-workspace" (for log directory names) |
| `session_name(workspace_id)` | `"ws-" + workspace_id[:8]` (tmux session name) |
| `create_tmux_session()` | Create tmux session + start pipe-pane recording |
| `start_pipe_pane()` | Start `tmux pipe-pane` for a session |
| `ensure_workspace_running()` | Create tmux + spawn ttyd on a free port |
| `stop_workspace_proc()` | Kill ttyd process for a workspace |
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
| `openLogViewer(workspace, file, name, active)` | Open log viewer with search + live tail |
| `stripAnsi(str)` | Client-side ANSI code removal |
| `sendString(str)` | Inject text into ttyd terminal via WebSocket |
| `attachHandlers()` | Set up custom keyboard with key-repeat logic |
| `renderShortcutBar()` | Arrow keys + Enter buttons above keyboard |
| `startWorkspace(id)` / `stopWorkspace(id)` | Workspace lifecycle from UI |
| `loadShellUrl(url)` | Clear iframe `onbeforeunload`, then navigate to url |
| `attachSwipeToDismiss(handleEl, sheetEl, closeFn, backdropEl)` | Wire swipe-down-to-dismiss on a bottom sheet |
| `startGhAuth(pendingSwitch)` | Begin GitHub device flow; shows modal with one-time code |
| `pollGhAuthStatus()` | Polls `/api/github/auth/status` every 3 s until connected |
| `renderGhConnected(status)` | Update Settings GitHub section (avatar, username, or "Not connected") |
| `setWorkspaceSource(src)` | Toggle Local ↔ GitHub in workspace creation sheet; shows 🔒 on button when not connected |
| `searchGhRepos(q)` | Debounced repo search; renders autocomplete dropdown |
| `refreshGithubSettingsState()` | Fetches auth status; updates Settings UI and GitHub Repo button icon |
| `applyTermTheme(name, syncApp)` | Apply a named Catppuccin/Solarized/One Dark theme; clears any active Base16 scheme when `syncApp` is true (user-initiated); persisted in localStorage |
| `applyBase16Scheme(slug, syncApp)` | Apply a Base16 community scheme by slug; sets all 19 CSS vars on `:root` inline, applies xterm.js terminal colors, persists full theme dict to API; deselects Catppuccin swatches |
| `clearBase16Theme()` | Remove inline CSS var overrides from `:root` so Catppuccin class-driven theming resumes; clears `localStorage('base16Theme')` |
| `renderB16List(query)` | Render the Base16 scheme picker list (color dots, name, variant badge, active highlight); used in Settings; has `._markActive(slug)` sub-function |
| `confirmDeleteWorkspace(p)` | Show two-step delete confirmation: "Delete workspace + directory" vs "Delete workspace only"; second prompt added after long-press/right-click context menu |
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
docker exec glade-ttyd curl -s http://localhost:7683/api/health

# API endpoints (port 7683 is not exposed to host — use docker exec or glade.home)
docker exec glade-ttyd curl -s http://localhost:7683/api/workspaces
curl -s https://glade.home/api/logs | python3 -m json.tool
curl -s https://glade.home/api/logs/search?q=docker

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

3. **Workspace slug → log directory** — Workspace "My App" becomes `my-app/` in `~/.glade/logs/`. The `slugify()` function handles this.

4. **Port pool is finite** — 40 per-window ports (7690–7729). `get_free_port()` finds the first unused one. Each tmux window gets its own ttyd process on its own port.

5. **Caddy-proxy is external** — It's a standalone container on the `shared_web` network. Its config lives in `services/Caddyfile` but must be copied into the actual caddy-proxy container's config.

6. **No build step for the frontend** — `web/index.html` is pure HTML/CSS/JS. No npm, no webpack, no transpilation.

7. **Legacy tables in schema** — `sessions` and `interactions` tables exist in `db/schema.sql` but are not used by current code. They're from the old copilot-logging era. Session logs now use flat files.

8. **The `bin/` and `lib/` directories are legacy** — `copilot-wrap`, `copilot-history`, and `logger.sh` are from the old architecture. The current system uses `tmux pipe-pane` + the web UI log viewer.

9. **iOS viewport math** — The PWA panel height is `31vh`, tuned for iOS Safari's viewport with keyboard open. Changing this requires testing on an actual iPhone.

10. **Two Caddyfiles** — `services/Caddyfile` is for the standalone caddy-proxy (routes glade.home traffic). `services/web.Caddyfile` is for the glade-web container (serves files, proxies API).

11. **`config/zshrc` is tracked in git; `config/packages.sh` is not — and its authoritative copy lives at `~/.glade/config/packages.sh`** — `config/zshrc` was committed early and stays tracked despite the `.gitignore` entry; it ships with the repo and the Dockerfile COPYs it. `config/packages.sh` is gitignored and absent from a fresh clone. The *authoritative* copy lives at `~/.glade/config/packages.sh` on the host — the rebuild-watcher (`~/.glade/scripts/rebuild-watcher.sh`) seeds `~/Dev/glade/config/packages.sh` from it before every `docker compose build`. `make setup` and `make build` only auto-copy from `packages.sh.example` if the file is *completely absent* — they will not restore a clobbered file. When editing packages, edit `~/.glade/config/packages.sh`; the next rebuild picks it up automatically.

12. **Personal directory mounts belong in `docker-compose.override.yml`** — This file is gitignored. Do not add volume mounts for personal directories (e.g. `~/Dev`) to `docker-compose.yml`.

13. **GitHub auth is isolated to a named Docker volume** — `gh-config` volume mounts to `/root/.config/gh` inside the container. Completely separate from the host's `~/.config/gh`. `_gh_auth_disconnect()` deletes `~/.config/gh/hosts.yml` directly — NOT `gh auth logout`, which is interactive when multiple accounts exist and hangs the request.

14. **GitHub workspaces clone to `~/.glade/projects/{slug}`** — Not `~/projects` or the bind-mounted dev dir. The `~/.glade/` volume is already mounted, so these repos persist across restarts without any extra config.

15. **`gh auth login -w` outputs to stderr** — The device flow one-time code and URL come from stderr (or mixed stdout/stderr). The `_gh_auth_start()` method reads both streams with a 20 s deadline. If the code line doesn't appear, it falls back to the default verification URL (`https://github.com/login/device`).

16. **`make build` stamps the build date** — `BUILD_DATE=$(shell date +%Y%m%d%H%M%S)` is passed as a Docker `--build-arg` and baked into `GLADE_BUILD_DATE` env var in the image. The `/api/health` response includes `build_date`. Since the app auto-updates via git pull (not rebuild), this only changes when `make build` is run explicitly.

17. **`navigator.vibrate` is Android-only** — iOS 18+ haptic is now supported via the WebKit `<input type="checkbox" switch>` trick. `haptic()` detects iOS via userAgent (`/iPhone|iPad|iPod/i`) and calls `label.click()` on a hidden switch input injected into the body on page load. `navigator.vibrate` is still used on Android. Older browsers/iOS: silent no-op.

18. **`input[type=checkbox][switch]` haptic trick** — `_hapticIsIOS` detects iOS via userAgent. A hidden `input[switch]` + `label` pair is injected into the body on page load. `label.click()` triggers iOS 18+ WebKit haptic even with `display:none`. This is the same technique used in production PWAs.

19. **Terminal iframe keyboard forwarding** — when the terminal iframe has focus, keydown fires on `iframe.contentWindow`, not the parent. A capture-phase listener on `iframe.contentWindow` forwards Meta / Ctrl+` / Escape combos to the parent via synthetic `KeyboardEvent`. Does not call `preventDefault`, so the terminal still receives keys normally.

20. **Terminal themes: named + Base16** — `applyTermTheme(name)` stores a named string in `localStorage('termTheme')`; six built-in named themes: Catppuccin Mocha (default), Frappé, Macchiato, Latte, Solarized Dark, One Dark. `applyBase16Scheme(slug)` stores the full xterm.js theme dict in `localStorage('base16Theme')` and a string slug in `currentB16Scheme`. On reconnect, `setConnectionState('connected')` prefers `base16Theme` over `termTheme`. The two pickers are mutually exclusive: picking a named theme calls `clearBase16Theme()`; picking a Base16 scheme deselects named swatches.

21. **Paste guard on multiline input** — pasting text with newlines shows a confirm dialog with line count before sending. Smart paste also detects secrets (PAT, OpenAI key, AWS AKIA, JWT, PEM, Slack token) and offers bracketed paste (concealed mode) via `looksLikeSecret()`.

22. **Shell-idle polling uses `pane_current_command`** — `GET /api/workspaces/:id/shell-idle` queries tmux `#{pane_current_command}`. Returns `{idle: true}` when the command is one of the known shell names (bash, zsh, sh, fish, -bash, -zsh). Used by the "Notify when done" feature.

23. **`config/zshrc` COPY must come _after_ the `packages.sh` RUN step in the Dockerfile** — `packages.sh` installs Oh My Zsh, which unconditionally writes a fresh default `.zshrc` (via `install.sh --unattended`). A `COPY config/zshrc` placed _before_ the `RUN packages.sh` step gets silently overwritten every build. The COPY must be the last config step. This bit us once — don't reorder it.

24. **`~/.glade/config/zshrc.local` is the right place for shell customisation** — sourced at the end of the container's `.zshrc` (on the host volume, so no rebuild needed). Use it for `PROMPT`, `RPROMPT`, `alias`, extra `source` lines. Changes take effect in the next new shell. `config/zshrc` sets `ZSH_THEME=""` — no theme — so no `precmd` hook will silently override `PROMPT`. If you reinstate a theme, make sure it doesn't register a precmd that resets PROMPT after `zshrc.local` runs.

25. **New shell double-prompt is architectural, not a bug — and is hidden** — ttyd connects at 80×24 (default pty size). FitAddon detects the real viewport and sends a resize → SIGWINCH → tmux redraws → zsh redraws → stray prompt line. Fix: hide the terminal iframe at `opacity:0` on load (preserves layout so FitAddon measures correctly), send Ctrl+L via `terminalInstance.input('\x0c', true)` once xterm.js is ready, then fade in (`opacity:1` with a 150ms CSS transition). If retries are exhausted, reveal unconditionally. This is wired in the `iframe load` handler — do not simplify it away.

26. **iOS cross-frame `instanceof WebSocket` always fails — use `terminalInstance.input()`** — WebKit enforces strict realm separation: a WebSocket created inside an iframe has a different constructor than `window.WebSocket` in the parent frame. Duck-typing also fails because ttyd bundles its WebSocket in webpack module scope, never on `window`. The only reliable path to inject input from the parent frame is `terminalInstance.input(str, true)` (found via `findTerminal()`). This is the same path used by the iOS keyboard relay. Never go back to `findWebSockets()` for this purpose.

27. **Rebuild button: poll immediately, POST is fire-and-forget** — `POST /api/rebuild` writes the trigger file and returns 200. Start `setInterval(pollRebuildLog, 2000)` immediately when the button is clicked — do not wait for the POST to resolve. Add an `AbortController` with an 8s timeout to the POST so a stale connection (common on iOS Safari) can't leave the button stuck on "Triggered…". When the poll's `catch` fires with `wasBuilding=true`, the container is restarting after `docker compose up -d` — show "Restarting…" and re-queue the poll after 4s rather than stopping it.

28. **`_onThemeLoad` must resolve the active theme, not assume Catppuccin** — `_onThemeLoad` runs on every iframe `load` event. It applies the terminal theme to `options.theme` and injects the `glade-theme-bg` style tag (which prevents the xterm viewport from flashing the wrong background on first paint). It checks `currentB16Scheme` first and derives colors via `_b16term()`; falls back to `TERM_THEMES[currentTermTheme]`. Do not simplify this back to only checking `TERM_THEMES` — that was the exact bug that caused the stale background color on theme switch.

29. **Deleting a workspace does not auto-delete the cloned directory** — `DELETE /api/workspaces/:id` only removes the DB record and kills ttyd by default. Pass `{delete_dir: true}` in the JSON body to also `shutil.rmtree` the `directory` field from the DB. The API resolves `os.path.realpath()` on both `WORKSPACES_DIR` and the target path before deleting — it will refuse to delete anything outside `~/.glade/projects/`. If the directory is not removed, re-creating a GitHub workspace from the same repo will increment the clone path counter (`my-project-2`, `-3`, etc.).

30. **Smart GitHub repo input: two modes** — In the new-workspace sheet, the repo input field has two behaviors. Typing plain text debounces a `/api/github/repos?q=` search and shows a dropdown. Typing `owner/repo` or a GitHub URL (contains `/` or `github.com`) hides the dropdown and skips the search; on blur it auto-fills the workspace name from the repo slug. Do not revert to auto-open-on-focus — it caused noise on every tap.

31. **Per-window ttyd via linked tmux sessions** — Each tmux window gets its own dedicated ttyd process on its own port. The ttyd attaches to a *linked (grouped) session* named `{sname}-w{idx}` rather than the source session. Linked sessions share all windows but track the current window independently — switching tabs on one device never moves the other device's active window. `_ttyd_shell_key(sname, idx)` returns `"sname:idx"`. `_ensure_window_ttyd(sname, idx)` is the idempotent entry point. `switchShell()` in the client just loads the new port in the iframe — no API call. `PUT /api/.../shells/:n/select` is kept for backward compatibility but is a no-op.

32. **Keyboard shortcuts on desktop** — Ctrl+Tab / Ctrl+Shift+Tab cycle shell tabs within the current workspace. Cmd+1–9 switch to the Nth workspace. Arrow keys (Up/Down/Left/Right) and Enter without modifiers are intercepted at the iframe capture-phase and forwarded directly to the terminal WebSocket — bypassing xterm.js focus handling so interactive TUI tools (gh copilot suggest, Go prompts) receive them reliably.

33. **Terminal URL links on mobile** — `findUrlAtTerminalPos(outerX, outerY)` converts outer-page viewport coordinates to a terminal cell, reads the xterm buffer, and extracts a URL if one is present at that cell. The `gestureOverlay touchend` handler calls this on every tap; if a URL is found it shows `showUrlActionSheet(url)` (Open in Safari / Copy URL / Cancel action sheet) instead of forwarding the tap to the iframe. On desktop, xterm.js `WebLinksAddon` handles links natively via Ctrl+click. Never attempt to forward a synthesised click or postMessage into the iframe to trigger link handling — `WebLinksAddon` only fires on a real `ctrl+mousedown` inside the xterm canvas; the outer-page tap path cannot fake that modifier.

34. **Mobile text selection — `#sel-text-overlay` approach (iOS WKWebView limitation)** — iOS WKWebView silently ignores `user-select: text` inside `<iframe>` elements regardless of CSS; native text selection cannot be enabled in the terminal iframe. Workaround: a `position:fixed` transparent div (`#sel-text-overlay`) in the outer page is filled with terminal buffer content via `updateSelOverlay()` and positioned pixel-exact over the xterm canvas using `position:fixed` viewport coordinates (not `position:absolute` inside an `overflow:hidden` container — iOS selection handle hit-testing requires the element to be outside all clipping contexts). In sel mode (`body.sel-mode`), `#gesture-overlay` gets `pointer-events:none` so touches fall through to the overlay; iOS can then long-press → loupe → drag handles → native Copy menu. The overlay has `contenteditable="false"` which gives it WebKit's full native selection-handle treatment.

35. **Mobile selection: must override `touch-action` on the `html` element via JS, not CSS** — `html, body { touch-action: none }` is set globally so our JS gesture overlay owns all touch events. CSS `body.sel-mode { touch-action: auto }` is not sufficient — UIKit reads `touch-action` from the root `html` element for the entire viewport. The CSS body rule overrides only the `body` element; the `html` root still reports `none`, so UIKit's selection handle pan recognizer never fires. Fix: `enterSelMode()` directly sets `document.documentElement.style.touchAction = 'auto'` and `document.documentElement.style.webkitTouchCallout = 'default'`; `exitSelMode()` clears both back to `''` to restore the stylesheet value.

36. **Mobile selection: the global `document touchmove { passive:false }` listener must exempt the overlay** — A `document.addEventListener('touchmove', handler, { passive: false })` call prevents native scroll on most elements by calling `e.preventDefault()` for touches outside the designated scrollable areas. During selection handle dragging, the touch target is `#sel-text-overlay`; if `e.preventDefault()` fires on that touchmove, WKWebView cancels UIKit's selection pan gesture (handles freeze). Guard at the top of that handler: `if (document.body.classList.contains('sel-mode') && e.target.closest('#sel-text-overlay')) return;`.

37. **Selection mode button lives in the shortcut bar** — The I-beam select button is created inside `renderShortcutBar()`, which is called every time keyboard mode changes. It calls `window._toggleSelMode()`. Because `renderShortcutBar()` rebuilds the bar on every call, the button must restore its `.active` state by checking `document.body.classList.contains('sel-mode')` at creation time. `window._toggleSelMode`, `window._exitSelMode`, and `window._isSelModeActive` are set once by the sel-mode IIFE and persist across rebuilds.

38. **iOS PWA home screen icon requires full certificate trust** — Installing the mkcert root CA profile on iOS (Settings → General → VPN & Device Management) enables Safari browsing but does NOT allow SpringBoard (the iOS home screen process) to fetch icons over the local HTTPS cert. Add to Home Screen and bookmarks will show a letter-monogram placeholder instead of the icon. After installing the profile, go to **Settings → General → About → Certificate Trust Settings** and toggle full trust for the mkcert root CA. Then remove and re-add the shortcut. This is documented in `SETUP.md`.

39. **After a clean wipe, `install.sh` must be re-run — `make setup` alone is not enough** — `install.sh` creates `~/.glade/scripts/rebuild-watcher.sh` and `auto-update.sh`, then registers both as macOS launchd agents. `make setup` does not call `install.sh`. If `~/.glade/` is deleted (e.g. a clean e2e test wipe) but `~/Library/LaunchAgents/` is not, the plists survive but the scripts they reference are gone. The launchd agents will exit with code 127 on every trigger. Symptoms: rebuild button spins forever, `rebuild.log` stays empty, trigger file is never consumed, `launchctl list | grep glade` shows exit 127. Fix: re-run `bash install.sh` (or manually recreate the two scripts and `launchctl unload/load` the plists).

40. **Reconnect stuck on "Reconnecting…" after app backgrounding — root cause: `about:blank` race on iOS WKWebView** — The original `forceReconnect()` did `iframe.src = 'about:blank'` then in a `requestAnimationFrame` set the real URL. On iOS WKWebView, `about:blank` loads asynchronously — its `load` event fires *after* the rAF has already written the real URL to `iframe.src`. The load guard (`if (iframe.src === 'about:blank') return`) then fails (the attribute already shows the real URL), the handler fires on the blank page, and `setConnectionState('connected')` is called prematurely for empty content. The terminal never completes its own connection cycle. Fix: remove the `about:blank` intermediate entirely. Append `?_r=Date.now()` to the ttyd URL to force a fresh navigation even when the port hasn't changed. One navigation, one `load` event, no race. Secondary fixes in the same patch: (1) `_reconnectingStuckTimer` is reset on every `setConnectionState('reconnecting')` call, not just when the state changes; (2) `checkConnection()` gates `forceReconnect()` on `consecutiveFailures >= MAX_FAIL_DISCONNECTED` (12 s of sustained empty body) — not on any non-connected state — to avoid triggering full reloads during the ~50 ms blank-iframe window that occurs on every workspace switch.

41. **Brief `visibilitychange` events during a reconnect cause a "reconnecting → empty shell → reconnecting" loop** — iOS fires `visibilitychange` for hides as short as 50 ms (notification shade, app switcher, screen dim). The prior code unconditionally set `reconnectInProgress = false` then called `forceReconnect()` whenever `connectionState !== 'connected'`. Each brief hide/show during an active reconnect killed the in-flight attempt (reset `_forceReconnectId`) and started a fresh one, which loaded the iframe briefly (empty shell visible) before the next hide hit — loop. Fix: gate the `reconnectInProgress = false` reset and `termPollTimer` clear behind `wasHiddenMs > 1500`. iOS only freezes timers after ~1.5 s of background; brief hides do not freeze anything, so the in-flight attempt is still valid. Guard `forceReconnect()` with `!reconnectInProgress` so brief hides during a reconnect do not stack a second attempt on top.

42. **`addShell()` must not set `currentShellIdx` before calling `switchShell()`** — After posting to create a new tmux window, `addShell()` calls `refreshShells()`. Setting `currentShellIdx = result.index` before `switchShell()` runs causes `switchShell(idx)` to hit its early-return guard (`if (currentShellIdx === idx) return`), leaving the iframe on the old port. When the old window is then closed, the iframe shows `[exited]` instead of the new shell. Correct pattern: call `switchShell(result.index)` after `refreshShells()` — `switchShell` sets `currentShellIdx`, saves the choice, and navigates the iframe to the correct port.

43. **`config/packages.sh` persistence — authoritative copy lives at `~/.glade/config/packages.sh`** — `config/packages.sh` is gitignored. `git reset --hard` (run by rebuild-watcher before each build) does not touch it, but other paths can clobber the repo copy (clean clone, `make setup` on a missing file, accidental overwrite). The fix: store the user's custom packages at `~/.glade/config/packages.sh` alongside `zshrc.local`. The rebuild-watcher copies it to `~/Dev/glade/config/packages.sh` before every `docker compose build`. To reset to defaults: `cp ~/Dev/glade/config/packages.sh.example ~/.glade/config/packages.sh`, edit, and rebuild.

44. **Docker build network must be `host` on this setup — and use `git clone`, not `curl | sh`** — `raw.githubusercontent.com` (the CDN behind Oh My Zsh's `install.sh` curl-pipe) is unreachable from Docker's default bridge build network. Two fixes applied: (1) `network: host` under the build section in `docker-compose.yml` lets the build container use the host's network stack; (2) use `git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git` in `packages.sh` instead of `curl -fsSL .../install.sh | sh`. `github.com` is reachable even without host networking. Without `set -e` in `packages.sh`, a silent `curl` failure exits 0 and the build appears to succeed while Oh My Zsh is never installed — no error, no log entry, just a missing `/root/.oh-my-zsh/`.

45. **`set -g mouse on` is required for touch scroll** — Without tmux mouse mode, xterm.js converts scroll wheel events to ↑/↓ arrow key sequences in normal screen mode. Zsh interprets these as history navigation, not terminal scroll — touch scroll cycles through command history instead of scrolling the viewport. With `set -g mouse on` in `config/tmux.conf` (baked into the image), tmux intercepts scroll events and enters copy mode to scroll its scrollback buffer. To hot-patch a running container: `docker exec glade-ttyd bash -c "tmux set-option -g mouse on"`.
