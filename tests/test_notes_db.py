"""Tests for tomenotas.infra.notes_db — SQLite storage (FTS5, tags,
favorites)."""

from datetime import datetime
from pathlib import Path

from tomenotas.infra.notes_db import SqliteNoteStore

CLOCK = lambda: datetime(2026, 7, 23, 15, 0, 38)  # noqa: E731


def make(tmp_path, now=CLOCK, mirror=True):
    # most tests below exercise the mirror behavior, so the helper turns
    # it on; the class default is mirror=False (see the mirror section)
    return SqliteNoteStore(tmp_path / "notes.db", tmp_path / "notes",
                           now=now, mirror=mirror)


# ---------------- save / list / delete ----------------

def test_save_writes_database_and_txt_mirror(tmp_path):
    store = make(tmp_path)
    note = store.save("minha nota")
    assert note.text == "minha nota"
    assert note.created_at == "2026-07-23T15:00:38"
    assert note.title == "2026-07-23_15-00-38"
    assert not note.favorite
    assert note.tags == ()
    mirror = tmp_path / "notes" / "2026-07-23_15-00-38.txt"
    assert mirror.read_text(encoding="utf-8") == "minha nota"


def test_save_in_the_same_second_does_not_overwrite(tmp_path):
    store = make(tmp_path)
    store.save("primeira")
    second = store.save("segunda")
    assert second.title == "2026-07-23_15-00-38-2"
    assert (tmp_path / "notes" / "2026-07-23_15-00-38-2.txt").exists()


def test_list_orders_most_recent_first(tmp_path):
    moments = iter([
        datetime(2026, 7, 21, 10, 0, 0),
        datetime(2026, 7, 23, 9, 0, 0),
        datetime(2026, 7, 22, 12, 0, 0),
    ])
    store = make(tmp_path, now=lambda: next(moments))
    store.save("antiga")
    store.save("recente")
    store.save("do meio")
    assert [n.text for n in store.list()] == ["recente", "do meio", "antiga"]


def test_delete_removes_database_row_and_mirror(tmp_path):
    store = make(tmp_path)
    note = store.save("descartável")
    store.delete(note)
    assert store.list() == []
    assert not (tmp_path / "notes" / f"{note.title}.txt").exists()


def test_close_closes_the_connection(tmp_path):
    import sqlite3

    import pytest

    store = make(tmp_path)
    store.save("x")
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        store.list()


def test_title_without_filename_uses_created_at_and_str_is_the_title(tmp_path):
    store = make(tmp_path)
    note = store.save("x")
    no_file = type(note)(id=1, created_at="2026-07-23T10:00:00",
                         text="x", favorite=False, tags=(),
                         filename=None)
    assert no_file.title == "2026-07-23 10:00:00"
    assert str(note) == note.title


def test_matches_compatibility_with_the_window_filter(tmp_path):
    store = make(tmp_path)
    store.save("Comprar PÃO na padaria")
    (note,) = store.list()
    assert note.matches("pão")
    assert note.matches("2026-07-23")  # also searches the title
    assert note.matches("")
    assert not note.matches("leite")


# ---------------- mirror on/off (default: off) ----------------

def test_mirror_disabled_by_default_saves_only_to_the_db(tmp_path):
    store = SqliteNoteStore(tmp_path / "notes.db", tmp_path / "notes",
                            now=CLOCK)
    note = store.save("só no banco")
    assert note.text == "só no banco"
    assert note.filename is None  # no file backs this note
    assert note.title == "2026-07-23 15:00:38"  # falls back to created_at
    assert not (tmp_path / "notes").exists()  # nothing written


def test_import_still_works_with_mirror_disabled(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "2026-07-20_08-30-00.txt").write_text("de fora",
                                                       encoding="utf-8")
    store = make(tmp_path, mirror=False)
    (note,) = store.list()
    assert note.text == "de fora"


