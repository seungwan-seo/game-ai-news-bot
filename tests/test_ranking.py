from __future__ import annotations

import unittest
from datetime import datetime, timezone

from game_ai_news_bot.models import Article
from game_ai_news_bot.ranking import deduplicate, keyword_score, rank_articles, select_diverse


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "sources": [{"id": "news", "min_relevance": 5}],
            "ranking": {
                "positive_keywords": {"ai npc": 9, "game development": 5},
                "negative_keywords": {"crypto": -10},
            },
        }

    def article(self, title: str, url: str = "https://example.com/a") -> Article:
        return Article("news", "News", title, url, published_at=datetime.now(timezone.utc), source_weight=5)

    def test_title_match_is_weighted(self):
        article = self.article("AI NPC arrives")
        self.assertEqual(keyword_score(article, {"ai npc": 9}, {}), 18)

    def test_filters_irrelevant_general_ai(self):
        results = rank_articles([self.article("A new office language model")], self.config)
        self.assertEqual(results, [])

    def test_negative_crypto_signal(self):
        article = self.article("AI NPC crypto token sale")
        score = keyword_score(article, {"ai npc": 9}, {"crypto": -10, "token sale": -10})
        self.assertLess(score, 0)

    def test_deduplicates_similar_titles(self):
        first = self.article("NVIDIA launches a new AI NPC system", "https://one.example/a")
        second = self.article("NVIDIA launches new AI NPC system", "https://two.example/a")
        self.assertEqual(len(deduplicate([first, second])), 1)

    def test_limits_articles_per_source(self):
        articles = [self.article(f"AI NPC item {index}", f"https://example.com/{index}") for index in range(4)]
        other = Article("other", "Other", "Game AI research", "https://other.example/a")
        selected = select_diverse(articles + [other], limit=4, max_per_source=2)
        self.assertEqual([item.source_id for item in selected], ["news", "news", "other"])


if __name__ == "__main__":
    unittest.main()
