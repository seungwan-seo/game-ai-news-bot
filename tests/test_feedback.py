from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import unittest

from game_ai_news_bot.feedback import (
    apply_reaction_updates,
    build_feedback_report,
    preference_adjustment,
    prune_feedback,
    register_deliveries,
)
from game_ai_news_bot.models import Article


NOW = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
CHAT = -1001234567890


def article(**overrides) -> Article:
    values = dict(
        source_id="geeknews", source_name="GeekNews", title="AI 개발 도구 비교",
        url="https://example.com/article", category="개발 도구", published_at=NOW - timedelta(days=4),
    )
    values.update(overrides)
    return Article(**values)


def receipt(message_id=1, sent_at=None, **overrides) -> dict:
    values = dict(
        chat_id=CHAT, message_id=message_id, chat_type="channel",
        date=int((sent_at or NOW - timedelta(days=3)).timestamp()),
    )
    values.update(overrides)
    return values


def update(update_id=1, message_id=1, up=3, down=1, event_at=None, chat_id=CHAT) -> dict:
    return {
        "update_id": update_id,
        "message_reaction_count": {
            "chat": {"id": chat_id, "type": "channel", "title": "do not retain this"},
            "message_id": message_id,
            "date": int((event_at or NOW - timedelta(days=2)).timestamp()),
            "reactions": [
                {"type": {"type": "emoji", "emoji": "👍"}, "total_count": up},
                {"type": {"type": "emoji", "emoji": "👎"}, "total_count": down},
            ],
        },
    }


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        register_deliveries(self.state, article(), [receipt()], NOW)

    def post(self, message_id=1):
        return self.state["feedback"]["posts"][f"{CHAT}:{message_id}"]

    def test_registers_minimum_channel_metadata_only(self):
        incoming = receipt(message_id=2, user={"id": 123, "first_name": "private"}, secret="secret")
        register_deliveries(self.state, article(), [incoming], NOW)
        post = self.post(2)
        self.assertEqual(post["url"], article().url)
        self.assertEqual(post["published_at"], article().published_at.isoformat())
        self.assertNotIn("user", post)
        self.assertNotIn("secret", post)

    def test_ignores_private_groups_invalid_receipts_and_preserves_existing(self):
        apply_reaction_updates(self.state, [update()])
        before = copy.deepcopy(self.post())
        register_deliveries(self.state, article(title="changed"), [
            receipt(), receipt(2, chat_type="private"), receipt(3, chat_type="supergroup"),
            receipt(4, chat_id=123), receipt(True), receipt(0), None,
        ], NOW)
        self.assertEqual(len(self.state["feedback"]["posts"]), 1)
        self.assertEqual(self.post(), before)

    def test_counts_are_snapshots_not_deltas_and_cancel_to_zero(self):
        self.assertEqual(apply_reaction_updates(self.state, [update()]), 1)
        self.assertEqual(apply_reaction_updates(self.state, [update()]), 0)
        self.assertEqual(self.post()["up"], 3)
        event = update(update_id=2)
        event["message_reaction_count"]["reactions"] = []
        self.assertEqual(apply_reaction_updates(self.state, [event]), 1)
        self.assertEqual((self.post()["up"], self.post()["down"]), (0, 0))
        self.assertEqual((self.post()["learning_up"], self.post()["learning_down"]), (0, 0))
        self.assertEqual(self.state["feedback"]["next_update_id"], 3)

    def test_reverse_arrival_preserves_latest_live_and_within_window(self):
        before_deadline = update(update_id=4, up=5, down=2)
        after_deadline = update(update_id=10, up=99, down=1, event_at=NOW)
        older = update(update_id=2, up=1, down=1, event_at=NOW - timedelta(days=2, hours=1))
        self.assertEqual(apply_reaction_updates(self.state, [after_deadline, before_deadline, older]), 1)
        post = self.post()
        self.assertEqual((post["up"], post["down"]), (99, 1))
        self.assertEqual((post["learning_up"], post["learning_down"]), (5, 2))
        self.assertEqual(post["reaction_update_id"], 10)
        self.assertEqual(post["learning_update_id"], 4)

    def test_same_timestamp_uses_update_id_and_missing_emoji_is_zero(self):
        newest = update(update_id=20, up=9, down=0)
        newest["message_reaction_count"]["reactions"] = newest["message_reaction_count"]["reactions"][:1]
        apply_reaction_updates(self.state, [newest, update(update_id=19, up=2, down=7)])
        self.assertEqual((self.post()["up"], self.post()["down"]), (9, 0))

    def test_unknown_messages_never_store_user_or_chat_payload(self):
        events = [update(update_id=5, chat_id=-1009999), update(update_id=6, message_id=500)]
        events.append({"update_id": 7, "message_reaction": {"user": {"id": 999, "first_name": "PRIVATE"}}})
        events.append({"update_id": 8, "message": {"text": "PRIVATE"}})
        self.assertEqual(apply_reaction_updates(self.state, events), 0)
        self.assertEqual(self.state["feedback"]["next_update_id"], 9)
        encoded = json.dumps(self.state)
        self.assertNotIn("PRIVATE", encoded)
        self.assertNotIn("1009999", encoded)
        self.assertNotIn("do not retain", encoded)

    def test_malformed_updates_are_discarded_but_valid_ids_are_acknowledged(self):
        for count in [-1, True, "4", None, float("inf")]:
            bad = update(update_id=30, up=count)
            self.assertEqual(apply_reaction_updates(self.state, [bad]), 0)
        self.assertEqual(self.state["feedback"]["next_update_id"], 31)
        self.assertEqual(self.post()["up"], 0)
        for bad_id in [-1, True, "99", None]:
            self.assertEqual(apply_reaction_updates(self.state, [update(update_id=bad_id)]), 0)
        self.assertEqual(self.state["feedback"]["next_update_id"], 31)

    def test_only_thumb_emoji_counts_are_kept(self):
        event = update()
        event["message_reaction_count"]["reactions"].extend([
            {"type": {"type": "custom_emoji", "custom_emoji_id": "private-id"}, "total_count": 100},
            {"type": {"type": "emoji", "emoji": "❤"}, "total_count": 10},
        ])
        apply_reaction_updates(self.state, [event])
        self.assertEqual((self.post()["up"], self.post()["down"]), (3, 1))
        self.assertNotIn("private-id", json.dumps(self.state))

    def test_before_send_events_do_not_change_counts(self):
        event = update(event_at=NOW - timedelta(days=4))
        self.assertEqual(apply_reaction_updates(self.state, [event]), 0)
        self.assertEqual(self.post()["up"], 0)

    def test_exact_window_deadline_counts_but_next_second_does_not(self):
        deadline = NOW - timedelta(days=1)
        apply_reaction_updates(self.state, [
            update(update_id=1, up=5, down=0, event_at=deadline),
            update(update_id=2, up=9, down=0, event_at=deadline + timedelta(seconds=1)),
        ])
        self.assertEqual(self.post()["up"], 9)
        self.assertEqual(self.post()["learning_up"], 5)

    def test_window_configuration_is_fixed_per_registered_post(self):
        self.state["feedback"]["window_hours"] = 24
        register_deliveries(self.state, article(), [receipt(2)], NOW)
        self.state["feedback"]["window_hours"] = 72
        self.assertEqual(self.post()["window_hours"], 48)
        self.assertEqual(self.post(2)["window_hours"], 24)
        apply_reaction_updates(self.state, [update(message_id=2, event_at=NOW - timedelta(days=1, hours=12))])
        self.assertEqual(self.post(2)["up"], 3)
        self.assertEqual(self.post(2)["learning_up"], 0)

    def test_current_counts_are_visible_before_learning_window_closes(self):
        register_deliveries(self.state, article(), [receipt(2, NOW - timedelta(hours=1))], NOW)
        apply_reaction_updates(self.state, [update(message_id=2, event_at=NOW, up=20, down=0)])
        report = build_feedback_report(self.state, {}, NOW)
        self.assertEqual(report["total"]["up"], 20)
        self.assertEqual(report["total"]["learning_up"], 0)
        self.assertEqual(report["total"]["mature_posts"], 1)
        self.assertFalse(report["total"]["mature"])

    def matured_group(self):
        for message_id in range(1, 6):
            register_deliveries(self.state, article(url=f"https://example.com/{message_id}"), [receipt(message_id)], NOW)
        apply_reaction_updates(self.state, [
            update(update_id=1, message_id=1, up=10, down=0),
            update(update_id=2, message_id=2, up=5, down=0),
            update(update_id=3, message_id=3, up=5, down=0),
        ])
        return build_feedback_report(self.state, {}, NOW)

    def test_maturity_requires_post_count_reacted_post_count_and_total_reactions(self):
        report = self.matured_group()
        source = report["by_source"]["geeknews"]
        self.assertTrue(source["mature"])
        self.assertEqual(source["mature_posts"], 5)
        self.assertEqual(source["learning_reacted_posts"], 3)
        self.assertEqual(source["learning_reactions"], 20)
        self.assertAlmostEqual(source["bias"], 20 / 30)
        self.assertEqual(report["by_category"]["개발 도구"], source)
        for settings in [{"min_posts": 6}, {"min_reacted_posts": 4}, {"min_reactions": 21}]:
            with self.subTest(settings=settings):
                self.assertFalse(build_feedback_report(self.state, settings, NOW)["total"]["mature"])

    def test_no_reaction_is_neutral_and_cannot_satisfy_reacted_post_gate(self):
        for message_id in range(1, 7):
            register_deliveries(self.state, article(), [receipt(message_id)], NOW)
        neutral = build_feedback_report(self.state, {}, NOW)["total"]
        self.assertEqual(neutral["bias"], 0)
        self.assertFalse(neutral["mature"])
        apply_reaction_updates(self.state, [update(up=100, down=0)])
        one = build_feedback_report(self.state, {}, NOW)["total"]
        self.assertFalse(one["mature"])
        self.assertEqual(one["learning_reacted_posts"], 1)

    def test_negative_bias_and_new_source_receive_no_unearned_adjustment(self):
        report = self.matured_group()
        config = {"apply_to_ranking": True}
        self.assertEqual(preference_adjustment(article(), report, {}), 0)
        self.assertEqual(preference_adjustment(article(), report, {"feedback": config}), 2)
        self.assertEqual(preference_adjustment(article(), report, {**config, "enabled": False}), 0)
        self.assertEqual(preference_adjustment(article(source_id="new", category="new"), report, config), 0)
        report["by_source"]["geeknews"]["bias"] = -1
        report["by_category"]["개발 도구"]["bias"] = -1
        self.assertEqual(preference_adjustment(article(), report, {**config, "max_adjustment": 99}), -3)

    def test_category_source_are_averaged_not_added(self):
        report = self.matured_group()
        report["by_source"]["geeknews"]["bias"] = 1
        report["by_category"]["개발 도구"]["bias"] = -1
        self.assertEqual(preference_adjustment(article(), report, {"apply_to_ranking": True}), 0)
        report["by_category"]["개발 도구"]["mature"] = False
        self.assertEqual(preference_adjustment(article(), report, {"apply_to_ranking": True}), 3)

    def test_thirty_day_report_does_not_mutate_state_and_excludes_future_posts(self):
        register_deliveries(self.state, article(source_id="old"), [receipt(2, NOW - timedelta(days=31))], NOW)
        register_deliveries(self.state, article(source_id="future"), [receipt(3, NOW + timedelta(days=1))], NOW)
        before = copy.deepcopy(self.state)
        report = build_feedback_report(self.state, {}, NOW)
        self.assertEqual(report["total"]["posts"], 1)
        self.assertEqual(set(report["by_source"]), {"geeknews"})
        self.assertEqual(self.state, before)

    def test_config_cannot_disable_safety_thresholds_or_exceed_score_cap(self):
        report = build_feedback_report(self.state, {"feedback": {
            "min_posts": 0, "min_reacted_posts": 0, "min_reactions": 0, "prior_reactions": 0,
        }}, NOW)
        self.assertEqual(report["gates"], {
            "min_posts": 5, "min_reacted_posts": 3, "min_reactions": 20, "prior_reactions": 10,
        })
        self.assertFalse(report["total"]["mature"])
        self.assertEqual(preference_adjustment(article(), report, {"apply_to_ranking": "true"}), 0)

    def test_malformed_legacy_state_does_not_raise(self):
        for value in [None, [], "broken"]:
            state = {"feedback": value}
            self.assertEqual(build_feedback_report(state, {}, NOW)["total"]["posts"], 0)
            apply_reaction_updates(state, [{"update_id": 5}])
            self.assertEqual(state["feedback"]["next_update_id"], 6)
            prune_feedback(state, NOW)
        self.post()["reaction_date"] = "broken"
        self.post()["learning_update_id"] = None
        self.assertEqual(apply_reaction_updates(self.state, [update()]), 1)

    def test_pruning_retains_recent_channel_posts_and_cursor(self):
        register_deliveries(self.state, article(), [receipt(2, NOW - timedelta(days=181))], NOW)
        self.state["feedback"]["posts"]["invalid"] = {"sent_at": NOW.isoformat(), "private": "no"}
        self.state["feedback"]["next_update_id"] = 100
        prune_feedback(self.state, NOW)
        self.assertEqual(set(self.state["feedback"]["posts"]), {f"{CHAT}:1"})
        self.assertEqual(self.state["feedback"]["next_update_id"], 100)

    def test_pruning_caps_post_count_at_six_thousand(self):
        base = copy.deepcopy(self.post())
        self.state["feedback"]["posts"] = {
            f"{CHAT}:{number}": {**base, "message_id": number, "sent_at": (NOW - timedelta(seconds=number)).isoformat()}
            for number in range(1, 6003)
        }
        prune_feedback(self.state, NOW)
        self.assertEqual(len(self.state["feedback"]["posts"]), 6000)
        self.assertNotIn(f"{CHAT}:6002", self.state["feedback"]["posts"])


if __name__ == "__main__":
    unittest.main()
