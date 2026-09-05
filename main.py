from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from game_ai_news_bot.collectors import Collector
from game_ai_news_bot.config import env_settings, load_config
from game_ai_news_bot.digest import build_article_post
from game_ai_news_bot.guide import build_channel_guide_post
from game_ai_news_bot.promotion import (
    build_promotion_post,
    mark_promotion_sent,
    promotion_is_due,
    select_promotion,
)
from game_ai_news_bot.ranking import rank_articles, select_diverse
from game_ai_news_bot.state import (
    delivered_today,
    load_state,
    mark_delivered,
    mark_seen,
    save_state,
)
from game_ai_news_bot.summarizer import summarize
from game_ai_news_bot.telegram import send_message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="게임 AI 뉴스를 선별해 텔레그램 브리핑으로 보냅니다.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="전송·상태 저장 없이 콘솔에 출력")
    parser.add_argument("--show-all", action="store_true", help="이미 본 기사도 후보에 포함")
    parser.add_argument(
        "--preview-send",
        action="store_true",
        help="이미 본 기사도 실제 전송하되 읽음 상태는 변경하지 않음",
    )
    parser.add_argument(
        "--send-promo-now",
        action="store_true",
        help="다음 자매 채널 홍보를 즉시 보내고 홍보 주기를 갱신",
    )
    parser.add_argument(
        "--send-channel-guide",
        action="store_true",
        help="고정용 채널 안내 게시물을 상태 변경 없이 즉시 발송",
    )
    parser.add_argument("--bootstrap", action="store_true", help="현재 기사 전체를 읽음 처리하고 종료")
    parser.add_argument("--no-ai", action="store_true", help="Gemini 키가 있어도 규칙 기반 요약 사용")
    parser.add_argument("--limit", type=int, help="이번 실행의 최대 기사 수")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Windows 기본 CP949 콘솔에서도 이모지·한글 드라이런이 깨지지 않게 한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    env = env_settings()
    digest_config = config.get("digest", {})
    translation_config = config.get("translation", {})
    promotion_config = config.get("promotion", {})
    state_path = Path(config["base_dir"]) / "state" / "news_state.json"
    state = load_state(state_path)
    now = datetime.now(timezone.utc)

    if args.send_channel_guide:
        guide_config = config.get("channel_guide", {})
        guide_message = build_channel_guide_post(guide_config)
        turtle_url = str(guide_config.get("turtle_url", "")).strip()
        image_url = str(guide_config.get("image_url", "")).strip()
        is_dry = args.dry_run or not (
            env["telegram_token"] and env["telegram_chat_ids"]
        )
        if is_dry:
            print("[CHANNEL GUIDE DRY-RUN]\n" + guide_message)
            print(f"[IMAGE] {image_url or '(대표 이미지 없음)'}")
            print(f"[BUTTON] 🐢 Steam에서 거북이 게임 보기 → {turtle_url}")
            return 0
        send_message(
            env["telegram_token"],
            env["telegram_chat_ids"],
            guide_message,
            button_text="🐢 Steam에서 거북이 게임 보기",
            button_url=turtle_url,
            image_url=image_url,
            preview_url=turtle_url,
            silent=True,
        )
        logging.info("고정용 채널 안내 게시물 발송 완료")
        return 0

    if args.send_promo_now:
        promotion = select_promotion(state, promotion_config)
        if promotion is None:
            logging.error("활성화된 자매 채널 홍보 설정이 없습니다.")
            return 2
        promotion_message = build_promotion_post(promotion)
        is_dry = args.dry_run or not (env["telegram_token"] and env["telegram_chat_ids"])
        if is_dry:
            print("[PROMOTION DRY-RUN]\n" + promotion_message)
            print(f'[BUTTON] 🎁 Steam 할인 채널 방문하기 → {promotion["url"]}')
            return 0
        send_message(
            env["telegram_token"],
            env["telegram_chat_ids"],
            promotion_message,
            button_text="🎁 Steam 할인 채널 방문하기",
            button_url=str(promotion["url"]),
        )
        mark_promotion_sent(state, promotion_config)
        save_state(state_path, state)
        logging.info("자매 채널 홍보 발송 완료: %s", promotion.get("name", ""))
        return 0

    collector = Collector(
        config.get("http", {}),
        description_limit=int(digest_config.get("max_description_chars", 900)),
    )
    articles, errors = collector.collect_all(config["sources"])
    if not articles:
        logging.error("모든 소스에서 수집하지 못했습니다: %s", "; ".join(errors))
        return 2

    ranked = rank_articles(articles, config)
    freshness_days = int(digest_config.get("freshness_days", 4))
    cutoff = now - timedelta(days=freshness_days)
    # 미리보기는 게시물 레이아웃 검증이 목적이므로 최신 후보가 요청 수보다
    # 적을 때도 충분히 볼 수 있게 수집된 관련 기사 전체에서 고른다.
    fresh = (
        ranked
        if args.preview_send
        else [
            item
            for item in ranked
            if item.published_at is None or item.published_at >= cutoff
        ]
    )
    if not (args.show_all or args.preview_send):
        fresh = [item for item in fresh if item.url not in state["seen"]]

    if args.bootstrap:
        mark_seen(state, [item.url for item in ranked], now)
        save_state(state_path, state)
        print(f"기준점 생성 완료: {len(ranked)}건을 읽음 처리했습니다.")
        return 0

    per_run_limit = int(
        digest_config.get("max_items_per_run", digest_config.get("max_items", 1))
    )
    limit = args.limit or per_run_limit
    is_live_delivery = not args.dry_run and not args.preview_send and bool(
        env["telegram_token"] and env["telegram_chat_ids"]
    )
    daily_limit = max(1, int(digest_config.get("daily_post_limit", 10)))
    if is_live_delivery:
        remaining_today = daily_limit - delivered_today(state, now)
        if remaining_today <= 0:
            logging.info("오늘의 뉴스 발송 한도 %d건을 이미 채웠습니다.", daily_limit)
            return 0
        limit = min(limit, remaining_today)
    selected = select_diverse(
        fresh,
        limit=max(1, limit),
        max_per_source=int(digest_config.get("max_items_per_source", 2)),
    )
    if not selected:
        logging.info("새로 선별된 게임 AI 소식이 없습니다.")
        return 0

    for article in selected:
        collector.enrich_article(article)

    api_key = "" if args.no_ai else env["gemini_api_key"]
    items, _trend = summarize(
        selected,
        api_key=api_key,
        model=env["gemini_model"],
        translate_titles=bool(translation_config.get("enabled", True)),
        translation_timeout=int(translation_config.get("timeout_seconds", 12)),
    )
    messages = [
        build_article_post(
            item,
            title=digest_config.get("title", "게임 AI 뉴스"),
            timezone_name=digest_config.get("timezone", "Asia/Seoul"),
        )
        for item in items
    ]
    promotion = None
    promotion_message = ""
    if not args.preview_send and promotion_is_due(state, promotion_config, now):
        promotion = select_promotion(state, promotion_config)
        if promotion is not None:
            promotion_message = build_promotion_post(promotion)

    is_dry = args.dry_run or not (env["telegram_token"] and env["telegram_chat_ids"])
    if is_dry:
        for index, (item, message) in enumerate(
            zip(items, messages, strict=True), 1
        ):
            print(f"[DRY-RUN {index}/{len(messages)}]\n{message}\n")
            print(f"[IMAGE] {item.article.image_url or '(대표 이미지 없음)'}")
            print(f"[BUTTON] 🔗 원문 기사 바로 보기 → {item.article.url}\n")
        if promotion_message:
            print("[PROMOTION DRY-RUN]\n" + promotion_message)
            print(f'[BUTTON] 🎁 Steam 할인 채널 방문하기 → {promotion["url"]}')
        if errors:
            print("\n[수집 실패 소스]\n- " + "\n- ".join(errors))
        return 0

    for item, message in zip(items, messages, strict=True):
        send_message(
            env["telegram_token"],
            env["telegram_chat_ids"],
            message,
            button_text="🔗 원문 기사 바로 보기",
            button_url=item.article.url,
            image_url=item.article.image_url,
            preview_url=item.article.url,
        )
        if not args.preview_send:
            # 중간 게시에서 실패해도 이미 성공한 기사가 다음 실행에 중복되지 않게 즉시 기록한다.
            mark_delivered(state, [item.article.url], now)
            save_state(state_path, state)

    if not args.preview_send:
        # 선택하지 않은 좋은 후보는 읽음 처리하지 않고 다음 예약 회차로 넘긴다.
        if promotion is not None:
            send_message(
                env["telegram_token"],
                env["telegram_chat_ids"],
                promotion_message,
                button_text="🎁 Steam 할인 채널 방문하기",
                button_url=str(promotion["url"]),
            )
            mark_promotion_sent(state, promotion_config, now)
            save_state(state_path, state)
    logging.info(
        "%s %d건 발송 완료",
        "미리보기 게시물" if args.preview_send else "뉴스 게시물",
        len(selected),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
