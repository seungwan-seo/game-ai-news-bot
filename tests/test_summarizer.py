from __future__ import annotations

import unittest
import json
from unittest.mock import Mock, patch

from game_ai_news_bot.models import Article
from game_ai_news_bot.summarizer import (
    fallback_insight,
    fallback_items,
    summarize,
    translate_title_to_korean,
)


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

    @patch("game_ai_news_bot.summarizer.translate_text_to_korean")
    @patch("game_ai_news_bot.summarizer.translate_title_to_korean")
    def test_fallback_translates_useful_excerpt(
        self, title_translate: Mock, text_translate: Mock
    ):
        title_translate.return_value = "게임 상태를 읽는 NPC"
        text_translate.return_value = "NPC가 실시간 게임 상태에 따라 행동을 바꿉니다."
        article = Article(
            "s",
            "Source",
            "NPC reads live game state",
            "https://example.com/a",
            description="The NPC reads live game state and changes behavior during playtests.",
            category="🤖 NPC·에이전트",
        )

        items, _ = fallback_items([article])

        self.assertEqual(items[0].summary_ko, text_translate.return_value)
        self.assertNotIn("확인할 가치", items[0].insight_ko)

    def test_insight_uses_article_specific_signal(self):
        article = Article(
            "s",
            "Source",
            "Open source game agent released",
            "https://example.com/a",
            description="The source code and GitHub repository are available.",
        )
        self.assertIn("공개 코드", fallback_insight(article))

    @patch("game_ai_news_bot.summarizer.requests.post")
    @patch("game_ai_news_bot.summarizer.requests.get")
    def test_geeknews_does_not_call_translation_or_gemini_even_with_key(self, get: Mock, post: Mock):
        article = Article(
            "geeknews", "긱뉴스", "Claude Code와 Codex 코딩 도구 비교", "https://news.hada.io/topic?id=1",
            description="75개 저장소에서 유효 세션 5,292개의 결과를 비교했다.",
            metadata={"editorial_filter": "geeknews"},
        )
        items, _ = summarize([article], api_key="unused-key", translate_titles=True)
        get.assert_not_called()
        post.assert_not_called()
        self.assertEqual(items[0].title_ko, article.title)
        self.assertEqual(items[0].summary_ko, article.description)
        self.assertNotIn("NPC", items[0].insight_ko)

    @patch("game_ai_news_bot.summarizer.requests.post")
    @patch("game_ai_news_bot.summarizer.requests.get")
    def test_mixed_batch_keeps_source_order_and_sends_only_foreign_articles_to_gemini(self, get: Mock, post: Mock):
        english_a = Article("a", "First source", "NPC benchmark published", "https://example.com/a", description="A benchmark evaluates game NPCs.")
        korean = Article(
            "geeknews", "긱뉴스", "Claude Code와 Codex 코딩 도구 비교", "https://news.hada.io/topic?id=2",
            description="75개 저장소에서 코딩 도구의 결과를 비교했다.",
            metadata={"editorial_filter": "geeknews"},
        )
        english_b = Article("b", "Last source", "Game engine AI tools", "https://example.com/b", description="A game engine adds AI development tools.")
        response = Mock()
        response.json.return_value = {"candidates": [{"content": {"parts": [{"text": json.dumps({
            "items": [
                {"id": 0, "title_ko": "NPC 평가 공개", "summary_ko": "평가 자료 소개", "insight_ko": "평가 조건 확인"},
                {"id": 1, "title_ko": "게임 엔진 AI 도구", "summary_ko": "개발 도구 소개", "insight_ko": "지원 범위 확인"},
            ], "trend_ko": "개발 동향",
        }, ensure_ascii=False)}]}}]}
        post.return_value = response
        items, _ = summarize([english_a, korean, english_b], api_key="unused-key")
        self.assertEqual([item.article for item in items], [english_a, korean, english_b])
        self.assertEqual([item.title_ko for item in items], ["NPC 평가 공개", korean.title, "게임 엔진 AI 도구"])
        self.assertEqual(items[1].summary_ko, korean.description)
        post.assert_called_once()
        prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        self.assertNotIn(korean.title, prompt)
        self.assertIn(english_a.title, prompt)
        self.assertIn(english_b.title, prompt)
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
