import sys
import json
import os
import glob
import argparse
import config

def judge_file(filepath):
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None
        
    p = data["portfolio"]
    bh_mdd = p["bh_mdd"]
    gr_mdd = p["gr_mdd"]
    bh_cagr = p["bh_cagr"]
    gr_cagr = p["gr_cagr"]
    bh_sharpe = p["bh_sharpe"]
    gr_sharpe = p["gr_sharpe"]
    
    pass_mdd = abs(gr_mdd) < abs(bh_mdd) * config.SUCCESS_MDD_RATIO
    pass_cagr = gr_cagr > bh_cagr * 0.85
    pass_sharpe = gr_sharpe > bh_sharpe * 0.9
    
    overall = "STRATEGY READY" if (pass_mdd and pass_cagr and pass_sharpe) else "NEEDS WORK"
    
    filename = os.path.basename(filepath)
    period_str = f"{data.get('start_date', 'N/A')} to {data.get('end_date', 'N/A')} ({data.get('period', 'N/A')})"
    
    result = f"""JUDGEMENT: {filename}
Period: {period_str}

MDD:    {gr_mdd:.1f}%  vs B&H {bh_mdd:.1f}%  → {'PASS' if pass_mdd else 'FAIL'}
CAGR:   {gr_cagr:.1f}%  vs B&H {bh_cagr:.1f}%  → {'PASS' if pass_cagr else 'FAIL'}
Sharpe: {gr_sharpe:.2f}  vs B&H {bh_sharpe:.2f}  → {'PASS' if pass_sharpe else 'FAIL'}

Overall: {overall}
"""
    if overall == "NEEDS WORK":
        result += "\\nIf NEEDS WORK, print which metrics failed and suggested fix:\\n"
        if not pass_mdd:
            result += "MDD fail → Tighten CRISIS threshold or add more defensive allocation\\n"
        if not pass_cagr:
            result += "CAGR fail → Increase SPY weight in NORMAL regime\\n"
        if not pass_sharpe:
            result += "Sharpe fail → Reduce false alarm rate — raise SIGNAL_MIN_STRESS\\n"
            
    print(result.strip())
    print()
    
    return {
        "file": filename,
        "period": period_str,
        "mdd_pass": pass_mdd,
        "cagr_pass": pass_cagr,
        "sharpe_pass": pass_sharpe,
        "overall": overall
    }

def print_table():
    files = glob.glob(os.path.join(config.RESULTS_DIR, "*_backtest.json"))
    files.sort()
    if not files:
        print("No result files found in directory.")
        return
        
    print(f"{'Filename':<35} | {'MDD':<5} | {'CAGR':<5} | {'Sharpe':<6} | {'Overall'}")
    print("-" * 75)
    
    for filepath in files:
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except: continue
        p = data["portfolio"]
        bh_mdd, gr_mdd = p["bh_mdd"], p["gr_mdd"]
        bh_cagr, gr_cagr = p["bh_cagr"], p["gr_cagr"]
        bh_sharpe, gr_sharpe = p["bh_sharpe"], p["gr_sharpe"]
        pass_mdd = abs(gr_mdd) < abs(bh_mdd) * config.SUCCESS_MDD_RATIO
        pass_cagr = gr_cagr > bh_cagr * 0.85
        pass_sharpe = gr_sharpe > bh_sharpe * 0.9
        ov = "READY" if (pass_mdd and pass_cagr and pass_sharpe) else "FIX "
        fname = os.path.basename(filepath)
        print(f"{fname:<35} | {'PASS' if pass_mdd else 'FAIL':<5} | {'PASS' if pass_cagr else 'FAIL':<5} | {'PASS' if pass_sharpe else 'FAIL':<6} | {ov}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?", help="Specific result file to judge")
    parser.add_argument("--all", action="store_true", help="Judge all files and print table")
    args = parser.parse_args()
    
    if args.all:
        print_table()
    elif args.file:
        judge_file(args.file)
    else:
        files = glob.glob(os.path.join(config.RESULTS_DIR, "*_backtest.json"))
        if not files:
            print("No result files found.")
        else:
            files.sort(key=os.path.getmtime)
            latest = files[-1]
            judge_file(latest)
