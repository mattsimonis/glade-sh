# Copilot Sync — Setup Guide

## Prerequisites

- Mac Mini is on and connected to your network
- You have admin access to the Mac Mini (SSH or local keyboard)
- A GitHub account with Copilot access

---

## Step 1: Install Tailscale on All Devices

**Mac Mini:**
```bash
brew install tailscale
```
Then open System Settings → Tailscale → Sign in with your account.

**Laptop:**
Download from [tailscale.com/download](https://tailscale.com/download) for your OS. Sign in with the same account.

**Phone:**
- iOS: App Store → "Tailscale" → Install → Sign in
- Android: Google Play → "Tailscale" → Install → Sign in

**Verify:** On the Mac Mini, run:
```bash
tailscale status
```
You should see all your devices listed. Note the Mac Mini's Tailscale hostname (e.g., `mac-mini`).

**Enable MagicDNS:** Go to [login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns) and enable MagicDNS so you can use hostnames instead of IPs.

---

## Step 2: Install Dependencies on Mac Mini

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Core tools
brew install gh sqlite3 git

# GitHub CLI auth
gh auth login
# Follow the prompts — choose GitHub.com, HTTPS, browser login

# Copilot extension
gh extension install github/gh-copilot

# Verify
gh copilot suggest "list files in current directory"
```

---

## Step 3: Copy the Project to Mac Mini

Copy the `copilot-sync` folder to the Mac Mini over SMB into `/Volumes/Photos/Dev/copilot-sync`.

---

## Step 4: Run the Installer on Mac Mini

SSH into the Mac Mini from your laptop:
```bash
ssh mac-mini
```

Then run:
```bash
cd /Volumes/Photos/Dev/copilot-sync
./install.sh
```

This will:
- Create `~/.copilot-sync/` with all subdirectories
- Copy scripts, schema, web files into place
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
cp BerkeleyMonoNerdFont-Regular.ttf ~/.copilot-sync/assets/fonts/
```

The filename must start with `BerkeleyMonoNerdFont-Regular` — that's what the `@font-face` declaration expects. If yours is named differently, rename it.

If you skip this, the UI falls back to JetBrains Mono / Fira Code / system monospace.

---

## Step 6: Set Up Pi-hole DNS for ai.home

On the machine running Pi-hole, add a local DNS record:

1. Open Pi-hole admin → **Local DNS** → **DNS Records**
2. Add:
   - **Domain:** `ai.home`
   - **IP Address:** Mac Mini's LAN IP (find it with `ipconfig getifaddr en0`)
3. Click **Add**

Verify from any device on the network:
```bash
ping ai.home
```

---

## Step 7: Add ai.home to Your Standalone Caddy

Copy the contents of `services/Caddyfile` (the `ai.home` block) into your Caddy project's `Caddyfile`, then generate a TLS cert with `mkcert` using the same CA already installed for `fizzy.home` and `yoto.home`:

```bash
cd /Volumes/Photos/Dev/caddy
mkcert ai.home
mv ai.home.pem certs/ai.home.pem
mv ai.home-key.pem certs/ai.home-key.pem

docker restart caddy-proxy
```

If `mkcert` isn't installed: `brew install mkcert && mkcert -install`

---

## Step 8: Start Services

**Docker (the only option — Caddy is handled by your standalone `caddy-proxy`):**

```bash
cd /Volumes/Photos/Dev/copilot-sync
docker compose up -d
```

First build takes ~2 minutes (installs packages into the image). Subsequent starts are instant.
Watch the build: `docker compose logs -f`

To rebuild after `Dockerfile` or `entrypoint.sh` changes:
```bash
docker compose build ttyd && docker compose up -d
```

**Native (no Docker) — ttyd only:**

```bash
brew install ttyd

ttyd --port 7681 --writable --reconnect 5 --max-clients 3 \
  -t 'theme={"background":"#1e1e2e","foreground":"#cdd6f4","cursor":"#f5e0dc","cursorAccent":"#1e1e2e","selectionBackground":"#585b70","selectionForeground":"#cdd6f4","black":"#45475a","red":"#f38ba8","green":"#a6e3a1","yellow":"#f9e2af","blue":"#89b4fa","magenta":"#f5c2e7","cyan":"#94e2d5","white":"#bac2de","brightBlack":"#585b70","brightRed":"#f38ba8","brightGreen":"#a6e3a1","brightYellow":"#f9e2af","brightBlue":"#89b4fa","brightMagenta":"#f5c2e7","brightCyan":"#94e2d5","brightWhite":"#a6adc8"}' \
  -t fontSize=14 \
  -t 'fontFamily=Berkeley Mono Nerd Font,JetBrains Mono,Fira Code,monospace' \
  -t cursorStyle=bar -t cursorBlink=true /bin/zsh
```

For static asset serving, run in a second terminal:
```bash
cd ~/.copilot-sync && python3 -m http.server 7682
```

Point your standalone Caddy at `localhost:7681` and `localhost:7682` instead of the container names.

---

## Step 7: Verify from the Mac Mini Itself

```bash
# Test the wrapper logs correctly
gh copilot suggest "how to list docker containers"

# Check it was logged
copilot-history
```

Also open a browser on the Mac Mini and go to `https://ai.home` — you should see the Copilot Sync web UI with a terminal.

---

## Step 10: Connect from Your Laptop

1. Make sure you're on the same network (or Tailscale is connected)
2. Open a browser
3. Go to: `https://ai.home`
4. You should see the terminal UI with Catppuccin Mocha theme
5. Type `gh copilot suggest "something"` — it runs on the Mac Mini

---

## Step 11: Connect from Your Phone

1. Make sure you're on the same network (or Tailscale is connected)
2. Open Safari (iOS) or Chrome (Android)
3. Go to: `https://ai.home`
4. The terminal loads with the mobile keyboard toolbar at the bottom
5. Use the extra keys (Esc, Tab, Ctrl, arrows) to navigate `gh copilot` interactive menus
6. Copy/Paste buttons are in the toolbar's second row

**Tip:** On iOS, tap "Share → Add to Home Screen" to make it feel like a native app (full screen, no browser chrome).

---

## Step 12: Make It Survive Reboots

**If using Docker:**
The `docker-compose.yml` already has `restart: unless-stopped`, so Docker handles this as long as Docker Desktop is set to start at login (Docker Desktop → Settings → General → "Start Docker Desktop when you sign in"). `caddy-proxy` handles itself the same way.

**If running natively**, create a launchd plist for ttyd:

```bash
cat > ~/Library/LaunchAgents/com.copilot-sync.ttyd.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.copilot-sync.ttyd</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/ttyd</string>
        <string>--port</string><string>7681</string>
        <string>--writable</string>
        <string>--reconnect</string><string>5</string>
        <string>--max-clients</string><string>3</string>
        <string>/bin/zsh</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.copilot-sync.ttyd.plist
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Can't reach `https://ai.home` | Verify Pi-hole DNS record. Check `caddy-proxy` is running: `docker ps`. Try the Mac Mini's LAN IP directly. |
| Browser shows cert warning | Run `mkcert -install` on the client device to trust the local CA. |
| Terminal shows but no input works | Make sure ttyd is running with `--writable` flag |
| `gh copilot` not found in terminal | Run `gh extension install github/gh-copilot` inside the container/terminal |
| Docker first build is slow | Normal — building the image. Watch with `docker compose logs -f ttyd` |
| Phone keyboard covers terminal | The toolbar should push the terminal up. If not, try "Add to Home Screen" for full-screen mode |
| History not logging | Run `copilot-history` — if it says "No history database", run `source ~/.copilot-sync/bin/copilot-wrap` then try a `gh copilot` command |
