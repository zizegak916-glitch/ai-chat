#!/usr/bin/env python3
"""AI Multi-Model Chat + Tools Panel."""

import json
import os
import sys
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
STATE_DB = HERMES_HOME / "state.db"
CRON_JOBS_FILE = HERMES_HOME / "cron" / "jobs.json"
CRON_OUTPUT_DIR = HERMES_HOME / "cron" / "output"
TODOS_FILE = HERMES_HOME / "todos.json"
STATIC_DIR = Path(__file__).parent / "static"

TZ = timezone(timedelta(hours=8))


def now_iso():
    return datetime.now(TZ).isoformat()


def load_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return data


def ensure_todos():
    if not TODOS_FILE.exists():
        TODOS_FILE.write_text(json.dumps({"todos": [], "updated_at": now_iso()}, indent=2))


def get_db():
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    return conn


# ========== Tasks API ==========

@app.route("/api/tasks/cron")
def tasks_cron():
    return jsonify(load_json(CRON_JOBS_FILE))


@app.route("/api/tasks/cron", methods=["POST"])
def tasks_cron_create():
    import uuid
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip() or "未命名任务"
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt 不能为空"}), 400
    schedule_raw = body.get("schedule_display", "60m")
    minutes = 60
    if isinstance(schedule_raw, str):
        s = schedule_raw.lower().replace("every ", "").strip()
        if s.endswith("m"): minutes = int(s.rstrip("m"))
        elif s.endswith("h"): minutes = int(s.rstrip("h")) * 60
        elif s.endswith("d"): minutes = int(s.rstrip("d")) * 1440
    if minutes < 5: minutes = 5
    display = f"every {minutes}m"
    if minutes >= 1440: display = f"every {minutes // 1440}d"
    elif minutes >= 60: display = f"every {minutes // 60}h"

    data = load_json(CRON_JOBS_FILE)
    jobs = data.get("jobs", [])
    n = now_iso()
    job = {"id": uuid.uuid4().hex[:12], "name": name, "prompt": prompt,
        "skills": [], "skill": None, "model": body.get("model"),
        "provider": None, "base_url": None, "script": None,
        "no_agent": False, "context_from": None,
        "schedule": {"kind": "interval", "minutes": minutes, "display": display},
        "schedule_display": display,
        "repeat": {"times": None, "completed": 0},
        "enabled": True, "state": "scheduled", "paused_at": None, "paused_reason": None,
        "created_at": n, "next_run_at": n, "last_run_at": None,
        "last_status": "pending", "last_error": None, "last_delivery_error": None,
        "deliver": body.get("deliver", "telegram"), "origin": None,
        "enabled_toolsets": None, "workdir": None, "profile": None}
    jobs.append(job)
    data["jobs"] = jobs
    data["updated_at"] = n
    write_json(CRON_JOBS_FILE, data)
    return jsonify(job), 201


@app.route("/api/tasks/cron/<job_id>", methods=["PUT"])
def tasks_cron_update(job_id):
    body = request.get_json(force=True)
    data = load_json(CRON_JOBS_FILE)
    for job in data.get("jobs", []):
        if job["id"] == job_id:
            if "enabled" in body:
                job["enabled"] = bool(body["enabled"])
                job["state"] = "paused" if not body["enabled"] else "scheduled"
                job["paused_at"] = now_iso() if not body["enabled"] else None
            for k in ("name", "prompt", "deliver"):
                if k in body and body[k]: job[k] = body[k]
            data["updated_at"] = now_iso()
            write_json(CRON_JOBS_FILE, data)
            return jsonify(job)
    return jsonify({"error": "not found"}), 404


@app.route("/api/tasks/cron/<job_id>", methods=["DELETE"])
def tasks_cron_delete(job_id):
    data = load_json(CRON_JOBS_FILE)
    jobs = data.get("jobs", [])
    new_jobs = [j for j in jobs if j["id"] != job_id]
    if len(new_jobs) == len(jobs):
        return jsonify({"error": "not found"}), 404
    data["jobs"] = new_jobs
    data["updated_at"] = now_iso()
    write_json(CRON_JOBS_FILE, data)
    return jsonify({"ok": True})


