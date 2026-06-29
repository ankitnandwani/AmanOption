from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

class Mode(Enum):
    HEDGED = "HEDGED"
    DIRECTIONAL = "DIRECTIONAL"

@dataclass
class Position:
    instrument_key: str
    option_type: str  # CE or PE
    strike_price: float
    entry_price: float
    lot_size: int
    num_lots: int
    sl_pct: float
    sl_price: float
    entry_time: datetime
    active: bool = True
    quantity: int = field(init=False)
    pnl: float = 0

    def __post_init__(self):
        self.quantity = self.lot_size * self.num_lots

@dataclass
class StrategyState:
    mode: Mode = Mode.HEDGED
    ce_position: Position = None
    pe_position: Position = None
    active_side: str = "BOTH"
    realized_pnl: float = 0.0

    def enter_hedged(self, ce_position, pe_position):
        self.mode = Mode.HEDGED
        self.ce_position = ce_position
        self.pe_position = pe_position
        self.active_side = "BOTH"

    def enter_directional(self, position):
        self.mode = Mode.DIRECTIONAL
        if position.option_type == "CE":
            self.ce_position = position
            self.pe_position = None
            self.active_side = "CE"
        else:
            self.pe_position = position
            self.ce_position = None
            self.active_side = "PE"

@dataclass
class TradingEngineState:
    strategy: StrategyState
    ltp_map: dict
    running: bool = True
    max_loss: float = -3000
    start_time: datetime = None

@dataclass
class MarketData:
    contracts_by_strike: dict = field(default_factory=dict)
    contracts_by_instrument_key: dict = field(default_factory=dict)

    def update_ltp(self, instrument_key, ltp):
        contract = self.contracts_by_instrument_key.get(instrument_key)

        if contract:
            contract["ltp"] = ltp

@dataclass
class StrategyConfig:
    access_token: str
    underlying_key: str
    lots: int
    target_premium: float
    sl_pct: float
    max_loss: float