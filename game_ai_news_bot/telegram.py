from __future__ import annotations

import html
import logging
import re
import time
from typing import TypedDict

import requests

logger = logging.getLogger(__name__)


class SendReceipt(TypedDict):
    chat_id: int
    message_id: int
    date: int
    chat_type: str


class TelegramSendError(RuntimeError):
    """Safe delivery error; retain earlier receipts without credentials or profiles."""

    def __init__(
        self,
        message: str,
        *,
        receipts: list[SendReceipt] | None = None,
        delivery_uncertain: bool = False,
    ) -> None:
        super().__init__(message)
        self.receipts = list(receipts or [])
        self.delivery_uncertain = delivery_uncertain


class _TelegramAPIError(TelegramSendError):
    """The API explicitly rejected the request, so photo fallback is safe."""


def _button_markup(button_text: str, button_url: str) -> dict | None:
    if not button_text:
        return None
    return {"inline_keyboard": [[{"text": button_text, "url": button_url}]]}


def _visible_length(text: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


def _post(url: str, payload: dict, timeout: int) -> requests.Response:
    def request() -> requests.Response:
        try:
            return requests.post(url, json=payload, timeout=timeout)
        except requests.RequestException:
            # Telegram embeds the token in request URLs. Never propagate those
            # exceptions, and do not resend when a successful response was lost.
            raise TelegramSendError(
                "Telegram 요청의 응답을 확인하지 못했습니다. 자동 재발송하지 않습니다.",
                delivery_uncertain=True,
            ) from None

    response = request()
    if response.status_code == 429:
        try:
            retry_after = int(response.json().get("parameters", {}).get("retry_after", 5))
            retry_after = max(0, retry_after)
        except (AttributeError, TypeError, ValueError):
            retry_after = 5
        time.sleep(retry_after + 1)
        response = request()
    if not 200 <= response.status_code < 300:
        status = response.status_code
        if 400 <= status < 500 and status != 408:
            raise _TelegramAPIError(f"Telegram API가 요청을 거절했습니다 (HTTP {status}).")
        raise TelegramSendError(
            f"Telegram 서버 응답을 확인할 수 없습니다 (HTTP {status}). 자동 재발송하지 않습니다.",
            delivery_uncertain=True,
        )
    return response


def _receipt(response: requests.Response) -> SendReceipt:
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict) and data.get("ok") is False:
        code = data.get("error_code")
        suffix = f" (code {code})" if type(code) is int else ""
        raise _TelegramAPIError(f"Telegram API가 요청을 거절했습니다{suffix}.")
    if isinstance(data, dict) and data.get("ok") is True:
        result = data.get("result")
        if isinstance(result, dict):
            chat = result.get("chat")
            message_id = result.get("message_id")
            date = result.get("date")
            if (
                isinstance(chat, dict)
                and type(chat.get("id")) is int
                and chat["id"] != 0
                and chat.get("type") in ("channel", "private", "group", "supergroup")
                and type(message_id) is int
                and message_id > 0
                and type(date) is int
                and date > 0
            ):
                return {
                    "chat_id": chat["id"],
                    "message_id": message_id,
                    "date": date,
                    "chat_type": chat["type"],
                }
    # This includes ok=true with a malformed Message: it may already be posted.
    raise TelegramSendError(
        "Telegram 발송 결과 형식이 올바르지 않습니다. 자동 재발송하지 않습니다.",
        delivery_uncertain=True,
    )


def send_message(
    token: str,
    chat_ids: list[str],
    text: str,
    timeout: int = 30,
    *,
    button_text: str = "",
    button_url: str = "",
    image_url: str = "",
    preview_url: str = "",
    silent: bool = False,
) -> list[SendReceipt]:
    """Send once per destination and return minimal Telegram message receipts.

    On failure, TelegramSendError retains preceding successful receipts. An
    uncertain delivery must not be blindly retried: Telegram may have posted it.
    Consumers collecting channel feedback should retain channel receipts only.
    """
    if not token or not chat_ids:
        raise ValueError("TELEGRAM_TOKEN과 TELEGRAM_CHAT_ID가 필요합니다.")
    if bool(button_text) != bool(button_url):
        raise ValueError("버튼 문구와 URL은 함께 지정해야 합니다.")
    if button_url and not button_url.startswith(("https://", "http://")):
        raise ValueError("버튼 URL은 http 또는 https 주소여야 합니다.")
    for value in (image_url, preview_url):
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("이미지와 미리보기 URL은 http 또는 https 주소여야 합니다.")
    api_base = f"https://api.telegram.org/bot{token}"
    reply_markup = _button_markup(button_text, button_url)
    receipts: list[SendReceipt] = []
    try:
        for chat_id in chat_ids:
            if image_url and _visible_length(text) <= 1024:
                photo_payload = {
                    "chat_id": chat_id,
                    "photo": image_url,
                    "caption": text,
                    "parse_mode": "HTML",
                    "disable_notification": silent,
                }
                if reply_markup:
                    photo_payload["reply_markup"] = reply_markup
                try:
                    response = _post(f"{api_base}/sendPhoto", photo_payload, timeout)
                    receipt = _receipt(response)
                except _TelegramAPIError as exc:
                    logger.warning("대표 이미지 발송 거절, 링크 미리보기로 대체: %s", exc)
                else:
                    receipts.append(receipt)
                    time.sleep(1.1)
                    continue

            message_payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_notification": silent,
                "link_preview_options": {"is_disabled": not bool(preview_url)},
            }
            if preview_url:
                message_payload["link_preview_options"].update(
                    {
                        "url": preview_url,
                        "prefer_large_media": True,
                        "show_above_text": True,
                    }
                )
            if reply_markup:
                message_payload["reply_markup"] = reply_markup
            response = _post(f"{api_base}/sendMessage", message_payload, timeout)
            receipts.append(_receipt(response))
            time.sleep(1.1)
    except TelegramSendError as exc:
        exc.receipts = receipts + exc.receipts
        raise
    return receipts
