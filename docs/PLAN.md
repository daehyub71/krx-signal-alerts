# PLAN.md — krx-signal-alerts

> 기준 문서: `SPEC.md` v1.1 (2026-08-17). SPEC과 어긋나면 SPEC이 기준이다.
> 작성 2026-08-17 · LangGraph 반영 2026-08-17.

---

## 1. 아키텍처

```
┌─ krx-stock-charts (별도 프로젝트) ─────────────────┐
│  평일 18:00 KST · pykrx → ksc_tickers / ksc_bars   │   ← 읽기만 한다. 수정하지 않는다
└────────────────────────┬───────────────────────────┘
                         │ SELECT (service_role)
┌────────────────────────▼───────────────────────────┐
│  krx-signal-alerts · 평일 08:00 KST · GitHub Actions│
│  LangGraph 상태 그래프 1개 (§1-1)                    │
│                                              │      │
│                                    ┌─────────▼────┐ │
│                                    │  ksa_signals │ │
│                                    │  ksa_runs    │ │
│                                    └─────────┬────┘ │
│                            notify ◀──────────┘      │
│                         ┌────┴────┐                 │
│                    kakao(F13)  email(F13b)          │
│                    상위 10건     전체+근거값         │
└─────────────────────────────────────────────────────┘
                         │ SELECT (anon)
┌────────────────────────▼───────────────────────────┐
│  web/ · Next.js · Vercel · /signals (F15~F17)      │
└─────────────────────────────────────────────────────┘
```

**두 층이 만나는 지점은 `ksa_signals` 스키마 하나뿐이다.** 배치는 파이썬, 웹은 TypeScript로
서로의 코드를 모른다. `evidence`(jsonb)의 키 이름이 사실상의 계약이므로 §4에서 고정한다.

### 1-1. LangGraph 그래프 (D16)

```
                          START
                            │
                     ┌──────▼───────┐
                     │  load_meta   │  ksc_meta에서 데이터 기준일 조회
                     └──────┬───────┘
                            │
                    ◇ check_freshness ◇        조건부 엣지 (F3)
                     stale │        │ ok
              ┌────────────▼──┐     │
              │ abort_stale   │     │           신호 계산을 건너뛴다
              └────────┬──────┘     │
                       │      ┌─────▼─────────┐
                       │      │ build_universe│  F1 (스팩·우선주·유동성)
                       │      └─────┬─────────┘
                       │      ┌─────▼─────────┐
                       │      │  load_bars    │  F2 (range 페이지네이션·300청크)
                       │      └─────┬─────────┘
                       │            │  fan-out ─ 5개 병렬
                       │   ┌────┬───┼────┬────┐
                       │   ▼    ▼   ▼    ▼    ▼
                       │  mtf  pb  vcp  sqz  turn      F5~F9
                       │   └────┴───┼────┴────┘
                       │            │  reducer: signals += (operator.add)
                       │      ┌─────▼─────────┐
                       │      │   suppress    │  F10 중복 억제 (DB 조회)
                       │      └─────┬─────────┘
                       │      ┌─────▼─────────┐
                       │      │     rank      │  F11 정규화·상한·전략별 보장
                       │      └─────┬─────────┘
                       │      ┌─────▼─────────┐
                       │      │   persist     │  F12 ksa_signals upsert
                       │      └─────┬─────────┘
                       └────────────┤
                                    │  순차 2 (F13c 오류 격리)
                             ┌──────▼──────┐
                             │ send_email  │  전체 + 근거값 — 먼저 보낸다
                             └──────┬──────┘
                             ┌──────▼──────┐
                             │ send_kakao  │  상위 10건 — 메일 실패를 실어 나른다
                             └──────┬──────┘
                             ┌──────▼──────┐
                             │ record_run  │  ksa_runs 기록
                             └──────┬──────┘
                             ┌──────▼──────┐
                             │  finalize   │  실패가 있으면 여기서만 raise (N5)
                             └──────┬──────┘
                                   END
```

**설계 의도**

