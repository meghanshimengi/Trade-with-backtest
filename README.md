# Indian Stock Market Backtester & Live Trader

A full-featured **Streamlit** web application for backtesting trading strategies on Indian stock markets (NSE/BSE) and executing them live through integrated broker APIs.

---

## Features

### Backtesting Engine
- Download historical OHLCV data via **Yahoo Finance** for 2400+ NSE stocks
- 6 built-in strategies: RSI, SMA Crossover, EMA Crossover, MACD, Bollinger Bands, Supertrend
- Custom strategy input in plain English (e.g. "Buy when RSI goes below 25")
- Configurable parameters for each strategy
- Realistic transaction cost model (0.1% per trade)
- 12 performance KPIs: Total Return, CAGR, Max Drawdown, Sharpe Ratio, Win Rate, Profit Factor, etc.
- Interactive Plotly charts: equity curve, drawdown, candlestick with indicator overlays, buy/sell markers
- Full trade log with color-coded P&L

### Live Trading
- Connect to real brokers and trade on live market data
- Real-time LTP (Last Traded Price) quotes
- Strategy signal computation on live data (BUY / SELL / HOLD)
- Manual order placement (MARKET, LIMIT, SL, SL-M)
- Auto-execute mode: automatically place orders when strategy triggers
- View open positions with unrealized P&L
- View delivery holdings
- Order book and trade book
- Exit individual positions or exit all at once
- Live candlestick price charts

### Supported Brokers

| Broker | Auth Method | Package |
|--------|-------------|---------|
| **Zerodha Kite Connect** | API Key + OAuth + TOTP | `kiteconnect` |
| **Angel One SmartAPI** | API Key + Client Code + PIN + TOTP | `smartapi-python` |
| **Upstox API v2** | API Key + Secret + OAuth 2.0 | `upstox-python-sdk` |

- Supports **NSE**, **BSE**, **NFO**, **MCX** exchanges
- Trade both **stocks** and **indices** (NIFTY 50, BANKNIFTY, etc.)
- Save broker credentials securely for quick reconnect

### User System
- User registration with **username**, **password**, **email**, **mobile number**
- Login / Logout
- **Forgot Password**: verify via email or mobile, generate reset token, reset password
- **Change Password** after login
- Credentials stored in local SQLite database (passwords hashed with SHA-256)

### Admin Panel
- Admin account: `administrator` / `Jitu4680**` (change password after first login)
- View user statistics (total users, active users)
- User management: view all users, edit email/mobile/status
- Reset any user's password
- Delete user accounts
- Change own admin password
- Admin account is protected from deletion and self-reset

---

## Project Structure

```
backtestopencode/
├── app.py                    # Main Streamlit application (UI + orchestration)
├── backtest_engine.py        # Backtesting engine (data fetch, simulation, KPIs)
├── strategies.py             # Technical indicators + strategy definitions + NL parser
├── nse_stocks.py             # NSE stock list fetcher with caching
├── database.py               # SQLite database (users, credentials, password resets)
├── broker/
│   ├── __init__.py           # Module exports
│   ├── base.py               # Abstract base class for all brokers
│   ├── zerodha.py            # Zerodha Kite Connect integration
│   ├── angel.py              # Angel One SmartAPI integration
│   ├── upstox.py             # Upstox API v2 integration
│   └── manager.py            # Broker manager (connection, signals, orders)
├── requirements.txt          # Python dependencies
└── broker_credentials.db     # SQLite database (auto-created on first run)
```

---

## Installation

### Prerequisites
- Python 3.10 or higher
- pip

### Steps

```bash
# Clone the repository
git clone <your-repo-url>
cd backtestopencode

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run app.py
```

The app opens at **http://localhost:8501** by default.

---

## Quick Start

### Backtesting (No login required)
1. Open the app in your browser
2. In the sidebar, select **"Backtest"** mode
3. Choose a stock from the dropdown or type a ticker (e.g. `RELIANCE`, `TCS`, `INFY`)
4. Set date range and select a strategy
5. Click **"Run Backtest"**
6. View equity curve, trade log, and performance metrics

