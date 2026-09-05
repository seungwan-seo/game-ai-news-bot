from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_STATE = {
    "version": 1,
    "seen": {},
    "last_success_at": "",
    "last_promo_at": "",
    "promotion_cursor": 0,
    "delivery_day_kst": "",
    "delivery_count": 0,
    "delivery_source_counts": {},
}

KST = timezone(timedelta(hours=9), name="KST")


def load_state(path: str | Path) -> dict:
    state_path = Path(path)
    # 호출 간 상태 딕셔너리가 공유되지 않도록 중첩 값도 새로 만든다.
    state = {**DEFAULT_STATE, "seen": {}, "delivery_source_counts": {}}
    if state_path.exists():
        with state_path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            state.update(loaded)
    if not isinstance(state.get("seen"), dict):
        state["seen"] = {}
    state["delivery_source_counts"] = _source_counts(state)
    return state


def mark_seen(state: dict, urls: list[str], now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    timestamp = now.isoformat()
    if not isinstance(state.get("seen"), dict):
        state["seen"] = {}
    for url in urls:
        state["seen"][url] = timestamp
    state["last_success_at"] = timestamp


def _safe_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _source_counts(state: dict) -> dict[str, int]:
    counts = state.get("delivery_source_counts", {})
    if not isinstance(counts, dict):
        return {}
    return {
        source_id: _safe_count(count)
        for source_id, count in counts.items()
        if isinstance(source_id, str) and source_id
    }


def delivered_today(state: dict, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    current_day = now.astimezone(KST).date().isoformat()
    if state.get("delivery_day_kst") != current_day:
        return 0
    return _safe_count(state.get("delivery_count", 0))


def delivered_for_source_today(state: dict, source_id: str, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    current_day = now.astimezone(KST).date().isoformat()
    if state.get("delivery_day_kst") != current_day:
        return 0
    return _source_counts(state).get(source_id, 0)


def mark_delivered(
    state: dict,
    urls: list[str],
    now: datetime | None = None,
    *,
    source_id: str = "",
    aliases: list[str] | None = None,
) -> None:
    now = now or datetime.now(timezone.utc)
    current_day = now.astimezone(KST).date().isoformat()
    current_count = delivered_today(state, now)
    source_counts = _source_counts(state) if state.get("delivery_day_kst") == current_day else {}
    unique_urls = list(dict.fromkeys(urls))
    mark_seen(state, list(dict.fromkeys([*unique_urls, *(aliases or [])])), now)
    state["delivery_day_kst"] = current_day
    state["delivery_count"] = current_count + len(unique_urls)
    if source_id:
        source_counts[source_id] = source_counts.get(source_id, 0) + len(unique_urls)
    state["delivery_source_counts"] = source_counts


def prune_state(state: dict, max_age_days: int = 180, max_items: int = 6000) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    alive: list[tuple[str, str]] = []
    for url, raw_timestamp in state.get("seen", {}).items():
        try:
            timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except (AttributeError, ValueError):
            continue
        if timestamp >= cutoff:
            alive.append((url, timestamp.isoformat()))
    alive.sort(key=lambda pair: pair[1], reverse=True)
    state["seen"] = dict(alive[:max_items])


def save_state(path: str | Path, state: dict) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    prune_state(state)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, state_path)