| 지점 | 왜 이렇게 두었나 |
|------|------------------|
| `check_freshness` 조건부 엣지 | 발송 중단 판정이 **그래프 위에 보인다**. 함수 안에 숨은 `if`는 나중에 아무도 못 찾는다 |
| 전략 5개 fan-out | SPEC F5~F9는 서로를 모른다. **`Annotated[list, operator.add]` reducer**로 각 노드가 반환한 신호를 합친다. 전략을 늘릴 때 엣지 2줄만 추가된다 |
| `abort_stale`이 발송으로 합류 | 낡은 데이터일 때 **침묵하지 않고 "데이터 지연" 메시지를 보낸다** (D10의 정신). 신호 계산만 건너뛴다 |
| 발송 2개 **순차** | **두 노드 모두 예외를 밖으로 내지 않는다.** 각자 `SendResult`를 상태에 적고, 실패 판정은 `finalize` 한 곳에서 한다 (F13c).<br>**병렬에서 순차로 바꿨다** (2026-08-17): 병렬이면 서로의 실패를 모르므로 "살아 있는 채널이 죽은 채널을 알려 준다"가 성립하지 않는다. 발송은 전체 70초 중 2~3초라 병렬로 얻는 것이 없다. 메일이 먼저인 이유는 내용을 다 담는 쪽이고 토큰 만료 같은 조용한 실패 모드가 없어서다 |
| `record_run`이 `finalize` 앞 | 실패해도 **`ksa_runs`에 먼저 기록**해야 사후에 원인을 본다. 예외를 먼저 던지면 기록이 날아간다 |
| 체크포인터 없음 | 단발 배치라 재개가 의미 없고, 상태에 토큰이 섞이면 디스크에 남는다 (N4) |

**노드별 재시도**: `load_meta` · `load_bars`에만 LangGraph `RetryPolicy`(최대 3회, 지수 백오프)를 건다.
순수 계산 노드는 재시도해도 같은 결과다. **발송 노드에는 걸지 않는다** — 예외를 밖으로 내지 않으므로
노드 단위 재시도가 발동하지 않는다. 전송 재시도는 `notify/` 클라이언트 안에서 한다.

### 1-2. 상태 정의

```python
# alerts/state.py
class AlertState(TypedDict):
    # 입력 (main이 주입 — 전략은 "오늘"을 모른다)
    run_date:  date
    channels:  list[str]              # ['kakao', 'email']
    dry_run:   bool

    # 단계 산출
    data_date: date | None            # ksc_meta 기준일
    stale:     bool
    universe:  list[TickerMeta]
    bars:      dict[str, BarSet]      # ticker -> {D: [...], W: [...], M: [...]}

    # 전략 fan-out 합류 지점 — reducer가 없으면 마지막 노드가 앞을 덮어쓴다
    signals:   Annotated[list[Signal], operator.add]

    ranked:    list[Signal]           # 발송 대상 (카카오용 상한 적용 전 전체)
    kakao_top: list[Signal]           # 상위 10건 (D8)

    # 발송 — 노드가 예외 대신 결과를 적는다 (F13c)
    results:   Annotated[dict[str, SendResult], merge_results]
    status:    str                    # ok | stale_data | partial_send_failed | send_failed
```

> `bars`를 상태에 통째로 담는다. 2,763종목 × (250+80+37)행 ≈ 100만 행이 메모리에 올라간다.
> 대략 200~400MB로 Actions 기본 러너(7GB)에서 문제없다. **M1에서 실측해 기록**한다 (R7).
> 초과하면 상태에 티커 목록만 두고 전략 노드가 청크로 읽는 구조로 바꾼다.

---

## 2. 디렉토리 구조

