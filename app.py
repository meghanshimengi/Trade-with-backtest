import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta, datetime
import time

from nse_stocks import get_nse_stocks, get_display_map
from backtest_engine import fetch_data, run_backtest, run_backtest_from_text
from strategies import (
    BUILTIN_STRATEGIES, PARAM_DEFAULTS, parse_strategy_text,
    compute_rsi, compute_sma, compute_ema, compute_macd, compute_bollinger,
)
from broker import BROKERS, BrokerManager
from database import (
    authenticate_user, create_user, save_broker_credentials,
    load_broker_credentials, list_broker_credentials,
    get_user, change_password, find_user_by_email_or_mobile,
    create_password_reset_token, reset_password_with_token,
    list_all_users, admin_update_user, admin_delete_user,
    admin_reset_password, admin_change_own_password,
    get_user_count, get_active_user_count,
    ADMIN_USERNAME,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="My App", 
    layout="wide", 
    initial_sidebar_state="auto",
    menu_items=None
)

st.markdown("""
<style>
    .stMetric .metric-container { background: #f0f2f6; border-radius: 8px; padding: 12px; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem; }
    .trade-win { color: #28a745; font-weight: bold; }
    .trade-loss { color: #dc3545; font-weight: bold; }
    .signal-buy { background-color: #d4edda; color: #155724; padding: 8px 16px;
                  border-radius: 6px; font-size: 1.4rem; font-weight: bold; text-align: center; }
    .signal-sell { background-color: #f8d7da; color: #721c24; padding: 8px 16px;
                   border-radius: 6px; font-size: 1.4rem; font-weight: bold; text-align: center; }
    .signal-hold { background-color: #fff3cd; color: #856404; padding: 8px 16px;
                   border-radius: 6px; font-size: 1.4rem; font-weight: bold; text-align: center; }
    .broker-connected { background-color: #d4edda; color: #155724; padding: 6px 12px;
                        border-radius: 4px; font-weight: bold; }
    .broker-disconnected { background-color: #f8d7da; color: #721c24; padding: 6px 12px;
                           border-radius: 4px; }
    #MainMenu { visibility: hidden; }
   footer { visibility: hidden; }
    header { visibility: hidden; }
    .stDeployButton { display: none; }
    div[data-testid="stDecoration"] { display: none; }
    .stAppToolbar { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar — App Mode
# ---------------------------------------------------------------------------
st.sidebar.title("📈 Trading Platform")

app_mode = st.sidebar.radio(
    "Mode:",
    ["📊 Backtest", "🔴 Live Trading"],
    horizontal=True,
)

mgr = BrokerManager()

# =========================================================================
#                        BACKTEST MODE (existing logic)
# =========================================================================
if app_mode == "📊 Backtest":
    st.sidebar.subheader("1. Select Stock")
    stock_map = get_display_map()
    stock_list = list(stock_map.keys())

    input_mode = st.sidebar.radio(
        "Input mode:",
        ["Dropdown", "Type Ticker Manually"],
        horizontal=True,
    )

    if input_mode == "Dropdown":
        selected_display = st.sidebar.selectbox(
            "Search & select an NSE stock",
            options=[stock_map[s] for s in stock_list],
            index=stock_list.index("RELIANCE") if "RELIANCE" in stock_list else 0,
        )
        ticker = selected_display.split(" - ")[0]
    else:
        ticker = st.sidebar.text_input(
            "Enter Yahoo Finance ticker (e.g. RELIANCE, TCS, INFY)",
            value="RELIANCE",
        ).strip().upper()
        st.sidebar.caption("For NSE stocks, just enter the symbol. .NS is added automatically.")

    st.sidebar.subheader("2. Date Range")
    col1, col2 = st.sidebar.columns(2)
    end_date = col1.date_input("End Date", value=date.today())
    start_date = col2.date_input("Start Date", value=date.today() - timedelta(days=365))

    st.sidebar.subheader("3. Strategy")
    strategy_mode = st.sidebar.radio(
        "Choose mode:",
        ["Pre-built Strategies", "Custom (Type Your Own)"],
        horizontal=True,
    )

    if strategy_mode == "Pre-built Strategies":
        selected_strategy_label = st.sidebar.selectbox(
            "Select strategy",
            options=list(BUILTIN_STRATEGIES.keys()),
        )
        strategy_key = BUILTIN_STRATEGIES[selected_strategy_label]
        params = dict(PARAM_DEFAULTS.get(strategy_key, {}))

        st.sidebar.markdown("**Parameters:**")
        updated_params = {}
        for k, v in params.items():
            if isinstance(v, float):
                updated_params[k] = st.sidebar.number_input(
                    k, value=v, step=0.1, format="%.1f", key=f"param_{k}"
                )
            else:
                updated_params[k] = st.sidebar.number_input(
                    k, value=v, step=1, key=f"param_{k}"
                )
        params = updated_params
        strategy_text = None
    else:
        strategy_text = st.sidebar.text_area(
            "Describe your strategy in plain English",
            value="Buy when RSI goes below 30, sell when RSI goes above 70",
            height=100,
        )
        strategy_key, params = parse_strategy_text(strategy_text)
        st.sidebar.info(f"Detected: **{strategy_key.replace('_', ' ').title()}** | Params: {params}")

    capital = st.sidebar.number_input("Starting Capital (INR)", value=100_000, step=10_000, min_value=10_000)
    run_btn = st.sidebar.button("🚀 Run Backtest", type="primary", use_container_width=True)

    # --- Main: Backtest ---
    st.title("🇮🇳 Indian Stock Market Backtester")
    st.caption("NSE/BSE backtesting with real data, transaction costs, and no look-ahead bias.")

    if not run_btn:
        st.info("Configure your backtest in the sidebar and click **Run Backtest**.")
        st.stop()

    with st.spinner(f"Fetching data for {ticker}.NS ..."):
        try:
            df = fetch_data(ticker, str(start_date), str(end_date))
        except Exception as e:
            st.error(f"Failed to fetch data: {e}")
            st.stop()

    st.success(f"Loaded **{len(df)}** trading days for **{ticker}.NS** ({df.index[0].date()} → {df.index[-1].date()})")

    with st.spinner("Running backtest ..."):
        if strategy_text:
            result = run_backtest_from_text(df, strategy_text, capital)
        else:
            result = run_backtest(df, strategy_key, params, capital)

    metrics = result["metrics"]
    trades = result["trades"]
    bt_df = result["df"]

    st.subheader("🧠 Strategy Logic")
    if strategy_text:
        st.markdown(f"**User Input:** _{strategy_text}_")
        st.markdown(f"**Interpreted As:** `{strategy_key}` with params `{params}`")
    else:
        st.markdown(f"**Strategy:** {selected_strategy_label}")
        st.markdown(f"**Parameters:** `{params}`")

    logic_descriptions = {
        "rsi": f"Compute RSI({params.get('period', 14)}). **BUY** when RSI < {params.get('oversold', 30)}. **SELL** when RSI > {params.get('overbought', 70)}.",
        "sma_crossover": f"SMA({params.get('short_period', 20)}) vs SMA({params.get('long_period', 50)}). **BUY** when short > long. **SELL** when short < long.",
        "ema_crossover": f"EMA({params.get('short_period', 12)}) vs EMA({params.get('long_period', 26)}). **BUY** when short > long. **SELL** when short < long.",
        "macd": f"MACD({params.get('fast', 12)}/{params.get('slow', 26)}/{params.get('signal', 9)}). **BUY** when MACD > signal. **SELL** when MACD < signal.",
        "bollinger": f"Bollinger Bands(period={params.get('period', 20)}, std={params.get('num_std', 2.0)}). **BUY** at lower band. **SELL** at upper band.",
        "supertrend": f"Supertrend(period={params.get('period', 10)}, mult={params.get('multiplier', 3.0)}). **BUY** on bullish flip. **SELL** on bearish flip.",
    }
    st.info(logic_descriptions.get(strategy_key, "Custom strategy applied."))

    st.subheader("📊 Performance Metrics")
    kpi_cols = st.columns(4)
    kpi_items = [
        ("Total Return", f"{metrics['Total Return (%)']}%", "🟢" if metrics["Total Return (%)"] > 0 else "🔴"),
        ("Buy & Hold", f"{metrics['Buy & Hold Return (%)']}%", "📊"),
        ("Max Drawdown", f"{metrics['Max Drawdown (%)']}%", "⚠️"),
        ("Sharpe Ratio", f"{metrics['Sharpe Ratio']}", "📈"),
    ]
    for col, (label, value, icon) in zip(kpi_cols, kpi_items):
        col.metric(label=f"{icon} {label}", value=value)

    kpi_cols2 = st.columns(4)
    kpi_items2 = [
        ("Win Rate", f"{metrics['Win Rate (%)']}%", "🎯"),
        ("Total Trades", f"{metrics['Total Trades']}", "🔄"),
        ("Profit Factor", f"{metrics['Profit Factor']}", "💰"),
        ("CAGR", f"{metrics['CAGR (%)']}%", "📅"),
    ]
    for col, (label, value, icon) in zip(kpi_cols2, kpi_items2):
        col.metric(label=f"{icon} {label}", value=value)

    st.caption(f"Final Equity: Rs.{metrics['Final Equity (INR)']:,.2f} | Starting Capital: Rs.{capital:,.2f}")

    st.subheader("📈 Equity Curve vs Buy & Hold")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.7, 0.3], subplot_titles=("Equity Curve", "Drawdown"))
    fig.add_trace(go.Scatter(x=bt_df.index, y=bt_df["equity"], name="Strategy",
                             line=dict(color="#1f77b4", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=bt_df.index, y=bt_df["buy_hold_equity"], name="Buy & Hold",
                             line=dict(color="#ff7f0e", width=1.5, dash="dot")), row=1, col=1)
    running_max = bt_df["equity"].cummax()
    drawdown = (bt_df["equity"] - running_max) / running_max * 100
    fig.add_trace(go.Scatter(x=bt_df.index, y=drawdown, name="Drawdown",
                             fill="tozeroy", line=dict(color="crimson", width=1)), row=2, col=1)
    buys = bt_df[(bt_df["trade_flag"] == 1) & (bt_df["position"] == 1)]
    sells = bt_df[(bt_df["trade_flag"] == 1) & (bt_df["position"] == 0)]
    fig.add_trace(go.Scatter(x=buys.index, y=buys["Close"], mode="markers", name="BUY",
                             marker=dict(symbol="triangle-up", size=10, color="green")), row=1, col=1)
    fig.add_trace(go.Scatter(x=sells.index, y=sells["Close"], mode="markers", name="SELL",
                             marker=dict(symbol="triangle-down", size=10, color="red")), row=1, col=1)
    fig.update_layout(height=650, template="plotly_white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      margin=dict(l=50, r=30, t=40, b=20))
    fig.update_yaxes(title_text="Equity (INR)", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown %", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📉 Price Chart with Indicators")
    fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                         row_heights=[0.75, 0.25],
                         subplot_titles=(f"{ticker}.NS Price", "RSI" if strategy_key == "rsi" else "Volume"))
    fig2.add_trace(go.Candlestick(x=bt_df.index, open=bt_df["Open"], high=bt_df["High"],
                                  low=bt_df["Low"], close=bt_df["Close"], name="Price",
                                  increasing_line_color="#26a69a", decreasing_line_color="#ef5350"), row=1, col=1)
    for col_name, label, color in [
        ("sma_short", "SMA Short", "blue"), ("sma_long", "SMA Long", "orange"),
        ("ema_short", "EMA Short", "blue"), ("ema_long", "EMA Long", "orange"),
        ("supertrend", "Supertrend", "purple"),
    ]:
        if col_name in bt_df.columns:
            fig2.add_trace(go.Scatter(x=bt_df.index, y=bt_df[col_name], name=label,
                                      line=dict(color=color, width=1.5)), row=1, col=1)
    if "bb_upper" in bt_df.columns:
        fig2.add_trace(go.Scatter(x=bt_df.index, y=bt_df["bb_upper"], name="BB Upper",
                                  line=dict(color="gray", width=1, dash="dash")), row=1, col=1)
        fig2.add_trace(go.Scatter(x=bt_df.index, y=bt_df["bb_lower"], name="BB Lower",
                                  line=dict(color="gray", width=1, dash="dash"),
                                  fill="tonexty", fillcolor="rgba(128,128,128,0.1)"), row=1, col=1)
    if strategy_key == "rsi" and "rsi" in bt_df.columns:
        fig2.add_trace(go.Scatter(x=bt_df.index, y=bt_df["rsi"], name="RSI",
                                  line=dict(color="purple", width=1.5)), row=2, col=1)
        fig2.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig2.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
        fig2.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100])
    else:
        fig2.add_trace(go.Bar(x=bt_df.index, y=bt_df["Volume"], name="Volume",
                              marker_color="steelblue", opacity=0.6), row=2, col=1)
        fig2.update_yaxes(title_text="Volume", row=2, col=1)
    fig2.update_layout(height=600, template="plotly_white", xaxis_rangeslider_visible=False,
                       margin=dict(l=50, r=30, t=40, b=20))
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📋 Trade Log")
    if trades:
        trades_df = pd.DataFrame(trades)
        trades_df.index = range(1, len(trades_df) + 1)
        trades_df.index.name = "#"
        styled = trades_df.style.map(
            lambda x: "color: green;" if x > 0 else "color: red;" if x < 0 else "color: black;",
            subset=["pnl_pct"],
        )
        st.dataframe(styled, use_container_width=True)
    else:
        st.info("No trades executed in this period.")

    st.subheader("📑 KPI Summary Table")
    kpi_table = pd.DataFrame([
        {"Metric": k, "Value": metrics[k]} for k in [
            "Total Return (%)", "Buy & Hold Return (%)", "CAGR (%)",
            "Max Drawdown (%)", "Sharpe Ratio", "Win Rate (%)",
            "Total Trades", "Winning Trades", "Losing Trades",
            "Profit Factor", "Avg Trade P&L (%)",
        ]
    ] + [{"Metric": "Final Equity (INR)", "Value": f"Rs.{metrics['Final Equity (INR)']:,.2f}"}]).set_index("Metric")
    st.table(kpi_table)

    st.divider()
    st.caption("⚠️ Disclaimer: For educational and research purposes only. Past performance does not guarantee future results.")

# =========================================================================
#                     LIVE TRADING MODE
# =========================================================================
else:
    # ---------------------------------------------------------------
    # SIDEBAR: User Authentication
    # ---------------------------------------------------------------
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "show_forgot" not in st.session_state:
        st.session_state.show_forgot = False
    if "show_change_pw" not in st.session_state:
        st.session_state.show_change_pw = False

    if not st.session_state.user_id:
        st.sidebar.subheader("🔐 Login / Register")

        auth_mode = st.sidebar.radio(
            "Account",
            ["Login", "Register", "Forgot Password"],
            horizontal=True,
            key="auth_mode",
        )

        if auth_mode == "Register":
            auth_user = st.sidebar.text_input("Username", key="auth_user")
            auth_pass = st.sidebar.text_input("Password", type="password", key="auth_pass",
                                               help="Min 6 characters")
            auth_email = st.sidebar.text_input("Email", key="auth_email")
            auth_mobile = st.sidebar.text_input("Mobile No.", key="auth_mobile",
                                                 help="10-digit mobile number")
            if st.sidebar.button("📝 Register", use_container_width=True, key="reg_btn"):
                if not auth_user or not auth_pass:
                    st.sidebar.error("Username and password are required")
                elif not auth_email or "@" not in auth_email:
                    st.sidebar.error("Valid email is required")
                elif not auth_mobile or len(auth_mobile) < 10:
                    st.sidebar.error("Valid 10-digit mobile number is required")
                elif len(auth_pass) < 6:
                    st.sidebar.error("Password must be at least 6 characters")
                else:
                    try:
                        uid = create_user(auth_user, auth_pass, auth_email, auth_mobile)
                        st.session_state.user_id = uid
                        st.session_state.username = auth_user
                        st.sidebar.success(f"Registered as {auth_user}")
                        st.rerun()
                    except Exception:
                        st.sidebar.error("Username already exists")

        elif auth_mode == "Forgot Password":
            st.sidebar.markdown("**Reset your password**")
            reset_identifier = st.sidebar.text_input(
                "Enter your Email or Mobile Number",
                key="reset_identifier",
                help="We will generate a reset token for you",
            )

            if st.sidebar.button("🔑 Get Reset Token", use_container_width=True, key="get_token_btn"):
                if not reset_identifier:
                    st.sidebar.error("Enter email or mobile")
                else:
                    user = find_user_by_email_or_mobile(reset_identifier)
                    if user:
                        token = create_password_reset_token(user["id"])
                        st.session_state["reset_token"] = token
                        st.sidebar.success("Token generated! (Since this is local, token shown below)")
                        st.sidebar.code(token, language=None)
                        st.sidebar.info("In production this would be sent via email/SMS.")
                    else:
                        st.sidebar.error("No account found with that email/mobile")

            new_pw = st.sidebar.text_input("New Password", type="password", key="reset_new_pw",
                                            help="Min 6 characters")
            reset_token_input = st.sidebar.text_area(
                "Paste Reset Token",
                value=st.session_state.get("reset_token", ""),
                key="reset_token_input",
                height=68,
            )
            if st.sidebar.button("✅ Reset Password", use_container_width=True, key="reset_pw_btn"):
                if not reset_token_input or not new_pw:
                    st.sidebar.error("Paste token and enter new password")
                elif len(new_pw) < 6:
                    st.sidebar.error("Password must be at least 6 characters")
                else:
                    ok, msg = reset_password_with_token(reset_token_input.strip(), new_pw)
                    if ok:
                        st.sidebar.success(msg)
                        st.session_state.pop("reset_token", None)
                    else:
                        st.sidebar.error(msg)

        else:
            auth_user = st.sidebar.text_input("Username", key="auth_user")
            auth_pass = st.sidebar.text_input("Password", type="password", key="auth_pass")
            if st.sidebar.button("🔑 Login", type="primary", use_container_width=True, key="login_btn"):
                uid = authenticate_user(auth_user, auth_pass)
                if uid:
                    st.session_state.user_id = uid
                    st.session_state.username = auth_user
                    st.rerun()
                else:
                    st.sidebar.error("Invalid credentials")

        if not st.session_state.user_id:
            st.info("Login or register to access live trading features.")
            st.stop()

    # --- Logged-in user info ---
    user_info = get_user(st.session_state.user_id)
    is_admin = user_info and user_info.get("role") == "admin" if user_info else False

    st.sidebar.caption(f"👤 Logged in as: **{st.session_state.username}**"
                       + (" (Admin)" if is_admin else ""))

    # --- Sidebar: Change Password ---
    if st.sidebar.button("🔑 Change Password", key="show_change_pw_btn"):
        st.session_state.show_change_pw = not st.session_state.get("show_change_pw", False)

    if st.session_state.get("show_change_pw"):
        with st.sidebar.form("change_pw_form", clear_on_submit=True):
            st.markdown("**Change Password**")
            old_pw = st.text_input("Current Password", type="password", key="cpw_old")
            new_pw = st.text_input("New Password", type="password", key="cpw_new",
                                   help="Min 6 characters")
            confirm_pw = st.text_input("Confirm New Password", type="password", key="cpw_confirm")
            cpw_submitted = st.form_submit_button("Update Password", use_container_width=True)
            if cpw_submitted:
                if not old_pw or not new_pw:
                    st.error("Fill all fields")
                elif new_pw != confirm_pw:
                    st.error("Passwords do not match")
                else:
                    ok, msg = change_password(st.session_state.user_id, old_pw, new_pw)
                    if ok:
                        st.success(msg)
                        st.session_state.show_change_pw = False
                        st.rerun()
                    else:
                        st.error(msg)

    if st.sidebar.button("🚪 Logout", use_container_width=True, key="logout_btn"):
        st.session_state.user_id = None
        st.session_state.username = ""
        st.session_state.show_change_pw = False
        mgr.disconnect()
        st.rerun()

    # ---------------------------------------------------------------
    # SIDEBAR: Broker Connection
    # ---------------------------------------------------------------
    st.sidebar.subheader("1. Connect Broker")

    if mgr.connected:
        st.sidebar.markdown(
            f'<div class="broker-connected">✅ Connected: {st.session_state.broker_name}</div>',
            unsafe_allow_html=True,
        )
        profile = mgr.get_profile()
        if profile:
            name = profile.get("name", "") or profile.get("client_id", "")
            st.sidebar.caption(f"Client: {name}")
            st.sidebar.caption(f"Available Cash: Rs.{profile.get('available_cash', 0):,.2f}")
        if st.sidebar.button("🔌 Disconnect", use_container_width=True):
            mgr.disconnect()
            st.rerun()
    else:
        broker_name = st.sidebar.selectbox("Select Broker", list(BROKERS.keys()))

        # --- Load saved credentials ---
        saved = load_broker_credentials(st.session_state.user_id, broker_name)
        if saved:
            st.sidebar.success(f"Found saved credentials for {broker_name}")
            if st.sidebar.button("⚡ Quick Connect with Saved Credentials", type="primary",
                                 use_container_width=True, key="quick_connect"):
                with st.spinner(f"Connecting to {broker_name}..."):
                    try:
                        connect_kwargs = dict(saved["additional_config"])
                        connect_kwargs["api_key"] = saved["api_key"]
                        connect_kwargs["client_secret"] = saved["api_secret"]
                        connect_kwargs["access_token"] = saved["access_token"]
                        ok, msg = mgr.connect(broker_name, **connect_kwargs)
                        if ok:
                            st.sidebar.success(msg)
                            st.rerun()
                        else:
                            st.sidebar.error(msg)
                    except Exception as e:
                        st.sidebar.error(f"Connection failed: {e}")

        # --- Credential input form ---
        st.sidebar.markdown("---")
        save_creds = st.sidebar.checkbox("Save credentials for future use", value=True, key="save_creds")

        if broker_name == "Zerodha Kite Connect":
            api_key = st.sidebar.text_input("API Key", value=saved["api_key"] if saved else "", key="z_api_key")
            auth_method = st.sidebar.radio("Auth method", ["Access Token", "Request Token + Secret"], horizontal=True, key="z_auth")
            if auth_method == "Access Token":
                access_token = st.sidebar.text_input("Access Token", key="z_token", type="password")
                api_secret = saved["api_secret"] if saved else ""
                request_token = ""
            else:
                request_token = st.sidebar.text_input("Request Token", key="z_req_token", type="password")
                api_secret = st.sidebar.text_input("API Secret", value=saved["api_secret"] if saved else "",
                                                    key="z_secret", type="password")
                access_token = ""
            if st.sidebar.button("🔌 Connect", type="primary", use_container_width=True, key="z_connect"):
                with st.spinner("Connecting to Zerodha..."):
                    ok, msg = mgr.connect(broker_name, api_key=api_key,
                                          access_token=access_token,
                                          request_token=request_token,
                                          api_secret=api_secret)
                if ok:
                    if save_creds:
                        save_broker_credentials(
                            st.session_state.user_id, broker_name,
                            api_key=api_key, api_secret=api_secret,
                            access_token=access_token,
                        )
                    st.sidebar.success(msg)
                    st.rerun()
                else:
                    st.sidebar.error(msg)

        elif broker_name == "Angel One SmartAPI":
            api_key = st.sidebar.text_input("API Key", value=saved["api_key"] if saved else "", key="a_api_key")
            client_code = st.sidebar.text_input("Client Code",
                                                 value=saved["additional_config"].get("client_code", "") if saved else "",
                                                 key="a_client")
            password = st.sidebar.text_input("PIN", key="a_pin", type="password")
            totp_secret = st.sidebar.text_input("TOTP Secret (QR code key)",
                                                 value=saved["api_secret"] if saved else "",
                                                 key="a_totp", type="password")
            if st.sidebar.button("🔌 Connect", type="primary", use_container_width=True, key="a_connect"):
                with st.spinner("Connecting to Angel One..."):
                    ok, msg = mgr.connect(broker_name, api_key=api_key,
                                          client_code=client_code,
                                          password=password, totp_secret=totp_secret)
                if ok:
                    if save_creds:
                        save_broker_credentials(
                            st.session_state.user_id, broker_name,
                            api_key=api_key, api_secret=totp_secret,
                            additional_config={"client_code": client_code},
                        )
                    st.sidebar.success(msg)
                    st.rerun()
                else:
                    st.sidebar.error(msg)

        elif broker_name == "Upstox API v2":
            st.sidebar.markdown("**Step 1:** Enter your Upstox app credentials")

            api_key = st.sidebar.text_input(
                "API Key (Client ID)",
                value=saved["api_key"] if saved else "",
                key="u_api_key",
                help="Your Upstox API key / client ID from developer portal",
            )
            client_secret = st.sidebar.text_input(
                "Client Secret (API Secret Key)",
                value=saved["api_secret"] if saved else "",
                key="u_secret",
                type="password",
                help="Your Upstox app secret key",
            )
            redirect_uri = st.sidebar.text_input(
                "Redirect URL",
                value=saved["additional_config"].get("redirect_uri", "http://localhost:8050") if saved else "http://localhost:8050",
                key="u_redirect",
                help="Must match the redirect URL registered in Upstox developer portal",
            )

            if api_key:
                from broker.upstox import UpstoxBroker
                auth_url = UpstoxBroker().get_auth_url(api_key, redirect_uri)
                st.sidebar.markdown(
                    f"**Step 2:** [Click here to login to Upstox]({auth_url})",
                )
                st.sidebar.caption("After login, copy the `code` from the redirect URL and paste below")

            code = st.sidebar.text_input(
                "Authorization Code",
                key="u_auth_code",
                type="password",
                help="Code from redirect URL after Upstox login",
            )

            st.sidebar.markdown("---")
            access_token_direct = st.sidebar.text_input(
                "Or enter Access Token directly (if you already have one)",
                key="u_token_direct",
                type="password",
            )

            if st.sidebar.button("🔌 Connect", type="primary", use_container_width=True, key="u_connect"):
                with st.spinner("Connecting to Upstox..."):
                    ok, msg = mgr.connect(
                        broker_name,
                        api_key=api_key,
                        client_secret=client_secret,
                        redirect_uri=redirect_uri,
                        code=code,
                        access_token=access_token_direct,
                    )
                if ok:
                    if save_creds:
                        save_broker_credentials(
                            st.session_state.user_id, broker_name,
                            api_key=api_key, api_secret=client_secret,
                            access_token=mgr.broker.access_token if mgr.broker else "",
                            additional_config={"redirect_uri": redirect_uri},
                        )
                    st.sidebar.success(msg)
                    st.rerun()
                else:
                    st.sidebar.error(msg)

    # ---------------------------------------------------------------
    # SIDEBAR: Instrument Selection (only if connected)
    # ---------------------------------------------------------------
    if mgr.connected:
        st.sidebar.subheader("2. Select Instrument")

        exchange = st.sidebar.selectbox("Exchange", ["NSE", "NFO", "BSE"], key="live_exchange")

        search_query = st.sidebar.text_input("Search instrument (type name or symbol)", key="inst_search")
        if search_query and len(search_query) >= 2:
            with st.spinner("Searching..."):
                results = mgr.search_instrument(search_query, exchange)
            if results:
                options = [f"{r['symbol']} — {r.get('name', '')}" for r in results]
                selected = st.sidebar.selectbox("Select instrument", options, key="inst_select")
                selected_idx = options.index(selected)
                live_symbol = results[selected_idx]["symbol"]
                live_token = results[selected_idx].get("token", "")
                st.sidebar.caption(f"Token: {live_token}")
            else:
                live_symbol = search_query.upper()
                live_token = ""
                st.sidebar.warning("No results. Using typed value as symbol.")
        else:
            live_symbol = st.sidebar.text_input("Or type symbol directly", value="RELIANCE", key="live_symbol_manual")
            live_token = ""

        live_quantity = st.sidebar.number_input("Quantity", value=1, min_value=1, step=1, key="live_qty")
        live_product = st.sidebar.selectbox("Product", ["MIS", "CNC", "NRML"], key="live_product")

        # ---------------------------------------------------------------
        # SIDEBAR: Strategy Selection for Live Signals
        # ---------------------------------------------------------------
        st.sidebar.subheader("3. Live Strategy")
        live_strategy_label = st.sidebar.selectbox(
            "Strategy for live signals",
            options=list(BUILTIN_STRATEGIES.keys()),
            key="live_strat",
        )
        live_strategy_key = BUILTIN_STRATEGIES[live_strategy_label]
        live_params = dict(PARAM_DEFAULTS.get(live_strategy_key, {}))

        st.sidebar.markdown("**Parameters:**")
        live_updated = {}
        for k, v in live_params.items():
            if isinstance(v, float):
                live_updated[k] = st.sidebar.number_input(
                    k, value=v, step=0.1, format="%.1f", key=f"live_param_{k}"
                )
            else:
                live_updated[k] = st.sidebar.number_input(
                    k, value=v, step=1, key=f"live_param_{k}"
                )
        live_params = live_updated

        live_interval = st.sidebar.selectbox("Data Interval", ["day", "5minute", "15minute", "hour"], key="live_int")
        auto_trade = st.sidebar.checkbox("Auto-execute trades on signal", value=False, key="auto_trade",
                                         help="Automatically place orders when strategy generates BUY/SELL signal")
        st.sidebar.caption("⚠️ Auto-trade places real orders. Use with caution!")

    # ---------------------------------------------------------------
    # MAIN AREA: Live Trading Dashboard
    # ---------------------------------------------------------------
    st.title("🔴 Live Trading Dashboard")

    # --- Admin Panel ---
    if is_admin:
        st.subheader("🛡️ Admin Panel")

        admin_tab_stats, admin_tab_users, admin_tab_change_pw = st.tabs([
            "📊 Statistics", "👥 User Management", "🔑 Change Admin Password",
        ])

        with admin_tab_stats:
            total = get_user_count()
            active = get_active_user_count()
            m1, m2 = st.columns(2)
            m1.metric("Total Users", total)
            m2.metric("Active Users", active)

        with admin_tab_users:
            all_users = list_all_users()
            if all_users:
                users_df = pd.DataFrame(all_users)
                st.dataframe(users_df, use_container_width=True)

                st.markdown("---")
                st.markdown("#### Manage User")
                manage_user = st.selectbox(
                    "Select user",
                    [f"{u['username']} (ID: {u['id']})" for u in all_users
                     if u["username"] != ADMIN_USERNAME],
                    key="admin_manage_user",
                )
                if manage_user:
                    uid_to_manage = int(manage_user.split("ID: ")[1].rstrip(")"))
                    user_obj = next((u for u in all_users if u["id"] == uid_to_manage), None)
                    if user_obj:
                        acol1, acol2 = st.columns(2)
                        with acol1:
                            new_email = st.text_input("Email", value=user_obj.get("email", ""),
                                                      key="admin_email")
                            new_mobile = st.text_input("Mobile", value=user_obj.get("mobile", ""),
                                                       key="admin_mobile")
                            new_status = st.checkbox("Active", value=bool(user_obj.get("is_active", 1)),
                                                     key="admin_active")
                            if st.button("💾 Update User", key="admin_update_user"):
                                ok, msg = admin_update_user(
                                    uid_to_manage, new_email, new_mobile, 1 if new_status else 0
                                )
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
                        with acol2:
                            reset_pw = st.text_input("Reset Password (new)", type="password",
                                                      key="admin_reset_pw")
                            if st.button("🔑 Reset User Password", key="admin_reset_btn"):
                                if reset_pw:
                                    ok, msg = admin_reset_password(uid_to_manage, reset_pw)
                                    if ok:
                                        st.success(msg)
                                    else:
                                        st.error(msg)
                                else:
                                    st.warning("Enter a new password")
                            if st.button("🗑️ Delete User", key="admin_delete_btn"):
                                ok, msg = admin_delete_user(uid_to_manage)
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)
            else:
                st.info("No users registered yet.")

        with admin_tab_change_pw:
            st.markdown("**Change admin password**")
            with st.form("admin_change_pw", clear_on_submit=True):
                admin_old_pw = st.text_input("Current Admin Password", type="password", key="admin_old_pw")
                admin_new_pw = st.text_input("New Admin Password", type="password", key="admin_new_pw")
                admin_confirm_pw = st.text_input("Confirm New Password", type="password", key="admin_confirm_pw")
                admin_pw_sub = st.form_submit_button("🔑 Update Admin Password", use_container_width=True)
                if admin_pw_sub:
                    if not admin_old_pw or not admin_new_pw:
                        st.error("Fill all fields")
                    elif admin_new_pw != admin_confirm_pw:
                        st.error("Passwords do not match")
                    else:
                        ok, msg = change_password(st.session_state.user_id, admin_old_pw, admin_new_pw)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)

    if not mgr.connected:
        st.warning("Please connect to a broker in the sidebar to start live trading.")
        st.stop()

    # --- Connection Status Banner ---
    st.success(f"Connected to **{st.session_state.broker_name}**")

    # --- Tabs for different sections ---
    tab_signal, tab_order, tab_positions, tab_holdings, tab_orders, tab_log = st.tabs([
        "📡 Live Signal", "🛒 Place Order", "📊 Positions",
        "🏦 Holdings", "📋 Order Book", "📜 Trade Log",
    ])

    # ===========================
    # TAB: Live Signal
    # ===========================
    with tab_signal:
        st.subheader(f"Strategy Signal: **{live_strategy_label}** on **{live_symbol}** ({exchange})")

        col_ltp, col_signal = st.columns([1, 1])

        # Fetch current LTP
        try:
            current_ltp = mgr.get_ltp(exchange, live_symbol)
        except Exception:
            current_ltp = 0.0

        with col_ltp:
            st.metric("Last Traded Price", f"Rs.{current_ltp:,.2f}" if current_ltp else "N/A")

        # Compute live signal
        if st.button("🔄 Refresh Signal", type="primary", key="refresh_signal"):
            with st.spinner(f"Computing signal on {exchange}:{live_symbol}..."):
                signal_data = mgr.compute_live_signal(
                    exchange=exchange, symbol=live_symbol,
                    strategy_key=live_strategy_key, params=live_params,
                    interval=live_interval,
                )
                st.session_state["live_signal_data"] = signal_data

        signal_data = st.session_state.get("live_signal_data", {})
        if signal_data:
            sig = signal_data.get("signal", 0)
            sig_label = signal_data.get("signal_label", "HOLD")

            with col_signal:
                if sig == 1:
                    st.markdown('<div class="signal-buy">🟢 BUY SIGNAL</div>', unsafe_allow_html=True)
                elif sig == -1:
                    st.markdown('<div class="signal-sell">🔴 SELL SIGNAL</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="signal-hold">🟡 HOLD</div>', unsafe_allow_html=True)

            info_cols = st.columns(4)
            info_cols[0].metric("Strategy", signal_data.get("strategy_key", "").replace("_", " ").title())
            info_cols[1].metric("Data Points", signal_data.get("data_points", 0))
            info_cols[2].metric("Last Data", signal_data.get("timestamp", "N/A")[:16])
            if signal_data.get("indicator_value") is not None:
                info_cols[3].metric("Indicator Value", signal_data["indicator_value"])

            if signal_data.get("error"):
                st.error(f"Signal computation error: {signal_data['error']}")

            # Auto-execute
            if auto_trade and sig != 0:
                st.warning(f"Auto-trade enabled. Executing {sig_label} order for {live_quantity} qty...")
                result = mgr.auto_execute_signal(
                    exchange=exchange, symbol=live_symbol,
                    signal=sig, quantity=live_quantity,
                    product=live_product,
                )
                if result:
                    mgr.log_trade(sig_label, live_symbol, signal_data.get("ltp", 0),
                                  live_quantity, result)
                    if result.success:
                        st.success(f"Order placed! ID: {result.order_id}")
                    else:
                        st.error(f"Order failed: {result.message}")

            # Manual trade buttons
            st.markdown("---")
            st.markdown("#### Manual Trade")
            mcol1, mcol2 = st.columns(2)
            with mcol1:
                if st.button("🟢 BUY", type="primary", use_container_width=True, key="manual_buy"):
                    result = mgr.place_order(exchange, live_symbol, "BUY", live_quantity,
                                             product=live_product)
                    mgr.log_trade("BUY", live_symbol, current_ltp, live_quantity, result)
                    if result.success:
                        st.success(f"BUY order placed! ID: {result.order_id}")
                    else:
                        st.error(f"BUY failed: {result.message}")
            with mcol2:
                if st.button("🔴 SELL", type="secondary", use_container_width=True, key="manual_sell"):
                    result = mgr.place_order(exchange, live_symbol, "SELL", live_quantity,
                                             product=live_product)
                    mgr.log_trade("SELL", live_symbol, current_ltp, live_quantity, result)
                    if result.success:
                        st.success(f"SELL order placed! ID: {result.order_id}")
                    else:
                        st.error(f"SELL failed: {result.message}")

        # Live price chart
        if current_ltp:
            st.markdown("---")
            st.subheader(f"📈 Recent Price Data: {live_symbol}")
            try:
                hist_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                hist_to = datetime.now().strftime("%Y-%m-%d")
                hist_df = mgr.broker.get_historical(exchange, live_symbol, live_interval, hist_from, hist_to)
                if not hist_df.empty:
                    fig_live = go.Figure(data=[go.Candlestick(
                        x=hist_df.index, open=hist_df["Open"], high=hist_df["High"],
                        low=hist_df["Low"], close=hist_df["Close"], name=live_symbol,
                        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
                    )])
                    fig_live.update_layout(height=400, template="plotly_white",
                                           xaxis_rangeslider_visible=False,
                                           title=f"{exchange}:{live_symbol} ({live_interval})")
                    st.plotly_chart(fig_live, use_container_width=True)
            except Exception as e:
                st.caption(f"Could not load price chart: {e}")

    # ===========================
    # TAB: Place Order
    # ===========================
    with tab_order:
        st.subheader("Manual Order Placement")

        with st.form("order_form", clear_on_submit=True):
            ocol1, ocol2 = st.columns(2)
            with ocol1:
                o_exchange = st.selectbox("Exchange", ["NSE", "NFO", "BSE"], key="o_exchange")
                o_symbol = st.text_input("Symbol", value=live_symbol if mgr.connected else "", key="o_symbol")
                o_txn = st.selectbox("Transaction", ["BUY", "SELL"], key="o_txn")
            with ocol2:
                o_qty = st.number_input("Quantity", value=1, min_value=1, key="o_qty")
                o_type = st.selectbox("Order Type", ["MARKET", "LIMIT", "SL", "SL-M"], key="o_type")
                o_product = st.selectbox("Product", ["MIS", "CNC", "NRML"], key="o_product")

            o_price = 0.0
            o_trigger = 0.0
            if o_type in ("LIMIT", "SL"):
                o_price = st.number_input("Price (Rs.)", value=0.0, min_value=0.0, step=0.05, key="o_price")
            if o_type in ("SL", "SL-M"):
                o_trigger = st.number_input("Trigger Price (Rs.)", value=0.0, min_value=0.0, step=0.05, key="o_trigger")

            submitted = st.form_submit_button("📤 Place Order", type="primary", use_container_width=True)

            if submitted:
                if not mgr.connected:
                    st.error("Not connected to broker!")
                elif not o_symbol.strip():
                    st.error("Please enter a symbol!")
                else:
                    result = mgr.place_order(
                        exchange=o_exchange, symbol=o_symbol.upper().strip(),
                        transaction_type=o_txn, quantity=o_qty,
                        order_type=o_type, price=o_price,
                        trigger_price=o_trigger, product=o_product,
                    )
                    mgr.log_trade(o_txn, o_symbol, o_price, o_qty, result)
                    if result.success:
                        st.success(f"Order placed! ID: {result.order_id}")
                    else:
                        st.error(f"Order failed: {result.message}")

    # ===========================
    # TAB: Positions
    # ===========================
    with tab_positions:
        st.subheader("Open Positions")

        if st.button("🔄 Refresh Positions", key="refresh_pos"):
            mgr.refresh_positions()

        positions = mgr.get_positions()
        if positions:
            pos_data = []
            total_pnl = 0
            for p in positions:
                pnl = p.pnl
                if pnl == 0 and p.last_price > 0:
                    pnl = (p.last_price - p.average_price) * p.quantity
                total_pnl += pnl
                pos_data.append({
                    "Symbol": p.symbol,
                    "Exchange": p.exchange,
                    "Qty": p.quantity,
                    "Avg Price": f"Rs.{p.average_price:,.2f}",
                    "LTP": f"Rs.{p.last_price:,.2f}",
                    "P&L": f"Rs.{pnl:,.2f}",
                    "Product": p.product,
                    "_pnl_raw": pnl,
                })
            pos_df = pd.DataFrame(pos_data)
            st.metric("Total Unrealized P&L", f"Rs.{total_pnl:,.2f}",
                       delta=None)

            styled_pos = pos_df.drop(columns=["_pnl_raw"]).style.map(
                lambda x: "color: green;" if isinstance(x, str) and "Rs." in x and not x.startswith("Rs.-") and x != "Rs.0.00" else "",
            )
            st.dataframe(pos_df.drop(columns=["_pnl_raw"]), use_container_width=True)

            st.markdown("---")
            st.markdown("#### Exit Positions")
            exit_cols = st.columns([2, 1, 1, 1])
            with exit_cols[0]:
                exit_symbol = st.selectbox("Select position", [p.symbol for p in positions], key="exit_sym")
            with exit_cols[1]:
                pos_obj = next((p for p in positions if p.symbol == exit_symbol), None)
                exit_qty = st.number_input("Qty", value=abs(pos_obj.quantity) if pos_obj else 1,
                                           min_value=1, key="exit_qty")
            with exit_cols[2]:
                exit_txn = "SELL" if pos_obj and pos_obj.quantity > 0 else "BUY"
                st.write(f"Action: **{exit_txn}**")
            with exit_cols[3]:
                st.write("")
                if st.button("🚪 Exit", type="primary", key="exit_pos_btn"):
                    result = mgr.exit_position(
                        exchange=pos_obj.exchange if pos_obj else exchange,
                        symbol=exit_symbol, quantity=exit_qty,
                        transaction_type=exit_txn,
                        product=pos_obj.product if pos_obj else "MIS",
                    )
                    mgr.log_trade(exit_txn, exit_symbol, 0, exit_qty, result)
                    if result.success:
                        st.success(f"Exit order placed! ID: {result.order_id}")
                        mgr.refresh_positions()
                        st.rerun()
                    else:
                        st.error(f"Exit failed: {result.message}")

            st.markdown("---")
            if st.button("🚨 Exit ALL Positions", type="secondary", key="exit_all"):
                results = mgr.exit_all_positions()
                success_count = sum(1 for r in results if r.success)
                st.success(f"Exited {success_count}/{len(results)} positions")
                mgr.refresh_positions()
                st.rerun()
        else:
            st.info("No open positions.")

    # ===========================
    # TAB: Holdings
    # ===========================
    with tab_holdings:
        st.subheader("Delivery Holdings")
        if st.button("🔄 Refresh Holdings", key="refresh_hol"):
            pass
        holdings = mgr.get_holdings()
        if holdings:
            hol_data = []
            total_val = 0
            total_pnl = 0
            for h in holdings:
                val = h.last_price * h.quantity
                pnl = h.pnl if h.pnl else (h.last_price - h.average_price) * h.quantity
                total_val += val
                total_pnl += pnl
                hol_data.append({
                    "Symbol": h.symbol,
                    "Exchange": h.exchange,
                    "Qty": h.quantity,
                    "Avg Price": f"Rs.{h.average_price:,.2f}",
                    "LTP": f"Rs.{h.last_price:,.2f}",
                    "Value": f"Rs.{val:,.2f}",
                    "P&L": f"Rs.{pnl:,.2f}",
                    "Product": h.product,
                })
            hol_cols = st.columns(3)
            hol_cols[0].metric("Total Holdings Value", f"Rs.{total_val:,.2f}")
            hol_cols[1].metric("Total P&L", f"Rs.{total_pnl:,.2f}")
            hol_cols[2].metric("Holdings Count", str(len(holdings)))
            st.dataframe(pd.DataFrame(hol_data), use_container_width=True)
        else:
            st.info("No delivery holdings.")

    # ===========================
    # TAB: Order Book
    # ===========================
    with tab_orders:
        st.subheader("Today's Orders")
        if st.button("🔄 Refresh Orders", key="refresh_orders"):
            mgr.refresh_orders()

        orders = mgr.get_orders()
        if orders:
            order_df = pd.DataFrame(orders)
            st.dataframe(order_df, use_container_width=True)
        else:
            st.info("No orders today.")

        st.markdown("---")
        st.subheader("Trades")
        trades = mgr.get_trades()
        if trades:
            trades_df = pd.DataFrame(trades)
            st.dataframe(trades_df, use_container_width=True)
        else:
            st.info("No trades today.")

    # ===========================
    # TAB: Trade Log
    # ===========================
    with tab_log:
        st.subheader("Session Trade Log")
        log = st.session_state.get("trade_log", [])
        if log:
            log_df = pd.DataFrame(log)
            styled_log = log_df.copy()
            st.dataframe(log_df, use_container_width=True)
        else:
            st.info("No trades executed in this session.")
        if st.button("🗑️ Clear Log", key="clear_log"):
            st.session_state.trade_log = []
            st.rerun()

    st.divider()
    st.caption("⚠️ Live trading involves real money. Trade responsibly. This tool is for educational purposes.")
