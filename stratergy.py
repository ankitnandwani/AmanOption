import time
from datetime import datetime
from datetime import time as dt_time

import requests
from models import StrategyState, Position, Mode, MarketData
from utils import get_ltp, calculate_position_pnl

BASE_URL = "https://api.upstox.com/v2"
ACCESS_TOKEN = ""
HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}


def get_option_contracts(instrument_key):
    url = f"{BASE_URL}/option/contract"
    params = {
        "instrument_key": instrument_key
    }

    response = requests.get(
        url=url,
        params=params,
        headers=HEADERS
    )

    response.raise_for_status()
    return response.json()


def enrich_with_ltp(market_data, option_chain_data):
    for item in option_chain_data["data"]:
        strike = item["strike_price"]

        if strike not in market_data.contracts_by_strike:
            continue

        # CE
        call = item.get("call_options")
        if call:
            ce_ltp = call.get("market_data", {}).get("ltp")
            market_data.contracts_by_strike[strike]["CE"]["ltp"] = ce_ltp

        # PE
        put = item.get("put_options")
        if put:
            pe_ltp = put.get("market_data", {}).get("ltp")
            market_data.contracts_by_strike[strike]["PE"]["ltp"] = pe_ltp


def get_option_chain(instrument_key, expiry_date):
    url = f"{BASE_URL}/option/chain"

    params = {
        "instrument_key": instrument_key,
        "expiry_date": expiry_date
    }

    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()

    return res.json()


def find_nearest_option(market_data, option_type, target=35):
    if option_type not in ["CE", "PE"]:
        raise ValueError("option_type must be CE or PE")

    best = None
    best_diff = float("inf")
    best_strike = None

    for strike, data in market_data.contracts_by_strike.items():
        option = data.get(option_type)
        if not option:
            continue

        ltp = option.get("ltp")

        # 🔥 IMPORTANT: skip invalid LTP
        if ltp is None or ltp <= 0:
            continue

        diff = abs(ltp - target)

        if diff < best_diff:
            best_diff = diff
            best = option
            best_strike = strike

        if best:
            best["strike_price"] = best_strike

    return best


def create_position(contract, num_lots, sl_pct):
    entry_price = contract["ltp"]
    return Position(
        instrument_key=contract["instrument_key"],
        option_type=contract["instrument_type"],
        strike_price=contract["strike_price"],
        entry_price=entry_price,
        lot_size=contract["lot_size"],
        num_lots=num_lots,
        sl_pct=sl_pct,
        sl_price=entry_price * (1 + sl_pct),
        entry_time=datetime.now()
    )


def square_off(state, market_data):
    if state.ce_position:
        ce_ltp = get_ltp(state.ce_position, market_data)
        state.realized_pnl += calculate_position_pnl(state.ce_position, ce_ltp)

    if state.pe_position:
        pe_ltp = get_ltp(state.pe_position, market_data)
        state.realized_pnl += calculate_position_pnl(state.pe_position, pe_ltp)

    state.ce_position = None
    state.pe_position = None
    state.active_side = "NONE"


def is_sl_hit(position, current_ltp):
    if position is None:
        return False

    return current_ltp >= position.sl_price


def check_hedged_sl(state, market_data):
    ce_ltp = get_ltp(state.ce_position, market_data)
    pe_ltp = get_ltp(state.pe_position, market_data)

    ce_sl_hit = is_sl_hit(state.ce_position, ce_ltp)
    pe_sl_hit = is_sl_hit(state.pe_position, pe_ltp)

    if ce_sl_hit:
        print("CE SL HIT")
        square_off(state, market_data)
        new_pe_contract = find_nearest_option(market_data, "PE", 35)
        new_pe_position = create_position(new_pe_contract, num_lots=1, sl_pct=0.25)
        state.enter_directional(new_pe_position)
    elif pe_sl_hit:
        print("PE SL HIT")
        square_off(state, market_data)
        new_ce_contract = find_nearest_option(market_data, "CE", 35)
        new_ce_position = create_position(new_ce_contract, num_lots=1, sl_pct=0.25)
        state.enter_directional(new_ce_position)


def check_directional_sl(state, market_data):
    if state.active_side == "CE":
        pos = state.ce_position
    else:
        pos = state.pe_position

    current_ltp = get_ltp(pos, market_data)

    if is_sl_hit(pos, current_ltp):
        print("Directional SL HIT")
        square_off(state, market_data)

        ce_contract = find_nearest_option(market_data, "CE", 35)
        pe_contract = find_nearest_option(market_data, "PE", 35)

        ce_position = create_position(ce_contract, num_lots=1, sl_pct=0.20)
        pe_position = create_position(pe_contract, num_lots=1, sl_pct=0.20)

        state.enter_hedged(ce_position, pe_position)


