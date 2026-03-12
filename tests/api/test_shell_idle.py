"""
test_shell_idle.py — Tests for GET /api/projects/:id/shell-idle

The endpoint asks tmux for pane_current_command and returns
{idle: bool, command: str}.  Shell names (bash, zsh, fish, …) are
considered idle; anything else (vim, python, node, …) is not.
"""

import subprocess
from types import SimpleNamespace

import api
from conftest import assert_cors


# ── Helpers ───────────────────────────────────────────────────────────────────


def _tmux_result(stdout: str, returncode: int = 0):
    """Return a subprocess.CompletedProcess stub with the given stdout."""
    return SimpleNamespace(stdout=stdout, returncode=returncode, stderr="")


def _make_project(client, name="IdleTest"):
    _, data, _ = client.post("/api/projects", {"name": name, "directory": "/tmp"})
    return data["id"]


# ── 404 for unknown project ───────────────────────────────────────────────────


def test_shell_idle_unknown_project_returns_404(client):
    status, data, headers = client.get("/api/projects/does-not-exist/shell-idle")
    assert status == 404
    assert "error" in data
    assert_cors(headers)


# ── Idle detection ────────────────────────────────────────────────────────────


def test_shell_idle_bash_is_idle(client, monkeypatch):
    pid = _make_project(client, "BashProject")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("bash\n"))
    status, data, headers = client.get(f"/api/projects/{pid}/shell-idle")
    assert status == 200
    assert data["idle"] is True
    assert data["command"] == "bash"
    assert_cors(headers)


def test_shell_idle_zsh_is_idle(client, monkeypatch):
    pid = _make_project(client, "ZshProject")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("zsh\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is True


def test_shell_idle_fish_is_idle(client, monkeypatch):
    pid = _make_project(client, "FishProject")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("fish\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is True


def test_shell_idle_sh_is_idle(client, monkeypatch):
    pid = _make_project(client, "ShProject")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("sh\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is True


def test_shell_idle_login_shell_prefix_is_idle(client, monkeypatch):
    """tmux sometimes prefixes login shell names with a dash (e.g. -bash)."""
    pid = _make_project(client, "LoginShell")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("-bash\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is True


def test_shell_idle_empty_command_is_idle(client, monkeypatch):
    """Empty pane_current_command (session not running) is treated as idle."""
    pid = _make_project(client, "EmptyCmd")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result(""))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is True


# ── Busy detection ────────────────────────────────────────────────────────────


def test_shell_idle_vim_is_not_idle(client, monkeypatch):
    pid = _make_project(client, "VimProject")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("vim\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is False
    assert data["command"] == "vim"


def test_shell_idle_python_is_not_idle(client, monkeypatch):
    pid = _make_project(client, "PyProject")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("python3\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is False


def test_shell_idle_node_is_not_idle(client, monkeypatch):
    pid = _make_project(client, "NodeProject")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("node\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is False


def test_shell_idle_long_running_command_is_not_idle(client, monkeypatch):
    pid = _make_project(client, "LongRun")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("pytest\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert data["idle"] is False


# ── Resilience ────────────────────────────────────────────────────────────────


def test_shell_idle_tmux_exception_returns_idle_true(client, monkeypatch):
    """If tmux isn't running or raises, the endpoint degrades gracefully."""
    pid = _make_project(client, "NoTmux")

    def _explode(*a, **kw):
        raise FileNotFoundError("tmux not found")

    monkeypatch.setattr(api.subprocess, "run", _explode)
    status, data, headers = client.get(f"/api/projects/{pid}/shell-idle")
    assert status == 200
    assert data["idle"] is True   # safe assumption when tmux is absent
    assert data["command"] == ""
    assert_cors(headers)


def test_shell_idle_response_has_both_fields(client, monkeypatch):
    """Response must always include both 'idle' and 'command' keys."""
    pid = _make_project(client, "FieldCheck")
    monkeypatch.setattr(api.subprocess, "run",
                        lambda *a, **kw: _tmux_result("bash\n"))
    _, data, _ = client.get(f"/api/projects/{pid}/shell-idle")
    assert "idle" in data
    assert "command" in data


# ── Tmux target uses correct session name ─────────────────────────────────────


def test_shell_idle_uses_session_name_not_slug(client, monkeypatch):
    """
    Regression: _shell_idle must call tmux with 'proj-{id[:8]}:0.0'
    (the session_name format), NOT slugify(project_name).
    A project named 'My Project' has tmux session 'proj-{id[:8]}',
    never 'my-project:0.0'.
    """
    pid = _make_project(client, "My Project")
    captured = {}

    def _capture_tmux(*args, **kwargs):
        captured["args"] = args[0] if args else []
        return _tmux_result("bash\n")

    monkeypatch.setattr(api.subprocess, "run", _capture_tmux)
    client.get(f"/api/projects/{pid}/shell-idle")

    assert "args" in captured, "subprocess.run was never called"
    cmd = captured["args"]
    # The target argument must be 'proj-{first 8 hex chars of pid}:0.0'
    expected_target = f"proj-{pid[:8]}:0.0"
    assert expected_target in cmd, (
        f"Expected tmux target '{expected_target}' in command {cmd}; "
        "got project-name slug instead — session_name() was not used"
    )
