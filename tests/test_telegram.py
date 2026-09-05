from __future__ import annotations

import unittest
import traceback
from unittest.mock import Mock, patch

import requests

from game_ai_news_bot.telegram import TelegramSendError, send_message


def api_response(message_id: int = 42, chat_id: int = -100123) -> Mock:
    response = Mock(status_code=200)
    response.json.return_value = {
        "ok": True,
        "result": {
            "message_id": message_id,
            "date": 1788656400,
            "chat": {"id": chat_id, "type": "channel", "username": "channel"},
            "from": {"id": 999, "first_name": "Private profile"},
            "text": "message",
        },
    }
    return response


class TelegramTests(unittest.TestCase):
    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_sends_visible_url_button(self, post: Mock, _sleep: Mock):
        post.return_value = api_response()
        receipts = send_message(
            "token",
            ["@channel"],
            "message",
            button_text="🔗 원문 기사 바로 보기",
            button_url="https://example.com/article",
        )
        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            payload["reply_markup"]["inline_keyboard"][0][0],
            {
                "text": "🔗 원문 기사 바로 보기",
                "url": "https://example.com/article",
            },
        )
        self.assertEqual(
            receipts,
            [{"chat_id": -100123, "message_id": 42, "date": 1788656400, "chat_type": "channel"}],
        )

    def test_rejects_incomplete_button(self):
        with self.assertRaises(ValueError):
            send_message("token", ["@channel"], "message", button_text="보기")

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_sends_article_as_photo(self, post: Mock, _sleep: Mock):
        post.return_value = api_response()
        receipts = send_message(
            "token",
            ["@channel"],
            "caption",
            image_url="https://cdn.example.com/hero.jpg",
            preview_url="https://example.com/article",
        )
        self.assertTrue(post.call_args.args[0].endswith("/sendPhoto"))
        self.assertEqual(
            post.call_args.kwargs["json"]["photo"],
            "https://cdn.example.com/hero.jpg",
        )
        self.assertEqual(receipts[0]["message_id"], 42)
        self.assertEqual(post.call_count, 1)

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_falls_back_to_large_link_preview(self, post: Mock, _sleep: Mock):
        failed = Mock(status_code=400)
        succeeded = api_response()
        post.side_effect = [failed, succeeded]

        receipts = send_message(
            "token",
            ["@channel"],
            "message",
            image_url="https://cdn.example.com/broken.jpg",
            preview_url="https://example.com/article",
        )

        self.assertTrue(post.call_args.args[0].endswith("/sendMessage"))
        options = post.call_args.kwargs["json"]["link_preview_options"]
        self.assertEqual(options["url"], "https://example.com/article")
        self.assertTrue(options["prefer_large_media"])
        self.assertTrue(options["show_above_text"])
        self.assertEqual([receipt["message_id"] for receipt in receipts], [42])
        self.assertEqual(post.call_count, 2)

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_silent_photo_disables_notification(self, post: Mock, _sleep: Mock):
        post.return_value = api_response()
        send_message(
            "token",
            ["@channel"],
            "guide",
            image_url="https://cdn.example.com/guide.jpg",
            silent=True,
        )
        self.assertTrue(post.call_args.kwargs["json"]["disable_notification"])

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_preserves_all_successful_receipts(self, post: Mock, _sleep: Mock):
        post.side_effect = [api_response(42, -100123), api_response(99, -100456)]
        receipts = send_message("token", ["@first", "@second"], "message")
        self.assertEqual([receipt["chat_id"] for receipt in receipts], [-100123, -100456])
        self.assertEqual([receipt["message_id"] for receipt in receipts], [42, 99])
        self.assertEqual(set(receipts[0]), {"chat_id", "message_id", "date", "chat_type"})

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_partial_failure_preserves_prior_success(self, post: Mock, _sleep: Mock):
        post.side_effect = [api_response(), Mock(status_code=403)]
        with self.assertRaises(TelegramSendError) as error:
            send_message("token", ["@first", "@second", "@third"], "message")
        self.assertEqual(error.exception.receipts[0]["message_id"], 42)
        self.assertFalse(error.exception.delivery_uncertain)
        self.assertEqual(post.call_count, 2)

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_partial_uncertain_failure_preserves_prior_success(self, post: Mock, _sleep: Mock):
        post.side_effect = [api_response(), requests.Timeout("secret URL")]
        with self.assertRaises(TelegramSendError) as error:
            send_message("token", ["@first", "@second"], "message")
        self.assertEqual(len(error.exception.receipts), 1)
        self.assertTrue(error.exception.delivery_uncertain)

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_http_success_with_api_error_is_failure(self, post: Mock, _sleep: Mock):
        response = api_response()
        response.json.return_value = {"ok": False, "error_code": 400, "description": "secret-token"}
        post.return_value = response
        with self.assertRaises(TelegramSendError) as error:
            send_message("secret-token", ["@channel"], "message")
        self.assertFalse(error.exception.delivery_uncertain)
        self.assertEqual(error.exception.receipts, [])
        self.assertNotIn("secret-token", str(error.exception))

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_explicit_photo_api_rejection_can_fall_back(self, post: Mock, _sleep: Mock):
        failed = api_response()
        failed.json.return_value = {"ok": False, "error_code": 400, "description": "secret-token"}
        post.side_effect = [failed, api_response()]
        with self.assertLogs("game_ai_news_bot.telegram", level="WARNING") as logs:
            receipts = send_message("secret-token", ["@channel"], "message", image_url="https://example.com/image")
        self.assertEqual(len(receipts), 1)
        self.assertTrue(post.call_args.args[0].endswith("/sendMessage"))
        self.assertNotIn("secret-token", " ".join(logs.output))

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_malformed_success_does_not_resend_photo(self, post: Mock, _sleep: Mock):
        for malformed in (None, [], {"ok": True}, {"ok": True, "result": {}}, {"ok": "true"}):
            with self.subTest(malformed=malformed):
                post.reset_mock()
                response = api_response()
                response.json.return_value = malformed
                post.return_value = response
                with self.assertRaises(TelegramSendError) as error:
                    send_message("token", ["@channel"], "message", image_url="https://example.com/image")
                self.assertTrue(error.exception.delivery_uncertain)
                self.assertEqual(post.call_count, 1)

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_invalid_json_does_not_resend_photo(self, post: Mock, _sleep: Mock):
        response = api_response()
        response.json.side_effect = ValueError("secret-token in response")
        post.return_value = response
        with self.assertRaises(TelegramSendError) as error:
            send_message("secret-token", ["@channel"], "message", image_url="https://example.com/image")
        self.assertTrue(error.exception.delivery_uncertain)
        self.assertEqual(post.call_count, 1)
        self.assertNotIn("secret-token", str(error.exception))

    @patch("game_ai_news_bot.telegram.requests.post")
    def test_network_error_is_safe_and_does_not_retry(self, post: Mock):
        post.side_effect = requests.ConnectionError("https://api.telegram.org/botsecret-token/sendPhoto")
        with self.assertRaises(TelegramSendError) as error:
            send_message("secret-token", ["@channel"], "message", image_url="https://example.com/image")
        rendered_error = "".join(traceback.format_exception(error.exception))
        self.assertNotIn("secret-token", rendered_error)
        self.assertTrue(error.exception.delivery_uncertain)
        self.assertEqual(post.call_count, 1)

    @patch("game_ai_news_bot.telegram.requests.post")
    def test_server_error_does_not_resend_photo(self, post: Mock):
        post.return_value = Mock(status_code=502)
        with self.assertRaises(TelegramSendError) as error:
            send_message("token", ["@channel"], "message", image_url="https://example.com/image")
        self.assertTrue(error.exception.delivery_uncertain)
        self.assertEqual(post.call_count, 1)

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_rate_limit_waits_then_returns_one_receipt(self, post: Mock, sleep: Mock):
        rate_limited = Mock(status_code=429)
        rate_limited.json.return_value = {"ok": False, "parameters": {"retry_after": 2}}
        post.side_effect = [rate_limited, api_response()]
        receipts = send_message("token", ["@channel"], "message")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(sleep.call_args_list[0].args, (3,))
        self.assertEqual(post.call_count, 2)

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_invalid_receipt_fields_are_uncertain(self, post: Mock, _sleep: Mock):
        for field, value in (("message_id", True), ("message_id", 0), ("date", "1788656400")):
            with self.subTest(field=field, value=value):
                response = api_response()
                response.json.return_value["result"][field] = value
                post.return_value = response
                with self.assertRaises(TelegramSendError) as error:
                    send_message("token", ["@channel"], "message")
                self.assertTrue(error.exception.delivery_uncertain)


if __name__ == "__main__":
    unittest.main()
