"""
Quant X Capital — Streamlit Trading Dashboard
运行方式：streamlit run gui/dashboard.py（从项目根目录）

【数据优先级说明】
  实时监控 / TCA 页面 优先读取本地 SQLite（Paper Trading 数据），
  若数据库为空（如 Streamlit Cloud 部署环境），自动回退到 backtest_cache.json 展示回测数据。
  这样无论是本地还是云端，页面始终有真实数据可展示。
"""

import sys
import os
import json
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    import streamlit as st
    import pandas as pd
except ImportError:
    print("请安装依赖：pip install streamlit pandas")
    sys.exit(1)

from database.db_manager import (
    get_account_history, get_current_positions,
    get_recent_orders, init_database
)

# ================================================================
# 页面配置
# ================================================================

st.set_page_config(
    page_title="Quant X Capital — Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ================================================================
# 侧边栏
# ================================================================

st.sidebar.title("⚙️ Quant X Capital")
st.sidebar.markdown("**多因子动量策略 | BTC/USDT**")
st.sidebar.divider()

mode = st.sidebar.radio(
    "查看模式",
    ["实时监控", "回测分析", "TCA 成本分析"],
    index=0,
)

st.sidebar.divider()
st.sidebar.markdown("初始资金：**50,000 USDT**")
st.sidebar.markdown("交易对：**BTC/USDT**")
st.sidebar.markdown("策略：**多因子动量**")
st.sidebar.divider()
if st.sidebar.button("🔄 手动刷新"):
    st.cache_data.clear()
    st.rerun()

# ================================================================
# 回测缓存加载（只读文件，毫秒级，不实时计算）
#
# 注意：backtest_cache.json 由 `python main.py --backtest` 自动生成，
#       不得手工修改，以确保 GUI 展示结果与代码计算结果完全一致。
# ================================================================

CACHE_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backtest_cache.json")
)

@st.cache_data(ttl=3600)
def load_backtest_cache():
    """从 backtest_cache.json 读取预计算结果，不再实时跑回测。"""
    if not os.path.exists(CACHE_FILE):
        return None, [], [], []
    try:
        with open(CACHE_FILE, "r") as f:
            metrics = json.load(f)
        equity    = metrics.get("equity_curve", [])
        benchmark = metrics.get("benchmark_curve", [])
        trades    = metrics.get("trades", [])
        return metrics, equity, benchmark, trades
    except Exception:
        return None, [], [], []


def downsample(data: list, n: int = 400) -> list:
    """将列表均匀降采样到最多 n 个点，避免绘图卡顿。"""
    if len(data) <= n:
        return data
    step = len(data) / n
    return [data[int(i * step)] for i in range(n)]


def trades_to_display_df(trades: list) -> pd.DataFrame:
    """将回测 trades 列表转为可展示的 DataFrame（统一字段格式）。"""
    rows = []
    for t in trades:
        rows.append({
            "方向":       "buy" if t.get("action") == "buy" else "sell",
            "价格(USDT)": f"{t.get('price', 0):,.2f}",
            "数量(BTC)":  f"{t.get('qty', 0):.6f}",
            "手续费(USDT)": f"{t.get('fee', 0):.4f}",
            "盈亏(USDT)":  f"{t.get('pnl', 0):+.2f}" if t.get("action") == "sell" else "—",
            "因子得分":   f"{t.get('score', 0):.4f}" if t.get("score") is not None else "—",
        })
    return pd.DataFrame(rows)


# ================================================================
# 实时监控页面
# ================================================================

