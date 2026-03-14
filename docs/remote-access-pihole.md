# Remote Access — Pi-hole DNS

If you have Pi-hole on your network, this is the cleanest setup. Add one DNS record and every device — laptop, phone, tablet — resolves `glade.home` automatically, with or without Tailscale connected, on the LAN and remotely.

---

## How It Works

The Pi-hole record points `glade.home` at the Glade host's **LAN IP**. On the local network that's a direct connection — no Tailscale needed. When you're away, Tailscale's subnet routing makes that same LAN IP reachable through the tunnel. Same URL, same IP, no reconfiguration between networks.

---

## Prerequisites

- Tailscale installed and running on the Glade host
- Tailscale installed on remote client devices (laptop, phone) — only needed when away from home
- MagicDNS enabled in [Tailscale admin → DNS](https://login.tailscale.com/admin/dns)

---

## Step 1: Add the DNS Record in Pi-hole

Find the Glade host's LAN IP (on the host):
```bash
ipconfig getifaddr en0        # macOS
hostname -I | awk '{print $1}' # Linux
```

Open Pi-hole admin → **Local DNS** → **DNS Records** → Add:
- **Domain:** `glade.home`
- **IP Address:** your host's LAN IP (`192.168.x.x`)

---

## Step 2: Enable Subnet Routing on the Glade Host

This tells Tailscale to route your home LAN through the host when you're remote — so the LAN IP resolves and connects from anywhere.

On the Glade host:
```bash
sudo tailscale up --accept-routes --advertise-routes=192.168.1.0/24
```

Replace `192.168.1.0/24` with your actual LAN subnet if different. If Tailscale was already configured with other flags (e.g. `--hostname`), re-run with those flags included — Tailscale will warn you if any are missing.

Then approve the route in [Tailscale admin → Machines](https://login.tailscale.com/admin/machines) → find the Glade host → three-dot menu → **Edit route settings** → enable the subnet.

---

## Step 3: Add Pi-hole as a Tailscale Nameserver

For `glade.home` to resolve when you're away from home, every Tailscale-connected device needs to use Pi-hole for DNS. Do this once in Tailscale admin and all devices pick it up automatically.

In [Tailscale admin → DNS](https://login.tailscale.com/admin/dns) → **Nameservers** → **Add nameserver** → **Custom…** → enter your Pi-hole's address.

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

Add that `100.x.x.x` address as the nameserver. Set **Use with exit node** on.

**Configure Pi-hole to accept queries from Tailscale:**

By default, Pi-hole only responds to DNS queries from devices on the local subnet. Tailscale peers come from `100.x.x.x` addresses, which Pi-hole treats as non-local and silently drops.

**Pi-hole v6** (check with `pihole version`):
```bash
sudo sed -i 's/listeningMode = "LOCAL"/listeningMode = "ALL"/' /etc/pihole/pihole.toml
sudo service pihole-FTL restart
```

**Pi-hole v5:**
```bash
sudo sed -i 's/DNSMASQ_LISTENING=local/DNSMASQ_LISTENING=all/' /etc/pihole/setupVars.conf
pihole restartdns
```

Or via the Pi-hole admin UI: **Settings → DNS → Interface settings** → select **Permit all origins**.

> Setting `ALL` means Pi-hole will respond to DNS queries from any source. Since Pi-hole is only reachable via your private Tailscale network, this is safe.

### Option B: Pi-hole without Tailscale

With subnet routing already enabled on the Glade host (Step 2), the Pi-hole's LAN IP is reachable via Tailscale when you're remote. Add the Pi-hole's **LAN IP** (e.g. `192.168.1.252`) as the nameserver instead.

---

## Step 4: Enable "Override DNS servers"

This is the step most guides skip — and why mobile devices (especially iOS on cellular) often fail even after everything else is correct.

By default, Tailscale only uses your configured nameservers for MagicDNS lookups. Devices fall back to their local or carrier DNS for everything else — so `glade.home` never reaches Pi-hole on a phone over mobile data.

In [Tailscale admin → DNS](https://login.tailscale.com/admin/dns) → **Global nameservers** → enable **Override DNS servers**.

This forces every Tailscale-connected device to route all DNS through Pi-hole, regardless of what DNS the device's network normally uses.

> Make sure all devices in your tailnet can reach the Pi-hole before enabling this. If a device can't reach the nameserver, it won't be able to resolve anything.

---

## Verify

From any device — on the LAN or remote via Tailscale:
```bash
dig +short glade.home
# should return 192.168.x.x (the Glade host's LAN IP)
```

Then open `https://glade.home` — loads on the LAN without Tailscale, and remotely with it.

---

## Troubleshooting

**`glade.home` doesn't resolve remotely**

Test whether Pi-hole is responding to DNS queries over Tailscale:
```bash
dig +short glade.home @<pi-hole-tailscale-ip> +timeout=3
```

If it times out, Pi-hole's listening mode is blocking queries from Tailscale addresses. Apply the FTL fix in Option A above.

If it returns the wrong IP or nothing, the DNS record in Pi-hole is missing or incorrect — check Pi-hole admin → **Local DNS** → **DNS Records**.

**DNS resolves but `https://glade.home` won't load remotely**

`glade.home` resolves to the LAN IP (`192.168.x.x`). For that to be routable remotely, casper's subnet route must be both advertised and approved:
```bash
# On the Glade host — confirm subnet is advertised
tailscale status --self
```

Then check [Tailscale admin → Machines](https://login.tailscale.com/admin/machines) → Glade host → **Edit route settings** → confirm the subnet is enabled.

**Works on the LAN but not remotely, even with Tailscale connected**

Confirm Tailscale is actually connected and the Pi-hole nameserver is in use:
```bash
# macOS / Linux client
dig +short glade.home
# should return 192.168.x.x, not empty
```

If empty, check that the Tailscale global nameserver is set to the Pi-hole's `100.x.x.x` address (not its LAN IP) in [Tailscale admin → DNS](https://login.tailscale.com/admin/dns).

**Works on laptop but not on iPhone/mobile over cellular**

iOS and Android use their carrier's DNS by default, even when Tailscale is connected. Pi-hole only gets used if Tailscale is configured to override it.

In [Tailscale admin → DNS](https://login.tailscale.com/admin/dns) → **Global nameservers** → make sure **Override DNS servers** is enabled. Without this toggle, mobile devices ignore the Pi-hole nameserver for custom domains like `glade.home`.
