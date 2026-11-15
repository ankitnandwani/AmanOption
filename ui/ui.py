import os
import threading
import traceback
import json
from datetime import date
from queue import Queue
from threading import Thread
from pathlib import Path


from nicegui import run, ui

from backtest.backtester import Backtester
from models.config import UPSTOX_ACCESS_TOKEN
from backtest.bootstrap import start_live
from backtest.backtest import start_backtest
from models.models import StrategyConfig
from services.backtest_report_service import (
    InvalidReport,
    ReportUnavailable,
    cloud_history_enabled,
    list_report_page,
    new_job_id,
    read_report,
    save_completed_report,
)

strategy = None
websocket = None
result_queue = Queue()
multi_result_queue = Queue()

RESULTS_DIR = Path("backtest_results")
RESULTS_DIR.mkdir(exist_ok=True)

def set_job_status(job_id, status):
    with open(RESULTS_DIR / f"{job_id}.status", "w") as f:
        f.write(status)

def load_backtest_results():
    results = []
    for file in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
        job_id = file.stem
        status_file = RESULTS_DIR / f"{job_id}.status"
        status = "unknown"
        if status_file.exists():
            status = status_file.read_text().strip()

        with open(file, "r") as f:
            data = json.load(f)
            results.append({"job_id": job_id, "data": data, "status": status})
    return results

def dict_to_backtest_result(data):
    from models.backtest_result import DayResult, BacktestResult
    days = [DayResult(day["date"], day["pnl"]) for day in data["days"]]
    return BacktestResult(days=days)

# -----------------------------
# Event handlers
# -----------------------------
def handle_event(event):
    try:
        if event["type"] == "log":
            append_log(event["data"])

        elif event["type"] == "state_changed":
            refresh_dashboard()
    except Exception:
        # Ignore errors if the UI client is gone or unavailable
        pass


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
    elif mode.value == "singleDayBacktest":
        Thread(
            target=run_backtest_worker,
            args=(
                config,
                backtest_date.value,
            ),
            daemon=True,
        ).start()
        return
    elif mode.value == "multiDayBacktest":
        job_id = new_job_id()
        Thread(
            target=run_multiday_worker,
            args=(
                config,
                start_date.value,
                end_date.value,
                job_id,
            ),
            daemon=True,
        ).start()
        ui.notify(f"Backtest started in background!\nJob ID: {job_id}\nYou can close this tab and check History later.", type="info")
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

    snapshot = strategy.run_backtest(historical)

    ui.notify(
        "Backtest Completed",
        type="positive",
    )

    strategy = None
    websocket = None


def run_multiday_worker(
        config,
        start_date,
        end_date,
        job_id,
):
    set_job_status(job_id, "running")
    try:

        backtester = Backtester()
        backtester.events.subscribe(handle_event)
        result = backtester.run_date_range(
            config=config,
            start_date=start_date,
            end_date=end_date,
        )

        cloud_saved = save_completed_report(RESULTS_DIR, job_id, result, start_date, end_date)
        set_job_status(job_id, "completed")
        multi_result_queue.put(
            ("success", (result, cloud_saved))
        )

    except Exception as e:
        traceback.print_exc()
        set_job_status(job_id, f"failed: {e}")
        multi_result_queue.put(
            ("error", e)
        )


def check_multiday_finished():
    if multi_result_queue.empty():
        return

    status, value = multi_result_queue.get()

    loading_dialog.close()

    run_button.enable()

    if status == "error":
        ui.notify(
            str(value),
            type="negative",
        )

        return

    ui.notify(
        "Multi-day backtest completed",
        type="positive",
    )

    result, cloud_saved = value
    render_multiday_results(result)
    if cloud_saved is False:
        ui.notify("The report was saved locally. Cloud history is unavailable for this run.", type="warning")

def update_mode():
    replay_container.set_visibility(
        mode.value == "singleDayBacktest"
    )

    multi_container.set_visibility(
        mode.value == "multiDayBacktest"
    )

    dashboard_container.set_visibility(
        mode.value != "multiDayBacktest"
    )


