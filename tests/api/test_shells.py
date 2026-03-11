"""
test_shells.py — Tests for tmux window (shell) management endpoints.

Regression coverage:
- "Fix tab close leaving dead iframe connection": DELETE /shells/{n} must
  remove the proc from _ttyd_procs and call terminate()
- "Navigate to next shell after closing current tab": kill_shell cleans up
"""

import api
from conftest import assert_cors


# ── List ──────────────────────────────────────────────────────────────────────


def test_list_shells_returns_empty_when_session_missing(client, project_id, monkeypatch):
    """GET /shells returns [] when tmux session doesn't exist."""

    def _run_no_session(cmd, **kwargs):
        r = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        r.returncode = 1  # has-session: not found
        r.stdout = ""
        r.stderr = ""
        return r

    monkeypatch.setattr(api.subprocess, "run", _run_no_session)

    status, data, headers = client.get(f"/api/projects/{project_id}/shells")
    assert status == 200
    assert data == []
    assert_cors(headers)


def test_list_shells_returns_windows_when_running(client, started_project):
    pid = started_project["id"]
    status, data, headers = client.get(f"/api/projects/{pid}/shells")
    assert status == 200
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["index"] == 0
    assert data[0]["name"] == "main"
    assert data[0]["active"] is True
    assert data[0]["port"] == 7690
    assert_cors(headers)


# ── Create ────────────────────────────────────────────────────────────────────


def test_new_shell_returns_index_and_port(client, started_project):
    pid = started_project["id"]
    status, data, headers = client.post(f"/api/projects/{pid}/shells")
    assert status == 201
    assert data["index"] == 1  # mock new-window returns "1"
    assert isinstance(data["port"], int)
    assert data["port"] == 7691  # second port (7690 taken by window 0)
    assert_cors(headers)


def test_new_shell_registers_proc_in_ttyd_procs(client, started_project):
    pid = started_project["id"]
    sname = api.session_name(pid)
    client.post(f"/api/projects/{pid}/shells")
    key = api._ttyd_shell_key(sname, 1)
    assert key in api._ttyd_procs


def test_new_shell_unknown_project_returns_404(client):
    status, data, headers = client.post("/api/projects/no-such/shells")
    assert status == 404
    assert_cors(headers)


def test_new_shell_project_not_running_returns_409(client, project_id, monkeypatch):
    """POST /shells returns 409 when tmux session doesn't exist."""
    from unittest.mock import MagicMock

    def _run_no_session(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 1  # any tmux command: failure / session not found
        r.stdout = ""
        r.stderr = ""
        return r

    monkeypatch.setattr(api.subprocess, "run", _run_no_session)

    status, data, headers = client.post(f"/api/projects/{project_id}/shells")
    assert status == 409
    assert "error" in data
    assert_cors(headers)


def test_new_shell_port_exhausted_returns_503(client, started_project, monkeypatch):
    """POST /shells returns 503 when port pool is exhausted."""
    monkeypatch.setattr(api, "get_free_port", lambda: None)
    pid = started_project["id"]
    status, data, headers = client.post(f"/api/projects/{pid}/shells")
    assert status == 503
    assert "error" in data
    assert_cors(headers)


# ── Delete ────────────────────────────────────────────────────────────────────


def test_kill_shell_returns_200(client, started_project):
    pid = started_project["id"]
    status, data, headers = client.delete(f"/api/projects/{pid}/shells/0")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)


def test_kill_shell_removes_proc_from_registry(client, started_project):
    """Regression: DELETE /shells/{n} must clean up the ttyd proc entry."""
    pid = started_project["id"]
    sname = api.session_name(pid)
    shell_key = api._ttyd_shell_key(sname, 0)

    # Entry exists after start
    assert shell_key in api._ttyd_procs

    client.delete(f"/api/projects/{pid}/shells/0")

    assert shell_key not in api._ttyd_procs


def test_kill_shell_calls_terminate_on_process(client, started_project):
    """Regression: ttyd proc must be terminated when a tab is closed."""
    pid = started_project["id"]
    sname = api.session_name(pid)
    shell_key = api._ttyd_shell_key(sname, 0)

    proc = api._ttyd_procs[shell_key]["process"]
    client.delete(f"/api/projects/{pid}/shells/0")
    proc.terminate.assert_called_once()


def test_kill_shell_nonexistent_index_still_returns_200(client, started_project):
    """kill_shell is idempotent — missing entry is a no-op."""
    pid = started_project["id"]
    status, data, _ = client.delete(f"/api/projects/{pid}/shells/99")
    assert status == 200
    assert data["ok"] is True


# ── Select ────────────────────────────────────────────────────────────────────


def test_select_shell_returns_ok(client, started_project):
    pid = started_project["id"]
    status, data, headers = client.put(f"/api/projects/{pid}/shells/0/select")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)
