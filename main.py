from config import UNDERLYING_KEY
from models import StrategyState, Mode
from strategy_service import get_option_contracts, bootstrap_strategy, Strategy
from utils import build_market_data
from websocket_client import WebSocketClient


def main():
    print("Loading option contracts...")
    contracts = get_option_contracts(UNDERLYING_KEY)

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

    strategy = Strategy(state, market_data)

    # Step 4 - Bootstrap strategy (REST snapshot)
    instrument_keys = bootstrap_strategy(strategy, market_data, UNDERLYING_KEY, nearest_expiry)

    # Step 5 - Connect websocket
    websocket = WebSocketClient(strategy, instrument_keys)
    websocket.connect()

if __name__ == "__main__":
    main()