# Glade — Setup Guide

> **DNS setup required.** `glade.home` won't resolve automatically — see [Accessing Outside Your Local Network](#accessing-outside-your-local-network) to configure DNS so the same URL works on your LAN and remotely via Tailscale.

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
DOMAIN=glade.home  # domain you'll use to access the UI
```

To mount personal directories inside the container, create a gitignored `docker-compose.override.yml`:

```yaml
services:
  ttyd:
    volumes:
      - /your/dev/dir:/mnt/dev
```

---

## Step 4: Add a Custom Font (Optional)

Commit Mono ships as the default and requires no setup. To use a custom font, open the Glade UI → Settings → Font and drag-drop a `.woff2`, `.ttf`, or `.otf` file. The font is stored server-side and applied automatically on next load.

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
mkcert glade.home
mv glade.home.pem       /path/to/caddy/certs/glade.home.pem
mv glade.home-key.pem   /path/to/caddy/certs/glade.home-key.pem
```

---

## Step 6: Add glade.home to Your Standalone Caddy

Copy the `glade.home` block from `services/Caddyfile` into your Caddy project's `Caddyfile`, then restart:

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

Then open `https://glade.home` in a browser on the host to confirm the UI loads.

---

## Step 9: Connect from Your Laptop

1. Make sure you're on the same network (or connected via Tailscale)
2. Go to `https://glade.home` in a browser
3. First visit: run `mkcert -install` on the laptop to trust the local CA (avoids cert warning)
4. Create a project and run a command — it executes on the host

---

## Step 10: Connect from Your Phone

1. Make sure Tailscale is connected (on LAN or remotely)
2. Open Safari (iOS) or Chrome (Android) → `https://glade.home`
3. The terminal loads with the mobile keyboard toolbar at the bottom

**Tip:** On iOS, tap "Share → Add to Home Screen" for full-screen mode with no browser chrome.

To avoid cert warnings on iOS: import the mkcert root CA profile → Settings → General → VPN & Device Management → trust it.

> **PWA icon on iOS:** Installing the CA profile alone is not enough for the home screen icon. iOS background processes (SpringBoard) require *full trust* to fetch icons over your local HTTPS cert. Without it, Add to Home Screen and Add Bookmark show a "G" monogram instead of the icon — even though Safari browsing works fine. After installing the profile, go to **Settings → General → About → Certificate Trust Settings** and toggle the mkcert root CA on.

---

## Optional: Attach Directly via tmux

If you prefer using your own terminal app instead of the browser UI, you can attach directly to any Glade session. Sessions run inside the `glade-ttyd` container and are named `proj-{id}`, where `{id}` is the first 8 characters of the project's UUID.

From the host machine, list all active sessions:

```bash
docker exec -it glade-ttyd tmux list-sessions
```

Then attach to the one you want:

```bash
docker exec -it glade-ttyd tmux attach -t proj-<id>
```

If you're on another machine on the network, SSH to the host first:

```bash
ssh user@your-host
docker exec -it glade-ttyd tmux attach -t proj-<id>
```

Detach with the standard tmux keybinding (`Ctrl+b d`) — the session stays running and is still accessible from the Glade PWA.

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

## Accessing Outside Your Local Network

Tailscale connects your devices over a mesh VPN so Glade is reachable from anywhere — home, office, phone on mobile data. Install it on the Glade host, then on any client device you want to use remotely. On the local network, Tailscale is not required — `glade.home` resolves directly.

**Install Tailscale on the host:**

| Platform | Command |
|---|---|
| macOS | `brew install tailscale` then open System Settings → Tailscale → Sign in |
| Linux / Raspberry Pi | `curl -fsSL https://tailscale.com/install.sh \| sh` then `sudo tailscale up` |
| Windows | Download from [tailscale.com/download](https://tailscale.com/download) |

**Install Tailscale on remote clients:** Download from [tailscale.com/download](https://tailscale.com/download) and sign in with the same account. Only needed when accessing Glade outside your home network.

**Enable MagicDNS:** Go to [login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns) → enable MagicDNS.

Once Tailscale is set up on the host, `glade.home` needs a DNS record so every device can find it — with or without Tailscale running. Pick the guide that matches your setup:

| Setup | Guide |
|---|---|
| You have Pi-hole | [docs/remote-access-pihole.md](docs/remote-access-pihole.md) — one record, works for all devices; Tailscale optional on LAN, automatic when remote |
| No Pi-hole | [docs/remote-access-hosts-file.md](docs/remote-access-hosts-file.md) — add an entry to `/etc/hosts` on each device manually |

---

## Optional: GitHub Integration

Glade includes a `gh` CLI and can connect to your GitHub account. This is entirely optional — local projects work without it.

**What it enables:**
- Create projects directly from a GitHub repo (clone happens automatically)
- Use `gh` commands, `gh copilot`, and authenticated git operations inside the terminal

**One-time setup:** `docker-compose.yml` uses a named Docker volume (`gh-config`) for `gh` auth — it lives inside Docker, separate from the host's `~/.config/gh`, and persists across container restarts and rebuilds.

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
| Can't reach `https://glade.home` | Check Pi-hole has an A record for `glade.home` pointing to the host's **LAN IP** (`192.168.x.x`). Check Tailscale is running on the client. Check `caddy-proxy` is running: `docker ps`. Try the LAN IP directly to isolate DNS from routing. |
| `glade.home` works on LAN but not on mobile | Tailscale's **Override DNS servers** toggle must be enabled — [Tailscale admin → DNS](https://login.tailscale.com/admin/dns) → Global nameservers → enable it. Without this, iOS/Android ignore Pi-hole and use carrier DNS. |
| PWA icon is blank / shows letter monogram after adding to home screen | iOS background processes require *full trust* for local CA certs, not just a profile install. Go to **Settings → General → About → Certificate Trust Settings** and enable full trust for the mkcert root CA. Then remove and re-add the shortcut. |
| Browser shows cert warning | Run `mkcert -install` on the client device to trust the local CA. |
| Terminal shows but no input works | Make sure ttyd is running with `--writable` flag |
| Docker first build is slow | Normal — first build takes ~2 min. Watch with `docker compose logs -f ttyd` |
| Phone keyboard covers terminal | The toolbar should push the terminal up. Try "Add to Home Screen" for full-screen mode. |
| History not logging | Check `ls ~/.glade/logs/` for files. Create a project and run a command to start recording. |

