# import upstox_client
# from upstox_client.rest import ApiException
#
# import websocket
# import json
# import threading
# import time as t
#
# from datetime import datetime, time
#
# # =========================================================
# # CONFIG
# # =========================================================
#
# ACCESS_TOKEN = ""
#
# LOT_SIZE = 1
# MAX_DAILY_LOSS = 3000
#
# COMBINED_SL_PERCENT = 10
# DIRECTIONAL_SL_PERCENT = 25
#
# # =========================================================
# # GLOBAL STATE
# # =========================================================
#
# live_prices = {}
#
# daily_pnl = 0
#
# running = True
#
# position = None
# directional_trade = None
#
# # =========================================================
# # API SETUP
# # =========================================================
#
# configuration = upstox_client.Configuration()
# configuration.access_token = ACCESS_TOKEN
#
# api_client = upstox_client.ApiClient(configuration)
#
# order_api = upstox_client.OrderApi(api_client)
#
# # =========================================================
# # ORDER FUNCTIONS
# # =========================================================
#
# def place_market_order(
#         instrument,
#         qty,
#         transaction_type
# ):
#
#     try:
#
#         body = upstox_client.PlaceOrderRequest(
#             quantity=qty,
#             product="D",
#             validity="DAY",
#             price=0,
#             tag="ws_bot",
#             instrument_token=instrument,
#             order_type="MARKET",
#             transaction_type=transaction_type,
#             disclosed_quantity=0,
#             trigger_price=0,
#             is_amo=False
#         )
#
#         response = order_api.place_order(body, "2.0")
#
#         print(
#             f"{transaction_type} SUCCESS:",
#             instrument
#         )
#
#         return response
#
#     except Exception as e:
#
#         print("ORDER ERROR:", e)
#
#         return None
#
#
# # =========================================================
# # WEBSOCKET
# # =========================================================
#
# def on_message(ws, message):
#
#     global live_prices
#
#     try:
#
#         data = json.loads(message)
#
#         if "feeds" not in data:
#             return
#
#         feeds = data["feeds"]
#
#         for instrument, values in feeds.items():
#
#             ltp = values["ltpc"]["ltp"]
#
#             live_prices[instrument] = ltp
#
#     except Exception as e:
#
#         print("WS MESSAGE ERROR:", e)
#
#
# def on_open(ws):
#
#     print("WebSocket Connected")
#
#     subscribe_data = {
#         "guid": "someguid",
#         "method": "sub",
#         "data": {
#             "mode": "ltpc",
#             "instrumentKeys": [
#                 position["ce"]["instrument"],
#                 position["pe"]["instrument"]
#             ]
#         }
#     }
#
#     ws.send(json.dumps(subscribe_data))
#
#
# def start_websocket():
#
#     ws_url = (
#         "wss://api.upstox.com/v3/feed/market-data-feed"
#     )
#
#     headers = [
#         f"Authorization: Bearer {ACCESS_TOKEN}"
#     ]
#
#     ws = websocket.WebSocketApp(
#         ws_url,
#         header=headers,
#         on_open=on_open,
#         on_message=on_message
#     )
#
#     ws.run_forever()
#
#
# # =========================================================
# # OPTION SELECTION
# # =========================================================
#
# def find_75_premium_options():
#
#     """
#     Replace with actual option chain lookup.
#     """
#
#     return {
#         "ce": {
#             "instrument": "NSE_FO|CE_TOKEN",
#             "price": 75
#         },
#         "pe": {
#             "instrument": "NSE_FO|PE_TOKEN",
#             "price": 75
#         }
#     }
#
#
# # =========================================================
# # ENTRY
# # =========================================================
#
# def enter_initial_strangle():
#
#     global position
#
#     options = find_75_premium_options()
#
#     ce = options["ce"]
#     pe = options["pe"]
#
#     place_market_order(
#         ce["instrument"],
#         LOT_SIZE,
#         "SELL"
#     )
#
#     place_market_order(
#         pe["instrument"],
#         LOT_SIZE,
#         "SELL"
#     )
#
#     entry_premium = (
#         ce["price"] + pe["price"]
#     )
#
#     position = {
#         "ce": ce,
#         "pe": pe,
#         "entry_premium": entry_premium,
#         "combined_sl": (
#             entry_premium
#             * (1 + COMBINED_SL_PERCENT / 100)
#         )
#     }
#
#     print("INITIAL STRANGLE ENTERED")
#
#     return position
#
#
# # =========================================================
# # EXIT
# # =========================================================
#
# def exit_all_positions():
#
#     global running
#
#     try:
#
#         if position:
#
#             place_market_order(
#                 position["ce"]["instrument"],
#                 LOT_SIZE,
#                 "BUY"
#             )
#
#             place_market_order(
#                 position["pe"]["instrument"],
#                 LOT_SIZE,
#                 "BUY"
#             )
#
#         if directional_trade:
#
#             place_market_order(
#                 directional_trade["instrument"],
#                 LOT_SIZE,
#                 "BUY"
#             )
#
#     except Exception as e:
#
#         print("EXIT ERROR:", e)
#
#     running = False
#
#     print("ALL POSITIONS CLOSED")
#
#
# # =========================================================
# # PNL
# # =========================================================
#
# def calculate_current_pnl():
#
#     global daily_pnl
#
#     if not position:
#         return 0
#
#     ce_live = live_prices.get(
#         position["ce"]["instrument"],
#         position["ce"]["price"]
#     )
#
#     pe_live = live_prices.get(
#         position["pe"]["instrument"],
#         position["pe"]["price"]
#     )
#
#     ce_pnl = (
#         position["ce"]["price"] - ce_live
#     ) * LOT_SIZE
#
#     pe_pnl = (
#         position["pe"]["price"] - pe_live
#     ) * LOT_SIZE
#
#     total = ce_pnl + pe_pnl
#
#     daily_pnl = total
#
#     return total
#
#
# # =========================================================
# # DIRECTIONAL ENTRY
# # =========================================================
#
# def enter_directional_trade():
#
#     global directional_trade
#
#     ce_live = live_prices[
#         position["ce"]["instrument"]
#     ]
#
#     pe_live = live_prices[
#         position["pe"]["instrument"]
#     ]
#
#     # profitable leg
#     if ce_live < pe_live:
#
#         selected = position["ce"]
#
#     else:
#
#         selected = position["pe"]
#
#     place_market_order(
#         selected["instrument"],
#         LOT_SIZE,
#         "SELL"
#     )
#
#     entry = live_prices[selected["instrument"]]
#
#     directional_trade = {
#         "instrument": selected["instrument"],
#         "entry_price": entry,
#         "lowest_price": entry
#     }
#
#     print("DIRECTIONAL TRADE ENTERED")
#
#
# # =========================================================
# # MAIN MONITOR
# # =========================================================
#
# def monitor_strategy():
#
#     global running
#
#     while running:
#
#         now = datetime.now().time()
#
#         # EOD EXIT
#         if now >= time(15, 20):
#
#             print("EOD EXIT")
#
#             exit_all_positions()
#
#             break
#
#         pnl = calculate_current_pnl()
#
#         print("LIVE PNL:", pnl)
#
#         # DAILY LOSS LIMIT
#         if pnl <= -MAX_DAILY_LOSS:
#
#             print("MAX DAILY LOSS HIT")
#
#             exit_all_positions()
#
#             break
#
#         # COMBINED PREMIUM
#         ce_live = live_prices.get(
#             position["ce"]["instrument"]
#         )
#
#         pe_live = live_prices.get(
#             position["pe"]["instrument"]
#         )
#
#         if ce_live and pe_live:
#
#             combined = ce_live + pe_live
#
#             print("Combined Premium:", combined)
#
#             # STRANGLE SL HIT
#             if combined >= position["combined_sl"]:
#
#                 print("COMBINED SL HIT")
#
#                 exit_all_positions()
#
#                 enter_directional_trade()
#
#         # TRAILING
#         if directional_trade:
#
#             current = live_prices.get(
#                 directional_trade["instrument"]
#             )
#
#             if current:
#
#                 if current < directional_trade["lowest_price"]:
#
#                     directional_trade["lowest_price"] = current
#
#                 trailing_sl = (
#                     directional_trade["lowest_price"]
#                     * 1.10
#                 )
#
#                 if current >= trailing_sl:
#
#                     print("TRAILING SL HIT")
#
#                     exit_all_positions()
#
#                     break
#
#         t.sleep(1)
#
#
# # =========================================================
# # MAIN
# # =========================================================
#
# def run():
#
#     # while datetime.now().time() < time(9, 16):
#     #
#     #     print("Waiting for 9:16...")
#     #
#     #     t.sleep(5)
#
#     enter_initial_strangle()
#
#     # start websocket
#     ws_thread = threading.Thread(
#         target=start_websocket
#     )
#
#     ws_thread.daemon = True
#
#     ws_thread.start()
#
#     # wait for initial ticks
#     t.sleep(3)
#
#     monitor_strategy()


