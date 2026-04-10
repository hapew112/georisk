# GeoRisk Backtest — Configuration

SYMBOLS = {
    "equity":  ["SPY"],
    "vix":     ["^VIX"],
    "dollar":  ["DX-Y.NYB"],
    "oil":     ["CL=F"],
    "yield":   ["^TNX"],
    "gold":    ["GC=F"],
    "crypto":  ["BTC-USD"],
    "korea":   ["^KS11"],
    "bond":    ["TLT"],
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
