from __future__ import annotations

import unittest

from game_ai_news_bot.digest import TELEGRAM_SAFE_LIMIT, build_digest
from game_ai_news_bot.models import Article, DigestItem


class DigestTests(unittest.TestCase):
    def test_escapes_untrusted_content_and_keeps_link(self):
        article = Article("s", "A&B", "raw", "https://example.com/a", category="🤖 NPC·에이전트")
        item = DigestItem(article, "<새 기능>", "A & B", "검증 <필요>")
        message = build_digest([item], "흐름 & 변화", "브리핑")
        self.assertIn("&lt;새 기능&gt;", message)
        self.assertIn("A &amp; B", message)
        self.assertIn('href="https://example.com/a"', message)

    def test_stays_under_telegram_limit(self):
        items = []
        for index in range(30):
            article = Article("s", "Source", "raw", f"https://example.com/{index}", category="📚 연구")
            items.append(DigestItem(article, "제목" * 50, "요약" * 100, "인사이트" * 50))
        message = build_digest(items, "전체 흐름", "브리핑")
        self.assertLessEqual(len(message), TELEGRAM_SAFE_LIMIT)


if __name__ == "__main__":
    unittest.main()
