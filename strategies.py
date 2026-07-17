import re
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Technical indicator helpers
# ---------------------------------------------------------------------------

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger(series: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = compute_sma(series, period)
    std = series.rolling(window=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=1 / period, min_periods=period).mean()


# ---------------------------------------------------------------------------
# Pre-built strategy generators  →  return DataFrame with 'signal' column
# Signal: 1 = BUY, -1 = SELL, 0 = HOLD
# ---------------------------------------------------------------------------

def strategy_rsi(df: pd.DataFrame, period: int = 14,
                 oversold: int = 30, overbought: int = 70) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = compute_rsi(df["Close"], period)
    df["signal"] = 0
    df.loc[df["rsi"] < oversold, "signal"] = 1
    df.loc[df["rsi"] > overbought, "signal"] = -1
    return df


def strategy_sma_crossover(df: pd.DataFrame, short_period: int = 20,
                           long_period: int = 50) -> pd.DataFrame:
    df = df.copy()
    df["sma_short"] = compute_sma(df["Close"], short_period)
    df["sma_long"] = compute_sma(df["Close"], long_period)
    df["signal"] = 0
    # 1 when short crosses above long, -1 when crosses below
    df.loc[df["sma_short"] > df["sma_long"], "signal"] = 1
    df.loc[df["sma_short"] < df["sma_long"], "signal"] = -1
    return df


def strategy_ema_crossover(df: pd.DataFrame, short_period: int = 12,
                           long_period: int = 26) -> pd.DataFrame:
    df = df.copy()
    df["ema_short"] = compute_ema(df["Close"], short_period)
    df["ema_long"] = compute_ema(df["Close"], long_period)
    df["signal"] = 0
    df.loc[df["ema_short"] > df["ema_long"], "signal"] = 1
    df.loc[df["ema_short"] < df["ema_long"], "signal"] = -1
    return df


def strategy_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
                  signal: int = 9) -> pd.DataFrame:
    df = df.copy()
    df["macd"], df["macd_signal"], df["macd_hist"] = compute_macd(df["Close"], fast, slow, signal)
    df["signal"] = 0
    df.loc[df["macd"] > df["macd_signal"], "signal"] = 1
    df.loc[df["macd"] < df["macd_signal"], "signal"] = -1
    return df


def strategy_bollinger(df: pd.DataFrame, period: int = 20,
                       num_std: float = 2.0) -> pd.DataFrame:
    df = df.copy()
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = compute_bollinger(df["Close"], period, num_std)
    df["signal"] = 0
    df.loc[df["Close"] < df["bb_lower"], "signal"] = 1
    df.loc[df["Close"] > df["bb_upper"], "signal"] = -1
    return df


def strategy_supertrend(df: pd.DataFrame, period: int = 10,
                        multiplier: float = 3.0) -> pd.DataFrame:
    df = df.copy()
    hl2 = (df["High"] + df["Low"]) / 2
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period).mean()
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=float)

    supertrend.iloc[0] = upper_band.iloc[0]
    direction.iloc[0] = -1

    for i in range(1, len(df)):
        if df["Close"].iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["Close"].iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        if direction.iloc[i] == 1:
            supertrend.iloc[i] = lower_band.iloc[i]
        else:
            supertrend.iloc[i] = upper_band.iloc[i]

    df["supertrend"] = supertrend
    df["supertrend_dir"] = direction
    df["signal"] = direction.astype(int)
    return df


STRATEGY_MAP = {
    "rsi": strategy_rsi,
    "sma crossover": strategy_sma_crossover,
    "sma": strategy_sma_crossover,
    "ema crossover": strategy_ema_crossover,
    "ema": strategy_ema_crossover,
    "macd": strategy_macd,
    "bollinger": strategy_bollinger,
    "bollinger bands": strategy_bollinger,
    "supertrend": strategy_supertrend,
}

