# Glade — Setup Guide

> **DNS is automatic.** `glade.local` resolves via mDNS on macOS, iOS, and Linux — no Pi-hole needed.  
> **Tailscale is optional** — required only for remote access outside your home network. Start without it.

---

## Prerequisites

- Mac Mini is on and connected to your network
- You have admin access to the Mac Mini (SSH or local keyboard)
- Docker Desktop installed

---

## Step 1: Install Dependencies on Mac Mini

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Core tools
brew install sqlite3 git
```

---

## Step 2: Clone the Project to Mac Mini

SSH into the Mac Mini from your laptop:
```bash
ssh mac-mini
```

Then clone the repo:
```bash
git clone https://github.com/mattsimonis/glade ~/Dev/glade
cd ~/Dev/glade
```

> Already have the project folder on your laptop? Copy it over SMB into a convenient path (e.g. `/Volumes/Photos/Dev/glade`) and `cd` into that directory instead.

---

## Step 3: Configure

```bash
cp .env.example .env
```

Edit `.env`:
```bash
HOST=mac-mini      # hostname of the machine running Docker
DOMAIN=glade.local # domain you'll use to access the UI
```

To mount personal directories (e.g. your code) inside the container, create a gitignored `docker-compose.override.yml`:

```yaml
services:
  ttyd:
    volumes:
      - /your/dev/dir:/mnt/dev
```

---

## Step 4: Run the Installer

```bash
./install.sh
```

This will:
- Create `~/.glade/` with all subdirectories
- Copy scripts, schema, and config files into place
- Initialize the SQLite database
- Add shell integration to your `.zshrc` and `.bashrc`
- Print warnings for anything missing

Restart your shell:
```bash
source ~/.zshrc
```

---

## Step 5: Add Your Font (Optional)

Copy the Regular Nerd Font variant into place:

```bash
cp BerkeleyMonoNerdFont-Regular.ttf ~/.glade/assets/fonts/
```

The filename must start with `BerkeleyMonoNerdFont-Regular` — that's what the `@font-face` declaration expects. If yours is named differently, rename it.

If you skip this, the UI falls back to JetBrains Mono → Fira Code → system monospace.

---

## Step 6: Set Up TLS — mkcert cert

On the machine where `caddy-proxy` is managed:

```bash
mkcert glade.local
mv glade.local.pem       /path/to/caddy/certs/glade.local.pem
mv glade.local-key.pem   /path/to/caddy/certs/glade.local-key.pem
```

If `mkcert` isn't installed: `brew install mkcert && mkcert -install`

---

## Step 7: Add glade.local to Your Standalone Caddy

Copy the contents of `services/Caddyfile` (the `glade.local` block) into your Caddy project's `Caddyfile`, then restart:

```bash
docker restart caddy-proxy
```

---

## Step 8: Start Services

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

## Step 9: Verify from the Mac Mini Itself

```bash
# Open a browser on the Mac Mini and go to https://glade.local
# You should see the Glade web UI with project cards and a terminal
```

Also verify the API:
```bash
curl -s http://localhost:7683/api/health | python3 -m json.tool
```

---

## Step 10: Connect from Your Laptop

1. Make sure you're on the same network
2. Open a browser
3. Go to: `https://glade.local`
4. First visit: run `mkcert -install` on the laptop to trust the local CA (avoids cert warning)
5. You should see the terminal UI with Catppuccin Mocha theme
6. Create a project and run a command — it executes on the Mac Mini

---

## Step 11: Connect from Your Phone

1. Make sure you're on the same network
2. Open Safari (iOS) or Chrome (Android)
3. Go to: `https://glade.local`
4. The terminal loads with the mobile keyboard toolbar at the bottom
5. Use the extra keys (Esc, Tab, Ctrl, arrows) to navigate interactive menus
6. Copy/Paste buttons are in the toolbar

**Tip:** On iOS, tap "Share → Add to Home Screen" to make it feel like a native app (full screen, no browser chrome).

On iOS: to avoid cert warnings, import the mkcert root CA profile → Settings → General → VPN & Device Management → trust it.

---

## Step 12: Make It Survive Reboots

The `docker-compose.yml` already has `restart: unless-stopped`, so Docker handles this as long as Docker Desktop is set to start at login:

**Docker Desktop → Settings → General → "Start Docker Desktop when you sign in"**

`caddy-proxy` handles itself the same way.

---

## Optional: Tailscale (Remote Access)

Skip this entirely if you only need LAN access. Add it later when you want to reach Glade from outside the home network.

**Mac Mini:**
```bash
brew install tailscale
```
Then open System Settings → Tailscale → Sign in.

**Laptop:** Download from [tailscale.com/download](https://tailscale.com/download). Sign in with the same account.

**Phone:**
- iOS: App Store → "Tailscale" → Install → Sign in
- Android: Google Play → "Tailscale" → Install → Sign in

**Verify:** On the Mac Mini:
```bash
tailscale status
```
You should see all your devices listed.

**Enable MagicDNS:** Go to [login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns) and enable MagicDNS so you can use `glade.local` over Tailscale instead of an IP.

Once connected, `https://glade.local` works from anywhere your Tailscale devices can reach the Mac Mini.

---

## Optional: Pi-hole DNS

`glade.local` resolves automatically via mDNS on macOS, iOS, and modern Linux. **You do not need Pi-hole.**

If you already run Pi-hole and want an explicit DNS entry (e.g. for devices that don't support mDNS), add a record:

1. Open Pi-hole admin → **Local DNS** → **DNS Records**
2. Add:
   - **Domain:** `glade.local`
   - **IP Address:** Mac Mini's LAN IP (find it with `ipconfig getifaddr en0`)
3. Click **Add**

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Can't reach `https://glade.local` | Try `ping glade.local` — mDNS should resolve it automatically. If not, check `caddy-proxy` is running: `docker ps`. Try the Mac Mini's LAN IP directly. |
| Browser shows cert warning | Run `mkcert -install` on the client device to trust the local CA. |
| Terminal shows but no input works | Make sure ttyd is running with `--writable` flag |
| Docker first build is slow | Normal — building the image. Watch with `docker compose logs -f ttyd` |
| Phone keyboard covers terminal | The toolbar should push the terminal up. If not, try "Add to Home Screen" for full-screen mode |
| History not logging | Session logs are recorded via tmux pipe-pane. Check `ls ~/.glade/logs/` for files. Create a project and run a command to start recording. |
