"""
成员 A — 回测系统
用历史数据模拟策略运行，计算各项绩效指标：
  - 总收益率
  - 夏普比率（Sharpe Ratio）
  - 最大回撤（Max Drawdown）
  - 胜率
  - 信息比率（IR）

【设计说明 — 信号与成交时点】
  为避免 look-ahead bias（未来函数），本系统采用以下规则：
    - 第 i 根K线收盘时生成信号（使用 i 根K线的 close 数据）
    - 实际成交价格 = 第 i+1 根K线的 open 价格
    - 手续费基于实际成交额计算
  这样模拟了真实交易中"收盘信号 → 次根K线开盘立即市价成交"的逻辑，
  不会用到信号生成时点之后的价格信息。

【滑点模型】
  滑点 = 成交额 × SLIPPAGE_RATE（默认 0.02%）
  这是对市场冲击成本的保守估算，适用于 BTC 现货这种高流动性标的。
"""

import sys
import os
import math
import json
from datetime import datetime
from typing import List, Dict

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from strategy.multi_factor_strategy import generate_signals

# ================================================================
# 回测引擎
# ================================================================

class Backtester:
    """
    回测引擎：在历史数据上模拟策略运行

    逻辑说明：
      - 信号生成时点：第 i 根K线收盘
      - 成交时点：第 i+1 根K线开盘（next-bar execution，无 look-ahead bias）
      - 每次买入使用当前可用资金的一定比例（仓位管理）
      - 不允许做空（只做多头，符合现货交易逻辑）
      - 手续费：0.1%（Binance 现货费率）
      - 滑点：0.02% 保守估算（高流动性现货市场）
    """

    def __init__(self,
                 initial_cash: float = 50000.0,   # 初始资金（USDT）
                 commission_rate: float = 0.001,   # 手续费率 0.1%
                 slippage_rate: float = 0.0002,    # 滑点率 0.02%（市场冲击估算）
                 position_size: float = 0.95):     # 每次买入动用资金的比例
        self.initial_cash    = initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate   = slippage_rate
        self.position_size   = position_size

    def run(self, data: List[Dict]) -> Dict:
        """
        运行回测

        参数：
            data: K线数据列表（来自 C 的数据库）

        返回：
            回测结果字典，包含所有绩效指标

        信号 → 成交逻辑（避免 look-ahead bias）：
            信号基于第 i 根K线收盘数据生成，
            实际成交发生在第 i+1 根K线开盘，使用 open 价格 + 滑点。
        """
        signals = generate_signals(data)

        # 账户状态
        cash     = self.initial_cash  # 可用现金（USDT）
        holdings = 0.0                # 持有的 BTC 数量
        avg_cost = 0.0                # 平均持仓成本

        # 记录
        equity_curve    = []  # 每根K线结束时的账户总价值
        benchmark_curve = []  # Buy-and-Hold 基准权益曲线
        trades          = []  # 每笔交易记录
        wins            = 0   # 盈利交易次数
        losses          = 0   # 亏损交易次数
        total_slippage  = 0.0 # 累计滑点成本

        # Buy-and-Hold 基准：在第一根K线开盘价全仓买入，持有到最后
        first_price = data[0]["open"] if data else 1.0
        bh_qty = (self.initial_cash * self.position_size) / first_price

        # 待执行信号队列（用于 next-bar 执行）
        pending_signal = None

        for i, sig in enumerate(signals):
            price = sig["close"]

            # --- Step 1：执行上一根K线产生的待成交信号 ---
            if pending_signal is not None and i > 0:
                # 使用当前K线的 open 价格成交（next-bar execution）
                exec_price = data[i]["open"]

                if pending_signal == "buy" and cash > 10:
                    # 买入滑点：成交价略高于开盘价（买入时更贵）
                    actual_price = exec_price * (1 + self.slippage_rate)
                    spend  = cash * self.position_size
                    fee    = spend * self.commission_rate
                    btc_qty = (spend - fee) / actual_price

                    if btc_qty > 0:
                        slippage_cost = spend * self.slippage_rate
                        total_slippage += slippage_cost

                        total_cost = avg_cost * holdings + actual_price * btc_qty
                        holdings  += btc_qty
                        avg_cost   = total_cost / holdings if holdings > 0 else actual_price
                        cash      -= spend

                        trades.append({
                            "action":    "buy",
                            "time":      sig["time"],
                            "price":     round(actual_price, 2),
                            "qty":       round(btc_qty, 8),
                            "fee":       round(fee, 4),
                            "slippage":  round(slippage_cost, 4),
                            "score":     sig["score"],
                        })

                elif pending_signal == "sell" and holdings > 0:
                    # 卖出滑点：成交价略低于开盘价（卖出时更便宜）
                    actual_price = exec_price * (1 - self.slippage_rate)
                    sell_value   = holdings * actual_price
                    fee          = sell_value * self.commission_rate
                    proceeds     = sell_value - fee
                    slippage_cost = holdings * exec_price * self.slippage_rate
                    total_slippage += slippage_cost

                    cost = avg_cost * holdings
                    pnl  = proceeds - cost

                    if pnl > 0:
                        wins += 1
                    else:
                        losses += 1

                    trades.append({
                        "action":    "sell",
                        "time":      sig["time"],
                        "price":     round(actual_price, 2),
                        "qty":       round(holdings, 8),
                        "fee":       round(fee, 4),
                        "slippage":  round(slippage_cost, 4),
                        "pnl":       round(pnl, 4),
                        "score":     sig["score"],
                    })

                    cash     += proceeds
                    holdings  = 0.0
                    avg_cost  = 0.0

                pending_signal = None

            # --- Step 2：当前K线收盘时根据信号决定是否挂单（下一根开盘成交）---
            signal = sig["signal"]
            if signal == "buy" and cash > 10:
                pending_signal = "buy"
            elif signal == "sell" and holdings > 0:
                pending_signal = "sell"

            # 记录当前账户总价值（现金 + 持仓按收盘价估值）
            total_value = cash + holdings * price
            equity_curve.append(total_value)

            # Buy-and-Hold 基准：初始仓位 + 剩余现金
            bh_value = (self.initial_cash - bh_qty * first_price) + bh_qty * price
            benchmark_curve.append(bh_value)

        # 如果最后还有仓位，按最后收盘价计算总价值
        final_price = data[-1]["close"]
        final_value = cash + holdings * final_price

        # ================================================================
        # 计算绩效指标
        # ================================================================
        metrics = self._calc_metrics(
            equity_curve, benchmark_curve, trades, wins, losses,
            final_value, total_slippage
        )
        metrics["trades"]           = trades
        metrics["equity_curve"]     = equity_curve
        metrics["benchmark_curve"]  = benchmark_curve
        metrics["final_cash"]       = round(cash, 4)
        metrics["final_holdings"]   = round(holdings, 8)
        metrics["final_price"]      = round(final_price, 2)
        metrics["final_value"]      = round(final_value, 4)
        metrics["total_slippage"]   = round(total_slippage, 4)

        return metrics

    def _calc_metrics(self, equity_curve: List[float], benchmark_curve: List[float],
                       trades: List[Dict], wins: int, losses: int,
                       final_value: float, total_slippage: float) -> Dict:
        """计算所有绩效指标"""

        if not equity_curve:
            return {}

        # 1. 总收益率（已是小数，单位：%）
        total_return = (final_value - self.initial_cash) / self.initial_cash * 100

        # 2. Buy-and-Hold 基准收益率
        bh_final = benchmark_curve[-1] if benchmark_curve else self.initial_cash
        bh_return = (bh_final - self.initial_cash) / self.initial_cash * 100

        # 3. 每步收益率（用于计算夏普比率）
        step_returns = []
        for i in range(1, len(equity_curve)):
            r = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            step_returns.append(r)

        # 4. 夏普比率（Sharpe Ratio）
        #    公式：（平均收益率 - 无风险收益率）/ 收益率标准差（年化）
        #    无风险利率：约 4.5% 年化 → 每分钟 4.5% / 525600
        RISK_FREE_PER_MIN = 0.045 / 525600
        sharpe = 0.0
        if step_returns:
            mean_r = sum(step_returns) / len(step_returns)
            std_r  = math.sqrt(
                sum((r - mean_r) ** 2 for r in step_returns) / max(len(step_returns) - 1, 1)
            )
            annual_factor = math.sqrt(525600)
            excess_mean   = mean_r - RISK_FREE_PER_MIN
            sharpe = (excess_mean / std_r * annual_factor) if std_r > 0 else 0.0

        # 5. 最大回撤（Max Drawdown）
        max_drawdown = 0.0
        peak = equity_curve[0]
        for v in equity_curve:
            if v > peak:
                peak = v
            drawdown = (peak - v) / peak
            max_drawdown = max(max_drawdown, drawdown)

        # 6. 胜率
        total_trades = wins + losses
        win_rate = wins / total_trades * 100 if total_trades > 0 else 0.0

        # 7. 信息比率（IR）— 相对于 Buy-and-Hold 的超额收益稳定性
        #    每步超额收益 = 策略步收益 - 基准步收益
        bh_step_returns = []
        for i in range(1, len(benchmark_curve)):
            r = (benchmark_curve[i] - benchmark_curve[i-1]) / benchmark_curve[i-1]
            bh_step_returns.append(r)

        ir = 0.0
        if step_returns and bh_step_returns:
            min_len = min(len(step_returns), len(bh_step_returns))
            excess  = [step_returns[i] - bh_step_returns[i] for i in range(min_len)]
            mean_ex = sum(excess) / len(excess)
            std_ex  = math.sqrt(
                sum((r - mean_ex) ** 2 for r in excess) / max(len(excess) - 1, 1)
            )
            ir = (mean_ex / std_ex * math.sqrt(525600)) if std_ex > 0 else 0.0

        # 8. 盈亏比
        sell_trades = [t for t in trades if t.get("action") == "sell"]
        avg_win  = (sum(t["pnl"] for t in sell_trades if t.get("pnl", 0) > 0) / wins) if wins > 0 else 0
        avg_loss = (sum(abs(t["pnl"]) for t in sell_trades if t.get("pnl", 0) < 0) / losses) if losses > 0 else 0
        profit_factor = (avg_win / avg_loss) if avg_loss > 0 else float("inf")

        # 9. 总手续费
        total_commission = sum(t.get("fee", 0) for t in trades)

        return {
            "total_return":       round(total_return, 2),       # 单位：%
            "benchmark_return":   round(bh_return, 2),          # 单位：%
            "sharpe_ratio":       round(sharpe, 3),
            "max_drawdown":       round(max_drawdown * 100, 2), # 单位：%
            "win_rate":           round(win_rate, 2),           # 单位：%
            "information_ratio":  round(ir, 3),
            "profit_factor":      round(profit_factor, 2),
            "total_trades":       total_trades,
            "winning_trades":     wins,
            "losing_trades":      losses,
            "total_commission":   round(total_commission, 4),
            "total_slippage":     round(total_slippage, 4),
        }


