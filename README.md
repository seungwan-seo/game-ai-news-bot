# game-ai-news-bot

게임 AI 개발 동향을 RSS·연구 API·공식 기술 블로그에서 모아 중요도와 중복을 정리한 뒤, 하루 동안 간격을 두고 텔레그램에 기사별로 게시하는 오픈소스 봇.

## 무엇을 수집하나

소스는 성격에 따라 우선순위를 다르게 둔다.

- **독립 분석**: AI and Games, Games and AI
- **전문 보도**: Game Developer, Video Games Industry Memo
- **한국어 큐레이션**: GeekNews — 게임 AI와 제작에 활용할 AI 개발 도구만 하루 최대 2건
- **연구·기술 원문**: Microsoft Research Game Intelligence, KRAFTON AI, Google DeepMind
- **엔진·런타임**: NVIDIA Developer, Inworld, Unreal Engine
- **논문**: arXiv의 게임 AI·NPC·게임 에이전트·절차 생성 관련 최신 논문

회사 블로그는 빠르고 구체적인 대신 홍보 관점이 강하다. 따라서 독립 분석과 전문 보도의 가중치를 높이고, `crypto`·`web3`·`NFT` 등 게임 AI와 무관한 홍보성 글은 감점한다.

## 동작 흐름

```text
RSS / HTML 목록 / arXiv
        ↓
게임 AI 키워드 관련성 점수
        ↓
URL·유사 제목 중복 제거
        ↓
출처 신뢰도 + 최신성으로 순위 결정
        ↓
선택된 원문의 대표 이미지·짧은 공개 문맥 보강
        ↓
무료 한국어 제목 번역 + 선택적 Gemini 요약
        ↓
대표 이미지가 붙은 텔레그램 기사별 게시물
```

본문 전체를 무단 복제하지 않는다. RSS가 제공한 제목·설명과 원문 페이지가 공개한 짧은 문맥만 저장·요약하고 항상 원문 링크를 보낸다.

### GeekNews 선별

