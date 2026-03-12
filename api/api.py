#!/usr/bin/env python3
"""
glade API — projects, snippets, keyboard layout, image uploads

Runs inside the ttyd Docker container on port 7683.
Manages project lifecycle: tmux sessions + ttyd child processes.

Routes:
  GET    /api/health                    {ok, update_pending, image_update_pending}
  POST   /api/restart                   trigger graceful API restart (exit 42 → entrypoint loops)
  GET    /api/projects                  list all projects with running status
  POST   /api/projects                  create {name, directory, color}
  PUT    /api/projects/:id              update project
  DELETE /api/projects/:id              delete + stop ttyd
  POST   /api/projects/:id/start        ensure tmux + ttyd running -> {port}
  POST   /api/projects/:id/stop         kill ttyd (keep tmux session)
  GET    /api/projects/:id/shells       list tmux windows [{index,name,active}]
  POST   /api/projects/:id/shells       open new tmux window -> {index}
  DELETE /api/projects/:id/shells/:n    kill tmux window n
  GET    /api/projects/activity         [{id, hasActivity}] for badge polling
  PUT    /api/projects/:id/viewed       clear activity baseline
  GET    /api/snippets
  POST   /api/snippets
  PUT    /api/snippets/:id
  DELETE /api/snippets/:id
  GET    /api/settings/layout
  PUT    /api/settings/layout
  POST   /api/upload-image              upload base64 image -> {path, url, filename}
  GET    /api/uploads                   list recent uploads (last 10)
  GET    /api/uploads/:filename         serve uploaded file
  GET    /api/export                    export interactions as JSON
  GET    /api/rebuild/log               {log, running} — rebuild output log + running state
  POST   /api/rebuild                   write trigger file for host watcher → {ok}
  GET    /api/github/auth/status        {connected, username, avatar_url}
  POST   /api/github/auth/start         begin device flow -> {user_code, verification_uri}
  DELETE /api/github/auth               disconnect (gh auth logout)
  GET    /api/github/repos?q=           list/search user repos -> [{nameWithOwner,name,description,isPrivate}]
"""

import base64
import json
import mimetypes
import os
import re
import shlex
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import shutil
from contextlib import contextmanager
from urllib.parse import unquote
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer

DB_PATH      = os.environ.get("DB_PATH", "/root/.glade/db/history.db")
PORT         = int(os.environ.get("PORT", "7683"))
GLADE_DIR    = os.environ.get("GLADE_DIR", "/root/.glade")
UPLOADS_DIR  = os.environ.get("UPLOADS_DIR", "/root/.glade/uploads")
LOGS_DIR     = os.environ.get("LOGS_DIR", "/root/.glade/logs")

DISABLE_UPDATE_CHECK = os.environ.get("DISABLE_UPDATE_CHECK", "").lower() in ("1", "true", "yes")

REBUILD_TRIGGER = os.path.join(GLADE_DIR, ".rebuild-requested")
REBUILD_LOCK    = os.path.join(GLADE_DIR, ".rebuild-running")
REBUILD_LOG     = os.path.join(GLADE_DIR, "rebuild.log")
PROJECTS_DIR    = os.path.join(GLADE_DIR, "projects")

PORT_POOL = list(range(7690, 7700))

_gh_auth_proc = None
_gh_auth_lock = threading.Lock()

# Shell key format: f"{sname}:{window_index}"  e.g. "proj-abc12345:0"
SHELL_KEY_RE = re.compile(r'^proj-[0-9a-f]{8}:\d+$')

TTYD_THEME = (
    '{"background":"#1e1e2e","foreground":"#cdd6f4","cursor":"#f5e0dc",'
    '"cursorAccent":"#1e1e2e","selectionBackground":"#585b70","selectionForeground":"#cdd6f4",'
    '"black":"#45475a","red":"#f38ba8","green":"#a6e3a1","yellow":"#f9e2af",'
    '"blue":"#89b4fa","magenta":"#f5c2e7","cyan":"#94e2d5","white":"#7f849c",'
    '"brightBlack":"#585b70","brightRed":"#f38ba8","brightGreen":"#a6e3a1",'
    '"brightYellow":"#f9e2af","brightBlue":"#89b4fa","brightMagenta":"#f5c2e7",'
    '"brightCyan":"#94e2d5","brightWhite":"#a6adc8"}'
)

_lock       = threading.Lock()
_ttyd_procs = {}   # shell_key (sname:widx) -> {"process": Popen|None, "port": int}
_baselines  = {}   # project_id -> int (tmux history_size at last view)


