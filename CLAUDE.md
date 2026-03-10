# Copilot CLI Sync — Multi-Device Session Persistence

## Goal

Make GitHub Copilot CLI (`gh copilot`) feel identical on every device (laptop, phone, other computers) by centralizing execution on a home Mac Mini with full session logging, searchable history, and transparent access from anywhere. The mobile web experience should feel as polished as Termius — custom keyboard toolbar, Catppuccin Mocha theme, Berkeley Mono Nerd Font, responsive layout that works on phone and desktop.

## Architecture

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Laptop     │   │   Phone      │   │  Other PC    │
│  (browser /  │   │ (Safari /    │   │ (browser /   │
│   Termius)   │   │  browser)    │   │  SSH)        │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                   │
       └──────────┬───────┴───────────────────┘
                  │  Tailscale (encrypted mesh VPN, no passwords)
                  ▼
       ┌──────────────────────────┐
       │    Mac Mini (Docker)     │
       │                          │
       │  Caddy (reverse proxy)   │
       │    ├─ /        → wrapper │
       │    └─ /ttyd    → ttyd    │
       │  ttyd (terminal backend) │
       │  gh copilot (execution)  │
       │  copilot-log (shim)      │
       │  SQLite (history)        │
       └──────────────────────────┘
```

## Design Direction

- **Color theme:** Catppuccin Mocha everywhere (terminal, toolbar, overlays, history viewer)
- **Font:** Berkeley Mono Nerd Font (locally licensed, Nerd-patched)
- **CSS framework:** Tailwind CSS (CDN) for the HTML wrapper UI
- **UX inspiration:** Termius iOS — extra key row, clean mobile layout, auto-reconnect
- **Responsive:** single HTML wrapper that adapts from phone to desktop seamlessly

### Catppuccin Mocha Palette Reference

```
Crust:     #11111b    (deepest bg, outer page bg)
Mantle:    #181825    (toolbar bg, deeper surfaces)
Base:      #1e1e2e    (terminal bg, card bg)
Surface0:  #313244    (button bg, input bg)
Surface1:  #45475a    (button hover, active states)
Surface2:  #585b70    (subtle borders, dividers)
Overlay0:  #6c7086    (placeholder text, disabled)
Subtext0:  #a6adc8    (secondary text, hints)
Text:      #cdd6f4    (primary text, key labels)
Blue:      #89b4fa    (accents, active indicator, links)
Green:     #a6e3a1    (success, connected dot)
Red:       #f38ba8    (errors, disconnected)
Mauve:     #cba6f7    (focus rings, highlights)
Peach:     #fab387    (warnings, reconnecting state)
Rosewater: #f5e0dc    (cursor color)
```

---

## Phase 1 — Server Foundation

### 1a. Tailscale Setup

Tailscale is the auth layer. No passwords, no port forwarding. Only devices on the tailnet can reach the server.

- Install Tailscale on the Mac Mini: `brew install tailscale` or download from tailscale.com
- Install Tailscale on all client devices:
  - iOS: App Store → Tailscale → sign in (one-tap setup)
  - Android: Google Play → Tailscale → sign in
  - Other laptops/PCs: download from tailscale.com/download
- Enable MagicDNS in Tailscale admin console so the Mac Mini is reachable by hostname
  (e.g. `http://mac-mini` instead of an IP)
- Optional: enable Tailscale SSH for keyless SSH access from Termius
- Verify: all devices can ping the Mac Mini via Tailscale hostname

### 1b. ttyd Setup (browser-based terminal)

ttyd is a single binary that shares your terminal as a web page. No VS Code UI, no overhead — just a terminal in a browser.

