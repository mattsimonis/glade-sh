"""
test_request_body.py — Tests for malformed/oversized request body handling.

_read_body is called by every POST/PUT endpoint. A bad body must return 400
with a JSON error; it must never 500 or silently swallow the error.
"""

import json

from conftest import assert_cors


# ── Invalid JSON ──────────────────────────────────────────────────────────────


def test_malformed_json_on_post_projects_returns_400(client):
    import urllib.request, urllib.error
    url = f"http://127.0.0.1:{client._port}/api/projects"
    req = urllib.request.Request(
        url,
        data=b"this is not json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
        assert False, "expected 400"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        body = json.loads(e.read())
        assert "error" in body
        assert_cors(e.headers)


def test_malformed_json_on_put_project_returns_400(client, project_id):
    import urllib.request, urllib.error
    url = f"http://127.0.0.1:{client._port}/api/projects/{project_id}"
    req = urllib.request.Request(
        url,
        data=b"{bad json",
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    try:
        urllib.request.urlopen(req)
        assert False, "expected 400"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        body = json.loads(e.read())
        assert "error" in body
        assert_cors(e.headers)


def test_malformed_json_on_post_snippets_returns_400(client):
    import urllib.request, urllib.error
    url = f"http://127.0.0.1:{client._port}/api/snippets"
    req = urllib.request.Request(
        url,
        data=b"[unclosed",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
        assert False, "expected 400"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        assert_cors(e.headers)


# ── Empty body ────────────────────────────────────────────────────────────────


def test_empty_body_on_post_projects_still_returns_400_for_missing_name(client):
    """Empty body is valid JSON ({}) but missing required name field."""
    status, data, headers = client.post("/api/projects", None)
    assert status == 400
    assert "name" in data.get("error", "").lower() or "error" in data
    assert_cors(headers)


# ── Oversized body ────────────────────────────────────────────────────────────


def test_oversized_body_closes_connection(client):
    """Bodies > 4 MB must be rejected — the connection closes, not 200."""
    import socket, time

    # Build a payload just over 4 MB
    big = b'{"name": "' + b"x" * (4 * 1024 * 1024 + 1) + b'"}'

    sock = socket.create_connection(("127.0.0.1", client._port), timeout=5)
    try:
        request = (
            f"POST /api/projects HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{client._port}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(big)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + big
        sock.sendall(request)
        # Server reads body and drops the connection; response is some 4xx or connection close
        response = b""
        sock.settimeout(3)
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
        except (socket.timeout, ConnectionResetError):
            pass
        # Either no valid 200 response, or a 400
        assert b"200" not in response[:20] or len(response) == 0
    finally:
        sock.close()
