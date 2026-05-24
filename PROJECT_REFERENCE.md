# PROJECT REFERENCE — OptiTrade AI → Alpaca Trading Bot v8

*Share this file with Claude in any future session to resume exactly where we left off.*

---

## What This Does

Full-stack automated trading bot:
- Receives BUY/SELL signals from TradingView (OptiTrade AI) via webhooks
- Places orders automatically on Alpaca paper/live account
- 9-tab web dashboard to monitor, control, research, analyze, and ask AI
- Telegram alerts on every trade + bot commands (/positions /pnl /close AAPL etc)
- Analyzer Pro: real-time RSI/MACD/ADX/BB/EMA50/VWAP scanner (pure Python, yfinance)
- Research engine: 13F institutional, earnings whiplash, sector rotation, insider+options
- Analytics tab: per-symbol win rates, P&L charts, equity curve, profit factor
- MirrorFish AI: free LLM market predictions via Groq/OpenRouter/HuggingFace
- Excel export of all trades and P&L

---

## GitHub

https://github.com/ambrose2107/TV_GPT_ALP

---

## Tech Stack

| Layer         | Tech                                                            |
| ------------- | --------------------------------------------------------------- |
| Language      | Python 3.11                                                     |
| Framework     | Flask 3.0                                                       |
| Database      | SQLite (trades.db)                                              |
| Broker        | Alpaca Markets API                                              |
| Market Data   | Yahoo Finance (via yfinance + direct API) — FREE, no key needed |
| SEC Data      | SEC EDGAR public API — FREE                                     |
| Hosting       | Railway (24/7)                                                  |
| Dev           | Replit                                                          |
| Signals       | TradingView + OptiTrade AI indicator                            |
| Notifications | Telegram Bot API                                                |
| Export        | openpyxl (Excel)                                                |
| Charts        | Chart.js (CDN, no install)                                      |
| AI Layer      | Groq / OpenRouter / HuggingFace (all free tiers)               |

---

## Environment Variables (Railway → Variables)

```
ALPACA_API_KEY        Alpaca API key (from alpaca.markets → paper trading → API keys)
ALPACA_SECRET_KEY     Alpaca secret key
ALPACA_MODE           paper (or live when ready)
APP_SECRET_KEY        Any random string (Flask session encryption)
DASHBOARD_PASSWORD    Password for dashboard login
WEBHOOK_SECRET        Must match "secret" field in TradingView JSON
TELEGRAM_BOT_TOKEN    From @BotFather on Telegram
TELEGRAM_CHAT_ID      From @userinfobot on Telegram
MAX_POSITION_SIZE     10 (max shares per order)
DAILY_LOSS_LIMIT      500 (USD)
MAX_OPEN_POSITIONS    5
KILL_SWITCH           false

# v8 NEW — MirrorFish AI (add at least one; all are free tier)
GROQ_API_KEY          Get free at console.groq.com  ← RECOMMENDED (fastest)
OPENROUTER_API_KEY    Get free at openrouter.ai     ← good fallback
HUGGINGFACE_API_KEY   Get free at huggingface.co    ← slowest but always works
```

---

## File Structure

```
main.py                           Entry point (gunicorn: main:app)
app.py                            Flask app factory — v8: registers mirrorfish_bp + analytics_bp
requirements.txt                  All deps (unchanged — no new packages needed)
Procfile                          Railway deploy command
railway.json                      Railway config

core/
  config.py                       All settings from env vars
  database.py                     v8: get_closed_positions(), dual-tz in webhook_log
  logger.py                       Centralised logging
  telegram.py                     Telegram alerts + bot message sender
  excel_export.py                 3-sheet Excel export
  analyzer.py                     Analyzer Pro — pure Python RSI/MACD/ADX/BB/EMA50/VWAP
  data_engine.py                  Free data layer — Yahoo Finance v8 API, SEC EDGAR
  timezone_utils.py               v8 REWRITTEN: format_dual_timezone(), parse_and_dual_format()
  order_sync.py                   v7: sync Alpaca filled orders to local DB
  analytics_routes.py             v8 NEW: /api/analytics/* routes for Analytics tab

brokers/
  alpaca_adapter.py               Alpaca REST API — buy/sell/close/positions/validate

webhook/
  handler.py                      Signal processor: validate → risk check → execute → alert
  routes.py                       POST /webhook  GET /health

mirrorfish/                       v8 NEW
  __init__.py
  engine.py                       Multi-LLM AI engine (Groq/OpenRouter/HuggingFace)
  routes.py                       /api/mirrorfish/* routes

dashboard/
  routes.py                       All API routes + Telegram bot command handler
  templates/
    login.html                    Password login page
    dashboard.html                Full 9-tab dashboard
    analytics_tab.html            v8 NEW: Analytics tab HTML snippet (paste into dashboard.html)
    mirrorfish_tab.html           v8 NEW: MirrorFish tab HTML snippet (paste into dashboard.html)

research/
  sec_filings.py                  SEC EDGAR 13F institutional tracker
  earnings.py                     Earnings whiplash: HV vs IV scanner
  sector_rotation.py              30-day sector return comparison
  insider_flow.py                 SEC Form 4 insider buys + unusual options flow
```

