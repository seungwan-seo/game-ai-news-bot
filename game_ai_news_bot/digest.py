from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import DigestItem


TELEGRAM_SAFE_LIMIT = 3900

PERSPECTIVE_LABELS = {
    "independent": "독립 분석",
    "journalism": "전문 보도",
    "research": "연구 원문",
    "vendor": "공식 발표",
}


def _esc(value: str) -> str:
    return html.escape(str(value), quote=False)


def build_article_post(
    item: DigestItem, title: str, timezone_name: str = "Asia/Seoul"
) -> str:
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        # 일부 최소 Windows/Python 환경에는 IANA tzdata가 없다. KST는 DST가 없어 고정 오프셋이 안전하다.
        if timezone_name != "Asia/Seoul":
            raise
        local_timezone = timezone(timedelta(hours=9), name="KST")
    now = datetime.now(local_timezone)
    article = item.article
    perspective = PERSPECTIVE_LABELS.get(article.perspective, "출처")
    article_url = html.escape(article.url, quote=True)
    original_title = ""
    if item.title_ko.casefold() != article.title.casefold():
        original_title = f"\n<i>EN · {_esc(article.title)}</i>"
    message = (
        f"<b>🎮 {_esc(title)}</b>\n"
        f"<code>{now:%Y-%m-%d}</code>\n\n"
        f"<b>{_esc(article.category)}</b>\n"
        f'<b><a href="{article_url}">🔗 {_esc(item.title_ko)}</a></b>'
        f"{original_title}\n\n"
        f"{_esc(item.summary_ko)}\n\n"
        f"💡 <b>개발 인사이트</b>\n{_esc(item.insight_ko)}\n\n"
        f"<i>출처 · {_esc(article.source_name)} · {perspective}</i>"
    )
    if len(message) > TELEGRAM_SAFE_LIMIT:
        raise ValueError("기사 게시물이 Telegram 안전 길이를 초과했습니다.")
    return message
