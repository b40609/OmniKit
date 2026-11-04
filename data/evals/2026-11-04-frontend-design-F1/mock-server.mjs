// CatOS 前端實測用的假後端：只回傳固定資料，不寫任何東西。
// 第二輪：一個進行中的 run（權益曲線、持倉、風控快照、成交），另外三個實例已結束（完成、手動停止、失敗）。
// 欄位照 CatOS 前端的 src/contracts；事件分類照後端 catos/simulation_catalog.py，payload 照 catos/local_sim_control_runner.py。
// v1 後端只有一個 Bot；這裡放 4 個同一個 SMA 模組的實例（同時只有一個在跑，符合單一槽位），用來看矩陣與列表在多筆資料時的樣子。
// 價格用接近真實行情的量級（不是 v1 合成資料的 100 左右），讓數字寬度接近實際使用。
// 直接執行時只提供 API（127.0.0.1:8779），給 vite dev server 代理；run.mjs 則引用 handleApi，跟建好的三個版本放在同一個埠。
// `node mock-server.mjs --dump` 只印出資料摘要，不啟動伺服器。
import http from 'node:http';
import { pathToFileURL } from 'node:url';

const PREFIX = '/api/workspace/simulation';
const CONTRACT = 'catos.simulation.v1';
const VERSION = 412;
const INSTANCE = '9ac8b9ba4e1d47c3b2f05a6d81c3e7f2';
const BUILD = 'c'.repeat(64);
const ARTIFACT = 'f'.repeat(64);
const TAG = '41cb53c54d6dABDE';
const FEE_RATE = 0.0005;
const START_BALANCE = 1000;
const LEVERAGE_LIMIT = 3;
const SYMBOL_SHARE = 0.5;
const MIN = 60_000;
const NOW = Math.floor(Date.now() / 1000) * 1000;   // 啟動時固定；同一個程序內，三張截圖看到的資料完全一樣
const DAY_START = Date.UTC(2026, 10, 3, 16);        // 合成時間 11/04 00:00（台灣）
const DAY = 20761;
const EVENT_GAP_MS = 2_400;                         // 模擬加速重播：每筆事件約隔 2.4 秒

const dec = (n, d = 8) => (Math.abs(n) < 0.5 * 10 ** -d ? 0 : n).toFixed(d);

