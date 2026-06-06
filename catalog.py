"""
Catalog — SQLite-based file index with FTS5 full-text search.

Stores file metadata, content summaries, categories, and scan history.
FTS5 enables fast keyword search over file content.
"""

import json
import logging
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Optional

try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)

FTS_FALLBACK_STOPWORDS = {
    "and",
    "before",
    "for",
    "from",
    "into",
    "or",
    "the",
    "with",
}


def _fallback_fts_match_query(query: str) -> str:
    """Build a syntax-safe FTS5 fallback query for operator-style searches.

    The primary FTS5 path keeps SQLite's normal MATCH behavior.  This fallback
    is only used when that path errors or produces no rows, which happens for
    useful FileMind benchmark/operator queries containing characters such as
    hyphens or percent signs.  Quoting terms prevents FTS5 from treating
    punctuation as operators or column selectors; joining with OR preserves
    recall for broad diagnostic queries.
    """

    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in re.findall(r"[A-Za-z0-9_./-]+", query.lower()):
        term = raw_term.strip("._-/")
        if len(term) < 2 or term in FTS_FALLBACK_STOPWORDS:
            continue
        if term in seen:
            continue
        seen.add(term)
        terms.append(f'"{term.replace(chr(34), chr(34) * 2)}"')
    return " OR ".join(terms)


def _process_exists(pid: int) -> bool:
    """Return whether a process id appears to still be alive."""
    if pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0 and str(pid) in completed.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _source_freshness_metadata(
    *,
    source_mtime: float,
    source_size: int,
    source_content_hash: str,
) -> str:
    """Serialize source-file freshness evidence for catalog consumers."""

    return json.dumps(
        {
            "source_mtime": float(source_mtime),
            "source_size": int(source_size),
            "source_content_hash": str(source_content_hash),
        },
        sort_keys=True,
    )


# ── Schema ──────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- File tracking table
CREATE TABLE IF NOT EXISTS file_index (
    path TEXT PRIMARY KEY,
    full_path TEXT NOT NULL,
    size INTEGER DEFAULT 0,
    mtime REAL DEFAULT 0,
    content_hash TEXT DEFAULT '',
    source_mtime REAL,
    source_size INTEGER,
    source_content_hash TEXT,
    source_metadata TEXT DEFAULT '{}',
    ext TEXT DEFAULT '',
    category TEXT DEFAULT 'unknown',
    confidence REAL DEFAULT 0.0,
    chunk_count INTEGER DEFAULT 0,
    indexed_at REAL DEFAULT 0,
    is_duplicate INTEGER DEFAULT 0,
    tags TEXT DEFAULT '[]',
    content_summary TEXT DEFAULT ''
);

-- FTS5 virtual table for content search
CREATE VIRTUAL TABLE IF NOT EXISTS file_content_fts USING fts5(
    path,
    content_summary,
    category,
    ext,
    content='file_index',
    content_rowid='rowid'
);

-- FTS5 insert trigger
CREATE TRIGGER IF NOT EXISTS file_index_ai AFTER INSERT ON file_index BEGIN
    INSERT INTO file_content_fts(rowid, path, content_summary, category, ext)
    VALUES (new.rowid, new.path, new.content_summary, new.category, new.ext);
END;

-- FTS5 delete trigger
CREATE TRIGGER IF NOT EXISTS file_index_ad AFTER DELETE ON file_index BEGIN
    INSERT INTO file_content_fts(file_content_fts, rowid, path, content_summary, category, ext)
    VALUES ('delete', old.rowid, old.path, old.content_summary, old.category, old.ext);
END;

-- FTS5 update trigger
CREATE TRIGGER IF NOT EXISTS file_index_au AFTER UPDATE ON file_index BEGIN
    INSERT INTO file_content_fts(file_content_fts, rowid, path, content_summary, category, ext)
    VALUES ('delete', old.rowid, old.path, old.content_summary, old.category, old.ext);
    INSERT INTO file_content_fts(rowid, path, content_summary, category, ext)
    VALUES (new.rowid, new.path, new.content_summary, new.category, new.ext);
END;

