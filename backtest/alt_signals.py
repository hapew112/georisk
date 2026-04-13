import pandas as pd
import numpy as np
import config
from signals import get_regime


def _base_signals(spy_df):
    df = pd.DataFrame(index=spy_df.index)
    df['date'] = df.index
    df['regime'] = "CALM"
    df['stress_score'] = 0
    df['action'] = "HOLD"
    return df


def alt_a_vix_meanreversion(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = _base_signals(data["SPY"]).copy()
    if "^VIX" not in data:
        return df

    vix = data["^VIX"]['Close']
    vix_sma = vix.rolling(window=config.VIX_SMA_PERIOD).mean()
    vix_std = vix.rolling(window=config.VIX_SMA_PERIOD).std()
    vix_zscore = (vix - vix_sma) / vix_std.replace(0, np.nan)

    defensive_mask = vix_zscore > config.VIX_ZSCORE_DEFENSIVE
    df.loc[defensive_mask, 'action'] = "DEFENSIVE"
    df.loc[defensive_mask, 'regime'] = "CRISIS"
    return df


def alt_b_cross_asset(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = _base_signals(data["SPY"]).copy()

    def below_sma(symbol):
        if symbol in data:
            price = data[symbol]['Close']
            return price < price.rolling(window=20).mean()
        return pd.Series(False, index=df.index)

    count_series = (
        below_sma("SPY").astype(int)
        + below_sma("TLT").astype(int)
        + below_sma("GC=F").astype(int)
        + below_sma("BTC-USD").astype(int)
    )

    defensive_mask = count_series >= 3
    df.loc[defensive_mask, 'action'] = "DEFENSIVE"
    df.loc[defensive_mask, 'regime'] = "CRISIS"
    df['stress_score'] = count_series
    return df


def alt_c_yield_vix(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = _base_signals(data["SPY"]).copy()

    if "TLT" in data and "SPY" in data and "^VIX" in data:
        spread_proxy = (
            data["TLT"]['Close'].pct_change(20)
            - data["SPY"]['Close'].pct_change(20)
        )
        vix = data["^VIX"]['Close']
        defensive_mask = (spread_proxy > 0.03) & (vix > 20)
        df.loc[defensive_mask, 'action'] = "DEFENSIVE"
        df.loc[defensive_mask, 'regime'] = "CRISIS"

    return df
