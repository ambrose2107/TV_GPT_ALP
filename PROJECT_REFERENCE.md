# PROJECT REFERENCE — OptiTrade AI → Alpaca Trading Bot v3
*Share this file in any future Claude conversation to resume exactly where we left off.*

---

## What This Project Does
Full-stack automated trading bot:
- Receives BUY/SELL signals from **TradingView (OptiTrade AI)** via webhooks
- Places orders on **Alpaca** paper/live account
- **Dashboard** — 6-tab web UI to monitor, control, and research
- **Telegram alerts** on every trade, error, kill switch
- **Research engine** — SEC 13F, earnings whiplash, sector rotation, insider+options
- **Analyzer Pro** — multi-stock/multi-timeframe technical scanner (RSI, MACD, ADX, BB, EMA50, VWAP)
- **Excel export** of all trades and P&L

---

## GitHub Repo
https://github.com/ambrose2107/trading-bot

---

## Tech Stack
| Layer | Tech |
|-------|------|
| Language | Python 3.11 |
| Framework | Flask 3.0 |
| Database | SQLite (trades.db) |
| Broker | Alpaca Markets (paper/live) |
| Data | yfinance |
| Hosting | Railway |
| Dev | Replit |
| Signals | TradingView + OptiTrade AI |
| Notifications | Telegram Bot API |
| Export | pandas + openpyxl |

---

## Environment Variables (Railway + Replit Secrets)
```
ALPACA_API_KEY        Alpaca API key
ALPACA_SECRET_KEY     Alpaca secret key
ALPACA_MODE           paper or live
APP_SECRET_KEY        Random string (Flask session)
DASHBOARD_PASSWORD    Your dashboard login password
WEBHOOK_SECRET        Must match TradingView JSON "secret" field (e.g. my_secret_123)
TELEGRAM_BOT_TOKEN    From @BotFather on Telegram
TELEGRAM_CHAT_ID      From @userinfobot on Telegram
MAX_POSITION_SIZE     Max shares per order (default 10)
DAILY_LOSS_LIMIT      USD loss limit per day (default 500)
MAX_OPEN_POSITIONS    Max simultaneous positions (default 5)
KILL_SWITCH           false (set true to halt all trading)
```

---

## Key URLs (after Railway deploy)
```
https://YOUR-URL/           Dashboard (password protected)
https://YOUR-URL/webhook    TradingView posts signals here
https://YOUR-URL/health     Uptime monitor ping URL
```

---

## Dashboard Tabs

### 1. 🏠 Dashboard
- Portfolio value, buying power, today P&L, open positions count, win rate
- Recent TradingView signals log
- Webhook URL display
- Close All / Kill Switch / Refresh / Export Excel buttons

### 2. 📊 Positions
- All open positions with P&L, % return
- Close selected position (full or partial qty)

### 3. 📋 History
- P&L summary (win rate, total P&L, best/worst trade)
- Closed positions with booked profit/loss
- All trades log
- Download Excel (3 sheets: All Trades, Closed Positions, P&L Summary)

### 4. 🔬 Analyzer Pro
- Multi-stock scanner (up to 10 symbols)
- Timeframes: 5m, 15m, 1h, 4h, 1D, 1W
- Indicators: RSI, MACD, ADX, Bollinger, EMA50, VWAP
- Color-coded like TradingView Analyzer Pro
- Overall Bull/Bear score per stock per timeframe

### 5. 🧠 Research (4 sub-tabs)
**A. Institutional Footprint** — SEC 13F filings, top 5 funds (Berkshire, Bridgewater, Renaissance, Citadel, Two Sigma), top holdings per fund

**B. Earnings Whiplash** — Next 14-day earnings with HV>8%, flags 3 asymmetric setups where IV < HV (options cheaper than history)

**C. Sector Rotation** — 30-day S&P 500 sector returns vs 1 year ago, rotating sectors, top ETFs by money flow

**D. Insider + Options** — Unusual options flow (vol/OI ratio >2x), SEC Form 4 insider buys, confluence detection

### 6. ⚙️ Settings
- Telegram test button
- Kill switch toggle
- Environment variable reference
- Telegram setup guide

---

## TradingView Alert Setup

