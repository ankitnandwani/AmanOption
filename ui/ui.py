import os
import threading
import traceback
from queue import Queue
from threading import Thread

from nicegui import ui

from models.config import UPSTOX_ACCESS_TOKEN
from backtest.bootstrap import start_live
from backtest.backtest import start_backtest
from models.models import StrategyConfig

strategy = None
websocket = None
result_queue = Queue()


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

    print("Dashboard snapshot:", snapshot["realized_pnl"], snapshot["total_pnl"])

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

    if mode.value == "live" and strategy is not None:
        ui.notify("Strategy already running")
        return

    token = access_token.value.strip()

    if not token:
        token = UPSTOX_ACCESS_TOKEN

    config = StrategyConfig(
        access_token=token,
        underlying_key=underlying.value,
        lots=int(lots.value),
        target_premium=float(target.value),
        sl_pct=float(sl.value) / 100,
        max_loss=float(max_loss.value),
    )

    run_button.disable()

    loading_dialog.open()

    if mode.value == "live":
        strategy, websocket = start_live(config)
    else:
        Thread(
            target=run_backtest_worker,
            args=(
                config,
                backtest_date.value,
            ),
            daemon=True,
        ).start()

        return

    strategy.events.subscribe(handle_event)

    refresh_dashboard()

    run_button.enable()

    if mode.value == "backtest":
        strategy = None
        websocket = None

    ui.notify("Strategy Started")

def run_backtest_worker(config, replay_date):

    try:

        strategy, historical  = start_backtest(
            config=config,
            replay_date=replay_date,
        )

        result_queue.put(
            (
                "success",
                (
                    strategy,
                    historical,
                ),
            )
        )

    except Exception as e:
        traceback.print_exc()
        result_queue.put(
            ("error", e)
        )

def check_backtest_finished():
    global strategy
    global websocket

    if result_queue.empty():
        return


    status, value = result_queue.get()

    loading_dialog.close()

    run_button.enable()

    if status == "error":

        ui.notify(
            str(value),
            type="negative",
        )

        return

    strategy, historical = value
    websocket = None
    strategy.events.subscribe(handle_event)

    refresh_dashboard()

    strategy.bootstrap_and_replay(historical)

    ui.notify(
        "Backtest Completed",
        type="positive",
    )

    strategy = None
    websocket = None


ui.colors(
    primary="#2563eb",
)

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

        run_button = ui.button(
            "▶ Run",
            on_click=start,
        ).props("color=positive")

        ui.button(
            "■ Stop",
        ).props("color=negative")


# -----------------------------
# Main Page
# -----------------------------
with ui.dialog().props("persistent") as loading_dialog:

    with ui.card().classes(
        "items-center p-8"
    ):

        ui.spinner(
            size="4rem"
        )

        ui.label(
            "Running Backtest..."
        ).classes(
            "text-xl font-bold mt-4"
        )

        ui.label(
            "Downloading historical data.\nPlease wait..."
        ).classes(
            "text-gray-500 text-center"
        )


with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):

    ui.label("📈 Options Trading Bot").classes(
        "text-3xl font-bold"
    )

    mode = ui.radio(
        {
            "live": "Live",
            "backtest": "Backtest",
        },
        value="live",
    ).props("inline")

    backtest_date = ui.input(
        label="Backtest Date",
        value="2026-07-14",
    )

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

ui.timer(
    0.25,
    check_backtest_finished,
)

ui.run(
    title="Options Trading Bot",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    favicon="📈",
)