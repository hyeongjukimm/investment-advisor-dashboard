from __future__ import annotations


def is_shared_mode(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def allow_admin_controls(*, shared: bool, raw_exists: bool) -> bool:
    return bool(raw_exists) and not bool(shared)
