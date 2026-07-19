from backtest.historical_market_data import load_historical_market_data
from utils import build_market_data
from models.models import Mode, StrategyConfig, StrategyState
from strategy import Strategy
from services.upstox_service import get_option_contracts


def start_backtest(
    config: StrategyConfig,
    replay_date: str,
):

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


def get_replay_expiry(replay_date, expiries):
    for expiry in sorted(expiries):
        if expiry >= replay_date:
            return expiry

    raise Exception("No valid expiry found")

