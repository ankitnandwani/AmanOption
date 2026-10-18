from backtest.replay_engine import run_replay
from models.events import EventBus
from services.strategy_service import create_position, calculate_total_pnl, run_strategy, bootstrap_backtest
from utils import get_ltp


class Strategy:

    def __init__(self, state, market_data, config):
        self.state = state
        self.market_data = market_data
        self.config = config
        self.events = EventBus()
        self.running = True

    def enter_initial_position(self, ce_contract, pe_contract):
        ce_position = create_position(self, ce_contract)
        pe_position = create_position(self, pe_contract)
        self.state.enter_hedged(ce_position, pe_position)
        self.events.info(
            f"Entered HEDGED position | "
            f"CE {ce_position.strike_price} @ {ce_position.entry_price:.2f} | "
            f"PE {pe_position.strike_price} @ {pe_position.entry_price:.2f}"
        )
        self.events.state_changed()

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
        return run_strategy(self)

    def get_snapshot(self):
        return {
            "mode": self.state.mode.value,
            "active_side": self.state.active_side,
            "realized_pnl": round(self.state.realized_pnl, 2),
            "total_pnl": round(calculate_total_pnl(self.state), 2),
            "ce": self._position_to_dict(self.state.ce_position),
            "pe": self._position_to_dict(self.state.pe_position),
            "running": True
        }

    def publish_snapshot(self):
        self.events.publish({
            "type": "snapshot",
            "data": self.get_snapshot()
        })

    def get_subscribed_instruments(self):
        instruments = []

        if self.state.ce_position:
            instruments.append(self.state.ce_position.instrument_key)

        if self.state.pe_position:
            instruments.append(self.state.pe_position.instrument_key)

        return instruments


    def run_backtest(self, historical):
        bootstrap_backtest(
            strategy=self,
            historical=historical,
        )

        return run_replay(
            strategy=self,
            historical_data=historical,
        )