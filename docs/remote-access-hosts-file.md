# Remote Access — `/etc/hosts` Per Device

No Pi-hole or extra infrastructure needed. Add one line to `/etc/hosts` on each device. Works on the LAN without Tailscale, and remotely with Tailscale via subnet routing. The trade-off: you repeat the step on every new device, and phones require a workaround.

---

## How It Works

The `/etc/hosts` entry points `glade.home` at the Glade host's **LAN IP**. On the local network that resolves directly — no Tailscale needed. When you're away, Tailscale's subnet routing makes the same LAN IP reachable through the tunnel. Same URL, same IP, same PWA shortcut everywhere.

---

## Prerequisites

- Tailscale installed on the Glade host
- MagicDNS enabled in [Tailscale admin → DNS](https://login.tailscale.com/admin/dns)

---

## Step 1: Find the Glade Host's LAN IP

On the Glade host:
```bash
ipconfig getifaddr en0         # macOS
hostname -I | awk '{print $1}' # Linux
```

Note the `192.168.x.x` address. Use it everywhere below.

---

## Step 2: Enable Subnet Routing on the Glade Host

This makes the LAN IP reachable via Tailscale when you're remote. Skip if you only need LAN access.

On the Glade host:
```bash
sudo tailscale up --accept-routes --advertise-routes=192.168.1.0/24
```

Replace `192.168.1.0/24` with your actual LAN subnet if different. Then approve the route in [Tailscale admin → Machines](https://login.tailscale.com/admin/machines) → find the Glade host → three-dot menu → **Edit route settings** → enable the subnet.

---

## Step 3: Add the Entry on Each Device

**macOS / Linux:**
```bash
sudo sh -c 'echo "192.168.x.x  glade.home" >> /etc/hosts'
```

Verify it took:
```bash
ping -c1 glade.home
```

**Windows** (run PowerShell as Administrator):
```powershell
Add-Content C:\Windows\System32\drivers\etc\hosts "192.168.x.x  glade.home"
```

**iOS / Android:** No `/etc/hosts` access without rooting. Options:
- **Use Pi-hole** — the cleanest path for phones; see [remote-access-pihole.md](remote-access-pihole.md)
- **Raw LAN IP** — open `http://192.168.x.x:7682` on the local network; no TLS, no PWA install

Replace `192.168.x.x` with your actual LAN IP from Step 1.

---

## Considerations

- Repeat Step 3 on every new device you want to access Glade from
- On the LAN, Tailscale does not need to be running — the LAN IP resolves directly
- Remote access requires Tailscale running on the client with the subnet route approved
- If the host's LAN IP changes (e.g. after a router reset), update the entry on every device — assign a static DHCP lease on your router to avoid this
