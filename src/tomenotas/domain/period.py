"""Translates the UI period shortcuts into date lower bounds."""

from datetime import datetime, timedelta


def period_since(period: str, now: datetime | None = None) -> str | None:
    """"today" | "7days" | "30days" → ISO lower bound used in
    search(since=...); any other value → None (no date filter)."""
    now = now or datetime.now()
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7days":
        start = now - timedelta(days=7)
    elif period == "30days":
        start = now - timedelta(days=30)
    else:
        return None
    return start.isoformat(timespec="seconds")
