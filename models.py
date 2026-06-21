from dataclasses import dataclass
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
    sl_pct: float
    sl_price: float = None
    entry_time: datetime = None
    active: bool = True
    unrealized_pnl: float = 0.0

@dataclass
class StrategyState:
    mode: Mode = Mode.HEDGED
    ce_position: Position = None
    pe_position: Position = None
    active_side: str = "BOTH"
    realized_pnl: float = 0.0
    lot_size: int = 1

@dataclass
class TradingEngineState:
    strategy: StrategyState
    ltp_map: dict
    running: bool = True
    max_loss: float = -3000
    start_time: datetime = None