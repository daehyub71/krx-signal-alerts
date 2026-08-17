# TASKS.md — krx-signal-alerts

> 기준: `SPEC.md` v1.1 · `PLAN.md` (2026-08-17, LangGraph 반영)
> 체크할 때마다 아래 대시보드를 함께 갱신한다.

---

## 진도율 대시보드

| 마일스톤 | 진도 | % | 태스크 | 상태 |
|----------|------|---|--------|------|
| M0 뼈대 + 걷는 해골 | `██████████` | 100% | 10/10 | ✅ 2026-08-17 |
| M1 데이터 계층 | `███░░░░░░░` | 25% | 2/8 | 🔄 |
| M2 전략 5개 | `░░░░░░░░░░` | 0% | 0/14 | 🔜 |
| M3 발송 | `░░░░░░░░░░` | 0% | 0/10 | 🔜 |
| M4 자동화 | `░░░░░░░░░░` | 0% | 0/7 | 🔜 |
| M5 웹 /signals | `░░░░░░░░░░` | 0% | 0/9 | 🔜 |
| M6 마무리 | `░░░░░░░░░░` | 0% | 0/6 | 🔜 |
| **전체** | `██░░░░░░░░` | **19%** | **12/64** | 🔄 |

범례: 🔜 대기 · 🔄 진행중 · ✅완료일

---

## M0 — 뼈대 + 걷는 해골

> **그래프를 먼저 세우고 노드를 나중에 채운다.** 노드를 다 만든 뒤 조립하면
> reducer·조건부 엣지·병렬 합류가 한꺼번에 터진다 (PLAN §5 M0)

- [x] venv 생성 · `requirements.txt`(**langgraph** · supabase) · `requirements-dev.txt`(ruff·mypy·pytest)
- [x] `pyproject.toml` — ruff 설정 + mypy strict
- [x] `.gitignore` — `.env` · `.tokens.json` · `venv/` · `__pycache__` · `.DS_Store`
- [x] `.env.example` — 시크릿 **키 이름만** (값 금지)
- [x] `alerts/config.py`(표준 라이브러리 로더, **기존 환경변수 덮어쓰지 않음** — CI 우선) · `alerts/models.py`
- [x] `alerts/state.py` — `AlertState` TypedDict + **`signals` reducer(`operator.add`)** + `results` merge reducer
- [x] `alerts/nodes.py` — 노드 전부를 **빈 통과 함수**로 (PLAN §1-1 구조 그대로)
- [x] `alerts/graph.py` — `build_graph()`: 노드·엣지·`check_freshness` 조건부 분기·`RetryPolicy`
- [x] `alerts/main.py` — 인자 파싱 → 초기 상태 → `graph.invoke()`. `--dry-run` 완주 확인
- [x] `scripts/export_graph.py` → `docs/GRAPH.md` (N12) · `git init` + 최초 커밋

**완료 기준 — 전부 충족 (2026-08-17)**
- `ruff check .` · `mypy` · `pytest` 전부 통과 (**테스트 28개**)
- 빈 그래프가 START→END 완주 (`python -m alerts.main --dry-run` → `status=ok`, exit 0)
- 분기 양쪽 경로 · **리듀서 5개 합류** · 발송 실패 격리 전부 테스트로 확인
- `docs/GRAPH.md`에 mermaid 다이어그램 생성됨 (노드 16 + START/END)

**M0에서 확정한 것**

| 항목 | 내용 |
|------|------|
| LangGraph 버전 | **1.2.11** (PLAN 작성 시 가정한 0.2 계열이 아니다). `StateGraph`·`add_conditional_edges`·`RetryPolicy` API는 그대로 호환 |
| 프레임워크 경계 | `add_node` 오버로드가 평범한 `Callable`을 strict 모드에서 거부한다. `graph.pick()`의 반환형만 `Any`로 완화하고 나머지는 strict 유지 |
| 테스트 주입구 | `build_graph(overrides)` — 노드를 스텁으로 갈아끼워 **배선만** 검사한다 (N11) |
| 예외 이름 | `AlertRunFailed` → **`AlertRunError`** (ruff N818) |

