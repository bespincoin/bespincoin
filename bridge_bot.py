#!/usr/bin/env python3
"""
Automated BSP Bridge Bot
Monitors BSP deposits and automatically mints wBSP on Polygon
"""

import time
import json
import os
import requests
from web3 import Web3
from datetime import datetime
import sqlite3

# Configuration
BSP_API = "http://127.0.0.1:8000"
BRIDGE_ADDRESS = "1BEdzEJXqAcfWpZDK3ePJiCAcjUL4rnMVw"
POLYGON_RPC = "https://polygon-mainnet.g.alchemy.com/v2/WbBffDdTbf-jugfTOOzGb"
WBSP_CONTRACT = "0xAAC69033F2e096b046D6b296CAAD4639843204c1"
CHECK_INTERVAL = 60  # Check every 60 seconds

# Database for tracking processed transactions
DB_FILE = "/root/bridge.db"

# Web3 setup
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))

# Contract ABI (just the mint function)
WBSP_ABI = [
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "bspAddress", "type": "string"}
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Addresses blacklisted from bridging (known exploiters)
BLACKLISTED_ADDRESSES = {
    '0x15ad76bf408375b78baea909ea138cd19b3d54b7',
    '0x6bf8be9a130934edd4ad531540a588f6ed456489',
}

def is_blacklisted(polygon_address):
    return polygon_address.lower() in BLACKLISTED_ADDRESSES

