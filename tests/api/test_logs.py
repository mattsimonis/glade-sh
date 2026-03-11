"""
test_logs.py — Tests for session log endpoints.

Security coverage:
- Path traversal (..) in project name or filename must return 400.
"""

import os

import api
from conftest import assert_cors


# ── List ──────────────────────────────────────────────────────────────────────


def test_list_logs_empty_when_no_logs_dir(client, monkeypatch, tmp_path):
    """If LOGS_DIR doesn't exist, return an empty list."""
    monkeypatch.setattr(api, "LOGS_DIR", str(tmp_path / "nonexistent"))
    status, data, headers = client.get("/api/logs")
    assert status == 200
    assert data == []
    assert_cors(headers)


def test_list_logs_returns_log_files(client, logs_dir):
    slug_dir = logs_dir / "myproject"
    slug_dir.mkdir()
    (slug_dir / "2024-01-01_10-00-00.log").write_text("session output")
    (slug_dir / "2024-01-02_11-00-00.log").write_text("another session")

    status, data, headers = client.get("/api/logs")
    assert status == 200
    assert len(data) == 2
    files = [e["file"] for e in data]
    assert "2024-01-01_10-00-00.log" in files
    assert "2024-01-02_11-00-00.log" in files
    assert_cors(headers)


def test_list_logs_entry_has_expected_fields(client, logs_dir):
    slug_dir = logs_dir / "proj-a"
    slug_dir.mkdir()
    (slug_dir / "2024-03-15_09-00-00.log").write_text("output")

    _, data, _ = client.get("/api/logs")
    entry = data[0]
    assert "project" in entry
    assert "file" in entry
    assert "size" in entry
    assert "mtime" in entry
    assert "active" in entry


# ── Get file ──────────────────────────────────────────────────────────────────


def test_get_log_file_returns_content(client, logs_dir):
    slug_dir = logs_dir / "myproject"
    slug_dir.mkdir()
    (slug_dir / "session.log").write_text("hello world\nline 2\n")

    status, data, headers = client.get("/api/logs/myproject/session.log")
    assert status == 200
    assert "hello world" in data
    assert "line 2" in data


def test_get_log_file_tail_returns_last_n_lines(client, logs_dir):
    slug_dir = logs_dir / "proj"
    slug_dir.mkdir()
    content = "\n".join(f"line {i}" for i in range(1, 21))  # 20 lines
    (slug_dir / "session.log").write_text(content)

    status, data, _ = client.get("/api/logs/proj/session.log?tail=5")
    assert status == 200
    lines = data.strip().splitlines()
    assert len(lines) == 5
    assert lines[0] == "line 16"
    assert lines[-1] == "line 20"


def test_get_log_file_unknown_project_returns_404(client, logs_dir):
    status, data, headers = client.get("/api/logs/no-such-project/session.log")
    assert status == 404
    assert_cors(headers)


def test_get_log_file_path_traversal_in_project_returns_400(client):
    # ".." inside the project segment triggers the guard in _get_log_file
    status, data, headers = client.get("/api/logs/..project/session.log")
    assert status == 400
    assert "error" in data
    assert_cors(headers)


def test_get_log_file_path_traversal_in_filename_returns_400(client):
    # ".." inside the filename segment triggers the guard in _get_log_file
    status, data, headers = client.get("/api/logs/myproject/..session.log")
    assert status == 400
    assert "error" in data
    assert_cors(headers)


# ── Delete ────────────────────────────────────────────────────────────────────


def test_delete_log_file_removes_it(client, logs_dir):
    slug_dir = logs_dir / "proj"
    slug_dir.mkdir()
    log = slug_dir / "2024-01-01_00-00-00.log"
    log.write_text("to be deleted")

    status, data, headers = client.delete("/api/logs/proj/2024-01-01_00-00-00.log")
    assert status == 200
    assert data["ok"] is True
    assert not log.exists()
    assert_cors(headers)


