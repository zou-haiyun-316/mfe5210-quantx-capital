"""
Member C — Data Pipeline
Fetches historical cryptocurrency candlestick data from Binance
and stores it in the database.

Note: Uses the data-api.binance.vision mirror (accessible without VPN)
"""

import time
import sys
import os
import ssl
import json
import urllib.request

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db_manager import save_klines, get_klines, init_database

# Bypass SSL certificate verification (network environment compatibility)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

BASE_URL = "https://data-api.binance.vision/api/v3"


def _get(path: str, params: dict = None) -> dict:
    """Send a GET request to the Binance mirror API."""
    url = f"{BASE_URL}{path}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    resp = urllib.request.urlopen(url, timeout=10, context=SSL_CTX)
    return json.loads(resp.read().decode())


# ================================================================
# Core: fetch candlestick data from Binance
# ================================================================

def fetch_and_store_klines(symbol: str = "BTC/USDT",
                            timeframe: str = "1m",
                            days: int = 7):
    """
    Fetch historical candlestick data from Binance and persist to the database.

    Args:
        symbol:    trading pair, e.g. 'BTC/USDT' (internally converted to BTCUSDT)
        timeframe: candle interval — '1m' = 1 minute, '5m' = 5 minutes, '1h' = 1 hour
        days:      number of past days to fetch
    """
    api_symbol = symbol.replace("/", "")  # BTC/USDT → BTCUSDT
    print(f"[Data Fetch] Fetching {symbol} {timeframe} data for the past {days} day(s)...")

    # Compute start timestamp (milliseconds)
    now_ms    = int(time.time() * 1000)
    since_ms  = now_ms - days * 24 * 60 * 60 * 1000
    batch_size = 1000

    all_klines = []

    while since_ms < now_ms - 60_000:
        try:
            raw = _get("/klines", {
                "symbol":    api_symbol,
                "interval":  timeframe,
                "startTime": since_ms,
                "limit":     batch_size,
            })
            if not raw:
                break

            # Binance candle format: [open_time, open, high, low, close, volume, ...]
            klines = [[r[0], float(r[1]), float(r[2]),
                       float(r[3]), float(r[4]), float(r[5])] for r in raw]
            all_klines.extend(klines)
            since_ms = klines[-1][0] + 1

            from datetime import datetime
            last_time = datetime.fromtimestamp(klines[-1][0] / 1000).strftime("%Y-%m-%d %H:%M")
            print(f"  Fetched {len(all_klines):,} bars — latest: {last_time}")

            time.sleep(0.15)

        except Exception as e:
            print(f"  [Warning] Request failed: {e} — retrying in 3 seconds...")
            time.sleep(3)

    if all_klines:
        save_klines(symbol, timeframe, all_klines)
        print(f"[Data Fetch] Done! Stored {len(all_klines):,} bars.")
    else:
        print("[Data Fetch] No data retrieved.")

    return len(all_klines)


def fetch_latest_price(symbol: str = "BTC/USDT") -> float:
    """
    Fetch the current real-time price.

    Returns:
        Current price in USDT.
    """
    api_symbol = symbol.replace("/", "")
    data = _get("/ticker/price", {"symbol": api_symbol})
    return float(data["price"])


def get_historical_data_for_backtest(symbol: str = "BTC/USDT",
                                      timeframe: str = "1m") -> list:
    """
    Retrieve historical data from the database (interface for Member A's backtester).

    Returns:
        List of dicts: [{open_time, open, high, low, close, volume}, ...]
    """
    data = get_klines(symbol, timeframe, limit=100000)
    print(f"[Data Interface] Returning {len(data):,} bars of {symbol} {timeframe} data")
    return data


def check_data_quality(symbol: str = "BTC/USDT", timeframe: str = "1m"):
    """Check the quality of data currently stored in the database."""
    data = get_klines(symbol, timeframe, limit=100000)

    if not data:
        print("[Data Quality] No data found in the database. Run fetch_and_store_klines() first.")
        return

    from datetime import datetime
    start_dt = datetime.fromtimestamp(data[0]['open_time'] / 1000).strftime("%Y-%m-%d %H:%M")
    end_dt   = datetime.fromtimestamp(data[-1]['open_time'] / 1000).strftime("%Y-%m-%d %H:%M")
    prices   = [d["close"] for d in data]

    print(f"\n[Data Quality] {symbol} {timeframe} Data Quality Report")
    print(f"  Total bars:    {len(data):,}")
    print(f"  Time range:    {start_dt} → {end_dt}")
    print(f"  Price range:   {min(prices):,.2f} ~ {max(prices):,.2f} USDT")
    print(f"  Average price: {sum(prices)/len(prices):,.2f} USDT\n")


if __name__ == "__main__":
    init_database()

    # Test price fetch
    price = fetch_latest_price("BTC/USDT")
    print(f"Current BTC/USDT price: {price:,.2f} USDT")

    # Fetch historical data
    fetch_and_store_klines(symbol="BTC/USDT", timeframe="1m", days=7)
    check_data_quality(symbol="BTC/USDT", timeframe="1m")
