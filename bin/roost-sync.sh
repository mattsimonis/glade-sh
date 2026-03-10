#!/bin/bash
# Polls origin/main and auto-deploys changes to the local repo.
# Runs the right make target based on what changed.
# Intended to be invoked by cron every 2 minutes on casper.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG_TAG="roost-sync"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

cd "$REPO"

git fetch origin -q

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0
fi

CHANGED=$(git diff --name-only HEAD origin/main)
log "Pulling $(git rev-parse --short origin/main) ($(echo "$CHANGED" | wc -l | tr -d ' ') files changed)"

git reset --hard origin/main

if echo "$CHANGED" | grep -qE '^(Dockerfile|entrypoint\.sh|config/)'; then
    log "Dockerfile/config changed — rebuilding image"
    make build
elif echo "$CHANGED" | grep -q '^api/api\.py'; then
    log "api.py changed — restarting ttyd"
    make restart
else
    log "Static files only — no restart needed"
fi

log "Done"
