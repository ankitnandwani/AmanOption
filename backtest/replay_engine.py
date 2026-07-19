from services.strategy_service import square_off


def run_replay(strategy, historical_data):
    if not historical_data:
        raise Exception("No historical data loaded")

    timeline = sorted({
        candle.timestamp
        for candles in historical_data.values()
        for candle in candles
    })

    candle_maps = {
        instrument_key: {
            candle.timestamp: candle
            for candle in candles
        }
        for instrument_key, candles in historical_data.items()
    }

    running = True

    for timestamp in timeline:
        if not running:
            break
        subscribed = strategy.get_subscribed_instruments()
        for instrument_key in subscribed:
            if not running:
                break
            candle_map = candle_maps.get(instrument_key)
            if candle_map is None:
                continue
            candle = candle_map.get(timestamp)
            if candle is None:
                continue
            prices = []
            for price in (
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
            ):
                if not prices or prices[-1] != price:
                    prices.append(price)

            for price in prices:
                running = strategy.on_tick(
                    instrument_key,
                    price,
                )

                if not running:
                    break

    if (
            strategy.state.ce_position is not None
            or strategy.state.pe_position is not None
    ):
        strategy.events.info("End of replay - squaring off remaining positions")
        square_off(strategy)

    snapshot = strategy.get_snapshot()
    strategy.events.info(
        f"Replay completed | "
        f"Realized={snapshot['realized_pnl']:.2f} | "
        f"Total={snapshot['total_pnl']:.2f}"
    )

    return snapshot