import pandas as pd
import numpy as np
import yfinance as yf

from strategies import execute_strategy, parse_strategy_text, PARAM_DEFAULTS


STARTING_CAPITAL = 100_000  # INR
TRANSACTION_COST_PCT = 0.001  # 0.1% per trade (brokerage + slippage + taxes)


def fetch_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance for NSE (.NS suffix)."""
    symbol = f"{ticker.strip().upper()}.NS"
    raw = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    if raw.empty:
        raise ValueError(f"No data found for {symbol} between {start} and {end}")
    # Flatten multi-level columns if present (yfinance >= 0.2.31)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return raw


def run_backtest(df: pd.DataFrame, strategy_key: str,
                 params: dict | None = None,
                 capital: float = STARTING_CAPITAL,
                 cost_pct: float = TRANSACTION_COST_PCT) -> dict:
    """
    Run a full backtest.

    Returns dict with:
      - 'df': DataFrame with signals, positions, equity curve
      - 'trades': list of trade dicts
      - 'metrics': dict of KPIs
      - 'strategy_key': name used
      - 'params': params used
    """
    # Compute indicators and signals
    df = execute_strategy(df.copy(), strategy_key, params)

    # Build position column: 1 = long, 0 = flat (no shorting)
    df["position"] = 0
    df.loc[df["signal"] == 1, "position"] = 1
    df.loc[df["signal"] == -1, "position"] = 0

    # Forward-fill position until next signal changes it
    pos = 0
    positions = []
    for _, row in df.iterrows():
        if row["signal"] == 1:
            pos = 1
        elif row["signal"] == -1:
            pos = 0
        positions.append(pos)
    df["position"] = positions

    # Daily returns
    df["daily_return"] = df["Close"].pct_change().fillna(0)
    df["strategy_return"] = df["position"].shift(1).fillna(0) * df["daily_return"]

    # Transaction costs: charged when position changes
    df["trade_flag"] = df["position"].diff().fillna(0).abs()
    df["cost"] = df["trade_flag"] * cost_pct

    df["net_return"] = df["strategy_return"] - df["cost"]
    df["equity"] = capital * (1 + df["net_return"]).cumprod()
    df["buy_hold_equity"] = capital * (1 + df["daily_return"]).cumprod()

    # Extract individual trades
    trades = _extract_trades(df)

    # Compute metrics
    metrics = _compute_metrics(df, trades, capital)

    return {
        "df": df,
        "trades": trades,
        "metrics": metrics,
        "strategy_key": strategy_key,
        "params": params or {},
    }


def _extract_trades(df: pd.DataFrame) -> list[dict]:
    """Extract round-trip trades from position changes."""
    trades = []
    entry_date = None
    entry_price = None

    for i in range(1, len(df)):
        prev_pos = df["position"].iloc[i - 1]
        curr_pos = df["position"].iloc[i]
        date = df.index[i]
        price = df["Close"].iloc[i]

        if prev_pos == 0 and curr_pos == 1:
            entry_date = date
            entry_price = price
        elif prev_pos == 1 and curr_pos == 0 and entry_date is not None:
            pnl_pct = (price - entry_price) / entry_price * 100
            trades.append({
                "entry_date": entry_date,
                "exit_date": date,
                "entry_price": round(float(entry_price), 2),
                "exit_price": round(float(price), 2),
                "pnl_pct": round(float(pnl_pct), 2),
                "status": "WIN" if pnl_pct > 0 else "LOSS",
            })
            entry_date = None
            entry_price = None

    return trades


def _compute_metrics(df: pd.DataFrame, trades: list[dict],
                     capital: float) -> dict:
    """Compute all KPIs."""
    total_return_pct = (df["equity"].iloc[-1] / capital - 1) * 100
    buy_hold_return_pct = (df["buy_hold_equity"].iloc[-1] / capital - 1) * 100

    # Max drawdown
    equity = df["equity"]
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown_pct = drawdown.min() * 100

    # Win rate
    total_trades = len(trades)
    wins = sum(1 for t in trades if t["status"] == "WIN")
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    # Sharpe ratio (annualized, using net returns)
    daily_returns = df["net_return"]
    if daily_returns.std() != 0:
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Profit factor
    gross_profit = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gross_loss = abs(sum(t["pnl_pct"] for t in trades if t["pnl_pct"] < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss != 0 else (round(gross_profit, 2) if gross_profit > 0 else 0.0)

    # Average trade
    avg_trade_pnl = np.mean([t["pnl_pct"] for t in trades]) if trades else 0

    # CAGR
    years = (df.index[-1] - df.index[0]).days / 365.25
    final_equity = df["equity"].iloc[-1]
    cagr = ((final_equity / capital) ** (1 / years) - 1) * 100 if years > 0 else 0

    return {
        "Total Return (%)": round(float(total_return_pct), 2),
        "Buy & Hold Return (%)": round(float(buy_hold_return_pct), 2),
        "CAGR (%)": round(float(cagr), 2),
        "Max Drawdown (%)": round(float(max_drawdown_pct), 2),
        "Sharpe Ratio": round(float(sharpe), 2),
        "Win Rate (%)": round(float(win_rate), 2),
        "Total Trades": total_trades,
        "Winning Trades": wins,
        "Losing Trades": total_trades - wins,
        "Profit Factor": round(float(profit_factor), 2),
        "Avg Trade P&L (%)": round(float(avg_trade_pnl), 2),
        "Final Equity (INR)": round(float(final_equity), 2),
        "Starting Capital (INR)": capital,
    }


def run_backtest_from_text(df: pd.DataFrame, strategy_text: str,
                           capital: float = STARTING_CAPITAL) -> dict:
    """Parse user text, run backtest, return results."""
    strategy_key, params = parse_strategy_text(strategy_text)
    return run_backtest(df, strategy_key, params, capital)
