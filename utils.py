def get_ltp(position, market_data):
    contract = market_data.contracts_by_instrument_key.get(position.instrument_key)

    if contract is None:
        return None

    return contract.get("ltp")

def calculate_position_pnl(position, ltp):
    pnl = (position.entry_price - ltp) * position.quantity
    position.pnl = pnl
    return pnl