def test_delete_log_file_not_found_returns_404(client, logs_dir):
    (logs_dir / "proj").mkdir()
    status, data, _ = client.delete("/api/logs/proj/ghost.log")
    assert status == 404


def test_delete_log_path_traversal_returns_400(client):
    # ".." inside the project segment triggers the guard
    status, data, headers = client.delete("/api/logs/..proj/2024-01-01_00-00-00.log")
    assert status == 400
    assert_cors(headers)


def test_delete_log_path_traversal_in_filename_returns_400(client):
    # ".." inside the filename segment triggers the guard
    status, data, _ = client.delete("/api/logs/myproject/..session.log")
    assert status == 400


# ── Search ────────────────────────────────────────────────────────────────────


def test_search_logs_empty_query_returns_empty(client):
    status, data, headers = client.get("/api/logs/search?q=")
    assert status == 200
    assert data == []
    assert_cors(headers)


def test_search_logs_finds_matching_content(client, logs_dir, monkeypatch):
    """Search locates text in log files and strips ANSI codes from results."""
    slug_dir = logs_dir / "proj"
    slug_dir.mkdir()
    log_file = slug_dir / "2024-01-01_00-00-00.log"
    log_file.write_text("normal line\nhello world\nanother line\n")

    # grep mock: return the log file path
    from unittest.mock import MagicMock

    def _mock_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        if cmd[0] == "grep":
            r.stdout = str(log_file) + "\n"
        else:
            r.stdout = ""
        r.stderr = ""
        return r

    monkeypatch.setattr(api.subprocess, "run", _mock_run)

    import urllib.parse

    status, data, _ = client.get(
        f"/api/logs/search?q={urllib.parse.quote('hello world')}"
    )
    assert status == 200
    assert len(data) >= 1
    assert data[0]["project"] == "proj"
    assert any("hello world" in m["text"] for m in data[0]["matches"])


def test_search_logs_strips_ansi_from_results(client, logs_dir, monkeypatch):
    slug_dir = logs_dir / "ansi-proj"
    slug_dir.mkdir()
    log_file = slug_dir / "session.log"
    log_file.write_text("\x1b[32mhello\x1b[0m world\n")

    from unittest.mock import MagicMock

    def _mock_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stdout = str(log_file) + "\n" if cmd[0] == "grep" else ""
        r.stderr = ""
        return r

    monkeypatch.setattr(api.subprocess, "run", _mock_run)

    import urllib.parse

    status, data, _ = client.get(
        f"/api/logs/search?q={urllib.parse.quote('hello')}"
    )
    assert status == 200
    assert data
    text = data[0]["matches"][0]["text"]
    assert "\x1b[" not in text
    assert "hello" in text


# ── Current (active session tail) ────────────────────────────────────────────


def test_tail_current_log_returns_last_lines(client, logs_dir):
    slug_dir = logs_dir / "my-project"
    slug_dir.mkdir()
    lines = "\n".join(f"line {i}" for i in range(1, 251))  # 250 lines
    (slug_dir / "2024-01-01_10-00-00.log").write_text(lines)

    status, data, _ = client.get("/api/logs/current/my-project")
    assert status == 200
    returned_lines = data.strip().splitlines()
    assert len(returned_lines) <= 200


def test_tail_current_log_no_project_returns_404(client, logs_dir):
    status, data, headers = client.get("/api/logs/current/no-such-project")
    assert status == 404
    assert_cors(headers)


def test_tail_current_log_empty_dir_returns_404(client, logs_dir):
    (logs_dir / "empty-project").mkdir()
    status, data, _ = client.get("/api/logs/current/empty-project")
    assert status == 404


def test_tail_current_log_path_traversal_returns_400(client):
    # ".." inside the slug segment triggers the guard
    status, data, _ = client.get("/api/logs/current/..etc")
    assert status == 400
