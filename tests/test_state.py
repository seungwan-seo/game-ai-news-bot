from __future__ import annotations

import unittest
from datetime import datetime, timezone

from game_ai_news_bot.state import delivered_today, mark_delivered


class DeliveryStateTests(unittest.TestCase):
    def test_counts_only_successfully_delivered_urls(self):
        state = {"seen": {}}
        now = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
        mark_delivered(state, ["https://example.com/1"], now)
        self.assertEqual(delivered_today(state, now), 1)
        self.assertIn("https://example.com/1", state["seen"])

    def test_resets_count_at_kst_date_boundary(self):
        state = {
            "seen": {},
            "delivery_day_kst": "2026-09-05",
            "delivery_count": 10,
        }
        next_day = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(delivered_today(state, next_day), 0)
        mark_delivered(state, ["https://example.com/new"], next_day)
        self.assertEqual(state["delivery_day_kst"], "2026-09-06")
        self.assertEqual(delivered_today(state, next_day), 1)


if __name__ == "__main__":
    unittest.main()