---

## M1 — 데이터 계층

- [x] `supabase/schema.sql` 작성 (`ksa_signals` · `ksa_runs` · RLS, 멱등)
- [x] 스키마 적용 (`scripts/apply_schema.py` — psycopg + `SUPABASE_DATABASE_URL`) ✅ 2026-08-17
      · 재적용 멱등 확인 · service_role upsert 성공 · **anon 쓰기 RLS 차단 확인** · CHECK 3종 동작
- [ ] `alerts/store.py` — 읽기(`range()` 페이지네이션 · 티커 300청크) / 쓰기(upsert)
- [ ] `alerts/indicators.py` — `ma` · `bollinger` · `percentile` (**테스트 먼저**)
- [ ] `alerts/universe.py` — F1 필터 (스팩 · 우선주 · 유동성 미달)
- [ ] **유니버스 건수를 SQL 직접 카운트와 대조** (REST로 세지 않는다 — R6)
- [ ] `load_meta` · `check_freshness` · `build_universe` · `load_bars` 노드에 실구현 연결
- [ ] 전 종목 조회 **소요 시간 + `bars` 상태 메모리** 측정 → 아래 「측정 기록」에 기입 (R7 · PLAN §1-2)

**완료 기준**: 절단 없는 조회 확인 · 제외 사유별 건수 로그 · 검증 3종 통과

---

## M2 — 전략 5개 ★ TDD 핵심

> 순서: 쉬운 것부터. **VCP를 마지막에** 붙인다 (PLAN §7 — 가장 깨지기 쉽다)

- [ ] `strategies/base.py` — Strategy 프로토콜 · 실행 주기 판정(매일/금요일/월말)
- [ ] F5 MTF 정배열 — 테스트(양성 1 + 조건별 음성) → 구현
- [ ] F8 밴드 스퀴즈 — 테스트 → 구현
- [ ] F6 주봉 눌림목 — 테스트 → 구현
- [ ] F9 장기 턴어라운드 — 테스트 → 구현 (R1: 횡보 6개월 고정)
- [ ] F7 VCP 수축 — 테스트 → 구현
- [ ] 전략 노드 5개를 그래프에 fan-out 연결 (엣지 `load_bars → 각 전략 → suppress`)
- [ ] **reducer 합류 테스트** — 노드 5개를 stub으로 두고 신호가 **전부** 모이는지 확인
      (`operator.add`를 빼먹으면 마지막 하나만 남고 **예외도 안 난다** — PLAN §6)
- [ ] `alerts/rank.py` F10 중복 억제 — 경계일(9/10/11일) 테스트 포함
- [ ] `alerts/rank.py` F11 랭킹 — 전략 내 백분위 정규화 · 전략별 최소 1건 보장
- [ ] `scripts/dryrun.py` — 과거 N거래일 재현 (발송 없음)
- [ ] **최근 60거래일 드라이런 → 전략별 일평균 신호량 리포트** (아래 기록)
- [ ] 신호량 극단 시 임계값 조정 + **SPEC §4-2에 변경 일자·사유·실측 근거 기록** (R8)
- [ ] 표본 3종목 손계산 대조

**완료 기준**: 전략별 양성·음성 테스트 통과 · 드라이런 신호량 합리적 · 검증 3종 통과

---

## M3 — 발송

- [ ] `alerts/render.py` — 카카오 요약 본문 (테스트 먼저: **200자 경계** · 0건 문구)
- [ ] `alerts/render.py` — 메일 HTML + 평문 대체본 (테스트: 근거값 전개 · **HTML 이스케이프**)
- [ ] `notify/base.py` — Channel 프로토콜 (N9)
- [ ] `notify/kakao.py` — 발송 + 토큰 갱신 + `KOE322` 시 명시적 실패
- [ ] `notify/email.py` — Gmail SMTP(587 STARTTLS) + 앱 비밀번호
- [ ] `scripts/kakao_auth.py` — 최초 인가 (`--force` 지원)
- [ ] F13c — 발송 노드 2개를 병렬로 연결. **두 노드 모두 예외를 밖으로 내지 않는다** (결과를 상태에 적는다)
- [ ] `record_run` → `finalize` 노드 — 기록을 먼저 하고 **실패 판정은 `finalize` 한 곳에서만** (N5)
- [ ] **실발송 확인** — 카카오 도착 · 메일이 **받은편지함**에 도착 (R11)
- [ ] **한 채널을 일부러 실패시켜** 다른 채널 도착 + 경고 부착 + `record_run` 도달 확인

