from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from game_ai_news_bot.telegram import send_message


class TelegramTests(unittest.TestCase):
    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_sends_visible_url_button(self, post: Mock, _sleep: Mock):
        post.return_value.status_code = 200
        send_message(
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

    def test_rejects_incomplete_button(self):
        with self.assertRaises(ValueError):
            send_message("token", ["@channel"], "message", button_text="보기")


if __name__ == "__main__":
    unittest.main()