def test_delete_removes_stale_mirror_even_when_disabled(tmp_path):
    # note saved while the mirror was on; later the mirror is disabled.
    # Deleting must still remove the file — otherwise the next startup
    # would re-import it and the note would resurrect.
    store = make(tmp_path, mirror=True)
    note = store.save("apagável")
    store.close()

    store2 = make(tmp_path, mirror=False)
    (note,) = store2.list()
    store2.delete(note)
    assert not (tmp_path / "notes" / f"{note.title}.txt").exists()
    store2.close()
    assert make(tmp_path, mirror=False).list() == []  # no resurrection


def test_update_with_mirror_disabled_keeps_db_and_skips_file(tmp_path):
    store = make(tmp_path, mirror=True)
    note = store.save("original")
    store.set_mirror(False)
    store.update_text(note.id, "editado")
    assert store.list()[0].text == "editado"
    mirror = tmp_path / "notes" / f"{note.title}.txt"
    assert mirror.read_text(encoding="utf-8") == "original"  # stale, kept


def test_set_mirror_enables_and_redirects_the_directory(tmp_path):
    store = make(tmp_path, mirror=False)
    store.save("antes")  # not mirrored
    other = tmp_path / "espelho"

    store.set_mirror(True, other)
    note = store.save("depois")

    assert (other / f"{note.title}.txt").read_text(
        encoding="utf-8") == "depois"
    assert not (tmp_path / "notes").exists()  # old dir untouched


# ---------------- .txt import ----------------

def test_imports_preexisting_txt_on_first_open(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "2026-07-20_08-30-00.txt").write_text("do bash", encoding="utf-8")

    store = make(tmp_path)
    (note,) = store.list()
    assert note.text == "do bash"
    assert note.created_at == "2026-07-20T08:30:00"


def test_reopening_does_not_duplicate_the_import(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "2026-07-20_08-30-00.txt").write_text("única", encoding="utf-8")
    make(tmp_path)
    store = make(tmp_path)  # second open (e.g. daemon restart)
    assert len(store.list()) == 1


def test_txt_created_later_is_imported_on_next_open(tmp_path):
    store = make(tmp_path)
    store.save("pela UI")
    # the legacy gravar.sh creates a txt outside the daemon
    (tmp_path / "notes" / "2026-07-23_20-00-00.txt").write_text(
        "pelo script legado", encoding="utf-8"
    )
    store2 = make(tmp_path)
    assert {n.text for n in store2.list()} == {"pela UI", "pelo script legado"}


def test_txt_with_nonstandard_name_uses_mtime(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "avulso.txt").write_text("sem timestamp", encoding="utf-8")
    store = make(tmp_path)
    (note,) = store.list()
    assert note.text == "sem timestamp"
    assert note.created_at  # derived from the mtime, but present


# ---------------- text editing ----------------

def test_update_text_changes_database_and_mirror(tmp_path):
    store = make(tmp_path)
    note = store.save("texto original")
    updated = store.update_text(note.id, "texto corrigido")
    assert updated.text == "texto corrigido"
    assert store.list()[0].text == "texto corrigido"
    mirror = tmp_path / "notes" / f"{note.title}.txt"
    assert mirror.read_text(encoding="utf-8") == "texto corrigido"


def test_update_text_reindexes_the_search(tmp_path):
    store = make(tmp_path)
    note = store.save("palavra antiga")
    store.update_text(note.id, "palavra novidade")
    assert store.search(text="novidade") != []
    assert store.search(text="antiga") == []


def test_update_text_empty_raises(tmp_path):
    import pytest

    store = make(tmp_path)
    note = store.save("conteúdo")
    with pytest.raises(ValueError):
        store.update_text(note.id, "   \n")
    assert store.list()[0].text == "conteúdo"  # nothing changed


def test_update_text_of_missing_note_is_ignored(tmp_path):
    store = make(tmp_path)
    assert store.update_text(999, "novo") is None


# ---------------- critical notes (alarm) ----------------

