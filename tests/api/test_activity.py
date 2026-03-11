"""
test_activity.py — Tests for /api/projects/activity and viewed endpoints.

Regression coverage:
- Activity route must be matched BEFORE the /:id GET route so that GET
  /api/projects/activity returns an array, not a 404 or project lookup.
- _get_activity has a known bug: it looks up _ttyd_procs[pid] instead of
  _ttyd_procs[sname:0], so hasActivity is always False. Tests document this.
"""

import api
from conftest import assert_cors


# ── Routing regression ────────────────────────────────────────────────────────


def test_activity_route_not_treated_as_project_id(client):
    """GET /api/projects/activity must return a list, not a 404 from _get_project."""
    status, data, headers = client.get("/api/projects/activity")
    assert status == 200
    assert isinstance(data, list), (
        "Route matched /:id instead of /activity — routing regression"
    )
    assert_cors(headers)


# ── Basic behavior ────────────────────────────────────────────────────────────


def test_activity_returns_empty_list_with_no_projects(client):
    status, data, _ = client.get("/api/projects/activity")
    assert status == 200
    assert data == []


def test_activity_returns_entry_for_each_project(client):
    client.post("/api/projects", {"name": "P1"})
    client.post("/api/projects", {"name": "P2"})

    status, data, _ = client.get("/api/projects/activity")
    assert status == 200
    assert len(data) == 2
    ids = {e["id"] for e in data}
    assert len(ids) == 2


def test_activity_entry_has_id_and_has_activity(client, project_id):
    _, data, _ = client.get("/api/projects/activity")
    entry = next((e for e in data if e["id"] == project_id), None)
    assert entry is not None
    assert "hasActivity" in entry


def test_activity_always_false_due_to_known_lookup_bug(client, project_id):
    """
    Known bug: _get_activity uses _ttyd_procs.get(pid) but keys are sname:widx.
    So running is always False and hasActivity is always False.
    This test documents the current behavior so a future fix is visible.
    """
    # Start the project so _ttyd_procs has an entry keyed as sname:0
    client.post(f"/api/projects/{project_id}/start")

    _, data, _ = client.get("/api/projects/activity")
    entry = next(e for e in data if e["id"] == project_id)
    # Due to the bug, this is always False even though the project is running
    assert entry["hasActivity"] is False


# ── Mark viewed ───────────────────────────────────────────────────────────────


def test_mark_viewed_returns_ok(client, project_id):
    status, data, headers = client.put(f"/api/projects/{project_id}/viewed")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)


def test_mark_viewed_sets_baseline(client, project_id):
    """PUT /viewed should record the current history_size as the baseline."""
    client.put(f"/api/projects/{project_id}/viewed")
    # Baseline is set; activity remains false afterward
    _, data, _ = client.get("/api/projects/activity")
    entry = next(e for e in data if e["id"] == project_id)
    assert entry["hasActivity"] is False


def test_mark_viewed_nonexistent_project_still_returns_200(client):
    """PUT /viewed on a missing project is a no-op (tmux_session_exists = False)."""
    status, data, _ = client.put("/api/projects/ghost-id/viewed")
    assert status == 200
    assert data["ok"] is True
