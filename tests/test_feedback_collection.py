from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import requests

from game_ai_news_bot.feedback_collection import FeedbackCollectionError, collect_feedback
from game_ai_news_bot.feedback import register_deliveries
from game_ai_news_bot.models import Article


NOW = datetime(2026, 9, 6, 0, 0, tzinfo=timezone.utc)


def response(result):
    result_response = Mock()
    result_response.json.return_value = {"ok": True, "result": result}
    return result_response


class FeedbackCollectionTests(unittest.TestCase):
    @patch("game_ai_news_bot.feedback_collection.requests.post")
    def test_only_subscribes_to_anonymous_counts_and_checkpoints_ignored_events(self, post):
        state = {"feedback": {"next_update_id": 42}}
        # Old events requested by another allowed_updates setting must not be persisted.
        post.side_effect = [response({"url": ""}), response([
            {"update_id": 42, "message": {"from": {"id": 555, "first_name": "private"}, "text": "secret"}},
            {"update_id": 43, "message_reaction_count": {
                "chat": {"id": -100999, "type": "channel"}, "message_id": 123,
                "date": 1788652800, "reactions": [],
            }},
        ])]
        result = collect_feedback(state, "dummy", {}, NOW)
        self.assertEqual(result["received"], 2)
        self.assertEqual(result["changed"], 0)
        self.assertEqual(state["feedback"]["next_update_id"], 44)
        self.assertEqual(post.call_args.kwargs["json"], {
            "offset": 42, "limit": 100, "timeout": 0,
            "allowed_updates": ["message_reaction_count"],
        })
        self.assertNotIn("private", json.dumps(state))
        self.assertNotIn("secret", json.dumps(state))
        self.assertEqual(state["feedback"]["last_poll_at"], NOW.isoformat())

    @patch("game_ai_news_bot.feedback_collection.requests.post")
    def test_existing_webhook_is_not_deleted_or_polled(self, post):
        post.return_value = response({"url": "https://private.example/webhook-secret"})
        state = {}
        with self.assertRaises(FeedbackCollectionError) as raised:
            collect_feedback(state, "dummy", {}, NOW)
        post.assert_called_once()
        self.assertEqual(state, {})
        self.assertNotIn("webhook-secret", str(raised.exception))

    @patch("game_ai_news_bot.feedback_collection.requests.post")
    def test_network_and_api_errors_do_not_leak_token_or_modify_state(self, post):
        sensitive = "https://api.telegram.org/bot123:secret/getUpdates"
        for failed_response in (
            requests.Timeout(sensitive),
            Mock(json=Mock(return_value={"ok": False, "description": sensitive})),
        ):
            with self.subTest(error=type(failed_response).__name__):
                state = {"feedback": {"next_update_id": 7}}
                before = copy.deepcopy(state)
                post.side_effect = [response({"url": ""}), failed_response]
                with self.assertRaises(FeedbackCollectionError) as raised:
                    collect_feedback(state, "123:secret", {}, NOW)
                self.assertNotIn("123:secret", str(raised.exception))
                self.assertEqual(state, before)

    @patch("game_ai_news_bot.feedback_collection.requests.post")
    def test_reads_only_one_page_before_caller_durably_saves_state(self, post):
        post.side_effect = [response({"url": ""}), response([{"update_id": i} for i in range(100)])]
        state = {}
        result = collect_feedback(state, "dummy", {}, NOW)
        self.assertTrue(result["full_batch"])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(state["feedback"]["next_update_id"], 100)

    @patch("game_ai_news_bot.feedback_collection.requests.post")
    def test_day_long_gap_is_flagged_and_empty_batch_keeps_offset(self, post):
        state = {"feedback": {"next_update_id": 17, "last_poll_at": (NOW - timedelta(hours=25)).isoformat()}}
        post.side_effect = [response({"url": ""}), response([])]
        result = collect_feedback(state, "dummy", {}, NOW)
        self.assertTrue(result["gap_warning"])
        self.assertEqual(state["feedback"]["next_update_id"], 17)
        self.assertEqual(state["feedback"]["last_gap_warning_at"], NOW.isoformat())

    @patch("game_ai_news_bot.feedback_collection.requests.post")
    def test_malformed_page_keeps_existing_checkpoint(self, post):
        state = {"feedback": {"next_update_id": 7}}
        before = copy.deepcopy(state)
        post.side_effect = [response({"url": ""}), response([{"update_id": "bad"}])]
        with self.assertRaises(FeedbackCollectionError):
            collect_feedback(state, "dummy", {}, NOW)
        self.assertEqual(state, before)

    @patch("game_ai_news_bot.feedback_collection.requests.post")
    def test_missing_token_does_not_call_api(self, post):
        with self.assertRaises(FeedbackCollectionError):
            collect_feedback({}, "", {}, NOW)
        post.assert_not_called()

    @patch("game_ai_news_bot.feedback_collection.requests.post")
    def test_malformed_emoji_cannot_break_news_collection(self, post):
        state = {}
        register_deliveries(state, Article("s", "Source", "title", "https://example.com/a"), [{
            "chat_id": -100123, "message_id": 1, "chat_type": "channel", "date": int(NOW.timestamp()),
        }], NOW)
        post.side_effect = [response({"url": ""}), response([{
            "update_id": 1, "message_reaction_count": {
                "chat": {"id": -100123, "type": "channel"}, "message_id": 1,
                "date": int(NOW.timestamp()),
                "reactions": [{"type": {"type": "emoji", "emoji": []}, "total_count": 1}],
            },
        }])]
        collect_feedback(state, "dummy", {}, NOW)
        self.assertEqual(state["feedback"]["next_update_id"], 2)


if __name__ == "__main__":
    unittest.main()
