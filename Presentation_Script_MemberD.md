# Member D — Presentation Script (15 minutes)
> Quant X Capital — MFE5210 Project Defence

---

## [Opening · 0:00–1:00] Cover Slide

**(Walk to the front calmly, pause for 2 seconds, scan the audience, smile)**

Good afternoon, professors and classmates.

We are **Quant X Capital**.

Today, we're going to show you something different — not just a trading strategy on paper, but a **fully functioning automated trading system** that we built from scratch.

It runs 24/7, reads live market data, makes decisions by itself, and shows you everything on a real-time dashboard.

Let's get started.

---

## [Contents · 1:00–1:30] Table of Contents

**(Switch to contents slide)**

Here's the roadmap for today. We have 15 minutes, and I'll walk you through six parts:

First, why we chose crypto and this strategy. Then the strategy itself — how it actually works. Third, the system architecture — how all the pieces fit together. Fourth, our backtesting results with real data. Fifth — and this is my favorite part — a live demo. And finally, a quick TCA analysis and our conclusions.

Let's go.

---

## [Part 1 · 1:30–2:30] Why Cryptocurrency?

**(Switch to Slide 3)**

Let me start with the "why."

Why Bitcoin? Why not stocks?

Three reasons.

First, **crypto never sleeps**. Unlike traditional stock markets that close in the afternoon, Bitcoin trades 24 hours a day, 7 days a week. That's ideal for an intraday strategy — more opportunities, more data.

Second, **the data is completely free**. Binance — the world's largest crypto exchange — provides public APIs with no registration required. We pulled over 10,000 minutes of real price data for free.

Third, **it's a great testing ground**. Crypto markets are volatile, which means if our strategy can survive there, it's robust. High risk, high learning.

As for why multi-factor momentum — I'll let [Member A's name] explain that in detail. But the short answer is: one signal lies; three signals together are much harder to fake.

---

## [Part 2 · 2:30–5:30] Strategy Design

**(Switch to Slides 4 & 5)**

**(Hand over to Member A for strategy presentation — approx. 2–3 minutes)**

> [Cue: Member A comes up to introduce the three-factor strategy and parameter optimisation; Member D continues after]

Thank you, [Member A]. So to summarise — our strategy generates a score between -1 and +1. Above 0.4, we buy. Below -0.4, we sell. Everything else, we wait.

Those thresholds weren't guessed. We ran a **grid search across 36 parameter combinations** and picked the one with the best Sharpe ratio. Science, not luck.

---

## [Part 3 · 5:30–7:00] System Architecture

**(Switch to Slide 5)**

Now let me show you how the whole system is wired together.

Think of it as a pipeline with four layers.

**Layer one — Data**, handled by [Member C]. They built a pipeline that pulls 1-minute candlestick data from Binance, cleans it, and stores it in a local SQLite database. Five tables: market data, orders, trades, positions, and account snapshots.

**Layer two — Strategy**, handled by [Member A]. This is where the three factors get computed and combined into a single trading signal.

**Layer three — Execution**, handled by [Member B]. When the signal says "buy," this layer places the order, records it in the database, and enforces our risk rules.

**Layer four — Display**, that's my job. I built the Streamlit dashboard that shows you everything in real time — account value, PnL curve, positions, order history.

The whole system talks through the database. Clean, modular, easy to debug.

---

## [Part 4 · 7:00–9:30] Backtest Results

**(Switch to Slides 6 & 7)**

Let's talk about results. Real results. Real data.

We backtested on **10,082 minutes of BTC/USDT data**, from April 12 to April 19, 2026.

**The headline numbers:**

Total return: **+4.96%** in 7 days. That's annualised roughly 290%.

Sharpe ratio: **6.53**. For context — a Sharpe above 1 is considered good, above 2 is excellent. We got 6.5. That's exceptional.

Maximum drawdown: **only 4.64%**. Even in the worst moment, we never lost more than 4.64% from our peak.

Win rate: **60%**. Six profitable trades out of every ten.

Profit factor: **6.06**. That means on average, every dollar we lose, we make six dollars back on our winning trades.

Now, I want to be transparent — buy-and-hold would have returned 5.9% in the same period, slightly higher. But look at the Sharpe ratio: buy-and-hold is around 1.2. Ours is 6.5.

The difference? **Risk-adjusted performance**. We made slightly less, but we took far less risk to get there. Our max drawdown was 4.6%. Buy-and-hold? Almost 10%.

That's the whole point of quantitative strategies — not just to make money, but to make money **safely**.

---

## [Part 5 · 9:30–12:30] Live Demo

**(Switch to browser — open http://localhost:8501)**

Now, the part I've been looking forward to — let me show you the system running live.

**(Open the Live Monitor page)**

This is our dashboard. On the top, you can see the account value and total return in real time. Below that is the PnL curve — this is how our account value has changed over time.

On the right, you can see current positions. If we're holding Bitcoin right now, it shows here — quantity, average cost, floating P&L.

Down below, the order history — every single trade the system has made, with timestamps, prices, and quantities.

**(Switch to Backtest Analysis page)**

This is the backtesting view. You can see all the performance metrics we just talked about — Sharpe ratio, drawdown, win rate — all in one place.

**(Switch to TCA Cost Analysis page)**

And this is TCA — Transaction Cost Analysis. I'll hand over to [Member C] for a quick explanation.

> [Cue: Member C introduces TCA content — approx. 1 minute; Member D continues after]

---

## [Part 6 · 12:30–14:00] Conclusion & Future Work

**(Switch to Slides 11 & 12)**

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

## [Closing · 14:00–15:00] Q&A Introduction

**(Switch to the final slide)**

Thank you for your attention.

My name is [your name], and I speak on behalf of **Quant X Capital**.

We'd be happy to answer any questions.

---

## Appendix: Anticipated Q&A

**Q: A Sharpe ratio of 6.5 seems very high — could this be overfitting?**

> A: We acknowledge that one week of data is a limited sample. The Sharpe ratio is high partly because we optimised on the same period. In a real deployment, we would use walk-forward validation — train on past data, test on future data. That said, even our worst parameter set produced a positive Sharpe, which suggests the strategy has genuine edge, not just curve fitting.

**Q: Why use 1-minute candles instead of a longer timeframe?**

> A: The project requires a holding period under 1 day, which means intraday signals. 1-minute candles give us enough resolution to detect short-term momentum while still having enough data per day to calculate meaningful statistics.

**Q: What is the difference between Paper Trading and live trading?**

> A: In paper trading, we simulate the fill at the last market price with no market impact. In reality, large orders would move the price — that's called market impact. Our TCA module estimates slippage at roughly 50% of commission, but live trading would require more sophisticated slippage modelling.

**Q: Why not use an existing backtest framework like Backtrader or Zipline?**

> A: We chose to build our own backtester to demonstrate understanding of the mechanics. It also gave us full control over the data format, fee model, and position sizing logic. Using a black box would have been faster but less educational.

---

*Script notes:*
- *Adjust language to all-English as required by the course*
- *[ ] placeholders should be filled in with actual names before presenting*
- *The Live Demo section has flexible timing — adjust based on how smoothly the demo runs*
