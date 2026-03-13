"""
test_settings.py — Tests for /api/settings/layout and /api/settings/compact-layout.
"""

from conftest import assert_cors


# ── Full keyboard layout ──────────────────────────────────────────────────────


def test_get_layout_returns_null_when_not_saved(client):
    """When no keyboard layout has been saved, returns 200 with null body — not 404.
    Callers guard with `if (serverLayout)`. Returning 404 shows as a red
    devtools error on every first load. See COPILOT_INSTRUCTIONS."""
    status, data, headers = client.get("/api/settings/layout")
    assert status == 200
    assert data is None
    assert_cors(headers)


def test_save_layout_returns_ok(client):
    status, data, headers = client.put("/api/settings/layout", {"rows": []})
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)


def test_get_layout_returns_saved_data(client):
    layout = {"rows": [["ctrl", "alt"], ["shift"]]}
    client.put("/api/settings/layout", layout)

    status, data, headers = client.get("/api/settings/layout")
    assert status == 200
    assert data == layout
    assert_cors(headers)


def test_layout_round_trip_complex_nested_json(client):
    layout = {
        "rows": [
            [{"key": "ctrl", "width": 2}, {"key": "alt"}],
            [{"key": "shift", "label": "⇧"}],
        ],
        "theme": "dark",
        "version": 3,
    }
    client.put("/api/settings/layout", layout)
    _, retrieved, _ = client.get("/api/settings/layout")
    assert retrieved == layout


def test_save_layout_overwrites_previous(client):
    client.put("/api/settings/layout", {"v": 1})
    client.put("/api/settings/layout", {"v": 2})
    _, data, _ = client.get("/api/settings/layout")
    assert data == {"v": 2}


# ── Compact keyboard layout ───────────────────────────────────────────────────


def test_get_compact_layout_returns_null_when_not_saved(client):
    """Same as layout — 200+null when not saved, not 404."""
    status, data, headers = client.get("/api/settings/compact-layout")
    assert status == 200
    assert data is None
    assert_cors(headers)


def test_save_compact_layout_returns_ok(client):
    status, data, headers = client.put("/api/settings/compact-layout", {"compact": True})
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)


def test_get_compact_layout_returns_saved_data(client):
    layout = {"compact": True, "rows": [["esc", "tab"]]}
    client.put("/api/settings/compact-layout", layout)

    status, data, headers = client.get("/api/settings/compact-layout")
    assert status == 200
    assert data == layout
    assert_cors(headers)


def test_compact_layout_round_trip_complex_json(client):
    layout = {"rows": [[{"key": "esc"}, {"key": "F1"}]], "fontSize": 12}
    client.put("/api/settings/compact-layout", layout)
    _, retrieved, _ = client.get("/api/settings/compact-layout")
    assert retrieved == layout


def test_layout_and_compact_layout_are_independent(client):
    """The two layout keys must not bleed into each other."""
    client.put("/api/settings/layout", {"which": "full"})
    client.put("/api/settings/compact-layout", {"which": "compact"})

    _, full, _ = client.get("/api/settings/layout")
    _, compact, _ = client.get("/api/settings/compact-layout")

    assert full == {"which": "full"}
    assert compact == {"which": "compact"}
