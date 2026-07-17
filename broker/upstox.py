from datetime import datetime
import pandas as pd
import requests
from broker.base import BrokerBase, OrderResult, Position, Holding


class UpstoxBroker(BrokerBase):
    """Upstox API v2 integration with full OAuth flow."""

    name = "Upstox API v2"
    AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

    def __init__(self):
        self.api_client = None
        self.configuration = None
        self.connected = False
        self.api_key = ""
        self.access_token = ""

    def get_auth_url(self, api_key: str, redirect_uri: str) -> str:
        """Generate the authorization URL for user login."""
        return (
            f"{self.AUTH_URL}"
            f"?response_type=code"
            f"&client_id={api_key}"
            f"&redirect_uri={redirect_uri}"
        )

    def exchange_code_for_token(self, code: str, api_key: str,
                                client_secret: str, redirect_uri: str) -> str:
        """Exchange authorization code for access token."""
        payload = {
            "code": code,
            "client_id": api_key,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        resp = requests.post(self.TOKEN_URL, data=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise ValueError(f"Token exchange failed: {data}")
        return data["access_token"]

    def connect(self, access_token: str = "", api_key: str = "",
                client_secret: str = "", redirect_uri: str = "",
                code: str = "", **kwargs) -> bool:
        """Connect with either a direct access_token or by exchanging a code."""
        try:
            import upstox_client
        except ImportError:
            raise ImportError(
                "upstox-python-sdk is not installed. "
                "Run: pip install upstox-python-sdk"
            )

        if not access_token and code:
            access_token = self.exchange_code_for_token(
                code, api_key, client_secret, redirect_uri
            )

        if not access_token:
            raise ValueError("Provide access_token or authorization code")

        self.api_key = api_key
        self.access_token = access_token
        self.configuration = upstox_client.Configuration()
        self.configuration.access_token = access_token
        self.api_client = upstox_client.ApiClient(self.configuration)
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.api_client = None
        self.configuration = None
        self.connected = False

    def _get_market_quote_api(self):
        import upstox_client
        return upstox_client.MarketQuoteV3Api(self.api_client)

    def _get_order_api(self):
        import upstox_client
        return upstox_client.OrderApiV3(self.api_client)

    def _get_portfolio_api(self):
        import upstox_client
        return upstox_client.PortfolioApi(self.api_client)

    def _get_user_api(self):
        import upstox_client
        return upstox_client.UserApi(self.api_client)

    def _get_history_api(self):
        import upstox_client
        return upstox_client.HistoryV3Api(self.api_client)

    def _get_instruments_api(self):
        import upstox_client
        return upstox_client.InstrumentsApi(self.api_client)

    def _instrument_key(self, exchange: str, symbol: str) -> str:
        mapping = {
            "NSE": "NSE_EQ", "BSE": "BSE_EQ",
            "NFO": "NFO_EQ", "MCX": "MCX_EQ",
            "NSE_INDEX": "NSE_INDEX",
        }
        if exchange.upper() in ("NSE_INDEX", "INDEX"):
            return f"NSE_INDEX|{symbol}"
        prefix = mapping.get(exchange.upper(), "NSE_EQ")
        return f"{prefix}|{symbol}"

    def get_profile(self) -> dict:
        try:
            api = self._get_user_api()
            data = api.get_user_funds_and_margin()
            funds = getattr(data, "data", None) or {}
            equity = funds.get("equity", {}) if isinstance(funds, dict) else {}
            profile_api = self._get_user_api()
            profile = profile_api.get_profile()
            profile_data = getattr(profile, "data", None) or {}
            return {
                "name": getattr(profile_data, "name", "") or profile_data.get("name", ""),
                "broker": "Upstox",
                "client_id": getattr(profile_data, "client_id", "") or profile_data.get("client_id", ""),
                "available_cash": float(equity.get("available_margin", 0) or 0),
                "used_margin": float(equity.get("used_margin", 0) or 0),
                "total_margin": float(equity.get("margin_used", 0) or 0),
            }
        except Exception:
            return {
                "name": "", "broker": "Upstox", "client_id": "",
                "available_cash": 0, "used_margin": 0, "total_margin": 0,
            }

    def get_ltp(self, exchange: str, symbol: str) -> float:
        api = self._get_market_quote_api()
        key = self._instrument_key(exchange, symbol)
        data = api.get_ltp(instrument_key=key)
        resp_data = getattr(data, "data", None)
        if resp_data and hasattr(resp_data, "last_price"):
            return float(resp_data.last_price or 0)
        return 0.0

    def get_quote(self, exchange: str, symbol: str) -> dict:
        api = self._get_market_quote_api()
        key = self._instrument_key(exchange, symbol)
        data = api.get_full_market_quote(instrument_key=key)
        resp_data = getattr(data, "data", None)
        if resp_data:
            return {"last_price": getattr(resp_data, "last_price", 0)}
        return {}

    def get_historical(self, exchange: str, symbol: str, interval: str,
                       from_date: str, to_date: str) -> pd.DataFrame:
        api = self._get_history_api()
        key = self._instrument_key(exchange, symbol)

        interval_map = {
            "minute": "1minute", "5minute": "5minute",
            "15minute": "15minute", "30minute": "30minute",
            "hour": "1h", "day": "1d",
        }
        intv = interval_map.get(interval, "1d")
        from_d = from_date if "T" in from_date else f"{from_date}T09:00:00"
        to_d = to_date if "T" in to_date else f"{to_date}T15:30:00"

        try:
            resp = api.get_historical_candle_data1(
                instrument_key=key, unit="days", interval=intv,
                to_date=to_d, from_date=from_d,
            )
        except Exception as e:
            raise ValueError(f"Historical data fetch failed: {e}")

        candles = []
        resp_data = getattr(resp, "data", None)
        if resp_data:
            candles = resp_data if isinstance(resp_data, list) else []
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(candles)
        if "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"])
        elif "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        else:
            df["date"] = pd.to_datetime(df.iloc[:, 0])
        df.set_index("date", inplace=True)

        rename_map = {}
        for c in df.columns:
            cl = c.lower()
            if cl in ("open", "high", "low", "close", "volume"):
                rename_map[c] = cl.capitalize()
        df.rename(columns=rename_map, inplace=True)
        return df

    def place_order(self, exchange: str, symbol: str, transaction_type: str,
                    quantity: int, order_type: str = "MARKET",
                    price: float = 0.0, trigger_price: float = 0.0,
                    product: str = "MIS", validity: str = "DAY",
                    **kwargs) -> OrderResult:
        import upstox_client

        key = self._instrument_key(exchange, symbol)
        ot_map = {
            "MARKET": "MARKET", "LIMIT": "LIMIT",
            "SL": "SL", "SLM": "SL-M", "SL-M": "SL-M",
        }
        prod_map = {
            "MIS": "I", "INTRADAY": "I",
            "CNC": "D", "DELIVERY": "D",
            "NRML": "D",
        }
        body = upstox_client.PlaceOrderV3Request(
            quantity=quantity,
            product=prod_map.get(product.upper(), "I"),
            validity=validity.upper(),
            price=price if price else 0.0,
            instrument_token=key,
            order_type=ot_map.get(order_type.upper(), "MARKET"),
            transaction_type=transaction_type.upper(),
            disclosed_quantity=0,
            trigger_price=trigger_price if trigger_price else 0.0,
            is_amo=False,
            slice=kwargs.get("slice", True),
        )
        try:
            api = self._get_order_api()
            resp = api.place_order(body)
            resp_data = getattr(resp, "data", None)
            order_id = getattr(resp_data, "order_id", "") if resp_data else ""
            return OrderResult(success=True, order_id=str(order_id or ""),
                               message="Order placed successfully")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def modify_order(self, order_id: str, exchange: str, symbol: str,
                     order_type: str, quantity: int, price: float = 0.0,
                     trigger_price: float = 0.0, **kwargs) -> OrderResult:
        import upstox_client
        ot_map = {"MARKET": "MARKET", "LIMIT": "LIMIT", "SL": "SL", "SL-M": "SL-M"}
        body = upstox_client.ModifyOrderV3Request(
            quantity=quantity,
            validity="DAY",
            price=price if price else 0.0,
            order_id=order_id,
            order_type=ot_map.get(order_type.upper(), "LIMIT"),
            disclosed_quantity=0,
            trigger_price=trigger_price if trigger_price else 0.0,
        )
        try:
            api = self._get_order_api()
            api.modify_order(body)
            return OrderResult(success=True, order_id=order_id,
                               message="Order modified")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def cancel_order(self, order_id: str, exchange: str = "") -> OrderResult:
        try:
            api = self._get_order_api()
            api.cancel_order(order_id)
            return OrderResult(success=True, order_id=order_id,
                               message="Order cancelled")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def get_positions(self) -> list[Position]:
        api = self._get_portfolio_api()
        data = api.get_positions()
        positions = []
        items = getattr(data, "data", None) or []
        for pos in items:
            qty = int(getattr(pos, "quantity", 0) or 0)
            if qty == 0:
                continue
            positions.append(Position(
                symbol=getattr(pos, "trading_symbol", ""),
                exchange=getattr(pos, "exchange", ""),
                quantity=qty,
                average_price=float(getattr(pos, "average_price", 0) or 0),
                last_price=float(getattr(pos, "last_price", 0) or 0),
                pnl=float(getattr(pos, "unrealised", 0) or 0),
                product=getattr(pos, "product", ""),
            ))
        return positions

    def get_holdings(self) -> list[Holding]:
        api = self._get_portfolio_api()
        data = api.get_holdings()
        items = getattr(data, "data", None) or []
        return [Holding(
            symbol=getattr(h, "trading_symbol", ""),
            exchange=getattr(h, "exchange", "NSE"),
            quantity=int(getattr(h, "quantity", 0) or 0),
            average_price=float(getattr(h, "average_price", 0) or 0),
            last_price=float(getattr(h, "last_price", 0) or 0),
            pnl=float(getattr(h, "pnl", 0) or 0),
            product=getattr(h, "product", ""),
        ) for h in items]

    def get_orders(self) -> list[dict]:
        api = self._get_order_api()
        data = api.get_order_book()
        items = getattr(data, "data", None) or []
        return [vars(h) if not isinstance(h, dict) else h for h in items]

    def get_trades(self) -> list[dict]:
        api = self._get_order_api()
        data = api.get_trades()
        items = getattr(data, "data", None) or []
        return [vars(t) if not isinstance(t, dict) else t for t in items]

    def exit_position(self, exchange: str, symbol: str, quantity: int,
                      transaction_type: str, product: str = "MIS",
                      **kwargs) -> OrderResult:
        return self.place_order(
            exchange=exchange, symbol=symbol,
            transaction_type=transaction_type,
            quantity=abs(quantity), order_type="MARKET",
            product=product,
        )

    def exit_all_positions(self) -> list[OrderResult]:
        positions = self.get_positions()
        if not positions:
            return [OrderResult(success=True, message="No positions to exit")]
        results = []
        for pos in positions:
            txn = "SELL" if pos.quantity > 0 else "BUY"
            r = self.exit_position(
                exchange=pos.exchange, symbol=pos.symbol,
                quantity=abs(pos.quantity), transaction_type=txn,
                product=pos.product,
            )
            results.append(r)
        return results

    def search_instrument(self, query: str, exchange: str = "NSE") -> list[dict]:
        api = self._get_instruments_api()
        try:
            data = api.search_instrument(query=query)
            items = getattr(data, "data", None) or []
        except Exception:
            return []

        results = []
        for inst in items:
            inst_exchange = getattr(inst, "exchange", "")
            if exchange.upper() not in inst_exchange.upper() and exchange.upper() != "ALL":
                continue
            sym = getattr(inst, "symbol", "") or getattr(inst, "tradingsymbol", "")
            name = getattr(inst, "name", "") or getattr(inst, "company_name", "")
            token = getattr(inst, "instrument_key", "") or getattr(inst, "token", "")
            results.append({
                "symbol": sym,
                "name": name,
                "exchange": inst_exchange,
                "token": str(token),
            })
            if len(results) >= 50:
                break
        return results

    def get_instrument_token(self, exchange: str, symbol: str) -> str:
        return self._instrument_key(exchange, symbol)
