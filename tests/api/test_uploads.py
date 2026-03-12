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

# Minimal plain-text content (base64-encoded)
_TXT_HELLO = base64.b64encode(b"Hello, Glade!\n").decode()


# ── Upload images ─────────────────────────────────────────────────────────────


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


def test_upload_image_returns_mime_field(client):
    _, data, _ = client.post(
        "/api/upload-image", {"data": _PNG_1X1, "type": "image/png"}
    )
    assert data["mime"] == "image/png"


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


# ── Universal file upload ─────────────────────────────────────────────────────


def test_upload_text_file_gets_txt_extension(client):
    """Plain-text files should be stored with a .txt extension."""
    status, data, headers = client.post(
        "/api/upload-image", {"data": _TXT_HELLO, "type": "text/plain"}
    )
    assert status == 200
    assert data["filename"].endswith(".txt")
    assert data["mime"] == "text/plain"
    assert_cors(headers)


def test_upload_with_original_filename_preserves_extension(client):
    """When a filename is provided the server uses its extension."""
    status, data, _ = client.post(
        "/api/upload-image",
        {"data": _TXT_HELLO, "type": "text/plain", "filename": "notes.md"},
    )
    assert status == 200
    assert data["filename"].endswith(".md")


def test_upload_filename_path_traversal_stripped(client):
    """A malicious filename containing path separators must be sanitised."""
    status, data, _ = client.post(
        "/api/upload-image",
        {"data": _TXT_HELLO, "type": "text/plain", "filename": "../etc/passwd"},
    )
    # Server should reject or sanitise — either a 4xx or a safe filename
    if status == 200:
        assert "/" not in data["filename"]
        assert ".." not in data["filename"]
    else:
        assert status >= 400


def test_upload_generic_binary_uses_file_prefix(client):
    """Unknown MIME types should use the 'file-' prefix, not 'img-'."""
    status, data, _ = client.post(
        "/api/upload-image",
        {"data": _TXT_HELLO, "type": "application/octet-stream"},
    )
    assert status == 200
    assert data["filename"].startswith("file-")


def test_upload_file_written_to_disk(client):
    """Non-image upload must actually land on disk."""
    _, data, _ = client.post(
        "/api/upload-image", {"data": _TXT_HELLO, "type": "text/plain"}
    )
    assert os.path.isfile(data["path"])
    with open(data["path"], "rb") as f:
        assert f.read() == b"Hello, Glade!\n"


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


def test_list_uploads_includes_mime_field(client):
    """Each entry in the uploads list must carry a mime field."""
    client.post("/api/upload-image", {"data": _PNG_1X1, "type": "image/png"})
    _, data, _ = client.get("/api/uploads")
    assert len(data) >= 1
    assert "mime" in data[0]
    # PNG file → image/png
    assert data[0]["mime"] == "image/png"


def test_list_uploads_mime_field_for_text_file(client):
    """Text uploads must report the correct MIME type in the list."""
    client.post(
        "/api/upload-image",
        {"data": _TXT_HELLO, "type": "text/plain", "filename": "readme.txt"},
    )
    _, data, _ = client.get("/api/uploads")
    txt_entry = next((e for e in data if e["filename"].endswith(".txt")), None)
    assert txt_entry is not None
    assert "text" in txt_entry["mime"]


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


def test_serve_upload_text_file_returns_text_content(client):
    _, upload, _ = client.post(
        "/api/upload-image",
        {"data": _TXT_HELLO, "type": "text/plain", "filename": "hello.txt"},
    )
    filename = upload["filename"]
    status, body, headers = client.get(f"/api/uploads/{filename}")
    assert status == 200
    # _Client decodes text/plain to str; check content equality
    assert "Hello, Glade!" in body


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
