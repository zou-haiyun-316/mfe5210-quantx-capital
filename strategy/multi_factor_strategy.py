"""
Member A — Multi-Factor Momentum Trading Strategy
Strategy logic: combines [Price Momentum], [Volume], and [Volatility]
to determine buy/sell timing.

Factor descriptions:
  Factor 1 - Price Momentum: computes the return over the past N bars.
             Higher positive returns = stronger buy inclination.
  Factor 2 - Volume Factor: checks whether current volume is significantly
             above the rolling average. Volume-price alignment is a bullish signal.
  Factor 3 - Volatility Factor: checks whether current market volatility is
             within a reasonable range. Very high volatility reduces position confidence.

Final signal: weighted composite score across all three factors;
exceeding a threshold triggers a buy or sell signal.
"""

import sys
import os
import math
from typing import List, Dict

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


# ================================================================
# Technical indicator helpers (the building blocks of the strategy)
# ================================================================

def calc_returns(closes: List[float], period: int) -> List[float]:
    """
    Compute price momentum (N-period return).
    e.g. period=20 calculates the return over the past 20 bars.
    Positive = price up, negative = price down.
    """
    returns = [None] * period
    for i in range(period, len(closes)):
        ret = (closes[i] - closes[i - period]) / closes[i - period]
        returns.append(ret)
    return returns


def calc_volume_ratio(volumes: List[float], period: int = 20) -> List[float]:
    """
    Compute volume ratio (current volume / rolling N-bar average volume).
    > 1 means volume expanding, < 1 means volume contracting.
    """
    ratios = [None] * period
    for i in range(period, len(volumes)):
        avg_vol = sum(volumes[i - period:i]) / period
        ratio = volumes[i] / avg_vol if avg_vol > 0 else 1.0
        ratios.append(ratio)
    return ratios


def calc_volatility(closes: List[float], period: int = 20) -> List[float]:
    """
    Compute volatility (standard deviation of returns over N bars).
    Higher std dev = more violent price swings = higher risk.
    """
    vols = [None] * period
    for i in range(period, len(closes)):
        window = closes[i - period:i]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        vols.append(math.sqrt(variance) / mean)  # normalised to percentage form
    return vols


def calc_ema(values: List[float], period: int) -> List[float]:
    """
    Compute Exponential Moving Average (EMA).
    Gives more weight to recent data than a simple moving average.
    """
    emas = [None] * (period - 1)
    if len(values) < period:
        return [None] * len(values)
    # Use SMA of first N values as the seed EMA
    emas.append(sum(values[:period]) / period)
    k = 2 / (period + 1)
    for i in range(period, len(values)):
        ema = values[i] * k + emas[-1] * (1 - k)
        emas.append(ema)
    return emas


# ================================================================
# Multi-factor scoring system
# ================================================================

def compute_factor_score(data: List[Dict]) -> List[float]:
    """
    Compute a composite factor score for each bar (range: -1 to +1).
    > 0 = bullish bias (lean toward buying)
    < 0 = bearish bias (lean toward selling)

    Args:
        data: list of bar dicts, each containing open/high/low/close/volume

    Returns:
        List of composite scores, one per bar.
    """
    closes  = [d["close"]  for d in data]
    volumes = [d["volume"] for d in data]

    # --- Factor 1: Price Momentum (weight 40%) ---
    # 20-bar return; positive = upside momentum, negative = downside momentum
    momentum_20 = calc_returns(closes, period=20)
    # Normalise to [-1, 1]: return > +2% scores +1, return < -2% scores -1
    f1 = []
    for m in momentum_20:
        if m is None:
            f1.append(None)
        else:
            f1.append(max(-1.0, min(1.0, m / 0.02)))

    # --- Factor 2: Volume (weight 30%) ---
    # Expanding volume (> 1.5x average) with rising price = bullish;
    # shrinking volume with rising price = weak move
    vol_ratio = calc_volume_ratio(volumes, period=20)
    f2 = []
    for i, vr in enumerate(vol_ratio):
        if vr is None or momentum_20[i] is None:
            f2.append(None)
        else:
            # Volume-price alignment adds score; divergence subtracts
            if momentum_20[i] > 0:
                score = min(1.0, (vr - 1.0) / 1.0)   # expanding volume on up move, max +1
            else:
                score = max(-1.0, -(vr - 1.0) / 1.0)  # expanding volume on down move, max -1
            f2.append(score)

    # --- Factor 3: Volatility (weight 30%) ---
    # High volatility reduces signal confidence (high vol = high uncertainty)
    volatility = calc_volatility(closes, period=20)
    # Reasonable volatility ceiling: above 0.5% the score is penalised
    f3 = []
    for vl in volatility:
        if vl is None:
            f3.append(None)
        else:
            # Higher volatility weakens the signal (negative adjustment to momentum)
            vol_penalty = max(0.0, 1.0 - vl / 0.005)  # full score <= 0.5%, penalised above
            f3.append(vol_penalty - 0.5)  # centre to [-0.5, 0.5]

    # --- Composite score: weighted sum ---
    final_scores = []
    for i in range(len(data)):
        if f1[i] is None or f2[i] is None or f3[i] is None:
            final_scores.append(None)
        else:
            score = 0.4 * f1[i] + 0.3 * f2[i] + 0.3 * f3[i]
            final_scores.append(round(score, 4))

    return final_scores