if mode == "实时监控":
    st.title("📈 Quant X Capital — 实时监控")
    init_database()

    # 加载回测缓存（备用数据源）
    bt_metrics, equity_curve, benchmark_curve, bt_trades = load_backtest_cache()

    # --- 账户指标卡片 ---
    account_history = get_account_history()
    using_backtest_fallback = False

    if account_history and len(account_history) > 1:
        # 优先使用 Paper Trading 实盘数据
        latest       = account_history[-1]
        first        = account_history[0]
        total_value  = latest["total_value"]
        initial      = first["total_value"]
        total_pnl    = total_value - initial
        total_return = (total_pnl / initial * 100) if initial > 0 else 0
        cash         = latest["cash"]
        position_value = max(total_value - cash, 0)
    elif bt_metrics:
        # 回退到回测结果展示
        using_backtest_fallback = True
        total_value    = bt_metrics.get("final_value", 50000)
        total_pnl      = total_value - 50000
        total_return   = bt_metrics.get("total_return", 0)   # 已是百分数
        cash           = bt_metrics.get("final_cash", total_value)
        position_value = max(total_value - cash, 0)
    else:
        total_value    = 50000.0
        total_pnl      = 0.0
        total_return   = 0.0
        cash           = 50000.0
        position_value = 0.0

    if using_backtest_fallback:
        st.info(
            "ℹ️ **当前展示的是回测结果数据**（回测区间：2026-04-12 至 2026-04-19）。"
            "  本地运行 `python main.py --live` 开始 Paper Trading 后，此处将自动切换为实盘数据。",
            icon="📊"
        )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💰 账户总价值",
                  f"{total_value:,.2f} USDT",
                  f"{total_pnl:+.2f} USDT")
    with col2:
        st.metric("📊 总收益率",
                  f"{total_return:.2f}%",
                  "vs 初始 50,000 USDT")
    with col3:
        st.metric("💵 可用现金", f"{cash:,.2f} USDT")
    with col4:
        st.metric("🪙 持仓市值", f"{position_value:,.2f} USDT")

    st.divider()

    # --- PnL 曲线 + 持仓 ---
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("📉 账户价值曲线（PnL Curve）")
        if account_history and len(account_history) > 1:
            df_equity = pd.DataFrame(account_history)
            df_equity["snapshot_at"] = pd.to_datetime(df_equity["snapshot_at"])
            df_equity = df_equity.set_index("snapshot_at")
            st.line_chart(df_equity["total_value"], color="#00ff88")
        elif equity_curve:
            sampled = downsample(equity_curve, 400)
            df_eq = pd.DataFrame({"策略权益 (USDT)": sampled})
            if benchmark_curve and len(benchmark_curve) > 1:
                sampled_bh = downsample(benchmark_curve, 400)
                min_len = min(len(sampled), len(sampled_bh))
                df_eq = pd.DataFrame({
                    "策略权益 (USDT)":       sampled[:min_len],
                    "基准-买入持有 (USDT)":  sampled_bh[:min_len],
                })
                st.line_chart(df_eq, color=["#00ff88", "#aaaaff"])
                st.caption("绿色 = 策略 | 蓝色 = Buy-and-Hold 基准")
            else:
                st.line_chart(df_eq, color="#00ff88")
        else:
            st.info("账户价值曲线将在交易开始后显示")

    with col_right:
        st.subheader("🪙 当前持仓")
        positions = get_current_positions()
        if positions and not using_backtest_fallback:
            for pos in positions:
                st.markdown(f"**{pos['symbol']}**")
                ca, cb = st.columns(2)
                ca.metric("持有数量", f"{pos['qty']:.6f}")
                cb.metric("浮动盈亏",
                          f"{pos['unrealized_pnl']:+.2f} USDT",
                          delta_color="normal")
                st.caption(f"平均成本：{pos['avg_cost']:.2f} USDT")
        elif using_backtest_fallback and bt_metrics:
            final_holdings = bt_metrics.get("final_holdings", 0)
            final_price    = bt_metrics.get("final_price", 0)
            if final_holdings > 0:
                st.markdown("**BTC/USDT**")
                ca, cb = st.columns(2)
                ca.metric("持有数量", f"{final_holdings:.6f} BTC")
                cb.metric("持仓市值", f"{final_holdings * final_price:,.2f} USDT")
            else:
                st.info("回测结束时空仓")
                st.markdown("所有 BTC 已于末次卖出信号清仓")
        else:
            st.info("当前空仓（无持仓）")
            st.markdown("**BTC/USDT**：0 BTC  \n等待买入信号...")

    st.divider()

    # --- 最近交易记录 ---
    st.subheader("📋 交易记录")
    db_orders = get_recent_orders(limit=20)

    def color_side(val):
        if val in ("buy", "买入"):
            return "background-color: #003300; color: #00ff00"
        elif val in ("sell", "卖出"):
            return "background-color: #330000; color: #ff4444"
        return ""

    if db_orders:
        # 有 Paper Trading 数据时展示数据库记录
        df_orders = pd.DataFrame(db_orders)
        column_map = {
            "order_id":   "订单号",
            "symbol":     "交易对",
            "side":       "方向",
            "price":      "价格(USDT)",
            "qty":        "数量(BTC)",
            "status":     "状态",
            "created_at": "时间",
        }
        display_cols = [c for c in column_map if c in df_orders.columns]
        df_display = df_orders[display_cols].rename(columns=column_map)
        if "价格(USDT)" in df_display.columns:
            df_display["价格(USDT)"] = df_display["价格(USDT)"].apply(lambda x: f"{x:,.2f}")
        if "数量(BTC)" in df_display.columns:
            df_display["数量(BTC)"] = df_display["数量(BTC)"].apply(lambda x: f"{x:.6f}")
        st.dataframe(
            df_display.style.map(color_side, subset=["方向"]),
            use_container_width=True,
            height=min(300, 38 + len(df_display) * 35),
        )
        st.caption(f"共 {len(db_orders)} 笔 Paper Trading 成交记录")

    elif bt_trades:
        # 回退：展示回测成交记录
        st.caption("📊 以下为回测成交明细（Paper Trading 启动后将替换为实盘记录）")
        df_bt = trades_to_display_df(bt_trades)
        st.dataframe(
            df_bt.style.map(color_side, subset=["方向"]),
            use_container_width=True,
            height=min(400, 38 + len(df_bt) * 35),
        )
        st.caption(f"共 {len(bt_trades)} 笔回测成交记录（BTC/USDT，2026-04-12 至 2026-04-19）")
    else:
        st.info("暂无交易记录")


