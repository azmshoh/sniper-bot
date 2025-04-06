# database/db_manager.py

import sqlite3
import json
import logging
from datetime import datetime
from config.settings import DB_NAME

class DatabaseManager:
    def __init__(self):
        self.setup_database()
        self.cursor = self.conn.cursor()  # cursor yaratish

    def setup_database(self):
        """Initialize database and create tables"""
        try:
            self.conn = sqlite3.connect(DB_NAME)
            self.conn.row_factory = sqlite3.Row  # Dict formatida qaytarish uchun
            cursor = self.conn.cursor()
            
            # Create tokens table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tokens (
                    address TEXT,
                    network TEXT,
                    dex TEXT,
                    initial_price REAL,
                    creation_time TIMESTAMP,
                    last_check TIMESTAMP,
                    targets_hit TEXT,
                    PRIMARY KEY (address, network, dex)
                )
            ''')
            
            # Create locks table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS locks (
                    token_address TEXT,
                    network TEXT,
                    platform TEXT,
                    amount REAL,
                    lock_time TIMESTAMP,
                    PRIMARY KEY (token_address, network, platform)
                )
            ''')
            
            # Create trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_address TEXT,
                    network TEXT,
                    dex TEXT,
                    status TEXT,
                    entry_price REAL,
                    current_price REAL,
                    highest_price REAL,
                    lowest_price REAL,
                    amount_in REAL,
                    amount_out REAL,
                    token_amount REAL,
                    remaining_amount REAL,
                    profit_loss REAL,
                    profit_loss_percent REAL,
                    entry_time TIMESTAMP,
                    last_update TIMESTAMP,
                    close_time TIMESTAMP,
                    tp_hit TEXT,
                    stop_loss_hit INTEGER,
                    trailing_stop_hit INTEGER,
                    notes TEXT,
                    tx_hashes TEXT
                )
            ''')
            
            # Create trade_history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER,
                    action TEXT,
                    amount REAL,
                    price REAL,
                    timestamp TIMESTAMP,
                    tx_hash TEXT,
                    reason TEXT,
                    FOREIGN KEY (trade_id) REFERENCES trades(id)
                )
            ''')
            
            # Create RPC endpoints table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rpc_endpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    network TEXT NOT NULL,
                    rpc_url TEXT NOT NULL,
                    is_active INTEGER DEFAULT 0,
                    last_check TIMESTAMP NOT NULL,
                    last_error TEXT,
                    success_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(network, rpc_url)
                )
            ''')
            
            self.conn.commit()
            logging.info("Database initialized successfully")
            
        except Exception as e:
            logging.error(f"Database setup error: {e}")
            raise

    def save_token(self, token_address: str, network: str, dex: str, initial_price: float):
        """Save new token to database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO tokens 
                (address, network, dex, initial_price, creation_time, last_check, targets_hit)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                token_address,
                network,
                dex,
                initial_price,
                datetime.now(),
                datetime.now(),
                json.dumps([])
            ))
            self.conn.commit()
            logging.info(f"Token saved: {token_address} on {network}/{dex}")
            
        except Exception as e:
            logging.error(f"Error saving token {token_address} on {network}/{dex}: {e}")

    def save_lock(self, token_address: str, network: str, platform: str, amount: float):
        """Save token lock information"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO locks 
                (token_address, network, platform, amount, lock_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (token_address, network, platform, amount, datetime.now()))
            self.conn.commit()
            
        except Exception as e:
            logging.error(f"Error saving lock info for {token_address}: {e}")

    def save_trade(self, token_address, network, dex, trade_type, amount_in, token_amount, entry_price, tx_hash=None):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO trades (
                token_address, network, dex, type, 
                amount, tokens, price, status, 
                remaining_amount, entry_price, tx_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                token_address, 
                network, 
                dex, 
                trade_type,
                float(amount_in),  # Float ga o'tkazish
                str(token_amount),  # Katta sonlarni string qilish
                float(entry_price),
                'active',
                str(token_amount),  # Remaining amount ham string
                float(entry_price),
                tx_hash
            ))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error saving trade: {e}")
            self.conn.rollback()

    def update_trade(self, token_address: str, action: str, amount: float, 
                    reason: str = None, tx_hash: str = None):
        """Update existing trade"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
                SELECT id, amount_in, remaining_amount, entry_price, tx_hashes
                FROM trades 
                WHERE token_address = ? AND status = 'active'
            ''', (token_address,))
            
            trade = cursor.fetchone()
            if not trade:
                logging.error(f"No active trade found for {token_address}")
                return
                
            trade_id = trade['id']
            amount_in = trade['amount_in']
            remaining_amount = trade['remaining_amount']
            entry_price = trade['entry_price']
            tx_hashes = json.loads(trade['tx_hashes'])
            
            if tx_hash:
                tx_hashes.append(tx_hash)
            
            new_remaining = remaining_amount - amount
            
            if action == 'sell':
                profit_loss = (amount * entry_price) - amount_in
                profit_loss_percent = (profit_loss / amount_in) * 100
                
                status = 'active' if new_remaining > 0 else 'closed'
                close_time = datetime.now() if status == 'closed' else None
                
                cursor.execute('''
                    UPDATE trades 
                    SET remaining_amount = ?,
                        amount_out = COALESCE(amount_out, 0) + ?,
                        profit_loss = COALESCE(profit_loss, 0) + ?,
                        profit_loss_percent = ?,
                        status = ?,
                        close_time = ?,
                        last_update = ?,
                        tx_hashes = ?
                    WHERE id = ?
                ''', (
                    new_remaining, amount, profit_loss, profit_loss_percent,
                    status, close_time, datetime.now(), json.dumps(tx_hashes),
                    trade_id
                ))
                
                if tx_hash:
                    cursor.execute('''
                        INSERT INTO trade_history (
                            trade_id, action, amount, price, timestamp, tx_hash, reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        trade_id, action, amount, entry_price, datetime.now(), 
                        tx_hash, reason
                    ))
                
            self.conn.commit()
            logging.info(f"Trade updated: {token_address} ({action})")
            
        except Exception as e:
            logging.error(f"Error updating trade for {token_address}: {e}")

    def close_trade(self, token_address: str, reason: str):
        """Savdoni tugatish"""
        try:
            self.cursor.execute("""
                UPDATE trades 
                SET status = 'closed', 
                    close_reason = ?,
                    closed_at = CURRENT_TIMESTAMP
                WHERE token_address = ? 
                AND status = 'active'
            """, (reason, token_address))
            self.conn.commit()
            logging.info(f"Trade closed for {token_address}. Reason: {reason}")
        except Exception as e:
            logging.error(f"Error closing trade: {e}")
            
    def update_trade_high(self, token_address: str, new_high: float):
        """Update trade's highest price"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                UPDATE trades 
                SET highest_price = ?,
                    last_update = ?
                WHERE token_address = ? AND status = 'active'
            ''', (new_high, datetime.now(), token_address))
            self.conn.commit()
            
        except Exception as e:
            logging.error(f"Error updating high price for {token_address}: {e}")

    def update_trade_tp(self, token_address: str, tp_key: str):
        """Update trade's take profit status"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT id, tp_hit FROM trades
                WHERE token_address = ? AND status = 'active'
            ''', (token_address,))
            
            trade = cursor.fetchone()
            if trade:
                tp_hit = json.loads(trade['tp_hit'])
                tp_hit[tp_key] = True
                
                cursor.execute('''
                    UPDATE trades 
                    SET tp_hit = ?,
                        last_update = ?
                    WHERE id = ?
                ''', (json.dumps(tp_hit), datetime.now(), trade['id']))
                
                self.conn.commit()
                
        except Exception as e:
            logging.error(f"Error updating TP status for {token_address}: {e}")

    def get_active_trades(self, network: str = None, dex: str = None):
        """Get all active trades with optional network/dex filter"""
        try:
            cursor = self.conn.cursor()
            
            query = "SELECT * FROM trades WHERE status = 'active'"
            params = []
            
            if network:
                query += " AND network = ?"
                params.append(network)
            if dex:
                query += " AND dex = ?"
                params.append(dex)
                
            cursor.execute(query, params)
            
            trades = []
            for row in cursor.fetchall():
                trade = dict(row)
                trade['tp_hit'] = json.loads(trade['tp_hit'])
                trade['tx_hashes'] = json.loads(trade['tx_hashes'])
                trades.append(trade)
                
            return trades
            
        except Exception as e:
            logging.error(f"Error getting active trades: {e}")
            return []

    def save_rpc_url(self, network: str, rpc_url: str, is_active: bool, last_check: datetime):
        """Save new RPC URL"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO rpc_endpoints 
                (network, rpc_url, is_active, last_check)
                VALUES (?, ?, ?, ?)
            ''', (network, rpc_url, 1 if is_active else 0, last_check))
            self.conn.commit()
            
        except Exception as e:
            logging.error(f"Error saving RPC URL: {e}")
            raise

    def update_rpc_status(self, network: str, rpc_url: str, is_active: bool, 
                     last_check: datetime, last_error: str = None):
        """Update RPC status"""
        try:
            cursor = self.conn.cursor()
            
            # Mavjud yozuvni tekshirish
            cursor.execute('''
                SELECT id FROM rpc_endpoints 
                WHERE network = ? AND rpc_url = ?
            ''', (network, rpc_url))
            
            existing_record = cursor.fetchone()
            
            try:
                if existing_record:
                    # Mavjud yozuvni yangilash
                    cursor.execute('''
                        UPDATE rpc_endpoints 
                        SET 
                            is_active = ?,
                            last_check = ?,
                            last_error = ?,
                            success_count = success_count + CASE WHEN ? THEN 1 ELSE 0 END,
                            error_count = error_count + CASE WHEN NOT ? THEN 1 ELSE 0 END
                        WHERE network = ? AND rpc_url = ?
                    ''', (
                        1 if is_active else 0,
                        last_check,
                        last_error,
                        is_active,
                        is_active,
                        network,
                        rpc_url
                    ))
                else:
                    # Yangi yozuv qo'shish
                    cursor.execute('''
                        INSERT INTO rpc_endpoints (
                            network, 
                            rpc_url, 
                            is_active, 
                            last_check, 
                            last_error,
                            success_count, 
                            error_count,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        network,
                        rpc_url,
                        1 if is_active else 0,
                        last_check,
                        last_error,
                        1 if is_active else 0,
                        1 if not is_active else 0
                    ))
                
                self.conn.commit()
            except sqlite3.OperationalError as oe:
                logging.error(f"SQLite operational error: {oe}")
                self.conn.rollback()
            
        except Exception as e:
            logging.error(f"Error updating RPC status: {e}")
            self.conn.rollback()

    def get_working_rpcs(self, network: str) -> list:
        """So'nggi ishlagan RPClarni olish"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT rpc_url FROM rpc_endpoints 
                WHERE network = ? 
                AND last_success IS NOT NULL
                ORDER BY last_success DESC
            ''', (network,))
            
            return [row['rpc_url'] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting working RPCs: {e}")
            return []
    def save_working_rpc(self, network: str, rpc_url: str, last_success: datetime):
        """Ishlagan RPC ni saqlash"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO rpc_endpoints (network, rpc_url, last_success)
                VALUES (?, ?, ?)
                ON CONFLICT(network, rpc_url) 
                DO UPDATE SET last_success = ?
            ''', (network, rpc_url, last_success, last_success))
            
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error saving working RPC: {e}")
            raise

    def get_trade_history(self, token_address: str = None):
        """Get trade history"""
        try:
            cursor = self.conn.cursor()
            
            if token_address:
                cursor.execute('''
                    SELECT th.* FROM trade_history th
                    JOIN trades t ON th.trade_id = t.id
                    WHERE t.token_address = ?
                    ORDER BY th.timestamp DESC
                ''', (token_address,))
            else:
                cursor.execute('SELECT * FROM trade_history ORDER BY timestamp DESC')
                
            return [dict(row) for row in cursor.fetchall()]
            
        except Exception as e:
            logging.error(f"Error getting trade history: {e}")
            return []

    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()
            logging.info("Database connection closed")