- Install ttyd: `brew install ttyd`
- No `--credential` flag needed — Tailscale handles auth (only tailnet devices can connect)
- Bind to Tailscale interface only for safety: `ttyd --interface tailscale0 ...`
- Run with Catppuccin Mocha theme and Berkeley Mono:
  ```
  ttyd --port 7681 \
       --writable \
       --reconnect 5 \
       --max-clients 3 \
       -t 'theme={
         "background":"#1e1e2e",
         "foreground":"#cdd6f4",
         "cursor":"#f5e0dc",
         "cursorAccent":"#1e1e2e",
         "selectionBackground":"#585b70",
         "selectionForeground":"#cdd6f4",
         "black":"#45475a",
         "red":"#f38ba8",
         "green":"#a6e3a1",
         "yellow":"#f9e2af",
         "blue":"#89b4fa",
         "magenta":"#f5c2e7",
         "cyan":"#94e2d5",
         "white":"#bac2de",
         "brightBlack":"#585b70",
         "brightRed":"#f38ba8",
         "brightGreen":"#a6e3a1",
         "brightYellow":"#f9e2af",
         "brightBlue":"#89b4fa",
         "brightMagenta":"#f5c2e7",
         "brightCyan":"#94e2d5",
         "brightWhite":"#a6adc8"
       }' \
       -t fontSize=14 \
       -t "fontFamily=Berkeley Mono Nerd Font" \
       -t cursorStyle=bar \
       -t cursorBlink=true \
       /bin/zsh
  ```
- Verify: open `http://mac-mini:7681` from another device on tailnet

### 1c. Caddy Reverse Proxy

Caddy sits in front, serving the HTML wrapper at `/` and proxying `/ttyd` to the ttyd backend.
This gives us a single URL, automatic HTTPS via Tailscale certs, and a clean setup.

- Install Caddy: `brew install caddy`
- Caddyfile:
  ```
  http://mac-mini {
      handle /ttyd/* {
          reverse_proxy localhost:7681
      }
      handle {
          root * /home/user/.roost/web
          file_server
      }
  }
  ```
- Optional: use `tailscale cert` + Caddy's TLS config for HTTPS
- Set up as a launchd service (macOS) for auto-start on boot

### 1d. gh CLI + Copilot

- Install `gh` CLI on the Mac Mini: `brew install gh`
- Run `gh auth login` to authenticate
- Install Copilot extension: `gh extension install github/gh-copilot`
- Verify: `gh copilot suggest "list files"` works
- Copy over any relevant shell config (.zshrc, .bashrc, aliases, env vars, starship config)

### 1e. Systemd / launchd Services

Create launchd plist files (macOS) so everything auto-starts on boot:

- **ttyd.plist** — runs ttyd with the full theme config
- **caddy.plist** — runs Caddy with the Caddyfile
- Both should restart on failure
- Both should start at boot

If Docker is preferred, create a `docker-compose.yml` with:
- ttyd container (with gh CLI, copilot, shell config, font file mounted in)
- Caddy container (with Caddyfile and web assets mounted in)
- Shared volume for `~/.roost/` (DB, logs, fonts, web assets)

---

## Phase 2 — Logging Wrapper

### Overview

A transparent shell wrapper that intercepts all `gh copilot` interactions and logs them to SQLite. The user's workflow doesn't change at all — they just use `gh copilot` as normal. If the logging layer fails, `gh copilot` still works — the wrapper must never block the real command.

### 2a. Project Structure

```
~/.roost/
├── assets/
│   └── fonts/
│       └── BerkeleyMonoNerdFont.woff2  # Licensed, Nerd-patched Berkeley Mono
├── bin/
│   ├── copilot-wrap          # Shell wrapper that intercepts gh copilot
│   └── copilot-history       # CLI tool to search/browse history
├── lib/
│   └── logger.sh             # Logging functions (write to SQLite)
├── db/
│   └── history.db            # SQLite database
├── logs/
│   └── raw/                  # Raw terminal captures via `script` command
├── web/
│   ├── index.html            # HTML wrapper (toolbar, font loading, reconnect overlay)
│   └── history.html          # Optional: web-based history viewer
├── services/
│   ├── ttyd.plist            # launchd service for ttyd
│   ├── caddy.plist           # launchd service for Caddy
│   └── Caddyfile             # Caddy configuration
├── docker-compose.yml        # Alternative: Docker-based setup
└── install.sh                # One-command setup script
```

