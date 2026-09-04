from __future__ import annotations

import unittest

from game_ai_news_bot.collectors import canonical_url, parse_date_from_text, parse_feed


SOURCE = {"id": "test", "name": "Test", "source_weight": 3, "perspective": "research"}


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


if __name__ == "__main__":
    unittest.main()
