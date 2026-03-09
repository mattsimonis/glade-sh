#!/bin/bash
# ── Copilot Sync — entrypoint ─────────────────────────────────────────────────
# Starts the API server, which manages all project ttyd instances.
# Projects are created and started on-demand via the web UI.

export DB_PATH="${COPILOT_SYNC_DIR}/db/history.db"
export PORT=7683

mkdir -p "${COPILOT_SYNC_DIR}/db"

exec python3 /app/api.py
