"""
test_snippets.py — Tests for snippet CRUD endpoints.
"""

from conftest import assert_cors


# ── List ──────────────────────────────────────────────────────────────────────


def test_list_snippets_empty(client):
    status, data, headers = client.get("/api/snippets")
    assert status == 200
    assert data == []
    assert_cors(headers)


# ── Create ────────────────────────────────────────────────────────────────────


def test_create_snippet_returns_id_name_command(client):
    status, data, headers = client.post(
        "/api/snippets", {"name": "greet", "command": "echo hi", "sort_order": 5}
    )
    assert status == 201
    assert "id" in data
    assert data["name"] == "greet"
    assert data["command"] == "echo hi"
    assert_cors(headers)


def test_create_snippet_missing_name_returns_400(client):
    status, data, headers = client.post("/api/snippets", {"command": "echo hi"})
    assert status == 400
    assert "error" in data
    assert_cors(headers)


def test_create_snippet_missing_command_returns_400(client):
    status, data, headers = client.post("/api/snippets", {"name": "greet"})
    assert status == 400
    assert "error" in data
    assert_cors(headers)


def test_create_snippet_empty_name_returns_400(client):
    status, data, _ = client.post(
        "/api/snippets", {"name": "  ", "command": "echo hi"}
    )
    assert status == 400


def test_create_snippet_empty_command_returns_400(client):
    status, data, _ = client.post(
        "/api/snippets", {"name": "greet", "command": "  "}
    )
    assert status == 400


def test_create_snippet_appears_in_list(client):
    client.post("/api/snippets", {"name": "alpha", "command": "cmd1"})
    client.post("/api/snippets", {"name": "beta", "command": "cmd2"})
    _, data, _ = client.get("/api/snippets")
    names = [s["name"] for s in data]
    assert "alpha" in names
    assert "beta" in names


def test_create_snippet_sort_order_preserved(client):
    client.post("/api/snippets", {"name": "z-last", "command": "z", "sort_order": 10})
    client.post("/api/snippets", {"name": "a-first", "command": "a", "sort_order": 1})
    _, data, _ = client.get("/api/snippets")
    assert data[0]["name"] == "a-first"
    assert data[1]["name"] == "z-last"


# ── Update ────────────────────────────────────────────────────────────────────


def test_update_snippet_name_and_command(client, snippet):
    sid = snippet["id"]
    status, data, headers = client.put(
        f"/api/snippets/{sid}", {"name": "renamed", "command": "echo renamed"}
    )
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)

    _, snippets, _ = client.get("/api/snippets")
    updated = next(s for s in snippets if s["id"] == sid)
    assert updated["name"] == "renamed"
    assert updated["command"] == "echo renamed"


def test_update_snippet_empty_name_returns_400(client, snippet):
    status, data, headers = client.put(
        f"/api/snippets/{snippet['id']}", {"name": "", "command": "echo hi"}
    )
    assert status == 400
    assert "error" in data
    assert_cors(headers)


def test_update_snippet_empty_command_returns_400(client, snippet):
    status, data, _ = client.put(
        f"/api/snippets/{snippet['id']}", {"name": "greet", "command": "  "}
    )
    assert status == 400


# ── Delete ────────────────────────────────────────────────────────────────────


def test_delete_snippet_removes_it(client, snippet):
    sid = snippet["id"]
    status, data, headers = client.delete(f"/api/snippets/{sid}")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)

    _, remaining, _ = client.get("/api/snippets")
    assert all(s["id"] != sid for s in remaining)


def test_delete_snippet_unknown_id_returns_200_no_op(client):
    """DELETE on a nonexistent snippet is a safe no-op."""
    status, data, headers = client.delete("/api/snippets/does-not-exist")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)
