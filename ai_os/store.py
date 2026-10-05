"""SQLite persistence and domain operations for AI-OS."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, goal TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','paused','done')),
 priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'ready' CHECK(status IN ('ready','in_progress','blocked','done')),
 priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
 due_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
 id TEXT PRIMARY KEY, action_type TEXT NOT NULL, scope TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','expired')),
 expires_at TEXT, created_at TEXT NOT NULL, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
 event_type TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_ready ON tasks(status, priority, due_at);
CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_type, entity_id, created_at);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status, action_type);
"""

GATED_ACTIONS = {"send_message", "spend_money", "trade", "publish", "delete_data", "deploy"}
VALID_ACTIONS = GATED_ACTIONS | {"prepare", "read", "analyze", "draft"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class AIOS:
    def __init__(self, db_path: str | Path | None = None):
        default = Path.home() / ".ai-os" / "ai_os.db"
        self.db_path = Path(db_path or os.environ.get("AI_OS_DB", default))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def _connection(self):
        """Commit successful units of work and always close the SQLite handle."""
        from contextlib import closing
        from contextlib import contextmanager

        @contextmanager
        def managed():
            with closing(self.connect()) as db:
                with db:
                    yield db
        return managed()

    def _read(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._connection() as db:
            return db.execute(query, params).fetchall()

    def _event(self, db: sqlite3.Connection, entity_type: str, entity_id: str,
               event_type: str, payload: dict[str, Any] | None = None) -> str:
        event_id = new_id("evt")
        db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                   (event_id, entity_type, entity_id, event_type,
                    json.dumps(payload or {}, sort_keys=True), now()))
        return event_id

    def add_project(self, name: str, goal: str = "", priority: int = 3) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("Project name cannot be empty")
        self._check_priority(priority)
        timestamp, project_id = now(), new_id("prj")
        with self._connection() as db:
            db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?)",
                       (project_id, name.strip(), goal.strip(), "active", priority, timestamp, timestamp))
            self._event(db, "project", project_id, "project.created", {"name": name.strip()})
            return dict(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())

    def list_projects(self) -> list[dict[str, Any]]:
        rows = self._read(
            """SELECT p.*, COUNT(t.id) AS open_tasks FROM projects p
               LEFT JOIN tasks t ON t.project_id=p.id AND t.status!='done'
               GROUP BY p.id ORDER BY p.priority, p.name"""
        )
        return [dict(row) for row in rows]

    def add_task(self, project_id: str, title: str, detail: str = "",
                 priority: int = 3, due_at: str | None = None) -> dict[str, Any]:
        if not title.strip():
            raise ValueError("Task title cannot be empty")
        self._check_priority(priority)
        timestamp, task_id = now(), new_id("tsk")
        with self._connection() as db:
            if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
                raise ValueError(f"Unknown project: {project_id}")
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)",
                       (task_id, project_id, title.strip(), detail.strip(), "ready",
                        priority, due_at, timestamp, timestamp))
            self._event(db, "task", task_id, "task.created",
                        {"project_id": project_id, "title": title.strip()})
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT t.*, p.name AS project_name FROM tasks t JOIN projects p ON p.id=t.project_id"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE t.status=?"
            params = (status,)
        query += " ORDER BY t.priority, t.due_at IS NULL, t.due_at, t.created_at"
        return [dict(row) for row in self._read(query, params)]

    def set_task_status(self, task_id: str, status: str) -> dict[str, Any]:
        if status not in {"ready", "in_progress", "blocked", "done"}:
            raise ValueError(f"Invalid task status: {status}")
        with self._connection() as db:
            if not db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
                raise ValueError(f"Unknown task: {task_id}")
            db.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                       (status, now(), task_id))
            self._event(db, "task", task_id, f"task.{status}")
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def request_approval(self, action_type: str, scope: str, reason: str = "",
                         expires_at: str | None = None) -> dict[str, Any]:
        if action_type not in VALID_ACTIONS:
            raise ValueError(f"Unknown action type: {action_type}")
        approval_id, timestamp = new_id("apr"), now()
        with self._connection() as db:
            db.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?)",
                       (approval_id, action_type, scope, reason, "pending", expires_at, timestamp, None))
            self._event(db, "approval", approval_id, "approval.requested",
                        {"action_type": action_type, "scope": scope})
            return dict(db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone())

    def decide_approval(self, approval_id: str, decision: str) -> dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Decision must be approved or rejected")
        with self._connection() as db:
            row = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if not row:
                raise ValueError(f"Unknown approval: {approval_id}")
            if row["status"] != "pending":
                raise ValueError(f"Approval is already {row['status']}")
            db.execute("UPDATE approvals SET status=?, decided_at=? WHERE id=?",
                       (decision, now(), approval_id))
            self._event(db, "approval", approval_id, f"approval.{decision}",
                        {"action_type": row["action_type"], "scope": row["scope"]})
            return dict(db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone())

    def authorize(self, action_type: str, scope: str, approval_id: str | None = None) -> bool:
        """Gated actions require an approved, unexpired exact-scope approval."""
        if action_type not in VALID_ACTIONS:
            return False
        if action_type not in GATED_ACTIONS:
            return True
        if not approval_id:
            return False
        with self._connection() as db:
            row = db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if not row or row["status"] != "approved":
                return False
            if row["action_type"] != action_type or row["scope"] != scope:
                return False
            if row["expires_at"] and row["expires_at"] < now():
                db.execute("UPDATE approvals SET status='expired' WHERE id=?", (approval_id,))
                return False
            return True

    def daily_brief(self) -> dict[str, Any]:
        projects = [dict(r) for r in self._read(
            "SELECT * FROM projects WHERE status='active' ORDER BY priority, name")]
        tasks = [dict(r) for r in self._read(
            """SELECT t.*, p.name AS project_name FROM tasks t JOIN projects p ON p.id=t.project_id
               WHERE p.status='active' AND t.status IN ('ready','in_progress','blocked')
               ORDER BY CASE t.status WHEN 'in_progress' THEN 0 ELSE 1 END,
               t.priority, t.due_at IS NULL, t.due_at, t.created_at LIMIT 10""")]
        pending = [dict(r) for r in self._read(
            "SELECT * FROM approvals WHERE status='pending' ORDER BY created_at")]
        return {"projects": projects, "next_actions": tasks, "pending_approvals": pending}

    def record_event(self, entity_type: str, entity_id: str, event_type: str,
                     payload: dict[str, Any] | None = None) -> str:
        if not entity_type.strip() or not entity_id.strip() or not event_type.strip():
            raise ValueError("Event entity and type cannot be empty")
        with self._connection() as db:
            return self._event(db, entity_type, entity_id, event_type, payload)

    def recent_events(self, limit: int = 25) -> list[dict[str, Any]]:
        rows = self._read("SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,))
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result

    @staticmethod
    def _check_priority(priority: int) -> None:
        if not isinstance(priority, int) or not 1 <= priority <= 5:
            raise ValueError("Priority must be an integer from 1 (highest) to 5")
