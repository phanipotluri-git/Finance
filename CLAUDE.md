# NSE Risk Monitor + ST Weekly Screener

## Project for Claude Code

-----

## What This Is

Two tools hosted on **GitHub Pages**, data updated by **GitHub Actions**, no server needed.

|Tool        |URL            |Purpose                                            |
|------------|---------------|---------------------------------------------------|
|Risk Monitor|`index.html`   |Live NSE risk score (0–100), position sizing signal|
|ST Screener |`screener.html`|Weekly SuperTrend stock scanner, Nifty 100         |

-----

## Repo Structure

```
repo-root/
├── CLAUDE.md                        ← you are here
├── index.html                       ← Risk Monitor PWA (main app)
├── screener.html                    ← ST Weekly Screener
├── manifest.json                    ← PWA manifest
├── sw.js                            ← Service worker (offline)
├── requirements.txt                 ← yfinance pandas numpy
├── icon-192.png                     ← App icons
├── icon-512.png
├── test.html                        ← Proxy diagnostics page
├── data/
│   ├── risk_factors.json            ← Written by fetch_risk_data.py
│   └── screener_results.json        ← Written by scan.py
├── scripts/
│   ├── fetch_risk_data.py           ← Risk Monitor data (breadth, FII, macro, sectors)
│   ├── scan.py                      ← ST Screener (SuperTrend signals for 90 stocks)
│   └── gen_icons.py                 ← One-time icon generator (needs Pillow)
├── phani/
│   ├── Dashscanner.html             ← DASH signal scanner (Yahoo Finance + CORS proxy)
│   ├── Backtest.html                ← DASH Daily vs Weekly backtester
│   ├── Fut.html                     ← F&O regime scanner
│   └── Ca.html                      ← Institutional 8-factor scanner
└── .github/workflows/
    ├── risk-data.yml                ← Runs fetch_risk_data.py (Mon-Fri 6:30AM, 10AM, 1PM IST)
    └── scan.yml                     ← Runs scan.py (Saturday 10:30AM IST)
```

-----

## Trading Systems

### Risk Monitor (`index.html`)

- **6 factors**: VIX (20%), Trend Strength (20%), Price Momentum (15%), Market Breadth (15%), FII Proxy (15%), Macro Stability (15%)
- **Live factors** (client-side, every 60s): VIX, Trend, Momentum via Yahoo Finance + CORS proxy chain
- **Daily factors** (GitHub Actions): Breadth, FII Proxy, Macro via `fetch_risk_data.py`
- **Output**: Composite score 0–100 → ENTER (70+) / HOLD (50–69) / REDUCE (35–49) / EXIT (<35)

### ST Weekly Screener (`screener.html` + `scripts/scan.py`)

- **Trend Judge**: SuperTrend(10, 2.5) on weekly chart — ST flip = trend actually changed
- **Trigger**: SuperTrend(10, 2.0) on weekly chart — for entries/exits within trend
- **Monthly filter**: ST(10, 2.0) on monthly chart (F1)
- **3 quality filters**: F1 Monthly ST bullish, F2 Weekly RSI(14) > 50, F3 Price within 30% of 52W high
- **Signal hierarchy**: FRESH ENTRY → RE-ENTRY → RE-ENTRY READY → BULLISH → SOFT EXIT → TREND BROKEN → BEARISH

### Options System (separate — runs on paper trading bot port 5000)

- **Entry**: Nifty 15-min closes above ST(10,2.5) → Bull Put Spread or Bear Call Spread
- **Spread**: 200-point width, 7 lots, next Tuesday expiry
- **Exit**: Index ST flip OR short-option price ST flip OR 70% premium decay

-----

## Key Technical Facts

- **Nifty 50 lot size**: 65 units (since January 2026)
- **Weekly expiry**: Tuesday (since September 2025)
- **Yahoo Finance**: NSE data has 15-minute delay by licensing — not fixable
- **CORS proxy chain**: corsproxy.io → allorigins → codetabs → thingproxy → cors.sh
- **GitHub Actions free tier**: Unlimited minutes for public repos
- **SEBI**: Kite Connect requires daily re-authentication (no full automation)

-----

## CORS Proxy Chain (used in all HTML tools)

```javascript
const PROXIES = [
  u => `https://corsproxy.io/?${encodeURIComponent(u)}`,
  u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
  u => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(u)}`,
  u => `https://thingproxy.freeboard.io/fetch/${u}`,
  u => `https://proxy.cors.sh/${u}`,
];
```

-----

## GitHub Actions Schedules

```yaml
# risk-data.yml — weekdays only
- cron: "0 1 * * 1-5"    # 6:30 AM IST
- cron: "30 4 * * 1-5"   # 10:00 AM IST
- cron: "30 7 * * 1-5"   # 1:00 PM IST

# scan.yml — weekly
- cron: "0 5 * * 6"      # Saturday 10:30 AM IST
```

-----

## Running Locally

```bash
# Test the risk data script
pip install yfinance pandas numpy
python scripts/fetch_risk_data.py

# Test the screener
python scripts/scan.py

# Serve locally to test HTML tools
python -m http.server 8080
# Open: http://localhost:8080/screener.html
#        http://localhost:8080/index.html
```

-----

## Design System

- **Background**: `#0a0c0f` (near black)
- **Surface**: `#0f1318`
- **Font**: JetBrains Mono (Google Fonts)
- **Accent**: `#f5a623` (amber) for primary actions
- **Green**: `#00d084` for bullish/positive
- **Red**: `#ff4757` for bearish/negative
- **Cyan**: `#00bcd4` for info/neutral
- All tools follow Bloomberg terminal dark aesthetic

-----

## Common Tasks for Claude Code

```
"Add XYZ stock to the NIFTY100 list in scripts/scan.py"
"Update the risk score thresholds in index.html"
"Add a new column to screener.html table"
"Fix the proxy detection in phani/Dashscanner.html"
"Commit and push all changes to GitHub"
"Run the screener locally and show me the output"
"Add a new workflow that runs scan.py on weekdays too"
```

-----

## GitHub Pages URL

`https://USERNAME.github.io/REPO-NAME/`

- Main app: `/index.html` (or just `/`)
- Screener: `/screener.html`
- Tools: `/phani/Dashscanner.html`, `/phani/Backtest.html`, etc.