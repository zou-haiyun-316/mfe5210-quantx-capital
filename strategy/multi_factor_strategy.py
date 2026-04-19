"""
成员 A — 多因子动量交易策略
策略逻辑：结合【价格动量】【成交量】【波动率】三个因子判断买卖时机

因子说明：
  因子1 - 价格动量：计算过去N根K线的涨跌幅。涨幅越强，买入倾向越高。
  因子2 - 成交量因子：当前成交量是否显著高于均值。量价齐升是强势信号。
  因子3 - 波动率因子：当前市场波动是否处于合理范围。波动太大时降低仓位。

最终信号：三个因子加权综合打分，超过阈值时产生买/卖信号。
"""

import sys
import os
import math
from typing import List, Dict

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


# ================================================================
# 技术指标计算函数（这些是策略的"零件"）
# ================================================================

def calc_returns(closes: List[float], period: int) -> List[float]:
    """
    计算价格动量（N周期涨跌幅）
    比如 period=20，就是算过去20根K线的涨跌幅
    返回值为正 = 上涨，为负 = 下跌
    """
    returns = [None] * period
    for i in range(period, len(closes)):
        ret = (closes[i] - closes[i - period]) / closes[i - period]
        returns.append(ret)
    return returns


def calc_volume_ratio(volumes: List[float], period: int = 20) -> List[float]:
    """
    计算成交量比率（当前成交量 / 过去N根的平均成交量）
    > 1 表示成交量放大，< 1 表示成交量萎缩
    """
    ratios = [None] * period
    for i in range(period, len(volumes)):
        avg_vol = sum(volumes[i - period:i]) / period
        ratio = volumes[i] / avg_vol if avg_vol > 0 else 1.0
        ratios.append(ratio)
    return ratios


def calc_volatility(closes: List[float], period: int = 20) -> List[float]:
    """
    计算波动率（过去N根K线收益率的标准差）
    标准差越大 = 价格波动越剧烈 = 风险越高
    """
    vols = [None] * period
    for i in range(period, len(closes)):
        window = closes[i - period:i]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        vols.append(math.sqrt(variance) / mean)  # 归一化为百分比形式
    return vols


def calc_ema(values: List[float], period: int) -> List[float]:
    """
    计算指数移动平均线（EMA）
    比简单平均线更重视近期数据
    """
    emas = [None] * (period - 1)
    if len(values) < period:
        return [None] * len(values)
    # 用前N个值的简单均值作为第一个EMA值
    emas.append(sum(values[:period]) / period)
    k = 2 / (period + 1)
    for i in range(period, len(values)):
        ema = values[i] * k + emas[-1] * (1 - k)
        emas.append(ema)
    return emas


# ================================================================
# 多因子打分系统
# ================================================================

def compute_factor_score(data: List[Dict]) -> List[float]:
    """
    计算每根K线的综合因子得分（-1 到 1 之间）
    > 0 偏多（倾向买入），< 0 偏空（倾向卖出）

    参数：
        data: K线数据列表，每项有 open/high/low/close/volume

    返回：
        每根K线的综合得分列表
    """
    closes  = [d["close"]  for d in data]
    volumes = [d["volume"] for d in data]

    # --- 因子1：价格动量（权重 40%）---
    # 用20根K线的涨跌幅，正值=上涨动量，负值=下跌动量
    momentum_20 = calc_returns(closes, period=20)
    # 标准化到 [-1, 1]：涨幅 > 2% 得满分1，跌幅 > -2% 得-1
    f1 = []
    for m in momentum_20:
        if m is None:
            f1.append(None)
        else:
            f1.append(max(-1.0, min(1.0, m / 0.02)))

    # --- 因子2：成交量（权重 30%）---
    # 成交量放大（>1.5倍均量）且价格上涨 = 强势；萎缩且上涨 = 弱势
    vol_ratio = calc_volume_ratio(volumes, period=20)
    f2 = []
    for i, vr in enumerate(vol_ratio):
        if vr is None or momentum_20[i] is None:
            f2.append(None)
        else:
            # 量价同向加分，量价背离减分
            if momentum_20[i] > 0:
                score = min(1.0, (vr - 1.0) / 1.0)  # 放量上涨，最高1分
            else:
                score = max(-1.0, -(vr - 1.0) / 1.0)  # 放量下跌，最低-1分
            f2.append(score)

    # --- 因子3：波动率（权重 30%）---
    # 波动率过高时降低信心（高波动=不确定性高）
    volatility = calc_volatility(closes, period=20)
    # 定义合理波动率上限：超过 0.5% 开始打折
    f3 = []
    for vl in volatility:
        if vl is None:
            f3.append(None)
        else:
            # 波动率越高，信号越弱（用负向调整动量信号）
            vol_penalty = max(0.0, 1.0 - vl / 0.005)  # 0.5%以内满分，超过打折
            f3.append(vol_penalty - 0.5)  # 居中到[-0.5, 0.5]

    # --- 综合打分：加权求和 ---
    final_scores = []
    for i in range(len(data)):
        if f1[i] is None or f2[i] is None or f3[i] is None:
            final_scores.append(None)
        else:
            score = 0.4 * f1[i] + 0.3 * f2[i] + 0.3 * f3[i]
            final_scores.append(round(score, 4))

    return final_scores


# ================================================================
# 信号生成（策略核心）
# ================================================================

# 信号阈值（经过网格搜索优化后的最优参数）
# 优化结果：夏普比率 6.53，总收益 4.96%，最大回撤 4.64%，胜率 60%
BUY_THRESHOLD  = 0.4   # 综合得分超过0.4 → 买入信号
SELL_THRESHOLD = -0.4  # 综合得分低于-0.4 → 卖出信号

def generate_signals(data: List[Dict]) -> List[Dict]:
    """
    根据因子得分生成交易信号

    返回：
        每根K线对应的信号列表，每项为：
        {
            "index": K线序号,
            "time":  时间戳,
            "close": 收盘价,
            "score": 综合得分,
            "signal": "buy" / "sell" / "hold"  (买/卖/观望)
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
# 对外接口（给成员B执行系统调用）
# ================================================================

def get_latest_signal(data: List[Dict]) -> Dict:
    """
    只返回最新一根K线的信号（给实时交易用）

    参数：
        data: 最近若干根K线（至少需要40根）

    返回：
        最新信号字典 {"signal": "buy"/"sell"/"hold", "score": float, "close": float}
    """
    if len(data) < 40:
        return {"signal": "hold", "score": 0.0, "close": data[-1]["close"] if data else 0}

    signals = generate_signals(data)
    return signals[-1]


if __name__ == "__main__":
    # 简单测试：生成模拟数据验证策略逻辑
    import random
    random.seed(42)

    # 生成100根模拟K线（模拟上涨趋势）
    mock_data = []
    price = 85000.0
    for i in range(100):
        change = random.gauss(0.0005, 0.005)  # 均值微涨，有随机噪音
        price = price * (1 + change)
        volume = random.uniform(10, 50) * (1 + abs(change) * 10)  # 量价相关
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

    print(f"策略信号测试完成：")
    print(f"  买入信号：{len(buys)} 次")
    print(f"  卖出信号：{len(sells)} 次")
    print(f"  观望信号：{len(holds)} 次")
    print(f"  最新信号：{signals[-1]}")
