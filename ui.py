from nicegui import ui

from bootstrap import start_strategy
from models import StrategyConfig

strategy = None
websocket = None


# -----------------------------
# Event handlers
# -----------------------------

def handle_event(event):
    if event["type"] == "log":
        append_log(event["data"])

    elif event["type"] == "state_changed":
        refresh_dashboard()


def refresh_dashboard():
    snapshot = strategy.get_snapshot()

    status_badge.set_text("Connected")
    status_badge.props("color=positive")

    mode_label.set_text(snapshot["mode"])
    active_label.set_text(snapshot["active_side"])

    realized_label.set_text(f"₹{snapshot['realized_pnl']:.2f}")
    total_label.set_text(f"₹{snapshot['total_pnl']:.2f}")

    update_position(snapshot["ce"], ce_widgets)
    update_position(snapshot["pe"], pe_widgets)


def update_position(position, widgets):
    if not position:
        widgets["strike"].set_text("-")
        widgets["entry"].set_text("-")
        widgets["ltp"].set_text("-")
        widgets["sl"].set_text("-")
        widgets["pnl"].set_text("-")
        return

    widgets["strike"].set_text(str(position["strike"]))
    widgets["entry"].set_text(f"₹{position['entry']:.2f}")
    widgets["ltp"].set_text(f"₹{position['ltp']:.2f}")
    widgets["sl"].set_text(f"₹{position['sl']:.2f}")

    pnl = position["pnl"]
    widgets["pnl"].set_text(f"₹{pnl:.2f}")

    if pnl >= 0:
        widgets["pnl"].classes(remove="text-red")
        widgets["pnl"].classes(add="text-green")
    else:
        widgets["pnl"].classes(remove="text-green")
        widgets["pnl"].classes(add="text-red")


def append_log(log):
    icon = "🟢" if log.level == "INFO" else "🔴"

    log_area.push(
        f"{icon} [{log.timestamp.strftime('%H:%M:%S')}] {log.message}"
    )


# -----------------------------
# Start Strategy
# -----------------------------

def start():
    global strategy, websocket

    if strategy is not None:
        ui.notify("Strategy already running")
        return

    config = StrategyConfig(
        access_token=access_token.value,
        underlying_key=underlying.value,
        lots=int(lots.value),
        target_premium=float(target.value),
        sl_pct=float(sl.value) / 100,
        max_loss=float(max_loss.value),
    )

    strategy, websocket = start_strategy(config)

    strategy.events.subscribe(handle_event)

    ui.notify("Strategy Started")


# -----------------------------
# Sidebar
# -----------------------------

with ui.left_drawer(value=True).classes("bg-grey-1 p-4"):

    ui.label("⚙ Configuration").classes("text-h6")

    access_token = ui.input(
        "Access Token",
        password=True,
        password_toggle_button=True,
    )

    underlying = ui.select(
        ["NSE_INDEX|Nifty 50"],
        value="NSE_INDEX|Nifty 50",
        label="Underlying",
    )

    lots = ui.number("Lots", value=1)

    target = ui.number("Target Premium", value=35)

    sl = ui.number("SL %", value=20)

    max_loss = ui.number("Max Loss", value=3000)

    ui.separator()

    with ui.row():

        ui.button(
            "▶ Run",
            on_click=start,
        ).props("color=positive")

        ui.button(
            "■ Stop",
        ).props("color=negative")


# -----------------------------
# Main Page
# -----------------------------

with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):

    ui.label("📈 Options Trading Bot").classes(
        "text-3xl font-bold"
    )

    ui.label(
        "Event-driven Options Selling Dashboard"
    ).classes("text-grey")

    status_badge = ui.badge(
        "Disconnected"
    ).props("color=negative")

    # Metrics

    with ui.row().classes("gap-4"):

        with ui.card().classes("items-center w-40"):
            ui.label("Mode")
            mode_label = ui.label("-").classes("text-h5")

        with ui.card().classes("items-center w-40"):
            ui.label("Active")
            active_label = ui.label("-").classes("text-h5")

        with ui.card().classes("items-center w-48"):
            ui.label("Realized")
            realized_label = ui.label("₹0").classes("text-h5")

        with ui.card().classes("items-center w-48"):
            ui.label("Total")
            total_label = ui.label("₹0").classes("text-h5")

    # Positions

    with ui.row().classes("w-full gap-4 items-stretch"):

        ce_widgets = {}

        with ui.card().classes("flex-1"):
            ui.label("CE Position").classes("text-h6")
            with ui.grid(columns=2).classes("gap-x-6 gap-y-2"):
                ui.label("Strike")
                ce_widgets["strike"] = ui.label("-")

                ui.label("Entry")
                ce_widgets["entry"] = ui.label("-")

                ui.label("LTP")
                ce_widgets["ltp"] = ui.label("-")

                ui.label("SL")
                ce_widgets["sl"] = ui.label("-")

                ui.label("PnL")
                ce_widgets["pnl"] = ui.label("-").classes("font-bold")

            # ce_widgets["strike"] = ui.label("-")
            # ce_widgets["entry"] = ui.label("-")
            # ce_widgets["ltp"] = ui.label("-")
            # ce_widgets["sl"] = ui.label("-")
            # ce_widgets["pnl"] = ui.label("-").classes("font-bold text-lg")

        pe_widgets = {}

        with ui.card().classes("flex-1"):
            ui.label("PE Position").classes("text-h6")

            with ui.grid(columns=2).classes("gap-x-6 gap-y-2"):
                ui.label("Strike")
                pe_widgets["strike"] = ui.label("-")

                ui.label("Entry")
                pe_widgets["entry"] = ui.label("-")

                ui.label("LTP")
                pe_widgets["ltp"] = ui.label("-")

                ui.label("SL")
                pe_widgets["sl"] = ui.label("-")

                ui.label("PnL")
                pe_widgets["pnl"] = ui.label("-").classes("font-bold")

    ui.separator()

    ui.label("Logs").classes("text-h6")

    log_area = ui.log(max_lines=500).classes("w-full h-80")


ui.run(
    title="Options Trading Bot"
)