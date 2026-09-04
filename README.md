# game-ai-news-bot

게임 AI 개발 동향을 RSS·연구 API·공식 기술 블로그에서 모아 중요도와 중복을 정리한 뒤, 매일 아침 텔레그램으로 보내는 개인용 오픈소스 봇.

## 무엇을 수집하나

소스는 성격에 따라 우선순위를 다르게 둔다.

- **독립 분석**: AI and Games, Games and AI
- **전문 보도**: Game Developer, Video Games Industry Memo
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
무료 한국어 제목 번역 + 선택적 Gemini 요약
        ↓
텔레그램 모닝 브리핑
```

본문 전체를 무단 복제하지 않는다. RSS가 제공한 제목·설명과 공개 목록의 짧은 문맥만 저장·요약하고 항상 원문 링크를 보낸다.

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

`GEMINI_API_KEY`가 없어도 선택된 영문 제목은 무료 MyMemory API로 번역하며, 텔레그램에는 **한국어 제목과 영문 원제**를 함께 표시한다. 번역 호출이 실패하면 영문 원제로 안전하게 되돌아가므로 발송은 중단되지 않는다. 키를 넣으면 기사 묶음 전체를 한 번만 호출해 한국어 제목·요약·실무 포인트·오늘의 흐름을 만든다.

제목 번역은 [`config.yaml`](config.yaml)의 `translation.enabled`로 끌 수 있다. 번역 대상은 공개된 기사 제목뿐이며 기사 본문이나 Telegram 정보는 번역 서비스로 보내지 않는다.

## 첫 배포

현재 노출된 예전 글을 전부 읽음 처리하고 앞으로 올라오는 글만 받고 싶다면 먼저 실행한다.

```bash
python main.py --bootstrap
```

반대로 첫날부터 최근 4일의 상위 기사 6개를 받고 싶으면 기준점을 만들지 않고 바로 실행한다. 발송에 성공한 경우에만 `state/news_state.json`을 갱신한다.

## GitHub Actions

[`.github/workflows/digest.yml`](.github/workflows/digest.yml)은 매일 **08:23 KST**에 실행된다. 저장소 Secrets에 아래 값을 등록한다.

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY` — 선택

저장소 Variables의 `GEMINI_MODEL`도 선택 사항이다. 상태 파일을 Actions 봇이 커밋하므로 워크플로에 `contents: write`가 필요하다. 저장소를 public으로 운영할 경우 `.env`는 올리지 말고 Secrets만 사용한다.

## 설정 조절

[`config.yaml`](config.yaml)에서 다음을 바꿀 수 있다.

- `max_items`: 하루 기사 수
- `max_items_per_source`: 한 출처가 브리핑을 독점하지 않게 하는 상한
- `freshness_days`: 며칠 이내 글만 후보로 볼지
- `source_weight`: 출처 우선순위
- `min_relevance`: 일반 피드에서 게임 AI 기사로 인정할 최소 점수
- `positive_keywords` / `negative_keywords`: 선별 기준

새 소스는 RSS를 우선한다. RSS가 없을 때만 `kind: html`과 보수적인 `link_pattern`을 추가한다. 사이트 이용약관이나 robots 정책이 수집을 금지하면 해당 소스를 사용하지 않는다.

Ubisoft La Forge도 좋은 원문 소스지만 현재 뉴스 목록이 브라우저에서만 그려져 안정적인 링크를 얻을 수 없어 설정에 비활성 상태로 남겨 두었다. 무거운 브라우저 자동화를 억지로 돌리기보다 RSS나 서버 렌더링 목록이 생길 때 활성화하는 편이 안전하다.

## 주요 명령

```bash
python main.py --dry-run             # 전송과 상태 변경 없이 미리보기
python main.py --dry-run --show-all  # 이미 본 기사도 포함
python main.py --bootstrap           # 현재 기사 기준점 생성
python main.py --no-ai               # 외부 AI 없이 실행
python main.py --verbose             # 상세 수집 로그
```

## 라이선스

봇 코드는 MIT License. 수집 대상 기사의 저작권과 이용약관은 각 원문 사이트에 귀속된다.

소스별 선정 이유와 자동 수집에서 제외한 후보는 [`docs/SOURCES.md`](docs/SOURCES.md)에 정리돼 있다.
