# Glade — Setup Guide

> **DNS requires a local DNS entry.** `glade.local` does not resolve via mDNS automatically — mDNS only resolves the machine's own hostname. Add an A record in Pi-hole, or an `/etc/hosts` entry on each client, pointing your chosen domain to your host's LAN IP.  
> **Tailscale is optional** — required only for remote access outside your home network. Start without it.

---

## Prerequisites

- An always-on host connected to your network (Mac Mini, Raspberry Pi, Linux server, or Windows PC)
- Admin access to the host (SSH or local keyboard)
- Docker installed on the host

---

## Step 1: Install Docker

**macOS:**
```bash
# Install Docker Desktop from https://www.docker.com/products/docker-desktop/
# Then: brew install git   (if not already installed)
```

**Linux / Raspberry Pi (Debian/Ubuntu):**
```bash
sudo apt update && sudo apt install -y git curl
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # log out and back in after this
```
> ARM is fully supported — the image builds for armhf, arm64, and amd64.

**Windows:**
```powershell
winget install Git.Git Docker.DockerDesktop
```
> Docker Desktop requires WSL2. Run `wsl --install` and reboot before installing Docker.

---

## Step 2: Clone the Project

SSH into the host from your laptop (or run directly if you have a display):
```bash
git clone https://github.com/mattsimonis/glade-sh ~/Dev/glade
cd ~/Dev/glade
```

---

## Step 3: Configure

```bash
cp .env.example .env
```

Edit `.env`:
```bash
HOST=your-hostname  # hostname of the machine running Docker
DOMAIN=glade.local  # domain you'll use to access the UI
```

To mount personal directories inside the container, create a gitignored `docker-compose.override.yml`:

```yaml
services:
  ttyd:
    volumes:
      - /your/dev/dir:/mnt/dev
```

---

## Step 4: Add Your Font (Optional)

Copy the Regular Nerd Font variant into place:

```bash
cp BerkeleyMonoNerdFont-Regular.ttf ~/.glade/assets/fonts/
```

The filename must start with `BerkeleyMonoNerdFont-Regular`. If yours is named differently, rename it.

If you skip this, the UI falls back to JetBrains Mono → Fira Code → system monospace.

---

## Step 5: Set Up TLS — mkcert cert

Install mkcert on the machine where `caddy-proxy` is managed:

