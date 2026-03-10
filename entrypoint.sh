#!/bin/bash
# ── Roost — entrypoint ─────────────────────────────────────────────────
# Starts the API server, which manages all project ttyd instances.
# Projects are created and started on-demand via the web UI.

export DB_PATH="${ROOST_DIR}/db/history.db"
export PORT=7683

mkdir -p "${ROOST_DIR}/db" "${ROOST_DIR}/logs/_main"

# Warn clearly if gh CLI is not authenticated — the terminal will still work
# but `gh copilot` commands will fail until auth is complete.
if ! gh auth status &>/dev/null; then
    echo ""
    echo "⚠️  GitHub CLI is not authenticated."
    echo "   Run: make auth"
    echo "   Or:  docker compose exec ttyd gh auth login"
    echo ""
fi

exec python3 /app/api.py
