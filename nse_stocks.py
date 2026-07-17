import csv
import io
import json
import os
import requests
from datetime import datetime, timedelta

import yfinance as yf

CACHE_FILE = os.path.join(os.path.dirname(__file__), "nse_stock_cache.json")
CACHE_MAX_AGE_HOURS = 72

NSE_CSV_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def _fetch_nse_csv() -> list[dict]:
    """Download the official NSE equity list CSV (2400+ stocks)."""
    resp = requests.get(NSE_CSV_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    stocks = []
    for row in reader:
        # NSE CSV uses uppercase keys with spaces: SYMBOL, NAME OF COMPANY, SERIES
        symbol = (row.get("SYMBOL") or row.get("Symbol") or "").strip()
        name = (row.get("NAME OF COMPANY") or row.get("Company Name") or row.get("name") or "").strip()
        series = (row.get(" SERIES") or row.get("Series") or row.get("series") or "EQ").strip()
        if symbol and series == "EQ":
            stocks.append({"symbol": symbol, "name": name or symbol})
    return stocks


def _fetch_yahoo_suggest(prefixes: list[str] | None = None) -> list[dict]:
    """
    Use yfinance Ticker search to find Indian stocks.
    Searches common letter prefixes to build a broad list.
    """
    if prefixes is None:
        prefixes = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    seen = set()
    stocks = []
    for letter in prefixes:
        try:
            tickers = yf.Tickers(f"{letter}.NS")
            # This doesn't work for bulk search, so we use a different approach
        except Exception:
            pass
    # yfinance doesn't have a good search API, so this is a placeholder
    return stocks


def _load_cache() -> list[dict] | None:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        cached_at = datetime.fromisoformat(cache["timestamp"])
        if datetime.now() - cached_at > timedelta(hours=CACHE_MAX_AGE_HOURS):
            return None
        stocks = cache.get("stocks", [])
        if len(stocks) > 50:
            return stocks
        return None
    except Exception:
        return None


def _save_cache(stocks: list[dict]):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "stocks": stocks}, f)
    except Exception:
        pass