def init_db():
    """Initialize database for tracking processed bridges"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processed_bridges
                 (bsp_txid TEXT PRIMARY KEY,
                  bsp_address TEXT,
                  polygon_address TEXT,
                  amount REAL,
                  polygon_txid TEXT,
                  timestamp TEXT,
                  status TEXT)''')
    conn.commit()
    conn.close()
    """Initialize database for tracking processed bridges"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processed_bridges
                 (bsp_txid TEXT PRIMARY KEY,
                  bsp_address TEXT,
                  polygon_address TEXT,
                  amount REAL,
                  polygon_txid TEXT,
                  timestamp TEXT,
                  status TEXT)''')
    conn.commit()
    conn.close()

def get_bridge_balance():
    """Get current balance of bridge address"""
    try:
        response = requests.get(f"{BSP_API}/wallet/balance/{BRIDGE_ADDRESS}")
        data = response.json()
        return data.get('balance', 0)
    except Exception as e:
        print(f"Error getting bridge balance: {e}")
        return 0

def get_recent_transactions():
    """Get recent transactions to bridge address directly from DB"""
    try:
        conn = sqlite3.connect("/root/blockchain.db", timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.cursor()
        # Also resolve the sender address via the input's previous output
        cursor.execute("""
            SELECT t.txid, o.amount, b.block_index,
                   (SELECT prev.script_pubkey
                    FROM tx_inputs i
                    JOIN tx_outputs prev ON i.prev_txid = prev.txid AND i.vout = prev.vout
                    WHERE i.txid = t.txid
                    LIMIT 1) as sender
            FROM transactions t
            JOIN blocks b ON t.block_index = b.block_index
            JOIN tx_outputs o ON t.txid = o.txid
            WHERE o.script_pubkey = ?
            ORDER BY b.block_index DESC
            LIMIT 200
        """, (BRIDGE_ADDRESS,))
        rows = cursor.fetchall()
        conn.close()
        transactions = []
        for row in rows:
            transactions.append({
                'txid': row[0],
                'amount': row[1],
                'block': row[2],
                'from': row[3] or 'unknown'
            })
        return transactions
    except Exception as e:
        print(f"Error getting transactions: {e}")
        return []

def is_processed(txid):
    """Check if transaction already processed"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM processed_bridges WHERE bsp_txid=?", (txid,))
    result = c.fetchone()
    conn.close()
    return result is not None

def mark_processed(txid, bsp_addr, poly_addr, amount, poly_txid, status):
    """Mark transaction as processed"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""INSERT INTO processed_bridges 
                 (bsp_txid, bsp_address, polygon_address, amount, polygon_txid, timestamp, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (txid, bsp_addr, poly_addr, amount, poly_txid, datetime.now().isoformat(), status))
    conn.commit()
    conn.close()

def mint_wbsp(to_address, amount, bsp_address, private_key):
    """Mint wBSP on Polygon"""
    try:
        # Convert amount to wei (18 decimals)
        amount_wei = int(amount * 10**18)
        
        # Setup contract
        contract = w3.eth.contract(address=WBSP_CONTRACT, abi=WBSP_ABI)
        
        # Get account from private key
        account = w3.eth.account.from_key(private_key)
        
        # Ensure checksum address
        to_address = w3.to_checksum_address(to_address)

        # Build transaction
        nonce = w3.eth.get_transaction_count(account.address)
        
        tx = contract.functions.mint(
            to_address,
            amount_wei,
            bsp_address
        ).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': w3.eth.gas_price
        })
        
        # Sign and send
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return tx_hash.hex(), receipt['status'] == 1
        
    except Exception as e:
        print(f"Error minting wBSP: {e}")
        return None, False

def get_pending_requests():
    """Get pending bridge requests that haven't expired (within 30 min window)"""
    try:
        conn = sqlite3.connect("/root/bridge_requests.db", timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        c = conn.cursor()
        # Expire requests older than 30 minutes
        c.execute("""UPDATE bridge_requests SET status='expired'
                     WHERE status='pending'
                     AND timestamp < datetime('now', '-30 minutes')""")
        conn.commit()
        c.execute("SELECT id, polygon_address, bsp_amount, bsp_from_address, timestamp FROM bridge_requests WHERE status='pending'")
        rows = c.fetchall()
        conn.close()
        return [{'id': r[0], 'polygon_address': r[1], 'bsp_amount': r[2], 'bsp_from_address': r[3], 'timestamp': r[4]} for r in rows]
    except Exception as e:
        print(f"Error getting pending requests: {e}")
        return []

def match_request(tx, pending):
    """Match a BSP transaction to a pending bridge request.
    Primary match: sender BSP address (exact). Amount is secondary.
    Minting uses the actual on-chain amount, not the requested amount."""
    sender = tx.get('from', 'unknown')

    # First pass: match on sender address only — amount doesn't need to match exactly
    if sender and sender != 'unknown':
        for req in pending:
            if req.get('bsp_from_address') and req['bsp_from_address'].strip() == sender.strip():
                return req

    # Second pass: amount-only for legacy requests without bsp_from_address
    for req in pending:
        amount_match = abs(tx['amount'] - req['bsp_amount']) < 0.01
        if amount_match and not req.get('bsp_from_address'):
            return req

    return None

def update_request_status(req_id, bsp_txid, poly_txid, status):
    conn = sqlite3.connect("/root/bridge_requests.db", timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    c = conn.cursor()
    c.execute("UPDATE bridge_requests SET status=?, bsp_txid=?, polygon_txid=? WHERE id=?",
              (status, bsp_txid, poly_txid, req_id))
    conn.commit()
    conn.close()

def process_bridge(tx, private_key):
    """Process a bridge transaction"""
    txid = tx['txid']
    bsp_addr = tx['from']
    amount = tx['amount']

    print(f"[{datetime.now()}] Processing bridge: {amount} BSP from {bsp_addr}")

    pending = get_pending_requests()
    req = match_request(tx, pending)

    if not req:
        print(f"  No matching bridge request found for {amount} BSP — skipping")
        mark_processed(txid, bsp_addr, 'none', amount, 'none', 'skipped')
        return False

    poly_addr = req['polygon_address']

    if is_blacklisted(poly_addr):
        print(f"  ⛔ Blacklisted address {poly_addr} — skipping")
        mark_processed(txid, bsp_addr, poly_addr, amount, 'none', 'blacklisted')
        update_request_status(req['id'], txid, 'none', 'blacklisted')
        return False

    # Mint the actual on-chain amount, not the requested amount
    mint_amount = amount
    print(f"  Matched request #{req['id']} → minting {mint_amount} wBSP to {poly_addr}")

    # Mark as in-progress immediately to prevent re-processing on next loop
    # if the mint call hangs or throws
    try:
        poly_txid, success = mint_wbsp(poly_addr, mint_amount, bsp_addr, private_key)
    except Exception as e:
        print(f"  ❌ Mint exception: {e}")
        mark_processed(txid, bsp_addr, poly_addr, mint_amount, '', 'failed')
        update_request_status(req['id'], txid, '', 'failed')
        return False

    if success:
        mark_processed(txid, bsp_addr, poly_addr, mint_amount, poly_txid, 'completed')
        update_request_status(req['id'], txid, poly_txid, 'completed')
        print(f"  ✅ Minted! Polygon tx: {poly_txid}")
        return True
    else:
        mark_processed(txid, bsp_addr, poly_addr, mint_amount, poly_txid or '', 'failed')
        update_request_status(req['id'], txid, poly_txid or '', 'failed')
        print(f"  ❌ Mint failed")
        return False

def main():
    """Main bridge bot loop"""
    print("=" * 60)
    print("BSP Bridge Bot Starting")
    print("=" * 60)
    print(f"Bridge Address: {BRIDGE_ADDRESS}")
    print(f"wBSP Contract: {WBSP_CONTRACT}")
    print(f"Check Interval: {CHECK_INTERVAL}s")
    print("=" * 60)

    init_db()

    private_key = os.environ.get('BRIDGE_PRIVATE_KEY', '6118c3db407200a298a19305a3ed1af4172a1d04442bf3787fc53c31471a5f92')
    if not private_key:
        print("ERROR: Private key required!")
        return

    # Verify key works
    account = w3.eth.account.from_key(private_key)
    print(f"Minter address: {account.address}")
    print("\nBot running. Press Ctrl+C to stop.\n")

    while True:
        try:
            transactions = get_recent_transactions()
            for tx in transactions:
                if tx.get('txid') and not is_processed(tx['txid']):
                    print(f"New deposit: {tx['amount']} BSP from {tx['from']}")
                    result = process_bridge(tx, private_key)
                    if result:
                        time.sleep(3)  # prevent nonce collisions only after successful mint
                    time.sleep(3)  # prevent nonce collisions

            balance = get_bridge_balance()
            print(f"[{datetime.now()}] Bridge balance: {balance} BSP")
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nShutting down bridge bot...")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
