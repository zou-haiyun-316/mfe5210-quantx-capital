"""
成员 A — 回测系统
用历史数据模拟策略运行，计算各项绩效指标：
  - 总收益率
  - 夏普比率（Sharp Ratio）
  - 最大回撤（Max Drawdown）
  - 胜率
  - 信息比率（IR）
"""

import sys
import os
import math
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
      - 每次买入使用当前可用资金的一定比例（仓位管理）
      - 不允许做空（只做多头，符合现货交易逻辑）
      - 手续费：0.1%（Binance 现货费率）
    """

    def __init__(self,
                 initial_cash: float = 50000.0,  # 初始资金（USDT）
                 commission_rate: float = 0.001,  # 手续费率 0.1%
                 position_size: float = 0.95):    # 每次买入动用资金的比例
        self.initial_cash   = initial_cash
        self.commission_rate = commission_rate
        self.position_size  = position_size

    def run(self, data: List[Dict]) -> Dict:
        """
        运行回测

        参数：
            data: K线数据列表（来自 C 的数据库）

        返回：
            回测结果字典，包含所有绩效指标
        """
        signals = generate_signals(data)

        # 账户状态
        cash     = self.initial_cash  # 可用现金（USDT）
        holdings = 0.0                # 持有的 BTC 数量
        avg_cost = 0.0                # 平均持仓成本

        # 记录
        equity_curve = []  # 每根K线结束时的账户总价值
        trades       = []  # 每笔交易记录
        wins         = 0   # 盈利交易次数
        losses       = 0   # 亏损交易次数

        for sig in signals:
            price  = sig["close"]
            signal = sig["signal"]

            # --- 执行买入 ---
            if signal == "buy" and cash > 10:  # 现金至少10U才买
                # 计算买入数量
                spend  = cash * self.position_size
                fee    = spend * self.commission_rate
                btc_qty = (spend - fee) / price

                if btc_qty > 0:
                    # 更新持仓均价（如果已有仓位，用加权平均）
                    total_cost = avg_cost * holdings + price * btc_qty
                    holdings  += btc_qty
                    avg_cost   = total_cost / holdings if holdings > 0 else price
                    cash      -= (spend)

                    trades.append({
                        "action":   "buy",
                        "time":     sig["time"],
                        "price":    price,
                        "qty":      btc_qty,
                        "fee":      fee,
                        "score":    sig["score"],
                    })

            # --- 执行卖出 ---
            elif signal == "sell" and holdings > 0:
                # 全仓卖出
                sell_value = holdings * price
                fee        = sell_value * self.commission_rate
                proceeds   = sell_value - fee

                # 计算本次交易盈亏
                cost    = avg_cost * holdings
                pnl     = proceeds - cost

                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

                trades.append({
                    "action":   "sell",
                    "time":     sig["time"],
                    "price":    price,
                    "qty":      holdings,
                    "fee":      fee,
                    "pnl":      pnl,
                    "score":    sig["score"],
                })

                cash     += proceeds
                holdings  = 0.0
                avg_cost  = 0.0

            # 记录当前账户总价值（现金 + 持仓市值）
            total_value = cash + holdings * price
            equity_curve.append(total_value)

        # 如果最后还有仓位，按最后价格计算总价值
        final_price = data[-1]["close"]
        final_value = cash + holdings * final_price

        # ================================================================
        # 计算绩效指标
        # ================================================================

        metrics = self._calc_metrics(equity_curve, trades, wins, losses,
                                      final_value)
        metrics["trades"]        = trades
        metrics["equity_curve"]  = equity_curve
        metrics["final_cash"]    = cash
        metrics["final_holdings"] = holdings
        metrics["final_price"]   = final_price
        metrics["final_value"]   = final_value

        return metrics

    def _calc_metrics(self, equity_curve: List[float], trades: List[Dict],
                       wins: int, losses: int, final_value: float) -> Dict:
        """计算所有绩效指标"""

        if not equity_curve:
            return {}

        # 1. 总收益率
        total_return = (final_value - self.initial_cash) / self.initial_cash

        # 2. 每步收益率（用于计算夏普比率）
        step_returns = []
        for i in range(1, len(equity_curve)):
            r = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            step_returns.append(r)

        # 3. 夏普比率（Sharp Ratio）
        # 公式：（平均收益率 - 无风险收益率）/ 收益率标准差
        # 解释：每承担1份风险，能赚多少超额收益
        # > 1 = 好，> 2 = 很好，> 3 = 优秀
        sharpe = 0.0
        if step_returns:
            mean_r  = sum(step_returns) / len(step_returns)
            std_r   = math.sqrt(sum((r - mean_r)**2 for r in step_returns) / len(step_returns))
            # 年化（1分钟K线：每年约525600根）
            annual_factor = math.sqrt(525600)
            sharpe = (mean_r / std_r * annual_factor) if std_r > 0 else 0.0

        # 4. 最大回撤（Max Drawdown）
        # 从历史最高点到之后最低点的最大跌幅
        # 解释：假设最倒霉的时候，账户从高点最多亏了多少百分比
        max_drawdown = 0.0
        peak = equity_curve[0]
        for v in equity_curve:
            if v > peak:
                peak = v
            drawdown = (peak - v) / peak
            max_drawdown = max(max_drawdown, drawdown)

        # 5. 胜率（盈利交易次数 / 总交易次数）
        total_trades = wins + losses
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        # 6. 信息比率（IR）
        # 衡量超额收益的稳定性，这里用相对于 Buy-and-Hold 的超额收益
        # Buy-and-Hold = 一开始就买入，一直持有到最后
        buy_hold_return = (equity_curve[-1] / equity_curve[0] - 1) if equity_curve[0] > 0 else 0
        excess_returns = [r - buy_hold_return / len(step_returns) for r in step_returns]
        ir = 0.0
        if excess_returns:
            mean_excess = sum(excess_returns) / len(excess_returns)
            std_excess  = math.sqrt(sum((r - mean_excess)**2 for r in excess_returns) / len(excess_returns))
            ir = (mean_excess / std_excess * math.sqrt(525600)) if std_excess > 0 else 0.0

        # 7. 盈亏比（平均盈利 / 平均亏损）
        sell_trades = [t for t in trades if t.get("action") == "sell"]
        avg_win  = (sum(t["pnl"] for t in sell_trades if t.get("pnl", 0) > 0) / wins) if wins > 0 else 0
        avg_loss = (sum(abs(t["pnl"]) for t in sell_trades if t.get("pnl", 0) < 0) / losses) if losses > 0 else 0
        profit_factor = (avg_win / avg_loss) if avg_loss > 0 else float("inf")

        return {
            "total_return":   round(total_return * 100, 2),    # 单位：%
            "sharpe_ratio":   round(sharpe, 3),
            "max_drawdown":   round(max_drawdown * 100, 2),    # 单位：%
            "win_rate":       round(win_rate * 100, 2),        # 单位：%
            "information_ratio": round(ir, 3),
            "profit_factor":  round(profit_factor, 2),
            "total_trades":   total_trades,
            "winning_trades": wins,
            "losing_trades":  losses,
        }


def print_backtest_report(metrics: Dict):
    """打印回测结果报告"""
    print("\n" + "="*50)
    print("         Quant X Capital — 回测报告")
    print("="*50)
    print(f"  策略：多因子动量策略（BTC/USDT 1分钟）")
    print(f"  初始资金：50,000 USDT")
    print("-"*50)
    print(f"  总收益率：   {metrics['total_return']:>8.2f}%")
    print(f"  夏普比率：   {metrics['sharpe_ratio']:>8.3f}  (>1好, >2很好)")
    print(f"  最大回撤：   {metrics['max_drawdown']:>8.2f}%  (越小越好)")
    print(f"  胜率：       {metrics['win_rate']:>8.2f}%")
    print(f"  信息比率：   {metrics['information_ratio']:>8.3f}")
    print(f"  盈亏比：     {metrics['profit_factor']:>8.2f}  (盈利/亏损倍数)")
    print(f"  总交易次数： {metrics['total_trades']:>8d}")
    print(f"  盈利次数：   {metrics['winning_trades']:>8d}")
    print(f"  亏损次数：   {metrics['losing_trades']:>8d}")
    print(f"  最终账户总值：{metrics['final_value']:>10.2f} USDT")
    print("="*50 + "\n")


if __name__ == "__main__":
    # 测试：用模拟数据跑回测
    import random
    random.seed(42)

    print("生成模拟数据...")
    mock_data = []
    price = 85000.0
    for i in range(500):
        change = random.gauss(0.0003, 0.005)
        price = max(price * (1 + change), 1)
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
    metrics = backtester.run(mock_data)
    print_backtest_report(metrics)
