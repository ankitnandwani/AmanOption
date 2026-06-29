from events import EventBus
from models import Mode
from strategy_service import create_position, update_live_pnl, check_hedged_sl, check_directional_sl, \
    calculate_total_pnl
from utils import get_ltp


class Strategy:

    def __init__(self, state, market_data, config):
        self.state = state
        self.market_data = market_data
        self.config = config
        self.events = EventBus()

    def enter_initial_position(self, ce_contract, pe_contract):
        ce_position = create_position(self, ce_contract)
        pe_position = create_position(self, pe_contract)
        self.state.enter_hedged(ce_position, pe_position)
        self.events.info("Initial positions created")

    def _position_to_dict(self, position):
        if position is None:
            return None

        return {
            "instrument_key": position.instrument_key,
            "option_type": position.option_type,
            "strike": position.strike_price,
            "entry": position.entry_price,
            "sl": position.sl_price,
            "ltp": get_ltp(position, self.market_data),
            "pnl": position.pnl,
            "quantity": position.quantity
        }

    def on_tick(self, instrument_key, ltp):
        if instrument_key not in self.market_data.contracts_by_instrument_key:
            return
        self.market_data.update_ltp(instrument_key, ltp)
        update_live_pnl(self)
        state_changed = False
        if self.state.mode == Mode.HEDGED:
            state_changed = check_hedged_sl(self)
        else:
            state_changed = check_directional_sl(self)
        if state_changed:
            self.events.info("Strategy state updated")

    def get_snapshot(self):
        return {
            "mode": self.state.mode.value,
            "active_side": self.state.active_side,
            "realized_pnl": self.state.realized_pnl,
            "total_pnl": calculate_total_pnl(self),
            "ce": self._position_to_dict(self.state.ce_position),
            "pe": self._position_to_dict(self.state.pe_position),
            "running": True
        }