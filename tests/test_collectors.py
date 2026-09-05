from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from game_ai_news_bot.collectors import (
    Collector,
    canonical_url,
    page_metadata,
    parse_date_from_text,
    parse_feed,
)
from game_ai_news_bot.models import Article


SOURCE = {"id": "test", "name": "Test", "source_weight": 3, "perspective": "research"}
GEEKNEWS_SOURCE = {
    "id": "geeknews", "name": "긱뉴스", "editorial_filter": "geeknews",
    "language": "ko", "perspective": "community",
}


class FeedParserTests(unittest.TestCase):
    def test_parses_rss(self):
        xml = """<?xml version="1.0"?><rss><channel><item>
        <title>AI NPC ships in a game</title><link>https://example.com/a?utm_source=x</link>
        <description><![CDATA[<p>Useful summary.</p>]]></description>
        <pubDate>Fri, 04 Sep 2026 10:00:00 GMT</pubDate>
        </item></channel></rss>"""
        articles = parse_feed(xml, SOURCE)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].url, "https://example.com/a")
        self.assertEqual(articles[0].description, "Useful summary.")
        self.assertIsNotNone(articles[0].published_at)

    def test_parses_atom_link_attribute(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Procedural content generation</title>
        <link rel="alternate" href="https://example.com/paper" />
        <summary>Paper summary</summary><updated>2026-09-04T10:00:00Z</updated>
        </entry></feed>"""
        articles = parse_feed(xml, SOURCE)
        self.assertEqual(articles[0].url, "https://example.com/paper")

    def test_extracts_rss_media_image(self):
        xml = """<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item>
        <title>AI game agent</title><link>https://example.com/article</link>
        <media:content medium="image" url="https://cdn.example.com/cover.jpg" />
        </item></channel></rss>"""
        article = parse_feed(xml, SOURCE)[0]
        self.assertEqual(article.image_url, "https://cdn.example.com/cover.jpg")

    def test_extracts_image_embedded_in_description(self):
        xml = """<rss><channel><item>
        <title>AI game agent</title><link>https://example.com/article</link>
        <description><![CDATA[<img src="/images/cover.webp"><p>Summary</p>]]></description>
        </item></channel></rss>"""
        article = parse_feed(xml, SOURCE)[0]
        self.assertEqual(article.image_url, "https://example.com/images/cover.webp")

    def test_extracts_page_open_graph_image_and_useful_excerpt(self):
        html = """<html><head>
        <meta property="og:image" content="/images/hero.jpg">
        <meta property="og:description" content="Hello all and welcome to this week's newsletter.">
        </head><body><article>
        <p>Our AI NPC agent now reads live game state and changes its behavior during playtests.</p>
        </article></body></html>"""
        image, excerpt = page_metadata(
            html, "https://example.com/post", "AI NPC agent playtest"
        )
        self.assertEqual(image, "https://example.com/images/hero.jpg")
        self.assertIn("live game state", excerpt)

    def test_rejects_non_http_url(self):
        self.assertEqual(canonical_url("javascript:alert(1)"), "")

    def test_ignores_script_appended_after_feed(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>AI gameplay</title><link href="https://example.com/a" />
        </entry></feed><script>challenge()</script>"""
        self.assertEqual(len(parse_feed(xml, SOURCE)), 1)

    def test_extracts_human_readable_date(self):
        result = parse_date_from_text("Introducing Muse February 19, 2025 | Research")
        self.assertEqual(result.year, 2025)

    def test_geeknews_atom_preserves_korean_escaped_html_and_paragraphs(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Claude Code와 Codex 비교</title>
        <link rel="self" href="https://news.hada.io/rss/news" />
        <link rel="alternate" href="https://news.hada.io/topic?id=123&amp;utm_source=rss" />
        <content type="html">&lt;p&gt;75개 저장소에서 &lt;strong&gt;코딩 도구&lt;/strong&gt;를 비교했다.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;유효 세션 5,292개를 분석했다.&lt;/li&gt;&lt;/ul&gt;</content>
        <updated>2026-09-06T01:00:00+09:00</updated>
        </entry></feed>"""
        article = parse_feed(xml, GEEKNEWS_SOURCE)[0]
        self.assertEqual(article.title, "Claude Code와 Codex 비교")
        self.assertEqual(article.url, "https://news.hada.io/topic?id=123")
        lines = article.description.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("75개 저장소에서", lines[0])
        self.assertIn("코딩 도구", lines[0])
        self.assertEqual(lines[1], "유효 세션 5,292개를 분석했다.")
        self.assertEqual(article.metadata["language"], "ko")
        self.assertEqual(article.metadata["button_text"], "📰 긱뉴스에서 읽기")
        self.assertEqual(article.published_at.isoformat(), "2026-09-05T16:00:00+00:00")

    def test_geeknews_atom_xhtml_keeps_text_and_block_boundaries(self):
        xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>AI 코딩 도구 평가</title><link href="https://news.hada.io/topic?id=124" />
        <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">
        <p>코딩 도구의 <strong>비용과 성능</strong>을 비교했다.</p>
        <p>75개 저장소에서 총 16,893회 실행했다.</p>
        </div></content></entry></feed>"""
        article = parse_feed(xml, GEEKNEWS_SOURCE)[0]
        self.assertEqual(len(article.description.splitlines()), 2)
        self.assertIn("비용과 성능", article.description.splitlines()[0])
        self.assertIn("16,893", article.description.splitlines()[1])
        self.assertNotIn("ns0:", article.description)

    def test_geeknews_enrichment_403_retains_feed_for_link_preview(self):
        collector = Collector({"delay_seconds": 0})
        article = Article(
            "geeknews", "긱뉴스", "코딩 도구 비교", "https://news.hada.io/topic?id=125",
            description="한국어 피드에 소개된 비교 실험 요약입니다.",
            metadata={"editorial_filter": "geeknews"},
        )
        with patch.object(collector, "_get", side_effect=requests.HTTPError("403 Forbidden")) as get:
            result = collector.enrich_article(article)
        self.assertIs(result, article)
        self.assertEqual(article.description, "한국어 피드에 소개된 비교 실험 요약입니다.")
        self.assertEqual(article.url, "https://news.hada.io/topic?id=125")
        self.assertEqual(article.image_url, "")
        self.assertNotIn("original_url", article.metadata)
        get.assert_called_once()

    def test_geeknews_enrichment_finds_original_url_without_replacing_korean_excerpt(self):
        collector = Collector({"delay_seconds": 0})
        article = Article(
            "geeknews", "긱뉴스", "코딩 도구 비교", "https://news.hada.io/topic?id=126",
            description="한국어 피드의 75개 저장소 분석 결과입니다.",
            metadata={"editorial_filter": "geeknews"},
        )
        response = Mock(headers={"content-type": "text/html"}, text="""
        <meta property="og:image" content="https://cdn.example.com/hero.jpg">
        <meta property="og:description" content="This longer English description must not overwrite the Korean feed excerpt.">
        <div class="topictitle"><a href="https://example.com/report?utm_source=geeknews&amp;version=1#summary">원문</a></div>
        """)
        with patch.object(collector, "_get", return_value=response) as get:
            collector.enrich_article(article)
        self.assertEqual(article.metadata["original_url"], "https://example.com/report?version=1")
        self.assertEqual(article.description, "한국어 피드의 75개 저장소 분석 결과입니다.")
        self.assertEqual(article.image_url, "https://cdn.example.com/hero.jpg")
        self.assertEqual(article.url, "https://news.hada.io/topic?id=126")
        get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
