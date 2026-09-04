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


def build_digest(
    items: list[DigestItem], trend: str, title: str, timezone_name: str = "Asia/Seoul"
) -> str:
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        # 일부 최소 Windows/Python 환경에는 IANA tzdata가 없다. KST는 DST가 없어 고정 오프셋이 안전하다.
        if timezone_name != "Asia/Seoul":
            raise
        local_timezone = timezone(timedelta(hours=9), name="KST")
    now = datetime.now(local_timezone)
    header = f"<b>🎮 {_esc(title)}</b>\n<code>{now:%Y-%m-%d}</code> · {len(items)}개 소식"
    footer = f"\n\n<b>📌 오늘의 흐름</b>\n{_esc(trend)}"
    blocks: list[str] = []
    for index, item in enumerate(items, 1):
        article = item.article
        perspective = PERSPECTIVE_LABELS.get(article.perspective, "출처")
        original_title = ""
        if item.title_ko.casefold() != article.title.casefold():
            original_title = f"\n<i>EN · {_esc(article.title)}</i>"
        block = (
            f"\n\n<b>{index}. {_esc(article.category)}  {_esc(item.title_ko)}</b>"
            f"{original_title}\n"
            f"{_esc(item.summary_ko)}\n"
            f"💡 {_esc(item.insight_ko)}\n"
            f'<a href="{html.escape(article.url, quote=True)}">'
            f'{_esc(article.source_name)} · {perspective} · 원문</a>'
        )
        if len(header + "".join(blocks) + block + footer) > TELEGRAM_SAFE_LIMIT:
            break
        blocks.append(block)
    return header + "".join(blocks) + footer
