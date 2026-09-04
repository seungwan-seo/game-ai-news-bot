from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from game_ai_news_bot.models import Article
from game_ai_news_bot.summarizer import fallback_items, translate_title_to_korean


class TitleTranslationTests(unittest.TestCase):
    @patch("game_ai_news_bot.summarizer.requests.get")
    def test_translates_english_title(self, mock_get: Mock):
        response = Mock()
        response.json.return_value = {
            "responseStatus": 200,
            "responseData": {"translatedText": "AI NPC는 플레이어를 기억할 수 있다"},
        }
        mock_get.return_value = response

        translated = translate_title_to_korean("AI NPCs can remember players | 02/09/26")

        self.assertEqual(translated, "AI NPC는 플레이어를 기억할 수 있다")
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(mock_get.call_args.kwargs["params"]["langpair"], "en|ko")
        self.assertEqual(mock_get.call_args.kwargs["params"]["q"], "AI NPCs can remember players")

    @patch("game_ai_news_bot.summarizer.requests.get")
    def test_skips_already_korean_title(self, mock_get: Mock):
        translated = translate_title_to_korean("게임 AI 연구 공개")

        self.assertEqual(translated, "게임 AI 연구 공개")
        mock_get.assert_not_called()

    @patch("game_ai_news_bot.summarizer.translate_title_to_korean")
    def test_translation_failure_keeps_original(self, mock_translate: Mock):
        mock_translate.side_effect = TimeoutError("timeout")
        article = Article("s", "Source", "Original title", "https://example.com/a")

        with self.assertLogs("game_ai_news_bot.summarizer", level="WARNING"):
            items, _ = fallback_items([article])

        self.assertEqual(items[0].title_ko, "Original title")


if __name__ == "__main__":
    unittest.main()
