from datetime import datetime, timedelta

from backtest.historical_market_data import load_historical_market_data
from backtest.replay_utils import get_replay_expiry
from models.backtest_result import DayResult, BacktestResult
from models.events import EventBus
from models.models import StrategyConfig, StrategyState, Mode
from services.upstox_service import get_option_contracts
from strategy import Strategy
from utils import build_market_data


class Backtester:

    def __init__(self):
        self.events = EventBus()

    def prepare_day(
        self,
        config: StrategyConfig,
        replay_date: str,
    ) -> Strategy:

        contracts = get_option_contracts(
            config.access_token,
            config.underlying_key,
        )

        expiries = sorted(
            {
                c["expiry"]
                for c in contracts["data"]
            }
        )

        replay_expiry = get_replay_expiry(
            replay_date,
            expiries,
        )

        contracts = get_option_contracts(
            config.access_token,
            config.underlying_key,
            expiry_date=replay_expiry,
        )

        market_data = build_market_data(
            contracts,
            replay_expiry,
        )

        state = StrategyState(
            mode=Mode.HEDGED,
            ce_position=None,
            pe_position=None,
            active_side="NONE",
            realized_pnl=0,
        )

        state.lot_size = config.lots

        strategy = Strategy(
            state,
            market_data,
            config,
        )

        strategy.events.info("Strategy initialized")
        strategy.events.info(f"Replay date: {replay_date}")
        strategy.events.info(f"Replay expiry: {replay_expiry}")

        historical = load_historical_market_data(
            access_token=config.access_token,
            contracts_by_instrument_key=market_data.contracts_by_instrument_key,
            from_date=replay_date,
            to_date=replay_date,
            events=strategy.events,
        )

        return strategy, historical

    def run_date_range(
            self,
            config,
            start_date: str,
            end_date: str,
    ):
        results = BacktestResult()

        current = datetime.strptime(
            start_date,
            "%Y-%m-%d",
        ).date()

        end = datetime.strptime(
            end_date,
            "%Y-%m-%d",
        ).date()

        while current <= end:

            replay_date = current.strftime("%Y-%m-%d")

            self.events.info(
                f"Running {replay_date}"
            )

            try:
                strategy, historical = self.prepare_day(
                    config,
                    replay_date,
                )
            except Exception as e:
                self.events.info(
                    f"Skipping {replay_date}: {e}"
                )
                current += timedelta(days=1)
                continue
            try:
                strategy.run_backtest(historical)
                snapshot = strategy.get_snapshot()
                results.days.append(
                    DayResult(
                        date=replay_date,
                        pnl=snapshot["total_pnl"],
                    )
                )

            except RuntimeError as e:
                self.events.error(
                    f"Skipping {replay_date}: {e}"
                )

            current += timedelta(days=1)

        return results