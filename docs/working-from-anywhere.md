# Working From Anywhere — Glade Setup Guide

Your Mac Mini runs the hub. Every device reaches it through Tailscale.
The terminal is a ttyd session inside Docker — your tools run there.

The gap: your project files live on your laptop, not the Mac Mini.
This doc closes that gap.

---

## The Core Idea

You have two good options depending on how you work:

| Option | What it means | Best for |
|--------|--------------|---------|
| **SSH from hub into laptop** | Mac Mini terminal SSHes to your laptop. Files, git, tools all stay on laptop. | Working on an active local project |
| **Clone project to Mac Mini** | Sync/clone project to Mac Mini. Work from there. | Long-running work, staying on the hub |

Most people start with Option 1. It requires nothing except Tailscale and SSH.

---

## Option 1: SSH Into Your Laptop From the Hub

The terminal on your Mac Mini can SSH into your laptop over Tailscale. Once connected, you're working on your laptop's filesystem — your files, your git history, your tools, your `gh auth`.

### One-time setup: Enable SSH on your Mac

On your laptop:

```
System Settings → General → Sharing → Remote Login → ON
```

Allow access for your user account. Note the machine name shown (e.g., `matts-macbook.local`). Tailscale will give it a cleaner name like `matts-macbook`.

### One-time setup: Add your Mac Mini's key to your laptop

This avoids password prompts. Run this from **inside the glade terminal** (the Mac Mini):

```sh
# Generate a key if one doesn't exist
ssh-keygen -t ed25519 -C "glade@mac-mini" -f ~/.ssh/id_ed25519 -N ""

# Copy it to your laptop (use your Tailscale hostname)
ssh-copy-id matt@matts-macbook
```

You'll enter your laptop password once. After that — no passwords.

### Daily workflow

1. Open the Glade web UI on your phone
2. In the terminal, type:
   ```sh
   ssh matt@matts-macbook
   cd ~/Dev/my-project
   ```
3. You're now on your laptop. Your tools work with full project context.
4. When done: `exit` returns you to the Mac Mini shell.

### Create a project shortcut for it