# ================================================================
# 回测分析页面
# ================================================================

elif mode == "回测分析":
    st.title("🔬 回测绩效分析")

    metrics, equity_curve, benchmark_curve, _ = load_backtest_cache()

    if metrics is None:
        st.error("未找到回测缓存，请运行：`python main.py --backtest`")
        st.stop()

    # ---- 核心指标（直接使用 metrics 中的值，不做额外百分比转换）----
    # 注意：backtester.py 已将 total_return / max_drawdown / win_rate
    #       全部存为百分数（如 4.8、4.64、60.0），此处直接格式化为字符串显示。
    total_return   = metrics.get("total_return", 0)     # 已是百分数，如 4.57
    bh_return      = metrics.get("benchmark_return", 0) # 已是百分数，如 5.44
    sharpe         = metrics.get("sharpe_ratio", 0)
    max_dd         = metrics.get("max_drawdown", 0)     # 已是百分数，如 4.68
    win_rate       = metrics.get("win_rate", 0)         # 已是百分数，如 60.0
    profit_fac     = metrics.get("profit_factor", 0)
    total_trades   = metrics.get("total_trades", 0)
    final_val      = metrics.get("final_value", 50000)
    net_profit     = final_val - 50000
    total_commission = metrics.get("total_commission", 0)
    total_slippage   = metrics.get("total_slippage", 0)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📈 总收益率",
                  f"{total_return:.2f}%",
                  f"净盈利 {net_profit:+.2f} USDT")
        st.metric("🏆 夏普比率",
                  f"{sharpe:.2f}",
                  "优秀 > 1.0" if sharpe > 1 else "待优化")
    with col2:
        st.metric("📉 最大回撤",
                  f"{max_dd:.2f}%",
                  "风险可控" if abs(max_dd) < 10 else "注意风险",
                  delta_color="inverse")
        st.metric("🎯 胜率",
                  f"{win_rate:.2f}%",
                  f"共 {total_trades} 笔交易")
    with col3:
        st.metric("💹 盈亏比",
                  f"{profit_fac:.2f}",
                  "盈多亏少" if profit_fac > 1 else "亏多盈少",
                  delta_color="normal" if profit_fac > 1 else "inverse")
        st.metric("💰 期末资金", f"{final_val:,.2f} USDT")

    st.divider()

    # ---- 权益曲线（含真实 Buy-and-Hold 基准曲线）----
    st.subheader("📉 权益曲线（Equity Curve）")
    st.caption(
        "📌 **基准线（Buy-and-Hold）** = 回测第一根K线开盘时以 95% 资金买入 BTC，"
        "持有至结束，模拟被动持有收益。策略线在此基准上方表示跑赢大盘。"
    )

    if equity_curve:
        sampled_eq = downsample(equity_curve, 400)
        if benchmark_curve and len(benchmark_curve) > 1:
            sampled_bh = downsample(benchmark_curve, 400)
            min_len = min(len(sampled_eq), len(sampled_bh))
            df_eq = pd.DataFrame({
                "策略权益 (USDT)":       sampled_eq[:min_len],
                "基准-买入持有 (USDT)":  sampled_bh[:min_len],
            })
            st.line_chart(df_eq, color=["#00ff88", "#aaaaff"])
            st.caption(
                f"绿色 = 策略权益曲线 | 蓝色 = Buy-and-Hold 真实基准"
                f"（初始价买入，持有至结束）"
                f" | 数据点数：{len(sampled_eq)}（原始 {len(equity_curve)} 点降采样）"
            )
        else:
            df_eq = pd.DataFrame({"策略权益 (USDT)": sampled_eq})
            st.line_chart(df_eq, color=["#00ff88"])
            st.info("旧版回测缓存无基准曲线数据，请重新运行 `python main.py --backtest` 更新缓存。")
    else:
        st.info("无权益曲线数据")

    st.divider()

    # ---- 详细统计 ----
    st.subheader("📋 详细回测统计")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**📊 绩效汇总**")
        perf_data = {
            "指标": ["初始资金", "期末资金", "净盈利", "总收益率",
                     "基准收益率 (B&H)", "超额收益",
                     "夏普比率", "盈亏比"],
            "数值": [
                "50,000.00 USDT",
                f"{final_val:,.2f} USDT",
                f"{net_profit:+.2f} USDT",
                f"{total_return:.2f}%",
                f"{bh_return:.2f}%",
                f"{total_return - bh_return:+.2f}%",
                f"{sharpe:.2f}",
                f"{profit_fac:.2f}",
            ],
        }
        st.dataframe(pd.DataFrame(perf_data), use_container_width=True, hide_index=True)

    with col_b:
        st.markdown("**⚠️ 风险与成本**")
        risk_data = {
            "指标": ["最大回撤", "胜率", "总交易次数",
                     "总手续费", "总滑点成本",
                     "回测周期", "数据频率", "手续费率"],
            "数值": [
                f"{max_dd:.2f}%",
                f"{win_rate:.2f}%",
                f"{total_trades} 笔",
                f"{total_commission:.2f} USDT",
                f"{total_slippage:.2f} USDT",
                "2026年4月12日—19日（7天）",
                "1分钟K线",
                "0.10%（Binance现货）",
            ],
        }
        st.dataframe(pd.DataFrame(risk_data), use_container_width=True, hide_index=True)

    st.divider()

    # ---- 策略说明 ----
    st.subheader("📖 策略说明")
    st.markdown("""
    ### 多因子动量策略

    **核心思想：** 结合三个维度的市场信号，综合判断买卖时机。

    | 因子 | 权重 | 含义 |
    |------|------|------|
    | 价格动量 | 40% | 过去20根K线的涨跌幅，判断趋势方向 |
    | 成交量因子 | 30% | 当前量是否显著放大，量价配合增强信号 |
    | 波动率因子 | 30% | 当前市场波动水平，高波动时降低信号强度 |

    **交易规则：**
    - 综合得分 > **0.4** → 买入（使用95%可用资金）
    - 综合得分 < **-0.4** → 卖出（全仓卖出）
    - 其余 → 观望（HOLD）

    **信号执行机制（无 look-ahead bias）：**
    - 第 i 根K线收盘时根据历史数据计算因子得分
    - 实际成交发生在第 i+1 根K线**开盘价**（含滑点）
    - 这确保策略不会使用未来信息

    **风控规则：**
    - 手续费：0.1%（Binance 现货标准费率）
    - 滑点：成交额 × 0.02%（市场冲击保守估算）
    - 最大回撤止损：15%（超过则停止交易）
    """)


