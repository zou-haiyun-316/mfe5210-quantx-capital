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

---

## 回测结果（2026-04-12 至 2026-04-19，真实数据）

| 指标 | 结果 |
|------|------|
| 总收益率 | **+4.96%** |
| 夏普比率 | **6.53** |
| 最大回撤 | **4.64%** |
| 胜率 | **60%** |
| 盈亏比 | **6.06** |
| 最终账户价值 | **52,478 USDT**（初始 50,000） |

---

## 快速开始

### 1. 安装依赖

```bash
pip install ccxt streamlit pandas
```

### 2. 获取历史数据（首次运行必须）

```bash
python main.py --fetch
```

### 3. 运行回测

```bash
python main.py --backtest
```

### 4. 启动 GUI 监控面板

```bash
streamlit run gui/dashboard.py
# 打开浏览器访问 http://localhost:8501
```

### 5. 模拟实时交易

```bash
python main.py --live --rounds 20
```

### 6. 完整流程一键运行

```bash
python main.py
```

---

## 项目结构

```
mfe5210program/
├── main.py                          # 主入口
├── requirements.txt                  # 依赖列表
├── README.md                         # 本文件
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
| 数据来源 | Binance 公开 API | 免费，无需账号 |
| 数据库 | SQLite | 轻量级，本地文件 |
| 回测框架 | 自研 | 无第三方依赖 |
| GUI 框架 | Streamlit | 快速搭建 Web 面板 |
| 数据处理 | pandas | 数据分析 |
| 交易接口 | ccxt | 支持200+交易所 |

---

## 风控规则

- 手续费率：0.1%（Binance 现货标准）
- 单次买入：使用95%可用现金
- 最大回撤止损：账户从峰值回撤超过 **15%** 时自动停止交易

---

## 数据说明

- 数据源：`data-api.binance.vision`（Binance 公开镜像，国内可访问）
- 数据粒度：1分钟 K线（OHLCV）
- 数据库位置：`database/quantx.db`（本地 SQLite 文件）

---

*Quant X Capital © 2026 | MFE5210 CUHK(SZ)*