| Platform | Command |
|---|---|
| macOS | `brew install mkcert && mkcert -install` |
| Linux / Raspberry Pi | `sudo apt install mkcert` or download from [github.com/FiloSottile/mkcert/releases](https://github.com/FiloSottile/mkcert/releases) |
| Windows | `winget install FiloSottile.mkcert` then `mkcert -install` |

Then generate the cert:
```bash
mkcert glade.local
mv glade.local.pem       /path/to/caddy/certs/glade.local.pem
mv glade.local-key.pem   /path/to/caddy/certs/glade.local-key.pem
```

---

## Step 6: Add glade.local to Your Standalone Caddy

Copy the `glade.local` block from `services/Caddyfile` into your Caddy project's `Caddyfile`, then restart:

```bash
docker restart caddy-proxy
```

---

## Step 7: Start Services

```bash
cd ~/Dev/glade
make setup
```

This creates the Docker network, builds the image, and starts everything. First build takes ~2 minutes. Subsequent starts are instant.

Watch the build: `docker compose logs -f`

To rebuild after `Dockerfile` or `entrypoint.sh` changes:
```bash
make build
```

---

## Step 8: Verify

```bash
curl -s http://localhost:7683/api/health | python3 -m json.tool
```

Then open `https://glade.local` in a browser on the host to confirm the UI loads.

---

## Step 9: Connect from Your Laptop

1. Make sure you're on the same network
2. Go to `https://glade.local` in a browser
3. First visit: run `mkcert -install` on the laptop to trust the local CA (avoids cert warning)
4. Create a project and run a command — it executes on the host

---

## Step 10: Connect from Your Phone

1. Make sure you're on the same network
2. Open Safari (iOS) or Chrome (Android) → `https://glade.local`
3. The terminal loads with the mobile keyboard toolbar at the bottom

**Tip:** On iOS, tap "Share → Add to Home Screen" for full-screen mode with no browser chrome.

To avoid cert warnings on iOS: import the mkcert root CA profile → Settings → General → VPN & Device Management → trust it.

---

## Step 11: Make It Survive Reboots

`docker-compose.yml` uses `restart: unless-stopped`, so containers restart automatically as long as Docker starts at boot.

**Docker Desktop (macOS / Windows):** Settings → General → "Start Docker Desktop when you sign in"

**Linux / Raspberry Pi (Docker Engine):**
```bash
sudo systemctl enable docker
```
Docker Engine starts at boot by default after `get.docker.com` install.

---

## Optional: Tailscale (Remote Access)

Skip this if you only need LAN access.

**Host:**

| Platform | Command |
|---|---|
| macOS | `brew install tailscale` then open System Settings → Tailscale → Sign in |
| Linux / Raspberry Pi | `curl -fsSL https://tailscale.com/install.sh \| sh` then `sudo tailscale up` |
| Windows | Download from [tailscale.com/download](https://tailscale.com/download) |

**Laptop / Phone:** Download Tailscale from [tailscale.com/download](https://tailscale.com/download) and sign in with the same account.

Verify on the host:
```bash
tailscale status
```

**Enable MagicDNS:** Go to [login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns) → enable MagicDNS so you can reach the host by hostname over Tailscale.

---

## Pi-hole DNS (Required for `glade.local`)

`glade.local` is not your machine's hostname, so it won't resolve automatically. Add an A record:

1. Open Pi-hole admin → **Local DNS** → **DNS Records**
2. Add:
   - **Domain:** `glade.local`
   - **IP Address:** your host's LAN IP

Find your host's LAN IP:

| Platform | Command |
|---|---|
| macOS | `ipconfig getifaddr en0` |
| Linux / Raspberry Pi | `hostname -I \| awk '{print $1}'` |
| Windows | `ipconfig` → IPv4 Address under your network adapter |

---

## Optional: GitHub Integration

Glade includes a `gh` CLI and can connect to your GitHub account. This is entirely optional — local projects work without it.

**What it enables:**
- Create projects directly from a GitHub repo (clone happens automatically)
- Use `gh` commands, `gh copilot`, and authenticated git operations inside the terminal

**One-time setup:** `docker-compose.yml` mounts `~/.config/gh` from the host by default — auth persists across container restarts.

**To connect:**
1. Open the Glade UI → tap the ⚙️ icon → **Settings**
2. Scroll to the **GitHub** section
3. Tap **Connect** — a device code appears
4. Open [github.com/login/device](https://github.com/login/device), enter the code
5. Done — your username and avatar appear in Settings

**To create a project from a GitHub repo:**
1. Tap **New Project** → toggle the source to **GitHub Repo**
2. Search for a repo, select it, tap Create
3. Glade clones the repo to `~/.glade/projects/{slug}` and opens a terminal in it

If you tap "GitHub Repo" without being connected, the auth flow starts automatically.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Can't reach `https://glade.local` | Check that Pi-hole (or `/etc/hosts`) has an A record for `glade.local` pointing to your host's LAN IP. Check `caddy-proxy` is running: `docker ps`. Try the IP directly to isolate DNS from routing. |
| Browser shows cert warning | Run `mkcert -install` on the client device to trust the local CA. |
| Terminal shows but no input works | Make sure ttyd is running with `--writable` flag |
| Docker first build is slow | Normal — first build takes ~2 min. Watch with `docker compose logs -f ttyd` |
| Phone keyboard covers terminal | The toolbar should push the terminal up. Try "Add to Home Screen" for full-screen mode. |
| History not logging | Check `ls ~/.glade/logs/` for files. Create a project and run a command to start recording. |

