#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Glade — Installer
#
# Sets up the Glade directory structure, initializes the SQLite database,
# copies files into place, and adds shell integration to .zshrc / .bashrc.
#
# Usage:
#   ./install.sh                              # Install to ~/.glade
#   GLADE_DIR=/opt/glade ./install.sh   # Custom location
#
# Safe to run multiple times (idempotent).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { printf "${BLUE}[info]${RESET}    %s\n" "$*"; }
success() { printf "${GREEN}[ok]${RESET}      %s\n" "$*"; }
warn()    { printf "${YELLOW}[warn]${RESET}    %s\n" "$*"; }
error()   { printf "${RED}[error]${RESET}   %s\n" "$*" >&2; }

# ── Resolve script directory (where the repo files live) ─────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Configuration ────────────────────────────────────────────────────────────
GLADE_DIR="${GLADE_DIR:-$HOME/.glade}"

WARNINGS=()
INSTALLED=()

printf "\n${BOLD}Glade Installer${RESET}\n"
printf "%-20s %s\n" "Source:" "$SCRIPT_DIR"
printf "%-20s %s\n" "Target:" "$GLADE_DIR"
printf "\n"

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Create directory structure
# ─────────────────────────────────────────────────────────────────────────────
info "Creating directory structure..."

dirs=(
    "$GLADE_DIR/assets/fonts"
    "$GLADE_DIR/bin"
    "$GLADE_DIR/lib"
    "$GLADE_DIR/db"
    "$GLADE_DIR/logs/_main"
    "$GLADE_DIR/uploads"
    "$GLADE_DIR/web"
    "$GLADE_DIR/services"
)

for dir in "${dirs[@]}"; do
    mkdir -p "$dir"
done

success "Directory structure ready."
INSTALLED+=("Directory structure at $GLADE_DIR")

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Initialize personal config files from examples
# ─────────────────────────────────────────────────────────────────────────────
info "Checking personal config files..."

init_from_example() {
    local name="$1"
    local example="$SCRIPT_DIR/config/${name}.example"
    local target="$SCRIPT_DIR/config/${name}"
    if [[ ! -f "$target" ]]; then
        if [[ -f "$example" ]]; then
            cp "$example" "$target"
            [[ "$name" == "packages.sh" ]] && chmod +x "$target"
            success "Created config/$name from example"
            INSTALLED+=("config/$name (from example)")
        else
            warn "No example found for config/$name — skipping"
            WARNINGS+=("Missing config/$name.example")
        fi
    else
        info "config/$name already exists (skipping)"
    fi
}

init_from_example "zshrc"
init_from_example "packages.sh"

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Copy files from repo to GLADE_DIR
# ─────────────────────────────────────────────────────────────────────────────
info "Copying files..."

copy_if_exists() {
    local src="$1"
    local dest="$2"
    local label="$3"

    if [[ -f "$src" ]]; then
        cp "$src" "$dest"
        success "Copied $label"
        INSTALLED+=("$label -> $dest")
    else
        warn "Source file not found: $src (skipping $label)"
        WARNINGS+=("Missing source file: $src")
    fi
}

# bin/
copy_if_exists "$SCRIPT_DIR/bin/glade-wrap"    "$GLADE_DIR/bin/glade-wrap"    "bin/glade-wrap"
copy_if_exists "$SCRIPT_DIR/bin/glade-history"  "$GLADE_DIR/bin/glade-history"  "bin/glade-history"

# lib/
copy_if_exists "$SCRIPT_DIR/lib/logger.sh"        "$GLADE_DIR/lib/logger.sh"        "lib/logger.sh"

# db/
copy_if_exists "$SCRIPT_DIR/db/schema.sql"        "$GLADE_DIR/db/schema.sql"        "db/schema.sql"

# web/
copy_if_exists "$SCRIPT_DIR/web/index.html"        "$GLADE_DIR/web/index.html"        "web/index.html"

