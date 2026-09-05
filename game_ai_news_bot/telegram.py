from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


def send_message(
    token: str,
    chat_ids: list[str],
    text: str,
    timeout: int = 30,
    *,
    button_text: str = "",
    button_url: str = "",
) -> None:
    if not token or not chat_ids:
        raise ValueError("TELEGRAM_TOKEN과 TELEGRAM_CHAT_ID가 필요합니다.")
    if bool(button_text) != bool(button_url):
        raise ValueError("버튼 문구와 URL은 함께 지정해야 합니다.")
    if button_url and not button_url.startswith(("https://", "http://")):
        raise ValueError("버튼 URL은 http 또는 https 주소여야 합니다.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id in chat_ids:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if button_text:
            payload["reply_markup"] = {
                "inline_keyboard": [[{"text": button_text, "url": button_url}]]
            }
        response = requests.post(url, json=payload, timeout=timeout)
        if response.status_code == 429:
            try:
                retry_after = int(response.json().get("parameters", {}).get("retry_after", 5))
            except (TypeError, ValueError):
                retry_after = 5
            time.sleep(retry_after + 1)
            response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        time.sleep(1.1)
