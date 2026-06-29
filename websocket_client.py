
import upstox_client

class WebSocketClient:

    def __init__(self, strategy, initial_instrument_keys, access_token):
        self.strategy = strategy
        self.initial_instrument_keys = initial_instrument_keys
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        api_client = upstox_client.ApiClient(configuration)
        self.streamer = upstox_client.MarketDataStreamerV3(api_client)
        self.register_callbacks()

    def register_callbacks(self):
        self.streamer.on("open", self.on_open)
        self.streamer.on("message", self.on_message)
        self.streamer.on("error", self.on_error)
        self.streamer.on("close", self.on_close)

    def connect(self):
        self.streamer.auto_reconnect(True, 5, 20)
        self.streamer.connect()

    def subscribe(self, instrument_keys):
        self.streamer.subscribe(instrument_keys, "full")

    def unsubscribe(self, instrument_keys):
        self.streamer.unsubscribe(instrument_keys)

    def on_open(self):
        print("Connected")
        self.subscribe(self.initial_instrument_keys)

    def on_message(self, message):
        if "feeds" not in message:
            return

        for instrument_key, feed in message["feeds"].items():
            try:
                ltp = (
                    feed["fullFeed"]
                    ["marketFF"]
                    ["ltpc"]
                    ["ltp"]
                )
            except Exception:
                continue

            self.strategy.on_tick(instrument_key, ltp)

    def on_error(self, error):
        print("WebSocket Error:")
        print(error)

    def on_close(self):
        print("WebSocket Closed")