from __future__ import annotations

import json
import logging
import re

import requests

from .models import Article, DigestItem
from .ranking import category_trend

logger = logging.getLogger(__name__)


CATEGORY_INSIGHTS = {
    "🤖 NPC·에이전트": "대화 데모보다 지연시간·행동 제어·게임 상태 연동 여부를 확인할 가치가 있습니다.",
    "🌍 월드·콘텐츠 생성": "결과의 일관성과 수정 가능성, 실제 엔진으로 내보낼 수 있는지가 실무 기준입니다.",
    "🛠 개발 도구": "제작 속도보다 반복 수정과 버전 관리에 안정적으로 들어오는지가 핵심입니다.",
    "🧪 테스트·플레이어 모델": "QA 비용 절감뿐 아니라 실제 플레이어 행동을 얼마나 잘 재현하는지 봐야 합니다.",
    "📚 연구": "논문 성능보다 공개 코드·재현성·실시간 실행 비용을 함께 확인해야 합니다.",
    "⚖️ 산업·정책": "도입률과 별개로 저작권·표시 의무·개발자와 플레이어 반응이 상용화 속도를 좌우합니다.",
    "📰 기타": "게임 제작이나 플레이 경험에 직접 연결되는 사례인지 원문에서 확인할 필요가 있습니다.",
}


def _truncate(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def fallback_items(articles: list[Article]) -> tuple[list[DigestItem], str]:
    items = []
    for article in articles:
        summary = article.description or "설명이 제공되지 않아 제목과 원문을 확인해야 합니다."
        items.append(
            DigestItem(
                article=article,
                title_ko=article.title,
                summary_ko=_truncate(summary, 230),
                insight_ko=CATEGORY_INSIGHTS.get(article.category, CATEGORY_INSIGHTS["📰 기타"]),
            )
        )
    return items, category_trend(articles)


def _strip_code_fence(text: str) -> str:
    value = text.strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    return value.strip()


def summarize_with_gemini(
    articles: list[Article], api_key: str, model: str, timeout: int = 45
) -> tuple[list[DigestItem], str]:
    if not api_key:
        return fallback_items(articles)

    payload_articles = [
        {
            "id": index,
            "source": article.source_name,
            "category": article.category,
            "title": article.title,
            "description": _truncate(article.description, 1600),
        }
        for index, article in enumerate(articles)
    ]
    prompt = f"""당신은 게임 개발자를 위한 뉴스 편집자다.
아래 자료만 근거로 한국어 브리핑을 작성하라. 과장하거나 자료에 없는 기능·수치·출시 여부를 만들지 마라.
회사 블로그는 주장으로 표현하고 사실처럼 확대하지 마라.

각 기사에 대해:
- title_ko: 고유명사를 보존한 자연스러운 한국어 제목
- summary_ko: 무엇이 새로 나왔거나 밝혀졌는지 1~2문장, 130자 이내
- insight_ko: 게임 개발자가 실제로 검증할 지점이나 의미 1문장, 100자 이내
전체 trend_ko: 여러 기사에서 공통으로 보이는 흐름 1~2문장, 160자 이내

반드시 다음 JSON 형태만 반환하라:
{{"items":[{{"id":0,"title_ko":"","summary_ko":"","insight_ko":""}}],"trend_ko":""}}

기사:
{json.dumps(payload_articles, ensure_ascii=False)}"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = requests.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(_strip_code_fence(text))
    returned = {int(item["id"]): item for item in parsed.get("items", [])}
    fallback, fallback_trend = fallback_items(articles)
    items: list[DigestItem] = []
    for index, article in enumerate(articles):
        item = returned.get(index, {})
        items.append(
            DigestItem(
                article=article,
                title_ko=_truncate(str(item.get("title_ko") or fallback[index].title_ko), 180),
                summary_ko=_truncate(str(item.get("summary_ko") or fallback[index].summary_ko), 180),
                insight_ko=_truncate(str(item.get("insight_ko") or fallback[index].insight_ko), 130),
            )
        )
    trend = _truncate(str(parsed.get("trend_ko") or fallback_trend), 190)
    return items, trend


def summarize(
    articles: list[Article], api_key: str = "", model: str = "gemini-2.5-flash"
) -> tuple[list[DigestItem], str]:
    if not api_key:
        return fallback_items(articles)
    try:
        return summarize_with_gemini(articles, api_key, model)
    except Exception as exc:
        logger.warning("Gemini 요약 실패, 규칙 기반 요약 사용: %s", exc)
        return fallback_items(articles)
