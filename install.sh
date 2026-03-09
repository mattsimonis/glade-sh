#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Copilot Sync — Installer
#
# Sets up the copilot-sync directory structure, initializes the SQLite database,
# copies files into place, and adds shell integration to .zshrc / .bashrc.
#
# Usage:
#   ./install.sh                              # Install to ~/.copilot-sync
#   COPILOT_SYNC_DIR=/opt/copilot-sync ./install.sh   # Custom location
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
COPILOT_SYNC_DIR="${COPILOT_SYNC_DIR:-$HOME/.copilot-sync}"

WARNINGS=()
INSTALLED=()

printf "\n${BOLD}Copilot Sync Installer${RESET}\n"
printf "%-20s %s\n" "Source:" "$SCRIPT_DIR"
printf "%-20s %s\n" "Target:" "$COPILOT_SYNC_DIR"
printf "\n"

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Create directory structure
# ─────────────────────────────────────────────────────────────────────────────
info "Creating directory structure..."

dirs=(
    "$COPILOT_SYNC_DIR/assets/fonts"
    "$COPILOT_SYNC_DIR/bin"
    "$COPILOT_SYNC_DIR/lib"
    "$COPILOT_SYNC_DIR/db"
    "$COPILOT_SYNC_DIR/logs/raw"
    "$COPILOT_SYNC_DIR/web"
    "$COPILOT_SYNC_DIR/services"
)

for dir in "${dirs[@]}"; do
    mkdir -p "$dir"
done

success "Directory structure ready."
INSTALLED+=("Directory structure at $COPILOT_SYNC_DIR")

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Copy files from repo to COPILOT_SYNC_DIR
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
copy_if_exists "$SCRIPT_DIR/bin/copilot-wrap"    "$COPILOT_SYNC_DIR/bin/copilot-wrap"    "bin/copilot-wrap"
copy_if_exists "$SCRIPT_DIR/bin/copilot-history"  "$COPILOT_SYNC_DIR/bin/copilot-history"  "bin/copilot-history"

# lib/
copy_if_exists "$SCRIPT_DIR/lib/logger.sh"        "$COPILOT_SYNC_DIR/lib/logger.sh"        "lib/logger.sh"

# db/
copy_if_exists "$SCRIPT_DIR/db/schema.sql"        "$COPILOT_SYNC_DIR/db/schema.sql"        "db/schema.sql"

# web/
copy_if_exists "$SCRIPT_DIR/web/index.html"        "$COPILOT_SYNC_DIR/web/index.html"        "web/index.html"

# services/
copy_if_exists "$SCRIPT_DIR/services/Caddyfile"    "$COPILOT_SYNC_DIR/services/Caddyfile"    "services/Caddyfile"

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Make bin/* executable
# ─────────────────────────────────────────────────────────────────────────────
info "Setting permissions..."

for f in "$COPILOT_SYNC_DIR/bin/"*; do
    [[ -f "$f" ]] && chmod +x "$f"
done

success "Binaries are executable."

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Initialize SQLite database
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH="$COPILOT_SYNC_DIR/db/history.db"
SCHEMA_PATH="$COPILOT_SYNC_DIR/db/schema.sql"

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
FONT_DIR="$COPILOT_SYNC_DIR/assets/fonts"
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
    warn "gh CLI not found. Install it before using copilot-sync."
    warn "  macOS:  brew install gh"
    warn "  Linux:  https://cli.github.com/"
    WARNINGS+=("gh CLI not installed")
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Check for gh copilot extension
# ─────────────────────────────────────────────────────────────────────────────
if command -v gh &>/dev/null; then
    if gh extension list 2>/dev/null | grep -q "gh-copilot"; then
        success "gh copilot extension is installed."
    else
        warn "gh copilot extension not found."
        warn "  Install it with: gh extension install github/gh-copilot"
        WARNINGS+=("gh copilot extension not installed")
    fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Step 8: sqlite3 availability (already checked above, just confirm)
# ─────────────────────────────────────────────────────────────────────────────
success "sqlite3 is available: $(sqlite3 --version | head -1)"

# ─────────────────────────────────────────────────────────────────────────────
# Step 9: Shell integration (.zshrc / .bashrc)
# ─────────────────────────────────────────────────────────────────────────────
PATH_LINE="export PATH=\"\$HOME/.copilot-sync/bin:\$PATH\""
SOURCE_LINE="[[ -f \"\$HOME/.copilot-sync/bin/copilot-wrap\" ]] && source \"\$HOME/.copilot-sync/bin/copilot-wrap\""

add_shell_integration() {
    local rcfile="$1"
    local name="$2"
    local changed=false

    if [[ ! -f "$rcfile" ]]; then
        info "$rcfile does not exist, skipping."
        return
    fi

    # Add PATH entry if not already present
    if ! grep -qF '.copilot-sync/bin' "$rcfile" 2>/dev/null; then
        printf '\n# Copilot Sync — PATH\n%s\n' "$PATH_LINE" >> "$rcfile"
        changed=true
    fi

    # Add source line if not already present
    if ! grep -qF 'copilot-wrap' "$rcfile" 2>/dev/null; then
        printf '\n# Copilot Sync — wrapper integration\n%s\n' "$SOURCE_LINE" >> "$rcfile"
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

  3. Start services (choose one):

     Docker Compose (recommended):
       cd $SCRIPT_DIR && docker compose up -d

     Or manually install ttyd + Caddy:
       brew install ttyd caddy
       # Then create launchd plists or run them directly

  4. From another device on your tailnet, visit:
       http://<this-machine-tailscale-hostname>

  5. If you haven't already, authenticate gh CLI:
       gh auth login

  6. Install the copilot extension if needed:
       gh extension install github/gh-copilot

EOF

printf "${GREEN}${BOLD}Done.${RESET}\n\n"
