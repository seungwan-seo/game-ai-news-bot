from __future__ import annotations

import os
from pathlib import Path

import yaml


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: str | Path) -> dict:
    config_path = Path(path).resolve()
    _load_dotenv(config_path.parent / ".env")
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config.get("sources"), list) or not config["sources"]:
        raise ValueError("config.yaml에 sources 목록이 필요합니다.")
    config["base_dir"] = str(config_path.parent)
    return config


def env_settings() -> dict:
    chat_ids = [
        value.strip()
        for value in os.environ.get("TELEGRAM_CHAT_ID", "").split(",")
        if value.strip()
    ]
    return {
        "telegram_token": os.environ.get("TELEGRAM_TOKEN", "").strip(),
        "telegram_chat_ids": chat_ids,
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", "").strip(),
        "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip(),
    }
