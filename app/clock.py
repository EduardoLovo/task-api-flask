from datetime import UTC, datetime


def now_iso() -> str:
    """Data/hora atual em UTC no mesmo formato do JavaScript: 2026-10-06T15:09:11.999Z."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
