# Glade.app — Native macOS Client

> Design document for a native macOS terminal app built on a Ghostty fork,
> connecting to the existing Glade server for project management, session
> recording, and tmux orchestration.

---

## Problem

The Glade PWA works well on mobile and remote devices. On a Mac sitting two
feet from the server, it routes every keystroke through a browser, an iframe,
a WebSocket, and ttyd before it reaches tmux. A native app cuts that chain
short. GPU-rendered terminal output, native keyboard handling, zero-latency
local input, proper macOS window management — the browser was never built
for this.

## Approach

Fork Ghostty (MIT-licensed, Zig core + Swift/AppKit shell, Metal renderer).
Add Glade's project layer on top. Keep Ghostty's terminal engine untouched.
Change the chrome around it.

The native app complements the PWA — both exist. PWA stays for
mobile/iPad/remote. The native app owns the Mac.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Glade.app (macOS)                          │
│                                             │
│  ┌─ Swift/AppKit/SwiftUI ──────────────┐    │
│  │  Project tab bar (inline title bar) │    │
│  │  Shell sub-tabs                     │    │
│  │  Command palette (⌘K)              │    │
│  │  Settings / Log viewer              │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─ libghostty (Zig + Metal) ──────────┐   │
│  │  Terminal surface (GPU-rendered)     │    │
│  │  Font rasterization                 │    │
│  │  Input handling                     │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─ Network layer ────────────────────┐     │
│  │  REST → api.py (projects, snippets)│     │
│  │  SSH or ttyd (terminal I/O)        │     │
│  └────────────────────────────────────┘     │
└─────────────────────────────────────────────┘
```

The server (Docker container with api.py, tmux, pipe-pane) stays unchanged.
Same API, same session management. The native app is a new client, not a new
server.

---

## Window Layout

Project tabs sit inline with the macOS window buttons — traffic lights on the
left, tabs flowing to their right. One row of chrome. Shell sub-tabs sit
below. The terminal fills everything else.

```
┌──────────────────────────────────────────────────────┐
│ ● ● ●  [● glade-sh] [● dotfiles] [● api-server] [+]│  ← title bar + project tabs
├──────────────────────────────────────────────────────┤
│  shell 0 │ shell 1 │ shell 2 │ [+]                  │  ← shell sub-tabs
├──────────────────────────────────────────────────────┤
│                                                      │
│  $ make build && make test                           │
│  ✓ All 247 tests passed                             │
│  $                                                   │
│                                                      │  ← GPU-rendered terminal
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Tab behavior:**

- Project tabs show name + color dot. Activity badge (blue pulse) for unseen output.
- Right-click project tab → Edit, Stop, Close.
- `[+]` opens project picker (search + cards with color/name/status).
- Shell sub-tabs show window index/name. `[+]` creates new tmux window via API.
- `⌘1–9` switches projects. `⌃Tab`/`⌃⇧Tab` cycles shells.
- Drag to reorder both levels.

**Command palette (`⌘K`):**

- Searches across projects (open/switch), snippets (send to terminal), and
  actions (new project, settings, logs).
- Fuzzy matching. Enter to act.
- Snippets show name + command preview. Selecting one sends it to the active
  terminal.

**Split panes:**

- Ghostty's native splits. `⌘D` horizontal, `⌘⇧D` vertical.
- Each pane can show a different shell from the same project.

---

## Connection & Transport

### Setup flow

1. First launch → Settings → "Connect to Glade server"
2. Enter server address: `glade.home`, `casper.local:7683`, or Tailscale IP
3. App tests connection: `GET /api/health`
4. Choose terminal transport:
   - **SSH (recommended)** — provide host/user/key. App opens SSH channel,
     runs `tmux attach-session -t {sname}`. Ghostty renders PTY natively.
   - **ttyd WebSocket** — connect to `wss://{host}/ttyd/{port}/`. Same
     transport the PWA uses.
5. Connection saved. Auto-reconnect on launch.

### Transport paths

**SSH mode:**
```
Keystroke → Ghostty → SSH channel → tmux → zsh
zsh output → tmux → SSH channel → Ghostty → Metal → screen
```

**ttyd mode:**
```
Keystroke → Ghostty → WebSocket → ttyd → tmux → zsh
zsh output → tmux → ttyd → WebSocket → Ghostty → Metal → screen
```

SSH cuts out ttyd — one fewer process, one fewer protocol translation.

### REST API client

Thin Swift layer over `URLSession`. Talks to `api.py` for project CRUD,
snippets, logs, settings, activity polling, GitHub auth status. Same
endpoints the PWA uses — no new server code needed.

---

## Feature Map

### Kept from PWA

| Feature | Native implementation |
|---|---|
| Project CRUD | Same API. Create/edit/delete via Settings or ⌘K |
| Project colors | Color dot in tab bar, stored server-side |
| Multi-shell tabs | Same tmux windows. Shell sub-tabs below project tabs |
| Snippets | Command palette only (⌘K → type → send) |
| Session logs | Sidebar log browser. Server records, app fetches via REST |
| Activity badges | Same API polling. Blue dot on tabs |
| GitHub auth | Same device flow from Settings |
| Themes | Ghostty's built-in theme system |
| Find in scrollback | ⌘F — Ghostty built-in |

### Dropped (mobile-only)

| Feature | Reason |
|---|---|
| Custom keyboard panel | Real keyboard available |
| Compact keyboard / layout editor | Same |
| Trackpad ring cursor | Native mouse/trackpad |
| Swipe gestures | Keyboard shortcuts |
| Bottom sheet / panel modes | Desktop layout |
| Focus mode | Terminal already fills the window |
| Text selection overlay | Native selection works |
| Haptic feedback | No haptic hardware |
| PWA manifest / service worker | Native app |

