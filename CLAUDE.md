# CLAUDE.md — krx-signal-alerts

워크스페이스 규칙(`../CLAUDE.md`)을 따르며, 아래는 이 프로젝트 고유 규칙이다.

**작업 시작 전 `docs/SPEC.md` → `docs/PLAN.md` → `docs/DESIGN.md` → `docs/TASKS.md` 순으로 읽는다.**

## 개요

국내 전 종목의 일·주·월봉을 다섯 전략으로 스크리닝해, 매일 아침 08:00 KST
**카카오톡(요약) + 이메일(전체 + 근거값)**로 알린다. 웹 `/signals`에서 이력과 근거를 본다.

- **시세를 수집하지 않는다.** `krx-stock-charts`가 적재한 `ksc_*` 테이블을 **읽기만** 한다.
- 배치 층: `alerts/` (Python + **LangGraph**) → Supabase `ksa_*` (service_role로 쓰기)
- 표현 층: `web/` (Next.js) → Supabase (anon 키로 읽기)
- 두 층이 만나는 지점은 **`ksa_signals` 스키마와 `evidence` 키뿐**이다 (PLAN §4)

### LangGraph 3층 분리 — 이 프로젝트의 핵심 규칙

배치는 LangGraph 상태 그래프 하나로 돈다 (구조: `PLAN.md` §1-1 · 다이어그램: `docs/GRAPH.md`).
**LLM은 없다.** LangGraph는 병렬 fan-out·조건부 분기·오류 격리라는 **배관**만 담당한다.

| 층 | 파일 | 규칙 |
|----|------|------|
| 그래프 | `state.py` · `nodes.py` · `graph.py` | LangGraph를 아는 **유일한** 층 |
| 도메인 | `strategies/` · `rank.py` · `render.py` · `universe.py` · `indicators.py` | **LangGraph를 import하지 않는다.** 순수 함수. 여기가 TDD 대상 |
| I/O | `store.py` · `notify/*` · `main.py` | 부수효과를 아는 유일한 곳 |

- **노드는 20줄을 넘지 않는다** (N11). 넘으면 도메인 로직이 새어 들어온 것이니 도메인 모듈로 옮긴다.
- **테스트는 도메인 함수를 직접 부른다.** 그래프 테스트는 **연결·분기·합류만** 본다.
- **LangGraph를 걷어내도 도메인 코드가 그대로 살아 있어야 한다.**

### Supabase 테이블

| 테이블 | 접두어 | 이 프로젝트의 권한 |
|--------|--------|-------------------|
| `ksc_tickers` · `ksc_bars` · `ksc_meta` | `ksc_` (krx-stock-charts 소유) | **SELECT만. 절대 쓰지 않는다** |
| `ksa_signals` · `ksa_runs` | `ksa_` (이 프로젝트 소유) | 읽기·쓰기 |

스키마 원본은 `supabase/schema.sql` — 재실행해도 안전하다(멱등).

## 실행

```bash
source venv/bin/activate

python -m alerts.main                          # 오늘 기준 스크리닝 + 두 채널 발송
python -m alerts.main --dry-run                # 발송 없이 결과만 출력
python -m alerts.main --channel email          # 한 채널만
python -m alerts.main --date 20260814          # 특정 기준일 재현

python scripts/kakao_auth.py                   # 최초 1회 카카오 인가
python scripts/kakao_auth.py --force           # 동의 화면 강제 (insufficient scopes 시)
python scripts/dryrun.py --days 60             # 과거 60거래일 신호량 리포트
python scripts/export_graph.py                 # 그래프 → docs/GRAPH.md (구조 변경 시 반드시 재실행)
```

## 검증 (태스크·마일스톤 완료 시 전부 통과 필수)

```bash
ruff check .        # 1. 린트
mypy alerts/        # 2. 타입 체크 (strict)
pytest tests/ -v    # 3. 테스트

cd web && npm run lint && npm test && npm run build   # 웹 (M5 이후)
```

## 자격증명

`.env`와 `.tokens.json`은 `.gitignore` 대상 — **절대 커밋 금지**. `.env.example`은 키 이름만 담는다.

| 키 | 용도 |
|----|------|
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | 배치 읽기·쓰기 (RLS 우회). **웹 번들에 절대 넣지 않는다** |
| `SUPABASE_ANON_KEY` | 웹 읽기 전용 |
| `SUPABASE_DATABASE_URL` | 스키마 적용(DDL) 전용 |
| `KAKAO_REST_API_KEY` / `KAKAO_CLIENT_SECRET` / `KAKAO_REDIRECT_URI` | 카카오 나에게 보내기 |
| `KAKAO_REFRESH_TOKEN` | 최초 인가로 발급. 갱신되면 **반드시 저장**한다 (약 2개월) |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | Gmail SMTP (앱 비밀번호 — 계정 비밀번호가 아니다) |
| `RECIPIENTS` | 수신자 쉼표 구분 목록 |