In Glade, add a project:
- **Name:** My Project (or whatever)
- **Directory:** `/root` (it'll change once you SSH in — this is just the starting point)

Then in that project's shell, you're one `ssh matt@matts-macbook && cd ~/Dev/my-project` away.

Better: add a shell alias to your Mac Mini's `~/.zshrc` inside the Docker container:
```sh
alias myproject='ssh matt@matts-macbook -t "cd ~/Dev/my-project && exec zsh"'
```

One word. You're in your project.

---

## Option 2: Clone / Sync Project to Mac Mini

If you want the project to live on the Mac Mini itself (no SSH hop):

### Initial clone

```sh
# Inside Mac Mini terminal
mkdir -p ~/projects
git clone git@github.com:you/your-project.git ~/projects/your-project
```

Then create a project in Glade pointing to `~/projects/your-project`.

### Keeping it in sync

If you're actively editing on your laptop AND want the Mac Mini terminal to have the latest:

**Option A — Git push/pull (recommended)**
```sh
# On laptop: commit and push when you want the hub to see it
git add -A && git commit -m "wip" && git push

# On Mac Mini: pull when needed
git pull
```

**Option B — Live rsync** (real-time, no git needed)
```sh
# On laptop, run this — it watches for file changes and rsyncs to Mac Mini
fswatch -r ~/Dev/my-project | xargs -I{} rsync -avz \
  --exclude 'node_modules' --exclude '.git' \
  ~/Dev/my-project/ your-mac:~/projects/my-project/
```

Requires `fswatch`: `brew install fswatch`.

**Option C — Mutagen** (the cleanest two-way sync)
```sh
brew install mutagen-io/mutagen/mutagen
mutagen sync create \
  --name=my-project \
  ~/Dev/my-project \
  matt@your-mac:~/projects/my-project
```

Mutagen syncs in real-time, both directions. Edit on laptop, run on Mac Mini, changes appear everywhere. Requires files `node_modules` to be excluded via a mutagen config.

---

## Setting Up Another Local Project

You have a second project on your laptop. Add it to Glade:

### If using SSH (Option 1)

No setup needed on the Mac Mini. Just SSH to your laptop and `cd` to the project. Create a Glade project entry as a reminder/shortcut.

Add an alias inside the Docker container:
```sh
# In Mac Mini's ~/.zshrc (edit via docker exec or rebuild)
alias work2='ssh matt@matts-macbook -t "cd ~/Dev/project-two && exec zsh"'
```

### If cloning (Option 2)

```sh
# Mac Mini terminal
git clone git@github.com:you/project-two.git ~/projects/project-two
```

Create a project in Glade → directory: `~/projects/project-two`.

---

## The "Going to Bed" Workflow

Tonight's scenario: you're working on your laptop, you want to dim it and continue from your phone.

### What to do before dimming

1. **Save your work.** `git add -A && git commit -m "wip"` or just save files.
2. **Leave the Mac Mini terminal running** — tmux sessions inside Docker persist. You don't need to do anything special. The session stays alive.
3. **If you were working in a Mac Mini terminal** (not SSH'd into laptop): already done. Your tmux session is there.
4. **If you were SSH'd into your laptop**: the SSH connection will drop when your laptop sleeps. That's fine. On your phone, open a new shell in the same project and re-SSH. Your files are still there (or pick up from git).

### On your phone

1. Open Safari → `http://your-mac.local` (or your Tailscale hostname)
2. Tap the project you were working on
3. If your session was in a Mac Mini terminal: it's exactly where you left it (tmux)
4. If you were SSH'd into your laptop: re-connect: `ssh matt@matts-macbook && cd ~/Dev/my-project`

### Keep your laptop accessible

Your laptop needs to be **awake and on the same Tailscale network** for SSH to work. Settings:

- **System Settings → Battery → Prevent automatic sleeping when display is off** → ON (on power)  
- Or set display sleep to never when plugged in
- The display can sleep/dim. The machine must stay awake.

Alternatively: use `caffeinate -i` on your laptop to keep it awake while you sleep:
```sh
# On laptop — keeps machine awake, kills when you close the terminal
caffeinate -i
```

---

## CLI Tools Over SSH

Tools installed in your Glade container (via `config/packages.sh`) are available in the Mac Mini terminal. When you SSH into your laptop, you use the laptop's own tools instead.

If you install `gh` on both machines:
- On Mac Mini: `gh auth login` inside the Docker container
- On laptop: `gh auth login` on the laptop itself

Any tool works the same pattern — install where you need it.

---

## Gaps Summary

| Gap | Status | Fix |
|-----|--------|-----|
| Project files on laptop | ✅ Solved | SSH into laptop from hub (Option 1) |
| Second project | ✅ Solved | Same SSH workflow or clone |
| Laptop stays awake | Action needed | Disable sleep-on-lid-close or use `caffeinate` |
| SSH key from Mac Mini | Action needed | `ssh-copy-id` (one-time, 2 minutes) |
| Tailscale on all devices | Assumed done | Already set up |

---

## Quick Checklist for Tonight

Run through this before you go to bed:

- [ ] Enable Remote Login on your laptop (System Settings → Sharing)
- [ ] From the Mac Mini terminal: `ssh-keygen` then `ssh-copy-id matt@matts-macbook`  
- [ ] Test: from Mac Mini terminal, `ssh matt@matts-macbook` — should connect without password
- [ ] `cd ~/Dev/your-project` — your files and tools should be accessible
- [ ] Add a shell alias so you can one-word connect tomorrow
- [ ] Set your laptop to not sleep when plugged in (if you want to SSH into it overnight)
- [ ] On your phone, open the Glade UI and confirm you can see your projects

That's it. Laptop stays on the desk. You pick up your phone and keep working.

---

## Troubleshooting

**SSH times out from Mac Mini terminal**
- Is your laptop on Tailscale? Check the Tailscale app on your laptop.
- Try the IP address: `ssh matt@100.x.x.x` (find it in Tailscale admin)

**Tools not found after SSH**
- SSH connects to your laptop, which has its own tools. Install what you need there.
- To use Mac Mini tools, work from the Mac Mini terminal and sync files (Option 2).

**Files out of sync between laptop and Mac Mini**
- Option 1 (SSH) doesn't have this problem — you're editing directly on the laptop
- Option 2: run `git pull` on Mac Mini or re-run your rsync

**Tailscale not connecting devices**
- Open Tailscale app, sign in, ensure both devices show in the admin console
- MagicDNS must be enabled for hostname resolution (hostname instead of IP)
