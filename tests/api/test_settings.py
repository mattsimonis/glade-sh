"""
test_settings.py — Tests for settings endpoints: layout, compact-layout, term-theme.
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


# ── Terminal theme ─────────────────────────────────────────────────────────────


def test_get_term_theme_returns_null_when_not_saved(client):
    """Same contract as layout: 200 + null when unset, not 404."""
    status, data, headers = client.get("/api/settings/term-theme")
    assert status == 200
    assert data is None
    assert_cors(headers)


def test_put_term_theme_with_string_name_returns_ok(client):
    status, data, headers = client.put("/api/settings/term-theme", "mocha")
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)


def test_get_term_theme_returns_saved_string(client):
    client.put("/api/settings/term-theme", "latte")
    status, data, _ = client.get("/api/settings/term-theme")
    assert status == 200
    assert data == "latte"


def test_put_term_theme_with_dict_object_returns_ok(client):
    """Base16 themes persist as full xterm.js theme dicts, not named strings."""
    theme = {
        "background": "#1d2021",
        "foreground": "#d5c4a1",
        "cursor": "#d5c4a1",
        "black": "#1d2021",
        "red": "#fb4934",
    }
    status, data, headers = client.put("/api/settings/term-theme", theme)
    assert status == 200
    assert data["ok"] is True
    assert_cors(headers)


def test_get_term_theme_returns_saved_dict(client):
    theme = {"background": "#002b36", "foreground": "#839496"}
    client.put("/api/settings/term-theme", theme)
    status, data, _ = client.get("/api/settings/term-theme")
    assert status == 200
    assert data == theme


def test_term_theme_string_round_trip(client):
    client.put("/api/settings/term-theme", "solarized-dark")
    _, data, _ = client.get("/api/settings/term-theme")
    assert data == "solarized-dark"


def test_term_theme_dict_round_trip(client):
    theme = {
        "background": "#282828",
        "foreground": "#ebdbb2",
        "cursor": "#ebdbb2",
        "black": "#282828",
        "red": "#cc241d",
        "green": "#98971a",
        "yellow": "#d79921",
        "blue": "#458588",
        "magenta": "#b16286",
        "cyan": "#689d6a",
        "white": "#a89984",
        "brightBlack": "#928374",
        "brightRed": "#fb4934",
        "brightGreen": "#b8bb26",
        "brightYellow": "#fabd2f",
        "brightBlue": "#83a598",
        "brightMagenta": "#d3869b",
        "brightCyan": "#8ec07c",
        "brightWhite": "#ebdbb2",
    }
    client.put("/api/settings/term-theme", theme)
    _, data, _ = client.get("/api/settings/term-theme")
    assert data == theme


def test_term_theme_overwrite_string_with_dict(client):
    """Switching from named theme to Base16 dict replaces the stored value."""
    client.put("/api/settings/term-theme", "mocha")
    theme = {"background": "#1d2021", "foreground": "#d5c4a1"}
    client.put("/api/settings/term-theme", theme)
    _, data, _ = client.get("/api/settings/term-theme")
    assert data == theme


def test_term_theme_overwrite_dict_with_string(client):
    """Switching from Base16 dict back to named theme replaces the stored value."""
    client.put("/api/settings/term-theme", {"background": "#1d2021"})
    client.put("/api/settings/term-theme", "frappe")
    _, data, _ = client.get("/api/settings/term-theme")
    assert data == "frappe"
