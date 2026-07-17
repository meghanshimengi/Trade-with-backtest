
from broker.base import BrokerBase
from broker.zerodha import ZerodhaBroker
from broker.angel import AngelBroker
from broker.upstox import UpstoxBroker
from broker.manager import BrokerManager

BROKERS = {
    "Zerodha Kite Connect": ZerodhaBroker,
    "Angel One SmartAPI": AngelBroker,
    "Upstox API v2": UpstoxBroker,
}

__all__ = ["BrokerBase", "ZerodhaBroker", "AngelBroker", "UpstoxBroker", "BrokerManager", "BROKERS"]
