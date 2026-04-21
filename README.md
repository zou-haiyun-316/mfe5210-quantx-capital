# Quant X Capital — 多因子动量量化交易系统

> MFE5210 Project | CUHK(SZ) | 2026 Spring

---

## 项目简介

本项目是 **Quant X Capital** 团队为 MFE5210 课程设计的全链路量化交易系统，交易标的为 **BTC/USDT 加密货币现货**，策略核心为**多因子动量策略**，系统涵盖数据管道、策略回测、模拟执行、可视化监控四大模块。

---

## 团队分工

| 成员 | 负责模块 | 核心文件 |
|------|---------|---------|
| 成员 C | 数据库 + 数据抓取管道 | `database/db_manager.py`, `data/data_fetcher.py` |
| 成员 A | 多因子策略 + 回测框架 | `strategy/multi_factor_strategy.py`, `strategy/backtester.py` |
| 成员 B | 模拟交易执行 + 风控 + TCA | `execution/paper_trader.py` |
| 成员 D | GUI 监控面板 + 项目整合 | `gui/dashboard.py`, `main.py` |

---

## 策略说明

### 多因子动量策略

结合三个维度的市场信号，综合打分决定买卖：

| 因子 | 权重 | 计算方式 |
|------|------|---------|
| 价格动量 | 40% | 过去20根K线的涨跌幅，正值=上涨趋势 |
| 成交量因子 | 30% | 当前成交量 / 20根K线均量，量价配合加分 |
| 波动率因子 | 30% | 收益率标准差，高波动时降低信号强度 |

**交易规则：**
- 综合得分 > **0.4** → 买入（动用95%可用资金）
- 综合得分 < **-0.4** → 全仓卖出
- 其余 → 观望

**信号执行机制（无 look-ahead bias）：**
- 第 i 根K线收盘时计算因子得分生成信号
- 实际成交发生在第 i+1 根K线**开盘价**（含0.02%滑点）
- 确保策略不使用未来信息

---

## 回测结果

> **回测区间：2026-04-12 至 2026-04-19（7天，BTC/USDT 1分钟K线真实数据）**
>
> 回测结果由 `python main.py --backtest` 自动生成并写入 `backtest_cache.json`，
> GUI 从此文件读取展示，确保数据一致。

| 指标 | 策略结果 | 基准（Buy-and-Hold） |
|------|----------|---------------------|
| 总收益率 | 见运行输出 | 见运行输出 |
| 夏普比率 | 见运行输出 | — |
| 最大回撤 | 见运行输出 | — |
| 胜率 | 见运行输出 | — |

> **注意：** 回测指标每次在真实数据上运行后自动更新，本 README 不硬编码具体数值，
> 以避免文档与代码输出不一致。请直接运行 `python main.py --backtest` 查看最新结果。

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 获取历史数据（首次运行必须）

```bash
python main.py --fetch
```

### 3. 运行回测

```bash
python main.py --backtest
```

回测完成后自动写入 `backtest_cache.json`（供 GUI 展示，请勿手工修改）。

### 4. 启动 GUI 监控面板

```bash
streamlit run gui/dashboard.py
# 打开浏览器访问 http://localhost:8501
```

### 5. 模拟实时交易

```bash
python main.py --live --rounds 20
```

### 6. 完整流程运行

```bash
# 含交互确认（回测完成后按 Enter 继续 Paper Trading）
python main.py

# 全自动模式（无需人工按 Enter，适合脚本调用）
python main.py --no-pause
```

---

## 项目结构

```
mfe5210program/
├── main.py                          # 主入口
├── requirements.txt                  # 依赖列表
├── README.md                         # 本文件
├── backtest_cache.json               # 回测结果缓存（由 --backtest 自动生成）
│
├── database/
│   └── db_manager.py               # SQLite 数据库（5张表 + 所有接口）
│
├── data/
│   └── data_fetcher.py             # Binance 数据抓取管道
│
├── strategy/
│   ├── multi_factor_strategy.py    # 多因子策略（信号生成）
│   └── backtester.py               # 回测引擎（绩效指标计算）
│
├── execution/
│   └── paper_trader.py             # 模拟交易 + 风控 + TCA 分析
│
└── gui/
    └── dashboard.py                # Streamlit 实时监控面板
```

---

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| 编程语言 | Python 3.10+ | 主要语言 |
| 数据来源 | Binance 公开 API | 直接调用 `data-api.binance.vision`，免费，无需账号 |
| 数据库 | SQLite | 轻量级，本地文件 |
| 回测框架 | 自研 | 无第三方依赖，纯 Python 实现 |
| GUI 框架 | Streamlit | 快速搭建 Web 面板 |
| 数据处理 | pandas | 数据分析 |

> **注意：** 数据抓取模块直接使用 Python 标准库 `urllib` 调用 Binance REST API，
> 不依赖 ccxt 库（ccxt 未作为核心实现）。

---

## 风控规则

- 手续费率：0.1%（Binance 现货标准）
- 滑点估算：0.02%（高流动性现货场景保守估算）
- 单次买入：使用95%可用现金
- 最大回撤止损：账户从峰值回撤超过 **15%** 时自动停止交易

---

## TCA 说明

本项目实现了**基础版 TCA（Transaction Cost Analysis）**，包括：

| 成本项 | 计算方式 | 备注 |
|--------|---------|------|
| 手续费 | 成交额 × 0.10% | Binance 现货费率 |
| 滑点 | 成交额 × 0.02% | 经验比例估算，非盘口数据驱动 |

**局限性说明：**
- 滑点基于经验比例，非真实成交数据或市场冲击模型（如 Almgren-Chriss）
- 未模拟部分成交、撤单、挂单等完整订单生命周期
- 适合课程原型，非生产级执行系统

---

## 数据说明

- 数据源：`data-api.binance.vision`（Binance 公开镜像，国内可访问）
- 数据粒度：1分钟 K线（OHLCV）
- 数据库位置：`database/quantx.db`（本地 SQLite 文件）

---

*Quant X Capital © 2026 | MFE5210 CUHK(SZ)*
