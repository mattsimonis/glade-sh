"""
test_uploads.py — Tests for image upload and serving endpoints.
"""

import base64
import os

from conftest import assert_cors


# Minimal 1×1 transparent PNG (44 bytes decoded)
_PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQ"
    "AABjkB6QAAAABJRU5ErkJggg=="
)


# ── Upload ────────────────────────────────────────────────────────────────────


def test_upload_image_valid_png_returns_path_and_url(client):
    status, data, headers = client.post(
        "/api/upload-image", {"data": _PNG_1X1, "type": "image/png"}
    )
    assert status == 200
    assert "path" in data
    assert "url" in data
    assert "filename" in data
    assert data["url"].startswith("/api/uploads/")
    assert data["filename"].endswith(".png")
    assert_cors(headers)


def test_upload_image_file_is_written_to_disk(client):
    _, data, _ = client.post(
        "/api/upload-image", {"data": _PNG_1X1, "type": "image/png"}
    )
    assert os.path.isfile(data["path"])


def test_upload_image_jpeg_gets_jpg_extension(client):
    # Use same PNG bytes but declare JPEG — extension is what matters for the test
    _, data, _ = client.post(
        "/api/upload-image", {"data": _PNG_1X1, "type": "image/jpeg"}
    )
    assert data["filename"].endswith(".jpg")


def test_upload_image_too_large_closes_connection(client):
    """
    read_json() hard-caps at 4 MB. A body larger than that drains the socket
    and raises ValueError — the connection closes without a response.
    This is the actual rejection mechanism for oversized requests.
    """
    import http.client

    big = "A" * (4 * 1024 * 1024 + 1)
    try:
        status, data, _ = client.post("/api/upload-image", {"data": big, "type": "image/png"})
        # If a response arrived it must be an error code
        assert status >= 400
    except (http.client.RemoteDisconnected, ConnectionResetError):
        pass  # expected — server closed connection on oversized body


def test_upload_image_invalid_base64_returns_400(client):
    status, data, headers = client.post(
        "/api/upload-image", {"data": "!!!not-base64!!!", "type": "image/png"}
    )
    assert status == 400
    assert_cors(headers)


# ── List uploads ──────────────────────────────────────────────────────────────


def test_list_uploads_empty_when_no_dir(client, monkeypatch, tmp_path):
    import api
    monkeypatch.setattr(api, "UPLOADS_DIR", str(tmp_path / "nonexistent"))
    status, data, headers = client.get("/api/uploads")
    assert status == 200
    assert data == []
    assert_cors(headers)


def test_list_uploads_returns_uploaded_files(client):
    client.post("/api/upload-image", {"data": _PNG_1X1, "type": "image/png"})
    client.post("/api/upload-image", {"data": _PNG_1X1, "type": "image/png"})

    status, data, headers = client.get("/api/uploads")
    assert status == 200
    assert len(data) == 2
    assert_cors(headers)

    entry = data[0]
    assert "filename" in entry
    assert "url" in entry
    assert "size" in entry
    assert "created_at" in entry


def test_list_uploads_capped_at_ten(client):
    for _ in range(12):
        client.post("/api/upload-image", {"data": _PNG_1X1, "type": "image/png"})

    _, data, _ = client.get("/api/uploads")
    assert len(data) <= 10


# ── Serve ─────────────────────────────────────────────────────────────────────


def test_serve_upload_returns_correct_mime_type(client):
    _, upload, _ = client.post("/api/upload-image", {"data": _PNG_1X1, "type": "image/png"})
    filename = upload["filename"]

    status, body, headers = client.get(f"/api/uploads/{filename}")
    assert status == 200
    assert "image" in headers.get("Content-Type", "")
    assert isinstance(body, bytes)  # binary content returned as bytes


def test_serve_upload_not_found_returns_404(client):
    status, data, headers = client.get("/api/uploads/ghost.png")
    assert status == 404
    assert_cors(headers)


def test_serve_upload_path_traversal_returns_400(client):
    # ".." inside a filename segment triggers the guard in _serve_upload
    status, data, headers = client.get("/api/uploads/..etc")
    assert status == 400
    assert_cors(headers)


def test_serve_upload_filename_with_dotdot_returns_400(client):
    status, data, _ = client.get("/api/uploads/..passwd")
    assert status == 400
