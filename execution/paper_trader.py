"""
Member B — Paper Trading Execution System (Simulated Trading)
Responsibilities: receive strategy signals → simulate order placement →
simulate matching/fill → update positions → persist to database.

Paper Trading = uses real market prices with virtual capital; no real financial risk.
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
# Account State (maintained in-memory in real time)
# ================================================================

class Account:
    """Simulated account — tracks cash and position information."""

    def __init__(self, initial_cash: float = 50000.0):
        self.cash         = initial_cash   # Available cash (USDT)
        self.holdings     = {}             # Positions: {symbol: {"qty": float, "avg_cost": float}}
        self.initial_cash = initial_cash

    def get_position(self, symbol: str) -> Dict:
        """Return the current position for a given symbol."""
        return self.holdings.get(symbol, {"qty": 0.0, "avg_cost": 0.0})

    def total_value(self, current_prices: Dict[str, float]) -> float:
        """Compute total account value (cash + market value of all positions)."""
        position_value = sum(
            info["qty"] * current_prices.get(symbol, 0)
            for symbol, info in self.holdings.items()
        )
        return self.cash + position_value

    def unrealized_pnl(self, symbol: str, current_price: float) -> float:
        """Compute unrealised P&L for a given symbol."""
        pos = self.get_position(symbol)
        if pos["qty"] <= 0:
            return 0.0
        return (current_price - pos["avg_cost"]) * pos["qty"]


# ================================================================
# Risk Management Module
# ================================================================

class RiskManager:
    """
    Risk manager: prevents excessive account losses.

    Rules:
      1. Max loss per trade: 2% of total account value
      2. Max position size: 95% of total account value (keep 5% cash reserve)
      3. Max drawdown stop: halt trading when account drops more than 15% from peak
    """

    def __init__(self, max_drawdown_limit: float = 0.15):
        self.max_drawdown_limit = max_drawdown_limit
        self.peak_value         = 0.0
        self.trading_enabled    = True

    def check_drawdown(self, current_value: float) -> bool:
        """Check whether the maximum drawdown threshold has been breached."""
        if current_value > self.peak_value:
            self.peak_value = current_value

        if self.peak_value > 0:
            drawdown = (self.peak_value - current_value) / self.peak_value
            if drawdown >= self.max_drawdown_limit:
                self.trading_enabled = False
                print(f"[Risk] Max drawdown reached {drawdown*100:.1f}%, "
                      f"exceeds limit {self.max_drawdown_limit*100:.0f}% — trading halted!")
                return False
        return True

    def check_order(self, account: Account, symbol: str,
                    side: str, qty: float, price: float) -> bool:
        """Validate an order against risk rules."""
        if not self.trading_enabled:
            print("[Risk] Trading is suspended (max drawdown stop triggered).")
            return False

        order_value = qty * price

        if side == "buy":
            # Check whether cash is sufficient
            if order_value > account.cash:
                print(f"[Risk] Insufficient cash: need {order_value:.2f} USDT, "
                      f"available {account.cash:.2f} USDT")
                return False

        elif side == "sell":
            # Check whether position is sufficient
            pos = account.get_position(symbol)
            if qty > pos["qty"]:
                print(f"[Risk] Insufficient position: need to sell {qty:.6f}, "
                      f"holding {pos['qty']:.6f}")
                return False

        return True


# ================================================================
# Simulated Matching Engine (Paper Trading core)
# ================================================================

class PaperTrader:
    """
    Simulated trade executor.
    Receives strategy signals, simulates fills, updates account state, persists to database.
    """

    COMMISSION_RATE = 0.001  # Commission rate: 0.1% (Binance spot)

    def __init__(self, initial_cash: float = 50000.0):
        self.account      = Account(initial_cash)
        self.risk_manager = RiskManager(max_drawdown_limit=0.15)
        self.order_history: List[Dict] = []

        # Initialise database and record initial account snapshot
        init_database()
        save_account_snapshot(initial_cash, initial_cash)
        self.risk_manager.peak_value = initial_cash
        print(f"[Execution] Initialised. Starting capital: {initial_cash:,.2f} USDT")

    def execute_signal(self, signal: Dict, current_price: float,
                        symbol: str = "BTC/USDT") -> Optional[Dict]:
        """
        Execute a strategy signal.

        Args:
            signal:        strategy signal {"signal": "buy"/"sell"/"hold", ...}
            current_price: current market price (simulated; pulled from API in live mode)
            symbol:        trading pair

        Returns:
            Fill record if a trade occurred, otherwise None.
        """
        action = signal.get("signal", "hold")

        if action == "hold":
            return None  # Hold — do nothing

        # Route to the appropriate execution handler
        if action == "buy":
            return self._execute_buy(symbol, current_price)
        elif action == "sell":
            return self._execute_sell(symbol, current_price)

        return None

    def _execute_buy(self, symbol: str, price: float) -> Optional[Dict]:
        """Execute a buy order."""
        # Deploy 95% of available cash
        spend = self.account.cash * 0.95
        if spend < 1.0:  # Minimum order size: 1 USDT
            return None

        # Compute quantity after deducting commission
        commission = spend * self.COMMISSION_RATE
        qty = (spend - commission) / price

        # Risk check
        if not self.risk_manager.check_order(self.account, symbol, "buy", qty, price):
            return None

        # Generate order ID
        order_id = f"BUY_{uuid.uuid4().hex[:8].upper()}"

        # Persist order to database
        save_order(order_id, symbol, "buy", "market", price, qty, "filled")

        # Update account state
        pos = self.account.get_position(symbol)
        total_qty  = pos["qty"] + qty
        total_cost = pos["avg_cost"] * pos["qty"] + price * qty
        new_avg_cost = total_cost / total_qty if total_qty > 0 else price

        self.account.cash -= spend
        self.account.holdings[symbol] = {"qty": total_qty, "avg_cost": new_avg_cost}

        # Persist fill record
        save_trade(order_id, symbol, "buy", price, qty, commission)

        # Update position in database
        unrealized = self.account.unrealized_pnl(symbol, price)
        update_position(symbol, total_qty, new_avg_cost, unrealized)

        # Record account snapshot
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
        print(f"[Fill] Bought {qty:.6f} {symbol} @ {price:.2f} USDT "
              f"(spent {spend:.2f} USDT, commission {commission:.4f} USDT)")
        return result

    def _execute_sell(self, symbol: str, price: float) -> Optional[Dict]:
        """Execute a sell order (liquidate full position)."""
        pos = self.account.get_position(symbol)
        if pos["qty"] <= 0:
            return None

        qty = pos["qty"]

        # Risk check
        if not self.risk_manager.check_order(self.account, symbol, "sell", qty, price):
            return None

        # Compute proceeds
        revenue    = qty * price
        commission = revenue * self.COMMISSION_RATE
        proceeds   = revenue - commission
        pnl        = proceeds - pos["avg_cost"] * qty

        # Generate order ID
        order_id = f"SELL_{uuid.uuid4().hex[:8].upper()}"

        # Persist order
        save_order(order_id, symbol, "sell", "market", price, qty, "filled")

        # Update account
        self.account.cash += proceeds
        self.account.holdings[symbol] = {"qty": 0.0, "avg_cost": 0.0}

        # Persist fill record
        save_trade(order_id, symbol, "sell", price, qty, commission)

        # Clear position in database
        update_position(symbol, 0.0, 0.0, 0.0)

        # Record account snapshot
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
        print(f"[Fill] Sold {qty:.6f} {symbol} @ {price:.2f} USDT "
              f"(received {proceeds:.2f} USDT, P&L {pnl_str} USDT)")
        return result

    def get_account_summary(self, current_price: float, symbol: str = "BTC/USDT") -> Dict:
        """Return account summary (called by the GUI module)."""
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
# TCA — Transaction Cost Analysis
# ================================================================

class TCAAnalyzer:
    """
    Transaction Cost Analysis.
    Analyses the various costs incurred across all executed trades.
    """

    def analyze(self, orders: List[Dict]) -> Dict:
        """Analyse transaction costs across all orders."""
        if not orders:
            return {}

        total_commission = sum(o.get("commission", 0) for o in orders)
        sell_orders = [o for o in orders if o.get("action") == "sell"]
        total_pnl   = sum(o.get("pnl", 0) for o in sell_orders)

        # Slippage analysis (Paper Trading assumes zero slippage; live trading would incur it)
        # Simplified estimate: slippage ≈ 50% of commission
        slippage_estimate = total_commission * 0.5

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
    # Quick test
    trader = PaperTrader(initial_cash=50000.0)

    # Simulate a few trades
    print("\n=== Simulated Trade Test ===")
    trader.execute_signal({"signal": "buy"},  current_price=85000.0)
    trader.execute_signal({"signal": "hold"}, current_price=85200.0)
    trader.execute_signal({"signal": "sell"}, current_price=86000.0)

    # View account state
    summary = trader.get_account_summary(current_price=86000.0)
    print("\nAccount Summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # TCA analysis
    tca = TCAAnalyzer()
    cost_report = tca.analyze(trader.order_history)
    print("\nTCA Cost Analysis:")
    for k, v in cost_report.items():
        print(f"  {k}: {v}")
