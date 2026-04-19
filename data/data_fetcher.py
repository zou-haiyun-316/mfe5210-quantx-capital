"""
成员 C — 数据抓取管道
负责从 Binance 交易所抓取加密货币历史K线数据，存入数据库

注意：使用 data-api.binance.vision 镜像，国内可访问
"""

import time
import sys
import os
import ssl
import json
import urllib.request

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db_manager import save_klines, get_klines, init_database

# 忽略 SSL 证书验证（国内网络环境）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

BASE_URL = "https://data-api.binance.vision/api/v3"


def _get(path: str, params: dict = None) -> dict:
    """发送 GET 请求到 Binance 镜像 API"""
    url = f"{BASE_URL}{path}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    resp = urllib.request.urlopen(url, timeout=10, context=SSL_CTX)
    return json.loads(resp.read().decode())


# ================================================================
# 核心：从 Binance 抓取K线数据
# ================================================================

def fetch_and_store_klines(symbol: str = "BTC/USDT",
                            timeframe: str = "1m",
                            days: int = 7):
    """
    从 Binance 抓取历史K线数据并存入数据库

    参数：
        symbol:    交易对，如 'BTC/USDT'（内部转为 BTCUSDT）
        timeframe: 时间粒度，'1m'=1分钟，'5m'=5分钟，'1h'=1小时
        days:      获取最近多少天的数据
    """
    api_symbol = symbol.replace("/", "")  # BTC/USDT → BTCUSDT
    print(f"[数据抓取] 开始获取 {symbol} {timeframe} 最近 {days} 天的数据...")

    # 计算起始时间（毫秒时间戳）
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

            # Binance K线格式：[开盘时间, 开, 高, 低, 收, 量, ...]
            klines = [[r[0], float(r[1]), float(r[2]),
                       float(r[3]), float(r[4]), float(r[5])] for r in raw]
            all_klines.extend(klines)
            since_ms = klines[-1][0] + 1

            from datetime import datetime
            last_time = datetime.fromtimestamp(klines[-1][0] / 1000).strftime("%Y-%m-%d %H:%M")
            print(f"  已获取 {len(all_klines):,} 根K线，最新时间：{last_time}")

            time.sleep(0.15)

        except Exception as e:
            print(f"  [警告] 请求失败：{e}，3秒后重试...")
            time.sleep(3)

    if all_klines:
        save_klines(symbol, timeframe, all_klines)
        print(f"[数据抓取] 完成！共存入 {len(all_klines):,} 根K线数据")
    else:
        print("[数据抓取] 未获取到数据")

    return len(all_klines)


def fetch_latest_price(symbol: str = "BTC/USDT") -> float:
    """
    获取当前最新价格（实时）

    返回：当前价格（USDT）
    """
    api_symbol = symbol.replace("/", "")
    data = _get("/ticker/price", {"symbol": api_symbol})
    return float(data["price"])


def get_historical_data_for_backtest(symbol: str = "BTC/USDT",
                                      timeframe: str = "1m") -> list:
    """
    从数据库获取历史数据（给成员A回测使用的接口）

    返回：
        列表，每项为字典：
        {open_time, open, high, low, close, volume}
    """
    data = get_klines(symbol, timeframe, limit=100000)
    print(f"[数据接口] 返回 {len(data):,} 条 {symbol} {timeframe} 数据")
    return data


def check_data_quality(symbol: str = "BTC/USDT", timeframe: str = "1m"):
    """检查数据库中数据的质量"""
    data = get_klines(symbol, timeframe, limit=100000)

    if not data:
        print("[数据检查] 数据库中没有数据，请先运行 fetch_and_store_klines()")
        return

    from datetime import datetime
    start_dt = datetime.fromtimestamp(data[0]['open_time'] / 1000).strftime("%Y-%m-%d %H:%M")
    end_dt   = datetime.fromtimestamp(data[-1]['open_time'] / 1000).strftime("%Y-%m-%d %H:%M")
    prices   = [d["close"] for d in data]

    print(f"\n[数据检查] {symbol} {timeframe} 数据质量报告")
    print(f"  总数据条数：{len(data):,}")
    print(f"  时间范围：  {start_dt} → {end_dt}")
    print(f"  价格范围：  {min(prices):,.2f} ~ {max(prices):,.2f} USDT")
    print(f"  平均价格：  {sum(prices)/len(prices):,.2f} USDT\n")


if __name__ == "__main__":
    init_database()

    # 测试价格获取
    price = fetch_latest_price("BTC/USDT")
    print(f"当前 BTC/USDT 价格：{price:,.2f} USDT")

    # 抓取历史数据
    fetch_and_store_klines(symbol="BTC/USDT", timeframe="1m", days=7)
    check_data_quality(symbol="BTC/USDT", timeframe="1m")
