import requests
import upstox_client
from models.config import BASE_URL


def get_headers(access_token):
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }


def _get_expired_api(access_token: str):
    """Create an ExpiredInstrumentApi instance configured with the given access token."""
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    return upstox_client.ExpiredInstrumentApi(upstox_client.ApiClient(configuration))


def get_option_contracts(
        access_token: str,
        instrument_key: str,
        expiry_date: str | None = None,
):
    url = f"{BASE_URL}/option/contract"
    params = {"instrument_key": instrument_key}
    if expiry_date:
        params["expiry_date"] = expiry_date
    response = requests.get(
        url=url,
        params=params,
        headers=get_headers(access_token)
    )

    response.raise_for_status()
    return response.json()


def get_expiries(access_token, instrument_key):
    api_instance = _get_expired_api(access_token)
    try:
        response = api_instance.get_expiries(instrument_key)
        # The SDK returns a list of expiries or a response object containing them
        # Based on Upstox docs, it returns a list of strings (dates)
        return response
    except Exception as e:
        print(f"Exception when calling expired instrument v3 api: {e}")
        return []


def get_expired_option_contracts(access_token, instrument_key, expiry_date):
    api_instance = _get_expired_api(access_token)
    try:
        response = api_instance.get_expired_option_contracts(instrument_key, expiry_date)
        # The SDK returns a GetOptionContractResponse object.
        # We extract the 'data' attribute and convert each InstrumentData object to a dictionary.
        # This ensures compatibility with the REST API format used by build_market_data.
        data_list = [c.to_dict() if hasattr(c, 'to_dict') else vars(c) for c in response.data]
        return {"data": data_list}
    except Exception as e:
        print(f"Exception when calling expired instrument api: {e}")
        return {"data": []}


def get_expired_historical_candles(access_token, instrument_key, interval, from_date, to_date):
    api_instance = _get_expired_api(access_token)
    try:
        # interval should be "1minute", "day", etc.
        response = api_instance.get_expired_historical_candle_data(
            instrument_key, interval, from_date, to_date
        )
        return response
    except Exception as e:
        print(f"Exception when calling expired historical candle api: {e}")
        return None


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
