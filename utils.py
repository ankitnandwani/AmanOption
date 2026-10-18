from models.models import MarketData


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

    current_expiry_contracts = []
    for c in contracts["data"]:
        c_expiry = c["expiry"]
        # Normalize datetime objects to YYYY-MM-DD strings for comparison
        if hasattr(c_expiry, "strftime"):
            c_expiry_str = c_expiry.strftime("%Y-%m-%d")
        else:
            c_expiry_str = str(c_expiry)

        if c_expiry_str == expiry:
            current_expiry_contracts.append(c)


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