def test_save_critical_marks_the_note(tmp_path):
    store = make(tmp_path, mirror=False)
    normal = store.save("nota comum")
    critical = store.save("urgente", critical=True)
    assert normal.critical is False
    assert critical.critical is True


def test_set_critical_toggles(tmp_path):
    store = make(tmp_path, mirror=False)
    note = store.save("vira crítica")
    store.set_critical(note.id, True)
    assert store.list()[0].critical
    store.set_critical(note.id, False)
    assert not store.list()[0].critical


def test_active_criticals_lists_only_active_most_recent_first(tmp_path):
    moments = iter([
        datetime(2026, 7, 20, 10, 0, 0),
        datetime(2026, 7, 21, 10, 0, 0),
        datetime(2026, 7, 22, 10, 0, 0),
    ])
    store = make(tmp_path, mirror=False, now=lambda: next(moments))
    store.save("normal")
    old = store.save("crítica antiga", critical=True)
    new = store.save("crítica nova", critical=True)

    assert [n.id for n in store.active_criticals()] == [new.id, old.id]

    store.set_critical(new.id, False)  # deactivated: leaves the alarm
    assert [n.id for n in store.active_criticals()] == [old.id]

    store.delete(store.list()[1])  # delete the remaining critical
    assert store.active_criticals() == []


# ---------------- favorites ----------------

def test_favorite_and_unfavorite(tmp_path):
    store = make(tmp_path)
    note = store.save("importante")
    store.set_favorite(note.id, True)
    assert store.list()[0].favorite
    store.set_favorite(note.id, False)
    assert not store.list()[0].favorite


# ---------------- tags ----------------

def test_add_and_remove_tag(tmp_path):
    store = make(tmp_path)
    note = store.save("mercado")
    store.add_tag(note.id, "compras")
    store.add_tag(note.id, "casa")
    assert store.list()[0].tags == ("casa", "compras")  # alphabetical
    store.remove_tag(note.id, "casa")
    assert store.list()[0].tags == ("compras",)
    assert store.tags() == ["casa", "compras"]  # the tag itself remains


def test_tags_are_case_insensitive(tmp_path):
    store = make(tmp_path)
    note = store.save("x")
    store.add_tag(note.id, "Compras")
    store.add_tag(note.id, "compras")  # same tag
    assert store.list()[0].tags == ("Compras",)
    assert store.tags() == ["Compras"]


def test_create_tag_creates_standalone_without_note(tmp_path):
    store = make(tmp_path)
    assert store.create_tag("projetos") is True
    assert store.create_tag("PROJETOS") is False  # already exists (nocase)
    assert store.tags() == ["projetos"]
    assert store.tags_with_counts() == [("projetos", 0)]


def test_create_empty_tag_raises(tmp_path):
    import pytest

    store = make(tmp_path)
    with pytest.raises(ValueError):
        store.create_tag("   ")


def test_delete_tag_removes_associations_but_not_the_notes(tmp_path):
    store = make(tmp_path)
    note = store.save("nota que fica")
    store.add_tag(note.id, "temporaria")
    store.delete_tag("temporaria")
    assert store.tags() == []
    (remaining,) = store.list()
    assert remaining.text == "nota que fica"
    assert remaining.tags == ()


def test_simple_rename_tag_preserves_associations(tmp_path):
    store = make(tmp_path)
    note = store.save("x")
    store.add_tag(note.id, "mercado")
    store.rename_tag("mercado", "compras")
    assert store.tags() == ["compras"]
    assert store.list()[0].tags == ("compras",)


def test_rename_tag_to_existing_name_merges(tmp_path):
    store = make(tmp_path)
    a = store.save("a")
    b = store.save("b")
    store.add_tag(a.id, "mercado")
    store.add_tag(b.id, "compras")
    store.add_tag(b.id, "mercado")  # b has both
    store.rename_tag("mercado", "compras")
    assert store.tags() == ["compras"]
    assert {n.text: n.tags for n in store.list()} == {
        "a": ("compras",), "b": ("compras",),
    }


