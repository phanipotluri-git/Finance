#!/usr/bin/env python3
"""
NSE Risk Monitor — Slow factor computation
Runs via GitHub Actions twice daily (pre-market + intraday).
Outputs: data/risk_factors.json

Factors computed here (all derived from Yahoo Finance via yfinance):
  - breadth   : % of Nifty 100 sample stocks above 20-day & 50-day MA
  - fii_proxy : INR/USD momentum + midcap vs largecap relative strength
  - macro     : INR vs 1-year range + VIX 20-day average
  - sectors   : Per-sector risk score (trend + RSI) for 10 NSE sector indices
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ── Configuration ──────────────────────────────────────────────────────────────
PERIOD = "6mo"
DELAY  = 0.4   # seconds between yfinance calls to stay under rate limits

# Representative sample of Nifty 100 stocks for breadth calculation
# (50 stocks → fast enough for Actions, accurate enough for breadth proxy)
BREADTH_TICKERS = [
    "RELIANCE.NS",  "TCS.NS",       "HDFCBANK.NS",  "INFY.NS",      "HINDUNILVR.NS",
    "ICICIBANK.NS", "SBIN.NS",      "BHARTIARTL.NS","KOTAKBANK.NS", "ITC.NS",
    "LT.NS",        "AXISBANK.NS",  "ASIANPAINT.NS","BAJFINANCE.NS","MARUTI.NS",
    "WIPRO.NS",     "TITAN.NS",     "NESTLEIND.NS", "ULTRACEMCO.NS","HCLTECH.NS",
    "SUNPHARMA.NS", "ONGC.NS",      "POWERGRID.NS", "NTPC.NS",      "M&M.NS",
    "TATAMOTORS.NS","TECHM.NS",     "BAJAJFINSV.NS","DIVISLAB.NS",  "CIPLA.NS",
    "ADANIENT.NS",  "JSWSTEEL.NS",  "TATASTEEL.NS", "GRASIM.NS",    "INDUSINDBK.NS",
    "BPCL.NS",      "EICHERMOT.NS", "HEROMOTOCO.NS","BRITANNIA.NS", "APOLLOHOSP.NS",
    "DRREDDY.NS",   "COALINDIA.NS", "HINDALCO.NS",  "ADANIPORTS.NS","SBILIFE.NS",
    "HDFCLIFE.NS",  "BAJAJ-AUTO.NS","SHREECEM.NS",  "UPL.NS",       "PIDILITIND.NS",
]

# NSE sector indices (Yahoo Finance tickers)
SECTOR_TICKERS = {
    "Nifty 50":   "^NSEI",
    "Bank Nifty": "^NSEBANK",
    "IT":         "^CNXIT",
    "Pharma":     "^CNXPHARMA",
    "Auto":       "^CNXAUTO",
    "FMCG":       "^CNXFMCG",
    "Metal":      "^CNXMETAL",
    "Realty":     "^CNXREALTY",
    "Energy":     "^CNXENERGY",
    "Infra":      "^CNXINFRA",
}

# ── Math helpers ───────────────────────────────────────────────────────────────
def ema(series: pd.Series, n: int) -> float:
    k = 2 / (n + 1)
    v = float(series.iloc[0])
    for x in series.iloc[1:]:
        v = float(x) * k + v * (1 - k)
    return v


def rsi_val(series: pd.Series, n: int = 14) -> float:
    """Wilder's smoothed RSI — matches Kite/TradingView exactly."""
    delta = series.diff().dropna()
    if len(delta) < n + 1:
        return 50.0

    gains  = delta.clip(lower=0)
    losses = (-delta.clip(upper=0))

    # First average: simple mean of first n periods
    avg_gain = gains.iloc[:n].mean()
    avg_loss = losses.iloc[:n].mean()

    # Wilder's smoothing for remaining periods
    for i in range(n, len(gains)):
        avg_gain = (avg_gain * (n - 1) + gains.iloc[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses.iloc[i]) / n

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def pct_chg(series: pd.Series, n: int) -> float:
    if len(series) < n + 1:
        return 0.0
    return float((series.iloc[-1] / series.iloc[-n - 1] - 1) * 100)


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(round(v))))


# ── Download helpers ───────────────────────────────────────────────────────────
def dl(ticker: str, period: str = PERIOD) -> pd.Series:
    """Download Close prices for a single ticker, return as pd.Series."""
    try:
        raw = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            return pd.Series(dtype=float)
        col = raw["Close"]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]
        return col.dropna()
    except Exception as e:
        print(f"  ⚠  dl({ticker}): {e}")
        return pd.Series(dtype=float)