```
krx-signal-alerts/
├── CLAUDE.md
├── docs/            SPEC.md · PLAN.md · DESIGN.md · TASKS.md
├── supabase/
│   └── schema.sql               ksa_signals · ksa_runs · RLS (멱등)
├── alerts/                      ← 배치 (Python)
│   ├── config.py                .env 로더 (표준 라이브러리, CI 환경변수 우선)
│   ├── models.py                Bar · BarSet · TickerMeta · Signal · SendResult (dataclass)
│   │
│   │  ── 아래 3개가 LangGraph 층. 도메인 로직을 담지 않는다 (N11) ──
│   ├── state.py                 AlertState (TypedDict) · reducer 함수
│   ├── nodes.py                 노드 함수 모음 — 상태 입출력만, 각 20줄 이내
│   ├── graph.py                 build_graph() — 노드·엣지·조건부 분기·RetryPolicy
│   │
│   │  ── 아래가 도메인 층. LangGraph를 모른다. 여기가 TDD 대상 ──
│   ├── store.py                 Supabase 읽기/쓰기 · range() 페이지네이션 · 300청크
│   ├── indicators.py            ma · bollinger · percentile — 순수 함수
│   ├── universe.py              F1 유니버스 필터
│   ├── strategies/
│   │   ├── base.py              Strategy 프로토콜 · 실행 주기 판정
│   │   ├── mtf.py               F5
│   │   ├── pullback.py          F6
│   │   ├── vcp.py               F7
│   │   ├── squeeze.py           F8
│   │   └── turnaround.py        F9
│   ├── rank.py                  F10 중복 억제 · F11 랭킹
│   ├── render.py                메시지 본문 생성 — 순수 함수 (N10)
│   ├── notify/
│   │   ├── base.py              Channel 프로토콜 (N9)
│   │   ├── kakao.py             F13
│   │   └── email.py             F13b
│   └── main.py                  CLI 진입점 — 인자 파싱 → 초기 상태 → graph.invoke()
├── scripts/
│   ├── kakao_auth.py            최초 1회 인가 (--force 지원)
│   ├── dryrun.py                과거 N거래일 드라이런 → 신호량 리포트 (R8)
│   └── export_graph.py          draw_mermaid() → docs/GRAPH.md (N12)
├── tests/                       pytest — 전략별 시나리오 · 렌더 · 랭킹 · 그래프 연결
├── web/                         Next.js 16 (M5)
└── .github/workflows/alert.yml  평일 08:00 KST cron
```

**의존성**: `langgraph` · `supabase` 둘만 추가한다.
카카오·메일·설정 로딩은 전부 표준 라이브러리(`urllib`, `smtplib`, `email`)로 한다.
`pandas`는 **쓰지 않는다** — 계산이 이동평균·표준편차·백분위뿐이라 `statistics`로 충분하고,
Actions 설치 시간을 줄이는 편이 낫다. (SPEC §8의 "PLAN에서 결정" 항목에 대한 답)
**`langchain-openai` 등 LLM 계열은 끌어오지 않는다** (SPEC §2-2).

---

## 3. 모듈 의존 관계

```
                    main
                      │
                    graph  ──────▶ state
                      │
                    nodes                      ← LangGraph를 아는 유일한 층
        ┌────┬────┬────┼──────┬──────┐
        ▼    ▼    ▼    ▼      ▼      ▼
     store universe strategies rank render notify/*
        │              │                 │
        └──▶ config    └──▶ indicators   └──▶ (urllib · smtplib)
                              │
                            models  ◀── 전부가 여기에 의존
```

**규칙 — 이 방향을 거스르지 않는다**

- **도메인 층(`store` 아래 전부)은 `state`·`graph`·`nodes`를 import하지 않는다.**
  LangGraph를 걷어내도 도메인 코드가 그대로 살아 있어야 한다.
- `strategies/`와 `render`는 **`store`도 모른다** — DB 없이 테스트된다 (N1·N10).
- 부수효과(네트워크·DB·시간)를 아는 곳은 `store`·`notify/*`·`main`뿐이다.
- **"오늘"을 전략이 직접 알지 못하게 한다.** 기준일은 `main`이 상태에 넣어 주입한다.
  그래야 드라이런(과거 날짜 재현)과 테스트가 성립한다.

**노드가 얇다는 것의 뜻** (N11)

```python
# nodes.py — 이 정도가 상한이다
def rank_node(state: AlertState) -> dict:
    ranked = rank.apply(state["signals"], limit=KAKAO_LIMIT)
    return {"ranked": ranked, "kakao_top": ranked[:KAKAO_LIMIT]}
```

