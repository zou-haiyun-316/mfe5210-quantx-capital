"""
Quant X Capital — Main Entry Point
One-command execution of the full quantitative trading pipeline
(Data Fetch → Backtest → Paper Trading)

Usage:
  python main.py              # Full pipeline (pauses after backtest; press Enter to continue Paper Trading)
  python main.py --no-pause   # Full pipeline, fully automated, no manual Enter required
  python main.py --backtest   # Run backtest only (auto-writes backtest_cache.json for GUI)
  python main.py --live       # Run paper trading only
  python main.py --fetch      # Fetch historical data only

Notes:
  - --backtest automatically writes results to backtest_cache.json; the GUI reads from this file.
  - Data source: data-api.binance.vision (Binance public mirror API, direct urllib call, no ccxt)
"""

import sys
import os
import time
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from database.db_manager   import init_database
from data.data_fetcher     import fetch_and_store_klines, get_historical_data_for_backtest, fetch_latest_price, check_data_quality
from strategy.backtester   import Backtester, print_backtest_report
from strategy.multi_factor_strategy import get_latest_signal
from execution.paper_trader import PaperTrader, TCAAnalyzer


def run_backtest():
    """Step 1: Backtest strategy on historical data"""
    print("\n" + "="*60)
    print("   Step 1/3: Running Backtest (Historical Data Validation)")
    print("="*60)

    data = get_historical_data_for_backtest("BTC/USDT", "1m")
    if len(data) < 50:
        print(f"Insufficient data ({len(data)} bars). Please fetch data first.")
        return None

    print(f"Running backtest on {len(data)} bars...")
    backtester = Backtester(initial_cash=50000.0)
    metrics    = backtester.run(data)
    print_backtest_report(metrics)
    return metrics


def run_live_trading(rounds: int = 10):
    """Step 2: Paper Trading (simulated live execution)"""
    print("\n" + "="*60)
    print("   Step 2/3: Paper Trading (Simulated Live Execution)")
    print("="*60)

    trader = PaperTrader(initial_cash=50000.0)
    symbol = "BTC/USDT"

    # Store recent candles for signal computation
    price_history = []

    print(f"\nStarting paper trading — {rounds} rounds (5-second interval each)...")
    print("(In production, replace with an infinite loop; press Ctrl+C to stop)\n")

    for i in range(rounds):
        try:
            # Fetch latest price
            current_price = fetch_latest_price(symbol)

            # Build a candle-like record for signal computation
            price_history.append({
                "open_time": int(time.time() * 1000),
                "open":   current_price,
                "high":   current_price,
                "low":    current_price,
                "close":  current_price,
                "volume": 10.0,
            })
            # Keep only the last 100 bars for indicator computation
            if len(price_history) > 100:
                price_history = price_history[-100:]

            # Generate signal
            signal = get_latest_signal(price_history)

            print(f"[Round {i+1:02d}/{rounds}] BTC: {current_price:,.2f} USDT | "
                  f"Score: {signal['score'] or 0:.3f} | Signal: {signal['signal'].upper()}")

            # Execute signal
            trader.execute_signal(signal, current_price, symbol)

            # Print account summary every 5 rounds
            if (i + 1) % 5 == 0:
                summary = trader.get_account_summary(current_price, symbol)
                print(f"\n  Account: Total {summary['total_value']:,.2f} USDT | "
                      f"P&L {summary['total_pnl']:+.2f} USDT ({summary['total_return']:+.2f}%)\n")

            time.sleep(5)

        except KeyboardInterrupt:
            print("\nUser stopped trading.")
            break
        except Exception as e:
            print(f"[Error] {e} — retrying in 5 seconds...")
            time.sleep(5)

    # Final account summary
    final_price   = fetch_latest_price(symbol)
    final_summary = trader.get_account_summary(final_price, symbol)
    print(f"\n[Session End] Final account value: {final_summary['total_value']:,.2f} USDT")
    print(f"              Total P&L: {final_summary['total_pnl']:+.2f} USDT ({final_summary['total_return']:+.2f}%)")

    return trader


def run_tca(trader: PaperTrader):
    """Step 3: TCA — Transaction Cost Analysis"""
    print("\n" + "="*60)
    print("   Step 3/3: TCA — Transaction Cost Analysis")
    print("="*60)

    tca = TCAAnalyzer()
    report = tca.analyze(trader.order_history)

    if report:
        print(f"  Total Commission:    {report['total_commission']:.4f} USDT")
        print(f"  Estimated Slippage:  {report['estimated_slippage']:.4f} USDT")
        print(f"  Total Cost:          {report['total_cost']:.4f} USDT")
        print(f"  Cost as % of P&L:   {report['cost_as_pct_of_pnl']:.2f}%")
        print(f"  Total Trades:        {report['num_trades']}")
    else:
        print("  No trade history available — TCA cannot be computed.")


def main():
    parser = argparse.ArgumentParser(description="Quant X Capital — Algorithmic Trading System")
    parser.add_argument("--backtest",  action="store_true", help="Run backtest only")
    parser.add_argument("--live",      action="store_true", help="Run paper trading only")
    parser.add_argument("--fetch",     action="store_true", help="Fetch historical data only")
    parser.add_argument("--rounds",    type=int, default=10, help="Number of paper trading rounds")
    parser.add_argument("--no-pause",  action="store_true",
                        help="Full pipeline without pause (fully automated, suitable for scripts)")
    args = parser.parse_args()

    print("\nQuant X Capital — Algorithmic Trading System Starting")
    print("="*60)

    # Initialize database
    init_database()

    # Fetch data only
    if args.fetch:
        print("\nFetching BTC/USDT 1-minute candles for the past 7 days...")
        fetch_and_store_klines("BTC/USDT", "1m", days=7)
        check_data_quality("BTC/USDT", "1m")
        return

    # Backtest only
    if args.backtest:
        run_backtest()
        return

    # Paper trading only
    if args.live:
        trader = run_live_trading(rounds=args.rounds)
        run_tca(trader)
        return

    # Default: full pipeline
    print("\nExecution order:")
    print("  1. Fetch historical data (skip if database already has data)")
    print("  2. Run backtest")
    print("  3. Paper Trading (10 rounds of simulated live trading)")
    print("  4. TCA cost analysis")
    print("\nTip: Open the GUI in another terminal simultaneously:")
    print("  streamlit run gui/dashboard.py")

    # Step 0: Check data availability
    data = get_historical_data_for_backtest("BTC/USDT", "1m")
    if len(data) < 50:
        print("\n[Data] Insufficient data in database — fetching now...")
        fetch_and_store_klines("BTC/USDT", "1m", days=3)

    # Step 1: Backtest
    run_backtest()

    # Step 2: Paper Trading
    # When --no-pause is set, skip manual confirmation for fully automated execution
    if not getattr(args, "no_pause", False):
        input("\nBacktest complete! Press Enter to start Paper Trading... (or use --no-pause to skip)")
    else:
        print("\n[Auto mode] Backtest complete — proceeding directly to Paper Trading...")
    trader = run_live_trading(rounds=args.rounds)

    # Step 3: TCA
    run_tca(trader)

    print("\nAll done! View the Dashboard in your browser:")
    print("   streamlit run gui/dashboard.py")


if __name__ == "__main__":
    main()
