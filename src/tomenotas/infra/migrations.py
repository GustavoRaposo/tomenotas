"""Notes database migrations (strategy detailed in the ROADMAP).

Rules:
- Every schema change enters as a NEW migration appended to MIGRATIONS;
  published migrations are immutable.
- The applied version lives in the database itself (PRAGMA user_version).
- apply_migrations applies only the pending ones, each in its own
  transaction: either it applies fully, or it rolls back and nothing
  changes. Before upgrading an existing database, the file gets a backup
  (the last N are kept).
"""

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..domain.errors import MigrationError

log = logging.getLogger("tomenotas.migrations")

BACKUPS_KEPT = 3


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    apply: Callable[[sqlite3.Connection], None]


def _v1_initial_schema(conn: sqlite3.Connection) -> None:
    # No executescript: it would COMMIT implicitly and break the transaction
    commands = [
        """CREATE TABLE notes (
               id         INTEGER PRIMARY KEY,
               created_at TEXT    NOT NULL,
               text       TEXT    NOT NULL,
               favorite   INTEGER NOT NULL DEFAULT 0
           )""",
        "CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE)",
        """CREATE TABLE note_tags (
               note_id INTEGER REFERENCES notes(id) ON DELETE CASCADE,
               tag_id  INTEGER REFERENCES tags(id)  ON DELETE CASCADE,
               PRIMARY KEY (note_id, tag_id)
           )""",
        """CREATE VIRTUAL TABLE notes_fts USING fts5(
               text, content='notes', content_rowid='id'
           )""",
        """CREATE TRIGGER notes_fts_ai AFTER INSERT ON notes BEGIN
               INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text);
           END""",
        """CREATE TRIGGER notes_fts_ad AFTER DELETE ON notes BEGIN
               INSERT INTO notes_fts(notes_fts, rowid, text)
               VALUES ('delete', old.id, old.text);
           END""",
        """CREATE TRIGGER notes_fts_au AFTER UPDATE OF text ON notes BEGIN
               INSERT INTO notes_fts(notes_fts, rowid, text)
               VALUES ('delete', old.id, old.text);
               INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text);
           END""",
    ]
    for command in commands:
        conn.execute(command)


def _v2_filename_column(conn: sqlite3.Connection) -> None:
    # .txt mirror: maps each note to its file in notes/ (legacy scripts)
    conn.execute("ALTER TABLE notes ADD COLUMN filename TEXT")


def _v3_critical_column(conn: sqlite3.Connection) -> None:
    # critical notes: periodic alarm until the user deactivates them
    conn.execute(
        "ALTER TABLE notes ADD COLUMN critical INTEGER NOT NULL DEFAULT 0"
    )


MIGRATIONS = [
    Migration(1, "initial schema (notes, tags, note_tags, FTS5)",
              _v1_initial_schema),
    Migration(2, "filename column for the .txt mirror", _v2_filename_column),
    Migration(3, "critical column for alarm notes", _v3_critical_column),
]

SCHEMA_VERSION = MIGRATIONS[-1].version


def apply_migrations(conn: sqlite3.Connection, db_path: Path | None = None,
                     migrations=None, now=datetime.now) -> list[int]:
    """Applies the pending migrations; returns the applied versions."""
    migrations = MIGRATIONS if migrations is None else migrations
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    pending = [m for m in migrations if m.version > current]
    if not pending:
        return []

    # Backup before upgrading a pre-existing database (version > 0)
    if db_path is not None and current > 0 and Path(db_path).exists():
        _backup(Path(db_path), current, now())

    applied = []
    previous_isolation = conn.isolation_level
    conn.isolation_level = None  # transactions handled manually
    try:
        for migration in pending:
            try:
                conn.execute("BEGIN")
                migration.apply(conn)
                conn.execute(f"PRAGMA user_version = {int(migration.version)}")
                conn.execute("COMMIT")
            except Exception as error:
                conn.execute("ROLLBACK")
                raise MigrationError(
                    f"Falha ao migrar o banco de notas para a versão "
                    f"{migration.version} ({migration.description}): {error}. "
                    f"Nenhum dado foi alterado."
                ) from error
            log.info("migration %d applied: %s",
                     migration.version, migration.description)
            applied.append(migration.version)
    finally:
        conn.isolation_level = previous_isolation
    return applied


def _backup(db_path: Path, version: int, now: datetime) -> None:
    name = f"{db_path.name}.bak-v{version}-{now.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(db_path, db_path.with_name(name))
    log.info("database backup created: %s", name)
    backups = sorted(db_path.parent.glob(db_path.name + ".bak-*"))
    for old in backups[:-BACKUPS_KEPT]:
        old.unlink()
        log.info("old backup removed: %s", old.name)
