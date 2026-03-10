#!/bin/bash
# ── Roost — entrypoint ─────────────────────────────────────────────────────────
# Clones or updates the app repo, then supervises the API server.
# The poller runs in the background and pulls new commits every 2 minutes.
# API restarts are user-triggered via POST /api/restart (exits with code 42).

ROOST_REPO_URL="${ROOST_REPO_URL:-https://github.com/mattsimonis/roost.git}"
APP_DIR="/app/roost"
UPDATE_PENDING_FILE="/tmp/roost-update-pending"
IMAGE_UPDATE_FILE="/tmp/roost-image-update-pending"
POLL_INTERVAL=120

export DB_PATH="${ROOST_DIR}/db/history.db"
export PORT=7683

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [roost] $*"; }

mkdir -p "${ROOST_DIR}/db" "${ROOST_DIR}/logs/_main"

# ── Clone or pull app repo ─────────────────────────────────────────────────────
if git -C "$APP_DIR" pull --ff-only -q 2>/dev/null; then
    log "Repo updated"
elif git -C "$APP_DIR" rev-parse HEAD >/dev/null 2>&1; then
    log "git pull failed — continuing with existing code"
else
    log "Cloning $ROOST_REPO_URL"
    rm -rf "$APP_DIR"
    git clone -q "$ROOST_REPO_URL" "$APP_DIR"
fi

# ── Background update poller ───────────────────────────────────────────────────
poller() {
    while true; do
        sleep "$POLL_INTERVAL"
        cd "$APP_DIR" || continue
        git fetch origin -q 2>/dev/null || continue
        LOCAL=$(git rev-parse HEAD 2>/dev/null) || continue
        REMOTE=$(git rev-parse origin/main 2>/dev/null) || continue
        [ "$LOCAL" = "$REMOTE" ] && continue

        CHANGED=$(git diff --name-only HEAD origin/main 2>/dev/null)
        git reset --hard origin/main -q
        log "Pulled $(git rev-parse --short HEAD) — $(echo "$CHANGED" | wc -l | tr -d ' ') file(s) changed"

        if echo "$CHANGED" | grep -qE '^(Dockerfile|entrypoint\.sh|config/)'; then
            log "Image-level changes detected — run 'make build' to apply"
            echo "image" > "$IMAGE_UPDATE_FILE"
        fi
        if echo "$CHANGED" | grep -q '^api/api\.py'; then
            log "api.py updated — restart pending"
            echo "api" > "$UPDATE_PENDING_FILE"
        fi
        # web/index.html and other static files are served live — no action needed
    done
}

poller &
POLLER_PID=$!

# ── API supervisor loop ────────────────────────────────────────────────────────
log "Starting API on port $PORT"
while true; do
    rm -f "$UPDATE_PENDING_FILE"
    python3 "$APP_DIR/api/api.py"
    EXIT=$?
    if [ "$EXIT" -eq 42 ]; then
        log "Restarting API (update applied)"
        continue
    fi
    log "API exited ($EXIT)"
    kill "$POLLER_PID" 2>/dev/null
    exit "$EXIT"
done
