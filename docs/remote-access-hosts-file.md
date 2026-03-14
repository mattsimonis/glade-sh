# Remote Access — `/etc/hosts` Per Device

No Pi-hole or extra infrastructure needed. Add one line to `/etc/hosts` on each device and `glade.home` resolves via the Glade host's Tailscale IP. Works immediately. The trade-off: you repeat the step on every new device, and phones require a workaround.

---

## Prerequisites

- Tailscale installed and running on the Glade host and all client devices
- MagicDNS enabled in [Tailscale admin → DNS](https://login.tailscale.com/admin/dns)

---

## Step 1: Find the Glade Host's Tailscale IP

On the Glade host:
```bash
tailscale ip -4
```

Note the `100.x.x.x` address. Use it everywhere below.

---

## Step 2: Add the Entry on Each Device

**macOS / Linux:**
```bash
sudo sh -c 'echo "100.x.x.x  glade.home" >> /etc/hosts'
```

Verify it took:
```bash
ping -c1 glade.home
```

**Windows** (run PowerShell as Administrator):
```powershell
Add-Content C:\Windows\System32\drivers\etc\hosts "100.x.x.x  glade.home"
```

**iOS / Android:** No `/etc/hosts` access without rooting. Options:
- **Use Pi-hole** — add the record there and configure it as a Tailscale global nameserver; see [remote-access-pihole.md](remote-access-pihole.md)
- **Raw Tailscale IP** — open `http://100.x.x.x:7682` directly in the browser; no TLS, no PWA install
- **MagicDNS device name** — access via `http://[hostname]` where hostname is the Glade host's device name in Tailscale admin (HTTP only unless you configure a cert for that name)

---

## Considerations

- Repeat Step 2 on every new device you want to access Glade from
- The entry uses the Tailscale IP, so Tailscale must be running on the client — on the LAN it routes directly, remote it tunnels
- If the Tailscale IP ever changes (rare, but possible if the node is removed and re-added), update the entry on every device
