from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

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

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_sends_article_as_photo(self, post: Mock, _sleep: Mock):
        post.return_value.status_code = 200
        send_message(
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

    @patch("game_ai_news_bot.telegram.time.sleep")
    @patch("game_ai_news_bot.telegram.requests.post")
    def test_falls_back_to_large_link_preview(self, post: Mock, _sleep: Mock):
        failed = Mock(status_code=400)
        failed.raise_for_status.side_effect = requests.HTTPError("bad image")
        succeeded = Mock(status_code=200)
        post.side_effect = [failed, succeeded]

        send_message(
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


if __name__ == "__main__":
    unittest.main()
