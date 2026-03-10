# Roost

A self-hosted, always-on terminal that's identical on every device — phone, laptop, desktop. Runs centrally on your own machine (Mac Mini, home server, VPS) and is accessible from anywhere via browser. All interactions are logged to SQLite with full-text search.

The UI is a single-file PWA styled in Catppuccin Mocha with a mobile keyboard toolbar, per-project terminal isolation via tmux, command snippets, and connection auto-recovery.

> **Screenshots/GIFs welcome** — if you set this up and want to contribute visuals to the README, open a PR.

---

## Architecture

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Laptop     │   │   Phone      │   │  Other PC    │
│  (browser)   │   │ (Safari PWA) │   │  (browser)   │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       └──────────┬───────┴───────────────────┘
                  │  LAN / Tailscale (VPN)
                  ▼
       ┌──────────────────────────────────────┐
       │           Mac Mini (Docker)          │
       │                                      │
       │  caddy-proxy (standalone container)  │
       │    https://ai.home → :7682 (web UI)  │
       │    /ttyd/* → :7681 + :7690–7699      │
       │                                      │
       │  roost-web  (:7682)           │
       │    serves index.html + assets        │
       │                                      │
       │  roost-ttyd (:7681, :7683)    │
       │    ttyd     — main terminal shell    │
       │    api.py   — REST API (:7683)       │
       │    per-project ttyd (:7690–7699)     │
       │    SQLite   — interaction history    │
       └──────────────────────────────────────┘
```

**DNS:** Pi-hole maps `ai.home` → Mac Mini LAN IP  
**TLS:** mkcert cert managed by the standalone `caddy-proxy`  
**Remote access:** Tailscale connects devices outside the home network  

---

## Features

- **Multi-project terminals** — each project gets an isolated tmux session and a ttyd instance on a dedicated port (7690–7699)
- **Mobile-optimised PWA** — installable via "Add to Home Screen"; keyboard toolbar with Esc, Tab, Ctrl, Alt, arrows, and combos
- **Key repeat** — hold any key on the custom keyboard or toolbar to repeat at 80ms intervals after a 400ms delay
- **Interaction logging** — every `gh copilot` call is captured (prompt, response, cwd, device, duration) to SQLite with FTS5 search
- **Command snippets** — saved commands that inject directly into the terminal
- **Connection recovery** — auto-reconnects on network drop or app background; force-reconnects after >5s in background
- **Catppuccin Mocha** — consistent theme across terminal, UI chrome, and toolbar
- **Berkeley Mono Nerd Font** — optional; falls back to JetBrains Mono → Fira Code → system monospace

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Mac Mini (or always-on Linux host) | The execution hub; everything runs here |
| Docker Desktop | For the container stack |
| Standalone `caddy-proxy` container | Pre-existing; handles TLS for all `*.home` domains |
| Pi-hole | Provides `ai.home` DNS record |
| Tailscale | For remote access outside the home network |
| GitHub account with Copilot access | `gh auth login` must succeed inside the container |
| Berkeley Mono Nerd Font `.woff2` or `.ttf` *(optional)* | Licensed; must be supplied by you |

---

## Directory Structure

```
roost/
├── api/
│   └── api.py              # Python REST API (BaseHTTPRequestHandler, port 7683)
├── assets/
│   └── fonts/              # Place BerkeleyMonoNerdFont-Regular.{woff2,ttf} here
├── bin/
│   ├── copilot-wrap        # Shell function: intercepts gh copilot, logs to SQLite
│   └── copilot-history     # CLI tool: search/browse interaction history (legacy)
├── config/
│   ├── zshrc               # Zsh config baked into container image
│   ├── bashrc              # Bash config baked into container image
│   └── tmux.conf           # Tmux status bar (Catppuccin Mocha, minimal)
├── db/
│   └── schema.sql          # SQLite schema (snippets, settings, projects)
├── docs/
│   └── working-from-anywhere.md  # How to SSH into a laptop from the terminal
├── lib/
│   └── logger.sh           # Bash logging library (init DB, record interactions)
├── logs/                   # Session logs (auto-recorded via tmux pipe-pane)
│   ├── _main/              # Main shell logs
│   └── {project-slug}/     # Per-project logs
├── services/
│   ├── Caddyfile           # ai.home block for the standalone caddy-proxy
│   └── web.Caddyfile       # Caddy config for the roost-web container
├── web/
│   ├── index.html          # Single-file PWA (~340 KB, all CSS + JS inline)
│   ├── manifest.json       # PWA manifest (icons, display: standalone)
│   └── icons/              # App icons: 32×32, 192×192, 512×512
├── .env.example            # Configuration template — copy to .env and edit
├── Dockerfile              # debian:bookworm-slim; installs ttyd, gh, oh-my-zsh
├── docker-compose.yml      # Two services: ttyd (app) + web (Caddy file server)
├── entrypoint.sh           # Container start: checks gh auth, launches api.py
├── install.sh              # Host machine installer (copies files, initialises DB)
├── Makefile                # Common operations: setup, up, build, logs, shell, auth
└── SETUP.md                # Full step-by-step setup walkthrough
```

---

## Setup

See **[SETUP.md](SETUP.md)** for the full walkthrough. The short version:

### 1. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```bash
HOST=mac-mini      # hostname of the machine running Docker
DOMAIN=ai.home     # domain you'll use to access the UI
DEV_DIR=~/Dev      # local directory to mount as /mnt/dev inside the container
```

### 2. DNS — Pi-hole

Add a local DNS record in Pi-hole admin → **Local DNS → DNS Records**:
- Domain: `ai.home` (or whatever you set `DOMAIN` to)
- IP: the machine's LAN IP (`ipconfig getifaddr en0` on macOS)

### 3. TLS — mkcert cert

On the machine where `caddy-proxy` is managed:

```bash
mkcert ai.home
mv ai.home.pem       /path/to/caddy/certs/ai.home.pem
mv ai.home-key.pem   /path/to/caddy/certs/ai.home-key.pem
```

Add the `ai.home` block from `services/Caddyfile` into your `caddy-proxy` Caddyfile, then restart it.

### 4. Font — Berkeley Mono Nerd Font (optional)

Copy the Regular weight into the assets directory:

```bash
cp BerkeleyMonoNerdFont-Regular.woff2 ~/.roost/assets/fonts/
# .ttf also works; filename must start with BerkeleyMonoNerdFont-Regular
```

The UI falls back to JetBrains Mono → Fira Code → system monospace if the font is absent.

### 5. First-time start

```bash
make setup
```

This creates the Docker network, builds and starts the containers, then drops you into `gh auth login`. Auth tokens are stored in `~/.config/gh` (volume-mounted — survives container rebuilds).

If the container was already running when you cloned:
```bash
make build    # rebuild image
make auth     # authenticate gh CLI
```

### 6. Shell integration on the host (optional, for local logging)

If you want `gh copilot` calls from the host shell (outside Docker) to be logged:

```bash
./install.sh
source ~/.zshrc
```

---

## Accessing the UI

| Device | URL | Notes |
|---|---|---|
| Laptop / desktop | `https://ai.home` | LAN or Tailscale |
| Phone (iOS) | `https://ai.home` → Share → Add to Home Screen | Full-screen PWA |
| Phone (Android) | `https://ai.home` → Install app | Full-screen PWA |
| Remote (Tailscale) | `https://ai.home` via Tailscale | Works anywhere |

### First visit — trust the mkcert CA

```bash
mkcert -install   # desktop/laptop
```

On iOS: import the mkcert root CA profile → Settings → General → VPN & Device Management → trust it.

---

## Using the Terminal


### Projects

- Tap **＋** to create a project (name, directory path, colour)
- Each project opens its own tmux session; closing the browser doesn't kill it
- Tap the project card to connect; the terminal loads in the browser
- Multiple shells per project — use the tmux window tabs inside the terminal

### Custom keyboard (mobile)

The panel at the bottom has two layouts (toggle with the compact/full button):

- **Full:** 7 rows of configurable keys
- **Compact:** 4 rows

Long-press any key to edit its label, value, and type. Drag to reorder.  
Hold a key to repeat it (400ms initial delay, 80ms interval).

### Shortcut bar (always visible)

Fixed row above the keyboard/panel: `↵ Enter`, `Ctrl`, `Alt`, `^C`, `◀ ▲ ▼ ▶`.  
Arrow keys and Enter support hold-to-repeat.

### Command snippets

Saved commands in the Snippets tab — tap to inject into the terminal.

---

## Session Logs

Every terminal session is recorded automatically via tmux `pipe-pane`. Logs are stored as flat files in `~/.roost/logs/{project-slug}/`.

Browse and search session logs from the **History** tab in the UI. Tap a session card to open the log viewer with client-side search. Active sessions show a live-updating tail.

### Log API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/logs` | List all log files (newest first, grouped by project) |
| `GET` | `/api/logs/:project/:file` | Raw log content (`?tail=N` for last N lines) |
| `GET` | `/api/logs/current/:project` | Tail active session (last 200 lines) |
| `GET` | `/api/logs/search?q=term` | Search across all logs (grep, ANSI-stripped excerpts) |

---

## API Reference

The Python API runs on port **7683** inside the container. All responses are JSON.

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Returns `{"ok": true}` |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create project `{name, directory, color}` |
| `GET` | `/api/projects/:id` | Get project |
| `PUT` | `/api/projects/:id` | Update project |
| `DELETE` | `/api/projects/:id` | Delete project and stop ttyd |
| `POST` | `/api/projects/:id/start` | Start ttyd → `{port}` |
| `POST` | `/api/projects/:id/stop` | Stop ttyd (tmux session kept) |
| `GET` | `/api/projects/activity` | Activity status for all projects (for badge polling) |
| `PUT` | `/api/projects/:id/viewed` | Mark project as viewed (clears activity badge) |

### Shells (tmux windows per project)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/projects/:id/shells` | List tmux windows `[{index, name, active}]` |
| `POST` | `/api/projects/:id/shells` | Create new window → `{index}` |
| `DELETE` | `/api/projects/:id/shells/:n` | Kill window n |

### Snippets

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/snippets` | List all snippets |
| `POST` | `/api/snippets` | Create `{name, command}` |
| `PUT` | `/api/snippets/:id` | Update snippet |
| `DELETE` | `/api/snippets/:id` | Delete snippet |

### Settings

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/settings/layout` | Get custom keyboard layout (JSON) |
| `PUT` | `/api/settings/layout` | Save keyboard layout |
| `GET` | `/api/settings/compact-layout` | Get compact layout |
| `PUT` | `/api/settings/compact-layout` | Save compact layout |

### Uploads

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/upload-image` | Upload base64 image → `{path, url, filename}` |
| `GET` | `/api/uploads` | List recent uploads (last 10) |
| `GET` | `/api/uploads/:filename` | Serve upload |

### History export

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/export` | Export all interactions as JSON |

### Session Logs

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/logs` | List all log files (newest first) |
| `GET` | `/api/logs/:project/:file` | Raw log content (`?tail=N` for last N lines) |
| `GET` | `/api/logs/current/:project` | Tail active session (last 200 lines) |
| `GET` | `/api/logs/search?q=term` | Search across all logs |

---

## Database Schema

SQLite at `~/.roost/db/history.db`. Schema lives in `db/schema.sql`.

**`projects`** — name, directory, color, sort order, last active timestamp  
**`snippets`** — saved commands  
**`settings`** — key/value store for keyboard layout and UI preferences  

Session logs are stored as flat files in `~/.roost/logs/`, not in the database.  

---

## Development

The repo lives on your server (the machine running Docker). All services mount files directly from the repo via bind mounts — `web/` into the web container, `api/api.py` into the ttyd container. This means a `git pull` on the server is the deploy step for most changes.

### Updating and deploying

Edit files on any machine, commit, and push. Then on the server:

```bash
cd /path/to/roost          # wherever you cloned the repo
git pull
```

That's it for web and API changes — the containers read directly from the repo. For changes that touch the Docker image itself, rebuild after pulling:

| What changed | Deploy command |
|---|---|
| `web/index.html`, icons, manifest | `git pull` — refresh browser |
| `api/api.py` | `git pull && make restart` |
| `Dockerfile`, `entrypoint.sh`, `config/` | `git pull && make build` |
| `docker-compose.yml` | `git pull && make down && make up` |

### Common commands (via `make`)

```bash
make up          # start all services
make down        # stop all services
make restart     # restart ttyd only (picks up api.py changes — no rebuild needed)
make build       # full rebuild (only needed after Dockerfile / config/ changes)
make logs        # tail logs for all services
make shell       # open a Zsh shell inside the container
make auth        # run gh auth login inside the container
make ps          # show container status
```

### What's mounted where

| Repo path | Container path | Service | Hot-reload? |
|---|---|---|---|
| `./web/` | `/srv/web` | roost-web | Yes — refresh browser |
| `./api/api.py` | `/app/api.py` | roost-ttyd | `make restart` |
| `./services/web.Caddyfile` | `/etc/caddy/Caddyfile` | roost-web | `make restart` |

Runtime data lives outside the repo in `~/.roost/`:

| Host path | Container path | Purpose |
|---|---|---|
| `~/.roost/` | `/root/.roost` | SQLite DB, logs, uploads |
| `~/.roost/assets/` | `/srv/assets` | Fonts (not in repo — user-provided) |
| `~/.config/gh/` | `/root/.config/gh` | GitHub CLI auth tokens |

### Ports (inside container / on Mac Mini LAN)

| Port | Service |
|------|---------|
| 7681 | ttyd — default shell (exposed to Caddy) |
| 7682 | Caddy web server — serves index.html and assets |
| 7683 | Python API |
| 7690–7699 | Per-project ttyd instances (allocated dynamically) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Can't reach `https://ai.home` | Check Pi-hole DNS record. Verify `caddy-proxy` is running: `docker ps`. Try Mac Mini's LAN IP directly. |
| Browser shows cert warning | Run `mkcert -install` on the client, or import the mkcert root CA on iOS. |
| Terminal loads but no input | Ensure ttyd is running with `--writable` (it is by default in Dockerfile). |
| `gh copilot` not found in terminal | Run `gh extension install github/gh-copilot` inside the container. |
| First Docker build is slow | Normal — downloads ~200 MB of packages. Watch with `docker compose logs -f ttyd`. |
| Phone keyboard covers terminal | Open as a PWA ("Add to Home Screen"). The shortcut bar handles Esc/Tab/Ctrl without the native keyboard. |
| History tab empty | Start a project — session logging begins when a tmux session spawns. Check `~/.roost/logs/` for log files. |
| "Press ↵ to Reconnect" stuck | Tap it — it should reconnect. If it doesn't, quit and reopen the PWA. The overlay auto-dismisses once the WebSocket is established. |
| Container keeps restarting | Check `docker compose logs ttyd` for startup errors, usually a missing volume or DB permission issue. |

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Terminal server | [ttyd](https://github.com/tsl0922/ttyd) | Single binary, xterm.js frontend, WebSocket protocol |
| Shell | Zsh + Oh My Zsh + Spaceship | Familiar, plugin ecosystem, git-aware prompt |
| Multiplexer | tmux | One session per project; survives disconnects |
| API | Python stdlib (`BaseHTTPRequestHandler`) | Zero dependencies, runs anywhere |
| Storage | SQLite + FTS5 | Single file, full-text search built in |
| Frontend | Vanilla JS + xterm.js | No build step; inline CSS + JS in one file |
| Theme | [Catppuccin Mocha](https://github.com/catppuccin/catppuccin) | Consistent palette, works well in terminals |
| Font | Berkeley Mono Nerd Font | Licensed; Nerd-patched for terminal glyphs |
| Reverse proxy | [Caddy](https://caddyserver.com/) | Auto TLS, simple config, shared with other home services |
| Remote access | [Tailscale](https://tailscale.com/) | Zero-config mesh VPN, iOS/Android apps |
| DNS | Pi-hole | Local `ai.home` record; already running |
| Containerisation | Docker Compose | Two services; `restart: unless-stopped` |
