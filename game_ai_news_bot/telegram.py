from __future__ import annotations

import html
import logging
import re
import time

import requests

logger = logging.getLogger(__name__)


def _button_markup(button_text: str, button_url: str) -> dict | None:
    if not button_text:
        return None
    return {"inline_keyboard": [[{"text": button_text, "url": button_url}]]}


def _visible_length(text: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


def _post(url: str, payload: dict, timeout: int) -> requests.Response:
    response = requests.post(url, json=payload, timeout=timeout)
    if response.status_code == 429:
        try:
            retry_after = int(response.json().get("parameters", {}).get("retry_after", 5))
        except (TypeError, ValueError):
            retry_after = 5
        time.sleep(retry_after + 1)
        response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response


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
) -> None:
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
                _post(f"{api_base}/sendPhoto", photo_payload, timeout)
                time.sleep(1.1)
                continue
            except requests.RequestException as exc:
                logger.warning("대표 이미지 발송 실패, 링크 미리보기로 대체: %s", exc)

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
        _post(f"{api_base}/sendMessage", message_payload, timeout)
        time.sleep(1.1)
