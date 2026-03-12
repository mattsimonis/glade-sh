"""
test_projects.py — Tests for project CRUD and lifecycle endpoints.

Regression coverage:
- "Fix terminal unclickable on desktop": start returns a valid port
- "Fall back to /root when project dir doesn't exist": start with nonexistent
  directory still returns a port, does not 500
"""

import api
from conftest import assert_cors


# ── List ──────────────────────────────────────────────────────────────────────


def test_list_projects_empty(client):
    status, data, headers = client.get("/api/projects")
    assert status == 200
    assert data == []
    assert_cors(headers)


# ── Create ────────────────────────────────────────────────────────────────────


def test_create_project_returns_id_and_fields(client):
    status, data, headers = client.post(
        "/api/projects", {"name": "My Project", "directory": "/tmp", "color": "#f38ba8"}
    )
    assert status == 201
    assert "id" in data
    assert data["name"] == "My Project"
    assert data["directory"] == "/tmp"
    assert data["color"] == "#f38ba8"
    assert data["running"] is False
    assert data["port"] is None
    assert_cors(headers)


def test_create_project_missing_name_returns_400(client):
    status, data, headers = client.post("/api/projects", {"directory": "/tmp"})
    assert status == 400
    assert "error" in data
    assert_cors(headers)


def test_create_project_empty_name_returns_400(client):
    status, data, _ = client.post("/api/projects", {"name": "   "})
    assert status == 400


def test_create_project_defaults_directory_and_color(client):
    status, data, _ = client.post("/api/projects", {"name": "Defaults"})
    assert status == 201
    assert data["directory"] in ("/", "")
    assert data["color"] == "#89b4fa"


def test_create_project_appears_in_list(client):
    client.post("/api/projects", {"name": "Alpha"})
    client.post("/api/projects", {"name": "Beta"})
    _, data, _ = client.get("/api/projects")
    names = [p["name"] for p in data]
    assert "Alpha" in names
    assert "Beta" in names


# ── Get ───────────────────────────────────────────────────────────────────────


def test_get_project_returns_project(client, project):
    status, data, headers = client.get(f"/api/projects/{project['id']}")
    assert status == 200
    assert data["id"] == project["id"]
    assert data["name"] == project["name"]
    assert_cors(headers)


def test_get_project_unknown_id_returns_404(client):
    status, data, headers = client.get("/api/projects/does-not-exist")
    assert status == 404
    assert "error" in data
    assert_cors(headers)


# ── Update ────────────────────────────────────────────────────────────────────


def test_update_project_name(client, project_id):
    status, data, headers = client.put(
        f"/api/projects/{project_id}", {"name": "Renamed"}
    )
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)

    _, updated, _ = client.get(f"/api/projects/{project_id}")
    assert updated["name"] == "Renamed"


def test_update_project_color(client, project_id):
    status, data, _ = client.put(f"/api/projects/{project_id}", {"color": "#f38ba8"})
    assert status == 200

    _, updated, _ = client.get(f"/api/projects/{project_id}")
    assert updated["color"] == "#f38ba8"


def test_update_project_no_fields_returns_400(client, project_id):
    status, data, headers = client.put(f"/api/projects/{project_id}", {})
    assert status == 400
    assert "error" in data
    assert_cors(headers)


# ── Delete ────────────────────────────────────────────────────────────────────


def test_delete_project_removes_it(client, project_id):
    status, data, headers = client.delete(f"/api/projects/{project_id}")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)

    _, remaining, _ = client.get("/api/projects")
    assert all(p["id"] != project_id for p in remaining)


def test_delete_project_not_in_list_after_deletion(client):
    _, p, _ = client.post("/api/projects", {"name": "Temporary"})
    pid = p["id"]
    client.delete(f"/api/projects/{pid}")
    _, projects, _ = client.get("/api/projects")
    assert not any(x["id"] == pid for x in projects)


# ── Start ─────────────────────────────────────────────────────────────────────


def test_start_project_returns_port_and_shells(client, project_id):
    status, data, headers = client.post(f"/api/projects/{project_id}/start")
    assert status == 200
    assert isinstance(data["port"], int)
    assert data["port"] == 7690  # first in pool with fresh _ttyd_procs
    assert isinstance(data["shells"], list)
    assert len(data["shells"]) >= 1
    assert data["shells"][0]["port"] == 7690
    assert_cors(headers)


def test_start_project_unknown_id_returns_404(client):
    status, data, headers = client.post("/api/projects/no-such-project/start")
    assert status == 404
    assert_cors(headers)


def test_start_project_with_nonexistent_directory_still_returns_port(client):
    """Regression: fall back to /root when project dir doesn't exist."""
    _, p, _ = client.post(
        "/api/projects", {"name": "NoDir", "directory": "/nonexistent/path/xyz"}
    )
    status, data, _ = client.post(f"/api/projects/{p['id']}/start")
    # Should not fail — ensure_project_running falls back to /root
    assert status == 200
    assert isinstance(data["port"], int)


def test_start_project_second_call_returns_same_port(client, project_id):
    """Starting a running project returns the existing ttyd port."""
    _, first, _ = client.post(f"/api/projects/{project_id}/start")
    _, second, _ = client.post(f"/api/projects/{project_id}/start")
    assert first["port"] == second["port"]


def test_start_project_marks_project_running(client, project_id):
    client.post(f"/api/projects/{project_id}/start")
    _, project, _ = client.get(f"/api/projects/{project_id}")
    assert project["running"] is True
    assert project["port"] == 7690


# ── Stop ──────────────────────────────────────────────────────────────────────


def test_stop_project_returns_ok(client, started_project):
    pid = started_project["id"]
    status, data, headers = client.post(f"/api/projects/{pid}/stop")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)


def test_stop_project_clears_running_state(client, started_project):
    pid = started_project["id"]
    client.post(f"/api/projects/{pid}/stop")
    _, proj, _ = client.get(f"/api/projects/{pid}")
    assert proj["running"] is False


# ── CORS on error responses ───────────────────────────────────────────────────


def test_cors_present_on_404(client):
    _, _, headers = client.get("/api/projects/nonexistent")
    assert_cors(headers)


def test_cors_present_on_400(client):
    _, _, headers = client.post("/api/projects", {"name": ""})
    assert_cors(headers)


def test_cors_present_on_503(client, project_id, monkeypatch):
    """Regression: CORS header must appear even when port pool is exhausted."""
    monkeypatch.setattr(api, "get_free_port", lambda: None)
    _, _, headers = client.post(f"/api/projects/{project_id}/start")
    assert_cors(headers)


# ── github_repo field in list and get responses ───────────────────────────────


def test_list_projects_includes_github_repo_field(client):
    """GET /api/projects must return github_repo for every project."""
    client.post("/api/projects", {"name": "Plain"})
    _, data, _ = client.get("/api/projects")
    assert len(data) >= 1
    for p in data:
        assert "github_repo" in p


def test_list_projects_github_repo_null_for_plain_project(client):
    _, created, _ = client.post("/api/projects", {"name": "No Repo"})
    _, data, _ = client.get("/api/projects")
    entry = next(p for p in data if p["id"] == created["id"])
    assert entry["github_repo"] is None


def test_get_project_includes_github_repo_field(client, project):
    _, data, _ = client.get(f"/api/projects/{project['id']}")
    assert "github_repo" in data
    assert data["github_repo"] is None
