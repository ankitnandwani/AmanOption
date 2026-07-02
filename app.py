import streamlit as st
from streamlit_autorefresh import st_autorefresh

from bootstrap import start_strategy
from models import StrategyConfig

st.set_page_config(
    page_title="Options Trading Bot",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Options Trading Bot")
st_autorefresh(interval=1000, key="dashboard_refresh")

# -------------------------
# Sidebar
# -------------------------

st.sidebar.header("Configuration")

access_token = st.sidebar.text_input(
    "Access Token",
    type="password"
)

underlying = st.sidebar.selectbox(
    "Underlying",
    [
        "NSE_INDEX|Nifty 50"
    ]
)

lots = st.sidebar.number_input("Lots", min_value=1, value=1)
target_premium = st.sidebar.number_input("Target Premium", min_value=1, value=35)
sl_percent = st.sidebar.number_input("SL %", min_value=1, max_value=100, value=20)
max_loss = st.sidebar.number_input("Max Loss", min_value=100, value=3000, step=100)

col1, col2 = st.sidebar.columns(2)

with col1:
    run_clicked = st.button(
        "▶ Run",
        use_container_width=True
    )

if run_clicked:
    if "strategy" not in st.session_state:
        config = StrategyConfig(
            access_token=access_token,
            underlying_key=underlying,
            lots=lots,
            target_premium=target_premium,
            sl_pct=sl_percent / 100,
            max_loss=max_loss
        )
        strategy, websocket = start_strategy(config)

        st.session_state.config = config
        st.session_state.strategy = strategy
        st.session_state.websocket = websocket
        st.success("Strategy started.")
    else:
        st.warning("Strategy is already running.")

with col2:
    stop_clicked = st.button(
        "■ Stop",
        use_container_width=True
    )

# -------------------------
# Dashboard
# -------------------------

metric1, metric2, metric3, metric4 = st.columns(4)

if "strategy" in st.session_state:

    snapshot = st.session_state.strategy.get_snapshot()

    metric1.metric("Mode", snapshot["mode"])
    metric2.metric("Active Side", snapshot["active_side"])
    metric3.metric("Realized PnL", f"₹{snapshot['realized_pnl']:.2f}")
    metric4.metric("Total PnL", f"₹{snapshot['total_pnl']:.2f}")

else:
    metric1.metric("Mode", "-")
    metric2.metric("Active Side", "-")
    metric3.metric("Realized PnL", "₹0")
    metric4.metric("Total PnL", "₹0")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("CE Position")
    if "strategy" in st.session_state:
        ce = snapshot["ce"]
        if ce:
            st.json(ce)
        else:
            st.info("No CE Position")

with col2:
    st.subheader("PE Position")
    if "strategy" in st.session_state:
        pe = snapshot["pe"]
        if pe:
            st.json(pe)
        else:
            st.info("No PE Position")

st.divider()

st.subheader("Logs")

log_placeholder = st.empty()

if "strategy" in st.session_state:

    logs = st.session_state.strategy.events.get_logs()

    text = "\n".join(
        f"[{log.timestamp.strftime('%H:%M:%S')}] "
        f"{log.level:<5} "
        f"{log.message}"
        for log in logs
    )

    log_placeholder.code(
        text or "No logs yet",
        language="text"
    )

else:
    log_placeholder.code(
        "Waiting for strategy...",
        language="text"
    )