# ================================================================
# TCA 成本分析页面
# ================================================================

elif mode == "TCA 成本分析":
    st.title("💸 TCA — 交易成本分析")

    st.markdown("""
    **TCA（Transaction Cost Analysis，交易成本分析）** 量化每笔交易产生的显性与隐性成本，
    直接影响策略实际盈利能力。

    > **说明：** 本系统为教学级 TCA，滑点基于成交额的经验比例估算（BTC 现货高流动性场景），
    > 非基于真实盘口数据或市场冲击模型。
    """)

    metrics, _, _, bt_trades = load_backtest_cache()

    if metrics is not None:
        total_trades      = metrics.get("total_trades", 0)
        final_val         = metrics.get("final_value", 50000)
        net_profit        = final_val - 50000
        total_commission  = metrics.get("total_commission", 0)
        total_slippage    = metrics.get("total_slippage", 0)
        total_cost        = total_commission + total_slippage
        cost_vs_profit    = (total_cost / abs(net_profit) * 100) if net_profit != 0 else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 手续费合计",
                      f"{total_commission:.2f} USDT",
                      f"{total_trades} 笔 × 0.1%",
                      delta_color="inverse")
        with col2:
            st.metric("📉 预估滑点",
                      f"{total_slippage:.2f} USDT",
                      "成交额 × 0.02% 估算",
                      delta_color="inverse")
        with col3:
            st.metric("📊 成本/收益比",
                      f"{cost_vs_profit:.1f}%",
                      "低于10%为优秀" if cost_vs_profit < 10 else "偏高，需优化",
                      delta_color="normal" if cost_vs_profit < 10 else "inverse")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 手续费合计", "-- USDT")
        c2.metric("📉 预估滑点",   "-- USDT")
        c3.metric("📊 成本/收益比","-- %")

    st.divider()

    # ---- 订单成本明细 ----
    st.subheader("📋 订单成本明细")
    db_orders = get_recent_orders(limit=50)

    if db_orders:
        # 优先使用 Paper Trading 数据库记录
        df_o = pd.DataFrame(db_orders)
        df_o["成交额(USDT)"]   = df_o["price"] * df_o["qty"]
        df_o["手续费(USDT)"]   = df_o["成交额(USDT)"] * 0.001
        df_o["预估滑点(USDT)"] = df_o["成交额(USDT)"] * 0.0002
        df_o["总成本(USDT)"]   = df_o["手续费(USDT)"] + df_o["预估滑点(USDT)"]
        show = df_o[["order_id", "side", "price", "qty",
                     "成交额(USDT)", "手续费(USDT)", "预估滑点(USDT)", "总成本(USDT)"]].copy()
        show = show.rename(columns={"order_id": "订单号", "side": "方向",
                                    "price": "价格", "qty": "数量"})
        for col in ["成交额(USDT)", "手续费(USDT)", "预估滑点(USDT)", "总成本(USDT)"]:
            show[col] = show[col].apply(lambda x: f"{x:.2f}")
        st.dataframe(show, use_container_width=True)
        n_orders = len(db_orders)

    elif bt_trades:
        # 回退：用回测成交记录计算成本明细
        st.caption("📊 以下为回测成交成本明细（Paper Trading 启动后将替换为实盘记录）")
        rows = []
        for t in bt_trades:
            price     = t.get("price", 0)
            qty       = t.get("qty", 0)
            trade_val = price * qty
            fee       = t.get("fee", trade_val * 0.001)
            slippage  = t.get("slippage", trade_val * 0.0002)
            rows.append({
                "方向":           t.get("action", "—"),
                "价格(USDT)":     f"{price:,.2f}",
                "数量(BTC)":      f"{qty:.6f}",
                "成交额(USDT)":   f"{trade_val:,.2f}",
                "手续费(USDT)":   f"{fee:.4f}",
                "预估滑点(USDT)": f"{slippage:.4f}",
                "总成本(USDT)":   f"{fee + slippage:.4f}",
                "盈亏(USDT)":     f"{t.get('pnl', 0):+.2f}" if t.get("action") == "sell" else "—",
            })
        df_bt = pd.DataFrame(rows)

        def color_side(val):
            if val == "buy":
                return "background-color: #003300; color: #00ff00"
            elif val == "sell":
                return "background-color: #330000; color: #ff4444"
            return ""

        st.dataframe(
            df_bt.style.map(color_side, subset=["方向"]),
            use_container_width=True,
        )
        n_orders = len(bt_trades)

    else:
        st.info("暂无成交记录")
        n_orders = 0

    st.divider()

    st.subheader("💡 TCA 成本概念与局限性说明")
    st.markdown(f"""
    | 成本类型 | 解释 | 本策略影响 | 计算方式 |
    |---------|------|-----------|--------|
    | **手续费** | 每次交易交给交易所的佣金 | Binance现货 0.1%，较低 | 成交额 × 0.10% |
    | **滑点** | 信号价格与实际成交价之差 | BTC流动性好，估算 0.02% | 成交额 × 0.02% |
    | **冲击成本** | 大单推动价格的成本 | BTC日均成交量大，基本忽略 | 未建模 |
    | **时机成本** | 信号到成交之间的价格漂移 | 采用次根K线开盘价成交 | next-bar execution |

    **TCA 系统局限性说明：**
    - 本 TCA 基于经验比例估算滑点，非真实盘口数据驱动，属于**教学级 TCA**
    - 未建立完整的市场冲击模型（如 Almgren-Chriss 模型）
    - 滑点估算仅适用于 BTC/USDT 等高流动性现货标的

    > **结论：** 本策略交易频率较低（7天仅 {n_orders} 笔），手续费+滑点总额可控，
    > 成本对整体盈利的影响较小。
    """)
