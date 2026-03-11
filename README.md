<div align="center">
  <img src="assets/glade_logo.png" width="140" alt="Glade">
  <h1>Glade</h1>
  <p>A self-hosted terminal that lives on your server and runs on every device.</p>

  [![License: MIT](https://img.shields.io/badge/License-MIT-cba6f7.svg?style=flat-square&labelColor=313244)](LICENSE)
  [![Docker](https://img.shields.io/badge/Docker-ready-89b4fa.svg?style=flat-square&labelColor=313244&logo=docker&logoColor=89b4fa)](docker-compose.yml)
  [![Python](https://img.shields.io/badge/API-Python_stdlib-a6e3a1.svg?style=flat-square&labelColor=313244&logo=python&logoColor=a6e3a1)](api/api.py)
  [![PWA](https://img.shields.io/badge/PWA-installable-fab387.svg?style=flat-square&labelColor=313244)](web/manifest.json)
</div>

---

Your terminal is open on your phone. The session is alive on your server. Close the browser — it keeps running. Open it on your laptop — same session, same history, same scrollback. That's Glade.

It runs on a Mac Mini or any always-on host inside Docker. Reach it from anywhere: on LAN through Caddy, remotely through Tailscale. No subscriptions. No cloud. Nothing leaves your machine.

---

## Quick Start

```bash
git clone https://github.com/mattsimonis/glade
cd glade
cp .env.example .env   # set HOST= to your server's hostname
```

Add the `glade.local` block from `services/Caddyfile` to your standalone `caddy-proxy` and generate a cert:

```bash
mkcert glade.local
# move cert files into your Caddy certs directory, restart caddy-proxy
```

Then:

```bash
make setup   # builds image (~2 min) and starts containers
```

Open `https://glade.local`. Tap **Share → Add to Home Screen** to install the PWA.

> `glade.local` resolves automatically via mDNS — no Pi-hole or extra DNS config needed.  
> Tailscale is optional — only needed for remote access outside your home network.  
> See [SETUP.md](SETUP.md) for the full walkthrough.

---

## Features

- **Persistent sessions** — tmux keeps every session alive on the server; close and reopen from any device
- **Installable PWA** — Add to Home Screen on iOS or Android; full-screen, no browser chrome
- **Custom mobile keyboard** — Esc, Tab, Ctrl, arrows, combos; long-press to repeat; drag to reorder
- **Project isolation** — each project gets its own tmux session and ttyd instance; multiple shell tabs per project
- **Session logging** — every session recorded automatically via `tmux pipe-pane`; browse and search from History tab
- **Command snippets** — saved commands that inject directly into the terminal with one tap
- **Command palette** — keyboard-accessible actions: `^C`, `^Z`, `^A`, new shell, history, snippets, and more
- **Auto-reconnect** — recovers from network drops and app backgrounding automatically
- **In-app rebuild** — queue a `git pull && docker compose build` from the UI; no SSH needed
- **Catppuccin Mocha** — consistent theme across terminal, UI, and toolbar

---

## Why Glade?

Most mobile terminal apps drop your session, cost money, or only work on one platform. Glade runs *on your server* — the session lives there, and any browser is just a window into it.

|  | **Glade** | Termius | Blink Shell | JuiceSSH | Raw SSH |
|---|---|---|---|---|---|
| Self-hosted | ✅ | ❌ | ❌ | ❌ | ✅ |
| Free | ✅ MIT | Freemium | $20 | Freemium | ✅ |
| Any device | ✅ browser | ✅ | iOS only | Android only | With client |
| Persistent sessions | ✅ tmux | ❌ | ❌ | ❌ | With tmux |
| Custom mobile keyboard | ✅ | ❌ | Limited | ❌ | ❌ |
| Session recording | ✅ | ❌ | ❌ | ❌ | ❌ |
| No cloud | ✅ | ❌ | ❌ | ❌ | ✅ |

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Always-on host (Mac Mini, Linux server) | Docker runs here |
| Docker Desktop | Container runtime |
| Standalone `caddy-proxy` container | Handles TLS for `*.local` domains |
| Tailscale *(optional)* | Remote access outside the home network |
| Berkeley Mono Nerd Font `.woff2` *(optional)* | Licensed; supply your own |

---

## Configuration

Copy `.env.example` to `.env` and edit:

```bash
HOST=mac-mini      # hostname of the machine running Docker
DOMAIN=glade.local # domain for the web UI
```

Optional environment variables:

| Variable | Default | Description |
|---|---|---|
| `GLADE_REPO_URL` | `https://github.com/mattsimonis/glade.git` | Override if using a fork |
| `GLADE_DIR` | `~/.glade` | Where Glade stores its DB, logs, and uploads |
| `DISABLE_UPDATE_CHECK` | _(unset)_ | Set to `1` to suppress the update-available banner |

To mount personal directories inside the container, create a gitignored `docker-compose.override.yml`:

```yaml
services:
  ttyd:
    volumes:
      - /your/dev/dir:/mnt/dev
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The test suite runs with `make test`.
