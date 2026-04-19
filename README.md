# NSE Risk Monitor — Drop-in PWA

Real-time Indian equity market risk dashboard hosted on GitHub Pages, installable as a mobile app.

---

## Files to drop into your repo root

```
your-repo/
├── index.html                          ← Main app (replace or add)
├── manifest.json                       ← PWA manifest
├── sw.js                               ← Service worker (offline support)
├── icon-192.png                        ← App icon
├── icon-512.png                        ← App icon (large)
├── .github/
│   └── workflows/
│       └── risk-data.yml               ← Scheduled data fetch (add to existing or create)
├── scripts/
│   └── fetch_risk_data.py              ← Python script run by Actions
└── data/
    └── risk_factors.json               ← Seed data (overwritten by Actions)
```

---

## One-time GitHub setup (do this once)

### 1. Enable GitHub Pages
`Settings → Pages → Source: Deploy from branch → Branch: main → Folder: / (root)`

### 2. Allow Actions to commit
`Settings → Actions → General → Workflow permissions → Read and write permissions ✓`

### 3. Push all files and trigger the first run
```bash
git add .
git commit -m "feat: NSE Risk Monitor PWA"
git push
```
Then go to `Actions` tab → `Update Risk Data` → `Run workflow` to populate live data immediately.

---

## Install as mobile app

**Android (Chrome)**  
Open your GitHub Pages URL → three-dot menu → `Add to Home screen`

**iOS (Safari)**  
Open your GitHub Pages URL → Share button → `Add to Home Screen`

---

## How it works

| Layer | What | When |
|-------|------|-------|
| Client-side (JS) | Nifty 50, Bank Nifty, India VIX, INR/USD via Yahoo Finance + CORS proxy chain | Every 60 s |
| GitHub Actions (Python) | Market breadth (% of 50 Nifty 100 stocks above 20-MA), FII proxy (INR momentum + midcap/largecap divergence), Macro stability (INR vs 1Y range + VIX avg), All 10 sector scores | 6:30 AM & 1:00 PM IST, Mon–Fri |

### Factor weights
| Factor | Weight | Source |
|--------|--------|--------|
| India VIX | 20% | Live |
| Trend Strength | 20% | Live |
| Price Momentum | 15% | Live |
| Market Breadth | 15% | Daily |
| FII Proxy | 15% | Daily |
| Macro Stability | 15% | Daily |

### Signal thresholds
| Score | Signal | Position size |
|-------|--------|--------------|
| 70–100 | ENTER | 100% |
| 50–69 | HOLD | 50% |
| 35–49 | REDUCE | 25% |
| 0–34 | EXIT | 0% |

---

## AI Analysis (optional)

Tap `⚙` → enter your Anthropic API key → stored in browser localStorage only.  
Tap `▶ AI ANALYSIS` on the Analysis tab for a Claude-generated risk brief.  
The rule-based narrative works without a key.

---

## Regenerate icons (if needed)
```bash
pip install Pillow
python scripts/gen_icons.py
# commits icon-192.png and icon-512.png
```
