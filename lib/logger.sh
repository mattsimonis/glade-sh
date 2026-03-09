#!/usr/bin/env bash
# copilot-sync/lib/logger.sh — Bash library for logging gh copilot interactions to SQLite
#
# Usage: source this file from copilot-wrap or any script that needs logging.
#
# All functions are safe — if sqlite3 is missing or any DB operation fails,
# the function returns silently. Logging must NEVER block the user's command.

COPILOT_SYNC_DIR="${COPILOT_SYNC_DIR:-$HOME/.copilot-sync}"
COPILOT_SYNC_DB="${COPILOT_SYNC_DIR}/db/history.db"
COPILOT_SYNC_SCHEMA="${COPILOT_SYNC_DIR}/db/schema.sql"

# --------------------------------------------------------------------------
# copilot_log_init_db — Create the database and apply schema if not present.
#
# Safe to call multiple times; uses IF NOT EXISTS in schema.
# Returns 0 on success, 1 on failure (silently).
# --------------------------------------------------------------------------
copilot_log_init_db() {
    # Bail if sqlite3 is not available
    command -v sqlite3 >/dev/null 2>&1 || return 1

    # Ensure the db directory exists
    mkdir -p "${COPILOT_SYNC_DIR}/db" 2>/dev/null || return 1

    # If schema file is missing, we cannot initialize
    if [[ ! -f "$COPILOT_SYNC_SCHEMA" ]]; then
        return 1
    fi

    # Apply schema (IF NOT EXISTS makes this idempotent)
    sqlite3 "$COPILOT_SYNC_DB" < "$COPILOT_SYNC_SCHEMA" 2>/dev/null || return 1

    return 0
}

# --------------------------------------------------------------------------
# copilot_log_start_session — Create a new session row.
#
# Outputs the session_id (UUID) to stdout.
# Args: none (cwd and device are auto-detected)
# --------------------------------------------------------------------------
copilot_log_start_session() {
    local session_id
    local cwd
    local device

    # Generate UUID — uuidgen is available on macOS; fall back to /proc/sys on Linux
    if command -v uuidgen >/dev/null 2>&1; then
        session_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
    elif [[ -r /proc/sys/kernel/random/uuid ]]; then
        session_id="$(cat /proc/sys/kernel/random/uuid)"
    else
        # Last resort: timestamp + random
        session_id="$(date +%s)-$$-${RANDOM}"
    fi

    cwd="$(pwd 2>/dev/null || echo '')"

    # Detect device name: prefer Tailscale hostname, fall back to system hostname
    if command -v tailscale >/dev/null 2>&1; then
        device="$(tailscale status --self --json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("Self",{}).get("HostName",""))' 2>/dev/null || hostname -s 2>/dev/null || echo 'unknown')"
    else
        device="$(hostname -s 2>/dev/null || echo 'unknown')"
    fi

    # Sanitize for SQL (escape single quotes)
    cwd="${cwd//\'/\'\'}"
    device="${device//\'/\'\'}"

    sqlite3 "$COPILOT_SYNC_DB" \
        "INSERT INTO sessions (session_id, cwd, device) VALUES ('${session_id}', '${cwd}', '${device}');" \
        2>/dev/null || return 1

    echo "$session_id"
}

# --------------------------------------------------------------------------
# copilot_log_end_session — Mark a session as ended.
#
# Args:
#   $1 — session_id
# --------------------------------------------------------------------------
copilot_log_end_session() {
    local session_id="${1:-}"
    [[ -z "$session_id" ]] && return 1

    sqlite3 "$COPILOT_SYNC_DB" \
        "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE session_id = '${session_id}';" \
        2>/dev/null || return 1
}

# --------------------------------------------------------------------------
# copilot_log_interaction — Insert an interaction row.
#
# Args (positional):
#   $1 — session_id       (required)
#   $2 — subcommand       (required, e.g. 'suggest', 'explain')
#   $3 — prompt           (optional)
#   $4 — response         (optional)
#   $5 — cwd              (optional, defaults to $PWD)
#   $6 — exit_code        (optional, integer)
#   $7 — duration_ms      (optional, integer)
#   $8 — raw_log_path     (optional)
# --------------------------------------------------------------------------
copilot_log_interaction() {
    local session_id="${1:-}"
    local subcommand="${2:-}"
    local prompt="${3:-}"
    local response="${4:-}"
    local cwd="${5:-$(pwd 2>/dev/null || echo '')}"
    local exit_code="${6:-}"
    local duration_ms="${7:-}"
    local raw_log_path="${8:-}"

    # session_id and subcommand are required
    [[ -z "$session_id" || -z "$subcommand" ]] && return 1

    # Escape single quotes for SQL safety
    session_id="${session_id//\'/\'\'}"
    subcommand="${subcommand//\'/\'\'}"
    prompt="${prompt//\'/\'\'}"
    response="${response//\'/\'\'}"
    cwd="${cwd//\'/\'\'}"
    raw_log_path="${raw_log_path//\'/\'\'}"

    # Build NULL-safe values for optional integer fields
    local exit_code_val="NULL"
    if [[ -n "$exit_code" ]]; then
        exit_code_val="$exit_code"
    fi

    local duration_ms_val="NULL"
    if [[ -n "$duration_ms" ]]; then
        duration_ms_val="$duration_ms"
    fi

    local raw_log_val="NULL"
    if [[ -n "$raw_log_path" ]]; then
        raw_log_val="'${raw_log_path}'"
    fi

    sqlite3 "$COPILOT_SYNC_DB" \
        "INSERT INTO interactions (session_id, subcommand, prompt, response, cwd, exit_code, duration_ms, raw_log_path)
         VALUES ('${session_id}', '${subcommand}', '${prompt}', '${response}', '${cwd}', ${exit_code_val}, ${duration_ms_val}, ${raw_log_val});" \
        2>/dev/null || return 1
}
