"""Note: the central domain type."""

from dataclasses import dataclass
from pathlib import Path


def preview(text: str, limit: int = 60) -> str:
    """Short preview used in notifications and in the notes list.

    Always a single line: newlines and repeated whitespace collapse into
    a single space, so list items keep a uniform height.
    """
    return " ".join(text.split())[:limit]


@dataclass(frozen=True)
class DbNote:
    id: int
    created_at: str  # ISO-8601
    text: str
    favorite: bool
    tags: tuple
    filename: str | None
    critical: bool = False  # active critical note (periodic alarm)

    @property
    def title(self) -> str:
        if self.filename:
            return Path(self.filename).stem
        return self.created_at.replace("T", " ")

    def matches(self, query: str) -> bool:
        """Fast in-memory filter (kept compatible with the notes window)."""
        query = query.strip().lower()
        return (query in self.text.lower()
                or query in self.title.lower())

    def __str__(self) -> str:
        return self.title  # readable logs ("note created: <timestamp>")
