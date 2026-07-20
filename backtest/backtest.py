from backtest.backtester import Backtester
from models.models import StrategyConfig

def start_backtest(
    config: StrategyConfig,
    replay_date: str,
):
    return Backtester().prepare_day(
        config,
        replay_date,
    )