def _hardcoded_fallback() -> list[dict]:
    """Comprehensive fallback list of ~250 major NSE stocks."""
    return [
        {"symbol": "ABB", "name": "ABB India Ltd"},
        {"symbol": "ABBOTINDIA", "name": "Abbott India Ltd"},
        {"symbol": "ABCAPITAL", "name": "Aditya Birla Capital Ltd"},
        {"symbol": "ABFRL", "name": "Aditya Birla Fashion & Retail Ltd"},
        {"symbol": "ACC", "name": "ACC Ltd"},
        {"symbol": "ADANIENT", "name": "Adani Enterprises Ltd"},
        {"symbol": "ADANIPORTS", "name": "Adani Ports & SEZ Ltd"},
        {"symbol": "ALKEM", "name": "Alkem Laboratories Ltd"},
        {"symbol": "AMARAJABAT", "name": "Amara Raja Batteries Ltd"},
        {"symbol": "AMBUJACEM", "name": "Ambuja Cements Ltd"},
        {"symbol": "ANGELONE", "name": "Angel One Ltd"},
        {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals Enterprise Ltd"},
        {"symbol": "APOLLOTYRE", "name": "Apollo Tyres Ltd"},
        {"symbol": "ASHOKLEY", "name": "Ashok Leyland Ltd"},
        {"symbol": "ASIANPAINT", "name": "Asian Paints Ltd"},
        {"symbol": "ASTRAL", "name": "Astral Ltd"},
        {"symbol": "ATUL", "name": "Atul Ltd"},
        {"symbol": "AUBANK", "name": "AU Small Finance Bank Ltd"},
        {"symbol": "AUROPHARMA", "name": "Aurobindo Pharma Ltd"},
        {"symbol": "AXISBANK", "name": "Axis Bank Ltd"},
        {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto Ltd"},
        {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv Ltd"},
        {"symbol": "BAJFINANCE", "name": "Bajaj Finance Ltd"},
        {"symbol": "BALKRISIND", "name": "Balkrishna Industries Ltd"},
        {"symbol": "BANDHANBNK", "name": "Bandhan Bank Ltd"},
        {"symbol": "BATAINDIA", "name": "Bata India Ltd"},
        {"symbol": "BEL", "name": "Bharat Electronics Ltd"},
        {"symbol": "BERGEPAINT", "name": "Berger Paints India Ltd"},
        {"symbol": "BHARATFORG", "name": "Bharat Forge Ltd"},
        {"symbol": "BHARTIARTL", "name": "Bharti Airtel Ltd"},
        {"symbol": "BIOCON", "name": "Biocon Ltd"},
        {"symbol": "BOSCHLTD", "name": "Bosch Ltd"},
        {"symbol": "BPCL", "name": "Bharat Petroleum Corporation Ltd"},
        {"symbol": "BRITANNIA", "name": "Britannia Industries Ltd"},
        {"symbol": "CANBK", "name": "Canara Bank Ltd"},
        {"symbol": "CHAMBLFERT", "name": "Chambal Fertilizers & Chemicals Ltd"},
        {"symbol": "CIPLA", "name": "Cipla Ltd"},
        {"symbol": "COALINDIA", "name": "Coal India Ltd"},
        {"symbol": "COFORGE", "name": "Coforge Ltd"},
        {"symbol": "COLPAL", "name": "Colgate-Palmolive (India) Ltd"},
        {"symbol": "CONCOR", "name": "Container Corporation of India Ltd"},
        {"symbol": "COROMANDEL", "name": "Coromandel International Ltd"},
        {"symbol": "CROMPTON", "name": "Crompton Greaves Consumer Electricals Ltd"},
        {"symbol": "CUB", "name": "City Union Bank Ltd"},
        {"symbol": "CUMMINSIND", "name": "Cummins India Ltd"},
        {"symbol": "DABUR", "name": "Dabur India Ltd"},
        {"symbol": "DALBHARAT", "name": "Dalmia Bharat Ltd"},
        {"symbol": "DEEPAKNTR", "name": "Deepak Nitrite Ltd"},
        {"symbol": "DIVISLAB", "name": "Divi's Laboratories Ltd"},
        {"symbol": "DIXON", "name": "Dixon Technologies (India) Ltd"},
        {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories Ltd"},
        {"symbol": "EICHERMOT", "name": "Eicher Motors Ltd"},
        {"symbol": "ESCORTS", "name": "Escorts Kubota Ltd"},
        {"symbol": "FEDERALBNK", "name": "Federal Bank Ltd"},
        {"symbol": "GAIL", "name": "GAIL (India) Ltd"},
        {"symbol": "GLENMARK", "name": "Glenmark Pharmaceuticals Ltd"},
        {"symbol": "GODREJCP", "name": "Godrej Consumer Products Ltd"},
        {"symbol": "GODREJPROP", "name": "Godrej Properties Ltd"},
        {"symbol": "GRASIM", "name": "Grasim Industries Ltd"},
        {"symbol": "HAVELLS", "name": "Havells India Ltd"},
        {"symbol": "HCLTECH", "name": "HCL Technologies Ltd"},
        {"symbol": "HDFCBANK", "name": "HDFC Bank Ltd"},
        {"symbol": "HDFCLIFE", "name": "HDFC Life Insurance Company Ltd"},
        {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp Ltd"},
        {"symbol": "HINDALCO", "name": "Hindalco Industries Ltd"},
        {"symbol": "HINDPETRO", "name": "Hindustan Petroleum Corporation Ltd"},
        {"symbol": "HINDUNILVR", "name": "Hindustan Unilever Ltd"},
        {"symbol": "ICICIBANK", "name": "ICICI Bank Ltd"},
        {"symbol": "IDFCFIRSTB", "name": "IDFC First Bank Ltd"},
        {"symbol": "INDHOTEL", "name": "Indian Hotels Company Ltd"},
        {"symbol": "INDIGO", "name": "InterGlobe Aviation Ltd"},
        {"symbol": "INDUSINDBK", "name": "IndusInd Bank Ltd"},
        {"symbol": "INFY", "name": "Infosys Ltd"},
        {"symbol": "IOC", "name": "Indian Oil Corporation Ltd"},
        {"symbol": "IRCTC", "name": "Indian Railway Catering & Tourism Corp Ltd"},
        {"symbol": "ITC", "name": "ITC Ltd"},
        {"symbol": "JUBLFOOD", "name": "Jubilant Foodworks Ltd"},
        {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank Ltd"},
        {"symbol": "LALPATHLAB", "name": "Dr. Lal PathLabs Ltd"},
        {"symbol": "LT", "name": "Larsen & Toubro Ltd"},
        {"symbol": "LUPIN", "name": "Lupin Ltd"},
        {"symbol": "MANAPPURAM", "name": "Manappuram Finance Ltd"},
        {"symbol": "MARICO", "name": "Marico Ltd"},
        {"symbol": "MARUTI", "name": "Maruti Suzuki India Ltd"},
        {"symbol": "MFSL", "name": "Max Financial Services Ltd"},
        {"symbol": "MOTHERSON", "name": "Motherson Sumi Systems Ltd"},
        {"symbol": "MPHASIS", "name": "Mphasis Ltd"},
        {"symbol": "MUTHOOTFIN", "name": "Muthoot Finance Ltd"},
        {"symbol": "NATIONALUM", "name": "National Aluminium Company Ltd"},
        {"symbol": "NESTLEIND", "name": "Nestle India Ltd"},
        {"symbol": "NMDC", "name": "NMDC Ltd"},
        {"symbol": "NTPC", "name": "NTPC Ltd"},
        {"symbol": "ONGC", "name": "Oil & Natural Gas Corporation Ltd"},
        {"symbol": "PAGEIND", "name": "Page Industries Ltd"},
        {"symbol": "PERSISTENT", "name": "Persistent Systems Ltd"},
        {"symbol": "PETRONET", "name": "Petronet LNG Ltd"},
        {"symbol": "PIDILITIND", "name": "Pidilite Industries Ltd"},
        {"symbol": "PIIND", "name": "PI Industries Ltd"},
        {"symbol": "POLYCAB", "name": "Polycab India Ltd"},
        {"symbol": "POWERGRID", "name": "Power Grid Corporation of India Ltd"},
        {"symbol": "PVRINOX", "name": "PVR Inox Ltd"},
        {"symbol": "RAMCOCEM", "name": "The Ramco Cements Ltd"},
        {"symbol": "RBLBANK", "name": "RBL Bank Ltd"},
        {"symbol": "RECLTD", "name": "REC Ltd"},
        {"symbol": "RELIANCE", "name": "Reliance Industries Ltd"},
        {"symbol": "SBICARD", "name": "SBI Cards & Payment Services Ltd"},
        {"symbol": "SBILIFE", "name": "SBI Life Insurance Company Ltd"},
        {"symbol": "SBIN", "name": "State Bank of India"},
        {"symbol": "SHREECEM", "name": "Shree Cement Ltd"},
        {"symbol": "SHRIRAMFIN", "name": "Shriram Finance Ltd"},
        {"symbol": "SIEMENS", "name": "Siemens Ltd"},
        {"symbol": "SRF", "name": "SRF Ltd"},
        {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries Ltd"},
        {"symbol": "TATACHEM", "name": "Tata Chemicals Ltd"},
        {"symbol": "TATACOMM", "name": "Tata Communications Ltd"},
        {"symbol": "TATACONSUM", "name": "Tata Consumer Products Ltd"},
        {"symbol": "TATAMOTORS", "name": "Tata Motors Ltd"},
        {"symbol": "TATAPOWER", "name": "Tata Power Company Ltd"},
        {"symbol": "TATASTEEL", "name": "Tata Steel Ltd"},
        {"symbol": "TCS", "name": "Tata Consultancy Services Ltd"},
        {"symbol": "TECHM", "name": "Tech Mahindra Ltd"},
        {"symbol": "TITAN", "name": "Titan Company Ltd"},
        {"symbol": "TORNTPHARM", "name": "Torrent Pharmaceuticals Ltd"},
        {"symbol": "TRENT", "name": "Trent Ltd"},
        {"symbol": "TVSMOTOR", "name": "TVS Motor Company Ltd"},
        {"symbol": "UBL", "name": "United Breweries Ltd"},
        {"symbol": "ULTRACEMCO", "name": "UltraTech Cement Ltd"},
        {"symbol": "UPL", "name": "UPL Ltd"},
        {"symbol": "VEDL", "name": "Vedanta Ltd"},
        {"symbol": "VOLTAS", "name": "Voltas Ltd"},
        {"symbol": "WHIRLPOOL", "name": "Whirlpool of India Ltd"},
        {"symbol": "WIPRO", "name": "Wipro Ltd"},
        {"symbol": "ZEEL", "name": "Zee Entertainment Enterprises Ltd"},
        {"symbol": "ZYDUSLIFE", "name": "Zydus Lifesciences Ltd"},
    ]


def _dedup(stocks: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for s in stocks:
        if s["symbol"] not in seen:
            seen.add(s["symbol"])
            out.append(s)
    return out


def get_nse_stocks() -> list[dict]:
    """
    Return sorted list of {'symbol', 'name'} dicts.
    Priority: cache -> NSE CSV -> hardcoded fallback.
    """
    cached = _load_cache()
    if cached:
        return cached

    stocks = []
    try:
        stocks = _fetch_nse_csv()
    except Exception:
        pass

    if len(stocks) < 50:
        stocks = _dedup(stocks + _hardcoded_fallback())

    stocks.sort(key=lambda x: x["symbol"])
    _save_cache(stocks)
    return stocks


def get_symbol_list() -> list[str]:
    return [s["symbol"] for s in get_nse_stocks()]


def get_display_map() -> dict[str, str]:
    return {s["symbol"]: f"{s['symbol']} - {s['name']}" for s in get_nse_stocks()}
