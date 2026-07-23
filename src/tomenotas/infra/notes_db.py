"""SQLite note storage: FTS5 search, tags, favorites (v3).

The database (~/.local/share/tomenotas/notes.db) is the source of truth.
The .txt mirror is an **opt-in plain-text export** (mirror=False by
default, configurable in Configurações): when enabled, each saved note
writes a .txt into notes_dir. Editing is always done through the UI —
the mirror is one-way. Regardless of the flag, .txt files dropped into
notes_dir are imported on the next startup, and deleting a note removes
its mirror file if one exists (otherwise the import would resurrect it).

Same contract as the old file-based NoteStore (save/list/delete +
Note.matches) plus favorites, tags and search() with combinable filters.
"""

import logging
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from ..domain.note import DbNote
from .migrations import apply_migrations

log = logging.getLogger("tomenotas.notes_db")

_STEM_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


class SqliteNoteStore:
    def __init__(self, db_path, notes_dir: Path, now=datetime.now,
                 mirror: bool = False):
        self.notes_dir = Path(notes_dir)
        self._mirror = bool(mirror)
        self._now = now
        # save() runs on the transcription thread; the rest on the main one
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.isolation_level = None  # autocommit outside migrations
        self._conn.execute("PRAGMA foreign_keys = ON")

        path = Path(db_path) if str(db_path) != ":memory:" else None
        apply_migrations(self._conn, db_path=path)

        imported = self._import_txt()
        if imported:
            log.info("%d .txt note(s) imported into the database", imported)

    def close(self) -> None:
        self._conn.close()

    def __del__(self):  # pragma: no cover - depends on GC timing
        try:
            self._conn.close()
        except Exception:
            pass

    # ---------------- basic contract (core/window) ----------------

    def set_mirror(self, enabled: bool, mirror_dir=None) -> None:
        """Turns the .txt mirror on/off at runtime and optionally moves
        it to another directory (existing files stay where they are)."""
        with self._lock:
            self._mirror = bool(enabled)
            if mirror_dir is not None:
                self.notes_dir = Path(mirror_dir)

    def save(self, text: str, critical: bool = False) -> DbNote:
        with self._lock:
            now = self._now()
            name = None
            if self._mirror:
                self.notes_dir.mkdir(parents=True, exist_ok=True)
                base = now.strftime("%Y-%m-%d_%H-%M-%S")
                name, counter = f"{base}.txt", 2
                while (self.notes_dir / name).exists():
                    name = f"{base}-{counter}.txt"
                    counter += 1
                (self.notes_dir / name).write_text(text, encoding="utf-8")
            cursor = self._conn.execute(
                "INSERT INTO notes (created_at, text, favorite, filename, "
                "critical) VALUES (?, ?, 0, ?, ?)",
                (now.isoformat(timespec="seconds"), text, name,
                 int(bool(critical))),
            )
            return self._note(cursor.lastrowid)

    def list(self) -> list[DbNote]:
        return self.search()

    def delete(self, note: DbNote) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM notes WHERE id = ?", (note.id,))
            # even with the mirror disabled: a leftover file would be
            # re-imported on the next startup, resurrecting the note
            if note.filename:
                (self.notes_dir / note.filename).unlink(missing_ok=True)

    def update_text(self, note_id: int, new_text: str) -> DbNote | None:
        """Edits the note text (database + FTS index via trigger + .txt
        mirror). Returns the updated note, or None if the id does not
        exist."""
        if not new_text.strip():
            raise ValueError("o texto da nota não pode ser vazio")
        with self._lock:
            row = self._conn.execute(
                "SELECT filename FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE notes SET text = ? WHERE id = ?",
                (new_text, note_id),
            )
            if self._mirror and row[0]:
                (self.notes_dir / row[0]).write_text(
                    new_text, encoding="utf-8"
                )
            return self._note(note_id)

    # ---------------- favorites and tags ----------------

    def set_favorite(self, note_id: int, value: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE notes SET favorite = ? WHERE id = ?",
                (int(bool(value)), note_id),
            )

    # ---------------- critical notes (alarm) ----------------

    def set_critical(self, note_id: int, value: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE notes SET critical = ? WHERE id = ?",
                (int(bool(value)), note_id),
            )

    def active_criticals(self) -> list[DbNote]:
        """Active critical notes, most recent first — drives the alarm
        and the read-latest-critical hotkey."""
        with self._lock:
            ids = [row[0] for row in self._conn.execute(
                "SELECT id FROM notes WHERE critical = 1 "
                "ORDER BY created_at DESC, id DESC"
            )]
            return [self._note(note_id) for note_id in ids]

    def add_tag(self, note_id: int, name: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,)
            )
            # name is UNIQUE COLLATE NOCASE: "Compras" and "compras" match
            tag_id = self._conn.execute(
                "SELECT id FROM tags WHERE name = ?", (name,)
            ).fetchone()[0]
            self._conn.execute(
                "INSERT OR IGNORE INTO note_tags (note_id, tag_id) "
                "VALUES (?, ?)",
                (note_id, tag_id),
            )

    def remove_tag(self, note_id: int, name: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM note_tags WHERE note_id = ? AND tag_id = "
                "(SELECT id FROM tags WHERE name = ?)",
                (note_id, name),
            )

    def tags(self) -> list[str]:
        with self._lock:
            return [row[0] for row in self._conn.execute(
                "SELECT name FROM tags ORDER BY name COLLATE NOCASE"
            )]

    def tags_with_counts(self) -> list[tuple[str, int]]:
        """[(name, number of notes)] — for the tag management page."""
        with self._lock:
            return [tuple(row) for row in self._conn.execute(
                "SELECT t.name, COUNT(nt.note_id) FROM tags t "
                "LEFT JOIN note_tags nt ON nt.tag_id = t.id "
                "GROUP BY t.id ORDER BY t.name COLLATE NOCASE"
            )]

    def create_tag(self, name: str) -> bool:
        """Creates a standalone tag (no note). Returns False if it
        already existed."""
        name = name.strip()
        if not name:
            raise ValueError("o nome da tag não pode ser vazio")
        with self._lock:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,)
            )
            return cursor.rowcount > 0

    def delete_tag(self, name: str) -> None:
        """Deletes the tag; notes stay, only the association goes
        (cascade)."""
        with self._lock:
            self._conn.execute("DELETE FROM tags WHERE name = ?", (name,))

    def rename_tag(self, old: str, new: str) -> None:
        """Renames the tag preserving associations. If the new name is
        already another tag, merges (the old tag's notes move to the
        existing one). Case-only change ("compras" → "Compras") is just a
        relabel."""
        new = new.strip()
        if not new:
            raise ValueError("o nome da tag não pode ser vazio")
        with self._lock:
            source = self._conn.execute(
                "SELECT id FROM tags WHERE name = ?", (old,)
            ).fetchone()
            if source is None:
                return
            target = self._conn.execute(
                "SELECT id FROM tags WHERE name = ?", (new,)
            ).fetchone()
            if target is None or target[0] == source[0]:
                self._conn.execute(
                    "UPDATE tags SET name = ? WHERE id = ?",
                    (new, source[0]),
                )
            else:  # merge into the existing tag
                self._conn.execute(
                    "INSERT OR IGNORE INTO note_tags (note_id, tag_id) "
                    "SELECT note_id, ? FROM note_tags WHERE tag_id = ?",
                    (target[0], source[0]),
                )
                self._conn.execute(
                    "DELETE FROM tags WHERE id = ?", (source[0],)
                )

    # ---------------- search (combinable filters) ----------------

    def search(self, text: str = "", tags=(), favorites: bool = False,
               since: str | None = None) -> list[DbNote]:
        with self._lock:
            sql = "SELECT n.id FROM notes n"
            conditions, params = [], []

            fts_query = self._fts_query(text)
            if fts_query:
                sql += " JOIN notes_fts ON notes_fts.rowid = n.id"
                conditions.append("notes_fts MATCH ?")
                params.append(fts_query)
            if tags:
                placeholders = ", ".join("?" * len(tags))
                conditions.append(
                    "n.id IN (SELECT nt.note_id FROM note_tags nt "
                    "JOIN tags t ON t.id = nt.tag_id "
                    f"WHERE t.name IN ({placeholders}) "
                    "GROUP BY nt.note_id HAVING COUNT(DISTINCT t.id) = ?)"
                )
                params.extend(tags)
                params.append(len(tags))
            if favorites:
                conditions.append("n.favorite = 1")
            if since:
                conditions.append("n.created_at >= ?")
                params.append(since)

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            # with text: relevance ranking; without: most recent first
            sql += (" ORDER BY bm25(notes_fts)" if fts_query
                    else " ORDER BY n.created_at DESC, n.id DESC")

            ids = [row[0] for row in self._conn.execute(sql, params)]
            return [self._note(note_id) for note_id in ids]

    @staticmethod
    def _fts_query(text: str) -> str | None:
        """Sanitizes the user's search into FTS5 syntax: each word
        becomes a prefix term ("word"*), combined with AND."""
        tokens = re.findall(r"\w+", text)
        if not tokens:
            return None
        return " ".join(f'"{token}"*' for token in tokens)

    # ---------------- internals ----------------

    def _note(self, note_id: int) -> DbNote:
        row = self._conn.execute(
            "SELECT id, created_at, text, favorite, filename, critical "
            "FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
        tags = tuple(t[0] for t in self._conn.execute(
            "SELECT t.name FROM tags t "
            "JOIN note_tags nt ON nt.tag_id = t.id "
            "WHERE nt.note_id = ? ORDER BY t.name COLLATE NOCASE",
            (note_id,),
        ))
        return DbNote(
            id=row[0], created_at=row[1], text=row[2],
            favorite=bool(row[3]), tags=tags, filename=row[4],
            critical=bool(row[5]),
        )

    def _import_txt(self) -> int:
        """Imports .txt files from notes/ that are not yet in the
        database (notes from the pre-SQLite era and ones created by the
        legacy gravar.sh)."""
        if not self.notes_dir.is_dir():
            return 0
        known = {row[0] for row in self._conn.execute(
            "SELECT filename FROM notes WHERE filename IS NOT NULL"
        )}
        total = 0
        for txt in sorted(self.notes_dir.glob("*.txt")):
            if txt.name in known:
                continue
            self._conn.execute(
                "INSERT INTO notes (created_at, text, favorite, filename) "
                "VALUES (?, ?, 0, ?)",
                (
                    self._created_at_for(txt),
                    txt.read_text(encoding="utf-8", errors="replace"),
                    txt.name,
                ),
            )
            total += 1
        return total

    @staticmethod
    def _created_at_for(txt: Path) -> str:
        match = _STEM_TS.match(txt.stem)
        if match:
            return datetime.strptime(
                match.group(1), "%Y-%m-%d_%H-%M-%S"
            ).isoformat(timespec="seconds")
        # non-standard name (hand-made file): fall back to the mtime
        return datetime.fromtimestamp(
            txt.stat().st_mtime
        ).isoformat(timespec="seconds")
