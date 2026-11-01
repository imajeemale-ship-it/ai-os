"""SQLite-backed prototype for recoverable MVI work. Not wired to the HTTP server.

A claim is fenced by a fresh lease token. A late or superseded worker cannot
acknowledge another worker's attempt. SQLite is for one-host private pilots,
not a distributed cloud queue.
"""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class DurableQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL,
                available_at REAL NOT NULL, lease_until REAL,
                lease_token TEXT, worker_id TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                result TEXT, error TEXT
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(status, available_at, created_at)")
        os.chmod(self.path, 0o600)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def enqueue(self, job_id, kind, payload, max_attempts=3, now=None):
        if not (isinstance(job_id, str) and job_id and kind in {"upload", "url", "learn_url", "learn_upload"}
                and isinstance(payload, dict) and isinstance(max_attempts, int)
                and not isinstance(max_attempts, bool) and 1 <= max_attempts <= 10):
            raise ValueError("Invalid queue job")
        now = time.time() if now is None else now
        serialized = json.dumps(payload, sort_keys=True)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT OR IGNORE INTO jobs
                (job_id,kind,payload,status,max_attempts,available_at,created_at,updated_at)
                VALUES (?,?,?,'queued',?,?,?,?)""",
                (job_id, kind, serialized, max_attempts, now, now, now))
            existing = db.execute("SELECT kind,payload,max_attempts FROM jobs WHERE job_id=?",
                                  (job_id,)).fetchone()
            if (existing["kind"], existing["payload"], existing["max_attempts"]) != (
                    kind, serialized, max_attempts):
                raise ValueError("Job ID reused with different input")
            db.commit()
        return job_id

    def claim(self, worker_id, lease_seconds=120, now=None):
        if not isinstance(worker_id, str) or not worker_id.strip() or not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid worker or lease")
        now = time.time() if now is None else now
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE jobs SET status='failed', error='Lease expired; attempts exhausted',
                lease_until=NULL, lease_token=NULL, worker_id=NULL, updated_at=?
                WHERE status='running' AND lease_until<=? AND attempts>=max_attempts""",
                (now, now))
            row = db.execute("""SELECT * FROM jobs
                WHERE attempts<max_attempts AND
                ((status='queued' AND available_at<=?) OR
                 (status='running' AND lease_until<=?))
                ORDER BY created_at, job_id LIMIT 1""", (now, now)).fetchone()
            if row is None:
                db.commit()
                return None
            token = uuid.uuid4().hex
            db.execute("""UPDATE jobs SET status='running', attempts=attempts+1,
                lease_until=?, lease_token=?, worker_id=?, updated_at=?
                WHERE job_id=?""", (now+lease_seconds, token, worker_id, now, row["job_id"]))
            db.commit()
            return {"job_id": row["job_id"], "kind": row["kind"],
                    "payload": json.loads(row["payload"]), "attempt": row["attempts"]+1,
                    "lease_token": token, "lease_until": now+lease_seconds}

    def renew(self, job_id, lease_token, lease_seconds=120, now=None):
        """A living worker must renew before expiry; a stale worker cannot renew."""
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease")
        now = time.time() if now is None else now
        with self._db() as db:
            updated = db.execute("""UPDATE jobs SET lease_until=?, updated_at=?
                WHERE job_id=? AND status='running' AND lease_token=? AND lease_until>?""",
                (now+lease_seconds, now, job_id, lease_token, now)).rowcount
        return updated == 1

    def complete(self, job_id, lease_token, result=None, now=None):
        now = time.time() if now is None else now
        with self._db() as db:
            updated = db.execute("""UPDATE jobs SET status='completed', result=?,
                lease_until=NULL, lease_token=NULL, worker_id=NULL, updated_at=?
                WHERE job_id=? AND status='running' AND lease_token=? AND lease_until>?""",
                (json.dumps(result), now, job_id, lease_token, now)).rowcount
        return updated == 1

    def fail(self, job_id, lease_token, error, retry_delay=0, now=None):
        if not 0 <= retry_delay <= 86400:
            raise ValueError("Invalid retry delay")
        now = time.time() if now is None else now
        with self._db() as db:
            updated = db.execute("""UPDATE jobs SET
                status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END,
                available_at=?, error=?, lease_until=NULL, lease_token=NULL,
                worker_id=NULL, updated_at=?
                WHERE job_id=? AND status='running' AND lease_token=? AND lease_until>?""",
                (now+retry_delay, str(error)[:500], now, job_id, lease_token, now)).rowcount
        return updated == 1

    def get(self, job_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return None
        state = dict(row)
        state["payload"] = json.loads(state["payload"])
        state["result"] = json.loads(state["result"]) if state["result"] is not None else None
        return state