랭킹 규칙이 이 함수 안에 들어오기 시작하면 `rank.py`로 옮긴다.

---

## 4. 공유 계약 — `evidence` 키 (배치 ↔ 웹)

웹 상세 화면(F16)이 이 키를 그대로 렌더한다. **먼저 고정하고 양쪽을 병렬로 만든다.**

```jsonc
{
  "conditions": [                       // 순서대로 화면에 나열된다
    {"label": "월봉 종가 > MA20",  "ok": true,  "actual": "71,200 > 68,430"},
    {"label": "주봉 MA20 > MA60",  "ok": true,  "actual": "69,100 > 66,880"}
  ],
  "price":  {"close": 71200, "change_pct": 2.14},
  "volume": {"value": 12345678, "amount": 879000000000},
  "meta":   {"in_progress": false}      // F8 진행중 주봉 표기용
}
```

- `conditions[].actual`은 **문자열**이다. 숫자 포맷을 배치에서 확정해 웹이 다시 포맷하지 않게 한다.
  같은 값이 메일 표(F13b)와 웹(F16)에서 다르게 보이는 사고를 막는다.
- 키를 늘릴 수는 있어도 **이름을 바꾸면 과거 이력이 깨진다.** 변경 시 SPEC부터 고친다.

---

## 5. 마일스톤

각 마일스톤은 **검증 3종 통과 + 사용자 확인**으로 닫는다.

### M0 — 뼈대 + 걷는 해골 (1일)
venv · `requirements.txt`(langgraph·supabase) · `pyproject.toml`(ruff·mypy strict) · `.gitignore` ·
`.env.example` · `config.py` · `models.py` · git init + 최초 커밋.

**여기서 그래프를 먼저 세운다.** 모든 노드를 **빈 통과 함수**로 두고 §1-1 구조 그대로 연결해,
`python -m alerts.main --dry-run`이 START→END까지 완주하게 만든다.

> 노드를 다 만든 뒤에 그래프를 조립하면 reducer·조건부 엣지·병렬 합류에서 한꺼번에 터진다.
> 배관을 먼저 통과시키고 노드를 하나씩 채우는 편이 훨씬 싸다.

**완료 기준**
- `ruff check .` · `mypy alerts/` · `pytest` 통과.
- 빈 그래프가 완주하고, `check_freshness` 분기 양쪽 경로가 모두 실행되는 것을 테스트로 확인.
- `scripts/export_graph.py` → `docs/GRAPH.md` 생성 (N12).

### M1 — 데이터 계층 (1일)
`supabase/schema.sql` 적용 · `store.py`(읽기/쓰기) · `universe.py`(F1) · `indicators.py`.
**여기서 R6(1000행 절단)과 URL 길이 문제를 먼저 잡는다** — 뒤에서 터지면 원인 찾기가 어렵다.
**완료 기준**
- 유니버스 건수가 SQL 직접 카운트와 **일치**(REST로 세지 않는다).
- 제외 사유별 건수 로그: 스팩 / 우선주 / 유동성 미달.
- 2,763종목 일봉 250행 조회가 절단 없이 완료되고 소요 시간을 기록.

### M2 — 전략 5개 (3일) ★ TDD 핵심
`strategies/` 5개 + `rank.py`. **테스트를 먼저 쓴다.**
각 전략마다 손으로 만든 봉 시나리오로 **양성 1개 이상 · 음성은 조건 수만큼**(각 조건을 하나씩
깨뜨려 탈락하는지) 검증한다. 조건이 5개면 음성 케이스도 5개다.

전략 노드 5개를 M0의 빈 그래프에 붙인다. 노드는 래퍼일 뿐이므로 각 전략은
**`strategies/*.py`의 순수 함수를 직접 부르는 테스트**로 검증하고, 그래프 쪽은
**reducer가 5개 결과를 실제로 합치는지**만 별도로 확인한다 (여기가 조용히 깨지는 지점이다).
**완료 기준**
- 전략별 양성·음성 테스트 전부 통과.
- `scripts/dryrun.py`로 최근 60거래일 드라이런 → **전략별 일평균 신호량 리포트**.
- 신호량이 극단(0건 또는 100건 초과)이면 **임계값을 조정하고 SPEC §4-2에 변경 사유를 기록**(R8).
- 표본 3종목을 손계산과 대조.

