from models import MarketData


def get_ltp(position, market_data):
    contract = market_data.contracts_by_instrument_key.get(position.instrument_key)

    if contract is None:
        return None

    return contract.get("ltp")


def calculate_position_pnl(position, ltp):
    pnl = (position.entry_price - ltp) * position.quantity
    position.pnl = pnl
    return pnl

def build_market_data(contracts, expiry):
    market_data = MarketData()

    current_expiry_contracts = [
        c for c in contracts["data"]
        if c["expiry"] == expiry
    ]

    current_expiry_contracts.sort(
        key=lambda x: (
            x["strike_price"],
            x["instrument_type"]
        )
    )

    for c in current_expiry_contracts:
        strike = c["strike_price"]
        option_type = c["instrument_type"]

        market_data.contracts_by_strike.setdefault(strike, {})
        market_data.contracts_by_strike[strike][option_type] = c
        market_data.contracts_by_instrument_key[
            c["instrument_key"]
        ] = c

    return market_data