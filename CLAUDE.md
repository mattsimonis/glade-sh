# Glade — Architecture Reference

> Self-hosted, always-on terminal accessible from any device via browser.
> Runs on any always-on host with Docker. Catppuccin (4 flavors) + 304 Base16 themes. Commit Mono font (bundled).

For AI-specific guidance (endpoints, gotchas, common tasks), see `COPILOT_INSTRUCTIONS.md`.
For user setup, see `SETUP.md`. For the full API reference, see `README.md`.

---

## System Architecture

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Laptop     │   │   Phone      │   │  Other PC    │
│  (browser)   │   │ (Safari PWA) │   │  (browser)   │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       └──────────┬───────┴───────────────────┘
                  │  LAN / Tailscale
                  ▼
       ┌──────────────────────────────────────┐
       │       Server / Host (Docker)        │
       │                                      │
       │  caddy-proxy (standalone container)  │
       │    glade.home → :7682                   │
       │    /ttyd/{port} → :769x              │
       │                                      │
       │  glade-web (:7682, Caddy)            │
       │    /         → index.html            │
       │    /api/*    → glade-ttyd:7683       │
       │    /assets/* → fonts                 │
       │                                      │
       │  glade-ttyd (:7681, :7683, :7690–7729) │
       │    api.py    — REST API              │
       │    ttyd      — terminal WebSocket    │
       │    tmux      — session multiplexer   │
       │    pipe-pane — session recording     │
       │    SQLite    — projects, snippets    │
       └──────────────────────────────────────┘
```

**DNS:** `glade.home` requires a Pi-hole A record pointing to the host's **Tailscale IP**. This makes the same URL resolve on the LAN and remotely over Tailscale. Pi-hole must be configured as a global nameserver in Tailscale admin DNS settings.
**TLS:** mkcert cert for `glade.home`, managed by standalone `caddy-proxy`.
**Remote:** Tailscale mesh VPN for access outside the home network.

---

## Container Layout

Two Docker services defined in `docker-compose.yml`:

**glade-ttyd** — the application container (Debian bookworm-slim):
- Python API on port 7683
- ttyd instances on ports 7681 (main) and 7690–7729 (per-window, one per tmux window)
- tmux for session management and pipe-pane recording
- gh CLI (official Debian apt repo, architecture-aware: amd64/arm64/armhf)
- Zsh + Oh My Zsh (`ZSH_THEME=""` — no theme; prompt set in `config/zshrc`, personalised via `zshrc.local`)
- `gh-config` named Docker volume for persistent, host-isolated GitHub auth

**glade-web** — Caddy file server:
- Serves `web/index.html` at `/`
- Proxies `/api/*` to `glade-ttyd:7683`
- Serves fonts from `/assets/*`
- No-cache headers on HTML/manifest for instant updates

**caddy-proxy** — standalone (not in this compose file):
- Pre-existing container shared with other `*.home` services
- Routes `glade.home` to `glade-web:7682`
- Routes `/ttyd/{port}` to `glade-ttyd:{port}` for WebSocket proxying
- Manages TLS certs

---

## Data Flow

### Terminal Session

1. User taps project card in PWA
2. PWA calls `POST /api/projects/:id/start`
3. API creates tmux session (if not running) via `create_tmux_session()`
4. API starts `tmux pipe-pane` to record output to `~/.glade/logs/{slug}/{timestamp}.log`
5. API spawns a ttyd per window via a **linked (grouped) tmux session** (`{sname}-w{idx}`) on a free port (7690–7729)
6. API returns `{port}` to PWA
7. PWA loads `https://glade.home/ttyd/{port}/` in an iframe
8. User types; input flows through iframe → WebSocket → ttyd → tmux → zsh

### Session Recording

- `tmux pipe-pane -o -t {session} 'cat >> {logfile}'` starts on session creation
- Raw terminal output (including ANSI codes) is appended to the log file
- Log files: `~/.glade/logs/{project-slug}/{YYYY-MM-DD_HH-MM-SS}.log`
- One file per session lifetime; stops when the tmux session closes
- ANSI codes stripped client-side (in PWA) or server-side (in search API)

### Session Log Browsing

1. User opens History tab
2. PWA calls `GET /api/logs` → list of log files with metadata
3. User taps a session → PWA calls `GET /api/logs/{project}/{file}`
4. If active: PWA polls `GET /api/logs/current/{project}` every 3 seconds
5. Client-side `stripAnsi()` cleans output for display
6. Client-side search filters rendered text in real-time

---

## Key Design Decisions

| Decision | What we chose | Why |
|---|---|---|
| Session recording | `tmux pipe-pane` to flat files | Zero overhead, always on, no daemon |
| Log storage | Flat files, not SQLite | Faster writes, simpler grep, cheaper |
| Frontend | Single-file PWA (~8500 lines) | No build step, instant deploy via git pull |
| API framework | Python stdlib `BaseHTTPRequestHandler` | Zero dependencies, runs on any Python |
| CSS approach | CSS custom properties on `:root`; Catppuccin flavors via class swap; Base16 via inline `style.setProperty`; no framework | Instant theme switching; both app UI and xterm.js terminal update together |
| Auth | Tailscale (network-level) | No passwords, no tokens, no sessions |
| Package installs | `config/packages.sh` build-time hook | Image ships lean; user adds what they need |
| Reverse proxy | Caddy (standalone container) | Shared with other `*.home` services |
| Font | Commit Mono (variable font, bundled in repo; custom upload via Settings) | Licensed beautifully; variable font ships in repo; user can override |
| Tab isolation | Per-window ttyd via linked tmux sessions (`{sname}-w{idx}`) | Each browser client independently controls which tab it views; switching tabs on one device never affects another |

---

## Catppuccin Mocha Palette

Default theme. Used consistently across terminal theme, UI chrome, buttons, overlays.

```
Crust:     #11111b    Mantle:    #181825    Base:      #1e1e2e
Surface0:  #313244    Surface1:  #45475a    Surface2:  #585b70
Overlay0:  #6c7086    Subtext0:  #a6adc8    Subtext1:  #bac2de
Text:      #cdd6f4    Blue:      #89b4fa    Green:     #a6e3a1
Red:       #f38ba8    Mauve:     #cba6f7    Peach:     #fab387
Rosewater: #f5e0dc
```

19 CSS custom properties are defined for each flavor: `--base`, `--mantle`, `--crust`, `--surface0`, `--surface1`, `--surface2`, `--overlay0`, `--overlay1`, `--subtext0`, `--subtext1`, `--text`, `--red`, `--peach`, `--yellow`, `--green`, `--teal`, `--sky`, `--blue`, `--mauve`, `--pink`, `--rosewater`.

Catppuccin flavor is applied by adding a class (`theme-mocha`, `theme-frappe`, `theme-macchiato`, `theme-latte`) to `html`. Base16 overrides all 19 vars via inline `style.setProperty` on `:root`, which has higher specificity than class rules. `clearBase16Theme()` removes the inline overrides to restore class-driven theming.

---

## File Map

### Source (in repo, version-controlled)

| File | Lines | Purpose |
|---|---|---|
| `web/index.html` | ~8500 | Single-file PWA: CSS, HTML, JavaScript inline |
| `api/api.py` | ~1510 | REST API: projects, snippets, logs, uploads, GitHub auth |
| `entrypoint.sh` | 11 | Container startup: create dirs, exec API |
| `Dockerfile` | ~60 | Image: Debian, ttyd, Oh My Zsh, packages.sh hook |
| `docker-compose.yml` | ~65 | Two services: ttyd + web |
| `Makefile` | ~57 | Daily commands: up, down, restart, build, logs |
| `install.sh` | 292 | Host-side installer (creates dirs, init DB, shell integration) |
| `db/schema.sql` | 64 | SQLite schema: projects, snippets, settings |
| `config/zshrc` | — | Shell config baked into image |
| `config/tmux.conf` | — | Tmux config (Catppuccin Mocha status bar) |
| `config/packages.sh` | — | Build-time hook: user-defined package installs (empty by default) |
| `config/packages.sh.example` | — | Recipe examples: gh CLI, Node.js, pip, Rust, apt |
| `services/Caddyfile` | 61 | Caddy-proxy config for glade.home |
| `services/web.Caddyfile` | 42 | Inner Caddy config for glade-web container |

### Runtime (outside repo, on host at `~/.glade/`)

| Path | Purpose |
|---|---|
| `db/history.db` | SQLite: projects, snippets, settings, keyboard layouts |
| `logs/{project-slug}/` | Session log files (one per tmux session) |
| `logs/_main/` | Main shell logs (reserved, currently unused) |
| `projects/{slug}/` | GitHub-cloned repos (created on project creation from GitHub source) |
| `uploads/` | Pasted images (temporary storage) |
| `assets/fonts/` | Custom font uploads (user-supplied via Settings UI) |
| `config/zshrc.local` | User shell overrides: `PROMPT`, `RPROMPT`, aliases, extra sources. Sourced last in container `.zshrc`. Edit on host — no rebuild needed. |
| `config/zsh_history` | Persisted zsh history (`HISTFILE`); survives container rebuilds |
| `config/github-copilot/` | GitHub Copilot CLI auth + sessions; bind-mounted to `/root/.config/github-copilot` |
| `config/claude/` | Claude CLI auth + sessions; bind-mounted to `/root/.claude` |

---

## Port Allocation

| Port | Service |
|------|---------|
| 7681 | ttyd — main/default terminal shell |
| 7682 | glade-web — Caddy serving index.html, assets, API proxy |
| 7683 | api.py — REST API |
| 7690–7729 | Per-window ttyd instances (one per tmux window, allocated dynamically) |

---

## Deployment Model

The container clones the repo from GitHub on first start and polls `origin/main` every 2 minutes. The host only needs `docker-compose.yml` and `.env`.

| What changed | How it deploys |
|---|---|
| `web/index.html` / static files | Auto-pulled; browser gets new file on next load |
| `api/api.py` | Auto-pulled; PWA shows "Update available" banner → user taps Restart |
| `Dockerfile`, `entrypoint.sh`, `config/` | Auto-pulled but can't apply without rebuild; banner shows "run `make build`" |
| `docker-compose.yml` | `make down && make up` on the host |

---

## ANSI Stripping

Terminal logs contain raw ANSI escape codes. Two implementations strip them:

**JavaScript (client-side, in `web/index.html`):**
```javascript
str.replace(/\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-B]|\x1b[>=]|[\x00-\x08\x0e-\x1f]/g, '')
```

**Python (server-side, in `api/api.py`):**
```python
re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-B]|\x1b[>=]|[\x00-\x08\x0e-\x1f]', '', text)
```

Both handle: CSI sequences (including `?` intermediates like bracketed paste), OSC sequences (BEL or ST terminated), charset switching, mode changes, and low control characters.

---

## Known Limitations

- No log rotation or retention policy (logs grow without bound)
- ANSI colors are stripped, not rendered, in the log viewer
- No multi-user access control (anyone on the tailnet sees all projects)
- Container restarts don't re-attach pipe-pane to existing sessions
- `_main/` log directory exists but main shell recording is not wired up
- The `sessions` and `interactions` tables in schema.sql are legacy (from the copilot-focused era); not used by current code

## Shell Customisation

The container's `.zshrc` sets `ZSH_THEME=""` (no theme) to prevent any Oh My Zsh `precmd` hook from silently overriding `PROMPT` after startup. The prompt is set once, cleanly.

User overrides belong in `~/.glade/config/zshrc.local` on the host — sourced last, no rebuild needed:

```zsh
PROMPT='%(?.%F{#89b4fa}.%F{#f38ba8})❯%f '
RPROMPT=''
source ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
source ~/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
```

> **Dockerfile ordering trap:** `packages.sh` installs Oh My Zsh, which overwrites `/root/.zshrc`. The `COPY config/zshrc /root/.zshrc` line must appear *after* the `RUN packages.sh` step — otherwise every build silently discards your config.