---

## Dashboard Tabs (v8)

| Tab           | Features                                                                  |
| ------------- | ------------------------------------------------------------------------- |
| Dashboard     | Account stats, kill switch, webhook URL, signal log (dual-tz), Excel      |
| Positions     | Open positions with P&L, close selected (full or partial qty)             |
| History       | P&L summary, closed positions with dual-tz timestamps, Excel download     |
| Analyzer Pro  | Signal grid (RSI/MACD/ADX/BB/EMA50/VWAP), price charts, compare tab      |
| Analytics     | NEW: per-symbol trade count, P&L, win rate charts, equity curve           |
| MirrorFish AI | NEW: symbol analysis, portfolio health, free-form market chat             |
| Research      | 13F institutional, earnings whiplash, sector rotation, insider+options    |
| Sessions      | ICT session analysis: Asia / London / New York                            |
| EOD Journal   | P&L calendar, equity curve, Excel export                                  |

---

## MirrorFish AI — How It Works

1. Reads your Analyzer Pro signal data (RSI, MACD, etc.) for context
2. Sends structured prompt to free LLM (Groq → OpenRouter → HuggingFace)
3. Returns JSON: prediction (BULLISH/BEARISH/NEUTRAL), confidence, key levels, reasoning
4. Portfolio mode: analyzes all open positions + recent P&L via LLM
5. Chat mode: free-form market questions answered by the LLM

Provider priority: Groq first (fastest, LLaMA 70B free), then OpenRouter, then HuggingFace.
No additional pip packages needed — uses `requests` already in requirements.txt.

### Getting free API keys
- **Groq**: console.groq.com → API Keys → Create → copy → Railway GROQ_API_KEY
- **OpenRouter**: openrouter.ai → Keys → Create → copy → Railway OPENROUTER_API_KEY
- **HuggingFace**: huggingface.co → Settings → Access Tokens → New token (read) → HUGGINGFACE_API_KEY

---

## Analytics Tab — How It Works

Reads `closed_positions` table (populated by v7 order_sync.py).
Computes per symbol: trade count, wins, losses, win rate %, total P&L, avg win/loss, profit factor.
Renders 4 Chart.js charts: equity curve, stacked bar (wins/losses), P&L bar, win rate bar.
Route: GET /api/analytics/summary

---

## v8 Changes Summary

### NEW: MirrorFish AI tab
- `mirrorfish/engine.py` — multi-provider LLM client (Groq, OpenRouter, HuggingFace)
- `mirrorfish/routes.py` — /api/mirrorfish/status, /analyze, /portfolio, /chat
- `dashboard/templates/mirrorfish_tab.html` — full tab UI with symbol analyzer, portfolio health, chat
- Zero new pip packages (uses requests)

### NEW: Analytics tab
- `core/analytics_routes.py` — /api/analytics/summary, /api/analytics/symbol/<sym>
- `dashboard/templates/analytics_tab.html` — 4 charts + per-symbol table
- Fixed `equityChart` initialization error (destroy before recreate pattern)

### FIXED: Recent Signals dual-timezone
- `core/timezone_utils.py` — `parse_and_dual_format()` returns "2026-05-23 09:35 EDT | 22:35 JST"
- `core/database.py` — `get_webhook_log()` now includes `timestamp_display` dual-tz field
- Dashboard webhook log table updated to show both US and JST times on each row

### HOW TO INTEGRATE INTO dashboard.html
1. Add two tab buttons to the nav:
   ```html
   <button class="tab-btn" onclick="switchTab('analytics')" id="tab-analytics">📊 Analytics</button>
   <button class="tab-btn" onclick="switchTab('mirrorfish')" id="tab-mirrorfish">🐟 MirrorFish AI</button>
   ```
2. Paste content of `analytics_tab.html` and `mirrorfish_tab.html` before the closing `</div>` of your tabs container.
3. In your `switchTab(tab)` JS function, add:
   ```javascript
   if (tab === 'analytics') loadAnalytics();
   if (tab === 'mirrorfish') loadMirrorFish();
   ```
4. In your webhook log render function, update the timestamp cell to use `row.timestamp_display` instead of `row.timestamp`.
5. Register blueprints in `app.py` (already done in v8 app.py).

---

## Tests

Run: `python test_bot.py`
Should pass all existing 29 tests (v8 adds no breaking changes to existing modules).

---

## Railway Deploy

1. Push v8 changes to GitHub
2. Railway auto-deploys from main branch
3. Add new env vars: GROQ_API_KEY (and/or others)
4. Visit /api/mirrorfish/status to verify provider is detected
