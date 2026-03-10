# Changelog

All notable changes to Roost are documented here.

---

## [Unreleased]

---

## [1.0.0] — 2025

Initial public release.

### Features

- **Multi-project terminals** — per-project tmux sessions with isolated ttyd instances on ports 7690–7699
- **Mobile PWA** — installable via "Add to Home Screen" on iOS and Android; full-screen display mode
- **Custom mobile keyboard** — configurable key toolbar with Esc, Tab, Ctrl, Alt, arrows, and combos; long-press to repeat; drag to reorder
- **Compact and full keyboard layouts** — toggle between 4-row and 7-row layouts; layout persisted via API
- **Session logging** — automatic recording via `tmux pipe-pane` to flat files in `~/.roost/logs/`
- **History tab** — browse and full-text search session logs; live tail for active sessions
- **Command snippets** — saved commands injected into the terminal on tap; CRUD via REST API
- **Auto-reconnect** — reconnects on network drop or app background; force-reconnects after >5s backgrounded
- **Activity badges** — per-project unread activity indicators; cleared on view
- **Shell management** — create, list, and kill tmux windows per project via API
- **Image uploads** — paste images into the terminal; served via `/api/uploads/`
- **Catppuccin Mocha theme** — consistent palette across terminal, UI chrome, and toolbar
- **Berkeley Mono Nerd Font** — optional; falls back to JetBrains Mono → Fira Code → system monospace
- **Python stdlib API** — zero third-party dependencies; `BaseHTTPRequestHandler` on port 7683
- **SQLite storage** — projects, snippets, settings, keyboard layouts in `~/.roost/db/history.db`
- **Docker Compose stack** — two services: `roost-ttyd` (app) and `roost-web` (Caddy file server)
- **Makefile** — `make setup`, `up`, `down`, `restart`, `build`, `logs`, `shell`, `ps`
- **Tailscale support** — remote access over mesh VPN; works on same `roost.local` URL from anywhere
- **mkcert TLS** — local HTTPS via standalone `caddy-proxy`; mkcert CA for trusted certs on all devices