def test_case_only_rename_updates_the_label(tmp_path):
    store = make(tmp_path)
    note = store.save("x")
    store.add_tag(note.id, "compras")
    store.rename_tag("compras", "Compras")
    assert store.tags() == ["Compras"]
    assert store.list()[0].tags == ("Compras",)


def test_rename_missing_tag_is_ignored(tmp_path):
    store = make(tmp_path)
    store.rename_tag("fantasma", "novo")  # must not raise
    assert store.tags() == []


def test_rename_tag_to_empty_raises(tmp_path):
    import pytest

    store = make(tmp_path)
    note = store.save("x")
    store.add_tag(note.id, "compras")
    with pytest.raises(ValueError):
        store.rename_tag("compras", "  ")


def test_tags_with_counts(tmp_path):
    store = make(tmp_path)
    a = store.save("a")
    b = store.save("b")
    store.add_tag(a.id, "compras")
    store.add_tag(b.id, "compras")
    store.add_tag(a.id, "casa")
    store.create_tag("vazia")
    assert store.tags_with_counts() == [
        ("casa", 1), ("compras", 2), ("vazia", 0),
    ]


def test_deleting_note_cleans_tag_associations(tmp_path):
    store = make(tmp_path)
    note = store.save("x")
    store.add_tag(note.id, "solta")
    store.delete(note)
    assert store.tags() == ["solta"]  # tag survives, association does not
    another = store.save("y")
    assert another.tags == ()


# ---------------- search (FTS5 + combinable filters) ----------------

def populate(store):
    moments = iter([
        datetime(2026, 7, 20, 10, 0, 0),
        datetime(2026, 7, 22, 10, 0, 0),
        datetime(2026, 7, 23, 10, 0, 0),
    ])
    store._now = lambda: next(moments)
    a = store.save("comprar pão e leite no mercado")
    b = store.save("reunião sobre o projeto do mercado municipal")
    c = store.save("ideia de presente de aniversário")
    return a, b, c


def test_text_search_with_prefix(tmp_path):
    store = make(tmp_path)
    populate(store)
    texts = [n.text for n in store.search(text="merc")]
    assert len(texts) == 2
    assert all("mercado" in t for t in texts)


def test_text_search_without_results(tmp_path):
    store = make(tmp_path)
    populate(store)
    assert store.search(text="inexistente") == []


def test_search_with_special_characters_does_not_blow_up(tmp_path):
    store = make(tmp_path)
    populate(store)
    assert store.search(text='pão " * () -') != []  # sanitized


def test_multi_word_search_requires_all(tmp_path):
    store = make(tmp_path)
    populate(store)
    (note,) = store.search(text="mercado municipal")
    assert "municipal" in note.text


def test_search_by_tag_is_intersection(tmp_path):
    store = make(tmp_path)
    a, b, _ = populate(store)
    store.add_tag(a.id, "compras")
    store.add_tag(b.id, "trabalho")
    store.add_tag(b.id, "compras")
    assert {n.id for n in store.search(tags=["compras"])} == {a.id, b.id}
    assert [n.id for n in store.search(tags=["compras", "trabalho"])] == [b.id]


def test_search_favorites_only(tmp_path):
    store = make(tmp_path)
    a, _, _ = populate(store)
    store.set_favorite(a.id, True)
    assert [n.id for n in store.search(favorites=True)] == [a.id]


def test_search_by_period(tmp_path):
    store = make(tmp_path)
    populate(store)
    recent = store.search(since="2026-07-22T00:00:00")
    assert len(recent) == 2


def test_combined_filters(tmp_path):
    store = make(tmp_path)
    a, b, _ = populate(store)
    store.add_tag(a.id, "compras")
    store.add_tag(b.id, "compras")
    store.set_favorite(b.id, True)
    result = store.search(text="mercado", tags=["compras"],
                          favorites=True)
    assert [n.id for n in result] == [b.id]
