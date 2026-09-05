"""Collect anonymous reaction snapshots without sending channel messages.

Only one getUpdates page is read per execution. Its next offset is committed
with our state before the *next* run acknowledges it to Telegram. Paging ahead
before GitHub persisted the state could lose reactions on a failed state push.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

from .feedback import apply_reaction_updates, prune_feedback

logger = logging.getLogger(__name__)


class FeedbackCollectionError(RuntimeError):
    """A safe error that never includes a token, request URL, or response body."""


def _api_call(token: str, method: str, payload: dict, timeout: int) -> object:
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload, timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
    except requests.RequestException:
        raise FeedbackCollectionError(f"반응 수집 {method} 요청 실패 (토큰/응답은 로그에서 제외)") from None
    except ValueError:
        raise FeedbackCollectionError(f"반응 수집 {method} JSON 응답 오류") from None
    if not isinstance(body, dict) or body.get("ok") is not True or "result" not in body:
        raise FeedbackCollectionError(f"반응 수집 {method} API 응답 오류")
    return body["result"]


def collect_feedback(state: dict, token: str, config: dict, now: datetime | None = None) -> dict:
    """Update in-memory aggregates; caller must durably save state after success.

Never delete a webhook, discard queued updates, or request identifiable users'
reaction events. Unknown/old message updates are ignored by the reducer.
"""
    if not token:
        raise FeedbackCollectionError("반응 수집에는 TELEGRAM_TOKEN이 필요합니다.")
    now = now or datetime.now(timezone.utc)
    timeout = max(1, min(30, int(config.get("timeout_seconds", 15))))
    webhook = _api_call(token, "getWebhookInfo", {}, timeout)
    if not isinstance(webhook, dict):
        raise FeedbackCollectionError("웹훅 상태 응답 형식 오류")
    if webhook.get("url"):
        raise FeedbackCollectionError("기존 웹훅이 있어 반응 수집을 중단했습니다. 웹훅은 변경하지 않았습니다.")

    feedback = state.get("feedback", {})
    if not isinstance(feedback, dict):
        feedback = {}
    offset = feedback.get("next_update_id", 0)
    if type(offset) is not int or offset < 0:
        offset = 0
    updates = _api_call(token, "getUpdates", {
        "offset": offset, "limit": 100, "timeout": 0,
        "allowed_updates": ["message_reaction_count"],
    }, timeout)
    if not isinstance(updates, list) or any(
        not isinstance(update, dict) or type(update.get("update_id")) is not int
        or update["update_id"] < 0 for update in updates
    ):
        raise FeedbackCollectionError("반응 업데이트 형식 오류: 체크포인트를 변경하지 않았습니다.")

    previous_poll = feedback.get("last_poll_at", "")
    gap_warning = False
    try:
        previous = datetime.fromisoformat(previous_poll)
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        gap_warning = now - previous >= timedelta(hours=24)
    except (TypeError, ValueError):
        pass
    changed = apply_reaction_updates(state, updates)
    feedback = state.setdefault("feedback", {})
    feedback.setdefault("started_at", now.isoformat())
    feedback["last_poll_at"] = now.isoformat()
    feedback["last_batch_size"] = len(updates)
    if gap_warning:
        # Keep an operator-visible warning even after the next successful poll.
        feedback["last_gap_warning_at"] = now.isoformat()
        logger.warning("반응 수집 간격이 24시간 이상입니다. Telegram 보관 만료로 일부 집계가 누락될 수 있습니다.")
    prune_feedback(state, now)
    full_batch = len(updates) == 100
    if full_batch:
        logger.warning("반응 업데이트 100건을 처리했습니다. 남은 항목은 상태 저장 후 다음 실행에서 받습니다.")
    logger.info("반응 수집: 업데이트 %d건, 추적 게시물 %d건 갱신", len(updates), changed)
    return {"received": len(updates), "changed": changed, "full_batch": full_batch, "gap_warning": gap_warning}
