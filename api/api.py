#!/usr/bin/env python3
"""
roost API — projects, snippets, keyboard layout, image uploads

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
  GET    /api/logs/search?q=            search across all logs (grep)
  GET    /api/logs/current/:slug        tail active session log (last 200 lines)
  GET    /api/logs/:project/:file       raw log file content (?tail=N optional)
"""

import base64
import json
import mimetypes
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer

DB_PATH      = os.environ.get("DB_PATH", "/root/.roost/db/history.db")
PORT         = int(os.environ.get("PORT", "7683"))
ROOST_DIR    = os.environ.get("ROOST_DIR", "/root/.roost")
UPLOADS_DIR  = os.environ.get("UPLOADS_DIR", "/root/.roost/uploads")
LOGS_DIR     = os.environ.get("LOGS_DIR", "/root/.roost/logs")

REBUILD_TRIGGER = os.path.join(ROOST_DIR, ".rebuild-requested")
REBUILD_LOCK    = os.path.join(ROOST_DIR, ".rebuild-running")
REBUILD_LOG     = os.path.join(ROOST_DIR, "rebuild.log")

PORT_POOL = list(range(7690, 7700))

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
_ttyd_procs = {}   # project_id -> {"process": Popen, "port": int}
_baselines  = {}   # project_id -> int (tmux history_size at last view)