### New (native-only)

| Feature | Description |
|---|---|
| Split panes | Ghostty native splits (⌘D / ⌘⇧D) |
| Native notifications | macOS notification on long-running command finish |
| Global hotkey | System-wide shortcut to summon/dismiss app |
| Spotlight-style launcher | ⌘K from anywhere opens app at that project |
| Drag-and-drop | Drag files into terminal to paste paths |
| Multiple windows | One per project, or all in one — user's choice |
| Menu bar | Standard macOS menu with all actions |

---

## Ghostty Fork Strategy

### What Ghostty provides (untouched)

- libghostty (Zig): terminal emulation, VT parser, Metal renderer, font handling
- Swift/AppKit shell: window management, tab bar, splits, settings, keybinds
- Configuration system (`~/.config/ghostty/config`)
- Built-in multiplexing (disabled — we use tmux)

### What we add

1. **Project-aware tab model.** Wrap Ghostty tabs in a "project" group with
   color, server-side tmux session, and shell sub-tabs. Title bar gets inline
   project tabs.

2. **GladeServer module.** REST calls to api.py, SSH session pooling,
   reconnection. Injected at app startup.

3. **Command palette.** SwiftUI overlay. Fetches projects + snippets from
   server, fuzzy-matches locally.

4. **Log viewer.** SwiftUI panel. Fetches logs from REST API, renders with
   ANSI stripped.

5. **Session startup.** Open project → `POST /api/projects/:id/start` → get
   tmux session → open SSH/ttyd connection → hand stream to libghostty.

### Separation strategy

- Glade code lives in `Sources/Glade/` — clearly separated from Ghostty
- Minimize edits to Ghostty's core Swift files — prefer extensions
- Track upstream releases. Rebase periodically
- Glade config keys in their own namespace

---

## Repository Structure

```
glade-app/                        ← forked from ghostty-org/ghostty
├── Sources/
│   ├── Ghostty/                  ← upstream Swift code (minimal edits)
│   └── Glade/
│       ├── GladeServer.swift     ← REST + SSH client
│       ├── ProjectTabBar.swift   ← project-aware tab model
│       ├── ShellSubTabs.swift    ← per-project shell tabs
│       ├── CommandPalette.swift  ← ⌘K overlay
│       ├── LogViewer.swift       ← session log browser
│       ├── Settings/             ← Glade-specific settings
│       └── Models/               ← Project, Snippet, LogEntry
├── src/                          ← upstream libghostty Zig code (untouched)
├── GladeConfig/                  ← server addr, transport, preferences
└── README.md
```

---

## Phases

### Phase 1 — Foundation

Get a working app that can open projects and run shells.

1. Fork Ghostty, build unmodified, verify it runs
2. Add `GladeServer` module — connect to api.py, fetch project list
3. Replace "new tab" with "open project" — start tmux session via API,
   connect via SSH or ttyd
4. Project tabs with color dots and names, inline in title bar
5. Shell sub-tabs per project
6. Command palette (⌘K) with project switching + snippet sending

### Phase 2 — Project Management

Full project lifecycle — create, edit, delete, reorder.

1. Project create UI — name, directory, color picker
2. GitHub repo cloning — device auth flow, create project from GitHub URL
3. Project edit — rename, change color, change directory
4. Project delete — with confirmation, optional directory cleanup
5. Project reordering — drag tabs to reorder, persisted via sort_order
6. Stop project — kill ttyd/SSH but keep tmux session alive

### Phase 3 — Awareness

Know what's happening across all projects without switching to each one.

1. Activity badges — poll `GET /api/projects/activity`, blue dot on tabs
   with unseen output
2. Idle detection — `GET /api/projects/:id/shell-idle` before sending
   snippets or commands
3. Activity polling interval — configurable in settings (default 5s)

### Phase 4 — Session History

Browse and search everything that happened in every project.

1. Log browser sidebar — list projects, their log files, timestamps, sizes
2. Log viewer — render log content with ANSI stripped, scrollable
3. Live log tailing — poll `GET /api/logs/current/:project` for active
   sessions, auto-scroll
4. Log search — `GET /api/logs/search?q=` with results grouped by project
5. Log deletion — per-file delete with confirmation

### Phase 5 — Settings & Configuration

In-app settings panel for everything that isn't Ghostty's own config.

1. Server connection — address, transport (SSH/ttyd), test connection
2. GitHub section — connect/disconnect, show username + avatar
3. Theme picker — in-app browser for Ghostty's themes (read config dir)
4. Custom font upload — upload woff2/ttf/otf via API, apply to terminal
5. Server status — build date, version, project count, health
6. Container rebuild trigger — same as PWA, with log viewer

### Phase 6 — Native Power

Features only a native app can do well.

1. Split panes — wire Ghostty's native splits to tmux windows
2. Native notifications — macOS notification when long-running command
   finishes (uses idle detection)
3. Global hotkey — system-wide shortcut to summon/dismiss the app
4. Drag-and-drop — drag files into terminal to paste paths
5. Multiple windows — one per project, or all in one, user's choice
6. Image paste/upload — paste image, upload via API, insert URL

### Phase 7 — Polish & Ship

1. Auto-update mechanism (Sparkle or similar)
2. `.dmg` distribution with code signing + notarization
3. App icon and branding
4. First-run onboarding flow (connect to server, pick transport)
5. Keyboard shortcut reference sheet (⌘? or help menu)
6. Menu bar — standard macOS menus with all actions wired up

---

## What Doesn't Change

- `api.py` — same endpoints, no modifications needed
- The PWA — keeps working alongside the native app
- Session recording — server-side pipe-pane, untouched
- tmux management — server-side, untouched
- Project/snippet storage — server-side SQLite, untouched
