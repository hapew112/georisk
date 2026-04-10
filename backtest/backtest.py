"""
backtest.py
GeoRisk Stress Backtest Engine — CLI Entry Point.
"""

import os
import json
import math
from datetime import date
from pathlib import Path

import config
from data_fetcher import fetch_all
from signals import compute_signals
from metrics import compute_forward_returns, compute_metrics, verdict

def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "item"): return obj.item()
    if isinstance(obj, float) and math.isnan(obj): return None
    return obj

def print_summary(result: dict):
    m = result["metrics"]
    
    def fmt_pct(v, decimals=1):
        if v is None: return "N/A"
        return f"{v * 100:.{decimals}f}%"

    def fmt_ret(v):
        if v is None: return "N/A"
        return f"{v:+.2f}%"

    print(f"\nGeoRisk Stress Backtest  ({result['data_range']}, {config.DATA_PERIOD})")
    print("━" * 55)
    
    # Signal Summary
    print(f"\nSignal Summary (threshold: stress>={config.SIGNAL_MIN_STRESS} + regime>={config.SIGNAL_MIN_REGIME} or stress>=3 or CRISIS)")
    print(f"  Signals fired:    {m.get('total_signals')} times")
    print(f"  Hit rate (3d):    {fmt_pct(m.get('hit_rate_3d'))}")
    print(f"  Hit rate (5d):    {fmt_pct(m.get('hit_rate_5d'))}")
    print(f"  Avg return 3d:    {fmt_ret(m.get('avg_return_3d'))} (baseline: {fmt_ret(m.get('baseline_avg_3d'))})")
    print(f"  Avg drawdown 5d:  {fmt_ret(m.get('avg_drawdown_5d'))}")
    print(f"  Worst case:       {fmt_ret(m.get('worst_case'))}")
    print(f"  False alarms:     {fmt_pct(m.get('false_alarm_rate'))}")
    print(f"  Edge vs baseline: {fmt_ret(m.get('signal_vs_baseline_3d'))}")

    # VIX Regime Breakdown
    print(f"\nVIX Regime Breakdown")
    for r in config.VIX_REGIMES.keys():
        b = m["regime_breakdown"].get(r, {})
        print(f"  {r}{' ' * (15-len(r))} {b.get('days', 0)} days, avg 3d ret: {fmt_ret(b.get('avg_ret_3d'))}")
    cr = m["regime_breakdown"].get("CRISIS", {})
    print(f"  CRISIS{' ' * 9} {cr.get('days', 0)} days, avg 3d ret: {fmt_ret(cr.get('avg_ret_3d'))}")

    # Portfolio Comparison
    p = m.get("portfolio", {})
    bh_cagr = p.get('bh_cagr')
    bh_sharpe = p.get('bh_sharpe')
    bh_mdd = p.get('bh_mdd')
    geo_cagr = p.get('geo_cagr')
    geo_sharpe = p.get('geo_sharpe')
    geo_mdd = p.get('geo_mdd')
    
    print(f"\nPortfolio Comparison ({config.DATA_PERIOD})")
    print(f"  Buy & Hold:    CAGR {fmt_ret(bh_cagr)}, Sharpe {bh_sharpe:.2f if bh_sharpe else 0}, MDD {fmt_ret(bh_mdd)}")
    print(f"  GeoRisk:       CAGR {fmt_ret(geo_cagr)}, Sharpe {geo_sharpe:.2f if geo_sharpe else 0}, MDD {fmt_ret(geo_mdd)}")
    
    if bh_cagr is not None and geo_cagr is not None:
        print(f"\n  Return delta:  {fmt_ret(geo_cagr - bh_cagr)}")
        print(f"  MDD delta:     {fmt_ret(geo_mdd - bh_mdd)}")
        print(f"  Sharpe delta:  {geo_sharpe - bh_sharpe:+.2f}")

    # Kelly
    k = m.get("kelly_f")
    kr = m.get("kelly_win_rate")
    kw = m.get("kelly_avg_win")
    kl = m.get("kelly_avg_loss")
    print(f"\nKelly Criterion")
    print(f"  win_rate: {fmt_pct(kr)}, avg_win: {fmt_pct(kw/100 if kw else 0)}, avg_loss: {fmt_pct(kl/100 if kl else 0)}")
    print(f"  kelly_f: {k:.2f} -> recommended max position: {k*100:.0f}%" if k else "  kelly_f: 0.0 -> no edge")

    print(f"\nVerdict: {result['verdict']}\n")


def main():
    out_dir = Path(config.RESULTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching market data ...")
    data = fetch_all()

    if config.SYMBOLS["equity"][0] not in data:
        print(f"ERROR: Could not fetch equity benchmark ({config.SYMBOLS['equity'][0]}). Aborting.")
        return

    print("Computing stress signals ...")
    signals_df = compute_signals(data)
    
    spy = data[config.SYMBOLS["equity"][0]]["Close"]

    print("Running backtest ...")
    fired = signals_df[signals_df["signal_fired"] == True]
    
    signal_dates = [
        {"date": d, "score": int(row["stress_score"])}
        for d, row in fired.iterrows()
    ]
    
    forward_df = compute_forward_returns(spy, signal_dates)
    metrics_result = compute_metrics(forward_df, spy, data, signals_df)
    v_dict = verdict(metrics_result)

    # events
    events = []
    for _, row in forward_df.iterrows():
        events.append({
            "date":        str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
            "score":       int(row["score"]) if not math.isnan(row["score"]) else None,
            "ret_1d":      round(float(row["ret_1d"]),  2) if not math.isnan(row["ret_1d"])  else None,
            "ret_3d":      round(float(row["ret_3d"]),  2) if not math.isnan(row["ret_3d"])  else None,
            "ret_5d":      round(float(row["ret_5d"]),  2) if not math.isnan(row["ret_5d"])  else None,
            "ret_10d":     round(float(row["ret_10d"]), 2) if not math.isnan(row["ret_10d"]) else None,
            "drawdown_5d": round(float(row["drawdown_5d"]), 2) if not math.isnan(row["drawdown_5d"]) else None,
        })

    spy_idx = spy.index
    data_range = f"{spy_idx[0].date()} to {spy_idx[-1].date()}"

    result = {
        "run_date":      str(date.today()),
        "data_range":    data_range,
        "period":        config.DATA_PERIOD,
        "total_signals": metrics_result.get("total_signals", 0),
        "metrics":       metrics_result,
        "signal_events": events,
        "verdict":       v_dict,
    }
    
    result = _json_safe(result)
    print_summary(result)

    today_str = date.today().strftime("%Y-%m-%d")
    out_path = out_dir / f"{today_str}_stress_vix_regime.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()
