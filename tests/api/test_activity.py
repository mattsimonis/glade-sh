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


def test_activity_false_when_history_unchanged(client, project_id):
    """hasActivity is False when tmux history hasn't grown since baseline."""
    client.post(f"/api/projects/{project_id}/start")
    # First poll sets the baseline (current == 0); subsequent poll sees no change.
    _, data, _ = client.get("/api/projects/activity")
    entry = next(e for e in data if e["id"] == project_id)
    assert entry["hasActivity"] is False


def test_activity_true_when_history_grows_after_baseline(client, project_id, monkeypatch):
    """hasActivity becomes True when tmux history_size exceeds the recorded baseline."""
    client.post(f"/api/projects/{project_id}/start")

    call_count = [0]

    def _history_size(sname):
        call_count[0] += 1
        # First call (baseline capture) → 0; subsequent calls → 42 (new output)
        return 0 if call_count[0] == 1 else 42

    monkeypatch.setattr(api, "tmux_history_size", _history_size)
    monkeypatch.setattr(api, "tmux_session_exists", lambda sname: True)

    # First GET establishes baseline = 0
    client.get("/api/projects/activity")
    # Second GET sees history_size = 42 > baseline = 0
    _, data, _ = client.get("/api/projects/activity")
    entry = next(e for e in data if e["id"] == project_id)
    assert entry["hasActivity"] is True


def test_activity_resets_to_false_after_viewed(client, project_id, monkeypatch):
    """PUT /viewed resets baseline so hasActivity goes back to False."""
    client.post(f"/api/projects/{project_id}/start")

    history = [42]
    monkeypatch.setattr(api, "tmux_history_size", lambda sname: history[0])
    monkeypatch.setattr(api, "tmux_session_exists", lambda sname: True)

    # Establish baseline at 0 by first call, then see growth
    call_count = [0]

    def _size(sname):
        call_count[0] += 1
        return 0 if call_count[0] == 1 else 42

    monkeypatch.setattr(api, "tmux_history_size", _size)

    client.get("/api/projects/activity")  # sets baseline = 0
    _, data, _ = client.get("/api/projects/activity")  # history = 42, hasActivity = True
    entry = next(e for e in data if e["id"] == project_id)
    assert entry["hasActivity"] is True

    # Now mark viewed — baseline advances to current (42)
    monkeypatch.setattr(api, "tmux_history_size", lambda sname: 42)
    client.put(f"/api/projects/{project_id}/viewed")

    _, data, _ = client.get("/api/projects/activity")
    entry = next(e for e in data if e["id"] == project_id)
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