def calculate_total_pnl(state):
    total = state.realized_pnl

    if state.ce_position:
        total += state.ce_position.pnl

    if state.pe_position:
        total += state.pe_position.pnl

    return total


def is_max_loss_hit(state, max_loss=3000):
    total_pnl = calculate_total_pnl(state)
    return total_pnl <= -max_loss


def update_live_pnl(state, market_data):
    if state.ce_position:
        ce_ltp = get_ltp(state.ce_position, market_data)
        calculate_position_pnl(state.ce_position, ce_ltp)

    if state.pe_position:
        pe_ltp = get_ltp(state.pe_position, market_data)
        calculate_position_pnl(state.pe_position, pe_ltp)


def print_state(state, market_data):
    print()
    print("=" * 50)
    print("MODE :", state.mode.value)
    print("ACTIVE :", state.active_side)
    print("REALIZED :", round(state.realized_pnl, 2))

    if state.ce_position:
        print()
        print("CE")
        print(state.ce_position.instrument_key)
        print("Strike :", state.ce_position.strike_price)
        print("Entry :", state.ce_position.entry_price)
        print("SL :", state.ce_position.sl_price)
        print("ltp :", get_ltp(state.ce_position, market_data))
        print("PnL :", round(state.ce_position.pnl, 2))

    if state.pe_position:
        print()
        print("PE")
        print(state.pe_position.instrument_key)
        print("Strike :", state.pe_position.strike_price)
        print("Entry :", state.pe_position.entry_price)
        print("SL :", state.pe_position.sl_price)
        print("ltp :", get_ltp(state.pe_position, market_data))
        print("PnL :", round(state.pe_position.pnl, 2))

    print()
    print("TOTAL :", round(calculate_total_pnl(state), 2))
    print("=" * 50)


def run_strategy(state, market_data):
    update_live_pnl(state, market_data)

    if is_max_loss_hit(state, 3000):
        print()
        print("MAX LOSS HIT")
        square_off(state, market_data)
        return False

    if state.mode == Mode.HEDGED:
        check_hedged_sl(state, market_data)

    elif state.mode == Mode.DIRECTIONAL:
        check_directional_sl(state, market_data)

    return True


def initialize_state(state, market_data):
    ce_contract = find_nearest_option(market_data, "CE", 35)
    pe_contract = find_nearest_option(market_data, "PE", 35)

    if ce_contract is None or pe_contract is None:
        raise Exception("No valid CE/PE found at startup")

    ce_position = create_position(ce_contract, num_lots=1, sl_pct=0.20)
    pe_position = create_position(pe_contract, num_lots=1, sl_pct=0.20)
    state.enter_hedged(ce_position, pe_position)


def run_day(state, market_data, instrument_key, expiry):
    initialized = False

    while True:
        option_chain = get_option_chain(instrument_key, expiry)
        enrich_with_ltp(market_data, option_chain)

        # STEP 1: INITIALIZE ONLY ONCE
        if not initialized:
            initialize_state(state, market_data)
            initialized = True
            print("INITIALIZED HEDGED POSITIONS")

        # STEP 2: RUN STRATEGY
        should_continue = run_strategy(state, market_data)
        print_state(state)

        # STEP 3: EXIT CONDITIONS
        if not should_continue:
            print("STOPPING STRATEGY")
            break

        current_time = datetime.now().time()
        if current_time >= dt_time(15, 15):
            print("DAY END EXIT")
            square_off(state, market_data)
            break

        time.sleep(1)


def main():
    contracts = get_option_contracts("NSE_INDEX|Nifty 50")

    expiries = sorted(
        set(
            c["expiry"]
            for c in contracts["data"]
        )
    )

    nearest_expiry = expiries[0]

    current_expiry_contracts = [
        c for c in contracts["data"]
        if c["expiry"] == nearest_expiry
    ]

    current_expiry_contracts.sort(
        key=lambda x: (
            x["strike_price"],
            x["instrument_type"]
        )
    )

    market_data = MarketData()

    for c in current_expiry_contracts:
        strike = c["strike_price"]
        option_type = c["instrument_type"]

        market_data.contracts_by_strike.setdefault(strike, {})
        market_data.contracts_by_strike[strike][option_type] = c
        market_data.contracts_by_instrument_key[
            c["instrument_key"]
        ] = c

    state = StrategyState(
        mode=Mode.HEDGED,
        ce_position=None,
        pe_position=None,
        active_side="NONE",
        realized_pnl=0
    )

    run_day(state, market_data, "NSE_INDEX|Nifty 50", nearest_expiry)


if __name__ == "__main__":
    main()
