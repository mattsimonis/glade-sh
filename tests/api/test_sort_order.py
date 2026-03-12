"""
test_sort_order.py — Tests for sort_order on projects and snippets.

Projects and snippets both carry a sort_order column. The list endpoints
must respect it; PUT must persist it.
"""

from conftest import assert_cors


# ══════════════════════════════════════════════════════════════════════════════
# Projects — sort_order
# ══════════════════════════════════════════════════════════════════════════════


def test_projects_listed_in_sort_order(client):
    """GET /api/projects returns rows ordered by sort_order ASC, then created_at."""
    _, a, _ = client.post("/api/projects", {"name": "Alpha"})
    _, b, _ = client.post("/api/projects", {"name": "Beta"})
    _, c, _ = client.post("/api/projects", {"name": "Gamma"})

    # Set sort_order via PUT (create doesn't accept it)
    client.put(f"/api/projects/{a['id']}", {"sort_order": 3})
    client.put(f"/api/projects/{b['id']}", {"sort_order": 1})
    client.put(f"/api/projects/{c['id']}", {"sort_order": 2})

    _, projects, _ = client.get("/api/projects")
    names = [p["name"] for p in projects]
    assert names.index("Beta") < names.index("Gamma") < names.index("Alpha")


def test_update_project_sort_order_changes_position(client):
    _, a, _ = client.post("/api/projects", {"name": "First"})
    _, b, _ = client.post("/api/projects", {"name": "Second"})

    # Give First a higher sort_order so Second naturally precedes it
    client.put(f"/api/projects/{a['id']}", {"sort_order": 10})
    client.put(f"/api/projects/{b['id']}", {"sort_order": 1})

    _, projects, _ = client.get("/api/projects")
    names = [p["name"] for p in projects]
    assert names.index("Second") < names.index("First")


def test_projects_default_sort_order_is_zero(client):
    _, p, _ = client.post("/api/projects", {"name": "NoOrder"})
    _, fetched, _ = client.get(f"/api/projects/{p['id']}")
    assert fetched.get("sort_order", 0) == 0


def test_update_project_sort_order_persists(client, project_id):
    client.put(f"/api/projects/{project_id}", {"sort_order": 42})
    _, p, _ = client.get(f"/api/projects/{project_id}")
    assert p["sort_order"] == 42


def test_projects_same_sort_order_ordered_by_created_at(client):
    """Tie-break: same sort_order → earlier created_at comes first."""
    _, a, _ = client.post("/api/projects", {"name": "Early", "sort_order": 5})
    _, b, _ = client.post("/api/projects", {"name": "Late",  "sort_order": 5})

    _, projects, _ = client.get("/api/projects")
    tied = [p["name"] for p in projects if p["name"] in ("Early", "Late")]
    assert tied == ["Early", "Late"]


# ══════════════════════════════════════════════════════════════════════════════
# Snippets — sort_order
# ══════════════════════════════════════════════════════════════════════════════


def test_snippets_listed_in_sort_order(client):
    client.post("/api/snippets", {"name": "z-last",  "command": "z", "sort_order": 10})
    client.post("/api/snippets", {"name": "a-first", "command": "a", "sort_order": 0})
    client.post("/api/snippets", {"name": "m-mid",   "command": "m", "sort_order": 5})

    _, snippets, _ = client.get("/api/snippets")
    names = [s["name"] for s in snippets]
    assert names.index("a-first") < names.index("m-mid") < names.index("z-last")


def test_update_snippet_sort_order_changes_position(client):
    _, a, _ = client.post("/api/snippets", {"name": "one", "command": "1", "sort_order": 0})
    _, b, _ = client.post("/api/snippets", {"name": "two", "command": "2", "sort_order": 1})

    # Push "two" before "one"
    client.put(f"/api/snippets/{b['id']}", {"name": "two", "command": "2", "sort_order": -1})

    _, snippets, _ = client.get("/api/snippets")
    names = [s["name"] for s in snippets]
    assert names.index("two") < names.index("one")


def test_snippet_default_sort_order_is_zero(client):
    _, s, _ = client.post("/api/snippets", {"name": "plain", "command": "echo"})
    assert s.get("sort_order", 0) == 0
