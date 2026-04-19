"""
Quant X Capital — Streamlit Trading Dashboard
运行方式：streamlit run gui/dashboard.py（从项目根目录）
"""

import sys
import os
import json

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
# ================================================================

CACHE_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backtest_cache.json")
)

@st.cache_data(ttl=3600)
def load_backtest_cache():
    """从 backtest_cache.json 读取预计算结果，不再实时跑回测。"""
    if not os.path.exists(CACHE_FILE):
        return None, []
    try:
        with open(CACHE_FILE, "r") as f:
            metrics = json.load(f)
        equity = metrics.get("equity_curve", [])
        return metrics, equity
    except Exception:
        return None, []


def downsample(data: list, n: int = 400) -> list:
    """将列表均匀降采样到最多 n 个点，避免绘图卡顿。"""
    if len(data) <= n:
        return data
    step = len(data) / n
    return [data[int(i * step)] for i in range(n)]


# ================================================================
# 实时监控页面
# ================================================================

if mode == "实时监控":
    st.title("📈 Quant X Capital — 实时监控")
    init_database()

    # --- 账户指标卡片 ---
    account_history = get_account_history()

    if account_history:
        latest       = account_history[-1]
        first        = account_history[0]
        total_value  = latest["total_value"]
        initial      = first["total_value"]
        total_pnl    = total_value - initial
        total_return = (total_pnl / initial * 100) if initial > 0 else 0
        cash         = latest["cash"]
    else:
        total_value = 50000.0
        total_pnl   = 0.0
        total_return = 0.0
        cash        = 50000.0

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
        position_value = max(total_value - cash, 0)
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
        else:
            metrics, equity_curve = load_backtest_cache()
            if equity_curve:
                st.info("ℹ️ 显示的是回测权益曲线（Paper Trading 数据积累后自动切换为实盘曲线）")
                sampled = downsample(equity_curve, 400)   # ← 关键：400点而非10106点
                df_eq = pd.DataFrame({"账户价值 (USDT)": sampled})
                st.line_chart(df_eq, color="#00ff88")
            else:
                st.info("账户价值曲线将在交易开始后显示")

    with col_right:
        st.subheader("🪙 当前持仓")
        positions = get_current_positions()
        if positions:
            for pos in positions:
                st.markdown(f"**{pos['symbol']}**")
                ca, cb = st.columns(2)
                ca.metric("持有数量", f"{pos['qty']:.6f}")
                cb.metric("浮动盈亏",
                          f"{pos['unrealized_pnl']:+.2f} USDT",
                          delta_color="normal")
                st.caption(f"平均成本：{pos['avg_cost']:.2f} USDT")
        else:
            st.info("当前空仓（无持仓）")
            st.markdown("**BTC/USDT**：0 BTC  \n等待买入信号...")

    st.divider()

    # --- 最近交易记录 ---
    st.subheader("📋 最近交易记录（Paper Trading）")
    orders = get_recent_orders(limit=20)

    def color_side(val):
        if val in ("buy", "买入"):
            return "background-color: #003300; color: #00ff00"
        elif val in ("sell", "卖出"):
            return "background-color: #330000; color: #ff4444"
        return ""

    if orders:
        df_orders = pd.DataFrame(orders)
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
        # 格式化数字
        if "价格(USDT)" in df_display.columns:
            df_display["价格(USDT)"] = df_display["价格(USDT)"].apply(lambda x: f"{x:,.2f}")
        if "数量(BTC)" in df_display.columns:
            df_display["数量(BTC)"] = df_display["数量(BTC)"].apply(lambda x: f"{x:.6f}")
        st.dataframe(
            df_display.style.map(color_side, subset=["方向"]),
            use_container_width=True,
            height=min(300, 38 + len(df_display) * 35),
        )
        st.caption(f"共 {len(orders)} 笔 Paper Trading 成交记录")
    else:
        st.info("暂无交易记录")


# ================================================================
# 回测分析页面
# ================================================================

