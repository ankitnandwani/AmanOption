from models import StrategyState, Mode, StrategyConfig
from strategy import Strategy
from strategy_service import bootstrap_strategy
from upstox_service import get_option_contracts
from utils import build_market_data
from websocket_client import WebSocketClient

def start_strategy(config: StrategyConfig):
    print("Loading option contracts...")
    contracts = get_option_contracts(config.access_token, config.underlying_key)

    expiries = sorted(
        set(
            c["expiry"]
            for c in contracts["data"]
        )
    )

    nearest_expiry = expiries[0]
    market_data = build_market_data(contracts, nearest_expiry)

    state = StrategyState(
        mode=Mode.HEDGED,
        ce_position=None,
        pe_position=None,
        active_side="NONE",
        realized_pnl=0
    )

    state.lot_size = config.lots
    strategy = Strategy(state, market_data, config)
    instrument_keys = bootstrap_strategy(strategy, config.underlying_key, nearest_expiry)
    websocket = WebSocketClient(strategy, instrument_keys, config.access_token)
    websocket.connect()

    return strategy, websocket