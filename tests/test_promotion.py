from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from game_ai_news_bot.promotion import (
    build_promotion_post,
    mark_promotion_sent,
    promotion_is_due,
    select_promotion,
)


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "enabled": True,
            "interval_days": 5,
            "channels": [
                {
                    "name": "Steam & Deals",
                    "url": "https://t.me/steam_deals_free",
                    "description": "무료 <게임>",
                },
                {
                    "name": "Second",
                    "url": "https://t.me/second_channel",
                    "description": "두 번째",
                },
            ],
        }
        self.now = datetime(2026, 9, 5, tzinfo=timezone.utc)

    def test_first_promotion_is_due(self):
        self.assertTrue(promotion_is_due({}, self.config, self.now))

    def test_interval_is_five_days(self):
        state = {"last_promo_at": (self.now - timedelta(days=4)).isoformat()}
        self.assertFalse(promotion_is_due(state, self.config, self.now))
        state["last_promo_at"] = (self.now - timedelta(days=5)).isoformat()
        self.assertTrue(promotion_is_due(state, self.config, self.now))

    def test_rotates_channels_after_success(self):
        state = {}
        self.assertEqual(select_promotion(state, self.config)["name"], "Steam & Deals")
        mark_promotion_sent(state, self.config, self.now)
        self.assertEqual(select_promotion(state, self.config)["name"], "Second")

    def test_promotion_html_is_escaped(self):
        message = build_promotion_post(self.config["channels"][0])
        self.assertIn("Steam &amp; Deals", message)
        self.assertIn("무료 &lt;게임&gt;", message)
        self.assertIn('href="https://t.me/steam_deals_free"', message)
        self.assertNotIn("채널 바로가기", message)


if __name__ == "__main__":
    unittest.main()
