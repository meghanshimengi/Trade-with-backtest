from abc import ABC, abstractmethod
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class OrderResult:
    success: bool
    order_id: str = ""
    message: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class Position:
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    last_price: float = 0.0
    pnl: float = 0.0
    product: str = ""
    token: str = ""


@dataclass
class Holding:
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    last_price: float = 0.0
    pnl: float = 0.0
    product: str = ""


class BrokerBase(ABC):
    """Abstract base class for all broker integrations."""

    name: str = "BaseBroker"
    connected: bool = False

    @abstractmethod
    def connect(self, **kwargs) -> bool:
        """Authenticate with broker. Returns True on success."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Terminate session."""
        ...

    @abstractmethod
    def get_profile(self) -> dict:
        """Return user profile info (name, broker, margin, etc.)."""
        ...

    @abstractmethod
    def get_ltp(self, exchange: str, symbol: str) -> float:
        """Get last traded price for a symbol."""
        ...

    @abstractmethod
    def get_quote(self, exchange: str, symbol: str) -> dict:
        """Get full quote (OHLCV, depth, OI)."""
        ...

    @abstractmethod
    def get_historical(self, exchange: str, symbol: str, interval: str,
                       from_date: str, to_date: str) -> pd.DataFrame:
        """Fetch historical candle data. Returns DataFrame with
        columns: date, open, high, low, close, volume."""
        ...

    @abstractmethod
    def place_order(self, exchange: str, symbol: str, transaction_type: str,
                    quantity: int, order_type: str = "MARKET",
                    price: float = 0.0, trigger_price: float = 0.0,
                    product: str = "MIS", validity: str = "DAY",
                    **kwargs) -> OrderResult:
        """Place an order. transaction_type: BUY/SELL. order_type: MARKET/LIMIT/SL/SL-M."""
        ...

    @abstractmethod
    def modify_order(self, order_id: str, exchange: str, symbol: str,
                     order_type: str, quantity: int, price: float = 0.0,
                     trigger_price: float = 0.0, **kwargs) -> OrderResult:
        """Modify a pending order."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str, exchange: str = "") -> OrderResult:
        """Cancel a pending order."""
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Get all open positions (intraday + overnight)."""
        ...

    @abstractmethod
    def get_holdings(self) -> list[Holding]:
        """Get delivery holdings."""
        ...

    @abstractmethod
    def get_orders(self) -> list[dict]:
        """Get today's order book."""
        ...

    @abstractmethod
    def get_trades(self) -> list[dict]:
        """Get today's trade book."""
        ...

    @abstractmethod
    def exit_position(self, exchange: str, symbol: str, quantity: int,
                      transaction_type: str, product: str = "MIS",
                      **kwargs) -> OrderResult:
        """Exit a specific position by placing opposite order."""
        ...

    @abstractmethod
    def exit_all_positions(self) -> list[OrderResult]:
        """Close all open positions."""
        ...

    @abstractmethod
    def search_instrument(self, query: str, exchange: str = "NSE") -> list[dict]:
        """Search for instruments by name/symbol. Returns list of
        dicts with keys: symbol, name, exchange, token."""
        ...

    def get_instrument_token(self, exchange: str, symbol: str) -> str:
        """Resolve a trading symbol to its instrument token.
        Override in subclasses if broker requires token-based API."""
        return symbol
