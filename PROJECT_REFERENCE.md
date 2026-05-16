# PROJECT REFERENCE — OptiTrade AI → Alpaca Trading Bot v4 (FINAL)
*Share this file with Claude in any future session to resume exactly where we left off.*

---

## What This Does
Full-stack automated trading bot:
- Receives BUY/SELL signals from TradingView (OptiTrade AI) via webhooks
- Places orders automatically on Alpaca paper/live account
- 6-tab web dashboard to monitor, control, research
- Telegram alerts on every trade + bot commands (/positions /pnl /close AAPL etc)
- Analyzer Pro: real-time RSI/MACD/ADX/BB/EMA50/VWAP scanner (pure Python, yfinance)
- Research engine: 13F institutional, earnings whiplash, sector rotation, insider+options
- Excel export of all trades and P&L

---

## GitHub
https://github.com/ambrose2107/trading-bot

---

## Tech Stack
| Layer | Tech |
|-------|------|
| Language | Python 3.11 |
| Framework | Flask 3.0 |
| Database | SQLite (trades.db) |
| Broker | Alpaca Markets API |
| Market Data | Yahoo Finance (via yfinance + direct API) — FREE, no key needed |
| SEC Data | SEC EDGAR public API — FREE |
| Hosting | Railway (24/7) |
| Dev | Replit |
| Signals | TradingView + OptiTrade AI indicator |
| Notifications | Telegram Bot API |
| Export | openpyxl (Excel) |
| Charts | Chart.js (CDN, no install) |

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
```

---

## File Structure
```
main.py                           Entry point (gunicorn: main:app)
app.py                            Flask app factory
requirements.txt                  All deps (flask, yfinance, pandas, openpyxl...)
Procfile                          Railway deploy command
railway.json                      Railway config
.env.example                      Copy to .env for local dev
test_bot.py                       29 unit tests — all passing ✅

core/
  config.py                       All settings from env vars
  database.py                     SQLite — trades, webhook_log, closed_positions tables
  logger.py                       Centralised logging
  telegram.py                     Telegram alerts + bot message sender
  excel_export.py                 3-sheet Excel export
  analyzer.py                     Analyzer Pro — pure Python RSI/MACD/ADX/BB/EMA50/VWAP
  data_engine.py                  Free data layer — Yahoo Finance v8 API, SEC EDGAR

brokers/
  alpaca_adapter.py               Alpaca REST API — buy/sell/close/positions/validate

webhook/
  handler.py                      Signal processor: validate → risk check → execute → alert
  routes.py                       POST /webhook  GET /health

dashboard/
  routes.py                       All 25+ API routes + Telegram bot command handler
  templates/
    login.html                    Password login page
    dashboard.html                Full 6-tab dashboard (1115 lines)

research/
  sec_filings.py                  SEC EDGAR 13F institutional tracker (free API)
  earnings.py                     Earnings whiplash: HV vs IV scanner
  sector_rotation.py              30-day sector return comparison vs 1yr ago
  insider_flow.py                 SEC Form 4 insider buys + unusual options flow
```

---

## Dashboard Tabs
| Tab | Features |
|-----|----------|
| Dashboard | Account stats, kill switch, webhook URL, signal log, Export Excel |
| Positions | Open positions with P&L, close selected (full or partial qty) |
| History | P&L summary, closed positions with booked P&L, all trades, Excel download |
| Analyzer Pro | Signal grid (RSI/MACD/ADX/BB/EMA50/VWAP), price charts, compare tab |
| Research | 13F institutional, earnings whiplash, sector rotation, insider+options |
| Settings | Env var reference, Telegram setup guide, TradingView JSON template |

---

## Analyzer Pro — How It Works
- Pure Python math (no pandas needed for indicators)
- Fetches OHLCV from Yahoo Finance v8 API (free, no auth)
- Calculates all 6 indicators from raw price data
- Scores each indicator 1-11 (1=strong bull, 11=strong bear)
- Averages scores → Overall signal per timeframe
- Color-coded grid: green=bull, red=bear, grey=neutral
- Charts tab: price chart per symbol (Chart.js)
- Compare tab: normalised % return comparison across stocks

---

## Research — Data Sources (All Free)
| Feature | Source |
|---------|--------|
| Institutional 13F | SEC EDGAR submissions API (data.sec.gov) |
| Holdings detail | SEC EDGAR Archives (XML parsing) |
| Earnings dates | Yahoo Finance quoteSummary API |
| Historical volatility | Calculated from Yahoo price data |
| Implied volatility | Yahoo Finance options chain |
| Sector ETF returns | Yahoo Finance chart API (XLK, XLV, etc.) |
| ETF money flow | Price × Volume from Yahoo Finance |
| Unusual options | Yahoo Finance options chain (vol/OI ratio) |
| Insider purchases | SEC EDGAR EFTS full-text search |

---

## TradingView Setup
**OptiTrade 2.0 Buy-Sell — Long Entry box:**
```json
{"secret":"my_secret_123","symbol":"AAPL","action":"buy","quantity":1,"order_type":"market"}
```
**Short Entry box:**
```json
{"secret":"my_secret_123","symbol":"AAPL","action":"sell","quantity":1,"order_type":"market"}
```
**Alert message:** `{{strategy.order.alert_message}}`
**Webhook URL:** `https://YOUR-RAILWAY-URL/webhook`

---

## Telegram Bot Commands
After deploying: `curl "https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://YOUR-URL/telegram/webhook"`
| Command | What it does |
|---------|-------------|
| /positions | Live open positions with P&L |
| /pnl | Win rate, total P&L, best/worst |
| /account | Portfolio balance |
| /close AAPL | Close one stock |
| /closeall | Emergency close all |

---

## Tests
29 tests, all passing:
- Config (4), Database (4), Webhook Handler (9), Flask Routes (6), Symbol Validation (6)

---

## Railway Deploy
1. railway.app → New Project → GitHub → select repo
2. Variables tab → add all env vars above
3. Deploy → copy URL → use as webhook in TradingView

---

## Known Notes
- yfinance/Yahoo Finance works on Railway (all domains open). Blocked in sandbox only.
- SEC EDGAR works on Railway. Some holdings XML parsing may vary by fund.
- 13F filings are 45 days delayed (reflect previous quarter).
- Analyzer Pro automatically uses whatever timeframes are checked.

---

## Planned Phase 5
- [ ] Market hours guard (only trade 9:30-16:00 ET)
- [ ] Daily loss limit auto-halt
- [ ] Position sizing by % of account equity
- [ ] Price alert watchlist
- [ ] AI trade journal (weekly summary)
- [ ] WhatsApp / Discord alerts
- [ ] Backtest viewer tab
