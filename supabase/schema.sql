-- krx-signal-alerts 스키마 (SPEC §5)
--
-- 같은 Supabase 프로젝트에 krx-stock-charts의 ksc_* 테이블이 있다.
-- 이 프로젝트가 소유하는 것은 ksa_* 둘뿐이고, ksc_*는 읽기만 한다.
--
-- 적용: python scripts/apply_schema.py
-- 재실행해도 안전하다(멱등).

-- ─────────────────────────────────────────────
-- 신호 (F12)
-- 발송 여부와 무관하게 판정된 신호를 전부 남긴다.
-- 웹 화면(F15~F17)과 중복 억제(F10)가 이 이력을 읽는다.
-- ─────────────────────────────────────────────
create table if not exists ksa_signals (
  d           date not null,              -- 신호 기준일 (봉의 마지막 거래일)
  strategy    text not null,
  ticker      text not null,

  -- 종목명을 여기에 둔다(비정규화). ksc_tickers로의 외래키를 일부러 걸지 않았으므로
  -- Supabase REST가 조인을 못 한다. 게다가 이 테이블은 **그날의 스냅샷**이라,
  -- 사명이 바뀌어도 신호가 났던 시점의 이름이 남는 편이 이력으로서 옳다 (DESIGN §1).
  name        text not null default '',

  score       double precision not null,

  -- 당일 전체 랭킹. 발송 상한(10건)에 밀린 신호는 null일 수 있다.
  rank_no     integer,

  -- 채널별로 따로 기록한다. 카카오는 상위 10건, 메일은 전 신호를 담으므로 값이 다르다 (D8).
  sent_kakao  boolean not null default false,
  sent_email  boolean not null default false,

  -- 중복 억제로 발송에서 제외됐는가 (F10). 저장은 하되 발송만 뺀다.
  suppressed  boolean not null default false,

  -- 조건별 근거값. 웹 상세(F16)와 메일 표(F13b)가 이걸 그대로 렌더한다.
  -- 키 이름이 배치와 웹의 계약이다 — 바꾸면 과거 이력이 깨진다 (PLAN §4).
  evidence    jsonb not null default '{}'::jsonb,

  created_at  timestamptz not null default now(),

  primary key (d, strategy, ticker),

  constraint ksa_signals_strategy
    check (strategy in ('mtf', 'pullback', 'vcp', 'squeeze', 'turnaround')),

  -- 티커는 숫자가 아니다. 0126Z0(삼성에피스홀딩스)처럼 문자가 섞인 6자리가 실재한다.
  constraint ksa_signals_ticker_format check (ticker ~ '^[0-9A-Z]{6}$')
);

-- ksc_tickers로의 외래키를 일부러 걸지 않는다.
-- 상장폐지로 종목이 지워지면 과거 신호 이력까지 함께 사라진다. 이력은 남아야 한다.

-- ── 마이그레이션 ──────────────────────────────
-- `create table if not exists`는 **이미 있는 테이블에 열을 추가하지 않는다.**
-- 위 정의만 고치면 새 DB에서만 반영되고 운영 DB는 조용히 그대로 남는다.
-- 열을 늘릴 때는 반드시 여기에 한 줄을 더한다.
alter table ksa_signals add column if not exists name text not null default '';

-- 중복 억제(F10) 조회용: "이 종목·이 전략이 최근에 나온 적 있나".
-- PK는 (d, strategy, ticker) 순서라 종목축 조회를 못 받는다.
create index if not exists ksa_signals_by_ticker
  on ksa_signals (ticker, strategy, d desc);

-- ─────────────────────────────────────────────
-- 실행 기록 (F13c)
-- "안 온 게 정상인지 고장인지"를 사후에 가리는 유일한 기록이다.
-- 실패한 실행도 반드시 남는다 — record_run이 finalize보다 앞에 있는 이유다.
-- ─────────────────────────────────────────────
create table if not exists ksa_runs (
  run_at        timestamptz primary key default now(),
  data_date     date,                     -- 사용한 데이터 기준일 (F3). 조회 실패 시 null
  universe_n    integer not null default 0,
  signal_n      integer not null default 0,
  sent_kakao_n  integer not null default 0,
  sent_email_n  integer not null default 0,
  status        text not null,

  -- 채널별 성공/실패와 오류 코드 (예: KOE322, SMTPAuthenticationError)
  detail        jsonb not null default '{}'::jsonb,

  constraint ksa_runs_status
    check (status in ('ok', 'stale_data', 'partial_send_failed', 'send_failed'))
);

create index if not exists ksa_runs_by_date on ksa_runs (data_date desc);

-- ─────────────────────────────────────────────
-- RLS — 읽기는 공개(웹이 anon 키로 SELECT), 쓰기는 service_role만.
-- service_role은 RLS를 우회하므로 쓰기 정책을 따로 만들지 않는다.
-- ─────────────────────────────────────────────
alter table ksa_signals enable row level security;
alter table ksa_runs    enable row level security;

drop policy if exists ksa_signals_read on ksa_signals;
drop policy if exists ksa_runs_read    on ksa_runs;

create policy ksa_signals_read on ksa_signals for select to anon, authenticated using (true);
create policy ksa_runs_read    on ksa_runs    for select to anon, authenticated using (true);
