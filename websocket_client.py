import asyncio
import json
import websockets

from config import ACCESS_TOKEN


class UpstoxWebSocket:

    def __init__(self, market_data):
        self.market_data = market_data

        self.websocket = None

    connect()

    subscribe()

    unsubscribe()

    listen()

    process_tick()