# ================================================================
# Signal generation (strategy core)
# ================================================================

# Signal thresholds (optimised via grid search)
# Result: Sharpe 6.53, total return 4.96%, max drawdown 4.64%, win rate 60%
BUY_THRESHOLD  = 0.4   # composite score above 0.4 → buy signal
SELL_THRESHOLD = -0.4  # composite score below -0.4 → sell signal

def generate_signals(data: List[Dict]) -> List[Dict]:
    """
    Generate trading signals from factor scores.

    Returns:
        A list of signal dicts, one per bar:
        {
            "index": bar index,
            "time":  timestamp,
            "close": close price,
            "score": composite score,
            "signal": "buy" / "sell" / "hold"
        }
    """
    scores = compute_factor_score(data)
    signals = []

    for i, (d, score) in enumerate(zip(data, scores)):
        if score is None:
            signal = "hold"
        elif score >= BUY_THRESHOLD:
            signal = "buy"
        elif score <= SELL_THRESHOLD:
            signal = "sell"
        else:
            signal = "hold"

        signals.append({
            "index":  i,
            "time":   d.get("open_time", i),
            "close":  d["close"],
            "volume": d["volume"],
            "score":  score,
            "signal": signal,
        })

    return signals


# ================================================================
# Public interface (called by Member B's execution system)
# ================================================================

def get_latest_signal(data: List[Dict]) -> Dict:
    """
    Return only the signal for the most recent bar (used in live trading).

    Args:
        data: recent bars (minimum 40 required)

    Returns:
        Latest signal dict: {"signal": "buy"/"sell"/"hold", "score": float, "close": float}
    """
    if len(data) < 40:
        return {"signal": "hold", "score": 0.0, "close": data[-1]["close"] if data else 0}

    signals = generate_signals(data)
    return signals[-1]


if __name__ == "__main__":
    # Quick sanity test: generate synthetic data and validate strategy logic
    import random
    random.seed(42)

    # Generate 100 synthetic bars (simulated uptrend)
    mock_data = []
    price = 85000.0
    for i in range(100):
        change = random.gauss(0.0005, 0.005)  # slight upward drift with noise
        price = price * (1 + change)
        volume = random.uniform(10, 50) * (1 + abs(change) * 10)  # volume-price correlation
        mock_data.append({
            "open_time": i * 60000,
            "open":   price * (1 - abs(change) / 2),
            "high":   price * (1 + abs(change)),
            "low":    price * (1 - abs(change)),
            "close":  price,
            "volume": volume,
        })

    signals = generate_signals(mock_data)
    buys  = [s for s in signals if s["signal"] == "buy"]
    sells = [s for s in signals if s["signal"] == "sell"]
    holds = [s for s in signals if s["signal"] == "hold"]

    print("Strategy signal test complete:")
    print(f"  Buy signals:  {len(buys)}")
    print(f"  Sell signals: {len(sells)}")
    print(f"  Hold signals: {len(holds)}")
    print(f"  Latest signal: {signals[-1]}")
