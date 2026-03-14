# Remote Access — Pi-hole DNS

If you have Pi-hole on your network, this is the cleanest setup. Add one DNS record and every device — laptop, phone, tablet — resolves `glade.home` automatically, on the LAN and over Tailscale, without any per-device configuration.

---

## Prerequisites

- Tailscale installed and running on the Glade host and all client devices
- MagicDNS enabled in [Tailscale admin → DNS](https://login.tailscale.com/admin/dns)

---

## Step 1: Add the DNS Record in Pi-hole

Point `glade.home` at the Glade host's **Tailscale IP** (not the LAN IP). Tailscale routes locally when you're home and tunnels when you're away — same URL, same IP, no reconfiguration between networks.

Find the Glade host's Tailscale IP (on the host):
```bash
tailscale ip -4
```

Open Pi-hole admin → **Local DNS** → **DNS Records** → Add:
- **Domain:** `glade.home`
- **IP Address:** your host's Tailscale IP (`100.x.x.x`)

---

## Step 2: Add Pi-hole as a Tailscale Nameserver

For `glade.home` to resolve when you're away from home, every Tailscale-connected device needs to use Pi-hole for DNS. Do this once in Tailscale admin and all devices pick it up automatically.

In [Tailscale admin → DNS](https://login.tailscale.com/admin/dns) → **Nameservers** → **Add nameserver** → enter your Pi-hole's address.

Two options depending on whether your Pi-hole is on Tailscale:

### Option A: Pi-hole on Tailscale (Recommended)

Install Tailscale on the Pi-hole machine:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Then get its Tailscale IP:
```bash
tailscale ip -4
```

Add that `100.x.x.x` address as a **Global nameserver** in Tailscale admin. A Tailscale IP is stable and reachable from anywhere on your tailnet — no dependency on your home network being up.

### Option B: Pi-hole without Tailscale — Subnet Routing

If you'd rather not install Tailscale on the Pi-hole, you can expose your LAN to Tailscale via subnet routing on the Glade host. Remote devices then reach the Pi-hole's LAN IP through the tunnel.

On the Glade host, advertise your LAN subnet:
```bash
sudo tailscale up --advertise-routes=192.168.1.0/24
```

Approve the route in [Tailscale admin → Machines](https://login.tailscale.com/admin/machines) → find the host → **Edit route settings** → enable the subnet.

Then add the Pi-hole's **LAN IP** (e.g. `192.168.1.252`) as a **Global nameserver** in Tailscale admin → DNS.

> This approach works but has a dependency: remote DNS resolution only works when the Glade host (and its subnet route) is online. Option A is more resilient.

---

## Verify

From any device on Tailscale, confirm the domain resolves:
```bash
dig +short glade.home
# should return 100.x.x.x (the Glade host's Tailscale IP)
```

Then open `https://glade.home` — it should load with no cert warning from any network.
