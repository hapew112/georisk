# GeoRisk Backtest — Configuration

SYMBOLS = {
    "equity":  ["SPY"],
    "vix":     ["^VIX"],
    "dollar":  ["DX-Y.NYB"],
    "oil":     ["CL=F"],
    "yield":   ["^TNX"],
    "gold":    ["GC=F", "GLD"],
    "crypto":  ["BTC-USD"],
    "korea":   ["^KS11"],
    "bond":    ["TLT", "SGOV"],
}

ALL_SYMBOLS = [s for group in SYMBOLS.values() for s in group]

# Data settings
DATA_PERIOD = "3y"
DATA_INTERVAL = "1d"
CACHE_DIR = "./data/cache"
RESULTS_DIR = "./results"
CACHE_MAX_AGE_HOURS = 24

# Stress signal thresholds (1-day % change)
STRESS_THRESHOLDS = {
    "vix_spike":    15.0,   # VIX +15% in 1 day
    "dollar_surge":  0.8,   # DXY +0.8% in 1 day
    "oil_spike":     5.0,   # WTI +5% in 1 day
    "yield_jump":    3.0,   # 10Y yield +3% in 1 day
    "gold_rush":     2.0,   # Gold +2% in 1 day (flight to safety)
}

# VIX regime boundaries
VIX_REGIMES = {
    "CALM":     (0, 15),
    "NORMAL":   (15, 20),
    "ELEVATED": (20, 28),
    "CRISIS":   (28, 999),
}

# Signal trigger: minimum stress score + minimum regime
SIGNAL_MIN_STRESS = 2
SIGNAL_MIN_REGIME = "ELEVATED"  # CALM < NORMAL < ELEVATED < CRISIS

# VIX Mean Reversion thresholds
VIX_ZSCORE_DEFENSIVE = 2.0    # go defensive when VIX 2 std above mean
VIX_ZSCORE_AGGRESSIVE = -1.0  # opportunity when VIX 1 std below mean
VIX_SMA_PERIOD = 20

# Lookforward windows (days after signal)
FORWARD_WINDOWS = [1, 3, 5, 10]

# Hypothetical portfolio allocations per regime
PORTFOLIO_ALLOCATIONS = {
    "CALM":     {"SPY": 1.0, "TLT": 0.0, "cash": 0.0},
    "NORMAL":   {"SPY": 1.0, "TLT": 0.0, "cash": 0.0},
    "ELEVATED": {"SPY": 0.7, "TLT": 0.3, "cash": 0.0},
    "CRISIS":   {"SPY": 0.4, "TLT": 0.4, "cash": 0.2},
}

# Kelly cap
KELLY_MAX_FRACTION = 0.25

# Success criteria
SUCCESS_HIT_RATE_3D = 0.60       # > 60%
SUCCESS_EDGE_VS_BASELINE = -0.5  # < -0.5% (signal days worse)
SUCCESS_MDD_RATIO = 0.6          # GeoRisk MDD < 60% of buy-and-hold MDD

# Hybrid allocation settings
HYBRID_RP_REGIMES = ["ELEVATED", "CRISIS"]   # regimes that use RP
HYBRID_RP_ASSETS  = ["SPY", "TLT", "GLD"]    # assets used in RP math (exclude SGOV)
HYBRID_CAPS = {
    "CALM":     {"SPY": 1.00, "TLT": 0.00, "GLD": 0.00, "SGOV": 0.00},  # fixed
    "NORMAL":   {"SPY": 1.00, "TLT": 0.00, "GLD": 0.00, "SGOV": 0.00},  # fixed
    "ELEVATED": {"SPY_MAX": 0.65, "GLD_MAX": 0.20, "SGOV_MIN": 0.00},    # RP with caps
    "CRISIS":   {"SPY_MAX": 0.35, "GLD_MAX": 0.20, "SGOV_MIN": 0.20},    # RP + cash buffer
}

# Risk Parity settings
RP_LOOKBACK = 20  # days for rolling volatility
RP_CAPS = {
    "CALM":     {"SPY_MAX": 1.00, "CASH_MIN": 0.0},
    "NORMAL":   {"SPY_MAX": 0.90, "CASH_MIN": 0.0},
    "ELEVATED": {"SPY_MAX": 0.65, "CASH_MIN": 0.0},
    "CRISIS":   {"SPY_MAX": 0.35, "CASH_MIN": 0.2},
}
RP_REBALANCE = "daily"  # daily for now. quarterly optimization later.
RP_MIN_TRADE = 0.02     # don't rebalance if weight change < 2%
