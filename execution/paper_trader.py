"""
成员 B — Paper Trading 执行系统（模拟交易）
负责：接收策略信号 → 模拟下单 → 模拟撮合成交 → 更新持仓 → 存入数据库

Paper Trading = 用真实市场价格，但用虚拟资金，不会有真实的资金风险
"""

import sys
import os
import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.db_manager import (
    save_order, update_order_status, save_trade,
    update_position, save_account_snapshot,
    get_current_positions, init_database
)

# ================================================================
# 账户状态（内存中实时维护）
# ================================================================

class Account:
    """模拟账户，维护现金和持仓信息"""

    def __init__(self, initial_cash: float = 50000.0):
        self.cash         = initial_cash   # 可用现金（USDT）
        self.holdings     = {}             # 持仓 {symbol: {"qty": float, "avg_cost": float}}
        self.initial_cash = initial_cash

    def get_position(self, symbol: str) -> Dict:
        """获取某个品种的持仓"""
        return self.holdings.get(symbol, {"qty": 0.0, "avg_cost": 0.0})

    def total_value(self, current_prices: Dict[str, float]) -> float:
        """计算账户总价值（现金 + 所有持仓市值）"""
        position_value = sum(
            info["qty"] * current_prices.get(symbol, 0)
            for symbol, info in self.holdings.items()
        )
        return self.cash + position_value

    def unrealized_pnl(self, symbol: str, current_price: float) -> float:
        """计算某个品种的未实现盈亏"""
        pos = self.get_position(symbol)
        if pos["qty"] <= 0:
            return 0.0
        return (current_price - pos["avg_cost"]) * pos["qty"]


# ================================================================
# 风控模块
# ================================================================

class RiskManager:
    """
    风控管理器：防止账户过度亏损

    规则：
      1. 单笔最大亏损：账户总值的 2%
      2. 最大持仓比例：账户总值的 95%（保留5%现金）
      3. 最大回撤止损：账户从峰值回撤超过 15% 时停止交易
    """

    def __init__(self, max_drawdown_limit: float = 0.15):
        self.max_drawdown_limit = max_drawdown_limit
        self.peak_value         = 0.0
        self.trading_enabled    = True

    def check_drawdown(self, current_value: float) -> bool:
        """检查是否触发最大回撤止损"""
        if current_value > self.peak_value:
            self.peak_value = current_value

        if self.peak_value > 0:
            drawdown = (self.peak_value - current_value) / self.peak_value
            if drawdown >= self.max_drawdown_limit:
                self.trading_enabled = False
                print(f"[风控] 最大回撤达到 {drawdown*100:.1f}%，超过限制 "
                      f"{self.max_drawdown_limit*100:.0f}%，停止交易！")
                return False
        return True

    def check_order(self, account: Account, symbol: str,
                    side: str, qty: float, price: float) -> bool:
        """检查订单是否符合风控要求"""
        if not self.trading_enabled:
            print("[风控] 交易已被暂停（触发最大回撤止损）")
            return False

        order_value = qty * price

        if side == "buy":
            # 检查现金是否足够
            if order_value > account.cash:
                print(f"[风控] 现金不足，需要 {order_value:.2f} USDT，"
                      f"可用 {account.cash:.2f} USDT")
                return False

        elif side == "sell":
            # 检查持仓是否足够
            pos = account.get_position(symbol)
            if qty > pos["qty"]:
                print(f"[风控] 持仓不足，需卖出 {qty:.6f}，"
                      f"实际持有 {pos['qty']:.6f}")
                return False

        return True


# ================================================================
# 模拟撮合引擎（Paper Trading 核心）
# ================================================================

