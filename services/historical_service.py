from datetime import datetime

import requests

from models.config import BASE_URL_V3
from models.models import Candle

def get_historical_candles(
    access_token: str,
    instrument_key: str,
    from_date: str,
    to_date: str,
    interval: int = 1,
):
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    url = (
        f"{BASE_URL_V3}/historical-candle/"
        f"{instrument_key}/"
        f"minutes/{interval}/"
        f"{to_date}/"
        f"{from_date}"
    )

    response = requests.get(
        url,
        headers=headers,
    )

    response.raise_for_status()

    data = response.json()

    candles = []

    for row in data["data"]["candles"]:
        candles.append(
            Candle(
                timestamp=datetime.fromisoformat(
                    row[0].replace("Z", "+00:00")
                ),
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
                oi=row[6],
            )
        )

    return list(reversed(candles))