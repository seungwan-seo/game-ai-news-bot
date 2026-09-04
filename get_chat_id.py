"""봇에게 메시지를 보낸 뒤 실행하면 최근 chat_id를 보여준다."""
from __future__ import annotations

import os
from pathlib import Path

import requests


def load_dotenv() -> None:
    path = Path(__file__).with_name(".env")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()
token = os.environ.get("TELEGRAM_TOKEN", "")
if not token:
    raise SystemExit(".env에 TELEGRAM_TOKEN을 먼저 입력하세요.")
response = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
response.raise_for_status()
for update in response.json().get("result", []):
    message = update.get("message") or update.get("channel_post") or {}
    chat = message.get("chat", {})
    if chat:
        print(chat.get("id"), chat.get("title") or chat.get("username") or chat.get("first_name", ""))
