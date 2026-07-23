"""Tests for tomenotas.infra.migrations — schema versioning without data
loss."""

import sqlite3
from datetime import datetime

import pytest

from tomenotas.domain.errors import MigrationError
from tomenotas.infra.migrations import (
    MIGRATIONS,
    SCHEMA_VERSION,
    Migration,
    apply_migrations,
)

CLOCK = lambda: datetime(2026, 7, 23, 1, 2, 3)  # noqa: E731


def version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def test_new_database_applies_all_and_records_version():
    conn = sqlite3.connect(":memory:")
    applied = apply_migrations(conn)
    assert applied == [m.version for m in MIGRATIONS]
    assert version(conn) == SCHEMA_VERSION
    # the final schema really exists
    conn.execute(
        "INSERT INTO notes (created_at, text, favorite, filename) "
        "VALUES ('2026-07-23T00:00:00', 'olá', 0, 'a.txt')"
    )
    conn.close()


def test_reapplying_is_idempotent():
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    assert apply_migrations(conn) == []
    assert version(conn) == SCHEMA_VERSION
    conn.close()


def test_old_database_migrates_preserving_data():
    conn = sqlite3.connect(":memory:")
    # installs only v1 (initial schema, no filename column) and populates
    apply_migrations(conn, migrations=MIGRATIONS[:1])
    assert version(conn) == 1
    conn.execute(
        "INSERT INTO notes (created_at, text, favorite) "
        "VALUES ('2026-07-22T10:00:00', 'nota antiga', 1)"
    )
    conn.commit()

    applied = apply_migrations(conn)  # program upgrade

    assert applied == [m.version for m in MIGRATIONS[1:]]
    assert version(conn) == SCHEMA_VERSION
    row = conn.execute(
        "SELECT text, favorite, filename, critical FROM notes"
    ).fetchone()
    assert row == ("nota antiga", 1, None, 0)  # nothing lost, not critical
    conn.close()


def test_v3_adds_critical_column_preserving_v2_data():
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn, migrations=MIGRATIONS[:2])  # up to v2
    assert version(conn) == 2
    conn.execute(
        "INSERT INTO notes (created_at, text, favorite, filename) "
        "VALUES ('2026-07-22T10:00:00', 'nota v2', 1, 'a.txt')"
    )
    conn.commit()

    apply_migrations(conn)

    row = conn.execute(
        "SELECT text, favorite, filename, critical FROM notes"
    ).fetchone()
    assert row == ("nota v2", 1, "a.txt", 0)  # default: not critical
    conn.close()


def test_failing_migration_rolls_back():
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)

    def breaks(c):
        c.execute("INSERT INTO tags (name) VALUES ('antes-da-falha')")
        c.execute("ISSO NAO E SQL")

    bad = MIGRATIONS + [Migration(99, "breaks midway", breaks)]
    with pytest.raises(MigrationError, match="99"):
        apply_migrations(conn, migrations=bad)

    assert version(conn) == SCHEMA_VERSION  # version did not advance
    assert conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0
    conn.close()


def test_upgrade_backs_up_the_file(tmp_path):
    db = tmp_path / "notes.db"
    conn = sqlite3.connect(db)
    apply_migrations(conn, db_path=db, migrations=MIGRATIONS[:1], now=CLOCK)
    conn.close()

    conn = sqlite3.connect(db)
    apply_migrations(conn, db_path=db, now=CLOCK)

    backups = list(tmp_path.glob("notes.db.bak-*"))
    assert len(backups) == 1
    assert "bak-v1-" in backups[0].name  # version it started from
    conn.close()


def test_new_database_creates_no_backup(tmp_path):
    db = tmp_path / "notes.db"
    conn = sqlite3.connect(db)
    apply_migrations(conn, db_path=db, now=CLOCK)
    assert list(tmp_path.glob("notes.db.bak-*")) == []
    conn.close()


def test_old_backups_are_pruned(tmp_path):
    db = tmp_path / "notes.db"
    for suffix in ["v1-20260101-000000", "v1-20260102-000000",
                   "v1-20260103-000000"]:
        (tmp_path / f"notes.db.bak-{suffix}").write_bytes(b"velho")

    conn = sqlite3.connect(db)
    apply_migrations(conn, db_path=db, migrations=MIGRATIONS[:1], now=CLOCK)
    conn.close()
    conn = sqlite3.connect(db)
    apply_migrations(conn, db_path=db, now=CLOCK)  # creates the 4th backup

    conn.close()
    backups = sorted(p.name for p in tmp_path.glob("notes.db.bak-*"))
    assert len(backups) == 3  # keeps only the 3 most recent
    assert "notes.db.bak-v1-20260101-000000" not in backups
