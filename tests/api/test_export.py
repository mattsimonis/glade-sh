"""
test_export.py — Tests for GET /api/export and POST /api/restart.
"""

import sqlite3
import time

import api
from conftest import assert_cors


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/export
# ══════════════════════════════════════════════════════════════════════════════


def test_export_empty_db_returns_empty_list(client):
    status, data, headers = client.get("/api/export")
    assert status == 200
    assert data == []
    assert_cors(headers)


def test_export_returns_interactions_as_json(client):
    with sqlite3.connect(api.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO interactions (session_id, subcommand, prompt, response) "
            "VALUES (?, ?, ?, ?)",
            ("sess-1", "chat", "hello", "world"),
        )

    _, data, _ = client.get("/api/export")
    assert len(data) == 1
    assert data[0]["prompt"] == "hello"
    assert data[0]["response"] == "world"


def test_export_sets_content_disposition_attachment(client):
    """Response must carry Content-Disposition: attachment so browsers download it."""
    import urllib.request

    url = f"http://127.0.0.1:{client._port}/api/export"
    with urllib.request.urlopen(url) as resp:
        cd = resp.headers.get("Content-Disposition", "")
    assert "attachment" in cd
    assert "glade-history.json" in cd


def test_export_returns_most_recent_first(client):
    with sqlite3.connect(api.DB_PATH) as conn:
        conn.execute(
            "INSERT INTO interactions (session_id, subcommand, timestamp, prompt) "
            "VALUES (?, ?, ?, ?)",
            ("s1", "chat", "2026-01-01T00:00:00", "older"),
        )
        conn.execute(
            "INSERT INTO interactions (session_id, subcommand, timestamp, prompt) "
            "VALUES (?, ?, ?, ?)",
            ("s2", "chat", "2026-03-01T00:00:00", "newer"),
        )

    _, data, _ = client.get("/api/export")
    assert data[0]["prompt"] == "newer"
    assert data[1]["prompt"] == "older"


def test_export_capped_at_500_rows(client):
    with sqlite3.connect(api.DB_PATH) as conn:
        conn.executemany(
            "INSERT INTO interactions (session_id, subcommand, prompt) VALUES (?, ?, ?)",
            [(f"s{i}", "chat", f"line {i}") for i in range(600)],
        )

    _, data, _ = client.get("/api/export")
    assert len(data) == 500


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/restart
# ══════════════════════════════════════════════════════════════════════════════


def test_restart_returns_200_ok(client, monkeypatch):
    monkeypatch.setattr(api.os, "_exit", lambda code: None)
    status, data, headers = client.post("/api/restart")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)


def test_restart_schedules_exit_42(client, monkeypatch):
    """Restart must eventually call os._exit(42) — the supervisor loop signal."""
    exited = []
    monkeypatch.setattr(api.os, "_exit", lambda code: exited.append(code))

    client.post("/api/restart")

    # Give the daemon thread (0.2s sleep) a moment to fire
    deadline = time.time() + 2.0
    while not exited and time.time() < deadline:
        time.sleep(0.05)

    assert 42 in exited
