from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone


def eligible_promotions(config: dict) -> list[dict]:
    if not config.get("enabled", False):
        return []
    promotions = []
    for entry in config.get("channels", []):
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url", "")).strip()
        name = str(entry.get("name", "")).strip()
        if name and url.startswith("https://t.me/"):
            promotions.append(entry)
    return promotions


def _parse_timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def promotion_is_due(state: dict, config: dict, now: datetime | None = None) -> bool:
    if not eligible_promotions(config):
        return False
    now = now or datetime.now(timezone.utc)
    last_sent = _parse_timestamp(state.get("last_promo_at", ""))
    if last_sent is None:
        return True
    interval_days = max(1, int(config.get("interval_days", 5)))
    return now - last_sent >= timedelta(days=interval_days)


def select_promotion(state: dict, config: dict) -> dict | None:
    promotions = eligible_promotions(config)
    if not promotions:
        return None
    cursor = int(state.get("promotion_cursor", 0)) % len(promotions)
    return promotions[cursor]


def build_promotion_post(entry: dict) -> str:
    name = html.escape(str(entry["name"]).strip(), quote=False)
    description = html.escape(str(entry.get("description", "")).strip(), quote=False)
    url = html.escape(str(entry["url"]).strip(), quote=True)
    description_block = f"\n{description}\n" if description else "\n"
    return (
        "<b>🤝 자매 채널 추천</b>\n\n"
        f"<b>{name}</b>\n"
        f"{description_block}\n"
        f'<a href="{url}">👉 채널 바로가기</a>'
    )


def mark_promotion_sent(
    state: dict, config: dict, now: datetime | None = None
) -> None:
    promotions = eligible_promotions(config)
    if not promotions:
        return
    now = now or datetime.now(timezone.utc)
    cursor = int(state.get("promotion_cursor", 0))
    state["last_promo_at"] = now.astimezone(timezone.utc).isoformat()
    state["promotion_cursor"] = (cursor + 1) % len(promotions)
