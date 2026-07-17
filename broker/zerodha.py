from datetime import datetime, timedelta
import pandas as pd
from broker.base import BrokerBase, OrderResult, Position, Holding


class ZerodhaBroker(BrokerBase):
    """Zerodha Kite Connect integration."""

    name = "Zerodha Kite Connect"

    def __init__(self):
        self.kite = None
        self.connected = False
        self._instruments_cache: list[dict] = []

    def connect(self, api_key: str = "", request_token: str = "",
                api_secret: str = "", access_token: str = "", **kwargs) -> bool:
        from kiteconnect import KiteConnect

        self.kite = KiteConnect(api_key=api_key)

        if access_token:
            self.kite.set_access_token(access_token)
        elif request_token and api_secret:
            data = self.kite.generate_session(request_token, api_secret=api_secret)
            self.kite.set_access_token(data["access_token"])
        else:
            raise ValueError(
                "Provide either access_token or (request_token + api_secret).\n"
                f"Login URL: {self.kite.login_url()}"
            )

        self.connected = True
        return True

    def get_login_url(self, api_key: str) -> str:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=api_key)
        return kite.login_url()

    def disconnect(self) -> None:
        self.kite = None
        self.connected = False

    def get_profile(self) -> dict:
        profile = self.kite.profile()
        margins = self.kite.margins()
        equity = margins.get("equity", {})
        return {
            "name": profile.get("user_name", ""),
            "broker": profile.get("broker", ""),
            "client_id": profile.get("user_id", ""),
            "available_cash": equity.get("available", {}).get("cash", 0),
            "used_margin": equity.get("used", {}).get("debits", 0),
            "total_margin": equity.get("net", 0),
        }

    def get_ltp(self, exchange: str, symbol: str) -> float:
        instrument = f"{exchange}:{symbol}"
        data = self.kite.ltp([instrument])
        return data[instrument]["last_price"]

    def get_quote(self, exchange: str, symbol: str) -> dict:
        instrument = f"{exchange}:{symbol}"
        data = self.kite.quote([instrument])
        return data.get(instrument, {})

    def get_historical(self, exchange: str, symbol: str, interval: str,
                       from_date: str, to_date: str) -> pd.DataFrame:
        token = self.get_instrument_token(exchange, symbol)
        interval_map = {
            "minute": self.kite.INTERVAL_MINUTE,
            "3minute": self.kite.INTERVAL_3MINUTE,
            "5minute": self.kite.INTERVAL_5MINUTE,
            "15minute": self.kite.INTERVAL_15MINUTE,
            "30minute": self.kite.INTERVAL_30MINUTE,
            "hour": self.kite.INTERVAL_HOUR,
            "day": self.kite.INTERVAL_DAY,
        }
        ki_interval = interval_map.get(interval, self.kite.INTERVAL_DAY)
        candles = self.kite.historical_data(
            instrument_token=int(token),
            from_date=from_date,
            to_date=to_date,
            interval=ki_interval,
        )
        if not candles:
            return pd.DataFrame()
        df = pd.DataFrame(candles)
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
        txn = self.kite.TRANSACTION_TYPE_BUY if transaction_type.upper() == "BUY" \
            else self.kite.TRANSACTION_TYPE_SELL

        ot_map = {
            "MARKET": self.kite.ORDER_TYPE_MARKET,
            "LIMIT": self.kite.ORDER_TYPE_LIMIT,
            "SL": self.kite.ORDER_TYPE_SL,
            "SLM": self.kite.ORDER_TYPE_SLM,
            "SL-M": self.kite.ORDER_TYPE_SLM,
        }
        ot = ot_map.get(order_type.upper(), self.kite.ORDER_TYPE_MARKET)

        prod_map = {
            "MIS": self.kite.PRODUCT_MIS,
            "CNC": self.kite.PRODUCT_CNC,
            "NRML": self.kite.PRODUCT_NRML,
            "INTRADAY": self.kite.PRODUCT_MIS,
            "DELIVERY": self.kite.PRODUCT_CNC,
        }
        pr = prod_map.get(product.upper(), self.kite.PRODUCT_MIS)

        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=symbol,
                transaction_type=txn,
                quantity=quantity,
                product=pr,
                order_type=ot,
                price=price,
                trigger_price=trigger_price,
                validity=validity,
            )
            return OrderResult(success=True, order_id=str(order_id),
                               message="Order placed successfully")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def modify_order(self, order_id: str, exchange: str, symbol: str,
                     order_type: str, quantity: int, price: float = 0.0,
                     trigger_price: float = 0.0, **kwargs) -> OrderResult:
        ot_map = {
            "MARKET": self.kite.ORDER_TYPE_MARKET,
            "LIMIT": self.kite.ORDER_TYPE_LIMIT,
            "SL": self.kite.ORDER_TYPE_SL,
            "SLM": self.kite.ORDER_TYPE_SLM,
        }
        try:
            self.kite.modify_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order_id,
                order_type=ot_map.get(order_type.upper(), self.kite.ORDER_TYPE_LIMIT),
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
            )
            return OrderResult(success=True, order_id=order_id,
                               message="Order modified")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def cancel_order(self, order_id: str, exchange: str = "") -> OrderResult:
        try:
            self.kite.cancel_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order_id,
            )
            return OrderResult(success=True, order_id=order_id,
                               message="Order cancelled")
        except Exception as e:
            return OrderResult(success=False, message=str(e))

    def get_positions(self) -> list[Position]:
        data = self.kite.positions()
        positions = []
        for pos in data.get("day", []) + data.get("overnight", []):
            qty = int(pos.get("quantity", 0))
            if qty == 0:
                continue
            positions.append(Position(
                symbol=pos.get("tradingsymbol", ""),
                exchange=pos.get("exchange", ""),
                quantity=qty,
                average_price=float(pos.get("average_price", 0)),
                last_price=float(pos.get("last_price", 0)),
                pnl=float(pos.get("pnl", 0)),
                product=pos.get("product", ""),
            ))
        return positions

    def get_holdings(self) -> list[Holding]:
        data = self.kite.holdings()
        return [Holding(
            symbol=h.get("tradingsymbol", ""),
            exchange=h.get("exchange", "NSE"),
            quantity=int(h.get("quantity", 0)),
            average_price=float(h.get("average_price", 0)),
            last_price=float(h.get("last_price", 0)),
            pnl=float(h.get("pnl", 0)),
            product=h.get("product", "CNC"),
        ) for h in data]

    def get_orders(self) -> list[dict]:
        return self.kite.orders()

    def get_trades(self) -> list[dict]:
        return self.kite.trades()

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
                product=pos.product,
            )
            results.append(r)
        return results

    def search_instrument(self, query: str, exchange: str = "NSE") -> list[dict]:
        if not self._instruments_cache:
            try:
                self._instruments_cache = self.kite.instruments()
            except Exception:
                return []
        q = query.upper()
        results = []
        for inst in self._instruments_cache:
            if inst.get("exchange") != exchange:
                continue
            sym = inst.get("tradingsymbol", "").upper()
            name = inst.get("name", "").upper()
            if q in sym or q in name:
                results.append({
                    "symbol": inst.get("tradingsymbol", ""),
                    "name": inst.get("name", ""),
                    "exchange": inst.get("exchange", ""),
                    "token": str(inst.get("instrument_token", "")),
                })
                if len(results) >= 50:
                    break
        return results

    def get_instrument_token(self, exchange: str, symbol: str) -> str:
        instruments = self.search_instrument(symbol, exchange)
        if instruments:
            return instruments[0]["token"]
        return symbol
