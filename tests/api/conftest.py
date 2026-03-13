"""
conftest.py — Test fixtures for Glade API tests.

CRITICAL BOOTSTRAP ORDER:
  1. Temp dirs created
  2. os.environ updated (DB_PATH, GLADE_DIR, etc.)
  3. socketserver.ThreadingTCPServer replaced with a null class (prevents
     api.py's module-level serve_forever() from blocking)
  4. subprocess.run patched during import (skips the pgrep port-cleanup at
     module level)
  5. api imported — module-level code runs harmlessly
  6. Patches restored; real test server started on a free port

Each test gets:
  - A fresh SQLite DB (monkeypatched DB_PATH → tmp_path/test.db)
  - Fresh LOGS / UPLOADS / GLADE dirs
  - Clean _ttyd_procs / _baselines globals
  - subprocess.run and subprocess.Popen mocked out (no real tmux/ttyd)
  - _recover_shell_procs mocked (reads /proc, unavailable on macOS)
"""

import json
import os
import socket
import sys
import tempfile
import threading
from http.client import HTTPMessage
from socketserver import ThreadingTCPServer
from unittest.mock import MagicMock, patch

import pytest

# ── 1. Temp root and environment vars (MUST precede api import) ───────────────

_tmp_root = tempfile.mkdtemp(prefix="glade_test_session_")
_DB_PATH = os.path.join(_tmp_root, "db", "test.db")
_GLADE_DIR = os.path.join(_tmp_root, "glade")
_UPLOADS_DIR = os.path.join(_tmp_root, "uploads")
_LOGS_DIR = os.path.join(_tmp_root, "logs")

os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
os.makedirs(_GLADE_DIR, exist_ok=True)
os.makedirs(_UPLOADS_DIR, exist_ok=True)
os.makedirs(_LOGS_DIR, exist_ok=True)

os.environ.update(
    {
        "DB_PATH": _DB_PATH,
        "GLADE_DIR": _GLADE_DIR,
        "UPLOADS_DIR": _UPLOADS_DIR,
        "LOGS_DIR": _LOGS_DIR,
        "PORT": "17683",
    }
)

# ── 2. Replace ThreadingTCPServer so serve_forever() is a no-op on import ────

import socketserver as _ss  # noqa: E402


class _NullServer:
    """Stands in for ThreadingTCPServer during import so the module doesn't block."""

    allow_reuse_address = True

    def __init__(self, *a, **kw):
        pass

    def serve_forever(self, *a, **kw):
        pass

    def shutdown(self):
        pass


_OrigTCPServer = _ss.ThreadingTCPServer
_ss.ThreadingTCPServer = _NullServer

# ── 3. Import api (with pgrep no-op so no real subprocess calls at import) ────

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_API_DIR = os.path.join(_REPO_ROOT, "api")
_TEST_API_DIR = os.path.dirname(os.path.abspath(__file__))