### Live Trading
1. Switch to **"Live Trading"** mode in the sidebar
2. **Register** a new account (username, password, email, mobile required)
3. **Select a broker** (Zerodha / Angel One / Upstox)
4. Enter broker API credentials and click **Connect**
5. Search for an instrument (stock or index)
6. View live strategy signals or place manual orders
7. Monitor positions and P&L in real-time

---

## Broker Setup Guides

### Zerodha Kite Connect
1. Create an account at [kite.zerodha.com](https://kite.zerodha.com)
2. Go to [developers.kite.trade](https://developers.kite.trade) and create an app
3. Copy your **API Key** and **API Secret**
4. In the app, select "Access Token" auth method and enter your API key + access token
5. For fresh tokens, use "Request Token + Secret" method

**Note:** WebSocket streaming and historical data require Kite Connect paid tier (~Rs. 2000/month).

### Angel One SmartAPI
1. Create an account at [angelone.in](https://www.angelone.in)
2. Go to [smartapi.angelone.in](https://smartapi.angelone.in) and generate an API key
3. Note your **API Key**, **Client Code**, **PIN**, and **TOTP Secret** (from QR code)
4. Enter all credentials in the app and click Connect

**Note:** Free API access. TOTP generates a new code every 30 seconds.

### Upstox API v2
1. Create an account at [upstox.com](https://upstox.com)
2. Go to [api.upstox.com/developer/dashboard](https://api.upstox.com/developer/dashboard) and create an app
3. Set the **Redirect URL** (default: `http://localhost:8050`)
4. Copy your **API Key** (Client ID) and **Client Secret**
5. In the app, enter API Key, Secret, and Redirect URL
6. Click the login link, authorize, and paste the `code` from the redirect URL

**Note:** Free API access. Token expires daily; re-login required.

---

## Built-in Strategies

| Strategy | Buy Signal | Sell Signal | Key Parameters |
|----------|-----------|-------------|----------------|
| **RSI** | RSI drops below oversold level | RSI rises above overbought level | `period=14`, `oversold=30`, `overbought=70` |
| **SMA Crossover** | Short SMA crosses above Long SMA | Short SMA crosses below Long SMA | `short=20`, `long=50` |
| **EMA Crossover** | Short EMA crosses above Long EMA | Short EMA crosses below Long EMA | `short=12`, `long=26` |
| **MACD** | MACD line above signal line | MACD line below signal line | `fast=12`, `slow=26`, `signal=9` |
| **Bollinger Bands** | Price touches lower band | Price touches upper band | `period=20`, `std=2.0` |
| **Supertrend** | Supertrend flips bullish | Supertrend flips bearish | `period=10`, `multiplier=3.0` |

All parameters are editable in the sidebar.

---

## Admin Panel

Login as admin to access the admin panel with three tabs:

- **Statistics**: View total and active user counts
- **User Management**: View all users, edit details, reset passwords, delete accounts
- **Change Admin Password**: Change the admin account password

Admin account is protected:
- Cannot be deleted
- Cannot be self-reset from admin panel (must use Change Password form)

---

## Database

SQLite database `broker_credentials.db` is auto-created on first run with these tables:

| Table | Purpose |
|-------|---------|
| `users` | User accounts (username, hashed password, email, mobile, role) |
| `password_resets` | Password reset tokens (1-hour expiry) |
| `broker_credentials` | Saved broker API keys and tokens per user |
| `trade_sessions` | Trade session logs |

---

## Configuration

### Transaction Costs
Default 0.1% per trade (configurable in `backtest_engine.py`):
```python
TRANSACTION_COST_PCT = 0.001  # 0.1% per trade
```

### NSE Stock List
Fetched from NSE India archives and cached for 72 hours in `nse_stock_cache.json`. Falls back to a hardcoded list of ~130 major stocks if fetch fails.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| UI Framework | Streamlit |
| Data Source | Yahoo Finance (yfinance) |
| Charts | Plotly |
| Data Processing | Pandas, NumPy |
| Database | SQLite3 |
| Broker APIs | Kite Connect, SmartAPI, Upstox SDK |

---

## Disclaimer

This tool is for **educational and research purposes only**. Trading in stock markets involves risk. Past performance does not guarantee future results. Always do your own research before trading. The developers are not responsible for any financial losses.

---

## License

MIT License
