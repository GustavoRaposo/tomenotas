"""Tests for tomenotas.infra.logs — structured file logging."""

import logging

from tomenotas.infra.logs import setup_logging


def test_writes_formatted_line_to_file(tmp_path):
    log_file = tmp_path / "sub" / "daemon.log"
    setup_logging(log_file)
    logging.getLogger("tomenotas.core").info("note saved: %s", "x.txt")

    content = log_file.read_text(encoding="utf-8")
    assert "INFO tomenotas.core: note saved: x.txt" in content


def test_repeated_setup_does_not_duplicate_lines(tmp_path):
    log_file = tmp_path / "daemon.log"
    setup_logging(log_file)
    setup_logging(log_file)  # idempotent: a single handler
    logging.getLogger("tomenotas.player").warning("only once")

    lines = [l for l in log_file.read_text(encoding="utf-8").splitlines()
             if "only once" in l]
    assert len(lines) == 1
