#!/usr/bin/env python3
"""
NSE Risk Monitor — Slow factor computation
Runs via GitHub Actions twice daily (pre-market + intraday).
Outputs: data/risk_factors.json

FIXES vs v1:
  - Wilder's smoothed RSI (matches Kite / TradingView exactly)
  - 2-year download for RSI warmup (was 6mo — caused high RSI bias)
  - 1-year download for core indices (macro INR range needs 252 bars)
  - No f-string backslash syntax (Python 3.11 compatible throughout)
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ── Configuration ──────────────────────────────────────────────────────────────
PERIOD_RSI     = "2y"   # sectors: ~500 bars for proper Wilder warmup
PERIOD_CORE    = "1y"   # core: 252 bars for INR 1Y range
PERIOD_BREADTH = "3mo"  # breadth: only needs 50 bars
DELAY = 0.5             # seconds between yfinance calls

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

def wilder_rsi(series, n=14):
    """
    Wilder's Smoothed RSI — matches Kite and TradingView exactly.
    Requires 2y of data for stable convergence (500+ bars).
    """
    series = series.dropna()
    if len(series) < n + 1:
        return 50.0

    delta  = series.diff().dropna()
    gains  = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    # Seed: simple mean of first n periods (Wilder's original spec)
    avg_gain = float(gains.iloc[:n].mean())
    avg_loss = float(losses.iloc[:n].mean())

    # Wilder's smoothing: multiplier = 1/n (NOT 2/(n+1) like standard EMA)
    for i in range(n, len(gains)):
        avg_gain = (avg_gain * (n - 1) + float(gains.iloc[i])) / n
        avg_loss = (avg_loss * (n - 1) + float(losses.iloc[i])) / n

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - 100.0 / (1.0 + rs), 2)


def sma(series, n):
    tail = series.tail(n)
    if len(tail) < n:
        return float(series.mean())
    return float(tail.mean())


def ema_last(series, n):
    series = series.dropna()
    if len(series) == 0:
        return 0.0
    k = 2.0 / (n + 1)
    v = float(series.iloc[0])
    for x in series.iloc[1:]:
        v = float(x) * k + v * (1 - k)
    return v


def pct_chg(series, n):
    if len(series) < n + 1:
        return 0.0
    return float((series.iloc[-1] / series.iloc[-(n + 1)] - 1) * 100)


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(round(float(v)))))


# ── Download helpers ───────────────────────────────────────────────────────────

def dl(ticker, period):
    try:
        raw = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            return pd.Series(dtype=float)
        col = raw["Close"]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]
        s = col.dropna()
        print("  dl " + ticker + ": " + str(len(s)) + " bars")
        return s
    except Exception as e:
        print("  WARNING dl(" + ticker + "): " + str(e))
        return pd.Series(dtype=float)


def dl_batch(tickers, period):
    try:
        raw = yf.download(tickers, period=period, progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            return pd.DataFrame()
        close = raw["Close"]
        if isinstance(close, pd.Series):
            close = close.to_frame(name=tickers[0])
        return close.dropna(how="all")
    except Exception as e:
        print("  WARNING dl_batch: " + str(e))
        return pd.DataFrame()


# ── Breadth factor ─────────────────────────────────────────────────────────────

def compute_breadth():
    print("Computing breadth factor...")
    above20 = []
    above50 = []

    for i in range(0, len(BREADTH_TICKERS), 10):
        batch = BREADTH_TICKERS[i: i + 10]
        frame = dl_batch(batch, PERIOD_BREADTH)
        for ticker in batch:
            if ticker not in frame.columns:
                continue
            s = frame[ticker].dropna()
            if len(s) >= 50:
                above20.append(1 if s.iloc[-1] > sma(s, 20) else 0)
                above50.append(1 if s.iloc[-1] > sma(s, 50) else 0)
        time.sleep(DELAY)

    pct20 = float(np.mean(above20) * 100) if above20 else 50.0
    pct50 = float(np.mean(above50) * 100) if above50 else 50.0
    score = clamp(pct20 * 0.6 + pct50 * 0.4)

    print("  Breadth: " + str(round(pct20, 1)) + "% above 20-MA, "
          + str(round(pct50, 1)) + "% above 50-MA -> score " + str(score))
    return {
        "score": score,
        "raw": {
            "pct_above_20ma": round(pct20, 1),
            "pct_above_50ma": round(pct50, 1),
            "stocks_sampled": len(above20),
        },
    }


# ── FII proxy factor ───────────────────────────────────────────────────────────

def compute_fii_proxy(inr, nifty, midcap):
    inr_chg20 = pct_chg(inr, 20) if len(inr) >= 21 else 0.0
    inr_score = clamp(50 - inr_chg20 * 5)

    ratio_chg = 0.0
    risk_on_score = 50
    if len(nifty) >= 21 and len(midcap) >= 21:
        ratio_now = float(midcap.iloc[-1]) / float(nifty.iloc[-1])
        ratio_20d = float(midcap.iloc[-20]) / float(nifty.iloc[-20])
        ratio_chg = (ratio_now / ratio_20d - 1) * 100
        risk_on_score = clamp(50 + ratio_chg * 10)

    score = clamp(inr_score * 0.5 + risk_on_score * 0.5)
    print("  FII proxy: INR_chg=" + str(round(inr_chg20, 2))
          + "%, ratio_chg=" + str(round(ratio_chg, 2)) + "% -> score " + str(score))
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

def compute_macro(inr, vix):
    tail252 = inr.tail(252) if len(inr) >= 252 else inr
    mn = float(tail252.min())
    mx = float(tail252.max())
    inr_rng = mx - mn
    if inr_rng > 0:
        inr_pct = float((inr.iloc[-1] - mn) / inr_rng * 100)
    else:
        inr_pct = 50.0
    inr_score = clamp(100 - inr_pct)

    if len(vix) >= 20:
        vix_avg = float(vix.tail(20).mean())
    elif len(vix) > 0:
        vix_avg = float(vix.mean())
    else:
        vix_avg = 16.0

    if vix_avg < 12:
        vix_score = 90
    elif vix_avg < 15:
        vix_score = 75
    elif vix_avg < 20:
        vix_score = 55
    elif vix_avg < 25:
        vix_score = 35
    else:
        vix_score = 15

    score = clamp(inr_score * 0.4 + vix_score * 0.6)
    print("  Macro: INR_pct_range=" + str(round(inr_pct, 1))
          + "%, VIX_20d_avg=" + str(round(vix_avg, 2)) + " -> score " + str(score))
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

def compute_sectors():
    print("Computing sector data (2y download for accurate RSI)...")
    sectors = {}

    for name, ticker in SECTOR_TICKERS.items():
        s = dl(ticker, PERIOD_RSI)
        if len(s) < 50:
            print("  WARNING " + name + ": only " + str(len(s)) + " bars, skipping")
            continue

        price   = float(s.iloc[-1])
        ma20    = sma(s, 20)
        ma50    = sma(s, 50)
        above20 = price > ma20
        above50 = price > ma50
        chg1d   = pct_chg(s, 1)
        chg5d   = pct_chg(s, 5)
        chg20d  = pct_chg(s, 20)

        # Wilder RSI using full 2y history
        rsi14 = wilder_rsi(s, 14)

        # Score: trend 70 pts + RSI 30 pts
        trend_pts = (40 if above20 else 0) + (30 if above50 else 0)
        rsi_pts   = max(0.0, min(30.0, (rsi14 - 30.0) * 30.0 / 40.0))
        score     = clamp(trend_pts + rsi_pts)

        sectors[name] = {
            "score":      score,
            "change_1d":  round(chg1d, 2),
            "change_5d":  round(chg5d, 2),
            "change_20d": round(chg20d, 2),
            "rsi":        round(rsi14, 1),
            "above_20ma": bool(above20),
            "above_50ma": bool(above50),
            "price":      round(price, 2),
            "ma20":       round(ma20, 2),
            "ma50":       round(ma50, 2),
        }

        print("  " + name + ": RSI=" + str(round(rsi14, 1))
              + " above20=" + str(above20)
              + " above50=" + str(above50)
              + " score=" + str(score))
        time.sleep(DELAY)

    return sectors


# ── Market context ─────────────────────────────────────────────────────────────

def compute_market_context(nifty, vix, inr):
    if len(nifty) < 20:
        return {}
    ctx = {
        "nifty_ema20":  round(ema_last(nifty, 20), 2),
        "nifty_ema50":  round(ema_last(nifty, min(50, len(nifty))), 2),
        "nifty_ema200": round(ema_last(nifty, min(200, len(nifty))), 2),
        "nifty_bars":   len(nifty),
    }
    if len(vix) >= 20:
        ctx["vix_20d_avg"] = round(float(vix.tail(20).mean()), 2)
    if len(inr) > 0:
        ctx["inr_current"] = round(float(inr.iloc[-1]), 4)
    return ctx


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("NSE Risk Monitor -- fetch_risk_data.py")
    print("Run time: " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 60)

    print("Downloading core indices (1y)...")
    core_tickers = ["^NSEI", "^NSMIDCP", "USDINR=X", "^INDIAVIX"]
    core_frame = dl_batch(core_tickers, PERIOD_CORE)
    time.sleep(DELAY)

    def get_col(sym):
        if sym in core_frame.columns:
            return core_frame[sym].dropna()
        return pd.Series(dtype=float)

    nifty_s  = get_col("^NSEI")
    midcap_s = get_col("^NSMIDCP")
    inr_s    = get_col("USDINR=X")
    vix_s    = get_col("^INDIAVIX")

    print("  Nifty bars : " + str(len(nifty_s)))
    print("  Midcap bars: " + str(len(midcap_s)))
    print("  INR bars   : " + str(len(inr_s)))
    print("  VIX bars   : " + str(len(vix_s)))

    breadth = compute_breadth()
    fii     = compute_fii_proxy(inr_s, nifty_s, midcap_s)
    macro   = compute_macro(inr_s, vix_s)
    sectors = compute_sectors()
    context = compute_market_context(nifty_s, vix_s, inr_s)

    now = datetime.now(timezone.utc)
    output = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "next_update":  (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
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

    print("\nWrote data/risk_factors.json")
    print("  Breadth score : " + str(breadth["score"]))
    print("  FII proxy     : " + str(fii["score"]))
    print("  Macro         : " + str(macro["score"]))
    parts = []
    for k, v in sectors.items():
        parts.append(k + "=" + str(v["score"]) + "(RSI " + str(v["rsi"]) + ")")
    print("  Sectors       : " + ", ".join(parts))


if __name__ == "__main__":
    main()
