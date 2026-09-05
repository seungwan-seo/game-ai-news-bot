from __future__ import annotations

import unittest

from game_ai_news_bot.digest import TELEGRAM_SAFE_LIMIT, build_article_post
from game_ai_news_bot.models import Article, DigestItem


class DigestTests(unittest.TestCase):
    def test_escapes_untrusted_content_and_keeps_link(self):
        article = Article("s", "A&B", "raw", "https://example.com/a", category="🤖 NPC·에이전트")
        item = DigestItem(article, "<새 기능>", "A & B", "검증 <필요>")
        message = build_article_post(item, "브리핑")
        self.assertIn("&lt;새 기능&gt;", message)
        self.assertIn("EN · raw", message)
        self.assertIn("A &amp; B", message)
        self.assertIn("개발 인사이트", message)
        self.assertIn('href="https://example.com/a"', message)
        self.assertLess(
            message.index('href="https://example.com/a"'), message.index("A &amp; B")
        )
        self.assertIn("출처 · A&amp;B ·", message)

    def test_omits_duplicate_original_title(self):
        article = Article("s", "Source", "같은 제목", "https://example.com/a")
        item = DigestItem(article, "같은 제목", "요약", "인사이트")
        message = build_article_post(item, "브리핑")
        self.assertNotIn("EN ·", message)

    def test_article_post_stays_under_telegram_limit(self):
        article = Article("s", "Source", "raw", "https://example.com/a", category="📚 연구")
        item = DigestItem(article, "제목" * 50, "요약" * 100, "인사이트" * 50)
        message = build_article_post(item, "브리핑")
        self.assertLessEqual(len(message), TELEGRAM_SAFE_LIMIT)


if __name__ == "__main__":
    unittest.main()