def print_backtest_report(metrics: Dict):
    """打印回测结果报告，并自动将结果写入 backtest_cache.json"""

    # 推算回测日期范围（从 equity_curve 长度 + 当前时间反推）
    now = datetime.now()
    total_minutes = len(metrics.get("equity_curve", []))
    from datetime import timedelta
    start_dt = now - timedelta(minutes=total_minutes)
    date_range = f"{start_dt.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')}"

    print("\n" + "="*60)
    print("         Quant X Capital — 回测报告")
    print("="*60)
    print(f"  策略：多因子动量策略（BTC/USDT 1分钟）")
    print(f"  初始资金：50,000 USDT")
    print(f"  回测区间：{date_range}")
    print(f"  信号执行：收盘信号，下一根K线开盘成交（无 look-ahead bias）")
    print(f"  滑点模型：成交额 × 0.02%（市场冲击保守估算）")
    print("-"*60)
    print(f"  总收益率：       {metrics['total_return']:>8.2f}%")
    print(f"  基准收益率(B&H)：{metrics['benchmark_return']:>8.2f}%  (买入持有基准)")
    print(f"  超额收益：       {metrics['total_return'] - metrics['benchmark_return']:>8.2f}%")
    print(f"  夏普比率：       {metrics['sharpe_ratio']:>8.3f}  (>1好, >2很好)")
    print(f"  最大回撤：       {metrics['max_drawdown']:>8.2f}%  (越小越好)")
    print(f"  胜率：           {metrics['win_rate']:>8.2f}%")
    print(f"  信息比率：       {metrics['information_ratio']:>8.3f}")
    print(f"  盈亏比：         {metrics['profit_factor']:>8.2f}  (盈利/亏损倍数)")
    print(f"  总交易次数：     {metrics['total_trades']:>8d}")
    print(f"  盈利次数：       {metrics['winning_trades']:>8d}")
    print(f"  亏损次数：       {metrics['losing_trades']:>8d}")
    print(f"  总手续费：       {metrics['total_commission']:>8.2f} USDT")
    print(f"  总滑点成本：     {metrics['total_slippage']:>8.2f} USDT")
    print(f"  最终账户总值：   {metrics['final_value']:>10.2f} USDT")
    print("="*60 + "\n")

    # 自动写入 backtest_cache.json（供 GUI 读取）
    _save_cache(metrics)


