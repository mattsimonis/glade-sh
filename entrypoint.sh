#!/bin/bash
# ── Roost — entrypoint ─────────────────────────────────────────────────
# Starts the API server, which manages all project ttyd instances.
# Projects are created and started on-demand via the web UI.

export DB_PATH="${ROOST_DIR}/db/history.db"
export PORT=7683

mkdir -p "${ROOST_DIR}/db" "${ROOST_DIR}/logs/_main"

exec python3 /app/api.py
