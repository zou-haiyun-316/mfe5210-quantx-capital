"""
Member C — Database Management Module
Creates and manages all data tables: market data, orders, positions, and trades.
Database: SQLite (lightweight, no server required, single local file).
"""

import sqlite3
import os
from datetime import datetime

# Database file path
DB_PATH = os.path.join(os.path.dirname(__file__), "quantx.db")


def get_connection():
    """Return a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Allow column-name access on query results
    return conn


def init_database():
    """Initialise the database and create all required tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------------------------------------
    # Table 1: Market Data (historical candlestick data)
    # Each candle represents one time period: open / high / low / close / volume
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kline (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT    NOT NULL,       -- trading pair, e.g. BTC/USDT
            timeframe   TEXT    NOT NULL,       -- interval, e.g. 1m = 1 minute, 1h = 1 hour
            open_time   INTEGER NOT NULL,       -- candle open timestamp (milliseconds)
            open        REAL    NOT NULL,       -- open price
            high        REAL    NOT NULL,       -- high price
            low         REAL    NOT NULL,       -- low price
            close       REAL    NOT NULL,       -- close price
            volume      REAL    NOT NULL,       -- volume (BTC quantity)
            UNIQUE(symbol, timeframe, open_time) -- one record per timestamp
        )
    """)

    # -------------------------------------------------------
    # Table 2: Orders (record of every order placed)
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT    NOT NULL UNIQUE,  -- unique order identifier
            symbol          TEXT    NOT NULL,          -- trading pair
            side            TEXT    NOT NULL,          -- direction: buy or sell
            order_type      TEXT    NOT NULL,          -- type: market or limit
            price           REAL,                      -- order price (null for market orders)
            qty             REAL    NOT NULL,          -- order quantity
            status          TEXT    NOT NULL,          -- status: open / filled / cancelled
            created_at      TEXT    NOT NULL,          -- order creation time
            updated_at      TEXT                       -- last update time
        )
    """)

    # -------------------------------------------------------
    # Table 3: Trades (record of actual fills)
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT    NOT NULL,   -- associated order ID
            symbol          TEXT    NOT NULL,
            side            TEXT    NOT NULL,   -- buy or sell
            filled_price    REAL    NOT NULL,   -- actual fill price
            filled_qty      REAL    NOT NULL,   -- actual fill quantity
            commission      REAL    NOT NULL,   -- commission paid (USDT)
            filled_at       TEXT    NOT NULL    -- fill timestamp
        )
    """)

    # -------------------------------------------------------
    # Table 4: Positions (current account positions)
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT    NOT NULL UNIQUE,  -- one record per trading pair
            qty             REAL    NOT NULL DEFAULT 0,     -- quantity held
            avg_cost        REAL    NOT NULL DEFAULT 0,     -- average holding cost
            unrealized_pnl  REAL    NOT NULL DEFAULT 0,     -- unrealised P&L (floating)
            updated_at      TEXT    NOT NULL               -- last update time
        )
    """)

    # -------------------------------------------------------
    # Table 5: Account Snapshots (balance snapshot after each operation)
    # -------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cash            REAL    NOT NULL,   -- available cash (USDT)
            total_value     REAL    NOT NULL,   -- total account value (cash + position value)
            snapshot_at     TEXT    NOT NULL    -- snapshot timestamp
        )
    """)

    conn.commit()
    conn.close()
    print(f"[Database] Initialised. File path: {DB_PATH}")


# ================================================================
# Public interface functions for other modules
# ================================================================

def save_klines(symbol: str, timeframe: str, klines: list):
    """
    Persist candlestick data.
    Args:
        symbol: trading pair, e.g. 'BTC/USDT'
        timeframe: candle interval, e.g. '1m'
        klines: list of [timestamp, open, high, low, close, volume]
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
    Retrieve candlestick data (used by Member A's backtester).
    Args:
        symbol: trading pair
        timeframe: candle interval
        limit: number of most recent bars to return
    Returns:
        List of dicts: [{open_time, open, high, low, close, volume}, ...]
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
    return list(reversed(rows))  # Return in chronological order


def save_order(order_id: str, symbol: str, side: str, order_type: str,
               price: float, qty: float, status: str = "open"):
    """Persist an order record (called by Member B)."""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT OR REPLACE INTO orders (order_id, symbol, side, order_type, price, qty, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_id, symbol, side, order_type, price, qty, status, now, now))
    conn.commit()
    conn.close()


def update_order_status(order_id: str, status: str):
    """Update the status of an existing order."""
    conn = get_connection()
    conn.execute("""
        UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?
    """, (status, datetime.now().isoformat(), order_id))
    conn.commit()
    conn.close()


def save_trade(order_id: str, symbol: str, side: str,
               filled_price: float, filled_qty: float, commission: float):
    """Persist a fill record (called by Member B)."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO trades (order_id, symbol, side, filled_price, filled_qty, commission, filled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (order_id, symbol, side, filled_price, filled_qty, commission, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def update_position(symbol: str, qty: float, avg_cost: float, unrealized_pnl: float):
    """Update position data (called by Member B)."""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO positions (symbol, qty, avg_cost, unrealized_pnl, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (symbol, qty, avg_cost, unrealized_pnl, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def save_account_snapshot(cash: float, total_value: float):
    """Record an account snapshot (called by Members B and D)."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO account_snapshots (cash, total_value, snapshot_at)
        VALUES (?, ?, ?)
    """, (cash, total_value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_account_history() -> list:
    """Retrieve account value history (used by Member D to plot the PnL curve)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT cash, total_value, snapshot_at FROM account_snapshots ORDER BY snapshot_at")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_current_positions() -> list:
    """Retrieve all current open positions (used by Member D to display holdings)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM positions WHERE qty > 0")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_orders(limit: int = 50) -> list:
    """Retrieve recent orders (used by Member D to display the order log)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


if __name__ == "__main__":
    init_database()
    print("Database module test passed!")