### 2b. SQLite Schema

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,    -- UUID
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    cwd TEXT,                           -- Working directory at session start
    device TEXT                         -- Tailscale hostname / device identifier
);

CREATE TABLE interactions (
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

CREATE INDEX idx_interactions_timestamp ON interactions(timestamp);
CREATE INDEX idx_interactions_subcommand ON interactions(subcommand);
CREATE INDEX idx_interactions_prompt ON interactions(prompt);

-- Full-text search on prompts and responses
CREATE VIRTUAL TABLE interactions_fts USING fts5(
    prompt,
    response,
    content='interactions',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER interactions_ai AFTER INSERT ON interactions BEGIN
    INSERT INTO interactions_fts(rowid, prompt, response)
    VALUES (new.id, new.prompt, new.response);
END;

CREATE TRIGGER interactions_ad AFTER DELETE ON interactions BEGIN
    INSERT INTO interactions_fts(interactions_fts, rowid, prompt, response)
    VALUES('delete', old.id, old.prompt, old.response);
END;
```

### 2c. copilot-wrap — The Shell Wrapper

This is the core piece. It needs to:

1. Detect when `gh copilot` is invoked (via shell alias or PATH override)
2. Capture the subcommand and arguments
3. Run the real `gh copilot` command, capturing stdout/stderr
4. Parse out the prompt and response
5. Log everything to SQLite
6. Pass output through to the user transparently (real-time, not buffered)
7. **NEVER block the real command** — if logging fails, gh copilot still runs normally

**Implementation approach:**
- Use a shell function that overrides `gh` (only intercepts `gh copilot *`, passes everything else through)
- Use `script` command to capture interactive output while still displaying it live
- For non-interactive usage (`gh copilot suggest -t shell "list files"`), simple tee-based capture works
- For interactive usage (where Copilot prompts for clarification), `script` captures the full PTY

**Key challenge:** `gh copilot` uses interactive prompts (arrow-key selection, follow-up questions).
The `script` command captures everything including ANSI escape sequences. A post-processor strips
ANSI codes and extracts prompt/response pairs from the raw capture.

**Fallback plan:** If `script`-based parsing proves too fragile for structured logging, upgrade to a
small Go binary that acts as a PTY proxy with cleaner output capture. The raw `script` logs are
still valuable even before parsing is perfect.

### 2d. copilot-history — Search CLI

A bash + sqlite3 CLI tool (zero dependencies beyond sqlite3) that queries the history database.

```
Usage:
  copilot-history                      # Show last 20 interactions
  copilot-history search <query>       # Full-text search across prompts & responses
  copilot-history show <id>            # Show full detail of one interaction
  copilot-history today                # Today's interactions
  copilot-history device <name>        # Filter by device
  copilot-history stats                # Summary stats (count by subcommand, etc.)
  copilot-history export [--json]      # Export history
```

### 2e. install.sh — One-Command Setup

The installer should:

1. Create the `~/.roost/` directory structure
2. Initialize the SQLite database with the schema
3. Copy binaries to `~/.roost/bin/`
4. Add the shell integration to `.zshrc` / `.bashrc`:
   - Source the `gh` wrapper function
   - Add `~/.roost/bin/` to PATH
5. Verify `gh copilot` is installed and authenticated
6. Verify Berkeley Mono Nerd Font .woff2 exists in assets/fonts/
7. Install launchd services (or docker-compose) for ttyd + Caddy
8. Run a test interaction to confirm logging works

---

## Phase 3 — Mobile UX Polish (lessons from Termius)

Termius nails the mobile terminal experience. We steal their best ideas and build them
into the HTML wrapper that sits in front of ttyd.

### 3a. HTML Wrapper — The Main UI

A single `index.html` that:
- Loads Berkeley Mono Nerd Font via `@font-face` from `/assets/fonts/`
- Pulls Tailwind CSS from CDN
- Embeds ttyd in an iframe (or connects via ttyd's WebSocket directly)
- Adds the mobile keyboard toolbar (3b)
- Adds the reconnect overlay (3e)
- Adds the clipboard buttons (3f)
- Uses Catppuccin Mocha palette for all UI chrome
- Is fully responsive: adapts from phone (toolbar visible, larger touch targets)
  to desktop (toolbar hidden, full-width terminal)
- Design should feel native and polished:
  - `backdrop-blur` on toolbar for glassy effect
  - Smooth transitions on toolbar show/hide
  - Rounded corners (`rounded-lg`, `rounded-xl`)
  - Subtle borders using Surface2
  - Focus rings using Mauve

### 3b. Extra Keyboard Row (critical for mobile)

The iOS/Android keyboard lacks Ctrl, Tab, Esc, arrow keys, pipe, etc.
A fixed toolbar at the bottom of the screen with touch-friendly buttons:

- **Row 1:** Esc, Tab, Ctrl, Alt, `|`, `-`, `/`, `~`
- **Row 2:** Arrow keys (◀ ▲ ▼ ▶), plus common combos (Ctrl+C, Ctrl+D, Ctrl+R)
- Buttons inject keystrokes into ttyd via its WebSocket API or xterm.js input
- Buttons should be:
  - Sized for thumb reach (min 44px touch target)
  - Styled with Surface0 bg, Surface1 hover, Text color labels
  - Subtle press animation (scale down on touch)
- Ctrl should act as a toggle (tap to activate, tap again to deactivate)
  with a visual indicator (Blue highlight when active)
- Toolbar is sticky at the bottom on mobile, hidden on desktop via `@media` query
- Swipe-up gesture to toggle toolbar visibility on mobile

### 3c. Touch Gestures

- Swipe left/right on terminal for command history (maps to up/down arrow)
- Pinch to zoom for font size adjustment (ttyd supports dynamic font size via xterm.js)
- Implement via JavaScript touch event handlers in the HTML wrapper

### 3d. Theming & Font

- Berkeley Mono Nerd Font loaded via @font-face from `~/.roost/assets/fonts/`
- ttyd's xterm.js configured with Catppuccin Mocha theme (see 1b for full config)
- The HTML wrapper UI matches: Mantle bg toolbar, Surface0 buttons, Text labels
- Test on mobile: ensure font size is readable without zooming (14-16px is usually right)
- Match the terminal theme to your shell prompt (starship, oh-my-posh, etc.)
  — consider including a starship.toml that uses Catppuccin Mocha colors

### 3e. Auto-Reconnect & Session Resilience

- ttyd's `--reconnect 5` handles the backend reconnection
- The HTML wrapper should show a styled overlay when connection drops:
  - Peach colored "Reconnecting..." text with a subtle pulse animation
  - Backdrop blur over the terminal
  - Auto-dismiss when connection is restored
- Small connection indicator in the toolbar:
  - Green dot (Green `#a6e3a1`) = connected
  - Pulsing Peach dot (`#fab387`) = reconnecting
  - Red dot (Red `#f38ba8`) = disconnected

### 3f. Clipboard (Copy/Paste)

Browser-based terminals on mobile have awkward clipboard behavior. Add explicit buttons:

- **Copy button** in the toolbar: copies the current terminal selection to clipboard
- **Paste button** in the toolbar: reads clipboard and sends content to ttyd
- Use the Clipboard API (`navigator.clipboard.readText()` / `writeText()`)
- Visual feedback on copy (brief Green flash) and paste (brief Blue flash)
- On desktop, these hide since Cmd+C/Cmd+V work natively

### 3g. Responsive Layout

The wrapper should feel right at every screen size:

- **Phone (< 640px):** Terminal fills viewport above toolbar, toolbar is fixed at bottom,
  larger font size (15-16px), toolbar keys are full-width
- **Tablet (640-1024px):** Terminal fills most of viewport, toolbar is more compact,
  consider side panel for history search
- **Desktop (> 1024px):** Terminal fills viewport, toolbar hidden entirely,
  optional floating history panel

### 3h. Device Identification

- Auto-detect device name from Tailscale hostname or `$HOSTNAME`
- Log which device each interaction came from
- `copilot-history` can filter by device

### 3i. Web History Viewer (stretch goal)

- A `history.html` page in the web directory
- Reads from SQLite via a tiny API endpoint served by a small script
  (could be a Python Flask one-liner, a Go binary, or a Caddy CGI script)
- Searchable, filterable by date/subcommand/device
- Styled with Tailwind + Catppuccin Mocha to match the terminal wrapper
- Accessible via Tailscale at `http://mac-mini/history`

### 3j. Backup & Sync

- SQLite DB is a single file — easy to back up
- Optional: cron job to back up `history.db` to git or cloud storage
- Optional: export to JSON for portability

---

## Implementation Order

1. **Phase 1a** — Install Tailscale on Mac Mini + all devices, verify connectivity
2. **Phase 1b** — Install ttyd, run with Catppuccin Mocha theme, verify from phone browser
3. **Phase 1d** — Install gh CLI + Copilot on Mac Mini, verify it works
4. **Phase 2b** — Create the SQLite schema and test it manually
5. **Phase 2c** — Build the wrapper script (start with `script`-based capture)
6. **Phase 2e** — Build the installer
7. **Phase 2d** — Build the history CLI
8. **Phase 3a-3g** — Build the HTML wrapper with toolbar, reconnect, clipboard, responsive layout
9. **Phase 1c** — Set up Caddy to serve wrapper + proxy ttyd
10. **Phase 1e** — Create launchd services (or docker-compose) for auto-start
11. **Test end-to-end** from phone, laptop, and desktop
12. **Phase 3i** — Web history viewer (stretch goal)

## Tech Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Host machine | Mac Mini (Docker optional) | Already owned, always on, local |
| Fallback host | DigitalOcean VPS | If Mac Mini has uptime issues |
| Storage | SQLite + FTS5 | Single file, no server, full-text search built in |
| Wrapper language | Bash (with Go fallback for PTY) | Minimal dependencies, shell-native |
| History CLI | Bash + sqlite3 | Zero dependencies beyond sqlite3 |
| Capture method | `script` command first, Go PTY proxy if needed | Start simple, upgrade if capture quality insufficient |
| Remote access | Tailscale (no passwords) | Mesh VPN, mobile apps for iOS/Android, zero config |
| Web terminal | ttyd | Single binary, just a terminal, lightweight |
| Reverse proxy | Caddy | Auto HTTPS, simple config, serves static files too |
| Wrapper CSS | Tailwind CSS (CDN) | Utility-first, fast to build responsive UI |
| Theme | Catppuccin Mocha | Consistent palette across terminal + UI |
| Font | Berkeley Mono Nerd Font | Licensed, Nerd glyph support, beautiful |

## Success Criteria

- [ ] `gh copilot suggest "list large files"` on any device hits the Mac Mini and works identically
- [ ] Every interaction is logged with timestamp, prompt, response, cwd, device
- [ ] `copilot-history search "docker"` returns all past Docker-related interactions
- [ ] Phone browser shows a polished terminal with Catppuccin Mocha theme and Berkeley Mono font
- [ ] Mobile keyboard toolbar provides Esc, Ctrl, Tab, arrows — `gh copilot` interactive menus are usable on phone
- [ ] Copy/paste works reliably on mobile via toolbar buttons
- [ ] Layout adapts cleanly from phone → tablet → desktop
- [ ] Auto-reconnect works when switching apps on phone or losing connection briefly
- [ ] If the logging layer breaks, `gh copilot` still works normally
- [ ] Everything auto-starts on Mac Mini boot