def _save_cache(metrics: Dict):
    """
    将回测结果写入 backtest_cache.json，供 GUI 模块读取。
    此文件由 python main.py --backtest 自动生成，不得手工修改。
    """
    cache_path = os.path.join(os.path.dirname(__file__), "..", "backtest_cache.json")
    cache_path = os.path.abspath(cache_path)

    # 只序列化可 JSON 化的字段（trades 中可能有 inf）
    safe_metrics = {}
    for k, v in metrics.items():
        if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
            safe_metrics[k] = None
        elif isinstance(v, list):
            # equity_curve / benchmark_curve / trades 直接写入
            safe_metrics[k] = v
        else:
            safe_metrics[k] = v

    # profit_factor 可能为 inf
    if isinstance(safe_metrics.get("profit_factor"), float):
        if math.isinf(safe_metrics["profit_factor"]):
            safe_metrics["profit_factor"] = 999.99

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(safe_metrics, f, ensure_ascii=False)
        print(f"[回测] 结果已自动写入 backtest_cache.json（供 GUI 读取，请勿手工修改）")
    except Exception as e:
        print(f"[警告] 写入 backtest_cache.json 失败：{e}")


if __name__ == "__main__":
    # 测试：用模拟数据跑回测
    import random
    random.seed(42)

    print("生成模拟数据...")
    mock_data = []
    price = 85000.0
    for i in range(500):
        change = random.gauss(0.0003, 0.005)
        price  = max(price * (1 + change), 1)
        volume = random.uniform(5, 30)
        mock_data.append({
            "open_time": i * 60000,
            "open":   price,
            "high":   price * (1 + abs(change)),
            "low":    price * (1 - abs(change)),
            "close":  price,
            "volume": volume,
        })

    backtester = Backtester(initial_cash=50000.0)
    metrics    = backtester.run(mock_data)
    print_backtest_report(metrics)