# Add both api/ and tests/api/ so `import api` and `from conftest import ...` work
for _d in (_API_DIR, _TEST_API_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

_null_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
with patch("subprocess.run", _null_run):
    import api  # noqa: E402

# Restore the real server class now that api.py is in sys.modules
_ss.ThreadingTCPServer = _OrigTCPServer

# ── 4. Start the real test server once for the whole session ──────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


TEST_PORT = _free_port()

_server = ThreadingTCPServer(("127.0.0.1", TEST_PORT), api.Handler)
_server.daemon_threads = True
_server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
_server_thread.start()

import atexit

atexit.register(_server.shutdown)

# ── 5. subprocess mock factory ────────────────────────────────────────────────


def _make_subprocess_run_mock():
    """Return a MagicMock for subprocess.run that gives sensible tmux outputs.

    Tracks session lifecycle: new-session adds to active set; kill-window and
    kill-session remove from it; has-session returns returncode=1 for unknown
    sessions so _kill_shell correctly detects last-window destruction.
    """
    _active_sessions: set = set()

    def _target_session(cmd):
        """Extract the -t value from a tmux command (strip :window suffix)."""
        for i, arg in enumerate(cmd):
            if arg == "-t" and i + 1 < len(cmd):
                return cmd[i + 1].split(":")[0]
        return None

    def _run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        if not isinstance(cmd, (list, tuple)) or len(cmd) < 2:
            return r
        if cmd[0] == "tmux":
            sub = cmd[1]
            if sub == "new-session":
                for i, arg in enumerate(cmd):
                    if arg == "-s" and i + 1 < len(cmd):
                        _active_sessions.add(cmd[i + 1])
                        break
            elif sub == "has-session":
                sname = _target_session(cmd)
                r.returncode = 0 if sname in _active_sessions else 1
            elif sub in ("kill-window", "kill-session"):
                sname = _target_session(cmd)
                if sname:
                    _active_sessions.discard(sname)
            elif sub == "list-windows":
                r.stdout = "0:main:1\n"
            elif sub == "display-message":
                r.stdout = "0\n"
            elif sub == "new-window":
                r.stdout = "1\n"
            elif sub == "list-sessions":
                r.stdout = ""
        elif cmd[0] == "grep":
            r.stdout = ""
        return r

    return MagicMock(side_effect=_run)


# ── 6. Client helper ──────────────────────────────────────────────────────────


class _Client:
    """Minimal HTTP helper that speaks to the test server."""

    _NOBODY = object()

    def __init__(self, port: int):
        self._port = port

    def _request(self, method: str, path: str, data=_NOBODY):
        import urllib.error
        import urllib.request

        if data is self._NOBODY or data is None:
            body = None
        else:
            body = json.dumps(data).encode()

        headers: dict = {"Content-Type": "application/json"} if body is not None else {}
        url = f"http://127.0.0.1:{self._port}{path}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                ct = resp.headers.get("Content-Type", "")
                raw = resp.read()
                if not raw:
                    return resp.status, {}, resp.headers
                if "json" in ct:
                    body_out = json.loads(raw)
                elif "text" in ct:
                    body_out = raw.decode("utf-8", errors="replace")
                else:
                    body_out = raw  # binary (images, etc.)
                return resp.status, body_out, resp.headers
        except urllib.error.HTTPError as e:
            raw = e.read()
            ct = e.headers.get("Content-Type", "")
            body_out = json.loads(raw) if raw and "json" in ct else (raw.decode() if raw else {})
            return e.code, body_out, e.headers

    def get(self, path):
        return self._request("GET", path)

    def options(self, path):
        return self._request("OPTIONS", path)

    def post(self, path, data=None):
        return self._request("POST", path, {} if data is None else data)

    def put(self, path, data=None):
        return self._request("PUT", path, {} if data is None else data)

    def delete(self, path):
        return self._request("DELETE", path)


# ── 7. Core per-test fixture ──────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Yield a _Client with fresh DB, dirs, and mocked subprocess."""
    db_path = tmp_path / "test.db"
    glade_dir = tmp_path / "glade"
    uploads = tmp_path / "uploads"
    logs = tmp_path / "logs"

    glade_dir.mkdir()
    uploads.mkdir()
    logs.mkdir()

    # Patch api module-level globals
    monkeypatch.setattr(api, "DB_PATH", str(db_path))
    monkeypatch.setattr(api, "GLADE_DIR", str(glade_dir))
    monkeypatch.setattr(api, "UPLOADS_DIR", str(uploads))
    monkeypatch.setattr(api, "LOGS_DIR", str(logs))
    monkeypatch.setattr(api, "REBUILD_TRIGGER", str(glade_dir / ".rebuild-requested"))
    monkeypatch.setattr(api, "REBUILD_LOCK", str(glade_dir / ".rebuild-running"))
    monkeypatch.setattr(api, "REBUILD_LOG", str(glade_dir / "rebuild.log"))

    # Reset process state
    monkeypatch.setattr(api, "_ttyd_procs", {})
    monkeypatch.setattr(api, "_baselines", {})

    # Reset port pool so get_free_port() always starts at 7690
    monkeypatch.setattr(api, "PORT_POOL", list(range(7690, 7700)))

    # Skip /proc reads — not available on macOS
    monkeypatch.setattr(api, "_recover_shell_procs", lambda: None)

    # Create DB schema in fresh file
    api.ensure_tables()

    # Mock subprocess
    mock_run = _make_subprocess_run_mock()
    monkeypatch.setattr(api.subprocess, "run", mock_run)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_popen = MagicMock(return_value=mock_proc)
    monkeypatch.setattr(api.subprocess, "Popen", mock_popen)

    yield _Client(TEST_PORT)


# ── 8. Convenience fixtures ───────────────────────────────────────────────────


@pytest.fixture
def project(client):
    """Create a project and return its response dict."""
    status, data, _ = client.post(
        "/api/projects", {"name": "Test Project", "directory": "/", "color": "#89b4fa"}
    )
    assert status == 201, f"project create failed: {data}"
    return data


@pytest.fixture
def project_id(project):
    return project["id"]


@pytest.fixture
def started_project(client, project_id):
    """Start a project (mocked) and return {id, port, shells}."""
    status, data, _ = client.post(f"/api/projects/{project_id}/start")
    assert status == 200, f"project start failed: {data}"
    return {"id": project_id, **data}


@pytest.fixture
def snippet(client):
    """Create a snippet and return its response dict."""
    status, data, _ = client.post(
        "/api/snippets", {"name": "hello", "command": "echo hello", "sort_order": 0}
    )
    assert status == 201, f"snippet create failed: {data}"
    return data


@pytest.fixture
def logs_dir(tmp_path):
    """Return the per-test logs path (same tmp_path as client fixture)."""
    d = tmp_path / "logs"
    d.mkdir(exist_ok=True)
    return d


# ── 9. Assertion helpers ──────────────────────────────────────────────────────


def assert_cors(headers):
    """Every JSON response must carry the CORS header — regression guard."""
    value = headers.get("Access-Control-Allow-Origin")
    assert value == "*", f"Missing CORS header. Got: {value!r}"
