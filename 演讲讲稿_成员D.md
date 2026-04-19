# 成员 D 演讲讲稿（15分钟）
> Quant X Capital — MFE5210 项目答辩

---

## 【开场 · 0:00–1:00】封面页

**（镇定走上台，先停顿2秒，环视评委，微笑）**

Good afternoon, professors and classmates.

We are **Quant X Capital**.

Today, we're going to show you something different — not just a trading strategy on paper, but a **fully functioning automated trading system** that we built from scratch.

It runs 24/7, reads live market data, makes decisions by itself, and shows you everything on a real-time dashboard.

Let's get started.

---

## 【目录 · 1:00–1:30】

**（切换到目录页）**

Here's the roadmap for today. We have 15 minutes, and I'll walk you through six parts:

First, why we chose crypto and this strategy. Then the strategy itself — how it actually works. Third, the system architecture — how all the pieces fit together. Fourth, our backtesting results with real data. Fifth — and this is my favorite part — a live demo. And finally, a quick TCA analysis and our conclusions.

Let's go.

---

## 【第一部分 · 1:30–2:30】为什么选加密货币？

**（切换到幻灯片3）**

Let me start with the "why."

Why Bitcoin? Why not stocks?

Three reasons.

First, **crypto never sleeps**. Unlike the A-share market that closes at 3pm, Bitcoin trades 24 hours a day, 7 days a week. That's ideal for an intraday strategy — more opportunities, more data.

Second, **the data is completely free**. Binance — the world's largest crypto exchange — provides public APIs with no registration required. We pulled over 10,000 minutes of real price data for free.

Third, **it's a great testing ground**. Crypto markets are volatile, which means if our strategy can survive there, it's robust. High risk, high learning.

As for why multi-factor momentum — I'll let [成员A的名字] explain that in detail. But the short answer is: one signal lies, three signals together are much harder to fake.

---

## 【第二部分 · 2:30–5:30】策略设计

**（切换到幻灯片4，5）**

**（引出成员A做策略介绍，约2–3分钟）**

> [提示：这里由成员A上台介绍三因子策略和参数优化过程，讲完后成员D继续]

Thank you, [成员A]. So to summarize — our strategy generates a score between -1 and +1. Above 0.4, we buy. Below -0.4, we sell. Everything else, we wait.

Those thresholds weren't guessed. We ran a **grid search across 36 parameter combinations** and picked the one with the best Sharpe ratio. Science, not luck.

---

## 【第三部分 · 5:30–7:00】系统架构

**（切换到幻灯片5）**

Now let me show you how the whole system is wired together.

Think of it as a pipeline with four layers.

**Layer one — Data**, handled by [成员C]. They built a pipeline that pulls 1-minute candlestick data from Binance, cleans it, and stores it in a local SQLite database. Five tables: market data, orders, trades, positions, and account snapshots.

**Layer two — Strategy**, handled by [成员A]. This is where the three factors get computed and combined into a single trading signal.

**Layer three — Execution**, handled by [成员B]. When the signal says "buy," this layer places the order, records it in the database, and enforces our risk rules.

**Layer four — Display**, that's my job. I built the Streamlit dashboard that shows you everything in real time — account value, PnL curve, positions, order history.

The whole system talks through the database. Clean, modular, easy to debug.

---

## 【第四部分 · 7:00–9:30】回测结果

**（切换到幻灯片6，7）**

Let's talk about results. Real results. Real data.

We backtested on **10,082 minutes of BTC/USDT data**, from April 12 to April 19, 2026.

**The headline numbers:**

Total return: **+4.96%** in 7 days. That's annualized roughly 290%.

Sharpe ratio: **6.53**. For context — a Sharpe above 1 is considered good, above 2 is excellent. We got 6.5. That's exceptional.

Maximum drawdown: **only 4.64%**. Even in the worst moment, we never lost more than 4.64% from our peak.

Win rate: **60%**. Six profitable trades out of every ten.