**완료 기준**: 위 2건의 실확인 · `ksa_runs`에 채널별 결과 기록 · 검증 3종 통과

---

## M4 — 자동화

- [ ] `alerts/main.py` CLI — `--date` · `--channel kakao|email|both` · `--dry-run`
- [ ] F3 데이터 신선도 검사 (기준일 불일치 시 발송 중단·실패)
- [ ] `.github/workflows/alert.yml` — cron `0 23 * * 0-4` + `workflow_dispatch`
- [ ] GitHub Secrets 등록 (Supabase · 카카오 · Gmail 앱 비밀번호)
- [ ] **리프레시 토큰 Secret 자동 갱신** (R2) — 권한 방식 결정 후 구현
- [ ] 워크플로 권한 최소화(`permissions:` 명시) · 로그 시크릿 미노출 확인
- [ ] 신선도 검사 실동작 시험 (기준일 조작)

**완료 기준**: 수동 실행 성공 → **연속 5거래일 두 채널 도착** (0건인 날 "없음" 포함)

---

## M5 — 웹 `/signals`

> ⚠ **`docs/DESIGN.md` 시안 사용자 합의 전에는 화면 구현을 시작하지 않는다** (SPEC N8)

- [ ] DESIGN.md §5 UI 시안(HTML 목업) 작성 → **사용자 합의**
- [ ] Next.js 16 + TS(strict) + Tailwind 초기화 (`web/`에서 npm 실행 — 루트 오설치 주의)
- [ ] Supabase 읽기 클라이언트 (anon 키)
- [ ] F15 신호 목록 — 전략별 그룹 · 필터 · 정렬
- [ ] F16 신호 상세 — `evidence.conditions` 렌더
- [ ] F17 이력 조회 — 과거 날짜
- [ ] Vitest 컴포넌트 테스트
- [ ] Vercel 배포
- [ ] 카카오·메일 본문의 웹 링크를 실 URL로 교체

**완료 기준**: `npm run lint` · `npm test` · `npm run build` 통과 · 배포 URL 실동작

---

## M6 — 마무리

- [ ] 보안 점검 (N7) — 보안 리뷰 · 시크릿 노출 · CI 권한/아티팩트
- [ ] `docs/GRAPH.md` 최종 갱신 (`scripts/export_graph.py` 재실행 — N12)
- [ ] `CLAUDE.md` 최종 갱신 (겪은 함정 기록)
- [ ] `README.md` (영어) · `README_KO.md` (한국어) + 상호 링크
- [ ] 워크스페이스 `../CLAUDE.md` 프로젝트 목록 표에 추가
- [ ] 운영 기록 — 첫 2주 도착 여부 점검

---

## 측정 기록

> 실측값을 여기에 남긴다. 추정으로 판단하지 않기 위해서다.

| 항목 | 값 | 측정일 |
|------|-----|--------|
| 유니버스 건수 (제외 후) | — | — |
| 제외: 스팩 / 우선주 / 유동성 미달 | — / — / — | — |
| 전 종목 봉 조회 소요 | — | — |
| `bars` 상태 메모리 (PLAN §1-2 추정 200~400MB) | — | — |
| 배치 전체 소요 | — | — |
| 드라이런 일평균 신호량 (MTF/눌림목/VCP/스퀴즈/턴어라운드) | — | — |

---

## 트러블슈팅 기록

> 겪은 오류와 원인을 남긴다. 같은 함정을 두 번 밟지 않기 위해서다.