### M3 — 발송 (1.5일)
`render.py` · `notify/{base,kakao,email}.py` · `scripts/kakao_auth.py`.
**렌더와 전송을 분리해 렌더부터 테스트한다** — 발송 없이 형식을 다 잡는다.
**완료 기준**
- 렌더 테스트: 200자 절단 · 0건 문구 · 근거값 전개 · 실패 경고 부착(F13c).
- 카카오 실제 도착 · 메일 실제 도착(**받은편지함 확인**, R11).
- **한 채널을 일부러 실패시켜** 다른 채널이 도착하고 경고가 붙는 것을 확인.
- `ksa_runs`에 채널별 결과가 남는 것을 확인.

### M4 — 자동화 (1일)
`.github/workflows/alert.yml` · Secrets 등록 · 리프레시 토큰 Secret 자동 갱신 · F3 신선도 검사.
**완료 기준**
- 수동 실행(`workflow_dispatch`) 성공.
- cron으로 **연속 5거래일** 두 채널 도착 (0건인 날 "없음" 포함).
- 신선도 검사가 낡은 데이터에서 실제로 발송을 막는지 확인(기준일을 조작해 시험).
- 워크플로 권한 최소화(`permissions:` 명시)·Secrets 미노출 확인.

### M5 — 웹 `/signals` (2일)
**DESIGN.md 시안 합의 후 착수** (SPEC N8). Next.js 16 + TS + Tailwind, Vercel 배포.
F15 목록 · F16 상세 · F17 이력.
**완료 기준**: `npm run lint` · `npm test` · `npm run build` 통과, 배포 URL에서 실동작 확인.

### M6 — 마무리 (0.5일)
보안 점검(N7) · README.md / README_KO.md · 운영 기록.

---

## 6. 테스트 전략

| 대상 | 방식 | 왜 |
|------|------|-----|
| `indicators` | 손계산 대조 | 여기가 틀리면 전부 틀린다 |
| `strategies/*` | 합성 봉 시나리오 — 양성 1 + 조건별 음성 N | **조건 하나를 지워도 테스트가 통과하면 그 조건은 검증되지 않은 것이다** |
| `universe` | 스팩·우선주·문자 티커(`0126Z0`) 케이스 | 실제로 존재하는 함정 |
| `rank` | 중복 억제 경계일(9일/10일/11일) · 전략별 최소 1건 보장 | off-by-one이 나기 쉽다 |
| `render` | 200자 경계 · 0건 · 실패 경고 · HTML 이스케이프 | 종목명에 `&`가 들어가면 메일이 깨진다 |
| `notify/*` | HTTP·SMTP를 **stub으로 대체** | 테스트가 실제로 메일을 보내면 안 된다 |
| `store` | 페이지네이션 경계(1000행) mock | R6 |
| **`graph`** | **연결·분기·합류만** — 노드를 stub으로 갈아끼우고 ① 신선/낡음 두 경로 ② **reducer가 5개 결과를 합치는지** ③ 발송 노드 하나가 실패해도 `record_run`·`finalize`에 도달하는지 | 전략 로직을 그래프로 테스트하지 않는다 (N11). 그래프가 검증할 것은 **배관**이다 |
| 웹 | Vitest — 컴포넌트 렌더·필터·정렬 | |
| 통합 | `scripts/dryrun.py` — 실DB, 발송 없음 | 실데이터에서만 드러나는 문제 |

**금지**: 실DB에 붙는 단위 테스트, 실제로 발송하는 테스트, **그래프를 통해 도메인 로직 테스트하기**.

> reducer 누락은 **조용히 틀린다** — `Annotated[..., operator.add]`를 빼먹으면 전략 5개 중
> 마지막 하나의 결과만 남고 예외도 안 난다. 그래프 테스트 ②가 이걸 잡는 유일한 장치다.