def render_multiday_results(result):
    multi_results_container.clear()
    multi_results_container.set_visibility(True)
    with (((((multi_results_container))))):
        ui.label(
            "📊 Multi-Day Backtest Summary"
        ).classes("text-h5")

        with ui.row().classes("gap-6"):

            ui.label(f"Days : {result.total_days}")

            ui.label(
                f"Winning : {result.profitable_days}"
            )

            ui.label(
                f"Losing : {result.losing_days}"
            )

            ui.label(
                f"Win Rate : {result.win_rate:.1f}%"
            )

        with ui.row().classes("gap-6"):
            ui.label(
                f"Total PnL : ₹{result.total_pnl:.2f}"
            )

            ui.label(
                f"Average : ₹{result.average_pnl:.2f}"
            )

            if result.days:
                ui.label(f"Best : ₹{result.best_day.pnl:.2f}")
                ui.label(f"Worst : ₹{result.worst_day.pnl:.2f}")

        ui.separator()

        rows = []

        for day in result.days:
            rows.append(
                {
                    "date": day.date,
                    "pnl": round(day.pnl, 2),
                    "color": (
                        "positive"
                        if day.pnl > 0
                        else "negative"
                        if day.pnl < 0
                        else ""
                    ),
                }
            )

        columns = [
            {
                "name": "date",
                "label": "Date",
                "field": "date",
            },
            {
                "name": "pnl",
                "label": "PnL",
                "field": "pnl",
            },
        ]

        table = ui.table(
            columns=columns,
            rows=rows,
            row_key="date",
        ).props("dense flat bordered").classes("w-96")

        table.add_slot(
            "body-cell-pnl",
            r'''
            <q-td :props="props">
                <span
                    :class="props.row.pnl >= 0 ? 'text-positive' : 'text-negative'">
                    {{ props.row.pnl.toFixed(2) }}
                </span>
            </q-td>
            '''
        )


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
            "singleDayBacktest": "Single Day Backtest",
            "multiDayBacktest": "Multi Day Backtest",
        },
        value="live",
    ).props("inline")

    replay_container = ui.column()

    with replay_container:
        backtest_date = ui.input(
            "Replay Date",
            value=date.today().isoformat(),
            placeholder="YYYY-MM-DD",
        ).props("outlined")

    multi_container = ui.column()

    with multi_container:
        with ui.row().classes("w-full gap-6"):
            start_date = ui.input(
                "Start Date",
                value=date.today().replace(day=1).isoformat(),
            ).props("outlined").classes("flex-1")

            end_date = ui.input(
                "End Date",
                value=date.today().isoformat(),
            ).props("outlined").classes("flex-1")
        if cloud_history_enabled():
            ui.label("Completed reports saved to shared history are visible to other visitors.")

    status_badge = ui.badge(
        "Disconnected"
    ).props("color=negative")

    # Metrics
    dashboard_container = ui.row().classes("w-full gap-4 items-stretch")
    with dashboard_container:

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

    mode.on_value_change(
        lambda _: update_mode()
    )

    update_mode()

ui.separator()
history_container = ui.column().classes("w-full")
history_container.set_visibility(False)

async def show_cloud_history():
    ui.label("Shared Backtest History").classes("text-h5")
    entries_container = ui.column().classes("w-full")
    page_controls = ui.row()
    selection = ui.row()
    has_entries = False

    async def open_report(key):
        selection.clear()
        with selection:
            message = ui.label("Loading report…")
        try:
            result = await run.io_bound(read_report, key)
        except ReportUnavailable:
            error = "This report is no longer available."
        except InvalidReport:
            error = "This report is invalid and could not be displayed."
        except Exception:
            error = "Could not load the report. Select View to retry."
        else:
            if result is not None and not message.is_deleted:
                message.delete()
                render_multiday_results(result)
            return
        if not message.is_deleted:
            message.set_text(error)

    def view_handler(key):
        async def view():
            await open_report(key)
        return view

    async def load_page(token=None):
        nonlocal has_entries
        page_controls.clear()
        with page_controls:
            ui.label("Loading history…")
        try:
            page = await run.io_bound(list_report_page, token)
        except Exception:
            if not page_controls.is_deleted:
                page_controls.clear()
                with page_controls:
                    ui.label("Cloud history is unavailable.")

                    async def retry():
                        await load_page(token)

                    ui.button("Retry", on_click=retry)
            return
        if page is None or page_controls.is_deleted:
            return
        entries, next_token = page
        with entries_container:
            for key, job_id, completed_at in entries:
                with ui.row().classes("items-center"):
                    ui.label(f"{completed_at:%Y-%m-%d %H:%M:%S} UTC")
                    ui.label(job_id)
                    ui.button("View", on_click=view_handler(key)).props("flat")
        has_entries = has_entries or bool(entries)
        page_controls.clear()
        with page_controls:
            if next_token:
                async def load_more():
                    await load_page(next_token)

                ui.button("Load more", on_click=load_more)
            elif not has_entries:
                ui.label("No previous results found.")

    await load_page()


async def show_history():
    history_container.set_visibility(not history_container.visible)
    history_container.clear()
    if history_container.visible:
        with history_container:
            if cloud_history_enabled():
                await show_cloud_history()
                return
            ui.label("📜 Backtest History").classes("text-h5")
            results = load_backtest_results()
            if not results:
                ui.label("No previous results found.")
                return

            for res in results:
                with ui.card().classes("w-full mb-4"):
                    with ui.row().classes("items-center justify-between w-full"):
                            status_color = "positive" if res['status'] == "completed" else "negative" if "failed" in res['status'] else "orange"
                            ui.label(f"Job: {res['job_id']}").classes("font-bold")
                            ui.badge(res['status']).props(f"color={status_color}")
                            ui.button("View", on_click=lambda r=res: render_multiday_results(dict_to_backtest_result(r['data']))).props("flat")

ui.button("🕒 View History", on_click=show_history).props("outline")

ui.separator()
multi_results_container = ui.column().classes("w-full")
multi_results_container.set_visibility(False)

ui.separator()
ui.label("Logs").classes("text-h6")
log_area = ui.log(max_lines=500).classes("w-full h-80")

ui.timer(
    0.25,
    check_backtest_finished,
)

ui.timer(
    0.25,
    check_multiday_finished,
)

ui.run(
    title="Options Trading Bot",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    favicon="📈",
)
