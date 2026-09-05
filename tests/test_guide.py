from __future__ import annotations

import unittest

from game_ai_news_bot.guide import build_channel_guide_post


class ChannelGuideTests(unittest.TestCase):
    def test_builds_evergreen_guide_with_both_links(self):
        post = build_channel_guide_post(
            {
                "steam_channel_url": "https://t.me/steam_deals_free",
                "turtle_url": "https://store.steampowered.com/app/3952050/Turtle_Game/",
            }
        )
        self.assertIn("게임 AI 개발 뉴스 안내", post)
        self.assertIn("https://t.me/steam_deals_free", post)
        self.assertIn("https://store.steampowered.com/app/3952050/Turtle_Game/", post)
        self.assertNotIn("reviews", post.casefold())
        self.assertNotIn("₩", post)


if __name__ == "__main__":
    unittest.main()
