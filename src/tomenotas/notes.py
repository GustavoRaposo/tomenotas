"""Armazenamento de notas: arquivos .txt com timestamp (v2 mantém .txt;
SQLite fica para a v3, ver ROADMAP)."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Note:
    path: Path
    text: str

    @property
    def title(self) -> str:
        return self.path.stem  # o timestamp do nome do arquivo

    def matches(self, consulta: str) -> bool:
        """Busca simples: substring sem diferenciar caixa, no texto e no
        nome (permite filtrar por data). Consulta vazia casa com tudo."""
        consulta = consulta.strip().lower()
        return consulta in self.text.lower() or consulta in self.title.lower()


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

    def list(self) -> list[Note]:
        """Todas as notas, mais recente primeiro (os nomes são timestamps,
        então a ordem lexicográfica reversa já é cronológica reversa)."""
        if not self.notes_dir.is_dir():
            return []
        return [
            Note(caminho, caminho.read_text(encoding="utf-8", errors="replace"))
            for caminho in sorted(self.notes_dir.glob("*.txt"), reverse=True)
        ]

    def delete(self, caminho: Path) -> None:
        caminho.unlink(missing_ok=True)