[공식 RSS](https://news.hada.io/rss/news)의 제목·짧은 소개를 읽고 게임 AI, AI 코딩 도구, 에셋·음성 생성, 추론 비용·지연처럼 제작 실무에 연결되는 글만 선별한다. 비교·평가·수치·사용 방법 언급을 가점으로 쓰며, 일반 투자·잡담·하드웨어 글은 제외한다. 긱뉴스라는 이유만으로 통과시키거나 추천 수를 추정하지 않는다.

한국어 제목은 재번역하거나 영문 제목을 만들어 붙이지 않는다. 소개는 최대 180자의 짧은 발췌로 제한하고, 제목 링크와 `📰 긱뉴스에서 읽기` 버튼으로 연결한다. 긴 요약 전문·댓글은 복제하지 않는다. 공개 상세 페이지에서 확인된 원문 주소는 중복 제거에 함께 쓰지만, 403 등으로 확인하지 못한 한·영 기사 사이의 중복까지 보장하지는 않는다. 이미지도 확인된 경우에만 붙이며, 없으면 링크 미리보기로 요청한다.

하루 최대 10건 중 긱뉴스는 최대 2건이다. 소스별 발송 횟수를 한국 시간 기준으로 저장하므로 여러 예약 회차에 걸쳐서도 상한을 지킨다.

## 로컬 실행

Python 3.11 이상을 권장한다.

```bash
python -m venv .venv
.venv/Scripts/activate       # Windows
pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py --dry-run --show-all --limit 6
```

Linux/macOS에서는 활성화 명령만 `source .venv/bin/activate`로 바꾼다.

## 텔레그램 연결

1. `@BotFather`에서 봇을 만들고 토큰을 받는다.
2. 개인 알림이면 봇에게 메시지를 하나 보낸다. 채널이면 봇을 게시 권한이 있는 관리자로 추가한다.
3. `.env.example`을 `.env`로 복사해 값을 입력한다.
4. 개인 `chat_id`가 필요하면 `python get_chat_id.py`를 실행한다.
5. `python main.py --dry-run`으로 확인한 뒤 `python main.py`로 실제 전송한다.

```dotenv
TELEGRAM_TOKEN=123456:example
TELEGRAM_CHAT_ID=123456789
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

`GEMINI_API_KEY`가 없어도 선택된 영문 제목과 공개된 짧은 발췌를 무료 MyMemory API로 번역하고, 기사 내용에 맞춘 `왜 봐야 하나`를 붙인다. 텔레그램에는 **뉴스 1개당 게시물 1개**로 한국어 제목과 영문 원제를 함께 표시한다. 상단 한국어 제목 전체가 원문 링크이고 게시물 아래에도 큰 `원문 기사 바로 보기` 버튼을 붙인다. 번역 호출이 실패하면 영문 원제로 안전하게 되돌아가므로 발송은 중단되지 않는다. 키를 넣으면 기사 묶음 전체를 한 번만 호출해 한국어 제목·요약·실무 포인트를 만든다.

대표 이미지는 임의로 만든 커버가 아니라 기사가 제공한 RSS 미디어, 원문 페이지의 `og:image`·Twitter 카드, 본문 이미지 순서로 찾는다. 이미지가 있으면 사진 게시물로 전송하며, Telegram이 원격 이미지를 받지 못하면 원문 링크의 큰 미리보기 카드가 붙은 텍스트 게시물로 자동 대체한다.

제목·발췌 번역은 [`config.yaml`](config.yaml)의 `translation.enabled`로 끌 수 있다. 번역 대상은 공개된 기사 제목과 요약에 쓸 짧은 공개 발췌뿐이며 기사 본문 전체나 Telegram 정보는 번역 서비스로 보내지 않는다.

## 자매 채널 교차 홍보

정상 뉴스가 올라오는 날을 기준으로 5일에 한 번 `@steam_deals_free`를 별도 게시물로 소개한다. 뉴스가 없는 날에는 광고만 단독으로 올리지 않는다. 홍보 성공 시각과 다음 채널 순번은 `state/news_state.json`에 기록하므로 재실행해도 중복되지 않는다.

향후 채널이 늘어나면 [`config.yaml`](config.yaml)의 `promotion.channels`에 이름·링크·설명을 추가한다. 봇은 목록을 순환하므로 특정 채널만 반복 노출되지 않는다.

GitHub Actions의 `Run workflow`에서 `다음 자매 채널 홍보만 즉시 발송`을 체크하면 뉴스 수집 없이 홍보 1건만 바로 보낼 수 있다.
`콘솔 미리보기만 출력`을 체크하면 텔레그램에 보내지 않고 Actions 로그에서 내용을 확인한다. `긱뉴스 피드의 특정 기사 URL 1건 게시`에 피드에 있는 주소를 입력하면 정상 운영용 기사 1건만 무음으로 게시하고 읽음 기록·하루 한도에 반영한다. 이미 보낸 기사, 부적합한 기사, 한도를 초과한 기사는 보내지 않으며 광고도 함께 보내지 않는다.
`고정용 채널 안내를 상태 변경 없이 즉시 발송`은 채널 소개, 자매 채널, 운영자의 Turtle Game을 한 게시물로 조용히 전송한다. 가격·리뷰 수치를 넣지 않은 공지용 문구라 발송 후 Telegram에서 고정해 두면 된다.

## 첫 배포

현재 노출된 예전 글을 전부 읽음 처리하고 앞으로 올라오는 글만 받고 싶다면 먼저 실행한다.

```bash
python main.py --bootstrap
```

반대로 기존 후보도 받고 싶으면 기준점을 만들지 않고 바로 실행한다. 발송에 성공한 기사만 `state/news_state.json`에 기록되며, 이번 회차에 선택되지 않은 후보는 다음 회차로 넘어간다.

## GitHub Actions

[`.github/workflows/digest.yml`](.github/workflows/digest.yml)은 매일 **08:23~21:53 KST 사이에 90분 간격으로 10회** 실행된다.

`08:23 · 09:53 · 11:23 · 12:53 · 14:23 · 15:53 · 17:23 · 18:53 · 20:23 · 21:53`

각 회차는 관련도 높은 새 기사 1개만 보내므로 하루 최대 10개다. 적합한 새 기사가 없으면 해당 회차는 아무것도 보내지 않는다. 저장소 Secrets에 아래 값을 등록한다.

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY` — 선택

저장소 Variables의 `GEMINI_MODEL`도 선택 사항이다. 상태 파일을 Actions 봇이 커밋하므로 워크플로에 `contents: write`가 필요하다. 저장소를 public으로 운영할 경우 `.env`는 올리지 말고 Secrets만 사용한다.

## 설정 조절

[`config.yaml`](config.yaml)에서 다음을 바꿀 수 있다.

- `daily_post_limit`: 한국 시간 기준 하루 최대 뉴스 게시물 수
- `max_items_per_run`: 예약 실행 1회당 최대 기사 수
- `max_items_per_source`: 한 출처가 브리핑을 독점하지 않게 하는 상한
- `freshness_days`: 며칠 이내 글만 후보로 볼지
- `source_weight`: 출처 우선순위
- 소스의 `max_items_per_day`: 여러 회차에 걸친 한국 시간 기준 출처별 하루 상한
- `min_relevance`: 일반 피드에서 게임 AI 기사로 인정할 최소 점수
- `positive_keywords` / `negative_keywords`: 선별 기준

새 소스는 RSS를 우선한다. RSS가 없을 때만 `kind: html`과 보수적인 `link_pattern`을 추가한다. 사이트 이용약관이나 robots 정책이 수집을 금지하면 해당 소스를 사용하지 않는다.

Ubisoft La Forge도 좋은 원문 소스지만 현재 뉴스 목록이 브라우저에서만 그려져 안정적인 링크를 얻을 수 없어 설정에 비활성 상태로 남겨 두었다. 무거운 브라우저 자동화를 억지로 돌리기보다 RSS나 서버 렌더링 목록이 생길 때 활성화하는 편이 안전하다.

## 주요 명령

운영 채널에는 테스트·미리보기 안내 문구를 넣지 않는다. 검토는 기본적으로 아래 `--dry-run` 결과를 현재 대화에 보여주는 방식으로 한다. 실제 채널 검증 발송은 사용자가 요청한 건수만 정상 게시 형식으로 수행한다. 예전 `--preview-send` 옵션은 이제 **전송 없는 미리보기 별칭**이다.

```bash
python main.py --dry-run             # 전송과 상태 변경 없이 미리보기
python main.py --dry-run --show-all  # 이미 본 기사도 포함
python main.py --source geeknews --dry-run --no-promo --limit 2
# 아래 명령은 실제 발송: 사용자가 요청한 운영 게시에만 사용
python main.py --source geeknews --article-url "https://news.hada.io/topic?id=기사번호" --no-promo
python main.py --send-promo-now          # 다음 자매 채널 홍보를 즉시 발송
python main.py --send-channel-guide      # 고정용 채널 안내를 무음으로 즉시 발송
python main.py --bootstrap           # 현재 기사 기준점 생성
python main.py --no-ai               # 외부 AI 없이 실행
python main.py --verbose             # 상세 수집 로그
```

## 라이선스

봇 코드는 MIT License. 수집 대상 기사의 저작권과 이용약관은 각 원문 사이트에 귀속된다.

소스별 선정 이유와 자동 수집에서 제외한 후보는 [`docs/SOURCES.md`](docs/SOURCES.md)에 정리돼 있다.
