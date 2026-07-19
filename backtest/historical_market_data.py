from services.historical_service import get_historical_candles


def load_historical_market_data(
    access_token,
    contracts_by_instrument_key,
    from_date,
    to_date,
    events,
):
    historical = {}

    total = len(contracts_by_instrument_key)

    events.info(
        f"Downloading historical data for {total} contracts..."
    )

    for index, instrument_key in enumerate(
        contracts_by_instrument_key,
        start=1,
    ):
        events.progress(
            stage=f"Downloading historical data ({instrument_key})",
            current=index,
            total=total,
        )

        candles = get_historical_candles(
            access_token=access_token,
            instrument_key=instrument_key,
            from_date=from_date,
            to_date=to_date,
        )

        historical[instrument_key] = candles

    events.info(
        "Historical data download completed."
    )

    return historical