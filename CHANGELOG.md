# Changelog

All notable changes to Glade are documented here.

---

## [Unreleased]

### Changed
- **Commit Mono replaces Berkeley Mono** as the default font; variable font (`CommitMonoV143-VF.woff2`) is now bundled in the repo (`web/assets/fonts/`, `docs/assets/fonts/`); no user setup required
- **iOS 18+ haptic feedback** — `haptic()` now detects iOS via userAgent and fires a light haptic using a hidden `<input type="checkbox" switch>` + `<label>` trick; Android still uses `navigator.vibrate`; older browsers silent no-op
- **Service worker fixed** — `res.clone()` must be called synchronously before any async gap; was throwing `TypeError: Failed to execute 'clone' on 'Response': Response body is already used`; cache bumped to `glade-shell-v3`
- **`toggleDesktopPanel` scope fix** — was defined inside an IIFE but called from outer keydown handler; fixed via `window.toggleDesktopPanel = toggleDesktopPanel`

### Added
- **Custom font upload** — Settings → Font: drag-drop zone or file picker accepts `.woff2`, `.ttf`, `.otf`; stored as `font-{ts}-{uuid}.{ext}` in `~/.glade/uploads/`; config persisted via `PUT /api/settings/font`
- **Font API endpoints** — `GET /api/settings/font`, `PUT /api/settings/font`, `POST /api/font`, `DELETE /api/font`
- **GitHub device auth UX** — `.gh-code-block` is now tappable (tap to copy with "Copied!" feedback); `.gh-code-value` has `user-select:text` for manual selection; "Open github.com/login/device" button copies the code before opening the URL
- **Keyboard shortcuts from iframe** — capture-phase keydown listener on `iframe.contentWindow` forwards Meta / Ctrl+` / Escape combos to the parent via synthetic `KeyboardEvent`

---

## [1.0.0] — 2025

Initial public release.

### Features

- **Multi-project terminals** — per-project tmux sessions with isolated ttyd instances on ports 7690–7699
- **Mobile PWA** — installable via "Add to Home Screen" on iOS and Android; full-screen display mode
- **Custom mobile keyboard** — configurable key toolbar with Esc, Tab, Ctrl, Alt, arrows, and combos; long-press to repeat; drag to reorder
- **Compact and full keyboard layouts** — toggle between 4-row and 7-row layouts; layout persisted via API
- **Session logging** — automatic recording via `tmux pipe-pane` to flat files in `~/.glade/logs/`
- **History tab** — browse and full-text search session logs; live tail for active sessions
- **Command snippets** — saved commands injected into the terminal on tap; CRUD via REST API
- **Auto-reconnect** — reconnects on network drop or app background; force-reconnects after >5s backgrounded
- **Activity badges** — per-project unread activity indicators; cleared on view
- **Shell management** — create, list, and kill tmux windows per project via API
- **Image uploads** — paste images into the terminal; served via `/api/uploads/`
- **Catppuccin Mocha theme** — consistent palette across terminal, UI chrome, and toolbar
- **Berkeley Mono Nerd Font** — optional; falls back to JetBrains Mono → Fira Code → system monospace
- **Python stdlib API** — zero third-party dependencies; `BaseHTTPRequestHandler` on port 7683
- **SQLite storage** — projects, snippets, settings, keyboard layouts in `~/.glade/db/history.db`
- **Docker Compose stack** — two services: `glade-ttyd` (app) and `glade-web` (Caddy file server)
- **Makefile** — `make setup`, `up`, `down`, `restart`, `build`, `logs`, `shell`, `ps`
- **Tailscale support** — remote access over mesh VPN; works on same `glade.local` URL from anywhere
- **mkcert TLS** — local HTTPS via standalone `caddy-proxy`; mkcert CA for trusted certs on all devices
