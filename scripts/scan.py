#!/usr/bin/env python3
"""
ST Weekly Screener — saves data/screener_results.json
SuperTrend(10,2) trigger + SuperTrend(10,2.5) trend judge on weekly chart
3 quality filters: Monthly ST, RSI>50, within 30% of 52W high
"""
import yfinance as yf, pandas as pd, numpy as np
import json, concurrent.futures, warnings
from datetime import datetime, timezone, timedelta
warnings.filterwarnings("ignore")
IST = timezone(timedelta(hours=5, minutes=30))

NIFTY100 = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS",
    "LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS",
    "TITAN.NS","NESTLEIND.NS","WIPRO.NS","ULTRACEMCO.NS","BAJFINANCE.NS",
    "HCLTECH.NS","TECHM.NS","ONGC.NS","NTPC.NS","POWERGRID.NS",
    "BAJAJFINSV.NS","INDUSINDBK.NS","TATAMOTORS.NS","TATASTEEL.NS",
    "ADANIENT.NS","ADANIPORTS.NS","COALINDIA.NS","JSWSTEEL.NS",
    "HINDALCO.NS","CIPLA.NS","DRREDDY.NS","EICHERMOT.NS","GRASIM.NS",
    "HEROMOTOCO.NS","BRITANNIA.NS","APOLLOHOSP.NS","BPCL.NS",
    "TATACONSUM.NS","DIVISLAB.NS","BAJAJ-AUTO.NS","SBILIFE.NS",
    "HDFCLIFE.NS","SHRIRAMFIN.NS","LTIM.NS","M&M.NS",
    "ADANIGREEN.NS","AMBUJACEM.NS","AUROPHARMA.NS","BANKBARODA.NS",
    "BERGEPAINT.NS","BOSCHLTD.NS","CANBK.NS","CHOLAFIN.NS",
    "COLPAL.NS","DABUR.NS","DLF.NS","DMART.NS","GODREJCP.NS",
    "HAVELLS.NS","ICICIPRULI.NS","INDUSTOWER.NS","IRCTC.NS",
    "JINDALSTEL.NS","LUPIN.NS","MARICO.NS","NMDC.NS","NAUKRI.NS",
    "OFSS.NS","PAGEIND.NS","PIDILITIND.NS","PNB.NS","RECLTD.NS",
    "SAIL.NS","SIEMENS.NS","SRF.NS","TORNTPHARM.NS","TRENT.NS",
    "TVSMOTOR.NS","VEDL.NS","VOLTAS.NS","ZOMATO.NS","MOTHERSON.NS",
    "MUTHOOTFIN.NS","LICI.NS","GAIL.NS","IOC.NS","HPCL.NS",
    "CONCOR.NS","CAMS.NS"
]

def supertrend(high, low, close, period=10, mult=2.0):
    n = len(close)
    if n < period + 5:
        return np.full(n, np.nan), np.zeros(n, dtype=int)
    h,l,c = np.array(high),np.array(low),np.array(close)
    tr = np.zeros(n); tr[0] = h[0]-l[0]
    for i in range(1,n):
        tr[i] = max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))
    atr = np.zeros(n)
    for i in range(period-1,n):
        atr[i] = np.mean(tr[i-period+1:i+1])
    mid=(h+l)/2.0; ub_r=mid+mult*atr; lb_r=mid-mult*atr
    ub,lb=ub_r.copy(),lb_r.copy()
    for i in range(1,n):
        ub[i]=ub_r[i] if (ub_r[i]<ub[i-1] or c[i-1]>ub[i-1]) else ub[i-1]
        lb[i]=lb_r[i] if (lb_r[i]>lb[i-1] or c[i-1]<lb[i-1]) else lb[i-1]
    st=np.zeros(n); d=np.zeros(n,dtype=int)
    st[0]=ub[0]; d[0]=-1
    for i in range(1,n):
        if st[i-1]==ub[i-1]:
            st[i]=lb[i] if c[i]>ub[i] else ub[i]; d[i]=1 if c[i]>ub[i] else -1
        else:
            st[i]=ub[i] if c[i]<lb[i] else lb[i]; d[i]=-1 if c[i]<lb[i] else 1
    return st,d