BUILTIN_STRATEGIES = {
    "RSI (Relative Strength Index)": "rsi",
    "SMA Crossover (20/50)": "sma_crossover",
    "EMA Crossover (12/26)": "ema_crossover",
    "MACD (12/26/9)": "macd",
    "Bollinger Bands (20,2)": "bollinger",
    "Supertrend (10,3)": "supertrend",
}

PARAM_DEFAULTS = {
    "rsi": {"period": 14, "oversold": 30, "overbought": 70},
    "sma_crossover": {"short_period": 20, "long_period": 50},
    "ema_crossover": {"short_period": 12, "long_period": 26},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "bollinger": {"period": 20, "num_std": 2.0},
    "supertrend": {"period": 10, "multiplier": 3.0},
}


# ---------------------------------------------------------------------------
# Natural language → strategy parser
# ---------------------------------------------------------------------------

def parse_strategy_text(text: str) -> tuple[str, dict]:
    """
    Parse a user's plain-English strategy and return (strategy_key, params).
    Falls back to 'rsi' if nothing is detected.
    """
    lower = text.lower().strip()

    # --- RSI ---
    if "rsi" in lower:
        params = dict(PARAM_DEFAULTS["rsi"])
        m = re.search(r"rsi\s*(?:of|period|length)?\s*(\d+)", lower)
        if m:
            params["period"] = int(m.group(1))
        m = re.search(r"(?:oversold|below)\s*(\d+)", lower)
        if m:
            params["oversold"] = int(m.group(1))
        m = re.search(r"(?:overbought|above)\s*(\d+)", lower)
        if m:
            params["overbought"] = int(m.group(1))
        return "rsi", params

    # --- MACD ---
    if "macd" in lower:
        params = dict(PARAM_DEFAULTS["macd"])
        return "macd", params

    # --- Bollinger ---
    if "bollinger" in lower or "bb " in lower:
        params = dict(PARAM_DEFAULTS["bollinger"])
        return "bollinger", params

    # --- Supertrend ---
    if "supertrend" in lower or "super trend" in lower:
        params = dict(PARAM_DEFAULTS["supertrend"])
        return "supertrend", params

    # --- EMA crossover ---
    if "ema" in lower and ("cross" in lower or "crossover" in lower):
        params = dict(PARAM_DEFAULTS["ema_crossover"])
        nums = re.findall(r"(\d+)\s*(?:day|period|EMA)", lower)
        if len(nums) >= 2:
            params["short_period"] = int(nums[0])
            params["long_period"] = int(nums[1])
        elif len(nums) == 1:
            params["short_period"] = int(nums[0])
        return "ema_crossover", params

    # --- SMA crossover ---
    if "sma" in lower or ("moving average" in lower and "cross" in lower):
        params = dict(PARAM_DEFAULTS["sma_crossover"])
        nums = re.findall(r"(\d+)\s*(?:day|period|SMA|MA)", lower)
        if len(nums) >= 2:
            params["short_period"] = int(nums[0])
            params["long_period"] = int(nums[1])
        return "sma_crossover", params

    # --- Simple "moving average" mention without crossover ---
    if "moving average" in lower or "ma " in lower:
        params = dict(PARAM_DEFAULTS["sma_crossover"])
        nums = re.findall(r"(\d+)", lower)
        if len(nums) >= 2:
            params["short_period"] = int(nums[0])
            params["long_period"] = int(nums[1])
        return "sma_crossover", params

    # Fallback
    return "rsi", dict(PARAM_DEFAULTS["rsi"])


def execute_strategy(df: pd.DataFrame, strategy_key: str,
                     params: dict | None = None) -> pd.DataFrame:
    """Run a named strategy on the dataframe. Returns df with 'signal' column."""
    if params is None:
        params = PARAM_DEFAULTS.get(strategy_key, {})

    strategy_fn_map = {
        "rsi": strategy_rsi,
        "sma_crossover": strategy_sma_crossover,
        "ema_crossover": strategy_ema_crossover,
        "macd": strategy_macd,
        "bollinger": strategy_bollinger,
        "supertrend": strategy_supertrend,
    }

    fn = strategy_fn_map.get(strategy_key, strategy_rsi)
    return fn(df, **params)