def dl_batch(tickers: list, period: str = PERIOD) -> pd.DataFrame:
    """Download Close prices for multiple tickers in one call."""
    try:
        raw = yf.download(tickers, period=period, progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            return pd.DataFrame()
        close = raw["Close"]
        if isinstance(close, pd.Series):
            close = close.to_frame(name=tickers[0])
        return close.dropna(how="all")
    except Exception as e:
        print(f"  ⚠  dl_batch: {e}")
        return pd.DataFrame()


# ── Breadth factor ─────────────────────────────────────────────────────────────
def compute_breadth() -> dict:
    print("Computing breadth factor…")
    above20, above50 = [], []
    batch_size = 10

    for i in range(0, len(BREADTH_TICKERS), batch_size):
        batch = BREADTH_TICKERS[i : i + batch_size]
        frame = dl_batch(batch)
        for ticker in batch:
            col = ticker if ticker in frame.columns else None
            if col is None:
                continue
            s = frame[col].dropna()
            if len(s) >= 50:
                above20.append(1 if s.iloc[-1] > s.tail(20).mean() else 0)
                above50.append(1 if s.iloc[-1] > s.tail(50).mean() else 0)
        time.sleep(DELAY)

    pct20 = float(np.mean(above20) * 100) if above20 else 50.0
    pct50 = float(np.mean(above50) * 100) if above50 else 50.0
    combined = pct20 * 0.6 + pct50 * 0.4
    score = clamp(combined)

    print(f"  Breadth: {pct20:.1f}% above 20-MA, {pct50:.1f}% above 50-MA → score {score}")
    return {
        "score": score,
        "raw": {
            "pct_above_20ma": round(pct20, 1),
            "pct_above_50ma": round(pct50, 1),
            "stocks_sampled": len(above20),
        },
    }


# ── FII proxy factor ───────────────────────────────────────────────────────────
def compute_fii_proxy(inr: pd.Series, nifty: pd.Series, midcap: pd.Series) -> dict:
    """
    Two components:
      1. USD/INR 20-day momentum — strengthening INR (falling USDINR) → FII inflows
      2. Nifty Midcap vs Nifty 50 ratio trend — rising ratio = risk-on = FII buying
    """
    # Component 1: INR momentum
    inr_chg20 = pct_chg(inr, 20) if len(inr) >= 21 else 0.0
    inr_score  = clamp(50 - inr_chg20 * 5)   # INR strength → higher score

    # Component 2: midcap/largecap ratio 20-day change
    risk_on_score = 50
    ratio_chg = 0.0
    if len(nifty) >= 21 and len(midcap) >= 21:
        ratio_now = midcap.iloc[-1] / nifty.iloc[-1]
        ratio_20d = midcap.iloc[-20] / nifty.iloc[-20]
        ratio_chg = float((ratio_now / ratio_20d - 1) * 100)
        risk_on_score = clamp(50 + ratio_chg * 10)

    score = clamp(inr_score * 0.5 + risk_on_score * 0.5)
    print(f"  FII proxy: INR_chg={inr_chg20:.2f}%, ratio_chg={ratio_chg:.2f}% → score {score}")
    return {
        "score": score,
        "raw": {
            "inr_20d_chg_pct": round(inr_chg20, 2),
            "midcap_vs_largecap_20d_chg": round(ratio_chg, 2),
            "inr_component": inr_score,
            "risk_on_component": risk_on_score,
        },
    }


# ── Macro stability factor ─────────────────────────────────────────────────────
def compute_macro(inr: pd.Series, vix: pd.Series) -> dict:
    """
    Two components:
      1. INR vs its 1-year range — stronger INR → better macro
      2. VIX 20-day average — sustained low VIX → stable macro
    """
    # Component 1: INR vs 1Y range
    tail252 = inr.tail(252) if len(inr) >= 252 else inr
    mn, mx  = tail252.min(), tail252.max()
    inr_rng = mx - mn
    inr_pct = float((inr.iloc[-1] - mn) / inr_rng * 100) if inr_rng > 0 else 50.0
    inr_score = clamp(100 - inr_pct)   # lower USDINR (stronger INR) → higher score

    # Component 2: VIX 20-day average
    vix_avg = float(vix.tail(20).mean()) if len(vix) >= 20 else float(vix.mean()) if len(vix) else 16.0
    vix_score = (
        90 if vix_avg < 12 else
        75 if vix_avg < 15 else
        55 if vix_avg < 20 else
        35 if vix_avg < 25 else 15
    )

    score = clamp(inr_score * 0.4 + vix_score * 0.6)
    print(f"  Macro: INR_pct_range={inr_pct:.1f}%, VIX_20d_avg={vix_avg:.2f} → score {score}")
    return {
        "score": score,
        "raw": {
            "inr_vs_1y_range_pct": round(inr_pct, 1),
            "vix_20d_avg": round(vix_avg, 2),
            "inr_component": inr_score,
            "vix_component": vix_score,
        },
    }


# ── Sector data ────────────────────────────────────────────────────────────────
def compute_sectors() -> dict:
    print("Computing sector data…")
    sectors = {}
    for name, ticker in SECTOR_TICKERS.items():
        s = dl(ticker)
        if len(s) < 20:
            print(f"  ⚠  {name}: insufficient data ({len(s)} bars)")
            continue
        price   = float(s.iloc[-1])
        ma20    = float(s.tail(20).mean())
        ma50    = float(s.tail(min(50, len(s))).mean())
        chg1d   = pct_chg(s, 1)
        chg5d   = pct_chg(s, 5)
        chg20d  = pct_chg(s, 20)
        rsi14   = rsi_val(s, 14)
        above20 = price > ma20
        above50 = price > ma50

        # Score: trend (70 pts) + RSI (30 pts)
        trend_pts = (40 if above20 else 0) + (30 if above50 else 0)
        rsi_pts   = max(0.0, min(30.0, (rsi14 - 30) * 30 / 40))
        score     = clamp(trend_pts + rsi_pts)

        sectors[name] = {
            "score":     score,
            "change_1d": round(chg1d, 2),
            "change_5d": round(chg5d, 2),
            "change_20d":round(chg20d, 2),
            "rsi":       round(rsi14, 1),
            "above_20ma":bool(above20),
            "above_50ma":bool(above50),
            "price":     round(price, 2),
        }
        print(f"  {name}: score={score}, RSI={rsi14:.1f}, above20MA={above20}")
        time.sleep(DELAY)
    return sectors


# ── Market context (EMA anchors for client-side use) ──────────────────────────
def compute_market_context(nifty: pd.Series, vix: pd.Series, inr: pd.Series) -> dict:
    if len(nifty) < 20:
        return {}
    ctx = {
        "nifty_ema20":  round(ema(nifty, 20), 2),
        "nifty_ema50":  round(ema(nifty, min(50,  len(nifty))), 2),
        "nifty_ema200": round(ema(nifty, min(200, len(nifty))), 2),
    }
    if len(vix) >= 20: ctx["vix_20d_avg"]  = round(float(vix.tail(20).mean()), 2)
    if len(inr):        ctx["inr_current"] = round(float(inr.iloc[-1]), 4)
    return ctx


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("NSE Risk Monitor — fetch_risk_data.py")
    print(f"Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # Core downloads (batch for efficiency)
    print("Downloading core indices…")
    core_frame = dl_batch(["^NSEI", "^NSMIDCP", "USDINR=X", "^INDIAVIX"])
    time.sleep(DELAY)

    def get_col(sym):
        if sym in core_frame.columns:
            return core_frame[sym].dropna()
        return pd.Series(dtype=float)

    nifty_s  = get_col("^NSEI")
    midcap_s = get_col("^NSMIDCP")
    inr_s    = get_col("USDINR=X")
    vix_s    = get_col("^INDIAVIX")

    print(f"  Nifty bars: {len(nifty_s)}  Midcap: {len(midcap_s)}  INR: {len(inr_s)}  VIX: {len(vix_s)}")

    # Compute factors
    breadth = compute_breadth()
    fii     = compute_fii_proxy(inr_s, nifty_s, midcap_s)
    macro   = compute_macro(inr_s, vix_s)
    sectors = compute_sectors()
    context = compute_market_context(nifty_s, vix_s, inr_s)

    now = datetime.now(timezone.utc)
    output = {
        "generated_at":  now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "next_update":   (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "factors": {
            "breadth":   breadth,
            "fii_proxy": fii,
            "macro":     macro,
        },
        "sectors":        sectors,
        "market_context": context,
    }

    Path("data").mkdir(exist_ok=True)
    with open("data/risk_factors.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\n✓ Wrote data/risk_factors.json")
    print(f"  Breadth score : {breadth['score']}")
    print(f"  FII proxy     : {fii['score']}")
    print(f"  Macro         : {macro['score']}")
    sector_summary = ", ".join(str(k) + "=" + str(v["score"]) for k, v in sectors.items())
    print("  Sectors       : " + sector_summary)



if __name__ == "__main__":
    main()
