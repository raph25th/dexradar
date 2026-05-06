from datetime import datetime, timezone
from typing import Any

_last_collection_at: str | None = None
_last_collection_summary: dict[str, Any] | None = None


def set_last_collection_summary(summary: dict[str, Any]) -> None:
    global _last_collection_at, _last_collection_summary
    _last_collection_at = datetime.now(timezone.utc).isoformat()
    _last_collection_summary = dict(summary)


def get_runtime_state() -> dict[str, Any]:
    return {
        "last_collection_at": _last_collection_at,
        "last_collection_summary": (
            dict(_last_collection_summary) if _last_collection_summary is not None else None
        ),
    }