function mulberry32(a) {
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// 確定性的價格序列；tail 是最後幾根的額外漲跌，用來讓已結束的 run 收在空手、進行中的 run 收在持倉
function prices({ n, start, drift, amp, wave, noise, seed, tick, tail = [] }) {
  const rnd = mulberry32(seed);
  const out = Array.from({ length: n }, (_, i) => start * (1 + drift * i + amp * Math.sin(i / wave) + noise * (rnd() - 0.5)));
  tail.forEach((change, k) => { out[n - tail.length + k] *= 1 + change; });
  return out.map((p) => Math.round(p / tick) * tick);
}

// 依執行順序排列（ETH → SOL → BTC 快線 → BTC），事件的全域 seq 照這個順序遞增
const BOTS = [
  { bot_id: 'sim-eth-sma', run_id: '3f9a1c27e4b84d0f9c51a2b6d8e07f13', inst: 'ETH-USDT-SWAP', ct: 0.1, tick: 0.01, qty: 3, period: 5,
    tf: 60 * MIN, outcome: 'completed', bars: 23, wall_start: NOW - 190 * MIN, run_count: 3, created_days_ago: 6,
    px: { start: 3452, drift: 0.0009, amp: 0.012, wave: 3.2, noise: 0.004, seed: 11, tail: [-0.008, -0.016, -0.024] } },
  { bot_id: 'sim-sol-sma', run_id: 'b74e02d95a1c4f38a6e9d3170c5b28fe', inst: 'SOL-USDT-SWAP', ct: 1, tick: 0.01, qty: 4, period: 4,
    tf: 5 * MIN, outcome: 'stopped', bars: 26, wall_start: NOW - 96 * MIN, run_count: 2, created_days_ago: 3,
    px: { start: 168.4, drift: -0.0004, amp: 0.009, wave: 2.6, noise: 0.005, seed: 23, tail: [-0.008, -0.016, -0.024] } },
  { bot_id: 'sim-btc-sma-fast', run_id: 'e15c8b3a07d94e62b9f4a1d6c38e5072', inst: 'BTC-USDT-SWAP', ct: 0.01, tick: 0.1, qty: 1, period: 3,
    tf: 5 * MIN, outcome: 'failed', bars: 12, wall_start: NOW - 41 * MIN, run_count: 1, created_days_ago: 1,
    px: { start: 67480, drift: 0.0002, amp: 0.004, wave: 2.1, noise: 0.002, seed: 37, tail: [-0.004, -0.008] } },
  { bot_id: 'sim-btc-sma', run_id: '5d3e91b04a7c4e28b6f1c09d2e8a7b43', inst: 'BTC-USDT-SWAP', ct: 0.01, tick: 0.1, qty: 1, period: 6,
    tf: 15 * MIN, outcome: 'running', bars: 54, wall_start: null, run_count: 5, created_days_ago: 9,
    px: { start: 67120, drift: 0.00045, amp: 0.011, wave: 4.3, noise: 0.003, seed: 5, tail: [0.004, 0.008, 0.011] } },
];

const RISK_STATE = { mode: 'RUN', health: 'HEALTHY', phase: 'IDLE', reasons: [], epoch: 1 };

function simulate(b) {
  const px = prices({ n: b.bars, tick: b.tick, ...b.px });
  const events = [];
  const emit = (kind, level, category, payload, synthetic = null) => {
    events.push({ run_id: b.run_id, bot_id: b.bot_id, kind, wall_time_ms: 0, synthetic_time_ms: synthetic, level, category, payload });
  };
  let pos = 0, avg = 0, realized = 0, fees = 0, fills = 0, last = null;
  const numbers = (mark) => {
    const unrealized = pos * b.ct * (mark - avg);
    const balance = START_BALANCE + realized - fees;
    return { unrealized, balance, equity: balance + unrealized };
  };
  const account = (mark) => {
    const n = numbers(mark);
    return {
      balance: dec(n.balance), position: String(pos), average_entry: pos ? dec(avg, 2) : null,
      realized_pnl: dec(realized), unrealized_pnl: dec(n.unrealized), equity: dec(n.equity),
      fees: dec(fees), funding_paid: dec(0), mark: dec(mark, 2),
    };
  };

  emit('run_state', 'INFO', 'SYSTEM', { state: 'starting', previous: null });
  emit('day_basis', 'INFO', 'RISK', {
    basis: { day: DAY, equity: dec(START_BALANCE), evidence_id: `synthetic-basis-${DAY}`, period_start_ms: DAY_START },
    account: account(px[0]), risk_state: RISK_STATE,
  }, DAY_START);
  for (let i = 0; i < b.period; i++) {
    emit('warmup', 'INFO', 'WORKER', { seq: i + 1, target: null, disposition: 'NO_INTENT' }, DAY_START + (i + 1) * b.tf);
  }
  emit('run_state', 'INFO', 'SYSTEM', { state: 'running', previous: 'starting' });

  for (let i = b.period; i < b.bars; i++) {
    const mark = px[i];
    const seq = i + 1;
    const now = DAY_START + seq * b.tf;
    const sma = px.slice(i - b.period + 1, i + 1).reduce((sum, p) => sum + p, 0) / b.period;
    const target = mark > sma ? b.qty : 0;
    let disposition = 'NO_CHANGE', reason = 'target_equals_position';
    if (target > pos) [disposition, reason] = ['RESERVED_SIMULATION', 'exposure_reserved'];
    if (target < pos) [disposition, reason] = ['RESERVED_SIMULATION', 'legal_reduction'];
    emit('signal', 'INFO', 'WORKER', {
      seq, synthetic_time_ms: now, target: String(target), disposition, reason, account: account(mark),
      intent_key: disposition === 'NO_CHANGE' ? null : `${b.run_id.slice(0, 8)}:${seq}`, mark: dec(mark, 2), risk_state: RISK_STATE,
    }, now);
    if (disposition === 'RESERVED_SIMULATION') {
      const delta = target - pos;
      const qty = Math.abs(delta);
      const fee = qty * b.ct * mark * FEE_RATE;
      if (delta > 0) avg = (pos * avg + delta * mark) / (pos + delta);
      else realized += qty * b.ct * (mark - avg);
      pos = target;
      if (pos === 0) avg = 0;
      fees += fee;
      fills += 1;
      const after = account(mark);
      emit('fill', 'INFO', 'ORDER', {
        seq, synthetic_time_ms: now,
        request: { inst_id: b.inst, side: delta > 0 ? 'buy' : 'sell', ord_type: 'market', td_mode: 'cross', sz: String(qty), cl_ord_id: `sim-control-${seq}`, tag: TAG },
        fill: { fill_id: `fill-${seq}`, quantity: String(qty), price: dec(mark, 2), fee: dec(fee) },
        position: after.position, fees: after.fees, equity: after.equity, state: 'FILLED',
      }, now);
    }
    last = { seq, now, mark, disposition, reason };
  }

  const final = account(last.mark);
  if (b.outcome === 'completed') {
    emit('final_account', 'INFO', 'RISK', { account: final, risk_state: RISK_STATE });
    emit('run_state', 'INFO', 'SYSTEM', { state: 'completed', previous: 'running' });
  } else if (b.outcome === 'stopped') {
    emit('stop_requested', 'WARN', 'SYSTEM', { request_id: `stop-${b.run_id.slice(0, 12)}` });
    emit('run_state', 'WARN', 'SYSTEM', { state: 'stopping', previous: 'running' });
    emit('final_account', 'INFO', 'RISK', { account: final, risk_state: RISK_STATE });
    emit('run_state', 'INFO', 'SYSTEM', { state: 'stopped', previous: 'stopping' });
  } else if (b.outcome === 'failed') {
    emit('anomaly', 'ERROR', 'SYSTEM', { error: 'worker_or_supervisor_not_healthy' });
    emit('run_state', 'ERROR', 'SYSTEM', { state: 'failed', previous: 'running' });
  }

  // 進行中的 run：最後一筆事件落在啟動前 2 秒；其他 run 從 wall_start 開始
  const start = b.wall_start ?? NOW - 2_000 - (events.length - 1) * EVENT_GAP_MS;
  events.forEach((e, k) => { e.wall_time_ms = start + k * EVENT_GAP_MS; });
  return { b, events, final, last, fills, pos, avg, realized, fees, ...numbers(last.mark),
    first_wall: start, last_wall: events.at(-1).wall_time_ms };
}

const runs = BOTS.map(simulate);
const events = runs.flatMap((r) => r.events).map((e, i) => ({ seq: i + 1, ...e }));

const botView = (r) => {
  const { b } = r;
  const active = b.outcome === 'running';
  return {
    version: VERSION, bot_id: b.bot_id, mode: 'local', strategy_id: 'sma-trend', strategy_version: 'sma-parameters-v1',
    strategy_name: 'SMA', artifact_hash: ARTIFACT, parameters: { period: b.period, quantity: String(b.qty) },
    inst_id: b.inst, symbol: b.inst,
    contract: { inst_id: b.inst, base_per_contract: String(b.ct), tick_size: String(b.tick), lot_size: '1', min_size: '1' },
    timeframe_ms: b.tf, trusted: true, created_at_ms: NOW - b.created_days_ago * 86_400_000, state: b.outcome,
    current_run_id: b.run_id, active, run_count: b.run_count, worker_pid: active ? 18244 : null,
    bars: b.bars - b.period, warmup_bars: b.period, fills: r.fills, last_synthetic_time_ms: r.last.now,
    run_created_at_ms: r.first_wall, finished_at_ms: active ? null : r.last_wall,
    account_source: b.outcome === 'completed' || b.outcome === 'stopped' ? 'final_account' : 'signal',
    position: r.final.position, average_entry: r.final.average_entry, balance: r.final.balance,
    realized_pnl: r.final.realized_pnl, unrealized_pnl: r.final.unrealized_pnl, equity: r.final.equity,
    fees: r.final.fees, funding_paid: r.final.funding_paid, mark: r.final.mark,
    last_disposition: r.last.disposition, last_reason: r.last.reason, ownership_retained: false,
    error: b.outcome === 'failed' ? 'RuntimeError' : null,
  };
};

const live = runs.find((r) => r.b.outcome === 'running');
const bots = [live, ...runs.filter((r) => r !== live)].map(botView);
const notional = live.pos * live.b.ct * live.last.mark;
const exposureBudget = LEVERAGE_LIMIT * live.equity;
const periodPnl = live.equity - START_BALANCE;
const leverage = notional / live.equity;

const service = {
  contract: CONTRACT, mode: 'local-sim-synthetic', build_id: BUILD, current_build_id: BUILD, restart_required: false,
  instance_id: INSTANCE, slot: 'running', active_run_id: live.b.run_id, capabilities: { start: false, stop: true },
  unavailable_reason: null, config: {},
};

const strategies = [{
  strategy_id: 'sma-trend', version: 'sma-parameters-v1', name: 'SMA', description: 'SMA 趨勢（Long / Flat）',
  artifact_hash: ARTIFACT, entry: 'catos.strategies.sma:Strategy', approval_state: 'approved', allowed_modes: ['local'],
  defaults: { parameters: { period: 2, quantity: '2' }, warmup_bars: 2 }, source_files: ['catos/strategies/sma.py'],
  kind: 'registered_python_module',
}];

const risk = {
  version: VERSION, run_id: live.b.run_id, bot_id: live.b.bot_id, run_state: 'running', seq: live.last.seq, time_ms: live.last.now,
  mode: 'RUN', health: 'HEALTHY', phase: 'IDLE', reasons: [], epoch: 1,
  limits: { leverage: String(LEVERAGE_LIMIT), symbol_share: String(SYMBOL_SHARE), soft_loss: '0.02', hard_loss: '0.04' },
  basis: {
    day: DAY, equity: dec(START_BALANCE), evidence_id: `synthetic-basis-${DAY}`, account_alias: 'okx-sim',
    environment: 'local-sim', source: 'synthetic', period_start_ms: DAY_START,
  },
  snapshot: {
    seq: live.last.seq, time_ms: live.last.now, valid_until_ms: live.last.now + live.b.tf,
    equity: dec(live.equity), risk_equity: dec(live.equity), position: String(live.pos), mark: dec(live.last.mark, 2),
    pending_buy: '0', pending_sell: '0', other_notional: dec(0), external_net: dec(0),
    valuation_known: true, flows_known: true, margin_ok: true, position_verified: true, reduction_conflict: false,
    flow_basis_id: null, flow_start_ms: null,
  },
  derived: {
    period_pnl: dec(periodPnl), period_pnl_ratio: dec(periodPnl / START_BALANCE), notional: dec(notional),
    effective_leverage: dec(leverage), exposure_budget: dec(exposureBudget), symbol_budget: dec(SYMBOL_SHARE * exposureBudget),
    can_increase: true, status: 'normal',
  },
};

const positions = live.pos ? [{
  bot_id: live.b.bot_id, run_id: live.b.run_id, run_state: 'running', inst_id: live.b.inst, symbol: live.b.inst,
  position: String(live.pos), average_entry: dec(live.avg, 2), mark: dec(live.last.mark, 2),
  unrealized_pnl: dec(live.unrealized), notional: dec(notional), verified: true,
  protection: null, funding_interval_ms: null, funding_rate: null, liquidation_price: null, margin: null,
}] : [];

const summary = {
  equity: dec(live.equity), realized_pnl: dec(live.realized), unrealized_pnl: dec(live.unrealized), fees: dec(live.fees),
  period_pnl: dec(periodPnl), period_pnl_ratio: dec(periodPnl / START_BALANCE), period_start_ms: DAY_START,
  basis_equity: dec(START_BALANCE), running_bots: 1, total_bots: bots.length, risk_status: 'normal',
  effective_leverage: dec(leverage), leverage_limit: String(LEVERAGE_LIMIT),
  invariants: { fixed_tag: TAG, settlement: 'cross_net_mode', arithmetic: 'decimal_text' },
};

const fullState = () => ({
  contract: CONTRACT, version: VERSION, instance_id: INSTANCE, observed_at_ms: Date.now(), unchanged: false,
  service, strategies, bots, risk, positions, summary,
  events: { items: events.slice(-40), next_since: events.length, omitted: 0 },
  domains: { service: VERSION, bots: VERSION, risk: VERSION, positions: VERSION, events: VERSION },
});

// 處理 /api/ 底下的請求並回傳 true；其他路徑回傳 false，交給呼叫端
export function handleApi(req, res) {
  const url = new URL(req.url, 'http://mock');
  if (!url.pathname.startsWith('/api/')) return false;
  const send = (body, status = 200) => {
    res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' });
    res.end(JSON.stringify(body));
    return true;
  };
  if (req.method !== 'GET') return send({ detail: 'read_only_mock' }, 405);
  if (url.pathname === `${PREFIX}/version`) return send(service);
  if (url.pathname === `${PREFIX}/state`) {
    const since = Number(url.searchParams.get('since_version') ?? -1);
    if (since >= VERSION) {
      return send({ contract: CONTRACT, version: VERSION, instance_id: INSTANCE, observed_at_ms: Date.now(), unchanged: true });
    }
    return send(fullState());
  }
  if (url.pathname === `${PREFIX}/events`) {
    const since = Number(url.searchParams.get('since') ?? 0);
    const limit = Number(url.searchParams.get('limit') ?? 40);
    const rest = events.filter((e) => e.seq > since);
    const items = rest.slice(0, limit);
    return send({ items, next_since: items.length ? items.at(-1).seq : since, more: rest.length > items.length, version: VERSION, omitted: 0 });
  }
  return send({ detail: 'not_mocked' }, 404);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv.includes('--dump')) {
    const kinds = events.reduce((m, e) => ({ ...m, [e.kind]: (m[e.kind] ?? 0) + 1 }), {});
    console.log(JSON.stringify({
      events: events.length, kinds,
      bots: bots.map((b) => ({ id: b.bot_id, state: b.state, equity: b.equity, position: b.position, fills: b.fills, bars: b.bars })),
      summary: { equity: summary.equity, period_pnl: summary.period_pnl, ratio: summary.period_pnl_ratio, realized: summary.realized_pnl, unrealized: summary.unrealized_pnl, fees: summary.fees, leverage: summary.effective_leverage },
      positions, curve_points: events.filter((e) => e.run_id === live.b.run_id && e.kind === 'signal').length,
    }, null, 1));
    process.exit(0);
  }
  http.createServer((req, res) => {
    if (!handleApi(req, res)) { res.writeHead(404); res.end(); }
  }).listen(8779, '127.0.0.1', () => console.log('mock ready on 127.0.0.1:8779'));
}
