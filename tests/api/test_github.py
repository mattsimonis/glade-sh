"""
test_github.py — Tests for GitHub integration endpoints and project-from-repo flow.

Covers:
  GET    /api/github/auth/status
  POST   /api/github/auth/start
  DELETE /api/github/auth
  GET    /api/github/repos?q=
  POST   /api/projects  {github_repo: ...}  (clone flow)
"""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import api
import pytest
from conftest import assert_cors


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_ok(**kwargs):
    """Return a mock subprocess.run result with returncode=0."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = kwargs.get("stdout", "")
    m.stderr = kwargs.get("stderr", "")
    return m


def _run_fail(**kwargs):
    m = MagicMock()
    m.returncode = 1
    m.stdout = kwargs.get("stdout", "")
    m.stderr = kwargs.get("stderr", "error")
    return m


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/github/auth/status
# ══════════════════════════════════════════════════════════════════════════════


def test_auth_status_gh_not_installed(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    status, data, headers = client.get("/api/github/auth/status")
    assert status == 200
    assert data["connected"] is False
    assert "error" in data
    assert_cors(headers)


def test_auth_status_not_logged_in(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: _run_fail() if "status" in cmd else _run_ok(),
    )
    status, data, headers = client.get("/api/github/auth/status")
    assert status == 200
    assert data["connected"] is False
    assert_cors(headers)


def test_auth_status_logged_in_returns_username_and_avatar(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)

    user_json = json.dumps({"login": "mattdipasquale", "avatar_url": "https://avatars.example.com/u/1"})

    def _run(cmd, **kw):
        if "status" in cmd:
            return _run_ok()
        if "api" in cmd and "user" in cmd:
            return _run_ok(stdout=user_json)
        return _run_ok()

    monkeypatch.setattr(api.subprocess, "run", _run)
    status, data, headers = client.get("/api/github/auth/status")
    assert status == 200
    assert data["connected"] is True
    assert data["username"] == "mattdipasquale"
    assert "avatar_url" in data
    assert data["avatar_url"].startswith("https://")
    assert_cors(headers)


def test_auth_status_logged_in_but_user_api_fails_still_connected(client, monkeypatch):
    """gh auth status succeeds but gh api user fails — still report connected."""
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)

    def _run(cmd, **kw):
        if "status" in cmd:
            return _run_ok()
        if "api" in cmd:
            return _run_fail()
        return _run_ok()

    monkeypatch.setattr(api.subprocess, "run", _run)
    status, data, _ = client.get("/api/github/auth/status")
    assert status == 200
    assert data["connected"] is True


def test_auth_status_exception_returns_connected_false(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(api.subprocess, "run", MagicMock(side_effect=OSError("boom")))
    status, data, _ = client.get("/api/github/auth/status")
    assert status == 200
    assert data["connected"] is False
    assert "error" in data


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/github/auth/start
# ══════════════════════════════════════════════════════════════════════════════


def _make_auth_proc(lines):
    """Build a mock Popen proc whose stdout yields the given lines."""
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stdout = iter(lines)
    return proc


def test_auth_start_gh_not_installed_returns_503(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    status, data, headers = client.post("/api/github/auth/start")
    assert status == 503
    assert "error" in data
    assert_cors(headers)


def test_auth_start_returns_user_code_and_uri(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)

    lines = [
        "First, copy your one-time code: ABCD-1234\n",
        "Then open: https://github.com/login/device\n",
        "Waiting for authorization...\n",
    ]
    proc = _make_auth_proc(lines)
    monkeypatch.setattr(api.subprocess, "Popen", MagicMock(return_value=proc))
    monkeypatch.setattr(api, "_gh_auth_proc", None)

    status, data, headers = client.post("/api/github/auth/start")
    assert status == 200
    assert data["user_code"] == "ABCD-1234"
    assert "github.com/login/device" in data["verification_uri"]
    assert_cors(headers)


def test_auth_start_parses_code_with_colon_format(client, monkeypatch):
    """Handle 'one-time code: XXXX-XXXX' format with colon."""
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)

    lines = [
        "! First copy your one-time code: ZZZZ-9999\n",
        "- Open this URL: https://github.com/login/device\n",
    ]
    proc = _make_auth_proc(lines)
    monkeypatch.setattr(api.subprocess, "Popen", MagicMock(return_value=proc))
    monkeypatch.setattr(api, "_gh_auth_proc", None)

    status, data, _ = client.post("/api/github/auth/start")
    assert status == 200
    assert data["user_code"] == "ZZZZ-9999"


def test_auth_start_no_code_in_output_returns_503(client, monkeypatch):
    """If gh produces no one-time code within deadline, return 503."""
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)

    # Patch time so the deadline expires instantly
    lines = ["Some unrelated output\n", "Still nothing\n"]
    proc = _make_auth_proc(lines)
    monkeypatch.setattr(api.subprocess, "Popen", MagicMock(return_value=proc))
    monkeypatch.setattr(api, "_gh_auth_proc", None)

    # Force deadline to already be past so the loop exits immediately
    import time as _time
    monkeypatch.setattr(api, "time", MagicMock(time=MagicMock(return_value=float("inf"))))

    status, data, _ = client.post("/api/github/auth/start")
    assert status == 503
    assert "error" in data


def test_auth_start_terminates_existing_proc(client, monkeypatch):
    """A second start call terminates any in-flight auth process."""
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)

    old_proc = MagicMock()
    old_proc.poll.return_value = None  # still running
    monkeypatch.setattr(api, "_gh_auth_proc", old_proc)

    lines = ["one-time code: AAAA-1111\n"]
    new_proc = _make_auth_proc(lines)
    monkeypatch.setattr(api.subprocess, "Popen", MagicMock(return_value=new_proc))

    client.post("/api/github/auth/start")
    old_proc.terminate.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# DELETE /api/github/auth
# ══════════════════════════════════════════════════════════════════════════════


def test_auth_disconnect_gh_not_installed_returns_503(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    status, data, headers = client.delete("/api/github/auth")
    assert status == 503
    assert "error" in data
    assert_cors(headers)


def test_auth_disconnect_removes_hosts_file(client, monkeypatch, tmp_path):
    """Disconnect removes ~/.config/gh/hosts.yml rather than calling gh auth logout."""
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    # Create a fake hosts file
    hosts = tmp_path / "hosts.yml"
    hosts.write_text("github.com:\n  oauth_token: fake\n")
    monkeypatch.setattr(api.os.path, "exists", lambda p: str(p) == str(hosts) or os.path.exists(p))
    removed = []
    real_remove = api.os.remove
    def _remove(p):
        if str(p) == str(hosts):
            removed.append(p)
        else:
            real_remove(p)
    monkeypatch.setattr(api.os, "remove", _remove)
    # Point the hosts path to our temp file
    monkeypatch.setattr(api.os.path, "expanduser",
                        lambda p: str(hosts) if "hosts.yml" in p else p)
    status, data, headers = client.delete("/api/github/auth")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)
    assert len(removed) == 1  # hosts file was removed


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/github/repos?q=
# ══════════════════════════════════════════════════════════════════════════════

_SAMPLE_REPOS = [
    {"nameWithOwner": "alice/glade", "name": "glade", "description": "Terminal browser", "isPrivate": False},
    {"nameWithOwner": "alice/dotfiles", "name": "dotfiles", "description": "My dotfiles", "isPrivate": False},
    {"nameWithOwner": "alice/secret-project", "name": "secret-project", "description": None, "isPrivate": True},
]


def test_repos_gh_not_installed_returns_empty_list(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    status, data, headers = client.get("/api/github/repos")
    assert status == 200
    assert data == []
    assert_cors(headers)


def test_repos_returns_list_from_gh(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: _run_ok(stdout=json.dumps(_SAMPLE_REPOS)),
    )
    status, data, headers = client.get("/api/github/repos")
    assert status == 200
    assert len(data) == 3
    assert data[0]["nameWithOwner"] == "alice/glade"
    assert_cors(headers)


def test_repos_filters_by_name_query(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: _run_ok(stdout=json.dumps(_SAMPLE_REPOS)),
    )
    status, data, _ = client.get("/api/github/repos?q=glade")
    assert status == 200
    assert len(data) == 1
    assert data[0]["name"] == "glade"


def test_repos_filters_by_description_query(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: _run_ok(stdout=json.dumps(_SAMPLE_REPOS)),
    )
    status, data, _ = client.get("/api/github/repos?q=dotfiles")
    assert status == 200
    assert any(r["name"] == "dotfiles" for r in data)


def test_repos_filter_case_insensitive(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: _run_ok(stdout=json.dumps(_SAMPLE_REPOS)),
    )
    status, data, _ = client.get("/api/github/repos?q=GLADE")
    assert status == 200
    assert len(data) == 1
    assert data[0]["name"] == "glade"


def test_repos_empty_query_returns_all(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: _run_ok(stdout=json.dumps(_SAMPLE_REPOS)),
    )
    status, data, _ = client.get("/api/github/repos?q=")
    assert status == 200
    assert len(data) == 3


def test_repos_gh_command_fails_returns_empty_list(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(api.subprocess, "run", lambda cmd, **kw: _run_fail())
    status, data, _ = client.get("/api/github/repos")
    assert status == 200
    assert data == []


def test_repos_gh_exception_returns_empty_list(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(api.subprocess, "run", MagicMock(side_effect=OSError("timeout")))
    status, data, _ = client.get("/api/github/repos")
    assert status == 200
    assert data == []


def test_repos_no_matching_query_returns_empty_list(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: _run_ok(stdout=json.dumps(_SAMPLE_REPOS)),
    )
    status, data, _ = client.get("/api/github/repos?q=zzznomatch")
    assert status == 200
    assert data == []


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/projects  {github_repo: ...}  — clone flow
# ══════════════════════════════════════════════════════════════════════════════


def test_create_project_with_github_repo_clones_and_returns_201(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(api, "PROJECTS_DIR", str(tmp_path / "projects"))

    cloned = []

    def _run(cmd, **kw):
        if "clone" in cmd:
            # Simulate actual clone by creating the directory
            clone_dir = cmd[-1]
            import os; os.makedirs(clone_dir, exist_ok=True)
            cloned.append(clone_dir)
            return _run_ok()
        return _run_ok()

    monkeypatch.setattr(api.subprocess, "run", _run)

    status, data, headers = client.post(
        "/api/projects",
        {"name": "My Glade", "github_repo": "alice/glade"},
    )
    assert status == 201
    assert data["github_repo"] == "alice/glade"
    assert "glade" in data["directory"]
    assert_cors(headers)
    assert len(cloned) == 1


def test_create_project_github_repo_stored_in_db(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(api, "PROJECTS_DIR", str(tmp_path / "projects"))

    def _run(cmd, **kw):
        if "clone" in cmd:
            import os; os.makedirs(cmd[-1], exist_ok=True)
            return _run_ok()
        return _run_ok()

    monkeypatch.setattr(api.subprocess, "run", _run)

    _, created, _ = client.post("/api/projects", {"name": "Cloned", "github_repo": "alice/glade"})
    pid = created["id"]

    _, fetched, _ = client.get(f"/api/projects/{pid}")
    assert fetched["github_repo"] == "alice/glade"


def test_create_project_github_repo_directory_uses_repo_slug(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(api, "PROJECTS_DIR", str(projects_dir))

    def _run(cmd, **kw):
        if "clone" in cmd:
            import os; os.makedirs(cmd[-1], exist_ok=True)
            return _run_ok()
        return _run_ok()

    monkeypatch.setattr(api.subprocess, "run", _run)

    _, data, _ = client.post("/api/projects", {"name": "X", "github_repo": "alice/my-cool-repo"})
    assert "my-cool-repo" in data["directory"]


def test_create_project_clone_dir_collision_gets_suffix(client, monkeypatch, tmp_path):
    """If clone dir already exists, append -1, -2, etc."""
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "glade").mkdir()          # pre-existing collision
    monkeypatch.setattr(api, "PROJECTS_DIR", str(projects_dir))

    cloned_dirs = []

    def _run(cmd, **kw):
        if "clone" in cmd:
            import os; os.makedirs(cmd[-1], exist_ok=True)
            cloned_dirs.append(cmd[-1])
            return _run_ok()
        return _run_ok()

    monkeypatch.setattr(api.subprocess, "run", _run)

    _, data, _ = client.post("/api/projects", {"name": "Y", "github_repo": "alice/glade"})
    assert data["directory"].endswith("-1")
    assert cloned_dirs[0].endswith("-1")


def test_create_project_clone_failure_returns_422(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    monkeypatch.setattr(api, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: _run_fail(stderr="repository not found") if "clone" in cmd else _run_ok(),
    )

    status, data, headers = client.post(
        "/api/projects", {"name": "Bad", "github_repo": "alice/does-not-exist"}
    )
    assert status == 422
    assert "error" in data
    assert "Clone failed" in data["error"]
    assert_cors(headers)


def test_create_project_github_repo_gh_missing_returns_503(client, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    status, data, headers = client.post(
        "/api/projects", {"name": "Needs GH", "github_repo": "alice/glade"}
    )
    assert status == 503
    assert "error" in data
    assert_cors(headers)


def test_create_project_no_github_repo_skips_clone(client, monkeypatch):
    """Ordinary project creation must NOT call gh repo clone."""
    monkeypatch.setattr(api.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    called = []
    monkeypatch.setattr(
        api.subprocess, "run",
        lambda cmd, **kw: called.append(cmd) or _run_ok(),
    )

    status, data, _ = client.post("/api/projects", {"name": "Plain", "directory": "/tmp"})
    assert status == 201
    assert data["github_repo"] is None
    assert not any("clone" in c for c in called)