Profit factor: **6.06**. That means on average, every dollar we lose, we make six dollars back on our winning trades.

Now, I want to be transparent — buy-and-hold would have returned 5.9% in the same period, slightly higher. But look at the Sharpe ratio: buy-and-hold is around 1.2. Ours is 6.5.

The difference? **Risk-adjusted performance**. We made slightly less, but we took far less risk to get there. Our max drawdown was 4.6%. Buy-and-hold? Almost 10%.

That's the whole point of quantitative strategies — not just to make money, but to make money **safely**.

---

## 【第五部分 · 9:30–12:30】Live Demo

**（切换到浏览器，打开 http://localhost:8501）**

Now, the part I've been looking forward to — let me show you the system running live.

**（打开实时监控页）**

This is our dashboard. On the top, you can see the account value and total return in real time. Below that is the PnL curve — this is how our account value has changed over time.

On the right, you can see current positions. If we're holding Bitcoin right now, it shows here — quantity, average cost, floating PnL.

Down below, the order history — every single trade the system has made, with timestamps, prices, and quantities.

**（切换到回测分析页）**

This is the backtesting view. You can see all the performance metrics we just talked about — Sharpe ratio, drawdown, win rate — all in one place.

**（切换到TCA分析页）**

And this is TCA — Transaction Cost Analysis. I'll hand over to [成员C] for a quick explanation.

> [提示：这里由成员C介绍TCA内容，约1分钟，讲完后成员D继续]

---

## 【第六部分 · 12:30–14:00】总结与展望

**（切换到幻灯片11，12）**

Let me bring it all together.

What did we actually build?

We built a **complete, end-to-end algorithmic trading system**. Not a toy. Not a backtest on Excel. A real system — with a database, a strategy engine, a risk manager, a paper trading module, and a live dashboard.

In 7 days of backtesting:
- Sharpe ratio of 6.53
- Maximum drawdown under 5%
- 60% win rate, 6:1 profit factor

And it's all running live, right now, on real Binance prices.

**Where can we go from here?**

The next step would be machine learning — using LSTM or XGBoost to predict signals instead of rule-based factors. We could also expand to multiple assets, or hook it up to a real exchange API and move from paper trading to live trading.

But for a course project built in a few weeks by four people — we think Quant X Capital is something we're genuinely proud of.

---

## 【结尾 · 14:00–15:00】Q&A 引入

**（切换到最后一张幻灯片）**

Thank you for your attention.

My name is [你的名字], and I speak on behalf of **Quant X Capital**.

We'd be happy to answer any questions.

---

## 附录：常见问题预答

**Q：夏普比率 6.5 是不是太高了，是否过拟合？**

> A：We acknowledge that one week of data is a limited sample. The Sharpe ratio is high partly because we optimized on the same period. In a real deployment, we would use walk-forward validation — train on past data, test on future data. That said, even our worst parameter set produced a positive Sharpe, which suggests the strategy has genuine edge, not just curve fitting.

**Q：为什么选 1 分钟 K 线，不选更长的时间粒度？**

> A：The project requires a holding period under 1 day, which means intraday signals. 1-minute candles give us enough resolution to detect short-term momentum while still having enough data per day to calculate meaningful statistics.

**Q：Paper Trading 和真实交易有什么区别？**

> A：In paper trading, we simulate the fill at the last market price with no market impact. In reality, large orders would move the price — that's called market impact. Our TCA module estimates slippage at roughly 50% of commission, but live trading would require more sophisticated slippage modeling.

**Q：为什么不直接用 Backtrader 或 Zipline 这些现成的回测框架？**

> A：We chose to build our own backtester to demonstrate understanding of the mechanics. It also gave us full control over the data format, fee model, and position sizing logic. Using a black box would have been faster but less educational.

---

*讲稿说明：*
- *中英文混用部分可根据课程语言要求调整为全英文或全中文*
- *[ ] 内为需要填写实际名字的占位符*
- *Live Demo 部分时间弹性较大，可根据实际演示流畅度调整*
