from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import main as app
from game_ai_news_bot.models import Article
from game_ai_news_bot.state import load_state, mark_delivered, save_state


class ProductionDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_path = Path(self.temporary.name) / "state" / "news_state.json"
        self.source = {
            "id": "geeknews", "name": "GeekNews · 긱뉴스",
            "editorial_filter": "geeknews", "max_items_per_day": 2,
        }
        self.config = {
            "base_dir": self.temporary.name,
            "sources": [self.source, {"id": "other", "name": "Other"}],
            "digest": {"daily_post_limit": 10, "max_items_per_run": 1},
            "promotion": {
                "enabled": True, "interval_days": 5,
                "channels": [{"name": "Sister", "url": "https://example.com/promo"}],
            },
        }
        self.env = {
            "telegram_token": "unit-test-placeholder", "telegram_chat_ids": ["unit-test"],
            "gemini_api_key": "", "gemini_model": "unused",
        }
        self.article = Article(
            "geeknews", "GeekNews · 긱뉴스", "Claude Code와 Codex 코딩 도구 비교",
            "https://news.hada.io/topic?id=12345",
            description="두 AI 코딩 도구의 선택 결과를 100회 실험으로 비교한 분석입니다.",
            published_at=datetime.now(timezone.utc), perspective="community",
            metadata={"editorial_filter": "geeknews", "button_text": "📰 긱뉴스에서 읽기"},
        )
        self.original_url = "https://example.com/coding-comparison"

    def execute(self, *args):
        with ExitStack() as stack:
            stack.enter_context(patch("sys.argv", ["main.py", *args]))
            stack.enter_context(patch.object(app, "load_config", return_value=self.config))
            stack.enter_context(patch.object(app, "env_settings", return_value=self.env))
            collector = stack.enter_context(patch.object(app, "Collector")).return_value
            collector.collect_all.return_value = ([self.article], [])

            def enrich(article):
                article.metadata["original_url"] = self.original_url
                return article

            collector.enrich_article.side_effect = enrich
            sender = stack.enter_context(patch.object(app, "send_message"))
            # A test must never make live translation or Telegram requests.
            stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden")))
            output = stack.enter_context(redirect_stdout(io.StringIO()))
            result = app.main()
        return result, sender, collector, output.getvalue()

    def single(self, *args):
        return self.execute("--source", "geeknews", "--article-url", self.article.url, *args)

    def test_specific_article_sends_once_without_promo_and_records_state(self):
        result, sender, collector, _ = self.single("--limit", "10")
        self.assertEqual(result, 0)
        sender.assert_called_once()
        collector.collect_all.assert_called_once_with([self.source])
        message = sender.call_args.args[2]
        for marker in ("테스트 메시지", "테스트 발송", "DRY-RUN", "미리보기", "Sister"):
            self.assertNotIn(marker, message)
        self.assertIn(self.article.title, message)
        self.assertEqual(sender.call_args.kwargs["button_text"], "📰 긱뉴스에서 읽기")
        self.assertTrue(sender.call_args.kwargs["silent"])
        state = load_state(self.state_path)
        self.assertEqual(state["delivery_count"], 1)
        self.assertEqual(state["delivery_source_counts"], {"geeknews": 1})
        self.assertIn(self.article.url, state["seen"])
        self.assertIn(self.original_url, state["seen"])
        self.assertFalse(state["last_promo_at"])
        result, sender, _, _ = self.single()
        self.assertEqual(result, 2)
        sender.assert_not_called()

    def test_previously_sent_original_is_detected_after_enrichment(self):
        state = load_state(self.state_path)
        mark_delivered(state, [self.original_url], source_id="other")
        save_state(self.state_path, state)
        result, sender, collector, _ = self.single()
        self.assertEqual(result, 2)
        collector.enrich_article.assert_called_once()
        sender.assert_not_called()

    def test_dry_run_and_legacy_preview_never_send_or_write(self):
        for args in (
            ("--source", "geeknews", "--dry-run", "--no-promo"),
            ("--source", "geeknews", "--preview-send"),
            ("--source", "geeknews", "--bootstrap", "--dry-run"),
        ):
            with self.subTest(args=args):
                result, sender, _, output = self.execute(*args)
                self.assertEqual(result, 0)
                sender.assert_not_called()
                self.assertIn("DRY-RUN", output)
                self.assertFalse(self.state_path.exists())

    def test_unlisted_article_url_cannot_be_published(self):
        result, sender, collector, _ = self.execute(
            "--source", "geeknews", "--article-url", "https://example.com/arbitrary",
        )
        self.assertEqual(result, 2)
        sender.assert_not_called()
        collector.enrich_article.assert_not_called()

    def test_source_and_total_daily_caps_apply_across_runs(self):
        for count, source_id in ((2, "geeknews"), (10, "other")):
            with self.subTest(count=count, source_id=source_id):
                state = load_state(Path(self.temporary.name) / "missing.json")
                mark_delivered(state, [f"https://example.com/{i}" for i in range(count)], source_id=source_id)
                save_state(self.state_path, state)
                result, sender, _, _ = self.single()
                self.assertEqual(result, 2)
                sender.assert_not_called()

    def test_conflicting_single_article_flags_are_rejected(self):
        for flag in ("--bootstrap", "--send-promo-now", "--send-channel-guide", "--preview-send", "--show-all"):
            with self.subTest(flag=flag), patch("sys.argv", [
                "main.py", "--source", "geeknews", "--article-url", self.article.url, flag,
            ]), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                app.parse_args()
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
