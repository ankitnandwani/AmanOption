import os

BASE_URL = "https://api.upstox.com/v2"
BASE_URL_V3 = "https://api.upstox.com/v3"
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
if not UPSTOX_ACCESS_TOKEN:
    raise RuntimeError(
        "UPSTOX_ACCESS_TOKEN is not set. Please add it to your ~/.zshrc."
    )