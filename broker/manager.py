import time
import pandas as pd
import streamlit as st
from broker.base import BrokerBase, OrderResult, Position
from broker.zerodha import ZerodhaBroker
from broker.angel import AngelBroker
from broker.upstox import UpstoxBroker
from strategies import execute_strategy, PARAM_DEFAULTS


class BrokerManager:
    """Manages broker connection, live signals, and order execution."""

    def __init__(self):
        if "broker" not in st.session_state:
            st.session_state.broker = None
        if "broker_name" not in st.session_state:
            st.session_state.broker_name = ""
        if "live_positions" not in st.session_state:
            st.session_state.live_positions = []
        if "live_orders" not in st.session_state:
            st.session_state.live_orders = []
        if "trade_log" not in st.session_state:
            st.session_state.trade_log = []

    @property
    def broker(self) -> BrokerBase | None:
        return st.session_state.broker

    @property
    def connected(self) -> bool:
        return st.session_state.broker is not None and st.session_state.broker.connected

    def connect(self, broker_name: str, **credentials) -> tuple[bool, str]:
        try:
            if broker_name == "Zerodha Kite Connect":
                b = ZerodhaBroker()
                b.connect(**credentials)
            elif broker_name == "Angel One SmartAPI":
                b = AngelBroker()
                b.connect(**credentials)
            elif broker_name == "Upstox API v2":
                b = UpstoxBroker()
                b.connect(**credentials)
            else:
                return False, f"Unknown broker: {broker_name}"

            st.session_state.broker = b
            st.session_state.broker_name = broker_name
            return True, f"Connected to {broker_name} successfully!"
        except Exception as e:
            return False, f"Connection failed: {e}"

    def disconnect(self) -> None:
        if self.broker:
            self.broker.disconnect()
        st.session_state.broker = None
        st.session_state.broker_name = ""

    def get_profile(self) -> dict:
        if not self.connected:
            return {}
        return self.broker.get_profile()

    def get_ltp(self, exchange: str, symbol: str) -> float:
        if not self.connected:
            return 0.0
        return self.broker.get_ltp(exchange, symbol)

    def place_order(self, exchange: str, symbol: str, transaction_type: str,
                    quantity: int, order_type: str = "MARKET",
                    price: float = 0.0, trigger_price: float = 0.0,
                    product: str = "MIS") -> OrderResult:
        if not self.connected:
            return OrderResult(success=False, message="Not connected to broker")
        result = self.broker.place_order(
            exchange=exchange, symbol=symbol,
            transaction_type=transaction_type,
            quantity=quantity, order_type=order_type,
            price=price, trigger_price=trigger_price,
            product=product,
        )
        if result.success:
            self.refresh_positions()
        return result

    def exit_position(self, exchange: str, symbol: str, quantity: int,
                      transaction_type: str, product: str = "MIS") -> OrderResult:
        if not self.connected:
            return OrderResult(success=False, message="Not connected to broker")
        result = self.broker.exit_position(
            exchange=exchange, symbol=symbol,
            quantity=quantity, transaction_type=transaction_type,
            product=product,
        )
        if result.success:
            self.refresh_positions()
        return result

    def exit_all_positions(self) -> list[OrderResult]:
        if not self.connected:
            return [OrderResult(success=False, message="Not connected")]
        results = self.broker.exit_all_positions()
        self.refresh_positions()
        return results

    def refresh_positions(self) -> None:
        if self.connected:
            st.session_state.live_positions = self.broker.get_positions()

    def refresh_orders(self) -> None:
        if self.connected:
            st.session_state.live_orders = self.broker.get_orders()

    def get_positions(self) -> list[Position]:
        if not self.connected:
            return []
        self.refresh_positions()
        return st.session_state.live_positions

    def get_holdings(self) -> list:
        if not self.connected:
            return []
        return self.broker.get_holdings()

    def get_orders(self) -> list[dict]:
        if not self.connected:
            return []
        self.refresh_orders()
        return st.session_state.live_orders

    def get_trades(self) -> list[dict]:
        if not self.connected:
            return []
        return self.broker.get_trades()

    def search_instrument(self, query: str, exchange: str = "NSE") -> list[dict]:
        if not self.connected:
            return []
        return self.broker.search_instrument(query, exchange)

    def compute_live_signal(self, exchange: str, symbol: str,
                            strategy_key: str, params: dict | None = None,
                            interval: str = "day", lookback_days: int = 100) -> dict:
        """Compute strategy signal on recent live data.

        Returns dict with:
          - signal: 1 (BUY), -1 (SELL), 0 (HOLD)
          - ltp: current last traded price
          - indicator_value: current value of the primary indicator
          - strategy_key: strategy used
          - params: params used
          - timestamp: data timestamp
        """
        if not self.connected:
            return {"signal": 0, "ltp": 0, "error": "Not connected"}

        try:
            from datetime import datetime, timedelta
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

            df = self.broker.get_historical(exchange, symbol, interval, from_date, to_date)
            if df.empty or len(df) < 20:
                return {"signal": 0, "ltp": 0, "error": "Insufficient data"}

            df = execute_strategy(df, strategy_key, params)
            last_signal = int(df["signal"].iloc[-1])
            last_price = float(df["Close"].iloc[-1])

            indicator_val = None
            indicator_col = {
                "rsi": "rsi", "macd": "macd", "bollinger": "bb_upper",
                "supertrend": "supertrend", "sma_crossover": "sma_short",
                "ema_crossover": "ema_short",
            }
            col = indicator_col.get(strategy_key, "")
            if col and col in df.columns:
                indicator_val = round(float(df[col].iloc[-1]), 2)

            return {
                "signal": last_signal,
                "signal_label": "BUY" if last_signal == 1 else "SELL" if last_signal == -1 else "HOLD",
                "ltp": last_price,
                "indicator_value": indicator_val,
                "strategy_key": strategy_key,
                "params": params or {},
                "timestamp": str(df.index[-1]),
                "data_points": len(df),
            }
        except Exception as e:
            return {"signal": 0, "ltp": 0, "error": str(e)}

    def auto_execute_signal(self, exchange: str, symbol: str, signal: int,
                            quantity: int, product: str = "MIS") -> OrderResult | None:
        """Execute an order based on signal (BUY=1, SELL=-1)."""
        if signal == 0:
            return None
        txn = "BUY" if signal == 1 else "SELL"
        return self.place_order(
            exchange=exchange, symbol=symbol,
            transaction_type=txn, quantity=quantity,
            order_type="MARKET", product=product,
        )

    def log_trade(self, signal: str, symbol: str, price: float,
                  quantity: int, order_result: OrderResult) -> None:
        """Append to session trade log."""
        from datetime import datetime
        st.session_state.trade_log.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "signal": signal,
            "symbol": symbol,
            "price": price,
            "quantity": quantity,
            "success": order_result.success,
            "order_id": order_result.order_id,
            "message": order_result.message,
        })