if __name__ == "__main__":

    run()

import upstox_client
import time
import requests
from upstox_client.rest import ApiException

def on_message(message):
    print("MESSAGE RECEIVED:")
    print(message)

def auth():
    headers = {
        "Authorization": f"Bearer "
    }

    response = requests.get(
        "https://api.upstox.com/v2/user/profile",
        headers=headers
    )

    print(response.status_code)
    print(response.text)


def place_order(token):
    print("inside place order")
    configuration = upstox_client.Configuration(sandbox=True)
    configuration.access_token = token
    api_instance = upstox_client.OrderApiV3(upstox_client.ApiClient(configuration))
    body = upstox_client.PlaceOrderV3Request(quantity=4000, product="D", validity="DAY",
                                             price=0, tag="string", instrument_token="NSE_EQ|INE669E01016",
                                             order_type="MARKET", transaction_type="BUY", disclosed_quantity=0,
                                             trigger_price=0.0, is_amo=False, slice=True)

    try:
        api_response = api_instance.place_order(body)
        print(api_response)
    except ApiException as e:
        print("Exception when calling OrderApiV3->place_order: %s\n" % e)

def main():

    print("calling auth")
    auth()
    sandbox_token = ""
    place_order(sandbox_token)

    configuration = upstox_client.Configuration()

    access_token = ""

    configuration.access_token = access_token

    api_client = upstox_client.ApiClient(configuration)

    streamer = upstox_client.MarketDataStreamerV3(
        api_client,
        ["NSE_INDEX|Nifty 50"],
        "full"
    )

    def on_open():

        print("Websocket Opened")

        streamer.subscribe(
            ["NSE_INDEX|Nifty 50"],
            "full"
        )

    def on_error(error):

        print("ERROR:")
        print(error)

    def on_close(message):

        print("CLOSED:")
        print(message)

    streamer.on("open", on_open)
    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)

    print("Connecting...")

    streamer.connect()

    print("Connected")

    # KEEP SCRIPT RUNNING
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()