@contextmanager
def open_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_tables():
    with open_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS snippets (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                command    TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS projects (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                directory   TEXT NOT NULL DEFAULT "/",
                color       TEXT NOT NULL DEFAULT "#89b4fa",
                sort_order  INTEGER DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active DATETIME
            );
            CREATE TABLE IF NOT EXISTS interactions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT,
                timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
                subcommand   TEXT NOT NULL DEFAULT '',
                prompt       TEXT,
                response     TEXT,
                cwd          TEXT,
                exit_code    INTEGER,
                duration_ms  INTEGER,
                raw_log_path TEXT
            );
        """)
        # Migrate: add github_repo column if it doesn't exist yet
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN github_repo TEXT")
        except Exception:
            pass


# ---- tmux helpers -----------------------------------------------------------

_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-B]|\x1b[>=]|[\x00-\x08\x0e-\x1f]')

def strip_ansi(text):
    return _ANSI_RE.sub('', text)


def slugify(name):
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-') or 'unnamed'


def session_name(project_id):
    return "proj-" + project_id[:8]


def tmux_session_exists(sname):
    r = subprocess.run(["tmux", "has-session", "-t", sname], capture_output=True)
    return r.returncode == 0


def start_pipe_pane(sname, log_slug):
    log_dir = os.path.join(LOGS_DIR, log_slug)
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = os.path.join(log_dir, ts + ".log")
    subprocess.run(
        ["tmux", "pipe-pane", "-o", "-t", sname, f"cat >> {log_path}"],
        capture_output=True
    )
    return log_path


def create_tmux_session(sname, directory, log_slug="_main"):
    if tmux_session_exists(sname):
        return
    effective_dir = directory if (directory and os.path.isdir(directory)) else "/root"
    subprocess.run(["tmux", "new-session", "-d", "-s", sname, "-c", effective_dir],
                   capture_output=True)
    subprocess.run(["tmux", "set", "-t", sname, "mouse", "on"], capture_output=True)
    subprocess.run(["tmux", "set", "-t", sname, "automatic-rename", "off"],
                   capture_output=True)
    subprocess.run(["tmux", "bind", "-T", "copy-mode", "WheelDownPane",
                    "if", "-F", "#{scroll_position}",
                    "send-keys -X scroll-down", "send-keys -X cancel"],
                   capture_output=True)
    start_pipe_pane(sname, log_slug)


def list_shells_tmux(sname):
    r = subprocess.run(
        ["tmux", "list-windows", "-t", sname, "-F",
         "#{window_index}:#{window_name}:#{window_active}"],
        capture_output=True, text=True
    )
    shells = []
    for line in r.stdout.strip().splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            shells.append({"index": int(parts[0]), "name": parts[1],
                           "active": parts[2] == "1"})
    return shells


def new_shell_tmux(sname, directory):
    # -d: create in background so existing ttyd clients keep their current window
    # Only pass -c if the directory actually exists in the container
    effective_dir = directory if (directory and os.path.isdir(directory)) else "/root"
    r = subprocess.run(
        ["tmux", "new-window", "-d", "-t", sname, "-c", effective_dir, "-P", "-F", "#{window_index}"],
        capture_output=True, text=True
    )
    s = r.stdout.strip()
    return int(s) if s.isdigit() else None


def select_shell_tmux(sname, index):
    subprocess.run(["tmux", "select-window", "-t", f"{sname}:{index}"],
                   capture_output=True)


def tmux_history_size(sname):
    r = subprocess.run(
        ["tmux", "display-message", "-t", sname, "-p", "#{history_size}"],
        capture_output=True, text=True
    )
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


# ---- ttyd process management ------------------------------------------------

def get_free_port():
    used = {info["port"] for info in _ttyd_procs.values()}
    for p in PORT_POOL:
        if p not in used:
            return p
    return None


def _ttyd_shell_key(sname, window_idx):
    return f"{sname}:{window_idx}"


def _recover_shell_procs():
    """Scan /proc to rebuild _ttyd_procs after an API restart.

    ttyd processes survive API restarts; we reconstruct the mapping by
    parsing each process's cmdline for:  ttyd -p PORT ... tmux attach-session -t SNAME:WIDX
    """
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as fh:
                parts = fh.read().split(b'\x00')
            if not parts[0].endswith(b'ttyd'):
                continue
            port = None
            target = None
            i = 0
            while i < len(parts):
                if parts[i] == b'-p' and i + 1 < len(parts):
                    try:
                        port = int(parts[i + 1])
                    except ValueError:
                        pass
                # look for: tmux attach-session -t TARGET
                if parts[i] == b'attach-session':
                    for j in range(i + 1, min(i + 4, len(parts))):
                        if parts[j] == b'-t' and j + 1 < len(parts):
                            t = parts[j + 1].decode('utf-8', errors='ignore')
                            if ':' in t and t.startswith('proj-'):
                                target = t
                            break
                i += 1
            if port and target:
                with _lock:
                    if target not in _ttyd_procs:
                        _ttyd_procs[target] = {"process": None, "port": port}
        except Exception:
            pass


def _shell_proc_alive(info):
    """Return True if the ttyd described by info is still running."""
    if info is None:
        return False
    proc = info.get("process")
    if proc is not None:
        return proc.poll() is None
    # Recovered process (no Popen): verify the port is still held by a ttyd in /proc
    port = info.get("port")
    if not port:
        return False
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as fh:
                raw = fh.read()
            if b'ttyd' in raw and (b'-p\x00' + str(port).encode()) in raw:
                return True
        except Exception:
            pass
    return False


def _start_shell_ttyd(sname, window_idx, port):
    """Start a ttyd instance attached to sname:window_idx and return the Popen."""
    target = f"{sname}:{window_idx}"
    proc = subprocess.Popen([
        "ttyd", "-p", str(port), "--writable", "--max-clients", "5",
        "-t", "theme=" + TTYD_THEME,
        "-t", "fontSize=14",
        "-t", "fontFamily=Berkeley Mono Nerd Font,JetBrains Mono,Fira Code,monospace",
        "-t", "cursorStyle=block",
        "-t", "cursorBlink=true",
        "-t", "scrollback=0",
        "tmux", "attach-session", "-t", target,
    ])
    return proc


def _kill_shell_ttyd(shell_key):
    """Kill the ttyd process for a shell key (sname:widx) and remove from registry."""
    with _lock:
        info = _ttyd_procs.pop(shell_key, None)
    if not info:
        return
    proc = info.get("process")
    if proc is not None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    else:
        # Recovered process: find and kill by port via /proc
        port = info.get("port")
        if port:
            for pid in os.listdir('/proc'):
                if not pid.isdigit():
                    continue
                try:
                    with open(f'/proc/{pid}/cmdline', 'rb') as fh:
                        raw = fh.read()
                    if b'ttyd' in raw and (b'-p\x00' + str(port).encode()) in raw:
                        os.kill(int(pid), 15)
                        break
                except Exception:
                    pass


def ensure_project_running(project_id, directory, project_name=""):
    """Ensure the tmux session exists and window-0's ttyd is running.

    Returns the port for window 0, or None if no ports are available.
    """
    sname = session_name(project_id)
    log_slug = slugify(project_name) if project_name else project_id[:8]
    create_tmux_session(sname, directory, log_slug=log_slug)

    key0 = _ttyd_shell_key(sname, 0)
    with _lock:
        info = _ttyd_procs.get(key0)
        if info and _shell_proc_alive(info):
            return info["port"]
        if info:
            del _ttyd_procs[key0]

    # Try to recover from /proc before starting a new process
    _recover_shell_procs()
    with _lock:
        info = _ttyd_procs.get(key0)
        if info and _shell_proc_alive(info):
            return info["port"]

    with _lock:
        port = get_free_port()
        if port is None:
            return None
        proc = _start_shell_ttyd(sname, 0, port)
        _ttyd_procs[key0] = {"process": proc, "port": port}
        return port


def stop_project_proc(project_id):
    """Kill all ttyd processes belonging to this project."""
    sname = session_name(project_id)
    with _lock:
        keys = [k for k in list(_ttyd_procs.keys()) if k.startswith(sname + ":")]
    for key in keys:
        _kill_shell_ttyd(key)


# ---- HTTP handler -----------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 4 * 1024 * 1024:  # 4 MB hard cap
            self.rfile.read(length)
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc

    def _read_body(self):
        """Parse JSON request body; returns (data, None) on success or (None, True) on failure."""
        try:
            return self.read_json(), None
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
            return None, True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def parts(self):
        return [x for x in self.path.split("?")[0].split("/") if x]

    def qs(self):
        """Parse query string from the request path. Returns a dict of {key: value}."""
        if "?" not in self.path:
            return {}
        qs = self.path.split("?", 1)[1]
        result = {}
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                result[unquote(k)] = unquote(v)
            elif part:
                result[unquote(part)] = ""
        return result

    def do_GET(self):
        p = self.parts()
        if p == ["api", "health"]:
            return self.send_json(200, {
                "ok": True,
                "update_pending": not DISABLE_UPDATE_CHECK and os.path.exists("/tmp/glade-update-pending"),
                "image_update_pending": not DISABLE_UPDATE_CHECK and os.path.exists("/tmp/glade-image-update-pending"),
                "build_date": os.environ.get("GLADE_BUILD_DATE", ""),
            })
        if p == ["api", "projects", "activity"]:
            return self._get_activity()
        if p == ["api", "projects"]:
            return self._list_projects()
        if len(p) == 3 and p[:2] == ["api", "projects"]:
            return self._get_project(p[2])
        if len(p) == 4 and p[:2] == ["api", "projects"] and p[3] == "shells":
            return self._list_shells(p[2])
        if p == ["api", "snippets"]:
            return self._list_snippets()
        if p == ["api", "settings", "layout"]:
            return self._get_layout()
        if p == ["api", "settings", "compact-layout"]:
            return self._get_compact_layout()
        if p == ["api", "uploads"]:
            return self._list_uploads()
        if len(p) == 3 and p[:2] == ["api", "uploads"]:
            return self._serve_upload(p[2])
        if p == ["api", "export"]:
            return self._export_interactions()
        if p == ["api", "rebuild", "log"]:
            return self._get_rebuild_log()
        if p == ["api", "logs"]:
            return self._list_logs()
        if p == ["api", "logs", "search"]:
            return self._search_logs()
        if len(p) == 4 and p[:2] == ["api", "logs"] and p[2] == "current":
            return self._tail_current_log(p[3])
        if len(p) == 4 and p[:2] == ["api", "logs"]:
            return self._get_log_file(p[2], p[3])
        if p == ["api", "github", "auth", "status"]:
            return self._gh_auth_status()
        if p == ["api", "github", "repos"]:
            return self._gh_repos()
        if len(p) == 4 and p[:2] == ["api", "projects"] and p[3] == "shell-idle":
            return self._shell_idle(p[2])
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        p = self.parts()
        if p == ["api", "rebuild"]:
            return self._trigger_rebuild()
        if p == ["api", "restart"]:
            return self._restart_api()
        if p == ["api", "projects"]:
            return self._create_project()
        if len(p) == 4 and p[:2] == ["api", "projects"] and p[3] == "start":
            return self._start_project(p[2])
        if len(p) == 4 and p[:2] == ["api", "projects"] and p[3] == "stop":
            return self._stop_project(p[2])
        if len(p) == 4 and p[:2] == ["api", "projects"] and p[3] == "shells":
            return self._new_shell(p[2])
        if p == ["api", "snippets"]:
            return self._create_snippet()
        if p == ["api", "upload-image"]:
            return self._upload_image()
        if p == ["api", "github", "auth", "start"]:
            return self._gh_auth_start()
        self.send_json(404, {"error": "not found"})

    def do_PUT(self):
        p = self.parts()
        if len(p) == 3 and p[:2] == ["api", "projects"]:
            return self._update_project(p[2])
        if len(p) == 4 and p[:2] == ["api", "projects"] and p[3] == "viewed":
            return self._mark_viewed(p[2])
        if len(p) == 6 and p[:2] == ["api", "projects"] and p[3] == "shells" and p[5] == "select":
            return self._select_shell(p[2], p[4])
        if p == ["api", "settings", "layout"]:
            return self._save_layout()
        if p == ["api", "settings", "compact-layout"]:
            return self._save_compact_layout()
        if len(p) == 3 and p[:2] == ["api", "snippets"]:
            return self._update_snippet(p[2])
        self.send_json(404, {"error": "not found"})

    def do_DELETE(self):
        p = self.parts()
        if len(p) == 3 and p[:2] == ["api", "projects"]:
            return self._delete_project(p[2])
        if len(p) == 5 and p[:2] == ["api", "projects"] and p[3] == "shells":
            return self._kill_shell(p[2], p[4])
        if len(p) == 3 and p[:2] == ["api", "snippets"]:
            return self._delete_snippet(p[2])
        if len(p) == 4 and p[:2] == ["api", "logs"]:
            return self._delete_log_file(p[2], p[3])
        if p == ["api", "github", "auth"]:
            return self._gh_auth_disconnect()
        self.send_json(404, {"error": "not found"})

    def _list_projects(self):
        with open_db() as conn:
            rows = conn.execute(
                "SELECT id,name,directory,color,sort_order,created_at,last_active,github_repo "
                "FROM projects ORDER BY sort_order, created_at"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            sname = session_name(r["id"])
            key0 = _ttyd_shell_key(sname, 0)
            with _lock:
                info = _ttyd_procs.get(key0)
                d["running"] = _shell_proc_alive(info)
                d["port"]    = info["port"] if d["running"] else None
            result.append(d)
        self.send_json(200, result)

    def _get_project(self, pid):
        with open_db() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            return self.send_json(404, {"error": "not found"})
        d = dict(row)
        sname = session_name(pid)
        key0 = _ttyd_shell_key(sname, 0)
        with _lock:
            info = _ttyd_procs.get(key0)
            d["running"] = _shell_proc_alive(info)
            d["port"]    = info["port"] if d["running"] else None
        self.send_json(200, d)

    def _create_project(self):
        data, err = self._read_body()
        if err:
            return
        name = (data.get("name") or "").strip()
        directory = (data.get("directory") or "/").strip() or "/"
        color = (data.get("color") or "#89b4fa").strip()
        github_repo = (data.get("github_repo") or "").strip()
        if not name:
            return self.send_json(400, {"error": "name required"})

        if github_repo:
            if not shutil.which("gh"):
                return self.send_json(503, {"error": "gh CLI not available"})
            repo_name = github_repo.split("/")[-1] if "/" in github_repo else github_repo
            slug = slugify(repo_name)
            clone_dir = os.path.join(PROJECTS_DIR, slug)
            base = clone_dir
            n = 1
            while os.path.exists(clone_dir):
                clone_dir = f"{base}-{n}"
                n += 1
            os.makedirs(PROJECTS_DIR, exist_ok=True)
            r = subprocess.run(
                ["gh", "repo", "clone", github_repo, clone_dir],
                capture_output=True, text=True, timeout=120
            )
            if r.returncode != 0:
                msg = (r.stderr or r.stdout or "unknown error").strip()
                return self.send_json(422, {"error": f"Clone failed: {msg}"})
            directory = clone_dir

        pid = str(uuid.uuid4())
        with open_db() as conn:
            conn.execute(
                "INSERT INTO projects (id,name,directory,color,github_repo) VALUES (?,?,?,?,?)",
                (pid, name, directory, color, github_repo or None)
            )
        self.send_json(201, {
            "id": pid, "name": name, "directory": directory,
            "color": color, "github_repo": github_repo or None,
            "running": False, "port": None,
        })

    def _update_project(self, pid):
        data, err = self._read_body()
        if err:
            return
        fields, vals = [], []
        for col in ("name", "directory", "color", "sort_order"):
            if col in data:
                fields.append(f"{col}=?")
                vals.append(data[col])
        if not fields:
            return self.send_json(400, {"error": "nothing to update"})
        vals.append(pid)
        with open_db() as conn:
            conn.execute(f"UPDATE projects SET {','.join(fields)} WHERE id=?", vals)
        self.send_json(200, {"ok": True})

    def _delete_project(self, pid):
        stop_project_proc(pid)
        # Kill the tmux session so no shells linger after deletion
        sname = session_name(pid)
        subprocess.run(["tmux", "kill-session", "-t", sname], capture_output=True)
        with open_db() as conn:
            conn.execute("DELETE FROM projects WHERE id=?", (pid,))
        self.send_json(200, {"ok": True})

    def _start_project(self, pid):
        with open_db() as conn:
            row = conn.execute("SELECT name, directory FROM projects WHERE id=?", (pid,)).fetchone()
            if not row:
                return self.send_json(404, {"error": "not found"})
            directory = row["directory"]
            project_name = row["name"]
            conn.execute("UPDATE projects SET last_active=CURRENT_TIMESTAMP WHERE id=?", (pid,))
        port = ensure_project_running(pid, directory, project_name=project_name)
        if port is None:
            return self.send_json(503, {"error": "no ports available"})
        sname = session_name(pid)
        shells = self._shells_with_ports(pid, sname)
        if pid not in _baselines:
            _baselines[pid] = tmux_history_size(sname)
        self.send_json(200, {"port": port, "shells": shells})

    def _stop_project(self, pid):
        stop_project_proc(pid)
        self.send_json(200, {"ok": True})

    def _shells_with_ports(self, pid, sname=None):
        """Return shell list from tmux, enriched with each shell's ttyd port."""
        if sname is None:
            sname = session_name(pid)
        # Rebuild proc map from /proc if we have no entries for this session
        with _lock:
            has_entries = any(k.startswith(sname + ":") for k in _ttyd_procs)
        if not has_entries:
            _recover_shell_procs()
        shells = list_shells_tmux(sname)
        with _lock:
            for sh in shells:
                key = _ttyd_shell_key(sname, sh["index"])
                info = _ttyd_procs.get(key)
                sh["port"] = info["port"] if info else None
        return shells

    def _list_shells(self, pid):
        sname = session_name(pid)
        if not tmux_session_exists(sname):
            return self.send_json(200, [])
        self.send_json(200, self._shells_with_ports(pid, sname))

    # ── GitHub ───────────────────────────────────────────────────────────────

    def _gh_available(self):
        return shutil.which("gh") is not None

    def _gh_auth_status(self):
        if not self._gh_available():
            return self.send_json(200, {"connected": False, "error": "gh not installed"})
        try:
            r = subprocess.run(
                ["gh", "auth", "status", "-h", "github.com"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode != 0:
                return self.send_json(200, {"connected": False})
            ur = subprocess.run(
                ["gh", "api", "user", "--jq", "{login: .login, avatar_url: .avatar_url}"],
                capture_output=True, text=True, timeout=10
            )
            if ur.returncode == 0:
                try:
                    info = json.loads(ur.stdout.strip())
                    return self.send_json(200, {
                        "connected": True,
                        "username": info.get("login", ""),
                        "avatar_url": info.get("avatar_url", ""),
                    })
                except Exception:
                    pass
            return self.send_json(200, {"connected": True, "username": "", "avatar_url": ""})
        except Exception as e:
            return self.send_json(200, {"connected": False, "error": str(e)})

    def _gh_auth_start(self):
        global _gh_auth_proc
        if not self._gh_available():
            return self.send_json(503, {"error": "gh CLI not installed in this container"})
        with _gh_auth_lock:
            if _gh_auth_proc and _gh_auth_proc.poll() is None:
                _gh_auth_proc.terminate()
            proc = subprocess.Popen(
                ["gh", "auth", "login", "-h", "github.com", "--git-protocol", "https", "-w"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            _gh_auth_proc = proc

        user_code = None
        verification_uri = "https://github.com/login/device"
        deadline = time.time() + 20
        for line in proc.stdout:
            line = strip_ansi(line).strip()
            m = re.search(r'one-time code[:\s]+([A-Z0-9]{4}-[A-Z0-9]{4})', line, re.I)
            if m:
                user_code = m.group(1)
            m = re.search(r'(https://github\.com/login/device\S*)', line)
            if m:
                verification_uri = m.group(1).rstrip(".")
            if user_code:
                break
            if time.time() > deadline:
                break

        if not user_code:
            return self.send_json(503, {"error": "Could not start GitHub device flow — check that gh is authenticated or try again"})

        return self.send_json(200, {
            "user_code": user_code,
            "verification_uri": verification_uri,
        })

    def _gh_auth_disconnect(self):
        if not self._gh_available():
            return self.send_json(503, {"error": "gh CLI not installed"})
        hosts_file = os.path.expanduser("~/.config/gh/hosts.yml")
        try:
            if os.path.exists(hosts_file):
                os.remove(hosts_file)
        except Exception as e:
            return self.send_json(500, {"error": str(e)})
        self.send_json(200, {"ok": True})

    def _gh_repos(self):
        if not self._gh_available():
            return self.send_json(200, [])
        q = self.qs().get("q", "").strip().lower()
        try:
            r = subprocess.run(
                ["gh", "repo", "list", "--limit", "100",
                 "--json", "nameWithOwner,name,description,isPrivate"],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode != 0:
                return self.send_json(200, [])
            repos = json.loads(r.stdout or "[]")
            if q:
                repos = [
                    repo for repo in repos
                    if q in repo.get("nameWithOwner", "").lower()
                    or q in (repo.get("description") or "").lower()
                ]
            return self.send_json(200, repos)
        except Exception:
            return self.send_json(200, [])

    def _new_shell(self, pid):
        with open_db() as conn:
            row = conn.execute("SELECT directory FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            return self.send_json(404, {"error": "not found"})
        sname = session_name(pid)
        if not tmux_session_exists(sname):
            return self.send_json(409, {"error": "project not running"})
        idx = new_shell_tmux(sname, row["directory"])
        if idx is None:
            return self.send_json(500, {"error": "tmux new-window failed"})
        with _lock:
            port = get_free_port()
        if port is None:
            return self.send_json(503, {"error": "no ports available"})
        proc = _start_shell_ttyd(sname, idx, port)
        with _lock:
            _ttyd_procs[_ttyd_shell_key(sname, idx)] = {"process": proc, "port": port}
        self.send_json(201, {"index": idx, "port": port})

    def _select_shell(self, pid, index):
        # No-op: with per-shell ttyd instances, the client just loads the
        # shell's own port in the iframe — no tmux window switching needed.
        self.send_json(200, {"ok": True})

    def _kill_shell(self, pid, index):
        sname = session_name(pid)
        shell_key = _ttyd_shell_key(sname, index)
        _kill_shell_ttyd(shell_key)
        try:
            subprocess.run(["tmux", "kill-window", "-t", f"{sname}:{index}"],
                           capture_output=True)
        except Exception:
            pass
        self.send_json(200, {"ok": True})

    def _get_activity(self):
        with open_db() as conn:
            rows = conn.execute("SELECT id FROM projects").fetchall()
        result = []
        for row in rows:
            pid = row["id"]
            sname = session_name(pid)
            key0 = _ttyd_shell_key(sname, 0)
            with _lock:
                info    = _ttyd_procs.get(key0)
                running = _shell_proc_alive(info)
            has_activity = False
            if running and tmux_session_exists(sname):
                current = tmux_history_size(sname)
                baseline = _baselines.get(pid, current)
                has_activity = current != baseline
            result.append({"id": pid, "hasActivity": has_activity})
        self.send_json(200, result)

    def _mark_viewed(self, pid):
        sname = session_name(pid)
        if tmux_session_exists(sname):
            _baselines[pid] = tmux_history_size(sname)
        self.send_json(200, {"ok": True})

    # -- snippets --

    def _list_snippets(self):
        with open_db() as conn:
            rows = conn.execute(
                "SELECT id,name,command,sort_order FROM snippets ORDER BY sort_order,created_at"
            ).fetchall()
        self.send_json(200, [dict(r) for r in rows])

    def _create_snippet(self):
        data, err = self._read_body()
        if err:
            return
        name    = (data.get("name") or "").strip()
        command = (data.get("command") or "").strip()
        if not name or not command:
            return self.send_json(400, {"error": "name and command required"})
        sid = str(uuid.uuid4())
        with open_db() as conn:
            conn.execute("INSERT INTO snippets (id,name,command,sort_order) VALUES (?,?,?,?)",
                         (sid, name, command, data.get("sort_order", 0)))
        self.send_json(201, {"id": sid, "name": name, "command": command})

    def _update_snippet(self, sid):
        data, err = self._read_body()
        if err:
            return
        name    = (data.get("name") or "").strip()
        command = (data.get("command") or "").strip()
        if not name or not command:
            return self.send_json(400, {"error": "name and command required"})
        with open_db() as conn:
            cur = conn.execute("UPDATE snippets SET name=?,command=?,sort_order=? WHERE id=?",
                               (name, command, data.get("sort_order", 0), sid))
            if cur.rowcount == 0:
                return self.send_json(404, {"error": "not found"})
        self.send_json(200, {"ok": True})

    def _delete_snippet(self, sid):
        with open_db() as conn:
            conn.execute("DELETE FROM snippets WHERE id=?", (sid,))
        self.send_json(200, {"ok": True})

    def _upload_image(self):
        data, err = self._read_body()
        if err:
            return
        b64  = data.get("data", "")
        if len(b64) > 20 * 1024 * 1024:  # ~15 MB decoded
            return self.send_json(400, {"error": "file too large"})
        mime = data.get("type", "application/octet-stream")
        # Prefer caller-provided filename; fall back to MIME-based naming
        orig_name = data.get("filename", "")
        if orig_name and "/" not in orig_name and "\\" not in orig_name and ".." not in orig_name:
            # Use a safe version of the original name
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in orig_name)
            ext = safe.rsplit(".", 1)[-1] if "." in safe else ""
            prefix = "file"
        else:
            img_ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
            if mime in img_ext_map:
                ext = img_ext_map[mime]
                prefix = "img"
            else:
                # Guess extension from MIME
                import mimetypes as _mt
                guessed = _mt.guess_extension(mime) or ""
                ext = guessed.lstrip(".") or "bin"
                prefix = "file"
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        ts       = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        short_id = str(uuid.uuid4()).replace("-", "")[:8]
        filename = f"{prefix}-{ts}-{short_id}.{ext}" if ext else f"{prefix}-{ts}-{short_id}"
        path     = os.path.join(UPLOADS_DIR, filename)
        try:
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))
        except Exception as e:
            return self.send_json(400, {"error": str(e)})
        self.send_json(200, {
            "path":     path,
            "url":      f"/api/uploads/{filename}",
            "filename": filename,
            "mime":     mime,
        })

    def _serve_upload(self, filename):
        # Only allow simple filenames — no path traversal
        if "/" in filename or "\\" in filename or ".." in filename:
            return self.send_json(400, {"error": "invalid filename"})
        path = os.path.join(UPLOADS_DIR, filename)
        if not os.path.isfile(path):
            return self.send_json(404, {"error": "not found"})
        mime, _ = mimetypes.guess_type(filename)
        mime = mime or "application/octet-stream"
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _list_uploads(self):
        if not os.path.isdir(UPLOADS_DIR):
            return self.send_json(200, [])
        entries = []
        for name in os.listdir(UPLOADS_DIR):
            fpath = os.path.join(UPLOADS_DIR, name)
            if not os.path.isfile(fpath):
                continue
            stat = os.stat(fpath)
            mime, _ = mimetypes.guess_type(name)
            entries.append({
                "filename":   name,
                "url":        f"/api/uploads/{name}",
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "size":       stat.st_size,
                "mime":       mime or "application/octet-stream",
            })
        entries.sort(key=lambda e: e["created_at"], reverse=True)
        self.send_json(200, entries[:10])

    _IDLE_SHELLS = {"bash", "zsh", "fish", "sh", "dash", "ksh", "tcsh", "csh", "-bash", "-zsh"}

    def _shell_idle(self, pid):
        with open_db() as conn:
            row = conn.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            return self.send_json(404, {"error": "project not found"})
        sname = slugify(row["name"])
        try:
            r = subprocess.run(
                ["tmux", "display-message", "-pt", f"{sname}:0.0", "#{pane_current_command}"],
                capture_output=True, text=True, timeout=3,
            )
            cmd = r.stdout.strip()
        except Exception:
            cmd = ""
        idle = cmd.lower() in self._IDLE_SHELLS or cmd == ""
        return self.send_json(200, {"idle": idle, "command": cmd})

    def _export_interactions(self):
        try:
            with open_db() as conn:
                rows = conn.execute(
                    "SELECT * FROM interactions ORDER BY timestamp DESC LIMIT 500"
                ).fetchall()
        except Exception:
            rows = []
        data = [dict(r) for r in rows]
        body = json.dumps(data, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Disposition", "attachment; filename=glade-history.json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    # -- settings --

    def _get_setting(self, key):
        with open_db() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        if row:
            self.send_json(200, json.loads(row["value"]))
        else:
            self.send_json(404, {"error": f"no {key} saved"})

    def _put_setting(self, key):
        data, err = self._read_body()
        if err:
            return
        with open_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key,value,updated_at) "
                "VALUES (?,?,CURRENT_TIMESTAMP)",
                (key, json.dumps(data))
            )
        self.send_json(200, {"ok": True})

    def _get_layout(self):         return self._get_setting("keyboard_layout")
    def _get_compact_layout(self): return self._get_setting("compact_keyboard_layout")
    def _save_layout(self):        return self._put_setting("keyboard_layout")
    def _save_compact_layout(self): return self._put_setting("compact_keyboard_layout")

    # -- session logs --

    def _active_tmux_sessions(self):
        r = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                           capture_output=True, text=True)
        return set(r.stdout.strip().splitlines()) if r.returncode == 0 else set()

    def _project_slug_map(self):
        with open_db() as conn:
            rows = conn.execute("SELECT id, name FROM projects").fetchall()
        return {slugify(r["name"]): r["name"] for r in rows}

    def _list_logs(self):
        if not os.path.isdir(LOGS_DIR):
            return self.send_json(200, [])
        active_sessions = self._active_tmux_sessions()
        with open_db() as conn:
            rows = conn.execute("SELECT id, name FROM projects").fetchall()
        slug_names   = {slugify(r["name"]): r["name"] for r in rows}
        active_slugs = {slugify(r["name"]) for r in rows
                        if session_name(r["id"]) in active_sessions}
        results = []
        for slug in sorted(os.listdir(LOGS_DIR)):
            slug_dir = os.path.join(LOGS_DIR, slug)
            if not os.path.isdir(slug_dir):
                continue
            display_name = slug_names.get(slug, "Main Shell" if slug == "_main" else slug)
            log_files = sorted([f for f in os.listdir(slug_dir) if f.endswith(".log")])
            is_slug_active = slug in active_slugs
            for fname in reversed(log_files):
                fpath = os.path.join(slug_dir, fname)
                try:
                    st = os.stat(fpath)
                except OSError:
                    continue
                results.append({
                    "project": slug,
                    "display_name": display_name,
                    "file": fname,
                    "size": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "active": is_slug_active and fname == log_files[-1],
                })
        results.sort(key=lambda x: x["mtime"], reverse=True)
        self.send_json(200, results)

    def _get_log_file(self, project, filename):
        if ".." in project or ".." in filename:
            return self.send_json(400, {"error": "invalid path"})
        fpath = os.path.join(LOGS_DIR, project, filename)
        if not os.path.isfile(fpath):
            return self.send_json(404, {"error": "not found"})
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        tail = 0
        for part in qs.split("&"):
            if part.startswith("tail="):
                try:
                    tail = int(part.split("=", 1)[1])
                except ValueError:
                    pass
        try:
            with open(fpath, "r", errors="replace") as f:
                content = f.read()
            if tail > 0:
                lines = content.splitlines()
                content = "\n".join(lines[-tail:])
        except OSError:
            return self.send_json(500, {"error": "read error"})
        body = content.encode("utf-8", errors="replace")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _tail_current_log(self, project):
        if ".." in project:
            return self.send_json(400, {"error": "invalid path"})
        slug_dir = os.path.join(LOGS_DIR, project)
        if not os.path.isdir(slug_dir):
            return self.send_json(404, {"error": "no logs for project"})
        logs = sorted([f for f in os.listdir(slug_dir) if f.endswith(".log")])
        if not logs:
            return self.send_json(404, {"error": "no log files"})
        latest = os.path.join(slug_dir, logs[-1])
        try:
            with open(latest, "r", errors="replace") as f:
                lines = f.readlines()
            content = "".join(lines[-200:])
        except OSError:
            return self.send_json(500, {"error": "read error"})
        body = content.encode("utf-8", errors="replace")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _search_logs(self):
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        query = ""
        for part in qs.split("&"):
            if part.startswith("q="):
                query = unquote(part.split("=", 1)[1])
        if not query or not os.path.isdir(LOGS_DIR):
            return self.send_json(200, [])
        try:
            r = subprocess.run(
                ["grep", "-ril", "--include=*.log", query, LOGS_DIR],
                capture_output=True, text=True, timeout=10
            )
        except subprocess.TimeoutExpired:
            return self.send_json(200, [])
        results = []
        slug_names = self._project_slug_map()
        for fpath in r.stdout.strip().splitlines()[:20]:
            if not fpath:
                continue
            rel = os.path.relpath(fpath, LOGS_DIR)
            parts = rel.split(os.sep, 1)
            if len(parts) != 2:
                continue
            slug, fname = parts
            display_name = slug_names.get(slug, "Main Shell" if slug == "_main" else slug)
            matches = []
            try:
                with open(fpath, "r", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if query.lower() in line.lower():
                            matches.append({
                                "line": i,
                                "text": strip_ansi(line.rstrip())[:200]
                            })
                            if len(matches) >= 5:
                                break
            except OSError:
                continue
            results.append({
                "project": slug,
                "display_name": display_name,
                "file": fname,
                "matches": matches,
            })
        self.send_json(200, results)

    def _delete_log_file(self, project, filename):
        if ".." in project or ".." in filename:
            return self.send_json(400, {"error": "invalid path"})
        fpath = os.path.join(LOGS_DIR, project, filename)
        if not os.path.isfile(fpath):
            return self.send_json(404, {"error": "not found"})
        try:
            os.remove(fpath)
        except OSError as e:
            return self.send_json(500, {"error": str(e)})
        self.send_json(200, {"ok": True})

    def _trigger_rebuild(self):
        try:
            # Clear previous log so the UI starts fresh
            with open(REBUILD_LOG, "w"):
                pass
            # Write trigger file — the host launchd watcher picks this up
            with open(REBUILD_TRIGGER, "w"):
                pass
        except OSError as e:
            return self.send_json(500, {"error": str(e)})
        self.send_json(200, {"ok": True})

    def _get_rebuild_log(self):
        running = os.path.exists(REBUILD_TRIGGER) or os.path.exists(REBUILD_LOCK)
        try:
            with open(REBUILD_LOG) as f:
                lines = f.readlines()
            log = "".join(lines[-200:])
        except FileNotFoundError:
            log = ""
        self.send_json(200, {"log": log, "running": running})

    def _restart_api(self):
        # Respond before exiting so the client gets a clean 200.
        self.send_json(200, {"ok": True, "message": "Restarting…"})
        # Exit code 42 signals the entrypoint supervisor loop to restart.
        threading.Thread(target=lambda: (
            __import__("time").sleep(0.2),
            os._exit(42)
        ), daemon=True).start()

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
ensure_tables()
# Kill any ttyd processes left over from a prior crash that still hold our ports.
try:
    result = subprocess.run(
        ["pgrep", "-f", "ttyd.*-p 769"],
        capture_output=True, text=True
    )
    for pid in result.stdout.strip().splitlines():
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
except Exception:
    pass
ThreadingTCPServer.allow_reuse_address = True
server = ThreadingTCPServer(("0.0.0.0", PORT), Handler)
print(f"glade API listening on :{PORT}", flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    with _lock:
        for info in _ttyd_procs.values():
            try:
                info["process"].terminate()
            except Exception:
                pass