class PaperTrader:
    """
    模拟交易执行器
    接收策略信号，模拟撮合成交，更新账户状态，存入数据库
    """

    COMMISSION_RATE = 0.001  # 手续费率：0.1%（Binance 现货）

    def __init__(self, initial_cash: float = 50000.0):
        self.account      = Account(initial_cash)
        self.risk_manager = RiskManager(max_drawdown_limit=0.15)
        self.order_history: List[Dict] = []

        # 初始化数据库并记录初始账户状态
        init_database()
        save_account_snapshot(initial_cash, initial_cash)
        self.risk_manager.peak_value = initial_cash
        print(f"[执行系统] 初始化完成，初始资金：{initial_cash:,.2f} USDT")

    def execute_signal(self, signal: Dict, current_price: float,
                        symbol: str = "BTC/USDT") -> Optional[Dict]:
        """
        执行一个策略信号

        参数：
            signal:        策略信号 {"signal": "buy"/"sell"/"hold", ...}
            current_price: 当前市场价格（模拟用，实盘从API获取）
            symbol:        交易对

        返回：
            成交记录（如果发生交易），否则返回 None
        """
        action = signal.get("signal", "hold")

        if action == "hold":
            return None  # 观望，不操作

        # 计算交易数量
        if action == "buy":
            return self._execute_buy(symbol, current_price)
        elif action == "sell":
            return self._execute_sell(symbol, current_price)

        return None

    def _execute_buy(self, symbol: str, price: float) -> Optional[Dict]:
        """执行买入操作"""
        # 计算买入金额（使用95%的可用现金）
        spend = self.account.cash * 0.95
        if spend < 1.0:  # 最低1U才下单
            return None

        # 计算买入数量（扣除手续费）
        commission = spend * self.COMMISSION_RATE
        qty = (spend - commission) / price

        # 风控检查
        if not self.risk_manager.check_order(self.account, symbol, "buy", qty, price):
            return None

        # 生成订单ID
        order_id = f"BUY_{uuid.uuid4().hex[:8].upper()}"

        # 保存订单到数据库
        save_order(order_id, symbol, "buy", "market", price, qty, "filled")

        # 更新账户状态
        pos = self.account.get_position(symbol)
        total_qty  = pos["qty"] + qty
        total_cost = pos["avg_cost"] * pos["qty"] + price * qty
        new_avg_cost = total_cost / total_qty if total_qty > 0 else price

        self.account.cash -= spend
        self.account.holdings[symbol] = {"qty": total_qty, "avg_cost": new_avg_cost}

        # 保存成交记录
        save_trade(order_id, symbol, "buy", price, qty, commission)

        # 更新持仓数据库
        unrealized = self.account.unrealized_pnl(symbol, price)
        update_position(symbol, total_qty, new_avg_cost, unrealized)

        # 记录账户快照
        total_value = self.account.total_value({symbol: price})
        save_account_snapshot(self.account.cash, total_value)
        self.risk_manager.check_drawdown(total_value)

        result = {
            "action":    "buy",
            "order_id":  order_id,
            "symbol":    symbol,
            "price":     price,
            "qty":       round(qty, 6),
            "cost":      round(spend, 2),
            "commission": round(commission, 4),
            "time":      datetime.now().isoformat(),
        }
        self.order_history.append(result)
        print(f"[执行] 买入 {qty:.6f} {symbol} @ {price:.2f} USDT "
              f"（花费 {spend:.2f} USDT，手续费 {commission:.4f} USDT）")
        return result

    def _execute_sell(self, symbol: str, price: float) -> Optional[Dict]:
        """执行卖出操作（全仓卖出）"""
        pos = self.account.get_position(symbol)
        if pos["qty"] <= 0:
            return None

        qty = pos["qty"]

        # 风控检查
        if not self.risk_manager.check_order(self.account, symbol, "sell", qty, price):
            return None

        # 计算收益
        revenue    = qty * price
        commission = revenue * self.COMMISSION_RATE
        proceeds   = revenue - commission
        pnl        = proceeds - pos["avg_cost"] * qty

        # 生成订单ID
        order_id = f"SELL_{uuid.uuid4().hex[:8].upper()}"

        # 保存订单
        save_order(order_id, symbol, "sell", "market", price, qty, "filled")

        # 更新账户
        self.account.cash += proceeds
        self.account.holdings[symbol] = {"qty": 0.0, "avg_cost": 0.0}

        # 保存成交记录
        save_trade(order_id, symbol, "sell", price, qty, commission)

        # 更新持仓（清零）
        update_position(symbol, 0.0, 0.0, 0.0)

        # 记录账户快照
        total_value = self.account.total_value({symbol: price})
        save_account_snapshot(self.account.cash, total_value)
        self.risk_manager.check_drawdown(total_value)

        pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
        result = {
            "action":     "sell",
            "order_id":   order_id,
            "symbol":     symbol,
            "price":      price,
            "qty":        round(qty, 6),
            "revenue":    round(revenue, 2),
            "commission": round(commission, 4),
            "pnl":        round(pnl, 2),
            "time":       datetime.now().isoformat(),
        }
        self.order_history.append(result)
        print(f"[执行] 卖出 {qty:.6f} {symbol} @ {price:.2f} USDT "
              f"（到账 {proceeds:.2f} USDT，盈亏 {pnl_str} USDT）")
        return result

    def get_account_summary(self, current_price: float, symbol: str = "BTC/USDT") -> Dict:
        """获取账户摘要（给GUI模块调用）"""
        pos         = self.account.get_position(symbol)
        total_value = self.account.total_value({symbol: current_price})
        unrealized  = self.account.unrealized_pnl(symbol, current_price)
        total_pnl   = total_value - self.account.initial_cash

        return {
            "cash":           round(self.account.cash, 2),
            "holdings_qty":   round(pos["qty"], 6),
            "holdings_symbol": symbol,
            "avg_cost":       round(pos["avg_cost"], 2),
            "current_price":  round(current_price, 2),
            "position_value": round(pos["qty"] * current_price, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_value":    round(total_value, 2),
            "total_pnl":      round(total_pnl, 2),
            "total_return":   round(total_pnl / self.account.initial_cash * 100, 2),
            "trading_enabled": self.risk_manager.trading_enabled,
        }


# ================================================================
# TCA — 交易成本分析（成员C的工作，放在这里方便联调）
# ================================================================

class TCAAnalyzer:
    """
    交易成本分析（Transaction Cost Analysis）
    分析实际交易中产生的各种成本
    """

    def analyze(self, orders: List[Dict]) -> Dict:
        """分析所有交易的成本"""
        if not orders:
            return {}

        total_commission = sum(o.get("commission", 0) for o in orders)
        sell_orders = [o for o in orders if o.get("action") == "sell"]
        total_pnl   = sum(o.get("pnl", 0) for o in sell_orders)

        # 滑点分析（Paper Trading 中假设没有滑点，实盘会有）
        # 实际成交价 vs 信号触发时的价格的差异
        slippage_estimate = total_commission * 0.5  # 简化估算：滑点约为手续费的50%

        return {
            "total_commission":   round(total_commission, 4),
            "estimated_slippage": round(slippage_estimate, 4),
            "total_cost":         round(total_commission + slippage_estimate, 4),
            "cost_as_pct_of_pnl": round(
                (total_commission + slippage_estimate) / abs(total_pnl) * 100, 2
            ) if total_pnl != 0 else 0,
            "num_trades": len(orders),
        }


if __name__ == "__main__":
    # 简单测试
    trader = PaperTrader(initial_cash=50000.0)

    # 模拟几笔交易
    print("\n=== 模拟交易测试 ===")
    trader.execute_signal({"signal": "buy"},  current_price=85000.0)
    trader.execute_signal({"signal": "hold"}, current_price=85200.0)
    trader.execute_signal({"signal": "sell"}, current_price=86000.0)

    # 查看账户状态
    summary = trader.get_account_summary(current_price=86000.0)
    print("\n账户摘要：")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # TCA 分析
    tca = TCAAnalyzer()
    cost_report = tca.analyze(trader.order_history)
    print("\nTCA 成本分析：")
    for k, v in cost_report.items():
        print(f"  {k}: {v}")
