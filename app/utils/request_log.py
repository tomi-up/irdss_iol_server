"""
In-memory request/event log buffer powering the Admin Panel's server monitoring
page. Deliberately non-persistent: it is a bounded ring buffer that lives for the
lifetime of the FastAPI process, so it adds zero DB load to the hot request path
and needs no Alembic migration.
"""

import itertools
import threading
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Optional

# Hard cap on retained entries. Oldest entries are evicted automatically.
MAX_LOG_ENTRIES = 1000

# Process start time, used to report uptime on the monitoring dashboard.
SERVER_STARTED_AT = datetime.now(timezone.utc)

_log_buffer: Deque[dict[str, Any]] = deque(maxlen=MAX_LOG_ENTRIES)
_log_lock = threading.Lock()
_id_counter = itertools.count(1)

# Lifetime counters, which survive ring-buffer eviction unlike the entries themselves.
_totals: dict[str, int] = {"requests": 0, "client_errors": 0, "server_errors": 0}


def _level_for_status(status_code: int) -> str:
    """Maps an HTTP status code onto a syslog-style severity level for the log viewer."""
    if status_code >= 500:
        return "ERROR"
    if status_code >= 400:
        return "WARNING"
    return "INFO"


def record_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: Optional[str] = None,
    hospital_name: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Appends a single completed HTTP request to the monitoring ring buffer."""
    entry = {
        "id": next(_id_counter),
        "timestamp": datetime.now(timezone.utc),
        "level": _level_for_status(status_code),
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "client_ip": client_ip,
        "hospital_name": hospital_name,
        "error": error,
    }

    with _log_lock:
        _log_buffer.append(entry)
        _totals["requests"] += 1
        if 400 <= status_code < 500:
            _totals["client_errors"] += 1
        elif status_code >= 500:
            _totals["server_errors"] += 1


def get_request_logs(
    level: Optional[str] = None,
    path_contains: Optional[str] = None,
    hospital_name: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Returns the most recent log entries (newest first), optionally filtered."""
    with _log_lock:
        entries = list(_log_buffer)

    if level:
        wanted = level.strip().upper()
        entries = [e for e in entries if e["level"] == wanted]

    if path_contains:
        needle = path_contains.strip().lower()
        entries = [e for e in entries if needle in e["path"].lower()]

    if hospital_name:
        needle = hospital_name.strip().lower()
        entries = [e for e in entries if (e["hospital_name"] or "").lower().find(needle) >= 0]

    entries.reverse()
    return entries[:max(limit, 1)]


def get_traffic_summary(window_minutes: int = 60) -> dict[str, Any]:
    """Aggregates buffered traffic into headline metrics for the monitoring dashboard."""
    with _log_lock:
        entries = list(_log_buffer)
        totals = dict(_totals)

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    recent = [e for e in entries if e["timestamp"] >= cutoff]

    durations = [e["duration_ms"] for e in recent]
    avg_response_ms = round(sum(durations) / len(durations), 2) if durations else 0.0
    slowest_ms = round(max(durations), 2) if durations else 0.0

    endpoint_counts = Counter(f"{e['method']} {e['path']}" for e in recent)
    status_counts = Counter(str(e["status_code"]) for e in recent)

    return {
        "window_minutes": window_minutes,
        "buffered_entries": len(entries),
        "requests_in_window": len(recent),
        "errors_in_window": len([e for e in recent if e["status_code"] >= 400]),
        "avg_response_ms": avg_response_ms,
        "slowest_response_ms": slowest_ms,
        "lifetime_requests": totals["requests"],
        "lifetime_client_errors": totals["client_errors"],
        "lifetime_server_errors": totals["server_errors"],
        "top_endpoints": [
            {"endpoint": name, "count": count}
            for name, count in endpoint_counts.most_common(8)
        ],
        "status_breakdown": [
            {"status_code": code, "count": count}
            for code, count in sorted(status_counts.items())
        ],
    }


def get_uptime_seconds() -> float:
    """Returns how long the FastAPI process has been running, in seconds."""
    return (datetime.now(timezone.utc) - SERVER_STARTED_AT).total_seconds()


def clear_request_logs() -> int:
    """Empties the ring buffer and returns how many entries were discarded."""
    with _log_lock:
        discarded = len(_log_buffer)
        _log_buffer.clear()
    return discarded
