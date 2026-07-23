"""Armazenamento de notas: arquivos .txt com timestamp (v2 mantém .txt;
SQLite fica para a v3, ver ROADMAP)."""

from datetime import datetime
from pathlib import Path


class NoteStore:
    def __init__(self, notes_dir: Path, now=datetime.now):
        self.notes_dir = notes_dir
        self._now = now

    def save(self, texto: str) -> Path:
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        ts = self._now().strftime("%Y-%m-%d_%H-%M-%S")
        caminho = self.notes_dir / f"{ts}.txt"
        # duas notas no mesmo segundo não podem se sobrescrever
        contador = 2
        while caminho.exists():
            caminho = self.notes_dir / f"{ts}-{contador}.txt"
            contador += 1
        caminho.write_text(texto, encoding="utf-8")
        return caminho

    @staticmethod
    def preview(texto: str, limite: int = 60) -> str:
        return texto[:limite]