def calc_rsi(close,p=14):
    s=pd.Series(close); dif=s.diff()
    g=dif.where(dif>0,0.0); ls=-dif.where(dif<0,0.0)
    rs=g.rolling(p).mean()/ls.rolling(p).mean().replace(0,np.nan)
    return (100-100/(1+rs)).values

RANK={"FRESH ENTRY":0,"RE-ENTRY":1,"RE-ENTRY READY":2,
      "BULLISH":3,"SOFT EXIT":4,"TREND BROKEN":5,"BEARISH":6}

def classify(d20,d25,dm,rsi_v,pct52):
    if len(d20)<2 or len(d25)<2: return "BEARISH",0,False,False,False
    c20,p20=int(d20[-1]),int(d20[-2]); c25,p25=int(d25[-1]),int(d25[-2])
    cm=int(dm[-1]) if len(dm)>0 else -1
    f1=cm==1; f2=float(rsi_v)>50 if not np.isnan(rsi_v) else False
    f3=float(pct52)<=30.0; fc=int(f1)+int(f2)+int(f3)
    fresh=c25==1 and p25==-1; bull20=c20==1 and p20==-1
    bear20=c20==-1 and p20==1; bear25=c25==-1 and p25==1
    if   fresh:              sig="FRESH ENTRY"
    elif bear25:             sig="TREND BROKEN"
    elif bull20 and c25==1:  sig="RE-ENTRY"
    elif bear20 and c25==1:  sig="SOFT EXIT"
    elif c25==1 and c20==1:  sig="BULLISH"
    elif c25==1 and c20==-1: sig="RE-ENTRY READY"
    else:                    sig="BEARISH"
    return sig,fc,f1,f2,f3

def analyse(sym):
    try:
        tk=yf.Ticker(sym)
        wk=tk.history(period="3y",interval="1wk",auto_adjust=True)
        mo=tk.history(period="5y",interval="1mo",auto_adjust=True)
        if len(wk)<30 or len(mo)<15: return None
        st20,d20=supertrend(wk.High,wk.Low,wk.Close,10,2.0)
        st25,d25=supertrend(wk.High,wk.Low,wk.Close,10,2.5)
        _,dm    =supertrend(mo.High,mo.Low,mo.Close,10,2.0)
        rsi_arr=calc_rsi(wk.Close.values,14)
        rsi_v=float(rsi_arr[-1]) if not np.isnan(rsi_arr[-1]) else 0.0
        price=float(wk.Close.iloc[-1])
        h52=float(wk.High.rolling(52).max().iloc[-1])
        pct52=round((1-price/h52)*100,1) if h52>0 else 100.0
        sig,fc,f1,f2,f3=classify(d20,d25,dm,rsi_v,pct52)
        name=sym.replace(".NS","")
        print(f"  {name:<15} {sig}")
        return {"symbol":name,"price":round(price,1),"signal":sig,
                "rank":RANK.get(sig,7),"quality":fc,
                "f1":f1,"f2":f2,"f3":f3,"rsi":round(rsi_v,1),
                "pct52w":pct52,"st25":round(float(st25[-1]),1),
                "st20":round(float(st20[-1]),1),
                "dir25":int(d25[-1]),"dir20":int(d20[-1])}
    except Exception as e:
        print(f"  {sym:<20} SKIP: {e}"); return None

def main():
    now=datetime.now(IST)
    print(f"\nST SCREENER  {now.strftime('%d %b %Y  %H:%M IST')}\n")
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(analyse,s):s for s in NIFTY100}
        for fut in concurrent.futures.as_completed(futs):
            r=fut.result()
            if r: results.append(r)
    results.sort(key=lambda x:(x["rank"],-x["quality"],x["symbol"]))
    counts={}
    for r in results: counts[r["signal"]]=counts.get(r["signal"],0)+1
    print(f"\nDone: {len(results)} stocks")
    for s,c in sorted(counts.items(),key=lambda x:RANK.get(x[0],9)):
        print(f"  {s:<20} {c}")
    import os; os.makedirs("data",exist_ok=True)
    json.dump({"scan_time":now.strftime("%d %b %Y  %H:%M IST"),
               "total_scanned":len(results),"counts":counts,"results":results},
              open("data/screener_results.json","w"),indent=2)
    print("Saved data/screener_results.json")

if __name__=="__main__":
    main()
