from nicegui import ui

from models import StrategyConfig
from bootstrap import start_strategy

ui.label("📈 Options Trading Bot").classes("text-2xl font-bold")
strategy = None
websocket = None

def handle_event(event):

    if event["type"] == "log":
        append_log(event["data"])

    elif event["type"] == "state_changed":
        refresh_dashboard()


def refresh_dashboard():
    snapshot = strategy.get_snapshot()
    mode_label.set_text(f"Mode : {snapshot['mode']}")
    active_label.set_text(
        f"Active : {snapshot['active_side']}"
    )

    realized_label.set_text(
        f"Realized : ₹{snapshot['realized_pnl']:.2f}"
    )

    total_label.set_text(
        f"Total : ₹{snapshot['total_pnl']:.2f}"
    )

    if snapshot["ce"]:
        ce_json.run_editor_method(
            "updateProps",
            {
                "content": {
                    "json": snapshot["ce"]
                }
            }
        )

    if snapshot["pe"]:
        pe_json.run_editor_method(
            "updateProps",
            {
                "content": {
                    "json": snapshot["pe"]
                }
            }
        )

def append_log(log):

    log_area.push(
        f"[{log.timestamp.strftime('%H:%M:%S')}] "
        f"{log.level} "
        f"{log.message}"
    )

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
    ui.notify("Strategy started")

with ui.card():

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

    lots = ui.number(
        label="Lots",
        value=1,
    )

    target = ui.number(
        label="Target Premium",
        value=35,
    )

    sl = ui.number(
        label="SL %",
        value=20,
    )

    max_loss = ui.number(
        label="Max Loss",
        value=3000,
    )

    with ui.row():
        ui.button("Run", on_click=start)
        ui.button("Stop")


mode_label = ui.label("Mode : -")
active_label = ui.label("Active : -")
realized_label = ui.label("Realized : ₹0")
total_label = ui.label("Total : ₹0")

with ui.row():

    with ui.card():
        ui.label("CE Position")
        ce_json = ui.json_editor({"content": {"json": {}}})

    with ui.card():
        ui.label("PE Position")
        pe_json = ui.json_editor({"content": {"json": {}}})


ui.separator()

ui.label("Logs")

log_area = ui.log(max_lines=200)

ui.run()