| 일자 | 증상 | 원인 | 해결 |
|------|------|------|------|
| 2026-08-17 | `ksc_bars`를 `count="exact"`로 세면 `57014 statement timeout` | 240만 행 전수 스캔. Supabase 기본 statement timeout을 넘긴다 | **`ksc_bars`에 exact count를 쓰지 않는다.** 완결성 검사는 psycopg로 SQL 집계 |
| 2026-08-17 | `ksc_meta.update`가 `tickers: 200`인데 유니버스는 2,763 | 종목 확장 이전 실행 기록이 남아 있다. 메타는 **마지막 실행이 무엇을 했는지**를 적을 뿐 데이터 최신 여부를 보증하지 않는다 | **F3을 `ksc_bars.max(d)` 기준으로 바꿨다** (SPEC v1.1.1). 표본 12종목 확인 결과 실제 데이터는 전부 2026-08-14로 최신 |
| 2026-08-17 | `mypy --strict`에서 `add_node` 오버로드 불일치 | LangGraph의 `_Node` 제네릭이 평범한 `Callable[[AlertState], Any]`를 못 받는다 | `graph.pick()` 반환형만 `Any`. 프레임워크 경계에서만 완화 |

### 미리 알고 있는 함정 (선행 프로젝트에서 확인됨)

| 함정 | 출처 |
|------|------|
| Supabase REST는 **1000행에서 오류 없이 잘린다**. 완결성 검사는 SQL로 | krx-stock-charts (오탐 "424개 누락" 실제 14개) |
| 티커 `.in()` 필터가 URL에 실린다. 2,763개 = 19KB → **400**. 300개씩 청크 | 동상 |
| 티커는 숫자가 아니다 — `0126Z0` 실재. `^[0-9A-Z]{6}$` | 동상 |
| 카카오 `KOE004`(로그인 비활성) → `KOE205`(동의항목) → `KOE006`(리다이렉트 URI는 **앱 설정 > 플랫폼 키 > REST API 키**에 등록) → `insufficient scopes`(`--force`로 재동의) | krx-strategy-alerts |
| macOS Python.org 설치본은 **CA 인증서가 없다**. `Install Certificates.command` 1회 실행 | 동상 |
| pip/npm은 **반드시 프로젝트 루트에서** (워크스페이스 루트 오설치 사례 있음) | 워크스페이스 CLAUDE.md |
| LangGraph 병렬 노드가 같은 상태 키를 쓰면 **reducer 없이는 조용히 덮어쓴다**. 예외가 안 나서 못 알아챈다 | PLAN §6 — 전용 테스트로 방어 |

---

## 미해소 이슈

| ID | 내용 | 상태 |
|----|------|------|
| ① | ~~anon 키가 다른 테이블 12개를 **읽는다**~~ → **실측 결과 더 심각.** 2026-08-17 권한을 직접 조회한 결과, RLS가 꺼진 테이블 **27개**에 anon이 `SELECT`뿐 아니라 **`INSERT`·`UPDATE`·`DELETE`·`TRUNCATE`** 권한을 갖는다 (`stocks`, `nq_questions`, `libraries`, `translations`, `shareholder_data_anal` 등). 배포된 웹의 anon 키는 공개돼 있다 | ⚠ **사용자 판단 필요.** 기존 수용(SPEC R4)은 "읽기"를 전제한 것이었다. **이 프로젝트의 `ksa_*`는 안전하다** — RLS on + SELECT 정책만이라 anon 쓰기가 실제로 차단되는 것을 확인했다. 노출을 늘리지는 않았으나, 27개 테이블의 쓰기 노출은 이 프로젝트 밖의 별건 |
| ② | Supabase 무료 한도 500MB 중 385MB 사용 (여유 115MB) | 인지. `ksa_*`는 연 수 MB로 영향 작음 (SPEC R9) |
| ③ | 월봉 3년(37개) → F9 판정 창 19개월, 신호가 드물다 | **의도된 선택** (D3). 월봉만 10년 확대로 언제든 해소 가능 (SPEC R1) |