def open_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_tables():
    conn = open_db()
    try:
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
        conn.commit()
    finally:
        conn.close()


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
    subprocess.run(["tmux", "new-session", "-d", "-s", sname, "-c", directory],
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
    r = subprocess.run(
        ["tmux", "new-window", "-t", sname, "-c", directory, "-P", "-F", "#{window_index}"],
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


def ensure_project_running(project_id, directory, project_name=""):
    with _lock:
        info = _ttyd_procs.get(project_id)
        if info and info["process"].poll() is None:
            return info["port"]
        if info:
            del _ttyd_procs[project_id]
        port = get_free_port()
        if port is None:
            return None
        sname = session_name(project_id)
        log_slug = slugify(project_name) if project_name else project_id[:8]
        create_tmux_session(sname, directory, log_slug=log_slug)
        proc = subprocess.Popen([
            "ttyd", "-p", str(port), "--writable", "--max-clients", "5",
            "-t", "theme=" + TTYD_THEME,
            "-t", "fontSize=14",
            "-t", "fontFamily=Berkeley Mono Nerd Font,JetBrains Mono,Fira Code,monospace",
            "-t", "cursorStyle=block",
            "-t", "cursorBlink=true",
            "-t", "scrollback=0",
            "tmux", "attach-session", "-t", sname,
        ])
        _ttyd_procs[project_id] = {"process": proc, "port": port}
        return port


def stop_project_proc(project_id):
    with _lock:
        info = _ttyd_procs.pop(project_id, None)
    if info:
        proc = info["process"]
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


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
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def parts(self):
        return [x for x in self.path.split("?")[0].split("/") if x]

    def do_GET(self):
        p = self.parts()
        if p == ["api", "health"]:
            return self.send_json(200, {
                "ok": True,
                "update_pending": os.path.exists("/tmp/roost-update-pending"),
                "image_update_pending": os.path.exists("/tmp/roost-image-update-pending"),
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
        self.send_json(404, {"error": "not found"})

    # -- projects --

    def _list_projects(self):
        conn = open_db()
        try:
            rows = conn.execute(
                "SELECT id,name,directory,color,sort_order,created_at,last_active "
                "FROM projects ORDER BY sort_order, created_at"
            ).fetchall()
        finally:
            conn.close()
        result = []
        for r in rows:
            d = dict(r)
            with _lock:
                info = _ttyd_procs.get(r["id"])
                d["running"] = bool(info and info["process"].poll() is None)
                d["port"]    = info["port"] if d["running"] else None
            result.append(d)
        self.send_json(200, result)

    def _get_project(self, pid):
        conn = open_db()
        try:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        finally:
            conn.close()
        if not row:
            return self.send_json(404, {"error": "not found"})
        d = dict(row)
        with _lock:
            info = _ttyd_procs.get(pid)
            d["running"] = bool(info and info["process"].poll() is None)
            d["port"]    = info["port"] if d["running"] else None
        self.send_json(200, d)

    def _create_project(self):
        data = self.read_json()
        name = (data.get("name") or "").strip()
        directory = (data.get("directory") or "/").strip() or "/"
        color = (data.get("color") or "#89b4fa").strip()
        if not name:
            return self.send_json(400, {"error": "name required"})
        pid = str(uuid.uuid4())
        conn = open_db()
        try:
            conn.execute("INSERT INTO projects (id,name,directory,color) VALUES (?,?,?,?)",
                         (pid, name, directory, color))
            conn.commit()
        finally:
            conn.close()
        self.send_json(201, {"id": pid, "name": name, "directory": directory,
                              "color": color, "running": False, "port": None})

    def _update_project(self, pid):
        data = self.read_json()
        fields, vals = [], []
        for col in ("name", "directory", "color", "sort_order"):
            if col in data:
                fields.append(f"{col}=?")
                vals.append(data[col])
        if not fields:
            return self.send_json(400, {"error": "nothing to update"})
        vals.append(pid)
        conn = open_db()
        try:
            conn.execute(f"UPDATE projects SET {','.join(fields)} WHERE id=?", vals)
            conn.commit()
        finally:
            conn.close()
        self.send_json(200, {"ok": True})

    def _delete_project(self, pid):
        stop_project_proc(pid)
        conn = open_db()
        try:
            conn.execute("DELETE FROM projects WHERE id=?", (pid,))
            conn.commit()
        finally:
            conn.close()
        self.send_json(200, {"ok": True})

    def _start_project(self, pid):
        conn = open_db()
        try:
            row = conn.execute("SELECT name, directory FROM projects WHERE id=?", (pid,)).fetchone()
            if not row:
                return self.send_json(404, {"error": "not found"})
            directory = row["directory"]
            project_name = row["name"]
            conn.execute("UPDATE projects SET last_active=CURRENT_TIMESTAMP WHERE id=?", (pid,))
            conn.commit()
        finally:
            conn.close()
        port = ensure_project_running(pid, directory, project_name=project_name)
        if port is None:
            return self.send_json(503, {"error": "no ports available"})
        sname = session_name(pid)
        shells = list_shells_tmux(sname)
        if pid not in _baselines:
            _baselines[pid] = tmux_history_size(sname)
        self.send_json(200, {"port": port, "shells": shells})

    def _stop_project(self, pid):
        stop_project_proc(pid)
        self.send_json(200, {"ok": True})

    def _list_shells(self, pid):
        with _lock:
            info = _ttyd_procs.get(pid)
            running = bool(info and info["process"].poll() is None)
        if not running:
            return self.send_json(200, [])
        self.send_json(200, list_shells_tmux(session_name(pid)))

    def _new_shell(self, pid):
        conn = open_db()
        try:
            row = conn.execute("SELECT directory FROM projects WHERE id=?", (pid,)).fetchone()
        finally:
            conn.close()
        if not row:
            return self.send_json(404, {"error": "not found"})
        sname = session_name(pid)
        if not tmux_session_exists(sname):
            return self.send_json(409, {"error": "project not running"})
        idx = new_shell_tmux(sname, row["directory"])
        self.send_json(201, {"index": idx})

    def _select_shell(self, pid, index):
        sname = session_name(pid)
        if not tmux_session_exists(sname):
            return self.send_json(409, {"error": "project not running"})
        try:
            select_shell_tmux(sname, int(index))
        except (ValueError, Exception):
            return self.send_json(400, {"error": "invalid index"})
        self.send_json(200, {"ok": True})

    def _kill_shell(self, pid, index):
        sname = session_name(pid)
        try:
            subprocess.run(["tmux", "kill-window", "-t", f"{sname}:{index}"],
                           capture_output=True)
        except Exception:
            pass
        self.send_json(200, {"ok": True})

    def _get_activity(self):
        conn = open_db()
        try:
            rows = conn.execute("SELECT id FROM projects").fetchall()
        finally:
            conn.close()
        result = []
        for row in rows:
            pid = row["id"]
            sname = session_name(pid)
            with _lock:
                info = _ttyd_procs.get(pid)
                running = bool(info and info["process"].poll() is None)
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
        conn = open_db()
        try:
            rows = conn.execute(
                "SELECT id,name,command,sort_order FROM snippets ORDER BY sort_order,created_at"
            ).fetchall()
        finally:
            conn.close()
        self.send_json(200, [dict(r) for r in rows])

    def _create_snippet(self):
        data = self.read_json()
        name    = (data.get("name") or "").strip()
        command = (data.get("command") or "").strip()
        if not name or not command:
            return self.send_json(400, {"error": "name and command required"})
        sid = str(uuid.uuid4())
        conn = open_db()
        try:
            conn.execute("INSERT INTO snippets (id,name,command,sort_order) VALUES (?,?,?,?)",
                         (sid, name, command, data.get("sort_order", 0)))
            conn.commit()
        finally:
            conn.close()
        self.send_json(201, {"id": sid, "name": name, "command": command})

    def _update_snippet(self, sid):
        data    = self.read_json()
        name    = (data.get("name") or "").strip()
        command = (data.get("command") or "").strip()
        if not name or not command:
            return self.send_json(400, {"error": "name and command required"})
        conn = open_db()
        try:
            cur = conn.execute("UPDATE snippets SET name=?,command=?,sort_order=? WHERE id=?",
                               (name, command, data.get("sort_order", 0), sid))
            conn.commit()
            if cur.rowcount == 0:
                return self.send_json(404, {"error": "not found"})
        finally:
            conn.close()
        self.send_json(200, {"ok": True})

    def _delete_snippet(self, sid):
        conn = open_db()
        try:
            conn.execute("DELETE FROM snippets WHERE id=?", (sid,))
            conn.commit()
        finally:
            conn.close()
        self.send_json(200, {"ok": True})

    def _upload_image(self):
        data = self.read_json()
        b64  = data.get("data", "")
        if len(b64) > 20 * 1024 * 1024:  # ~15 MB decoded
            return self.send_json(400, {"error": "image too large"})
        mime = data.get("type", "image/png")
        ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
        ext  = ext_map.get(mime, "png")
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        ts       = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        short_id = str(uuid.uuid4()).replace("-", "")[:8]
        filename = f"img-{ts}-{short_id}.{ext}"
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
            entries.append({
                "filename":   name,
                "url":        f"/api/uploads/{name}",
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "size":       stat.st_size,
            })
        entries.sort(key=lambda e: e["created_at"], reverse=True)
        self.send_json(200, entries[:10])

    def _export_interactions(self):
        conn = open_db()
        try:
            rows = conn.execute(
                "SELECT * FROM interactions ORDER BY timestamp DESC LIMIT 500"
            ).fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()
        data = [dict(r) for r in rows]
        body = json.dumps(data, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Disposition", "attachment; filename=roost-history.json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- settings --

    def _get_layout(self):
        conn = open_db()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='keyboard_layout'"
            ).fetchone()
        finally:
            conn.close()
        if row:
            self.send_json(200, json.loads(row["value"]))
        else:
            self.send_json(404, {"error": "no layout saved"})

    def _save_layout(self):
        data = self.read_json()
        conn = open_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key,value,updated_at) "
                "VALUES ('keyboard_layout',?,CURRENT_TIMESTAMP)",
                (json.dumps(data),)
            )
            conn.commit()
        finally:
            conn.close()
        self.send_json(200, {"ok": True})

    def _get_compact_layout(self):
        conn = open_db()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='compact_keyboard_layout'"
            ).fetchone()
        finally:
            conn.close()
        if row:
            self.send_json(200, json.loads(row["value"]))
        else:
            self.send_json(404, {"error": "no compact layout saved"})

    def _save_compact_layout(self):
        data = self.read_json()
        conn = open_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key,value,updated_at) "
                "VALUES ('compact_keyboard_layout',?,CURRENT_TIMESTAMP)",
                (json.dumps(data),)
            )
            conn.commit()
        finally:
            conn.close()
        self.send_json(200, {"ok": True})

    # -- session logs --

    def _active_tmux_sessions(self):
        r = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                           capture_output=True, text=True)
        return set(r.stdout.strip().splitlines()) if r.returncode == 0 else set()

    def _project_slug_map(self):
        conn = open_db()
        try:
            rows = conn.execute("SELECT id, name FROM projects").fetchall()
        finally:
            conn.close()
        return {slugify(r["name"]): r["name"] for r in rows}

    def _list_logs(self):
        if not os.path.isdir(LOGS_DIR):
            return self.send_json(200, [])
        active_sessions = self._active_tmux_sessions()
        slug_names = self._project_slug_map()
        # Build slug→active by checking which projects have a running tmux session
        conn = open_db()
        try:
            rows = conn.execute("SELECT id, name FROM projects").fetchall()
        finally:
            conn.close()
        active_slugs = set()
        for row in rows:
            sname = session_name(row["id"])
            if sname in active_sessions:
                active_slugs.add(slugify(row["name"]))
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
                from urllib.parse import unquote
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
            open(REBUILD_LOG, "w").close()
            # Write trigger file — the host launchd watcher picks this up
            open(REBUILD_TRIGGER, "w").close()
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
print(f"roost API listening on :{PORT}", flush=True)
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