### OptiTrade 2.0 Buy-Sell Strategy (RECOMMENDED)
**Long Entry (BUY) box:**
```json
{
  "secret": "my_secret_123",
  "symbol": "AAPL",
  "action": "buy",
  "quantity": 1,
  "order_type": "market"
}
```
**Short Entry (SELL) box:**
```json
{
  "secret": "my_secret_123",
  "symbol": "AAPL",
  "action": "sell",
  "quantity": 1,
  "order_type": "market"
}
```
**Alert message box:** `{{strategy.order.alert_message}}`
**Webhook URL:** `https://YOUR-RAILWAY-URL/webhook`

---

## Webhook JSON Reference
| Field | Required | Values |
|-------|----------|--------|
| secret | ✅ | Must match WEBHOOK_SECRET env var |
| symbol | ✅ | US stock ticker e.g. AAPL, TSLA, QQQ |
| action | ✅ | buy / sell / close / close_all |
| quantity | ✅ | Number of shares |
| order_type | optional | market (default) / limit |
| price | optional | Required if order_type=limit |

---

## Project File Structure
```
main.py                           Entry point (gunicorn imports app)
app.py                            Flask factory
requirements.txt                  All Python deps
Procfile                          Railway start command
railway.json                      Railway deploy config
runtime.txt                       Python 3.11
.env.example                      Template for local dev
test_bot.py                       29 unit tests — all passing ✅

core/
  config.py                       All settings from env vars
  database.py                     SQLite — trades, webhook_log, closed_positions
  logger.py                       Centralised logging
  telegram.py                     Telegram alert functions
  excel_export.py                 Excel export (trades + P&L summary)
  analyzer.py                     Analyzer Pro — RSI/MACD/ADX/BB/EMA50/VWAP

brokers/
  alpaca_adapter.py               Alpaca REST API wrapper + symbol validation

webhook/
  handler.py                      Signal processor (validate → risk → execute → alert)
  routes.py                       POST /webhook + GET /health

dashboard/
  routes.py                       All web routes (account, positions, close, export, research)
  templates/
    login.html                    Password login page
    dashboard.html                6-tab dashboard (1012 lines)

research/
  sec_filings.py                  SEC EDGAR 13F institutional tracker
  earnings.py                     Earnings whiplash scanner
  sector_rotation.py              Sector rotation detector
  insider_flow.py                 Insider buys + unusual options flow
```

---

## Tests
29 unit tests — all passing ✅
- Config: 4 tests
- Database: 4 tests
- Webhook Handler: 9 tests (buy, sell, flip, wrong secret, bad action, zero qty, max size, missing symbol, kill switch)
- Flask Routes: 6 tests
- Symbol Validation: 6 tests

---

## Indicators Analysed from OptiTrade AI
| File | Type | Best For |
|------|------|----------|
| OptiTrade_2_0_Buy-Sell_Strategy.txt | Flip — BUY flips to SELL | ✅ Full automation |
| OptiTrade_2_0_HWR_Strategy.txt | Trend with separate exits | Automation with 4 alerts |
| OptiTrade_2_0_TP-SL_Strategy.txt | Entry + 4 TPs + SL | Entry only automation |
| Analyzer_Pro.txt | Multi-TF multi-indicator scanner | Replicated in Python as Analyzer Pro tab |

---

## Telegram Setup (Quick)
1. Message @BotFather → /newbot → copy token
2. Message @userinfobot → copy chat_id
3. Add to Railway: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
4. Dashboard → Settings → Test Telegram

---

## Railway Deploy (Quick)
1. railway.app → New Project → Deploy from GitHub → select trading-bot repo
2. Settings → Variables → add all env vars above
3. Settings → Domains → copy URL
4. URL/webhook = your TradingView webhook address

---

## Known Limitations
- yfinance data: Analyzer Pro + Research tabs need live internet (works on Railway, blocked in sandbox)
- SEC 13F data: 45-day lag (reflects previous quarter holdings)
- Earnings IV: requires active options market (most liquid US stocks)
- Alpaca: US stocks/ETFs only (no Indian stocks — use Dhan for those)

---

## Suggested Future Features (Phase 4)
- [ ] Scheduled market-hours guard (9:30–16:00 ET only)
- [ ] Daily loss limit auto-halt (env var set, logic partially done)
- [ ] Position sizing by % of account equity instead of fixed qty
- [ ] Multi-account support (paper + live simultaneously)
- [ ] Price alert system (notify on breakout levels)
- [ ] Backtest viewer — show OptiTrade signal history on chart
- [ ] Auto-TP/SL orders placed on Alpaca after entry
- [ ] WhatsApp/Discord alerts (in addition to Telegram)
- [ ] AI trade journal — auto-summarise week's trades with lessons
- [ ] Watchlist with price target tracking
