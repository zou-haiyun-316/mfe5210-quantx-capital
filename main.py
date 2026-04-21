"""
Quant X Capital — 主程序入口
一键运行完整的量化交易系统（数据获取 → 回测 → Paper Trading）

使用方式：
  python main.py              # 完整流程（回测完成后会暂停，按 Enter 继续 Paper Trading）
  python main.py --no-pause   # 完整流程，全自动运行，无需人工按 Enter
  python main.py --backtest   # 只跑回测（自动写入 backtest_cache.json 供 GUI 读取）
  python main.py --live       # 只跑实时模拟交易
  python main.py --fetch      # 只获取历史数据

注意：
  - --backtest 运行完成后会自动写入 backtest_cache.json，GUI 读取此文件展示结果。
  - 数据来源：data-api.binance.vision（Binance 公开镜像 API，直接 urllib 调用，无需 ccxt）
"""

import sys
import os
import time
import argparse

# 把项目根目录加到路径
sys.path.insert(0, os.path.dirname(__file__))

from database.db_manager   import init_database
from data.data_fetcher     import fetch_and_store_klines, get_historical_data_for_backtest, fetch_latest_price, check_data_quality
from strategy.backtester   import Backtester, print_backtest_report
from strategy.multi_factor_strategy import get_latest_signal
from execution.paper_trader import PaperTrader, TCAAnalyzer


def run_backtest():
    """步骤1：用历史数据回测策略"""
    print("\n" + "="*60)
    print("   步骤 1/3：运行回测（历史数据验证策略）")
    print("="*60)

    data = get_historical_data_for_backtest("BTC/USDT", "1m")
    if len(data) < 50:
        print(f"数据量不足（只有 {len(data)} 条），请先获取数据")
        return None

    print(f"使用 {len(data)} 根K线数据进行回测...")
    backtester = Backtester(initial_cash=50000.0)
    metrics    = backtester.run(data)
    print_backtest_report(metrics)
    return metrics


def run_live_trading(rounds: int = 10):
    """步骤2：模拟实时交易（Paper Trading）"""
    print("\n" + "="*60)
    print("   步骤 2/3：Paper Trading（模拟实时交易）")
    print("="*60)

    trader = PaperTrader(initial_cash=50000.0)
    symbol = "BTC/USDT"

    # 存储历史K线用于计算信号
    price_history = []

    print(f"\n开始模拟交易，共运行 {rounds} 轮（每轮间隔5秒）...")
    print("（实际部署时改为无限循环，按 Ctrl+C 停止）\n")

    for i in range(rounds):
        try:
            # 获取最新价格
            current_price = fetch_latest_price(symbol)

            # 构建用于信号计算的数据
            price_history.append({
                "open_time": int(time.time() * 1000),
                "open":   current_price,
                "high":   current_price,
                "low":    current_price,
                "close":  current_price,
                "volume": 10.0,
            })
            # 最多保留最近100根用于计算指标
            if len(price_history) > 100:
                price_history = price_history[-100:]

            # 生成信号
            signal = get_latest_signal(price_history)

            print(f"[轮次 {i+1:02d}/{rounds}] BTC: {current_price:,.2f} USDT | "
                  f"得分: {signal['score'] or 0:.3f} | 信号: {signal['signal'].upper()}")

            # 执行信号
            trader.execute_signal(signal, current_price, symbol)

            # 每5轮打印一次账户状态
            if (i + 1) % 5 == 0:
                summary = trader.get_account_summary(current_price, symbol)
                print(f"\n  账户状态：总值 {summary['total_value']:,.2f} USDT | "
                      f"收益 {summary['total_pnl']:+.2f} USDT ({summary['total_return']:+.2f}%)\n")

            time.sleep(5)  # 等待5秒再获取下一个价格

        except KeyboardInterrupt:
            print("\n用户停止交易")
            break
        except Exception as e:
            print(f"[错误] {e}，5秒后继续...")
            time.sleep(5)

    # 最终账户状态
    final_price   = fetch_latest_price(symbol)
    final_summary = trader.get_account_summary(final_price, symbol)
    print(f"\n[交易结束] 最终账户总值：{final_summary['total_value']:,.2f} USDT")
    print(f"           总收益：{final_summary['total_pnl']:+.2f} USDT ({final_summary['total_return']:+.2f}%)")

    return trader


def run_tca(trader: PaperTrader):
    """步骤3：TCA 交易成本分析"""
    print("\n" + "="*60)
    print("   步骤 3/3：TCA 交易成本分析")
    print("="*60)

    tca = TCAAnalyzer()
    report = tca.analyze(trader.order_history)

    if report:
        print(f"  总手续费：    {report['total_commission']:.4f} USDT")
        print(f"  预估滑点：    {report['estimated_slippage']:.4f} USDT")
        print(f"  总交易成本：  {report['total_cost']:.4f} USDT")
        print(f"  成本占收益比：{report['cost_as_pct_of_pnl']:.2f}%")
        print(f"  总交易次数：  {report['num_trades']} 笔")
    else:
        print("  暂无交易记录，TCA 无法计算")


def main():
    parser = argparse.ArgumentParser(description="Quant X Capital 量化交易系统")
    parser.add_argument("--backtest",  action="store_true", help="只运行回测")
    parser.add_argument("--live",      action="store_true", help="只运行实时模拟交易")
    parser.add_argument("--fetch",     action="store_true", help="只获取数据")
    parser.add_argument("--rounds",    type=int, default=10, help="实时交易轮数")
    parser.add_argument("--no-pause",  action="store_true",
                        help="完整流程不暂停，全自动运行（适合脚本调用）")
    args = parser.parse_args()

    print("\n🚀 Quant X Capital — 量化交易系统启动")
    print("="*60)

    # 初始化数据库
    init_database()

    # 只获取数据
    if args.fetch:
        print("\n获取 BTC/USDT 最近7天的1分钟K线数据...")
        fetch_and_store_klines("BTC/USDT", "1m", days=7)
        check_data_quality("BTC/USDT", "1m")
        return

    # 只回测
    if args.backtest:
        run_backtest()
        return

    # 只实时交易
    if args.live:
        trader = run_live_trading(rounds=args.rounds)
        run_tca(trader)
        return

    # 默认：完整流程
    print("\n将按以下顺序执行：")
    print("  1. 获取历史数据（如果数据库已有数据则跳过）")
    print("  2. 回测策略")
    print("  3. Paper Trading（模拟实时交易 10 轮）")
    print("  4. TCA 成本分析")
    print("\n提示：同时在另一个终端运行 GUI：")
    print("  streamlit run gui/dashboard.py")

    # 步骤0：检查数据
    data = get_historical_data_for_backtest("BTC/USDT", "1m")
    if len(data) < 50:
        print("\n[数据] 数据库中数据不足，开始抓取...")
        fetch_and_store_klines("BTC/USDT", "1m", days=3)

    # 步骤1：回测
    run_backtest()

    # 步骤2：实时模拟
    # 使用 --no-pause 时跳过人工确认，实现真正的全自动运行
    if not getattr(args, "no_pause", False):
        input("\n回测完成！按 Enter 开始 Paper Trading...（或使用 --no-pause 跳过）")
    else:
        print("\n[自动模式] 回测完成，直接进入 Paper Trading...")
    trader = run_live_trading(rounds=args.rounds)

    # 步骤3：TCA
    run_tca(trader)

    print("\n✅ 全部完成！在浏览器中查看 Dashboard：")
    print("   streamlit run gui/dashboard.py")


if __name__ == "__main__":
    main()
