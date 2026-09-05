"""Anonymous channel reactions, bounded observation windows and conservative ranking.

Only article posts registered after a successful send are tracked. Telegram users,
individual reaction events and messages from unknown chats are never retained.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from .models import Article


DEFAULT_WINDOW_HOURS = 48


def _integer(value: object, minimum: int = 0) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= minimum:
        return value
    return None


def _number(value: object, default: float, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return min(maximum, max(minimum, result)) if math.isfinite(result) else default


def _datetime(value: object) -> datetime | None:
    try:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, str):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif _integer(value) is not None:
            result = datetime.fromtimestamp(value, timezone.utc)
        else:
            return None
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _now(value: datetime | None) -> datetime:
    return _datetime(value) or datetime.now(timezone.utc)


def _settings(config: dict) -> dict:
    candidate = config.get("feedback", config) if isinstance(config, dict) else {}
    return candidate if isinstance(candidate, dict) else {}


def _feedback(state: dict) -> dict:
    if not isinstance(state.get("feedback"), dict):
        state["feedback"] = {}
    feedback = state["feedback"]
    if not isinstance(feedback.get("posts"), dict):
        feedback["posts"] = {}
    if _integer(feedback.get("next_update_id")) is None:
        feedback["next_update_id"] = 0
    return feedback


def _post_key(chat_id: object, message_id: object) -> str | None:
    if not isinstance(chat_id, int) or isinstance(chat_id, bool) or chat_id >= 0:
        return None
    if _integer(message_id, 1) is None:
        return None
    return f"{chat_id}:{message_id}"


def register_deliveries(
    state: dict, article: Article, receipts: list[dict], now: datetime | None = None,
) -> None:
    """Register channel receipts once; re-registration cannot reset collected votes.

    ``state['feedback']['window_hours']`` may configure the window for *new* posts.
    A post's window is fixed on registration so later configuration changes do not
    mix unequal exposure periods in its observation history.
    """
    feedback = _feedback(state)
    current = _now(now)
    window = _number(feedback.get("window_hours"), DEFAULT_WINDOW_HOURS, 1, 168)
    for receipt in receipts:
        if not isinstance(receipt, dict) or receipt.get("chat_type") != "channel":
            continue
        key = _post_key(receipt.get("chat_id"), receipt.get("message_id"))
        if not key or key in feedback["posts"]:
            continue
        sent_at = _datetime(receipt.get("date")) or current
        feedback["posts"][key] = {
            "chat_id": receipt["chat_id"],
            "message_id": receipt["message_id"],
            "url": article.url,
            "title": article.title,
            "source_id": article.source_id,
            "category": article.category,
            "published_at": article.published_at.isoformat() if article.published_at else "",
            "sent_at": sent_at.isoformat(),
            "window_hours": window,
            "up": 0,
            "down": 0,
            "reaction_date": 0,
            "reaction_update_id": -1,
            "learning_up": 0,
            "learning_down": 0,
            "learning_date": 0,
            "learning_update_id": -1,
        }


def _reaction_counts(reactions: object) -> tuple[int, int] | None:
    if not isinstance(reactions, list):
        return None
    counts = {"👍": 0, "👎": 0}
    for reaction in reactions:
        if not isinstance(reaction, dict) or not isinstance(reaction.get("type"), dict):
            return None
        kind = reaction["type"]
        emoji = kind.get("emoji") if kind.get("type") == "emoji" else None
        if not isinstance(emoji, str) or emoji not in counts:
            continue
        count = _integer(reaction.get("total_count"))
        if count is None:
            return None
        counts[emoji] += count
    return counts["👍"], counts["👎"]


def _snapshot_order(post: dict, prefix: str) -> tuple[int, int]:
    date = _integer(post.get(f"{prefix}_date"))
    update_id = _integer(post.get(f"{prefix}_update_id"))
    return (date if date is not None else 0, update_id if update_id is not None else -1)


def apply_reaction_updates(state: dict, updates: list[dict]) -> int:
    """Apply latest aggregate snapshots, never deltas, and return changed post count.

    Every syntactically valid nonnegative integer update_id advances the cursor,
    even for unsupported/malformed/unknown-chat updates; their payload is discarded.
    Missing/invalid IDs cannot safely be acknowledged and are ignored entirely.
    Live and within-window snapshots are ordered independently by (date, update_id),
    so cancellation, retries, and reverse delivery order cannot double-count votes.
    """
    feedback = _feedback(state)
    changed: set[str] = set()
    for update in updates:
        if not isinstance(update, dict):
            continue
        update_id = _integer(update.get("update_id"))
        if update_id is None:
            continue
        feedback["next_update_id"] = max(feedback["next_update_id"], update_id + 1)
        reaction = update.get("message_reaction_count")
        if not isinstance(reaction, dict) or not isinstance(reaction.get("chat"), dict):
            continue
        chat = reaction["chat"]
        if chat.get("type") != "channel":
            continue
        key = _post_key(chat.get("id"), reaction.get("message_id"))
        post = feedback["posts"].get(key)
        if not isinstance(post, dict):
            continue
        date = _integer(reaction.get("date"), 1)
        counts = _reaction_counts(reaction.get("reactions"))
        sent_at = _datetime(post.get("sent_at"))
        event_at = _datetime(date)
        if counts is None or sent_at is None or event_at is None or event_at < sent_at:
            continue
        order = (date, update_id)
        live_order = _snapshot_order(post, "reaction")
        if order > live_order:
            post.update(up=counts[0], down=counts[1], reaction_date=date, reaction_update_id=update_id)
            changed.add(key)
        window = _number(post.get("window_hours"), DEFAULT_WINDOW_HOURS, 1, 168)
        if event_at <= sent_at + timedelta(hours=window):
            learning_order = _snapshot_order(post, "learning")
            if order > learning_order:
                post.update(
                    learning_up=counts[0], learning_down=counts[1],
                    learning_date=date, learning_update_id=update_id,
                )
                changed.add(key)
    return len(changed)


def _empty_group() -> dict:
    return {
        "posts": 0, "up": 0, "down": 0, "reacted_posts": 0,
        "mature_posts": 0, "learning_up": 0, "learning_down": 0,
        "learning_reacted_posts": 0,
    }


def build_feedback_report(state: dict, config: dict, now: datetime | None = None) -> dict:
    """Report recent current totals separately from completed-window learning data.

    No reaction is never treated as dislike. A group's neutral-prior estimate is
    visible during observation, but it is eligible for ranking only after all gates.
    This function does not mutate state.
    """
    settings = _settings(config)
    current = _now(now)
    days = _number(settings.get("lookback_days"), 30, 1, 180)
    cutoff = current - timedelta(days=days)
    gates = {
        "min_posts": int(_number(settings.get("min_posts"), 5, 5, 6000)),
        "min_reacted_posts": int(_number(settings.get("min_reacted_posts"), 3, 3, 6000)),
        "min_reactions": int(_number(settings.get("min_reactions"), 20, 20, 1000000)),
        "prior_reactions": _number(settings.get("prior_reactions"), 10, 10, 1000000),
    }
    feedback = state.get("feedback", {})
    feedback = feedback if isinstance(feedback, dict) else {}
    posts = feedback.get("posts", {})
    posts = posts if isinstance(posts, dict) else {}
    report = {
        "generated_at": current.isoformat(),
        "lookback_days": days,
        "apply_to_ranking": settings.get("apply_to_ranking") is True,
        "collection": {
            "last_poll_at": feedback.get("last_poll_at", ""),
            "last_gap_warning_at": feedback.get("last_gap_warning_at", ""),
            "last_batch_size": feedback.get("last_batch_size", 0),
        },
        "gates": gates,
        "total": _empty_group(),
        "by_source": {},
        "by_category": {},
    }
    for post in posts.values():
        if not isinstance(post, dict):
            continue
        sent_at = _datetime(post.get("sent_at"))
        if sent_at is None or not cutoff <= sent_at <= current:
            continue
        window = _number(post.get("window_hours"), DEFAULT_WINDOW_HOURS, 1, 168)
        complete = current >= sent_at + timedelta(hours=window)
        up = _integer(post.get("up")) or 0
        down = _integer(post.get("down")) or 0
        learning_up = (_integer(post.get("learning_up")) or 0) if complete else 0
        learning_down = (_integer(post.get("learning_down")) or 0) if complete else 0
        groups = [report["total"]]
        for field, bucket in (("source_id", "by_source"), ("category", "by_category")):
            name = post.get(field)
            if isinstance(name, str) and name:
                groups.append(report[bucket].setdefault(name, _empty_group()))
        for group in groups:
            group["posts"] += 1
            group["up"] += up
            group["down"] += down
            group["reacted_posts"] += int(up + down > 0)
            group["mature_posts"] += int(complete)
            group["learning_up"] += learning_up
            group["learning_down"] += learning_down
            group["learning_reacted_posts"] += int(learning_up + learning_down > 0)
    for group in [report["total"], *report["by_source"].values(), *report["by_category"].values()]:
        reactions = group["learning_up"] + group["learning_down"]
        group["learning_reactions"] = reactions
        group["bias"] = (group["learning_up"] - group["learning_down"]) / (reactions + gates["prior_reactions"])
        group["mature"] = (
            group["mature_posts"] >= gates["min_posts"]
            and group["learning_reacted_posts"] >= gates["min_reacted_posts"]
            and reactions >= gates["min_reactions"]
        )
    return report


def preference_adjustment(article: Article, report: dict, config: dict) -> float:
    """Observe-only by default; mature category/source mean can adjust at most ±3."""
    settings = _settings(config)
    if settings.get("apply_to_ranking") is not True or settings.get("enabled", True) is False:
        return 0.0
    biases = []
    for bucket, key in (("by_source", article.source_id), ("by_category", article.category)):
        groups = report.get(bucket, {})
        group = groups.get(key, {}) if isinstance(groups, dict) else {}
        if isinstance(group, dict) and group.get("mature") is True:
            biases.append(_number(group.get("bias"), 0, -1, 1))
    if not biases:
        return 0.0
    cap = _number(settings.get("max_adjustment"), 3, 0, 3)
    return round(cap * sum(biases) / len(biases), 6)


def prune_feedback(state: dict, now: datetime | None = None) -> None:
    """Keep at most 6,000 tracked channel posts from the latest 180 days."""
    feedback = _feedback(state)
    current = _now(now)
    cutoff = current - timedelta(days=180)
    alive = []
    for key, post in feedback["posts"].items():
        if not isinstance(post, dict) or key != _post_key(post.get("chat_id"), post.get("message_id")):
            continue
        sent_at = _datetime(post.get("sent_at"))
        if sent_at is not None and cutoff <= sent_at <= current:
            alive.append((key, post, sent_at))
    alive.sort(key=lambda entry: entry[2], reverse=True)
    feedback["posts"] = {key: post for key, post, _ in alive[:6000]}
