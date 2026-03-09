#!/usr/bin/env python3
"""
copilot-sync API — projects, snippets, keyboard layout

Runs inside the ttyd Docker container on port 7683.
Manages project lifecycle: tmux sessions + ttyd child processes.

Routes:
  GET    /api/health
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
"""

import json
import os
import sqlite3
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler
from socketserver import ThreadingTCPServer

DB_PATH = os.environ.get("DB_PATH", "/root/.copilot-sync/db/history.db")
PORT    = int(os.environ.get("PORT", "7683"))

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
        """)
        conn.commit()
    finally:
        conn.close()


# ---- tmux helpers -----------------------------------------------------------

def session_name(project_id):
    return "proj-" + project_id[:8]


def tmux_session_exists(sname):
    r = subprocess.run(["tmux", "has-session", "-t", sname], capture_output=True)
    return r.returncode == 0


def create_tmux_session(sname, directory):
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


def ensure_project_running(project_id, directory):
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
        create_tmux_session(sname, directory)
        proc = subprocess.Popen([
            "ttyd", "-p", str(port), "--writable", "--max-clients", "5",
            "-t", "theme=" + TTYD_THEME,
            "-t", "fontSize=14",
            "-t", "fontFamily=Berkeley Mono Nerd Font,JetBrains Mono,Fira Code,monospace",
            "-t", "cursorStyle=block",
            "-t", "cursorBlink=true",
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
        pass

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
            return self.send_json(200, {"ok": True})
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
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        p = self.parts()
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
            row = conn.execute("SELECT directory FROM projects WHERE id=?", (pid,)).fetchone()
            if not row:
                return self.send_json(404, {"error": "not found"})
            directory = row["directory"]
            conn.execute("UPDATE projects SET last_active=CURRENT_TIMESTAMP WHERE id=?", (pid,))
            conn.commit()
        finally:
            conn.close()
        port = ensure_project_running(pid, directory)
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


if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    ensure_tables()
    ThreadingTCPServer.allow_reuse_address = True
    server = ThreadingTCPServer(("0.0.0.0", PORT), Handler)
    print(f"copilot-sync API listening on :{PORT}", flush=True)
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
