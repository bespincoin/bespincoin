"""
Blockchain Persistence Layer
Saves blockchain data to SQLite database
"""

import sqlite3
import json
from typing import List, Optional
from blockchain import Block
from transaction import Transaction, TxInput, TxOutput


class BlockchainDB:
    """SQLite database for blockchain persistence"""
    
    def __init__(self, db_path: str = "blockchain.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        """Create database tables if they don't exist"""
        cursor = self.conn.cursor()
        
        # Blocks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                block_index INTEGER PRIMARY KEY,
                timestamp REAL NOT NULL,
                previous_hash TEXT NOT NULL,
                merkle_root TEXT NOT NULL,
                nonce INTEGER NOT NULL,
                difficulty INTEGER NOT NULL,
                hash TEXT NOT NULL
            )
        """)
        
        # Transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                txid TEXT PRIMARY KEY,
                block_index INTEGER NOT NULL,
                version INTEGER NOT NULL,
                locktime INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY (block_index) REFERENCES blocks(block_index)
            )
        """)
        
        # Transaction inputs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tx_inputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txid TEXT NOT NULL,
                prev_txid TEXT NOT NULL,
                vout INTEGER NOT NULL,
                script_sig TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                FOREIGN KEY (txid) REFERENCES transactions(txid)
            )
        """)
        
        # Transaction outputs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tx_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txid TEXT NOT NULL,
                vout INTEGER NOT NULL,
                amount REAL NOT NULL,
                script_pubkey TEXT NOT NULL,
                FOREIGN KEY (txid) REFERENCES transactions(txid)
            )
        """)
        
        # UTXO set table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS utxos (
                txid TEXT NOT NULL,
                vout INTEGER NOT NULL,
                amount REAL NOT NULL,
                address TEXT NOT NULL,
                PRIMARY KEY (txid, vout)
            )
        """)
        
        # Metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        self.conn.commit()
    
    def save_block(self, block: Block):
        """Save a block and its transactions to database"""
        cursor = self.conn.cursor()
        
        try:
            # Save block
            cursor.execute("""
                INSERT OR REPLACE INTO blocks 
                (block_index, timestamp, previous_hash, merkle_root, nonce, difficulty, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                block.index,
                block.timestamp,
                block.previous_hash,
                block.merkle_root,
                block.nonce,
                block.difficulty,
                block.hash
            ))
            
            # Save transactions
            for tx in block.transactions:
                self.save_transaction(tx, block.index)
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error saving block: {e}")
            self.conn.rollback()
            return False
    
    def save_transaction(self, tx: Transaction, block_index: int):
        """Save a transaction and its inputs/outputs"""
        cursor = self.conn.cursor()
        
        # Save transaction
        cursor.execute("""
            INSERT OR REPLACE INTO transactions 
            (txid, block_index, version, locktime, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (tx.txid, block_index, tx.version, tx.locktime, tx.timestamp))
        
        # Delete old inputs/outputs if updating
        cursor.execute("DELETE FROM tx_inputs WHERE txid = ?", (tx.txid,))
        cursor.execute("DELETE FROM tx_outputs WHERE txid = ?", (tx.txid,))
        
        # Save inputs
        for tx_input in tx.inputs:
            cursor.execute("""
                INSERT INTO tx_inputs 
                (txid, prev_txid, vout, script_sig, sequence)
                VALUES (?, ?, ?, ?, ?)
            """, (
                tx.txid,
                tx_input.txid,
                tx_input.vout,
                tx_input.script_sig,
                tx_input.sequence
            ))
        
        # Save outputs
        for i, tx_output in enumerate(tx.outputs):
            cursor.execute("""
                INSERT INTO tx_outputs 
                (txid, vout, amount, script_pubkey)
                VALUES (?, ?, ?, ?)
            """, (tx.txid, i, tx_output.amount, tx_output.script_pubkey))
    
    def load_blockchain(self) -> List[Block]:
        """Load entire blockchain from database"""
        cursor = self.conn.cursor()
        
        # Get all blocks ordered by index
        cursor.execute("""
            SELECT block_index, timestamp, previous_hash, merkle_root, 
                   nonce, difficulty, hash
            FROM blocks
            ORDER BY block_index
        """)
        
        blocks = []
        for row in cursor.fetchall():
            block_index, timestamp, previous_hash, merkle_root, nonce, difficulty, block_hash = row
            
            # Load transactions for this block
            transactions = self.load_transactions_for_block(block_index)
            
            # Reconstruct block
            block = Block(block_index, transactions, previous_hash, difficulty)
            block.timestamp = timestamp
            block.merkle_root = merkle_root
            block.nonce = nonce
            block.hash = block_hash
            
            blocks.append(block)
        
        return blocks
    
    def load_recent_blocks(self, count: int = 100) -> List[Block]:
        """Load only the most recent N blocks from database"""
        cursor = self.conn.cursor()
        
        # Get the most recent blocks
        cursor.execute("""
            SELECT block_index, timestamp, previous_hash, merkle_root, 
                   nonce, difficulty, hash
            FROM blocks
            ORDER BY block_index DESC
            LIMIT ?
        """, (count,))
        
        blocks = []
        for row in cursor.fetchall():
            block_index, timestamp, previous_hash, merkle_root, nonce, difficulty, block_hash = row
            
            # Load transactions for this block
            transactions = self.load_transactions_for_block(block_index)
            
            # Reconstruct block
            block = Block(block_index, transactions, previous_hash, difficulty)
            block.timestamp = timestamp
            block.merkle_root = merkle_root
            block.nonce = nonce
            block.hash = block_hash
            
            blocks.append(block)
        
        # Reverse to get chronological order
        blocks.reverse()
        return blocks
    
    def load_transactions_for_block(self, block_index: int) -> List[Transaction]:
        """Load all transactions for a specific block"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT txid, version, locktime, timestamp
            FROM transactions
            WHERE block_index = ?
            ORDER BY txid
        """, (block_index,))
        
        transactions = []
        for row in cursor.fetchall():
            txid, version, locktime, timestamp = row
            
            # Load inputs
            cursor.execute("""
                SELECT prev_txid, vout, script_sig, sequence
                FROM tx_inputs
                WHERE txid = ?
            """, (txid,))
            
            inputs = []
            for input_row in cursor.fetchall():
                prev_txid, vout, script_sig, sequence = input_row
                inputs.append(TxInput(prev_txid, vout, script_sig, sequence))
            
            # Load outputs
            cursor.execute("""
                SELECT vout, amount, script_pubkey
                FROM tx_outputs
                WHERE txid = ?
                ORDER BY vout
            """, (txid,))
            
            outputs = []
            for output_row in cursor.fetchall():
                vout, amount, script_pubkey = output_row
                outputs.append(TxOutput(amount, script_pubkey))
            
            # Reconstruct transaction
            tx = Transaction(inputs, outputs, locktime=locktime)
            tx.version = version
            tx.txid = txid
            tx.timestamp = timestamp
            
            transactions.append(tx)
        
        return transactions
    
    def save_utxo_set(self, utxo_set):
        """Save UTXO set to database (incremental update, not full replace)"""
        # This is called after each block is added
        # We should not clear the entire UTXO table since we only have recent blocks in memory
        # Instead, just commit the current state - the UTXO set in memory is already correct
        # for the blocks we've processed
        cursor = self.conn.cursor()
        
        # For now, do nothing - UTXO updates happen in real-time via add_utxo/remove_utxo
        # This prevents clearing the UTXO table when we only have 100 blocks in memory
        pass
    
    def add_utxo(self, utxo):
        """Add a single UTXO to database"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO utxos (txid, vout, amount, address)
            VALUES (?, ?, ?, ?)
        """, (utxo.txid, utxo.vout, utxo.amount, utxo.script_pubkey))
        self.conn.commit()
    
    def remove_utxo(self, txid: str, vout: int):
        """Remove a spent UTXO from database"""
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM utxos WHERE txid = ? AND vout = ?
        """, (txid, vout))
        self.conn.commit()
    
    def save_utxo_set_full(self, utxo_set):
        """Save complete UTXO set to database (full replace)"""
        cursor = self.conn.cursor()
        
        # Clear existing UTXOs
        cursor.execute("DELETE FROM utxos")
        
        # Save all UTXOs
        for utxo in utxo_set.utxos.values():
            cursor.execute("""
                INSERT INTO utxos (txid, vout, amount, address)
                VALUES (?, ?, ?, ?)
            """, (utxo.txid, utxo.vout, utxo.amount, utxo.address))
        
        self.conn.commit()
    
    def load_utxo_set(self, db=None):
        """Load UTXO set from database"""
        from utxo_set import UTXOSet
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT txid, vout, amount, address FROM utxos")
        
        utxo_set = UTXOSet(db=db)  # Pass database connection
        for row in cursor.fetchall():
            txid, vout, amount, address = row
            from transaction import UTXO
            utxo = UTXO(txid, vout, amount, address)
            # Add to memory only, don't write back to database
            key = f"{txid}:{vout}"
            utxo_set.utxos[key] = utxo
        
        return utxo_set
    
    def get_block_count(self) -> int:
        """Get total number of blocks"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM blocks")
        return cursor.fetchone()[0]
    
    def save_metadata(self, key: str, value: str):
        """Save metadata key-value pair"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO metadata (key, value)
            VALUES (?, ?)
        """, (key, value))
        self.conn.commit()
    
    def get_metadata(self, key: str) -> Optional[str]:
        """Get metadata value by key"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None
    
    def close(self):
        """Close database connection"""
        self.conn.close()
