"""
成员 C — 数据库管理模块
负责创建和管理所有数据表：行情表、订单表、持仓表、成交表
数据库使用 SQLite（轻量级，无需安装服务器，直接是本地文件）
"""

import sqlite3
import os
from datetime import datetime

# 数据库文件路径
DB_PATH = os.path.join(os.path.dirname(__file__), "quantx.db")


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 让查询结果可以用列名访问
    return conn


def init_database():
    """初始化数据库，创建所有需要的表"""
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------------------------------------
    # 表1：行情表（存储历史K线数据）
    # K线：每根K线代表一段时间内的 开盘价/最高价/最低价/收盘价/成交量
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kline (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT    NOT NULL,       -- 交易对，如 BTC/USDT
            timeframe   TEXT    NOT NULL,       -- 时间粒度，如 1m=1分钟, 1h=1小时
            open_time   INTEGER NOT NULL,       -- K线开始时间戳（毫秒）
            open        REAL    NOT NULL,       -- 开盘价
            high        REAL    NOT NULL,       -- 最高价
            low         REAL    NOT NULL,       -- 最低价
            close       REAL    NOT NULL,       -- 收盘价
            volume      REAL    NOT NULL,       -- 成交量（BTC数量）
            UNIQUE(symbol, timeframe, open_time) -- 同一时间点只存一条
        )
    """)

    # -------------------------------------------------------
    # 表2：订单表（每次下单的记录）
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT    NOT NULL UNIQUE,  -- 唯一订单号
            symbol          TEXT    NOT NULL,          -- 交易对
            side            TEXT    NOT NULL,          -- 方向：buy 或 sell
            order_type      TEXT    NOT NULL,          -- 订单类型：market(市价) / limit(限价)
            price           REAL,                      -- 委托价格（市价单可为空）
            qty             REAL    NOT NULL,          -- 委托数量
            status          TEXT    NOT NULL,          -- 状态：open/filled/cancelled
            created_at      TEXT    NOT NULL,          -- 下单时间
            updated_at      TEXT                       -- 最后更新时间
        )
    """)

    # -------------------------------------------------------
    # 表3：成交表（实际成交的记录）
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT    NOT NULL,   -- 关联的订单号
            symbol          TEXT    NOT NULL,
            side            TEXT    NOT NULL,   -- buy 或 sell
            filled_price    REAL    NOT NULL,   -- 实际成交价格
            filled_qty      REAL    NOT NULL,   -- 实际成交数量
            commission      REAL    NOT NULL,   -- 手续费（USDT）
            filled_at       TEXT    NOT NULL    -- 成交时间
        )
    """)

    # -------------------------------------------------------
    # 表4：持仓表（当前账户持仓状态）
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT    NOT NULL UNIQUE,  -- 交易对（一个品种只有一条记录）
            qty             REAL    NOT NULL DEFAULT 0,     -- 持有数量
            avg_cost        REAL    NOT NULL DEFAULT 0,     -- 平均持仓成本
            unrealized_pnl  REAL    NOT NULL DEFAULT 0,     -- 未实现盈亏（浮动盈亏）
            updated_at      TEXT    NOT NULL               -- 更新时间
        )
    """)

    # -------------------------------------------------------
    # 表5：账户资金表（记录每次操作后的账户余额快照）
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cash            REAL    NOT NULL,   -- 可用现金（USDT）
            total_value     REAL    NOT NULL,   -- 账户总价值（现金 + 持仓市值）
            snapshot_at     TEXT    NOT NULL    -- 记录时间
        )
    """)

    conn.commit()
    conn.close()
    print(f"[数据库] 初始化完成，文件路径：{DB_PATH}")


# ================================================================
# 以下是给其他模块调用的接口函数
# ================================================================

def save_klines(symbol: str, timeframe: str, klines: list):
    """
    保存K线数据
    参数：
        symbol: 交易对，如 'BTC/USDT'
        timeframe: 时间粒度，如 '1m'
        klines: 列表，每项为 [时间戳, 开, 高, 低, 收, 量]
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT OR IGNORE INTO kline (symbol, timeframe, open_time, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [(symbol, timeframe, k[0], k[1], k[2], k[3], k[4], k[5]) for k in klines])
    conn.commit()
    conn.close()


def get_klines(symbol: str, timeframe: str, limit: int = 1000) -> list:
    """
    获取K线数据（给成员A回测用）
    参数：
        symbol: 交易对
        timeframe: 时间粒度
        limit: 获取最近多少根K线
    返回：
        列表，每项为字典 {open_time, open, high, low, close, volume}
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT open_time, open, high, low, close, volume
        FROM kline
        WHERE symbol = ? AND timeframe = ?
        ORDER BY open_time DESC
        LIMIT ?
    """, (symbol, timeframe, limit))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return list(reversed(rows))  # 时间从早到晚排列


def save_order(order_id: str, symbol: str, side: str, order_type: str,
               price: float, qty: float, status: str = "open"):
    """保存订单记录（给成员B调用）"""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT OR REPLACE INTO orders (order_id, symbol, side, order_type, price, qty, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_id, symbol, side, order_type, price, qty, status, now, now))
    conn.commit()
    conn.close()


def update_order_status(order_id: str, status: str):
    """更新订单状态"""
    conn = get_connection()
    conn.execute("""
        UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?
    """, (status, datetime.now().isoformat(), order_id))
    conn.commit()
    conn.close()


def save_trade(order_id: str, symbol: str, side: str,
               filled_price: float, filled_qty: float, commission: float):
    """保存成交记录（给成员B调用）"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO trades (order_id, symbol, side, filled_price, filled_qty, commission, filled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (order_id, symbol, side, filled_price, filled_qty, commission, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def update_position(symbol: str, qty: float, avg_cost: float, unrealized_pnl: float):
    """更新持仓（给成员B调用）"""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO positions (symbol, qty, avg_cost, unrealized_pnl, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (symbol, qty, avg_cost, unrealized_pnl, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def save_account_snapshot(cash: float, total_value: float):
    """记录账户快照（给成员B和D调用）"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO account_snapshots (cash, total_value, snapshot_at)
        VALUES (?, ?, ?)
    """, (cash, total_value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_account_history() -> list:
    """获取账户历史价值（给成员D画PnL曲线用）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT cash, total_value, snapshot_at FROM account_snapshots ORDER BY snapshot_at")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_current_positions() -> list:
    """获取当前所有持仓（给成员D显示持仓用）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM positions WHERE qty > 0")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_orders(limit: int = 50) -> list:
    """获取最近订单（给成员D显示订单流水用）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


if __name__ == "__main__":
    init_database()
    print("数据库模块测试通过！")
