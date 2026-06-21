from datetime import datetime

import requests
from models import StrategyState, Position, Mode

BASE_URL = "https://api.upstox.com/v2"
ACCESS_TOKEN="eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiIyMzQ3MDEiLCJqdGkiOiI2YTM4MWZjMWJhNjdhYzBlYWM5YjM0NmIiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc4MjA2MzA0MSwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzgyMDc5MjAwfQ.FsSIZnxIIY_dOlCcZLLByfbkfwIWsnr18A7ARE4N7Jc"
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

def enrich_with_ltp(contracts_by_strike, option_chain_data):

    for item in option_chain_data["data"]:

        strike = item["strike_price"]

        if strike not in contracts_by_strike:
            continue

        # CE
        call = item.get("call_options")
        if call:

            ce_ltp = call.get("market_data", {}).get("ltp")

            if (
                    "CE" in contracts_by_strike[strike]
                    and ce_ltp is not None
            ):
                contracts_by_strike[strike]["CE"]["ltp"] = ce_ltp

        # PE
        put = item.get("put_options")
        if put:

            pe_ltp = put.get("market_data", {}).get("ltp")

            if (
                    "PE" in contracts_by_strike[strike]
                    and pe_ltp is not None
            ):
                contracts_by_strike[strike]["PE"]["ltp"] = pe_ltp

    return contracts_by_strike

def get_option_chain(instrument_key, expiry_date):

    url = f"{BASE_URL}/option/chain"

    params = {
        "instrument_key": instrument_key,
        "expiry_date": expiry_date
    }

    res = requests.get(url, headers=HEADERS, params=params)
    res.raise_for_status()

    return res.json()

def find_nearest_option(contracts_by_strike, option_type, target=35):
    if option_type not in ["CE", "PE"]:
        raise ValueError("option_type must be CE or PE")

    best = None
    best_diff = float("inf")
    best_strike = None

    for strike, data in contracts_by_strike.items():
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

def create_position(contract, option_type, lot_size, sl_pct):
    entry_price = contract["ltp"]
    return Position(
        instrument_key=contract["instrument_key"],
        option_type=option_type,
        strike_price=contract["strike_price"],
        entry_price=entry_price,
        lot_size=lot_size,
        sl_pct=sl_pct,
        sl_price=entry_price * (1 + sl_pct),
        entry_time=datetime.now()
    )

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

    contracts_by_strike = {}

    for c in current_expiry_contracts:
        strike = c["strike_price"]
        option_type = c["instrument_type"]

        contracts_by_strike.setdefault(strike, {})
        contracts_by_strike[strike][option_type] = c

    option_chain = get_option_chain("NSE_INDEX|Nifty 50", nearest_expiry)
    contracts_by_strike = enrich_with_ltp(
        contracts_by_strike,
        option_chain
    )

    ce_contract = find_nearest_option(contracts_by_strike, "CE", 35)
    pe_contract = find_nearest_option(contracts_by_strike, "PE", 35)

    ce_position = create_position(ce_contract,"CE", lot_size=75, sl_pct=0.20)
    pe_position = create_position(pe_contract,"PE", lot_size=75, sl_pct=0.20)

    state = StrategyState(
        mode=Mode.HEDGED,
        ce_position=ce_position,
        pe_position=pe_position,
        active_side="BOTH"
    )

    print()
    print("MODE :", state.mode.value)
    print()
    print("CE POSITION")
    print("Instrument :", state.ce_position.instrument_key)
    print("Strike :", state.ce_position.strike_price)
    print("Entry :", state.ce_position.entry_price)
    print("SL :", state.ce_position.sl_price)
    print()
    print("PE POSITION")
    print("Instrument :", state.pe_position.instrument_key)
    print("Strike :", state.pe_position.strike_price)
    print("Entry :", state.pe_position.entry_price)
    print("SL :", state.pe_position.sl_price)

if __name__ == "__main__":
    main()