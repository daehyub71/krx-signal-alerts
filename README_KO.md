# krx-signal-alerts

*[English README](README.md)*

국내 주식 아침 스크리너. 평일 08:20 KST에 유동성이 받쳐 주는 코스피·코스닥 전 종목을
다섯 가지 스윙·추세 전략으로 훑어, 장 시작 전에 카카오톡과 이메일로 보냅니다.

신호는 **관찰 후보 목록이지 매매 지시가 아닙니다.** 목표가·손절가를 제시하지 않고,
수익률을 검증하지도, 주문을 내지도 않습니다.

## 어떻게 도는가

```
krx-stock-charts (별도 저장소)              이 저장소
  18:00 KST  pykrx → ksc_bars    ──읽기──▶  08:20 KST  LangGraph 배치
                                                │
                                       ksa_signals / ksa_runs
                                                │
                                     메일(전체) + 카카오톡(상위 10)
```

시세를 직접 수집하지 않습니다. [krx-stock-charts](https://github.com/daehyub71/krx-stock-charts)가
매일 저녁 채우는 `ksc_*` 테이블(2,763종목 240만 행)을 **읽기만** 하고,
쓰기는 자기 소유인 `ksa_*`에만 합니다.

배치는 LangGraph 상태 그래프 하나입니다 — 노드 16개, 조건부 게이트 1곳, 5방향 병렬 fan-out.
**LLM은 하나도 없습니다.** LangGraph는 지능이 아니라 배관(리듀서를 낀 병렬 합류, 눈에 보이는
신선도 게이트, 격리된 실패 영역)을 위해 씁니다. 구조는 [docs/GRAPH.md](docs/GRAPH.md).

## 다섯 전략

| 전략 | 주기 | 무엇을 찾나 |
|---|---|---|
| **MTF 정배열** | 매일 | 월·주·일 세 축이 같은 날 정렬되는 순간 — 전환일 하루만 |
| **주봉 눌림목** | 주 마감 | 상승 추세가 20주선까지 밀렸다가 그 주 안에 되돌린 경우, 거래량은 마른 채로 |
| **VCP 수축** | 매일 | 장대양봉 뒤 몸통 절반을 지키면서 거래량·변동폭만 마르는 구간 |
| **밴드 스퀴즈** | 매일 | 주봉 밴드폭이 52주 최저로 좁혀졌다가 상단을 뚫는 주 |
| **장기 턴어라운드** | 월 마감 | 6개월 횡보 뒤 거래량·거래대금이 **함께** 3배로 들어오며 박스 돌파 |

60거래일 실측: 중복 억제 후 883건, **하루 약 15건**.
임계값과 전략별 건수는 [docs/SPEC.md](docs/SPEC.md) §4-2에 있습니다.

## 채널을 둘 쓰는 이유

메일이 먼저 나가고 전 신호를 조건별 근거값까지 담습니다. 카카오톡이 뒤따르며 상위 10건만
보냅니다 — 텍스트 템플릿 본문이 200자로 막혀 있습니다.

둘을 함께 쓰는 건 단순 이중화가 아닙니다. 카카오 리프레시 토큰은 약 2개월마다 끊기고,
끊기면 **알림이 조용히 멈춥니다.** 메일에는 그 실패 모드가 없습니다.
**한쪽만 오는 날이 곧 경보입니다.** 메일이 실패하면 카카오 메시지가 그 사실을 실어 나릅니다.

## 실행

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # 자격증명 입력

python scripts/apply_schema.py    # ksa_signals / ksa_runs 생성 (멱등)
python scripts/kakao_auth.py      # 최초 1회 브라우저 동의

python -m alerts.main                    # 스크리닝 + 발송
python -m alerts.main --dry-run          # 발송·저장 없음
python -m alerts.main --channel email    # 한 채널만
python -m alerts.main --date 20260814    # 과거 날짜 재현

python scripts/dryrun.py --days 60       # 최근 60거래일 신호량
python scripts/export_graph.py           # docs/GRAPH.md 재생성
```

## 검증

```bash
ruff check .   # 린트
mypy           # strict
pytest -q      # 테스트 181개
```

## 구조

```
alerts/
  state.py nodes.py graph.py    LangGraph를 아는 유일한 층
  strategies/ rank.py render.py universe.py indicators.py freshness.py schedule.py
                                순수 함수 — 프레임워크도 I/O도 모른다
  store.py notify/ main.py      네트워크를 아는 유일한 층
supabase/schema.sql             ksa_signals · ksa_runs · RLS
scripts/                        스키마 적용 · 카카오 인가 · 드라이런 · 그래프 내보내기
docs/                           SPEC · PLAN · TASKS · GRAPH
```

도메인 코드는 LangGraph를 import하지 않습니다. 노드는 20줄을 넘지 않습니다 —
넘으면 도메인 로직이 그래프 층으로 새어 들어온 것입니다.

## 단위 테스트가 못 잡은 두 가지

**거래정지가 VCP를 도배하고 있었다.** KRX는 거래정지일을 거래량 0, 시·고·저가를 종가로
눌러서 보냅니다. 그러면 "거래량 0.00배 · 변동성 0.00배" — 교과서적으로 완벽한 수축이
됩니다. 전 일봉의 4.5%가 이런 행입니다. 합성 데이터에는 거래정지가 없으니 실제 60거래일
드라이런에서야 드러났습니다. 이제 판정일에 거래가 없으면 다섯 전략 모두 건너뜁니다.

**눌림목이 평평한 종목에서도 잡혔다.** "MA60이 4주 전보다 높다"를 부호로만 보면,
상승봉 하나에 0.03%만 올라도 참이 됩니다. 기울기에 4주간 0.5% 하한을 넣었습니다.

## 라이선스

MIT