@app.route("/api/tasks/cron/<job_id>/output")
def tasks_cron_output(job_id):
    out_dir = CRON_OUTPUT_DIR / job_id
    if not out_dir.exists():
        return jsonify({"files": []})
    files = sorted(out_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files[:10]:
        try:
            content = f.read_text()[:10000] if f.stat().st_size < 50000 else "[文件过大]"
        except:
            content = "[读取失败]"
        result.append({"name": f.name, "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "content": content})
    return jsonify({"files": result})


# ===== Todos =====

@app.route("/api/tasks/todos")
def todos_list():
    ensure_todos()
    return jsonify(load_json(TODOS_FILE))


@app.route("/api/tasks/todos", methods=["POST"])
def todos_create():
    ensure_todos()
    body = request.get_json(force=True)
    data = load_json(TODOS_FILE)
    todo = {"id": str(int(datetime.now().timestamp() * 1000)),
        "content": (body.get("content") or "").strip(),
        "status": body.get("status", "pending"),
        "category": body.get("category", ""),
        "created_at": now_iso(), "updated_at": now_iso()}
    data.setdefault("todos", []).append(todo)
    data["updated_at"] = now_iso()
    write_json(TODOS_FILE, data)
    return jsonify(todo), 201


@app.route("/api/tasks/todos/<tid>", methods=["PUT"])
def todos_update(tid):
    ensure_todos()
    body = request.get_json(force=True)
    data = load_json(TODOS_FILE)
    for t in data.get("todos", []):
        if t["id"] == tid:
            for k in ("content", "status", "category"):
                if k in body: t[k] = body[k]
            t["updated_at"] = now_iso()
            data["updated_at"] = now_iso()
            write_json(TODOS_FILE, data)
            return jsonify(t)
    return jsonify({"error": "not found"}), 404


@app.route("/api/tasks/todos/<tid>", methods=["DELETE"])
def todos_delete(tid):
    ensure_todos()
    data = load_json(TODOS_FILE)
    data["todos"] = [t for t in data.get("todos", []) if t["id"] != tid]
    data["updated_at"] = now_iso()
    write_json(TODOS_FILE, data)
    return jsonify({"ok": True})


# ========== Memory API ==========

@app.route("/api/memory/sessions")
def memory_sessions():
    limit = request.args.get("limit", 20, type=int)
    offset = request.args.get("offset", 0, type=int)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, source, title, started_at, ended_at, message_count, "
            "tool_call_count, input_tokens, output_tokens "
            "FROM sessions ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
        sessions = []
        for r in rows:
            sessions.append({
                "id": r["id"], "source": r["source"], "title": r["title"],
                "started_at": datetime.fromtimestamp(r["started_at"]).isoformat() if r["started_at"] else None,
                "ended_at": datetime.fromtimestamp(r["ended_at"]).isoformat() if r["ended_at"] else None,
                "message_count": r["message_count"],
                "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"]})
        return jsonify({"sessions": sessions})
    finally:
        conn.close()


@app.route("/api/memory/sessions/<session_id>")
def memory_session_detail(session_id):
    conn = get_db()
    try:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            return jsonify({"error": "not found"}), 404
        msgs = conn.execute(
            "SELECT id, role, content, tool_name, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY timestamp LIMIT 200",
            (session_id,)).fetchall()
        messages = []
        for m in msgs:
            c = m["content"] or ""
            if len(c) > 2000: c = c[:2000] + "..."
            messages.append({"id": m["id"], "role": m["role"], "content": c,
                "tool_name": m["tool_name"],
                "timestamp": datetime.fromtimestamp(m["timestamp"]).isoformat() if m["timestamp"] else None})
        return jsonify({
            "session": {"id": session["id"], "source": session["source"],
                "title": session["title"], "model": session["model"],
                "started_at": datetime.fromtimestamp(session["started_at"]).isoformat() if session["started_at"] else None},
            "messages": messages})
    finally:
        conn.close()


@app.route("/api/memory/search")
def memory_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"results": []})
    limit = min(request.args.get("limit", 20, type=int), 50)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT m.id, m.session_id, m.role, m.content, m.timestamp, "
            "snippet(messages_fts, 0, '<b>', '</b>', '...', 40) as snip "
            "FROM messages_fts fts JOIN messages m ON fts.rowid = m.rowid "
            "WHERE messages_fts MATCH ? LIMIT ?",
            (q, limit)).fetchall()
        results = []
        for r in rows:
            c = r["content"] or ""
            if len(c) > 300: c = c[:300] + "..."
            results.append({"id": r["id"], "session_id": r["session_id"],
                "role": r["role"], "content": c, "snippet": r["snip"],
                "timestamp": datetime.fromtimestamp(r["timestamp"]).isoformat() if r["timestamp"] else None})
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})
    finally:
        conn.close()


# ========== Static ==========

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(STATIC_DIR, path)


if __name__ == "__main__":
    os.makedirs(STATIC_DIR, exist_ok=True)
    ensure_todos()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8082
    print(f"AI Panel running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
