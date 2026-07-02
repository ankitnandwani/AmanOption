from datetime import datetime
from models import Position, Mode
from upstox_service import get_option_chain, refresh_option_chain_prices
from utils import get_ltp, calculate_position_pnl, build_market_data


def find_nearest_option(strategy, option_type):
    market_data = strategy.market_data
    target = strategy.config.target_premium
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


def create_position(strategy, contract):
    entry_price = contract["ltp"]
    sl_pct = strategy.config.sl_pct
    return Position(
        instrument_key=contract["instrument_key"],
        option_type=contract["instrument_type"],
        strike_price=contract["strike_price"],
        entry_price=entry_price,
        lot_size=contract["lot_size"],
        num_lots=strategy.config.lots,
        sl_pct=sl_pct,
        sl_price=entry_price * (1 + sl_pct),
        entry_time=datetime.now()
    )


def square_off(strategy):
    state = strategy.state
    market_data = strategy.market_data
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


def check_hedged_sl(strategy):
    state = strategy.state
    market_data = strategy.market_data
    ce_ltp = get_ltp(state.ce_position, market_data)
    pe_ltp = get_ltp(state.pe_position, market_data)

    ce_sl_hit = is_sl_hit(state.ce_position, ce_ltp)
    pe_sl_hit = is_sl_hit(state.pe_position, pe_ltp)

    if ce_sl_hit:
        strategy.events.info("CE SL HIT")
        square_off(strategy)
        new_pe_contract = find_nearest_option(strategy, "PE")
        new_pe_position = create_position(strategy, new_pe_contract)
        state.enter_directional(new_pe_position)
        return True
    elif pe_sl_hit:
        strategy.events.info("PE SL HIT")
        square_off(strategy)
        new_ce_contract = find_nearest_option(strategy, "CE")
        new_ce_position = create_position(strategy, new_ce_contract)
        state.enter_directional(new_ce_position)
        return True
    return False


def check_directional_sl(strategy):
    state = strategy.state
    market_data = strategy.market_data
    if state.active_side == "CE":
        pos = state.ce_position
    else:
        pos = state.pe_position

    current_ltp = get_ltp(pos, market_data)

    if is_sl_hit(pos, current_ltp):
        strategy.events.info("Directional SL HIT")
        square_off(strategy)

        ce_contract = find_nearest_option(strategy, "CE")
        pe_contract = find_nearest_option(strategy, "PE")

        ce_position = create_position(strategy, ce_contract)
        pe_position = create_position(strategy, pe_contract)

        state.enter_hedged(ce_position, pe_position)
        return True
    return False


def calculate_total_pnl(strategy):
    state = strategy.state
    total = state.realized_pnl

    if state.ce_position:
        total += state.ce_position.pnl

    if state.pe_position:
        total += state.pe_position.pnl

    return total


def is_max_loss_hit(strategy):
    total_pnl = calculate_total_pnl(strategy.state)
    return total_pnl <= -strategy.config.max_loss


def update_live_pnl(strategy):
    state = strategy.state
    market_data = strategy.market_data
    if state.ce_position:
        ce_ltp = get_ltp(state.ce_position, market_data)
        calculate_position_pnl(state.ce_position, ce_ltp)

    if state.pe_position:
        pe_ltp = get_ltp(state.pe_position, market_data)
        calculate_position_pnl(state.pe_position, pe_ltp)


def run_strategy(strategy):
    state = strategy.state
    update_live_pnl(strategy)

    if is_max_loss_hit(strategy):
        strategy.events.info()
        strategy.events.info("MAX LOSS HIT")
        square_off(strategy)
        return False

    if state.mode == Mode.HEDGED:
        check_hedged_sl(strategy)
    elif state.mode == Mode.DIRECTIONAL:
        check_directional_sl(strategy)

    return True


def bootstrap_strategy(strategy, underlying_key, expiry):
    market_data = strategy.market_data
    option_chain = get_option_chain(strategy, underlying_key, expiry)
    refresh_option_chain_prices(market_data, option_chain)

    ce_contract = find_nearest_option(strategy, "CE")
    pe_contract = find_nearest_option(strategy, "PE")

    strategy.enter_initial_position(ce_contract, pe_contract)

    return [
        ce_contract["instrument_key"],
        pe_contract["instrument_key"]
    ]
