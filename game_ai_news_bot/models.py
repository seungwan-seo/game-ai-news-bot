from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Article:
    source_id: str
    source_name: str
    title: str
    url: str
    description: str = ""
    published_at: datetime | None = None
    source_weight: int = 0
    perspective: str = "unknown"
    relevance: int = 0
    score: float = 0.0
    category: str = "기타"
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class DigestItem:
    article: Article
    title_ko: str
    summary_ko: str
    insight_ko: str