---

## 7. 리스크와 대응 (SPEC §6 중 실행 관점)

| 리스크 | 언제 드러나나 | 선제 대응 |
|--------|---------------|-----------|
| **R8 임계값** — 신호가 0건이거나 수백 건 | M2 드라이런 | M2를 닫기 전에 반드시 드라이런. **이것이 M2의 진짜 완료 조건**이다 |
| **R6 1000행 절단** — 조용한 누락 | M1, 안 잡으면 M2에서 오진 유발 | M1에서 SQL 카운트와 대조해 못 박는다 |
| **R7 실행 시간** — 5분 초과 | M1 조회 시점 | M1에서 시간을 재 둔다. 초과하면 유니버스를 줄이지 말고 조회를 병렬화 |
| **R2 토큰 만료** | 2개월 뒤 | M4에서 Secret 자동 갱신을 반드시 넣는다. 메일 채널이 백업 |
| **R11 스팸함** | M3 첫 발송 | 받은편지함 도착을 M3 완료 기준에 넣었다 |
| **F7(VCP) 정의가 안 맞음** | M2 | 5개 중 가장 깨지기 쉽다. **다른 4개를 먼저 끝내고 마지막에 붙인다** — VCP가 막혀도 M2가 통째로 멈추지 않게 |
| **reducer 누락으로 신호가 조용히 사라짐** | M2, 안 잡으면 배포 후에도 모른다 | M0에서 빈 그래프로 합류를 먼저 확인하고, M2에 전용 테스트를 둔다 (§6) |
| **LangGraph가 도메인에 새어 들어옴** | M2~M3에 서서히 | N11 — 노드 20줄 상한. 넘으면 도메인 모듈로 옮긴다. 코드 리뷰 시 매번 본다 |
| **`bars` 상태 메모리** | M1 | 실측해 기록한다(§1-2). 초과 시 상태에 티커만 두고 청크 조회로 전환 |

---

## 8. 일정

| 마일스톤 | 예상 | 누적 |
|----------|------|------|
| M0 뼈대 + 걷는 해골 | 1일 | 1 |
| M1 데이터 계층 | 1일 | 2 |
| M2 전략 5개 | 3일 | 5 |
| M3 발송 | 1.5일 | 6.5 |
| M4 자동화 | 1일 | 7.5 |
| M5 웹 | 2일 | 9.5 |
| M6 마무리 | 0.5일 | 10 |

**M4까지 오면 목표(매일 아침 알림)는 달성된다.** M5·M6은 그 위의 보강이다.

---

## 9. 사용자 준비물

| 시점 | 준비물 |
|------|--------|
| M1 전 | `SUPABASE_URL` · `SUPABASE_SERVICE_KEY` · `SUPABASE_DATABASE_URL` (krx-stock-charts `.env`에서 재사용) |
| M3 전 | **Gmail 앱 비밀번호 발급** (Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호) |
| M3 전 | 카카오 개발자센터 앱 — 기존 앱 재사용. `KAKAO_REST_API_KEY`(+ 활성화돼 있으면 `KAKAO_CLIENT_SECRET`) |
| M4 전 | GitHub 저장소 생성 + Secrets 등록. 토큰 자동 갱신을 위해 **`contents: write` 대신 저장소 Secret 쓰기 권한이 있는 PAT** 필요 여부를 M4에서 결정 |
| M5 전 | Vercel 프로젝트 생성 |

---

## 10. 변경 이력

| 일자 | 내용 |
|------|------|
| 2026-08-17 | 최초 작성 (SPEC v1.0 기준) |
| 2026-08-17 | **LangGraph 반영** (SPEC v1.1 / D16). §1-1 그래프 구조 · §1-2 상태 정의 신설, §2 디렉토리에 `state`/`nodes`/`graph` 3층 분리, §3 의존 방향 규칙, M0을 「걷는 해골」로 확장(0.5→1일), §6에 그래프 테스트 추가, §7에 reducer 누락·로직 유출 리스크 추가 |
