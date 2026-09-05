from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from game_ai_news_bot.state import delivered_for_source_today, delivered_today, load_state, mark_delivered


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
            "delivery_source_counts": {"geeknews": 2, "ai-and-games": 8},
        }
        before_midnight = datetime(2026, 9, 5, 14, 59, tzinfo=timezone.utc)
        self.assertEqual(delivered_for_source_today(state, "geeknews", before_midnight), 2)
        next_day = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(delivered_today(state, next_day), 0)
        self.assertEqual(delivered_for_source_today(state, "geeknews", next_day), 0)
        mark_delivered(state, ["https://example.com/new"], next_day, source_id="geeknews")
        self.assertEqual(state["delivery_day_kst"], "2026-09-06")
        self.assertEqual(delivered_today(state, next_day), 1)
        self.assertEqual(delivered_for_source_today(state, "geeknews", next_day), 1)
        self.assertEqual(delivered_for_source_today(state, "ai-and-games", next_day), 0)

    def test_tracks_sources_independently_and_aliases_do_not_use_delivery_quota(self):
        state = {"seen": {}}
        now = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
        topic_url = "https://news.hada.io/topic?id=123"
        original_url = "https://example.com/original"
        mark_delivered(
            state, [topic_url, topic_url], now,
            source_id="geeknews", aliases=[original_url, topic_url],
        )
        self.assertEqual(delivered_today(state, now), 1)
        self.assertEqual(delivered_for_source_today(state, "geeknews", now), 1)
        self.assertEqual(set(state["seen"]), {topic_url, original_url})
        self.assertEqual(state["last_success_at"], now.isoformat())

        mark_delivered(state, ["https://example.com/other"], now, source_id="ai-and-games")
        self.assertEqual(delivered_today(state, now), 2)
        self.assertEqual(delivered_for_source_today(state, "geeknews", now), 1)
        self.assertEqual(delivered_for_source_today(state, "ai-and-games", now), 1)

    def test_legacy_state_preserves_total_when_source_tracking_starts(self):
        state = {"seen": {}, "delivery_day_kst": "2026-09-05", "delivery_count": 4}
        now = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(delivered_for_source_today(state, "geeknews", now), 0)
        mark_delivered(state, ["https://news.hada.io/topic?id=123"], now, source_id="geeknews")
        self.assertEqual(delivered_today(state, now), 5)
        self.assertEqual(delivered_for_source_today(state, "geeknews", now), 1)
        mark_delivered(state, ["https://example.com/legacy-call"], now)
        self.assertEqual(delivered_today(state, now), 6)
        self.assertEqual(delivered_for_source_today(state, "geeknews", now), 1)

    def test_malformed_counters_are_safe(self):
        now = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
        for malformed in [None, [], "broken", -2, float("inf"), True]:
            with self.subTest(malformed=malformed):
                state = {
                    "delivery_day_kst": "2026-09-05",
                    "delivery_count": malformed,
                    "delivery_source_counts": {"geeknews": malformed, "other": "2"},
                }
                self.assertEqual(delivered_today(state, now), 0)
                self.assertEqual(delivered_for_source_today(state, "geeknews", now), 0)
                mark_delivered(state, ["https://example.com/news"], now, source_id="geeknews")
                self.assertEqual(delivered_today(state, now), 1)
                self.assertEqual(delivered_for_source_today(state, "geeknews", now), 1)
                self.assertEqual(delivered_for_source_today(state, "other", now), 2)

        state["delivery_source_counts"] = "broken"
        mark_delivered(state, ["https://example.com/new"], now, source_id="geeknews")
        self.assertEqual(delivered_for_source_today(state, "geeknews", now), 1)

    def test_load_state_dictionaries_are_independent(self):
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "state.json"
            first = load_state(missing)
            second = load_state(missing)
            now = datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc)
            mark_delivered(first, ["https://example.com/news"], now, source_id="geeknews")
            self.assertEqual(second["seen"], {})
            self.assertEqual(second["delivery_source_counts"], {})


if __name__ == "__main__":
    unittest.main()
