"""
Member A — Backtest Engine
Simulates strategy execution on historical data and computes performance metrics:
  - Total Return
  - Sharpe Ratio
  - Maximum Drawdown
  - Win Rate
  - Information Ratio (IR)

[Design Note — Signal vs. Fill Timing]
  To avoid look-ahead bias, the system applies the following rule:
    - Signal is generated at the close of bar i (using bar i's close price)
    - Actual fill price = open price of bar i+1
    - Commission is calculated on the actual fill amount
  This simulates real-world "close-bar signal → immediate market fill at next open" logic
  and does not use any price information after the signal generation point.

[Slippage Model]
  Slippage = trade value × SLIPPAGE_RATE (default 0.02%)
  This is a conservative estimate of market impact cost, appropriate for
  high-liquidity instruments such as BTC spot.
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
# Backtest Engine
# ================================================================

class Backtester:
    """
    Backtesting engine: simulates strategy execution on historical data.

    Execution logic:
      - Signal generated at: close of bar i
      - Fill at: open of bar i+1 (next-bar execution, no look-ahead bias)
      - Each buy uses a fixed fraction of available cash (position sizing)
      - Short selling not allowed (long-only, consistent with spot trading)
      - Commission: 0.1% (Binance spot rate)
      - Slippage: 0.02% conservative estimate (high-liquidity spot market)
    """

    def __init__(self,
                 initial_cash: float = 50000.0,   # Starting capital (USDT)
                 commission_rate: float = 0.001,   # Commission rate 0.1%
                 slippage_rate: float = 0.0002,    # Slippage rate 0.02% (market impact estimate)
                 position_size: float = 0.95):     # Fraction of cash deployed per buy
        self.initial_cash    = initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate   = slippage_rate
        self.position_size   = position_size

    def run(self, data: List[Dict]) -> Dict:
        """
        Run the backtest.

        Args:
            data: list of bar dicts (sourced from Member C's database)

        Returns:
            Dict of backtest results containing all performance metrics.

        Signal → fill logic (avoids look-ahead bias):
            Signal is generated from bar i's close data;
            actual fill occurs at bar i+1's open price plus slippage.
        """
        signals = generate_signals(data)

        # Account state
        cash     = self.initial_cash  # Available cash (USDT)
        holdings = 0.0                # BTC quantity held
        avg_cost = 0.0                # Average holding cost

        # Tracking records
        equity_curve    = []  # Account total value at the end of each bar
        benchmark_curve = []  # Buy-and-hold benchmark equity curve
        trades          = []  # Trade log
        wins            = 0   # Number of profitable trades
        losses          = 0   # Number of losing trades
        total_slippage  = 0.0 # Cumulative slippage cost

        # Buy-and-Hold benchmark: buy at the open of the first bar, hold until the end
        first_price = data[0]["open"] if data else 1.0
        bh_qty = (self.initial_cash * self.position_size) / first_price

        # Pending signal queue (for next-bar execution)
        pending_signal = None

        for i, sig in enumerate(signals):
            price = sig["close"]

            # --- Step 1: Execute the pending signal from the previous bar ---
            if pending_signal is not None and i > 0:
                # Fill at the current bar's open price (next-bar execution)
                exec_price = data[i]["open"]

                if pending_signal == "buy" and cash > 10:
                    # Buy slippage: fill price slightly above open (more expensive to buy)
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
                    # Sell slippage: fill price slightly below open (less received when selling)
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

            # --- Step 2: At the close of the current bar, queue an order for the next open ---
            signal = sig["signal"]
            if signal == "buy" and cash > 10:
                pending_signal = "buy"
            elif signal == "sell" and holdings > 0:
                pending_signal = "sell"

            # Record account total value (cash + holdings marked to close price)
            total_value = cash + holdings * price
            equity_curve.append(total_value)

            # Buy-and-Hold benchmark: initial position + remaining cash
            bh_value = (self.initial_cash - bh_qty * first_price) + bh_qty * price
            benchmark_curve.append(bh_value)

        # If still holding at the end, mark to the final close price
        final_price = data[-1]["close"]
        final_value = cash + holdings * final_price

        # ================================================================
        # Compute performance metrics
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
        """Compute all performance metrics."""

        if not equity_curve:
            return {}

        # 1. Total return (decimal, converted to %)
        total_return = (final_value - self.initial_cash) / self.initial_cash * 100

        # 2. Buy-and-Hold benchmark return
        bh_final = benchmark_curve[-1] if benchmark_curve else self.initial_cash
        bh_return = (bh_final - self.initial_cash) / self.initial_cash * 100

        # 3. Per-step returns (used to compute Sharpe ratio)
        step_returns = []
        for i in range(1, len(equity_curve)):
            r = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            step_returns.append(r)

        # 4. Sharpe Ratio
        #    Formula: (mean return - risk-free rate) / std dev of returns (annualised)
        #    Risk-free rate: ~4.5% p.a. → per minute: 4.5% / 525600
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

        # 5. Maximum Drawdown
        max_drawdown = 0.0
        peak = equity_curve[0]
        for v in equity_curve:
            if v > peak:
                peak = v
            drawdown = (peak - v) / peak
            max_drawdown = max(max_drawdown, drawdown)

        # 6. Win Rate
        total_trades = wins + losses
        win_rate = wins / total_trades * 100 if total_trades > 0 else 0.0

        # 7. Information Ratio (IR) — excess return stability vs. Buy-and-Hold
        #    Per-step excess return = strategy step return - benchmark step return
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

        # 8. Profit Factor
        sell_trades = [t for t in trades if t.get("action") == "sell"]
        avg_win  = (sum(t["pnl"] for t in sell_trades if t.get("pnl", 0) > 0) / wins) if wins > 0 else 0
        avg_loss = (sum(abs(t["pnl"]) for t in sell_trades if t.get("pnl", 0) < 0) / losses) if losses > 0 else 0
        profit_factor = (avg_win / avg_loss) if avg_loss > 0 else float("inf")

        # 9. Total commission
        total_commission = sum(t.get("fee", 0) for t in trades)

        return {
            "total_return":       round(total_return, 2),       # unit: %
            "benchmark_return":   round(bh_return, 2),          # unit: %
            "sharpe_ratio":       round(sharpe, 3),
            "max_drawdown":       round(max_drawdown * 100, 2), # unit: %
            "win_rate":           round(win_rate, 2),           # unit: %
            "information_ratio":  round(ir, 3),
            "profit_factor":      round(profit_factor, 2),
            "total_trades":       total_trades,
            "winning_trades":     wins,
            "losing_trades":      losses,
            "total_commission":   round(total_commission, 4),
            "total_slippage":     round(total_slippage, 4),
        }


def print_backtest_report(metrics: Dict):
    """Print the backtest results report and auto-write to backtest_cache.json."""

    # Infer backtest date range from equity_curve length + current time
    now = datetime.now()
    total_minutes = len(metrics.get("equity_curve", []))
    from datetime import timedelta
    start_dt = now - timedelta(minutes=total_minutes)
    date_range = f"{start_dt.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}"

    print("\n" + "="*60)
    print("         Quant X Capital — Backtest Report")
    print("="*60)
    print(f"  Strategy:    Multi-Factor Momentum (BTC/USDT 1-min)")
    print(f"  Capital:     50,000 USDT")
    print(f"  Period:      {date_range}")
    print(f"  Execution:   Close-bar signal, filled at next bar's open (no look-ahead bias)")
    print(f"  Slippage:    Trade value × 0.02% (conservative market impact estimate)")
    print("-"*60)
    print(f"  Total Return:        {metrics['total_return']:>8.2f}%")
    print(f"  Benchmark (B&H):     {metrics['benchmark_return']:>8.2f}%  (buy-and-hold)")
    print(f"  Excess Return:       {metrics['total_return'] - metrics['benchmark_return']:>8.2f}%")
    print(f"  Sharpe Ratio:        {metrics['sharpe_ratio']:>8.3f}  (>1 good, >2 excellent)")
    print(f"  Max Drawdown:        {metrics['max_drawdown']:>8.2f}%  (lower is better)")
    print(f"  Win Rate:            {metrics['win_rate']:>8.2f}%")
    print(f"  Information Ratio:   {metrics['information_ratio']:>8.3f}")
    print(f"  Profit Factor:       {metrics['profit_factor']:>8.2f}  (profit/loss ratio)")
    print(f"  Total Trades:        {metrics['total_trades']:>8d}")
    print(f"  Winning Trades:      {metrics['winning_trades']:>8d}")
    print(f"  Losing Trades:       {metrics['losing_trades']:>8d}")
    print(f"  Total Commission:    {metrics['total_commission']:>8.2f} USDT")
    print(f"  Total Slippage:      {metrics['total_slippage']:>8.2f} USDT")
    print(f"  Final Account Value: {metrics['final_value']:>10.2f} USDT")
    print("="*60 + "\n")

    # Auto-write to backtest_cache.json (read by the GUI)
    _save_cache(metrics)


def _save_cache(metrics: Dict):
    """
    Write backtest results to backtest_cache.json for the GUI module to read.
    This file is auto-generated by `python main.py --backtest`; do not edit manually.
    """
    cache_path = os.path.join(os.path.dirname(__file__), "..", "backtest_cache.json")
    cache_path = os.path.abspath(cache_path)

    # Only serialise JSON-safe fields (trades may contain inf)
    safe_metrics = {}
    for k, v in metrics.items():
        if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
            safe_metrics[k] = None
        elif isinstance(v, list):
            # equity_curve / benchmark_curve / trades written as-is
            safe_metrics[k] = v
        else:
            safe_metrics[k] = v

    # profit_factor may be inf
    if isinstance(safe_metrics.get("profit_factor"), float):
        if math.isinf(safe_metrics["profit_factor"]):
            safe_metrics["profit_factor"] = 999.99

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(safe_metrics, f, ensure_ascii=False)
        print("[Backtest] Results written to backtest_cache.json (read by GUI; do not edit manually)")
    except Exception as e:
        print(f"[Warning] Failed to write backtest_cache.json: {e}")


if __name__ == "__main__":
    # Test: run backtest on synthetic data
    import random
    random.seed(42)

    print("Generating synthetic data...")
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