# services/
copy_if_exists "$SCRIPT_DIR/services/Caddyfile"    "$GLADE_DIR/services/Caddyfile"    "services/Caddyfile"

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Make bin/* executable
# ─────────────────────────────────────────────────────────────────────────────
info "Setting permissions..."

for f in "$GLADE_DIR/bin/"*; do
    [[ -f "$f" ]] && chmod +x "$f"
done

success "Binaries are executable."

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Initialize SQLite database
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH="$GLADE_DIR/db/history.db"
SCHEMA_PATH="$GLADE_DIR/db/schema.sql"

if ! command -v sqlite3 &>/dev/null; then
    error "sqlite3 is required but not found. Please install it first."
    error "  macOS:  brew install sqlite3   (usually pre-installed)"
    error "  Linux:  apt install sqlite3"
    exit 1
fi

if [[ -f "$DB_PATH" ]]; then
    info "SQLite database already exists at $DB_PATH (skipping init)."
else
    if [[ -f "$SCHEMA_PATH" ]]; then
        info "Initializing SQLite database..."
        sqlite3 "$DB_PATH" < "$SCHEMA_PATH"
        success "Database initialized at $DB_PATH"
        INSTALLED+=("SQLite database at $DB_PATH")
    else
        warn "Schema file not found at $SCHEMA_PATH — cannot initialize database."
        WARNINGS+=("Database not initialized (missing schema.sql)")
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Check for Berkeley Mono Nerd Font
# ─────────────────────────────────────────────────────────────────────────────
FONT_DIR="$GLADE_DIR/assets/fonts"
FONT_FOUND=false

for ext in woff2 woff ttf otf; do
    if compgen -G "$FONT_DIR/"*.[Bb]erkeley*."$ext" &>/dev/null || \
       compgen -G "$FONT_DIR/"*berkeley*."$ext" &>/dev/null; then
        FONT_FOUND=true
        break
    fi
done

# Also check with broader pattern in case of different naming
if [[ "$FONT_FOUND" == false ]]; then
    # Check if any font files exist at all
if compgen -G "$FONT_DIR/*.woff2" &>/dev/null || compgen -G "$FONT_DIR/*.ttf" &>/dev/null; then
        FONT_FOUND=true
    fi
fi

if [[ "$FONT_FOUND" == true ]]; then
    success "Font file(s) found in $FONT_DIR"
else
    warn "No Berkeley Mono Nerd Font (.ttf or .woff2) found in $FONT_DIR"
    warn "  The UI will fall back to JetBrains Mono / Fira Code / system monospace."
    warn "  To add it later, place BerkeleyMonoNerdFont-Regular.ttf in: $FONT_DIR/"
    WARNINGS+=("Berkeley Mono Nerd Font not found (optional)")
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Check for gh CLI
# ─────────────────────────────────────────────────────────────────────────────
if command -v gh &>/dev/null; then
    GH_VERSION="$(gh --version | head -1)"
    success "gh CLI found: $GH_VERSION"
else
    warn "gh CLI not found. Install it before using Glade."
    warn "  macOS:  brew install gh"
    warn "  Linux:  https://cli.github.com/"
    WARNINGS+=("gh CLI not installed")
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: sqlite3 availability (already checked above, just confirm)
# ─────────────────────────────────────────────────────────────────────────────
success "sqlite3 is available: $(sqlite3 --version | head -1)"

# ─────────────────────────────────────────────────────────────────────────────
# Step 8: Shell integration (.zshrc / .bashrc)
# ─────────────────────────────────────────────────────────────────────────────
PATH_LINE="export PATH=\"\$HOME/.glade/bin:\$PATH\""
SOURCE_LINE="[[ -f \"\$HOME/.glade/bin/glade-wrap\" ]] && source \"\$HOME/.glade/bin/glade-wrap\""

add_shell_integration() {
    local rcfile="$1"
    local name="$2"
    local changed=false

    if [[ ! -f "$rcfile" ]]; then
        info "$rcfile does not exist, skipping."
        return
    fi

    # Add PATH entry if not already present
    if ! grep -qF '.glade/bin' "$rcfile" 2>/dev/null; then
        printf '\n# Glade — PATH\n%s\n' "$PATH_LINE" >> "$rcfile"
        changed=true
    fi

    # Add source line if not already present
    if ! grep -qF 'glade-wrap' "$rcfile" 2>/dev/null; then
        printf '\n# Glade — wrapper integration\n%s\n' "$SOURCE_LINE" >> "$rcfile"
        changed=true
    fi

    if [[ "$changed" == true ]]; then
        success "Added shell integration to $name"
        INSTALLED+=("Shell integration in $rcfile")
    else
        info "Shell integration already present in $name (no changes)."
    fi
}

add_shell_integration "$HOME/.zshrc"  ".zshrc"
add_shell_integration "$HOME/.bashrc" ".bashrc"

# ─────────────────────────────────────────────────────────────────────────────
# Step 9: Rebuild watcher + auto-update (macOS only — launchd agents)
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$(uname -s)" == "Darwin" ]]; then
    SCRIPTS_DIR="$GLADE_DIR/scripts"
    WATCHER_SCRIPT="$SCRIPTS_DIR/rebuild-watcher.sh"
    UPDATER_SCRIPT="$SCRIPTS_DIR/auto-update.sh"
    WATCHER_PLIST="$HOME/Library/LaunchAgents/com.glade.rebuild-watcher.plist"
    UPDATER_PLIST="$HOME/Library/LaunchAgents/com.glade.auto-update.plist"
    TRIGGER_FILE="$GLADE_DIR/.rebuild-requested"
    LOCK_FILE="$GLADE_DIR/.rebuild-running"
    REBUILD_LOG="$GLADE_DIR/rebuild.log"
    LAUNCH_CTL_UID=$(id -u)

    mkdir -p "$SCRIPTS_DIR" "$HOME/Library/LaunchAgents"

    # ── Remove stale agents from any prior install, regardless of project name ─
    # Scan all LaunchAgents plists for any that reference our GLADE_DIR or
    # the rebuild trigger path — covers renames without hardcoding old labels.
    while IFS= read -r -d '' plist; do
        [[ "$plist" == "$WATCHER_PLIST" || "$plist" == "$UPDATER_PLIST" ]] && continue
        if grep -qF "$GLADE_DIR" "$plist" 2>/dev/null || \
           grep -q "rebuild-watcher\|auto-update" "$plist" 2>/dev/null; then
            label=$(defaults read "$plist" Label 2>/dev/null || true)
            launchctl bootout "gui/$LAUNCH_CTL_UID" "$plist" 2>/dev/null || \
                launchctl unload "$plist" 2>/dev/null || true
            rm -f "$plist"
            [[ -n "$label" ]] && info "Removed stale agent: $label" || info "Removed stale agent: $plist"
        fi
    done < <(find "$HOME/Library/LaunchAgents" -name "*.plist" -print0 2>/dev/null)

    # ── Rebuild watcher: fires when .rebuild-requested appears ───────────────
    # Paths resolved at install time; script does not depend on $PWD.
    cat > "$WATCHER_SCRIPT" << WATCHER_EOF
#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH"
TRIGGER="$TRIGGER_FILE"
LOCK="$LOCK_FILE"
LOG="$REBUILD_LOG"
REPO_DIR="$SCRIPT_DIR"
[[ -f "\$TRIGGER" ]] || exit 0
rm -f "\$TRIGGER"
touch "\$LOCK"
echo "=== Rebuild started \$(date) ===" >> "\$LOG"
git -C "\$REPO_DIR" fetch origin 2>&1 | tee -a "\$LOG" && \
    git -C "\$REPO_DIR" reset --hard origin/HEAD 2>&1 | tee -a "\$LOG" && \
    docker compose -f "\$REPO_DIR/docker-compose.yml" --project-directory "\$REPO_DIR" build --build-arg BUILD_DATE=\$(date +%Y%m%d%H%M%S) ttyd 2>&1 | tee -a "\$LOG" && \
    docker compose -f "\$REPO_DIR/docker-compose.yml" --project-directory "\$REPO_DIR" up -d 2>&1 | tee -a "\$LOG" && \
    docker exec glade-ttyd git -C /app/glade fetch origin -q 2>&1 | tee -a "\$LOG" && \
    docker exec glade-ttyd git -C /app/glade reset --hard origin/HEAD 2>&1 | tee -a "\$LOG"
STATUS=\$?
rm -f "\$LOCK"
echo "=== Rebuild finished \$(date) exit=\$STATUS ===" >> "\$LOG"
WATCHER_EOF
    chmod +x "$WATCHER_SCRIPT"

    cat > "$WATCHER_PLIST" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>         <string>com.glade.rebuild-watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$WATCHER_SCRIPT</string>
    </array>
    <key>WatchPaths</key>
    <array><string>$TRIGGER_FILE</string></array>
    <key>StandardOutPath</key>  <string>$SCRIPTS_DIR/watcher.log</string>
    <key>StandardErrorPath</key><string>$SCRIPTS_DIR/watcher.log</string>
    <key>RunAtLoad</key>        <false/>
</dict>
</plist>
PLIST_EOF

    # ── Auto-update: polls git every 30 min, triggers rebuild when behind ────
    cat > "$UPDATER_SCRIPT" << UPDATER_EOF
#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH"
REPO_DIR="$SCRIPT_DIR"
TRIGGER="$TRIGGER_FILE"
LOCK="$LOCK_FILE"
LOG="$REBUILD_LOG"
# Skip if a rebuild is already running
[[ -f "\$LOCK" || -f "\$TRIGGER" ]] && exit 0
git -C "\$REPO_DIR" fetch origin --quiet 2>/dev/null || exit 0
BEHIND=\$(git -C "\$REPO_DIR" rev-list HEAD..origin/HEAD --count 2>/dev/null || echo 0)
if [[ "\$BEHIND" -gt 0 ]]; then
    echo "=== Auto-update: \$BEHIND new commit(s) detected at \$(date) ===" >> "\$LOG"
    touch "\$TRIGGER"
fi
UPDATER_EOF
    chmod +x "$UPDATER_SCRIPT"

    cat > "$UPDATER_PLIST" << UPLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>          <string>com.glade.auto-update</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$UPDATER_SCRIPT</string>
    </array>
    <key>StartInterval</key>  <integer>1800</integer>
    <key>RunAtLoad</key>      <true/>
    <key>StandardOutPath</key>  <string>$SCRIPTS_DIR/auto-update.log</string>
    <key>StandardErrorPath</key><string>$SCRIPTS_DIR/auto-update.log</string>
</dict>
</plist>
UPLIST_EOF

    # ── Load (or reload) both agents ─────────────────────────────────────────
    _load_agent() {
        local plist="$1" label="$2"
        launchctl bootout "gui/$LAUNCH_CTL_UID" "$plist" 2>/dev/null || true
        if launchctl bootstrap "gui/$LAUNCH_CTL_UID" "$plist" 2>/dev/null; then
            success "Agent registered: $label"
        else
            launchctl load -w "$plist" 2>/dev/null || true
            success "Agent registered (legacy): $label"
        fi
        INSTALLED+=("$label")
    }
    _load_agent "$WATCHER_PLIST" "com.glade.rebuild-watcher"
    _load_agent "$UPDATER_PLIST" "com.glade.auto-update"
else
    info "Skipping rebuild watcher / auto-update (macOS only)."
fi

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
printf "\n${BOLD}━━━ Installation Summary ━━━${RESET}\n\n"

if [[ ${#INSTALLED[@]} -gt 0 ]]; then
    printf "${GREEN}${BOLD}Installed:${RESET}\n"
    for item in "${INSTALLED[@]}"; do
        printf "  ${GREEN}+${RESET} %s\n" "$item"
    done
    printf "\n"
fi

if [[ ${#WARNINGS[@]} -gt 0 ]]; then
    printf "${YELLOW}${BOLD}Warnings:${RESET}\n"
    for item in "${WARNINGS[@]}"; do
        printf "  ${YELLOW}!${RESET} %s\n" "$item"
    done
    printf "\n"
fi

printf "${BOLD}━━━ Next Steps ━━━${RESET}\n\n"

cat <<EOF
  1. Restart your shell (or run: source ~/.zshrc)

  2. Ensure Tailscale is installed and running on this machine:
       brew install tailscale   # macOS
       # Then: enable in System Settings or run tailscaled

  3. Start services:

     Docker Compose (recommended):
       cd $SCRIPT_DIR && make setup

     Or just bring up the containers:
       cd $SCRIPT_DIR && make up

  4. From another device on your network, visit:
       https://glade.local   (if Pi-hole DNS is configured)
       or the Mac Mini's LAN IP

  5. (Optional) Authenticate gh CLI inside the container:
       make auth

EOF

printf "${GREEN}${BOLD}Done.${RESET}\n\n"