-- Duplicate tracking
CREATE TABLE IF NOT EXISTS duplicates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_group TEXT NOT NULL,
    path TEXT NOT NULL,
    is_exact INTEGER DEFAULT 0,
    similarity REAL DEFAULT 0.0
);

-- Scan history
CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL,
    completed_at REAL,
    heartbeat_at REAL,
    pid INTEGER,
    mode TEXT DEFAULT 'unknown',
    command TEXT DEFAULT '',
    files_scanned INTEGER DEFAULT 0,
    files_changed INTEGER DEFAULT 0,
    files_new INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'
);

-- Schema Migrations
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL,
    description TEXT
);
"""


class Catalog:
    """SQLite-based file index with FTS5 search."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the catalog.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path) if db_path else config.sqlite_db
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-2000")  # 2MB cache
        return self._conn

    def init_db(self):
        """Create database schema if not exists."""
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
        self._apply_migrations()
        logger.info(f"Catalog initialized: {self.db_path}")

    def _apply_migrations(self):
        """Run backward-compatible schema migrations."""

        def is_applied(version: int) -> bool:
            return (
                self.conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
                ).fetchone()
                is not None
            )

        def record(version: int, desc: str):
            self.conn.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (version, time.time(), desc),
            )
            self.conn.commit()

        if not is_applied(1):
            logger.info(
                "Applying Migration 1: Rebuilding FTS with custom tokenchars..."
            )
            self.conn.execute("DROP TRIGGER IF EXISTS file_index_ai")
            self.conn.execute("DROP TRIGGER IF EXISTS file_index_ad")
            self.conn.execute("DROP TRIGGER IF EXISTS file_index_au")
            self.conn.execute("DROP TABLE IF EXISTS file_content_fts")
            self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS file_content_fts USING fts5(
                path, content_summary, category, ext,
                content='file_index', content_rowid='rowid',
                tokenize = "unicode61 remove_diacritics 2 tokenchars '-_./'"
            )
            """)
            self.conn.execute(
                "INSERT INTO file_content_fts(file_content_fts) VALUES('rebuild')"
            )
            self.conn.executescript("""
            CREATE TRIGGER file_index_ai AFTER INSERT ON file_index BEGIN
                INSERT INTO file_content_fts(rowid, path, content_summary, category, ext)
                VALUES (new.rowid, new.path, new.content_summary, new.category, new.ext);
            END;
            CREATE TRIGGER file_index_ad AFTER DELETE ON file_index BEGIN
                INSERT INTO file_content_fts(file_content_fts, rowid, path, content_summary, category, ext)
                VALUES ('delete', old.rowid, old.path, old.content_summary, old.category, old.ext);
            END;
            CREATE TRIGGER file_index_au AFTER UPDATE ON file_index BEGIN
                INSERT INTO file_content_fts(file_content_fts, rowid, path, content_summary, category, ext)
                VALUES ('delete', old.rowid, old.path, old.content_summary, old.category, old.ext);
                INSERT INTO file_content_fts(rowid, path, content_summary, category, ext)
                VALUES (new.rowid, new.path, new.content_summary, new.category, new.ext);
            END;
            """)
            record(1, "Rebuild FTS5 with custom tokenchars")

        if not is_applied(2):
            logger.info("Applying Migration 2: Adding tier column...")
            try:
                self.conn.execute(
                    "ALTER TABLE file_index ADD COLUMN tier TEXT DEFAULT 'user'"
                )
            except Exception:
                pass
            record(2, "Add tier column to file_index")

        if not is_applied(3):
            logger.info("Applying Migration 3: Adding needs_classification column...")
            try:
                self.conn.execute(
                    "ALTER TABLE file_index ADD COLUMN needs_classification INTEGER DEFAULT 0"
                )
            except Exception:
                pass
            record(3, "Add needs_classification to file_index")

        if not is_applied(4):
            logger.info("Applying Migration 4: Adding scan process metadata...")
            scan_log_columns = {
                row["name"]
                for row in self.conn.execute("PRAGMA table_info(scan_log)").fetchall()
            }
            column_statements = {
                "heartbeat_at": "ALTER TABLE scan_log ADD COLUMN heartbeat_at REAL",
                "pid": "ALTER TABLE scan_log ADD COLUMN pid INTEGER",
                "mode": "ALTER TABLE scan_log ADD COLUMN mode TEXT DEFAULT 'unknown'",
                "command": "ALTER TABLE scan_log ADD COLUMN command TEXT DEFAULT ''",
            }
            for column, statement in column_statements.items():
                if column in scan_log_columns:
                    continue
                try:
                    self.conn.execute(statement)
                except sqlite3.OperationalError:
                    pass
            self.conn.execute(
                "UPDATE scan_log SET heartbeat_at = started_at WHERE heartbeat_at IS NULL"
            )
            record(4, "Add process metadata to scan_log")

        file_index_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(file_index)").fetchall()
        }
        source_column_statements = {
            "source_mtime": "ALTER TABLE file_index ADD COLUMN source_mtime REAL",
            "source_size": "ALTER TABLE file_index ADD COLUMN source_size INTEGER",
            "source_content_hash": (
                "ALTER TABLE file_index ADD COLUMN source_content_hash TEXT"
            ),
            "source_metadata": (
                "ALTER TABLE file_index ADD COLUMN source_metadata TEXT DEFAULT '{}'"
            ),
        }
        for column, statement in source_column_statements.items():
            if column in file_index_columns:
                continue
            try:
                self.conn.execute(statement)
            except sqlite3.OperationalError:
                pass

        if not is_applied(5):
            logger.info("Applying Migration 5: Adding source freshness metadata...")
            rows = self.conn.execute(
                """
                SELECT path, size, mtime, content_hash
                FROM file_index
                """
            ).fetchall()
            for row in rows:
                source_size = int(row["size"] or 0)
                source_mtime = float(row["mtime"] or 0.0)
                source_content_hash = str(row["content_hash"] or "")
                self.conn.execute(
                    """
                    UPDATE file_index
                    SET source_size = ?,
                        source_mtime = ?,
                        source_content_hash = ?,
                        source_metadata = ?
                    WHERE path = ?
                    """,
                    (
                        source_size,
                        source_mtime,
                        source_content_hash,
                        _source_freshness_metadata(
                            source_mtime=source_mtime,
                            source_size=source_size,
                            source_content_hash=source_content_hash,
                        ),
                        row["path"],
                    ),
                )
            record(5, "Add source freshness metadata to file_index")

    def upsert_file(
        self,
        path: str,
        full_path: str,
        size: int,
        mtime: float,
        content_hash: str,
        ext: str,
        content_summary: str = "",
        category: str = "unknown",
        confidence: float = 0.0,
        chunk_count: int = 0,
        tags: list[str] | None = None,
        tier: str = "user",
        source_mtime: float | None = None,
        source_size: int | None = None,
        source_content_hash: str | None = None,
    ):
        """
        Insert or update a file record.

        Args:
            path: Relative path
            full_path: Absolute path
            size: File size in bytes
            mtime: Modification timestamp
            content_hash: MD5 hash for change detection
            ext: File extension
            content_summary: Extracted content trimmed to the configured budget
            category: AI-assigned category
            confidence: Classification confidence
            chunk_count: Number of embedded chunks
            tags: Optional tags list
            tier: Quality routing tier
            source_mtime: Source file modification timestamp used for freshness checks
            source_size: Source file size used for freshness checks
            source_content_hash: Source content hash used for freshness checks
        """
        tags_json = json.dumps(tags or [])
        indexed_at = time.time()
        recorded_source_mtime = mtime if source_mtime is None else source_mtime
        recorded_source_size = size if source_size is None else source_size
        recorded_source_hash = (
            content_hash if source_content_hash is None else source_content_hash
        )
        source_metadata = _source_freshness_metadata(
            source_mtime=recorded_source_mtime,
            source_size=recorded_source_size,
            source_content_hash=recorded_source_hash,
        )

        self.conn.execute(
            """
            INSERT INTO file_index (
                path, full_path, size, mtime, content_hash, ext,
                source_mtime, source_size, source_content_hash, source_metadata,
                category, confidence, chunk_count, indexed_at,
                content_summary, tags, tier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                full_path=excluded.full_path,
                size=excluded.size,
                mtime=excluded.mtime,
                content_hash=excluded.content_hash,
                ext=excluded.ext,
                source_mtime=excluded.source_mtime,
                source_size=excluded.source_size,
                source_content_hash=excluded.source_content_hash,
                source_metadata=excluded.source_metadata,
                category=excluded.category,
                confidence=excluded.confidence,
                chunk_count=excluded.chunk_count,
                indexed_at=excluded.indexed_at,
                content_summary=excluded.content_summary,
                tags=excluded.tags,
                tier=excluded.tier
            """,
            (
                path,
                full_path,
                size,
                mtime,
                content_hash,
                ext,
                recorded_source_mtime,
                recorded_source_size,
                recorded_source_hash,
                source_metadata,
                category,
                confidence,
                chunk_count,
                indexed_at,
                content_summary[: config.max_content_length],
                tags_json,
                tier,
            ),
        )

    def get_file(self, path: str) -> Optional[dict]:
        """Get file record by path."""
        row = self.conn.execute(
            "SELECT * FROM file_index WHERE path = ?", (path,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_hash(self, content_hash: str) -> list[dict]:
        """Find files with matching content hash (duplicates)."""
        rows = self.conn.execute(
            "SELECT * FROM file_index WHERE content_hash = ?", (content_hash,)
        ).fetchall()
        return [dict(r) for r in rows]

    def fts_search(self, query: str, top_k: int = 20) -> list[dict]:
        """Full-text keyword search via FTS5."""
        sql = """
            SELECT f.*, rank FROM file_content_fts f
            WHERE file_content_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """
        try:
            # Use SQLite FTS5's normal parser first for precise quoted/operator
            # queries.  Escape literal quotes but otherwise preserve existing
            # behavior for callers that intentionally use FTS5 syntax.
            rows = self.conn.execute(
                sql,
                (query.replace('"', '""'), top_k),
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            logger.debug("Primary FTS search failed; trying safe fallback: %s", exc)

        fallback_query = _fallback_fts_match_query(query)
        if not fallback_query:
            return []
        rows = self.conn.execute(sql, (fallback_query, top_k)).fetchall()
        return [dict(r) for r in rows]

    def get_files_by_category(self, category: str) -> list[dict]:
        """Get all files in a category."""
        rows = self.conn.execute(
            "SELECT * FROM file_index WHERE category = ? ORDER BY path", (category,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_files_by_type(self, ext: str) -> list[dict]:
        """Get all files with a specific extension."""
        rows = self.conn.execute(
            "SELECT * FROM file_index WHERE ext = ? ORDER BY path", (ext.lower(),)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_files(self) -> list[dict]:
        """Get all indexed files in stable path order."""
        rows = self.conn.execute("SELECT * FROM file_index ORDER BY path").fetchall()
        return [dict(r) for r in rows]

    def update_category(self, path: str, category: str, confidence: float):
        """Update file category and confidence."""
        self.conn.execute(
            "UPDATE file_index SET category = ?, confidence = ? WHERE path = ?",
            (category, confidence, path),
        )
        self.conn.commit()

    def update_content_summary(self, path: str, content_summary: str):
        """Update the stored extracted summary for a file."""
        self.conn.execute(
            "UPDATE file_index SET content_summary = ?, indexed_at = ? WHERE path = ?",
            (content_summary[: config.max_content_length], time.time(), path),
        )

    def update_chunk_count(self, path: str, count: int):
        """Update file's chunk count."""
        self.conn.execute(
            "UPDATE file_index SET chunk_count = ? WHERE path = ?", (count, path)
        )

    def reset_all_chunk_counts(self):
        """Reset chunk counts before a full vector-store rebuild."""
        self.conn.execute("UPDATE file_index SET chunk_count = 0")

    def move_file(
        self,
        old_path: str,
        new_path: str,
        new_full_path: str,
        size: int,
        mtime: float,
        content_hash: str,
        ext: str,
    ) -> bool:
        """Update an indexed file's path after a move or rename."""
        source_metadata = _source_freshness_metadata(
            source_mtime=mtime,
            source_size=size,
            source_content_hash=content_hash,
        )
        cursor = self.conn.execute(
            """
            UPDATE file_index
            SET path = ?, full_path = ?, size = ?, mtime = ?,
                content_hash = ?, ext = ?, indexed_at = ?,
                source_mtime = ?, source_size = ?,
                source_content_hash = ?, source_metadata = ?
            WHERE path = ?
            """,
            (
                new_path,
                new_full_path,
                size,
                mtime,
                content_hash,
                ext,
                time.time(),
                mtime,
                size,
                content_hash,
                source_metadata,
                old_path,
            ),
        )
        return cursor.rowcount > 0

    def mark_duplicate(self, path: str, is_dup: bool = True):
        """Mark a file as a duplicate."""
        self.conn.execute(
            "UPDATE file_index SET is_duplicate = ? WHERE path = ?",
            (1 if is_dup else 0, path),
        )

    def delete_file(self, path: str):
        """Remove a file record (FTS triggers handle cleanup)."""
        self.conn.execute("DELETE FROM file_index WHERE path = ?", (path,))

    def delete_by_hash(self, content_hash: str):
        """Delete all files with matching hash."""
        self.conn.execute(
            "DELETE FROM file_index WHERE content_hash = ?", (content_hash,)
        )

    def file_exists(self, path: str) -> bool:
        """Check if a file is indexed."""
        row = self.conn.execute(
            "SELECT 1 FROM file_index WHERE path = ?", (path,)
        ).fetchone()
        return row is not None

    def count(self) -> int:
        """Total files indexed."""
        return self.conn.execute("SELECT COUNT(*) as c FROM file_index").fetchone()["c"]

    def get_stats(self) -> dict:
        """Get catalog statistics."""
        total = self.count()
        categories = {}
        for row in self.conn.execute(
            "SELECT category, COUNT(*) as cnt FROM file_index GROUP BY category"
        ):
            categories[row["category"]] = row["cnt"]

        extensions = {}
        for row in self.conn.execute(
            "SELECT ext, COUNT(*) as cnt FROM file_index GROUP BY ext ORDER BY cnt DESC LIMIT 10"
        ):
            extensions[row["ext"]] = row["cnt"]

        total_size = (
            self.conn.execute("SELECT SUM(size) as s FROM file_index").fetchone()["s"]
            or 0
        )

        dups = self.conn.execute(
            "SELECT COUNT(*) as c FROM file_index WHERE is_duplicate = 1"
        ).fetchone()["c"]

        return {
            "total_files": total,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "categories": categories,
            "top_extensions": extensions,
            "duplicates": dups,
        }

    # ── Scan Logging ───────────────────────────────────────────────────

    def start_scan(
        self,
        mode: str = "unknown",
        command: str | None = None,
        pid: int | None = None,
    ) -> int:
        """Log scan start, returns scan_id."""
        self.reconcile_running_scans(stale_legacy=True)
        started_at = time.time()
        cursor = self.conn.execute(
            """
            INSERT INTO scan_log (started_at, heartbeat_at, pid, mode, command, status)
            VALUES (?, ?, ?, ?, ?, 'running')
            """,
            (
                started_at,
                started_at,
                os.getpid() if pid is None else pid,
                mode,
                command or "",
            ),
        )
        self.conn.commit()
        scan_id = cursor.lastrowid
        if scan_id is None:
            raise RuntimeError("SQLite did not return a scan_log row id")
        return scan_id

    def complete_scan(
        self,
        scan_id: int,
        files_scanned: int,
        files_changed: int,
        files_new: int,
        files_deleted: int,
        errors: int,
        status: str | None = None,
    ):
        """Log scan completion."""
        final_status = status or ("completed" if errors == 0 else "failed")
        self.conn.execute(
            """
            UPDATE scan_log SET
                completed_at = ?, heartbeat_at = ?, files_scanned = ?, files_changed = ?,
                files_new = ?, files_deleted = ?, errors = ?, status = ?
            WHERE id = ?
            """,
            (
                time.time(),
                time.time(),
                files_scanned,
                files_changed,
                files_new,
                files_deleted,
                errors,
                final_status,
                scan_id,
            ),
        )
        self.conn.commit()

    def fail_scan(self, scan_id: int, error: str = ""):
        """Log scan failure."""
        self.conn.execute(
            "UPDATE scan_log SET completed_at = ?, heartbeat_at = ?, status = 'failed' WHERE id = ?",
            (time.time(), time.time(), scan_id),
        )
        self.conn.commit()

    def heartbeat_scan(self, scan_id: int):
        """Refresh the heartbeat for an in-progress scan."""
        self.conn.execute(
            "UPDATE scan_log SET heartbeat_at = ? WHERE id = ? AND status = 'running'",
            (time.time(), scan_id),
        )
        self.conn.commit()

    def reconcile_running_scans(
        self,
        *,
        stale_after_seconds: float | None = None,
        stale_legacy: bool = False,
    ) -> list[dict]:
        """Mark dead running scans as stale and return the rows changed.

        New scan rows include a PID, so dead-process detection is authoritative.
        Legacy rows without a PID can be marked stale when a new locked scan
        starts (``stale_legacy=True``) or when an explicit age threshold is
        supplied for maintenance.
        """
        now = time.time()
        rows = self.conn.execute(
            """
            SELECT * FROM scan_log
            WHERE status = 'running'
            ORDER BY started_at ASC
            """
        ).fetchall()
        stale_rows: list[dict] = []

        for row in rows:
            data = dict(row)
            raw_pid = data.get("pid")
            pid = int(raw_pid) if raw_pid not in (None, "") else None
            heartbeat_at = data.get("heartbeat_at") or data.get("started_at") or now
            stale_reason = ""

            if pid is not None and not _process_exists(pid):
                stale_reason = f"pid_not_running:{pid}"
            elif pid is None and stale_legacy:
                stale_reason = "legacy_running_row_without_pid"
            elif (
                pid is None
                and stale_after_seconds is not None
                and now - float(heartbeat_at) > stale_after_seconds
            ):
                stale_reason = "legacy_running_row_timed_out"

            if not stale_reason:
                continue

            self.conn.execute(
                """
                UPDATE scan_log
                SET completed_at = ?, heartbeat_at = ?, status = 'stale'
                WHERE id = ? AND status = 'running'
                """,
                (now, now, data["id"]),
            )
            data["stale_reason"] = stale_reason
            stale_rows.append(data)

        if stale_rows:
            self.conn.commit()
        return stale_rows

    def get_running_scans(self, *, reconcile: bool = True) -> list[dict]:
        """Return scan_log rows that still represent live in-progress scans."""
        if reconcile:
            self.reconcile_running_scans()
        rows = self.conn.execute(
            """
            SELECT * FROM scan_log
            WHERE status = 'running'
            ORDER BY started_at DESC
            """
        )
        return [dict(r) for r in rows]

    def get_scan_history(self, limit: int = 10) -> list[dict]:
        """Get recent scan logs."""
        rows = self.conn.execute(
            "SELECT * FROM scan_log ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Duplicate Tracking ──────────────────────────────────────────────

    def add_duplicate(
        self, hash_group: str, path: str, is_exact: bool = True, similarity: float = 1.0
    ):
        """Record a duplicate file."""
        self.conn.execute(
            """
            INSERT INTO duplicates (hash_group, path, is_exact, similarity)
            VALUES (?, ?, ?, ?)
            """,
            (hash_group, path, 1 if is_exact else 0, similarity),
        )

    def get_duplicates(self) -> list[dict]:
        """Get all duplicate groups."""
        rows = self.conn.execute(
            """
            SELECT d.*, f.size, f.category
            FROM duplicates d
            LEFT JOIN file_index f ON d.path = f.path
            ORDER BY d.hash_group, d.path
            """
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Cleanup ─────────────────────────────────────────────────────────

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.init_db()
        return self

    def __exit__(self, *args):
        self.close()
