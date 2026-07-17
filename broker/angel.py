
from datetime import datetime
import pandas as pd
from broker.base import BrokerBase, OrderResult, Position, Holding


class AngelBroker(BrokerBase):
    """Angel One SmartAPI integration."""

    name = "Angel One SmartAPI"

    def __init__(self):
        self.api = None
        self.feed_token = ""
        self.auth_token = ""
        self.refresh_token = ""
        self.client_code = ""
        self.connected = False

    def connect(self, api_key: str = "", client_code: str = "",
                password: str = "", totp_secret: str = "", **kwargs) -> bool:
        from SmartApi.smartConnect import SmartConnect
        import pyotp

        self.api = SmartConnect(api_key=api_key)
        self.client_code = client_code

        totp = pyotp.TOTP(totp_secret).now()
        data = self.api.generateSession(client_code, password, totp)

        if not data.get("status"):
            raise ConnectionError(f"Angel One login failed: {data}")

        self.auth_token = data["data"]["jwtToken"]
        self.refresh_token = data["data"]["refreshToken"]
        self.feed_token = self.api.getfeedToken()
        self.api.generateToken(self.refresh_token)
        self.connected = True
        return True

    def disconnect(self) -> None:
        try:
            if self.api and self.client_code:
                self.api.terminateSession(self.client_code)
        except Exception:
            pass
        self.api = None
        self.connected = False

    def get_profile(self) -> dict:
        try:
            rms = self.api.rmsLimit()
            data = rms.get("data", {}) if isinstance(rms, dict) else {}
            return {
                "name": self.client_code,
                "broker": "Angel One",
                "client_id": self.client_code,
                "available_cash": float(data.get("availableCash", 0)),
                "used_margin": float(data.get("usedMargin", 0)),
                "total_margin": float(data.get("availableMargin", 0)),
            }
        except Exception:
            return {
                "name": self.client_code,
                "broker": "Angel One",
                "client_id": self.client_code,
                "available_cash": 0,
                "used_margin": 0,
                "total_margin": 0,
            }

    def _resolve_exchange(self, exchange: str) -> str:
        mapping = {"NSE": "NSE", "BSE": "BSE", "NFO": "NFO", "MCX": "MCX",
                    "NCDEX": "NCDEX"}
        return mapping.get(exchange.upper(), "NSE")

    def get_ltp(self, exchange: str, symbol: str) -> float:
        token = self.get_instrument_token(exchange, symbol)
        data = self.api.ltpData(self._resolve_exchange(exchange), symbol, str(token))
        if data and data.get("data"):
            return float(data["data"].get("ltp", 0))
        return 0.0

    def get_quote(self, exchange: str, symbol: str) -> dict:
        token = self.get_instrument_token(exchange, symbol)
        mode = "FULL"
        exchange_tokens = {self._resolve_exchange(exchange): [str(token)]}
        data = self.api.getMarketData(mode, exchange_tokens)
        if data and data.get("data"):
            for item in data["data"]:
                if item.get("symbol") == symbol or item.get("token") == str(token):
                    return item
        return data.get("data", {}) if isinstance(data, dict) else {}

    def get_historical(self, exchange: str, symbol: str, interval: str,
                       from_date: str, to_date: str) -> pd.DataFrame:
        token = self.get_instrument_token(exchange, symbol)
        interval_map = {
            "minute": "1minute", "3minute": "5minute",
            "5minute": "5minute", "15minute": "15minute",
            "30minute": "30minute", "hour": "hour", "day": "day",
        }
        params = {
            "exchange": self._resolve_exchange(exchange),
            "symboltoken": str(token),
            "interval": interval_map.get(interval, "day"),
            "fromdate": from_date if " " in from_date else f"{from_date} 09:00",
            "todate": to_date if " " in to_date else f"{to_date} 15:30",
        }
        data = self.api.getCandleData(params)
        candles = data.get("data", []) if isinstance(data, dict) else []
        if not candles:
            return pd.DataFrame()
        df = pd.DataFrame(candles, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                           "close": "Close", "volume": "Volume"}, inplace=True)
        return df

    def place_order(self, exchange: str, symbol: str, transaction_type: str,
                    quantity: int, order_type: str = "MARKET",
                    price: float = 0.0, trigger_price: float = 0.0,
                    product: str = "MIS", validity: str = "DAY",
                    **kwargs) -> OrderResult:
        token = kwargs.get("symboltoken", self.get_instrument_token(exchange, symbol))

        ot_map = {
            "MARKET": "MARKET", "LIMIT": "LIMIT",
            "SL": "STOPLOSS_LIMIT", "SLM": "STOPLOSS_MARKET",
            "SL-M": "STOPLOSS_MARKET",
        }
        prod_map = {
            "MIS": "INTRADAY", "INTRADAY": "INTRADAY",
            "CNC": "DELIVERY", "DELIVERY": "DELIVERY",
            "NRML": "CARRYFORWARD",
        }
        params = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": str(token),
            "transactiontype": transaction_type.upper(),
            "exchange": self._resolve_exchange(exchange),
            "ordertype": ot_map.get(order_type.upper(), "MARKET"),
            "producttype": prod_map.get(product.upper(), "INTRADAY"),
            "duration": validity.upper(),
            "quantity": str(quantity),
            "price": str(price) if price else "0",
            "triggerprice": str(trigger_price) if trigger_price else "0",
        }
        try:
            order_id = self.api.placeOrder(params)
            return OrderResult(success=True, order_id=str(order_id),
                               message="Order placed successfully")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def modify_order(self, order_id: str, exchange: str, symbol: str,
                     order_type: str, quantity: int, price: float = 0.0,
                     trigger_price: float = 0.0, **kwargs) -> OrderResult:
        token = kwargs.get("symboltoken", self.get_instrument_token(exchange, symbol))
        ot_map = {"MARKET": "MARKET", "LIMIT": "LIMIT",
                  "SL": "STOPLOSS_LIMIT", "SLM": "STOPLOSS_MARKET"}
        params = {
            "variety": "NORMAL",
            "orderid": order_id,
            "ordertype": ot_map.get(order_type.upper(), "LIMIT"),
            "producttype": kwargs.get("producttype", "INTRADAY"),
            "duration": "DAY",
            "price": str(price),
            "quantity": str(quantity),
            "tradingsymbol": symbol,
            "symboltoken": str(token),
            "exchange": self._resolve_exchange(exchange),
        }
        try:
            self.api.modifyOrder(params)
            return OrderResult(success=True, order_id=order_id,
                               message="Order modified")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def cancel_order(self, order_id: str, exchange: str = "") -> OrderResult:
        try:
            self.api.cancelOrder(order_id, "NORMAL")
            return OrderResult(success=True, order_id=order_id,
                               message="Order cancelled")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def get_positions(self) -> list[Position]:
        data = self.api.position()
        positions = []
        items = data.get("data", []) if isinstance(data, dict) else []
        for pos in items:
            qty = int(pos.get("netqty", 0))
            if qty == 0:
                continue
            positions.append(Position(
                symbol=pos.get("tradingsymbol", ""),
                exchange=pos.get("exchange", ""),
                quantity=qty,
                average_price=float(pos.get("averageprice", 0)),
                last_price=float(pos.get("ltp", 0)),
                pnl=float(pos.get("pnl", 0)),
                product=pos.get("producttype", ""),
                token=pos.get("symboltoken", ""),
            ))
        return positions

    def get_holdings(self) -> list[Holding]:
        data = self.api.holding()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [Holding(
            symbol=h.get("tradingsymbol", ""),
            exchange=h.get("exchange", "NSE"),
            quantity=int(h.get("quantity", 0)),
            average_price=float(h.get("averageprice", 0)),
            last_price=float(h.get("ltp", 0)),
            pnl=float(h.get("pnl", 0)),
            product=h.get("producttype", "DELIVERY"),
        ) for h in items]

    def get_orders(self) -> list[dict]:
        data = self.api.orderBook()
        return data.get("data", []) if isinstance(data, dict) else []

    def get_trades(self) -> list[dict]:
        data = self.api.tradeBook()
        return data.get("data", []) if isinstance(data, dict) else []

    def exit_position(self, exchange: str, symbol: str, quantity: int,
                      transaction_type: str, product: str = "MIS",
                      **kwargs) -> OrderResult:
        token = kwargs.get("symboltoken", "")
        return self.place_order(
            exchange=exchange, symbol=symbol,
            transaction_type=transaction_type,
            quantity=abs(quantity), order_type="MARKET",
            product=product, symboltoken=token,
        )

    def exit_all_positions(self) -> list[OrderResult]:
        results = []
        for pos in self.get_positions():
            if pos.quantity > 0:
                txn = "SELL"
            elif pos.quantity < 0:
                txn = "BUY"
            else:
                continue
            r = self.exit_position(
                exchange=pos.exchange, symbol=pos.symbol,
                quantity=abs(pos.quantity), transaction_type=txn,
                product=pos.product, symboltoken=pos.token,
            )
            results.append(r)
        return results

    def search_instrument(self, query: str, exchange: str = "NSE") -> list[dict]:
        try:
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            import requests
            resp = requests.get(url, timeout=10)
            instruments = resp.json()
        except Exception:
            return []

        q = query.upper()
        ex = self._resolve_exchange(exchange)
        results = []
        for inst in instruments:
            if inst.get("exch_seg") != ex:
                continue
            sym = inst.get("symbol", "").upper()
            name = inst.get("name", "").upper()
            if q in sym or q in name:
                results.append({
                    "symbol": inst.get("symbol", ""),
                    "name": inst.get("name", ""),
                    "exchange": inst.get("exch_seg", ""),
                    "token": str(inst.get("token", "")),
                })
                if len(results) >= 50:
                    break
        return results

    def get_instrument_token(self, exchange: str, symbol: str) -> str:
        instruments = self.search_instrument(symbol, exchange)
        if instruments:
            return instruments[0]["token"]
        return ""