## 이 프로젝트에서 조심할 것

- **LangGraph 병렬 노드는 reducer 없이 상태를 조용히 덮어쓴다** — 전략 5개가 `signals`에 각자 쓰는데
  `Annotated[list[Signal], operator.add]`를 빼먹으면 **마지막 하나만 남고 예외도 안 난다.**
  `tests/test_graph.py`의 합류 테스트가 이걸 잡는 유일한 장치다. 지우지 말 것.
- **발송 노드는 예외를 밖으로 내지 않는다** — 결과를 상태에 적는다. 실패 판정은 `finalize` 한 곳에서만.
  발송 노드가 raise하면 `record_run`에 도달하지 못해 **실패 기록 자체가 사라진다.**
- **체크포인터를 쓰지 않는다** — 단발 배치라 재개가 무의미하고, 상태에 토큰이 섞이면 디스크에 남는다.
- **그래프를 고쳤으면 `scripts/export_graph.py`를 다시 돌린다** — `docs/GRAPH.md`가 낡으면 문서가 거짓말을 한다.
- **Supabase REST는 1000행에서 조용히 잘린다** — `limit(2000)`을 줘도 1000행만 오고 오류가 없다.
  대량 조회는 `range()` 페이지네이션 필수. **완결성 검사를 REST로 하면 오탐**이 난다
  (선행 프로젝트에서 "424개 누락" 오탐, 실제 14개).
- **티커 `.in()`은 쿼리 문자열에 들어간다** — 2,763개를 한 번에 넣으면 URL 19KB로 400. 300개씩 청크.
- **티커는 숫자가 아니다** — `0126Z0`처럼 문자가 섞인 6자리가 실재한다. 검증식 `^[0-9A-Z]{6}$`.
- **진행 중인 주·월봉은 미완성이다** — 주봉 전략(F6)은 금요일, 월봉 전략(F9)은 월말에만 산출한다.
  F8은 매일 산출하되 본문에 `(진행중)`을 표기한다.
- **전략은 "오늘"을 몰라야 한다** — 기준일은 `main`이 주입한다. 그래야 드라이런과 테스트가 성립한다.
- **조건 하나를 지워도 테스트가 통과하면 그 조건은 검증되지 않은 것이다** — 전략마다
  양성 1개 + **조건 수만큼의 음성** 케이스를 둔다.
- **발송은 채널별로 격리한다** — 카카오가 죽어도 메일은 간다. 살아 있는 채널에 실패 경고를 붙인다.
  다만 **하나라도 실패하면 워크플로는 실패**시킨다. 부분 성공을 성공으로 위장하지 않는다.
- **침묵을 정상으로 두지 않는다** — 신호 0건인 날에도 "없음"을 보낸다. 안 그러면 고장을 몇 주간 못 본다.
- **카카오 본문 200자 상한** — 초과 시 자르고 보낸다. 400을 받아 알림이 통째로 사라지는 것보다 낫다.
- **리프레시 토큰은 약 2개월** — 갱신된 토큰을 반드시 저장·Secret 갱신한다. `KOE322`면 재인증.
- **메일 HTML은 이스케이프한다** — 종목명에 `&`가 들어가면 깨진다.
- **`ksc_*` 테이블에 쓰지 않는다** — 상위 프로젝트 소유다.
- **pip/npm은 이 디렉토리(또는 `web/`)에서** — 워크스페이스 루트 오설치 사례 있음.

## 선행 프로젝트

| 프로젝트 | 관계 |
|----------|------|
| `../krx-stock-charts/` | **데이터 공급자.** 읽기만 한다 |
| `../krx-strategy-alerts/` | **참고용 보관.** 카카오 연동을 먼저 뚫어 본 프로젝트 — 오류 4종의 원인·해결이 README에 있다. 코드는 가져오지 않고 처음부터 쓰되, 막히면 이 기록을 본다. 카카오 개발자센터 앱 설정은 재사용된다 |

## 진행 상태

- **SPEC v1.0 확정** (2026-08-17) — D1~D15 전부 확정. `PLAN.md`·`TASKS.md` 작성 완료.
- **M0 착수 대기.** 진도는 `docs/TASKS.md` 대시보드 참조.
- ⚠ 수용된 이슈: anon 키가 같은 Supabase의 다른 테이블 12개를 읽는 문제
  (2026-08-17 사용자 "그대로 두고 진행" — SPEC R4).
