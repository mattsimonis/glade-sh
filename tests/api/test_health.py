"""
test_health.py — Tests for /api/health, /api/rebuild, OPTIONS, and 404.
"""

import os

from conftest import assert_cors


def test_health_returns_ok(client):
    status, data, headers = client.get("/api/health")
    assert status == 200
    assert data["ok"] is True
    assert data["update_pending"] is False
    assert data["image_update_pending"] is False
    assert_cors(headers)


def test_health_includes_build_date_field(client):
    """GET /api/health must always include build_date (added in 'add build ver' commit)."""
    _, data, _ = client.get("/api/health")
    assert "build_date" in data


def test_health_build_date_defaults_to_empty_string(client, monkeypatch):
    monkeypatch.delenv("GLADE_BUILD_DATE", raising=False)
    _, data, _ = client.get("/api/health")
    assert data["build_date"] == ""


def test_health_build_date_reads_from_env(client, monkeypatch):
    monkeypatch.setenv("GLADE_BUILD_DATE", "2026-03-12")
    _, data, _ = client.get("/api/health")
    assert data["build_date"] == "2026-03-12"


def test_health_update_pending_when_flag_exists(client):
    flag = "/tmp/glade-update-pending"
    open(flag, "w").close()
    try:
        status, data, _ = client.get("/api/health")
        assert status == 200
        assert data["update_pending"] is True
        assert data["image_update_pending"] is False
    finally:
        os.unlink(flag)


def test_health_image_update_pending_when_flag_exists(client):
    flag = "/tmp/glade-image-update-pending"
    open(flag, "w").close()
    try:
        status, data, _ = client.get("/api/health")
        assert status == 200
        assert data["image_update_pending"] is True
    finally:
        os.unlink(flag)


def test_rebuild_creates_trigger_file(client):
    import api

    trigger = api.REBUILD_TRIGGER
    assert not os.path.exists(trigger)

    status, data, headers = client.post("/api/rebuild")
    assert status == 200
    assert data["ok"] is True
    assert os.path.exists(trigger)
    assert_cors(headers)


def test_rebuild_log_initially_empty(client):
    status, data, headers = client.get("/api/rebuild/log")
    assert status == 200
    assert data["log"] == ""
    assert data["running"] is False
    assert_cors(headers)


def test_rebuild_log_running_when_trigger_exists(client):
    import api

    open(api.REBUILD_TRIGGER, "w").close()

    status, data, _ = client.get("/api/rebuild/log")
    assert status == 200
    assert data["running"] is True


def test_rebuild_log_returns_content(client):
    import api

    with open(api.REBUILD_LOG, "w") as f:
        f.write("Step 1\nStep 2\n")

    status, data, _ = client.get("/api/rebuild/log")
    assert status == 200
    assert "Step 1" in data["log"]
    assert "Step 2" in data["log"]


def test_options_returns_204_with_cors(client):
    status, _, headers = client.options("/api/health")
    assert status == 204
    assert headers.get("Access-Control-Allow-Origin") == "*"
    assert "GET" in headers.get("Access-Control-Allow-Methods", "")


def test_unknown_route_returns_404(client):
    status, data, headers = client.get("/api/does-not-exist")
    assert status == 404
    assert "error" in data
    assert_cors(headers)


def test_unknown_post_returns_404(client):
    status, data, headers = client.post("/api/does-not-exist")
    assert status == 404
    assert_cors(headers)
