from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from .models import Article

logger = logging.getLogger(__name__)


def clean_text(value: str, limit: int = 1200) -> str:
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"}:
        return ""
    kept_query = []
    for pair in parts.query.split("&") if parts.query else []:
        key = pair.partition("=")[0].lower()
        if key.startswith("utm_") or key in {"fbclid", "gclid", "mc_cid", "mc_eid"}:
            continue
        kept_query.append(pair)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "&".join(kept_query), ""))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children_by_name(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _first_text(element: ET.Element, *names: str) -> str:
    # 호출자가 준 순서를 우선순위로 사용한다. 예: 짧은 description보다 encoded 본문이 우선.
    for name in names:
        wanted = name.lower()
        for child in list(element):
            if _local_name(child.tag) == wanted and child.text:
                return child.text.strip()
    return ""


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        result = None
    if result is None:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def parse_date_from_text(value: str) -> datetime | None:
    if not value:
        return None
    iso_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", value)
    if iso_match:
        return datetime.strptime(iso_match.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    month_match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+20\d{2}\b",
        value,
        flags=re.IGNORECASE,
    )
    if month_match:
        return datetime.strptime(month_match.group(0).title(), "%B %d, %Y").replace(tzinfo=timezone.utc)
    return None


def parse_feed(xml_text: str, source: dict, description_limit: int = 900) -> list[Article]:
    # 일부 CDN은 정상 XML 뒤에 챌린지 <script>를 덧붙인다. 첫 피드 문서까지만 파싱한다.
    for closing_tag in ("</rss>", "</feed>"):
        end = xml_text.find(closing_tag)
        if end >= 0:
            xml_text = xml_text[: end + len(closing_tag)]
            break
    root = ET.fromstring(xml_text)
    root_name = _local_name(root.tag)
    entries: list[ET.Element] = []
    if root_name == "rss":
        channel = next((c for c in list(root) if _local_name(c.tag) == "channel"), root)
        entries = _children_by_name(channel, "item")
    elif root_name == "feed":
        entries = _children_by_name(root, "entry")
    else:
        entries = [e for e in root.iter() if _local_name(e.tag) in {"item", "entry"}]

    articles: list[Article] = []
    for entry in entries:
        title = clean_text(_first_text(entry, "title"), 300)
        description = _first_text(entry, "encoded", "content", "summary", "description")
        link = _first_text(entry, "link")
        if not link:
            for node in _children_by_name(entry, "link"):
                href = node.attrib.get("href", "")
                rel = node.attrib.get("rel", "alternate")
                if href and rel in {"alternate", ""}:
                    link = href
                    break
        published = _first_text(entry, "pubdate", "published", "updated", "date")
        url = canonical_url(link)
        if not title or not url:
            continue
        articles.append(
            Article(
                source_id=source["id"],
                source_name=source["name"],
                title=title,
                url=url,
                description=clean_text(description, description_limit),
                published_at=parse_datetime(published),
                source_weight=int(source.get("source_weight", 0)),
                perspective=source.get("perspective", "unknown"),
            )
        )
    return articles


class Collector:
    def __init__(self, http_config: dict, description_limit: int = 900):
        self.timeout = int(http_config.get("timeout_seconds", 25))
        self.delay = float(http_config.get("delay_seconds", 0.5))
        self.description_limit = description_limit
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": http_config.get("user_agent", "game-ai-news-bot/0.1"),
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8",
            }
        )

    def _get(self, url: str, **kwargs) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        time.sleep(self.delay)
        return response

    def collect_source(self, source: dict) -> list[Article]:
        kind = source.get("kind", "rss")
        if kind == "rss":
            return self._collect_rss(source)
        if kind == "html":
            return self._collect_html(source)
        if kind == "arxiv":
            return self._collect_arxiv(source)
        if kind == "krafton_blog":
            return self._collect_krafton_blog(source)
        raise ValueError(f"지원하지 않는 source kind: {kind}")

    def collect_all(self, sources: list[dict]) -> tuple[list[Article], list[str]]:
        articles: list[Article] = []
        errors: list[str] = []
        for source in sources:
            if source.get("enabled", True) is False:
                continue
            try:
                found = self.collect_source(source)
                logger.info("%s: %d건 수집", source["name"], len(found))
                articles.extend(found)
            except Exception as exc:  # 한 소스 장애가 전체 브리핑을 막지 않게 한다.
                logger.warning("%s 수집 실패: %s", source.get("name", source.get("id")), exc)
                errors.append(f"{source.get('name', source.get('id'))}: {exc}")
        return articles, errors

    def _collect_rss(self, source: dict) -> list[Article]:
        response = self._get(source["url"])
        return parse_feed(response.text, source, self.description_limit)

    def _collect_arxiv(self, source: dict) -> list[Article]:
        params = {
            "search_query": source["query"],
            "start": 0,
            "max_results": int(source.get("max_results", 30)),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = "https://export.arxiv.org/api/query?" + urlencode(params)
        response = self._get(url)
        return parse_feed(response.text, source, self.description_limit)

    def _collect_html(self, source: dict) -> list[Article]:
        response = self._get(source["url"])
        soup = BeautifulSoup(response.content, "html.parser")
        pattern = re.compile(source["link_pattern"], re.IGNORECASE)
        seen: set[str] = set()
        articles: list[Article] = []
        for anchor in soup.find_all("a", href=True):
            url = canonical_url(urljoin(source["url"], anchor["href"]))
            if not url or not pattern.search(url) or url in seen:
                continue
            title = clean_text(anchor.get("aria-label") or anchor.get_text(" ", strip=True), 300)
            if len(title) < 10:
                continue
            container = anchor.find_parent("article") or anchor.find_parent("li") or anchor.parent
            description = clean_text(container.get_text(" ", strip=True) if container else "", self.description_limit)
            if description == title:
                description = ""
            published = parse_date_from_text(description)
            if source.get("require_date", False) and published is None:
                continue
            seen.add(url)
            articles.append(
                Article(
                    source_id=source["id"],
                    source_name=source["name"],
                    title=title,
                    url=url,
                    description=description,
                    published_at=published,
                    source_weight=int(source.get("source_weight", 0)),
                    perspective=source.get("perspective", "unknown"),
                )
            )
            if len(articles) >= int(source.get("max_results", 30)):
                break
        return articles

    def _collect_krafton_blog(self, source: dict) -> list[Article]:
        """KRAFTON AI가 페이지 안에 제공하는 공개 영문 포스트 메타데이터를 읽는다."""
        response = self._get(source["url"])
        text = response.content.decode("utf-8", errors="replace")
        pattern = re.compile(
            r'\{\s*date_en:\s*"(?P<date>(?:\\.|[^"\\])*)"'
            r'.*?title_en:\s*"(?P<title>(?:\\.|[^"\\])*)"'
            r'.*?excerpt_en:\s*"(?P<description>(?:\\.|[^"\\])*)"'
            r'.*?file_en:\s*"(?P<file>(?:\\.|[^"\\])*)"',
            re.DOTALL,
        )

        def unescape(value: str) -> str:
            return (
                value.replace("\\'", "'")
                .replace('\\"', '"')
                .replace("\\n", " ")
                .replace("\\/", "/")
            )

        articles: list[Article] = []
        for match in pattern.finditer(text):
            date_value = unescape(match.group("date"))
            published = None
            try:
                published = datetime.strptime(date_value, "%B %d, %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            title = clean_text(unescape(match.group("title")), 300)
            description = clean_text(unescape(match.group("description")), self.description_limit)
            url = canonical_url(urljoin(source["url"], unescape(match.group("file"))))
            if title and url:
                articles.append(
                    Article(
                        source_id=source["id"],
                        source_name=source["name"],
                        title=title,
                        url=url,
                        description=description,
                        published_at=published,
                        source_weight=int(source.get("source_weight", 0)),
                        perspective=source.get("perspective", "unknown"),
                    )
                )
        return articles[: int(source.get("max_results", 30))]
