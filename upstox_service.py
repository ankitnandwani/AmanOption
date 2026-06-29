import requests
from config import BASE_URL

def get_headers(access_token):
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

def get_option_contracts(access_token, instrument_key):
    url = f"{BASE_URL}/option/contract"

    response = requests.get(
        url=url,
        params={"instrument_key": instrument_key},
        headers=get_headers(access_token)
    )

    response.raise_for_status()
    return response.json()


def get_option_chain(strategy, instrument_key, expiry_date):
    access_token = strategy.config.access_token
    url = f"{BASE_URL}/option/chain"

    params = {
        "instrument_key": instrument_key,
        "expiry_date": expiry_date
    }

    res = requests.get(url, headers=get_headers(access_token), params=params)
    res.raise_for_status()

    return res.json()


def refresh_option_chain_prices(market_data, option_chain_data):
    for item in option_chain_data["data"]:
        strike = item["strike_price"]

        if strike not in market_data.contracts_by_strike:
            continue

        # CE
        call = item.get("call_options")
        if call:
            ce_ltp = call.get("market_data", {}).get("ltp")
            market_data.contracts_by_strike[strike]["CE"]["ltp"] = ce_ltp

        # PE
        put = item.get("put_options")
        if put:
            pe_ltp = put.get("market_data", {}).get("ltp")
            market_data.contracts_by_strike[strike]["PE"]["ltp"] = pe_ltp
