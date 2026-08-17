# krx-signal-alerts

*[한국어 README](README_KO.md)*

A morning screener for the Korean stock market. Every weekday at 08:20 KST it runs
five swing/trend strategies across every liquid KOSPI and KOSDAQ ticker and delivers
the result to KakaoTalk and email before the market opens.

**Live: [https://krx-signal-alerts.vercel.app](https://krx-signal-alerts.vercel.app)**

Signals are a **watchlist, not trade instructions**. The project does not suggest entry
or exit prices, does not backtest returns, and does not place orders.

## How it works

```
krx-stock-charts (separate repo)          this repo
  18:00 KST  pykrx → ksc_bars    ──read──▶  08:20 KST  LangGraph batch
                                                │
                                       ksa_signals / ksa_runs
                                                │
                                    email (all) + KakaoTalk (top 10)
                                                │
                                          web /signals
```

Prices are not collected here. The batch reads the `ksc_*` tables that
[krx-stock-charts](https://github.com/daehyub71/krx-stock-charts) fills each evening —
2.4M bars across 2,763 tickers — and only ever writes to its own `ksa_*` tables.

The batch is a single LangGraph state graph: 16 nodes, one conditional gate, and a
five-way parallel fan-out. There is no LLM anywhere in it — LangGraph is used for the
plumbing (parallel fan-out with a reducer, a visible freshness gate, isolated failure
domains), not for intelligence. See [docs/GRAPH.md](docs/GRAPH.md).

## The five strategies

| Strategy | Cadence | Looks for |
|---|---|---|
| **MTF alignment** | daily | Monthly, weekly and daily trends aligning on the same day — the transition day only |
| **Weekly pullback** | week close | An uptrend that dipped to the 20-week average and recovered within the week, on dry volume |
| **VCP contraction** | daily | Volume and range drying up after a wide-range up bar, without giving back half its body |
| **Band squeeze** | daily | Weekly Bollinger width at a 52-week low, then expanding through the upper band |
| **Long turnaround** | month close | Six flat months, then 3× volume *and* 3× turnover breaking the box |

Measured over 60 trading days: 883 signals after duplicate suppression, about
**15 a day**. Thresholds and per-strategy counts are in [docs/SPEC.md](docs/SPEC.md) §4-2.

## Two channels, on purpose

Email goes first and carries every signal with its per-condition evidence. KakaoTalk
follows with the top 10 — its text template caps at 200 characters.

Running both is not redundancy for its own sake. Kakao's refresh token expires roughly
every two months, and when it dies the alert stops silently; email has no such failure
mode. **A day where only one arrives is itself the alarm.** If email fails, the Kakao
message carries the notice.

## Running it

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # fill in credentials

python scripts/apply_schema.py    # create ksa_signals / ksa_runs (idempotent)
python scripts/kakao_auth.py      # one-time browser consent

python -m alerts.main                    # screen and send
python -m alerts.main --dry-run          # no send, no writes
python -m alerts.main --channel email    # one channel
python -m alerts.main --date 20260814    # replay a past date

python scripts/dryrun.py --days 60       # signal volume over the last 60 sessions
python scripts/export_graph.py           # regenerate docs/GRAPH.md
```

## Checks

```bash
ruff check . && mypy && pytest -q          # batch — 183 tests
cd web && npm run lint && npm test && npm run build   # web — 8 tests
```

## Layout

```
alerts/
  state.py nodes.py graph.py    the only layer that knows LangGraph
  strategies/ rank.py render.py universe.py indicators.py freshness.py schedule.py
                                pure functions — no framework, no I/O
  store.py notify/ main.py      the only layer that knows the network
web/                            Next.js 16 — one screen, detail expands in place
supabase/schema.sql             ksa_signals, ksa_runs, RLS
scripts/                        schema, kakao auth, dryrun, graph export
docs/                           SPEC · PLAN · DESIGN · TASKS · GRAPH
```

Domain code does not import LangGraph. Nodes stay under twenty lines; anything longer
means logic has leaked out of the domain layer and back into the graph.

## Two bugs the unit tests could not catch

**Trading halts were flooding VCP.** KRX reports a halted day as volume 0 with open,
high and low collapsed onto the close. That reads as a textbook volatility contraction —
"volume 0.00×, range 0.00×" — and 4.5% of all daily bars look like this. Synthetic
fixtures have no halts, so only a real 60-day dryrun surfaced it. Every strategy now
skips a ticker that did not trade on the judgement day.

**Pullback fired on flat stocks.** "MA60 above MA60 four weeks ago" is true after a
single up bar nudges it 0.03%. The slope now needs 0.5%.

And one the web caught: **amount and change were mixed across timeframes.** Pullback
reported a weekly turnover next to MTF's daily figure in the same column, which makes
sorting meaningless. Display values now always come from the daily bar.

## License

MIT