elif mode == "回测分析":
    st.title("🔬 回测绩效分析")

    metrics, equity_curve = load_backtest_cache()

    if metrics is None:
        st.error("未找到回测缓存，请运行：`python main.py --backtest`")
        st.stop()

    # ---- 核心指标 ----
    total_return = metrics.get("total_return", 0)
    sharpe       = metrics.get("sharpe_ratio", 0)
    max_dd       = metrics.get("max_drawdown", 0)
    win_rate     = metrics.get("win_rate", 0)
    profit_fac   = metrics.get("profit_factor", 0)
    total_trades = metrics.get("total_trades", 0)
    final_val    = metrics.get("final_value", 50000)
    net_profit   = final_val - 50000

    # 百分比格式化
    def pct(v):
        return f"{v * 100:.2f}%" if abs(v) < 100 else f"{v:.2f}%"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📈 总收益率",    pct(total_return),  f"净盈利 {net_profit:+.2f} USDT")
        st.metric("🏆 夏普比率",    f"{sharpe:.2f}",    "优秀 > 1.0" if sharpe > 1 else "待优化")
    with col2:
        st.metric("📉 最大回撤",    pct(max_dd),        "风险可控" if abs(max_dd) < 0.1 else "注意风险",
                  delta_color="inverse")
        st.metric("🎯 胜率",        pct(win_rate),      f"共 {total_trades} 笔交易")
    with col3:
        st.metric("💹 盈亏比",      f"{profit_fac:.2f}",
                  "盈多亏少" if profit_fac > 1 else "亏多盈少",
                  delta_color="normal" if profit_fac > 1 else "inverse")
        st.metric("💰 期末资金",    f"{final_val:,.2f} USDT")

    st.divider()

    # ---- 权益曲线（降采样避免卡顿）----
    st.subheader("📉 权益曲线（Equity Curve）")
    if equity_curve:
        sampled = downsample(equity_curve, 400)          # ← 400点，流畅
        df_eq = pd.DataFrame({
            "策略权益 (USDT)":     sampled,
            "基准-持有不动 (USDT)": [50000.0] * len(sampled),
        })
        st.line_chart(df_eq, color=["#00ff88", "#666666"])
        st.caption(f"绿色 = 策略权益曲线 | 灰色 = 持有不动基准（50,000 USDT）"
                   f" | 数据点数：{len(sampled)}（原始 {len(equity_curve)} 点降采样）")
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
                     "夏普比率", "盈亏比"],
            "数值": [
                "50,000.00 USDT",
                f"{final_val:,.2f} USDT",
                f"{net_profit:+.2f} USDT",
                pct(total_return),
                f"{sharpe:.2f}",
                f"{profit_fac:.2f}",
            ],
        }
        st.dataframe(pd.DataFrame(perf_data), use_container_width=True, hide_index=True)

    with col_b:
        st.markdown("**⚠️ 风险指标**")
        risk_data = {
            "指标": ["最大回撤", "胜率", "总交易次数",
                     "回测周期", "数据频率", "手续费率"],
            "数值": [
                pct(max_dd),
                pct(win_rate),
                f"{total_trades} 笔",
                "2025年4月12日—19日（7天）",
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

    **参数优化：** 通过网格搜索（36种组合）在真实数据上择优，买入阈值=0.4时夏普比率最高。

    **风控规则：**
    - 手续费：0.1%（Binance 现货标准费率）
    - 最大回撤止损：15%（超过则停止交易）
    """)


# ================================================================
# TCA 成本分析页面
# ================================================================

elif mode == "TCA 成本分析":
    st.title("💸 TCA — 交易成本分析")

    st.markdown("""
    **TCA（Transaction Cost Analysis）** 帮助你了解交易中产生的各项隐性成本，
    这些成本会直接影响策略的实际盈利能力。
    """)

    metrics, _ = load_backtest_cache()

    if metrics is not None:
        total_trades     = metrics.get("total_trades", 0)
        final_val        = metrics.get("final_value", 50000)
        net_profit       = final_val - 50000
        avg_trade_size   = 50000 * 0.95
        commission_rate  = 0.001
        total_commission = avg_trade_size * commission_rate * total_trades
        est_slippage     = total_commission * 0.3
        total_cost       = total_commission + est_slippage
        cost_vs_profit   = (total_cost / abs(net_profit) * 100) if net_profit != 0 else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💰 手续费合计",
                      f"{total_commission:.2f} USDT",
                      f"{total_trades} 笔 × 0.1%",
                      delta_color="inverse")
        with col2:
            st.metric("📉 预估滑点",
                      f"{est_slippage:.2f} USDT",
                      "成交额 × 0.03% 估算",
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
    orders = get_recent_orders(limit=50)
    if orders:
        df_o = pd.DataFrame(orders)
        df_o["成交额(USDT)"]   = df_o["price"] * df_o["qty"]
        df_o["手续费(USDT)"]   = df_o["成交额(USDT)"] * 0.001
        df_o["预估滑点(USDT)"] = df_o["成交额(USDT)"] * 0.0003
        df_o["总成本(USDT)"]   = df_o["手续费(USDT)"] + df_o["预估滑点(USDT)"]
        show = df_o[["order_id", "side", "price", "qty",
                      "成交额(USDT)", "手续费(USDT)", "预估滑点(USDT)", "总成本(USDT)"]].copy()
        show = show.rename(columns={"order_id": "订单号", "side": "方向",
                                    "price": "价格", "qty": "数量"})
        for col in ["成交额(USDT)", "手续费(USDT)", "预估滑点(USDT)", "总成本(USDT)"]:
            show[col] = show[col].apply(lambda x: f"{x:.2f}")
        st.dataframe(show, use_container_width=True)
    else:
        st.info("暂无成交记录")

    st.divider()

    st.subheader("💡 成本概念解释")
    n_orders = len(orders) if orders else 0
    st.markdown(f"""
    | 成本类型 | 解释 | 本策略影响 |
    |---------|------|-----------|
    | **手续费** | 每次交易交给交易所的佣金 | Binance现货 0.1%，较低 |
    | **滑点** | 想在100元成交，实际成交价差额 | 模拟交易约0.03%估算 |
    | **冲击成本** | 大单把价格买上去的成本 | BTC流动性极好，基本忽略 |
    | **时机成本** | 信号到下单之间的价格变动 | 1分钟K线，约1根K线延迟 |

    > **结论：** 本策略交易频率较低（7天仅 {n_orders} 笔），手续费总额可控，
    > 成本对整体盈利的影响较小。
    """)
