from flask import Flask, jsonify, request
from flask_cors import CORS
from chain import Blockchain
from crypto_utils import Wallet
from network import P2PNode
import threading
import sqlite3
import hashlib
import uuid
import os
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins

# Global blockchain and network node
blockchain = None
p2p_node = None
node_wallet = None

# Mining lock to prevent concurrent mining
mining_lock = threading.Lock()


def init_node(port: int = 5000, api_port: int = 8000, seed_nodes: list = None, founder_address: str = None):
    """Initialize blockchain node"""
    global blockchain, p2p_node, node_wallet
    
    blockchain = Blockchain(difficulty=4, founder_address=founder_address)
    node_wallet = Wallet()
    p2p_node = P2PNode(blockchain, host="0.0.0.0", port=port, seed_nodes=seed_nodes)
    p2p_node.start()
    
    print(f"Node wallet address: {node_wallet.address}")
    if founder_address:
        print(f"Founder allocation: {blockchain.founder_allocation:,.0f} BSP to {founder_address}")
    return app


# Blockchain endpoints
@app.route('/blockchain', methods=['GET'])
def get_blockchain():
    """Get entire blockchain"""
    # For large blockchains, only return recent blocks
    # Full blockchain is in the database
    chain_data = []
    for block in blockchain.chain:
        chain_data.append(block.to_dict())
    
    actual_height = blockchain.db.get_block_count()
    
    # FIX: Handle None case when database returns None
    if actual_height is None:
        actual_height = len(blockchain.chain)
    
    return jsonify({
        'length': actual_height,
        'chain': chain_data,
        'difficulty': blockchain.difficulty,
        'note': f'Showing {len(blockchain.chain)} most recent blocks. Full blockchain in database.'
    }), 200


@app.route('/blockchain/validate', methods=['GET'])
def validate_blockchain():
    """Validate blockchain integrity"""
    is_valid = blockchain.is_chain_valid()
    return jsonify({
        'valid': is_valid
    }), 200


@app.route('/block/<int:index>', methods=['GET'])
def get_block(index):
    """Get specific block by index"""
    if index < 0 or index >= len(blockchain.chain):
        return jsonify({'error': 'Block not found'}), 404
    
    block = blockchain.chain[index]
    return jsonify(block.to_dict()), 200


@app.route('/block/latest', methods=['GET'])
def get_latest_block():
    """Get latest block"""
    block = blockchain.get_latest_block()
    return jsonify(block.to_dict()), 200


# Transaction endpoints
MAX_INPUTS_PER_TX = 150  # safe limit well under 1MB JSON

@app.route('/transaction/new', methods=['POST'])
def new_transaction():
    """Create new transaction - auto-batches large UTXO sets in background"""
    data = request.get_json()

    required = ['sender_private_key', 'recipient_address', 'amount']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        from transaction import Transaction, TxInput, TxOutput
        import time as _time
        import threading

        sender_wallet = Wallet.from_private_key(data['sender_private_key'])
        amount = float(data['amount'])
        recipient_address = data['recipient_address']
        memo = str(data.get('memo', ''))[:64]  # cap at 64 chars

        # Exclude UTXOs already spent by pending mempool transactions
        mempool_spent = {
            (inp.txid, inp.vout)
            for tx in blockchain.pending_transactions
            for inp in tx.inputs
        }
        all_utxos = [
            u for u in blockchain.utxo_set.get_utxos_for_address(sender_wallet.address)
            if (u.txid, u.vout) not in mempool_spent
        ]
        total_balance = sum(u.amount for u in all_utxos)

        if total_balance < amount:
            return jsonify({'error': f'Insufficient funds. Balance: {total_balance}, requested: {amount}'}), 400

        def build_and_sign_tx(batch_utxos, to_address, send_amount):
            total_in = sum(u.amount for u in batch_utxos)
            inputs = [TxInput(txid=u.txid, vout=u.vout, script_sig="") for u in batch_utxos]
            outputs = [TxOutput(amount=send_amount, script_pubkey=to_address)]
            change = round(total_in - send_amount, 8)
            if change > 0.00000001:
                outputs.append(TxOutput(amount=change, script_pubkey=sender_wallet.address))
            tx = Transaction(inputs, outputs, memo=memo)
            for i, tx_input in enumerate(tx.inputs):
                sig = sender_wallet.sign(tx.get_signing_data(i))
                tx_input.script_sig = sig.hex() + ":" + sender_wallet.get_public_key_hex()
            return tx

        def submit_tx(tx):
            success, error = blockchain.add_transaction(tx)
            if not success:
                return False, error
            p2p_node.broadcast_transaction(tx)
            return True, None

        # Select only UTXOs needed to cover amount
        selected = []
        running = 0.0
        for u in all_utxos:
            selected.append(u)
            running += u.amount
            if running >= amount:
                break

        # Single batch — process immediately and return
        if len(selected) <= MAX_INPUTS_PER_TX:
            tx = build_and_sign_tx(selected, recipient_address, amount)
            ok, err = submit_tx(tx)
            if not ok:
                return jsonify({'error': err}), 400
            return jsonify({'message': 'Transaction added to mempool', 'txid': tx.txid}), 201

        # Multiple batches needed — run in background, return immediately
        # Build first batch tx now to get a txid to return to the user
        batches = [selected[i:i+MAX_INPUTS_PER_TX] for i in range(0, len(selected), MAX_INPUTS_PER_TX)]
        first_batch = batches[0]
        first_tx = build_and_sign_tx(first_batch, sender_wallet.address, round(sum(u.amount for u in first_batch), 8))
        ok, err = submit_tx(first_tx)
        if not ok:
            return jsonify({'error': f'Transaction failed: {err}'}), 400

        # Process remaining batches + final send in background
        def process_remaining(remaining_batches, final_amount, final_recipient, wallet):
            try:
                for i, batch in enumerate(remaining_batches[:-1]):
                    _time.sleep(0.5)
                    batch_total = round(sum(u.amount for u in batch), 8)
                    tx = build_and_sign_tx(batch, wallet.address, batch_total)
                    submit_tx(tx)

                # Final send — re-fetch UTXOs to get consolidated ones
                _time.sleep(1.0)
                fresh_utxos = blockchain.utxo_set.get_utxos_for_address(wallet.address)
                fresh_mempool_spent = {
                    (inp.txid, inp.vout)
                    for tx in blockchain.pending_transactions
                    for inp in tx.inputs
                }
                fresh_utxos = [u for u in fresh_utxos if (u.txid, u.vout) not in fresh_mempool_spent]
                fresh_selected = []
                fresh_running = 0.0
                for u in fresh_utxos:
                    fresh_selected.append(u)
                    fresh_running += u.amount
                    if fresh_running >= final_amount:
                        break
                if fresh_running >= final_amount:
                    final_tx = build_and_sign_tx(fresh_selected[:MAX_INPUTS_PER_TX], final_recipient, final_amount)
                    submit_tx(final_tx)
                    print(f"Background batch complete. Final txid: {final_tx.txid}")
            except Exception as e:
                print(f"Background batch error: {e}")
                import traceback; traceback.print_exc()

        t = threading.Thread(target=process_remaining, args=(batches[1:], amount, recipient_address, sender_wallet), daemon=True)
        t.start()

        return jsonify({
            'message': 'Transaction processing — funds will arrive shortly',
            'txid': first_tx.txid,
            'note': 'Large balance requires batch processing, completing in background'
        }), 201

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 400


@app.route('/transactions/pending', methods=['GET'])
def get_pending_transactions():
    """Get pending transactions"""
    pending = []
    for tx in blockchain.pending_transactions:
        pending.append(tx.to_dict())
    
    return jsonify({
        'count': len(pending),
        'transactions': pending
    }), 200


# Mining endpoints
@app.route('/mine', methods=['POST'])
def mine_block():
    """Mine endpoint - returns work template for client-side PoW.
    Miners must solve the PoW and submit via /mine/submit"""
    data = request.get_json()
    miner_address = data.get('miner_address', node_wallet.address)

    actual_height = blockchain.db.get_block_count()
    latest_block = blockchain.db.get_latest_block_from_db() or blockchain.get_latest_block()
    reward = blockchain.get_current_mining_reward()

    from transaction import Transaction
    coinbase_tx = Transaction.create_coinbase(miner_address, reward, actual_height)
    transactions = [coinbase_tx] + blockchain.pending_transactions

    return jsonify({
        'message': 'Work template - solve PoW and submit to /mine/submit',
        'work': {
            'block_index': actual_height,
            'previous_hash': latest_block.hash,
            'difficulty': blockchain.difficulty,
            'transactions': [tx.to_dict() for tx in transactions],
            'reward': reward,
            'miner_address': miner_address
        }
    }), 200


@app.route('/mine/work', methods=['POST'])
def get_mining_work():
    """Get block template for external mining - returns instantly"""
    data = request.get_json()
    miner_address = data.get('miner_address', node_wallet.address)

    actual_height = blockchain.db.get_block_count()
    latest_block = blockchain.db.get_latest_block_from_db() or blockchain.get_latest_block()
    reward = blockchain.get_current_mining_reward()

    from transaction import Transaction
    coinbase_tx = Transaction.create_coinbase(miner_address, reward, actual_height)
    transactions = [coinbase_tx] + blockchain.pending_transactions

    return jsonify({
        'block_index': actual_height,
        'previous_hash': latest_block.hash,
        'difficulty': blockchain.difficulty,
        'transactions': [tx.to_dict() for tx in transactions],
        'reward': reward,
        'miner_address': miner_address
    }), 200


@app.route('/mine/submit', methods=['POST'])
def submit_mined_block():
    """Submit a solved block - fast commit, no PoW"""
    data = request.get_json()
    if not data or 'block' not in data:
        return jsonify({'error': 'Missing block data'}), 400

    try:
        from blockchain import Block
        from transaction import Transaction, TxInput, TxOutput

        block_data = data['block']

        # Reconstruct transactions
        transactions = []
        for tx_data in block_data.get('transactions', []):
            inputs = [TxInput(i['txid'], i['vout'], i['script_sig'], i.get('sequence', 4294967295))
                      for i in tx_data.get('inputs', [])]
            outputs = [TxOutput(o['amount'], o['script_pubkey'])
                       for o in tx_data.get('outputs', [])]
            tx = Transaction(inputs, outputs)
            tx.txid = tx_data['txid']
            tx.timestamp = tx_data.get('timestamp', 0)
            transactions.append(tx)

        # Reconstruct block
        block = Block(
            block_data['index'],
            transactions,
            block_data['previous_hash'],
            block_data['difficulty']
        )
        block.timestamp = block_data['timestamp']
        block.nonce = block_data['nonce']
        block.merkle_root = block_data['merkle_root']
        block.hash = block_data['hash']

        if blockchain.add_block(block):
            # Clear any pending transactions that were included in this block
            included_txids = {tx.txid for tx in transactions if not tx.is_coinbase()}
            blockchain.pending_transactions = [
                tx for tx in blockchain.pending_transactions
                if tx.txid not in included_txids
            ]
            p2p_node.broadcast_block(block)
            return jsonify({
                'message': 'Block accepted',
                'block_index': block.index
            }), 200
        else:
            return jsonify({'error': 'Block rejected'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 400


# Wallet endpoints
@app.route('/wallet/new', methods=['POST'])
def create_wallet():
    """Create new wallet"""
    wallet = Wallet()
    return jsonify({
        'address': wallet.address,
        'private_key': wallet.get_private_key_hex(),
        'public_key': wallet.get_public_key_hex()
    }), 201


@app.route('/wallet/derive', methods=['POST'])
def derive_wallet():
    """Derive wallet address from private key"""
    data = request.get_json()
    
    if 'private_key' not in data:
        return jsonify({'error': 'Missing private_key'}), 400
    
    try:
        wallet = Wallet.from_private_key(data['private_key'])
        return jsonify({
            'address': wallet.address,
            'public_key': wallet.get_public_key_hex()
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/wallet/balance/<address>', methods=['GET'])
def get_balance(address):
    """Get wallet balance"""
    balance = blockchain.get_balance(address)
    utxos = blockchain.utxo_set.get_utxos_for_address(address)
    
    return jsonify({
        'address': address,
        'balance': balance,
        'utxo_count': len(utxos)
    }), 200


@app.route('/wallet/utxos/<address>', methods=['GET'])
def get_utxos(address):
    """Get UTXOs for address"""
    utxos = blockchain.utxo_set.get_utxos_for_address(address)
    utxos_data = [utxo.to_dict() for utxo in utxos]
    
    return jsonify({
        'address': address,
        'utxos': utxos_data
    }), 200


@app.route('/address/<address>', methods=['GET'])
def get_address_info(address):
    """Get complete address information including balance and recent transactions"""
    # Get balance and UTXOs
    balance = blockchain.get_balance(address)
    utxos = blockchain.utxo_set.get_utxos_for_address(address)
    
    # Get recent transactions from database
    transactions = []
    try:
        conn = blockchain.db.conn
        cursor = conn.cursor()
        
        # Query transactions where address received coins
        cursor.execute("""
            SELECT b.block_index, t.txid, t.timestamp, o.amount, o.vout, t.memo
            FROM transactions t
            JOIN blocks b ON t.block_index = b.block_index
            JOIN tx_outputs o ON t.txid = o.txid
            WHERE o.script_pubkey = ?
            ORDER BY b.block_index DESC
            LIMIT 50
        """, (address,))
        
        rows = cursor.fetchall()
        print(f"Found {len(rows)} transactions for {address}")
        
        for row in rows:
            txid = row[1]
            
            # Get sender address (from first input)
            from_address = None
            cursor.execute("""
                SELECT prev_out.script_pubkey
                FROM tx_inputs i
                JOIN tx_outputs prev_out ON i.prev_txid = prev_out.txid AND i.vout = prev_out.vout
                WHERE i.txid = ?
                LIMIT 1
            """, (txid,))
            sender_row = cursor.fetchone()
            if sender_row:
                from_address = sender_row[0]
            
            transactions.append({
                'txid': row[1],
                'block': row[0],
                'timestamp': row[2],
                'type': 'received',
                'amount': row[3],
                'vout': row[4],
                'from': from_address or 'Coinbase',
                'memo': row[5] or ''
            })
    except Exception as e:
        print(f"Error fetching transactions for {address}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            cursor.close()
        except:
            pass
    
    return jsonify({
        'address': address,
        'balance': balance,
        'utxo_count': len(utxos),
        'transactions': transactions
    }), 200


# Network endpoints
@app.route('/peers', methods=['GET'])
def get_peers():
    """Get connected peers"""
    peers_list = [str(peer) for peer in p2p_node.peers]
    return jsonify({
        'count': len(peers_list),
        'peers': peers_list
    }), 200


@app.route('/peers/sync', methods=['POST'])
def sync_peers():
    """Sync blockchain with peers"""
    p2p_node.sync_blockchain()
    return jsonify({'message': 'Sync initiated'}), 200


# Node info endpoints
@app.route('/info', methods=['GET'])
def get_info():
    """Get node information"""
    # Get actual blockchain height from database
    actual_height = blockchain.db.get_block_count()
    
    # FIX: Handle None case when database returns None
    if actual_height is None:
        actual_height = len(blockchain.chain)
    
    return jsonify({
        'currency': 'Bespin',
        'symbol': 'BSP',
        'tagline': 'Fast, Secure Peer-to-Peer Cryptocurrency',
        'node_address': node_wallet.address,
        'blockchain_height': actual_height,
        'difficulty': blockchain.difficulty,
        'pending_transactions': len(blockchain.pending_transactions),
        'connected_peers': len(p2p_node.peers),
        'mining_reward': blockchain.get_current_mining_reward(),
        'max_supply': blockchain.max_supply,
        'circulating_supply': blockchain.get_circulating_supply(),
        'remaining_supply': blockchain.get_remaining_supply(),
        'founder_allocation': blockchain.founder_allocation,
        'mining_allocation': blockchain.mining_allocation
    }), 200


@app.route('/price', methods=['GET'])
def get_price():
    """Get current BSP price in USD from CoinGecko, fallback to $0.01"""
    import requests as req
    try:
        r = req.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=bespincoin&vs_currencies=usd',
            timeout=5
        )
        usd = r.json()['bespincoin']['usd']
    except Exception:
        usd = 0.01  # fallback until CoinGecko has data
    return jsonify({'usd': usd, 'symbol': 'BSP'}), 200


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


@app.route('/stats/miners', methods=['GET'])
def get_miner_stats():
    """Get mining statistics - unique miners and distribution"""
    cursor = blockchain.db.conn.cursor()
    
    # Create index if it doesn't exist (one-time operation)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tx_block ON transactions(block_index)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_output_txid ON tx_outputs(txid, vout)
    """)
    
    # Get coinbase outputs: rowid=1 per block (coinbase is always inserted first)
    cursor.execute("""
        SELECT 
            o.script_pubkey as address,
            COUNT(*) as blocks_mined,
            SUM(o.amount) as total_rewards
        FROM tx_outputs o
        INNER JOIN (
            SELECT MIN(rowid) as min_rowid
            FROM transactions
            GROUP BY block_index
        ) cb ON o.txid = (SELECT txid FROM transactions WHERE rowid = cb.min_rowid)
        WHERE o.vout = 0
        GROUP BY o.script_pubkey
        ORDER BY blocks_mined DESC
        LIMIT 100
    """)
    
    miners = []
    for row in cursor.fetchall():
        address, blocks_mined, total_rewards = row
        miners.append({
            'address': address,
            'blocks_mined': blocks_mined,
            'total_rewards': total_rewards
        })
    
    total_blocks = blockchain.db.get_block_count()
    
    # FIX: Handle None case when database returns None
    if total_blocks is None:
        total_blocks = len(blockchain.chain)
    
    return jsonify({
        'total_miners': len(miners),
        'total_blocks': total_blocks,
        'miners': miners
    }), 200


# Payment endpoints
import uuid
import time as time_module

# In-memory payment store (keyed by payment_id)
payments = {}

@app.route('/payment/create', methods=['POST'])
def create_payment():
    """Create a payment request for merchants"""
    data = request.get_json()
    required = ['merchant_address', 'amount', 'description']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields: merchant_address, amount, description'}), 400

    payment_id = str(uuid.uuid4())
    payment = {
        'id': payment_id,
        'merchant_address': data['merchant_address'],
        'amount': float(data['amount']),
        'description': data['description'],
        'status': 'pending',
        'created_at': time_module.time(),
        'expires_at': time_module.time() + 3600,  # 1 hour expiry
        'paid_txid': None
    }
    payments[payment_id] = payment

    return jsonify({
        'payment_id': payment_id,
        'payment_url': f'https://api.bespincoin.com/pay/{payment_id}',
        'merchant_address': payment['merchant_address'],
        'amount': payment['amount'],
        'description': payment['description'],
        'expires_at': payment['expires_at']
    }), 201


@app.route('/payment/<payment_id>', methods=['GET'])
def get_payment(payment_id):
    """Get payment status"""
    payment = payments.get(payment_id)
    if not payment:
        return jsonify({'error': 'Payment not found'}), 404

    # Check if expired
    if time_module.time() > payment['expires_at'] and payment['status'] == 'pending':
        payment['status'] = 'expired'

    if payment['status'] == 'pending':
        # Check mempool first - instant detection
        for tx in blockchain.pending_transactions:
            for output in tx.outputs:
                if output.script_pubkey == payment['merchant_address'] and output.amount >= payment['amount']:
                    payment['status'] = 'detected'
                    payment['paid_txid'] = tx.txid
                    break

    # Check UTXO set - merchant has a UTXO >= amount means payment confirmed
    if payment['status'] in ('pending', 'detected'):
        txid, _ = blockchain.db.find_payment_tx(
            payment['merchant_address'],
            payment['amount'],
            payment['created_at']
        )
        if txid:
            payment['status'] = 'confirmed'
            payment['paid_txid'] = txid

    return jsonify(payment), 200


@app.route('/pay/<payment_id>', methods=['GET'])
def payment_page(payment_id):
    """Hosted payment page - redirect merchants here"""
    payment = payments.get(payment_id)
    if not payment:
        return "Payment not found", 404

    if time_module.time() > payment['expires_at']:
        return "Payment expired", 410

    amount = payment['amount']
    address = payment['merchant_address']
    description = payment['description']

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pay with BSP</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }}
  .card {{ background: #1a1a2e; border: 1px solid #16213e; border-radius: 16px; padding: 40px; max-width: 420px; width: 100%; text-align: center; }}
  .logo {{ font-size: 2rem; margin-bottom: 8px; }}
  h1 {{ font-size: 1.4rem; color: #e2b96f; margin-bottom: 4px; }}
  .desc {{ color: #888; font-size: 0.9rem; margin-bottom: 24px; }}
  .amount {{ font-size: 2.5rem; font-weight: bold; color: #e2b96f; margin-bottom: 4px; }}
  .amount span {{ font-size: 1rem; color: #888; }}
  .address-label {{ color: #888; font-size: 0.8rem; margin: 20px 0 6px; }}
  .address {{ background: #0a0a0a; border: 1px solid #333; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 0.8rem; word-break: break-all; color: #e2b96f; }}
  .copy-btn {{ margin-top: 12px; background: #e2b96f; color: #0a0a0a; border: none; border-radius: 8px; padding: 12px 24px; font-size: 1rem; font-weight: bold; cursor: pointer; width: 100%; }}
  .copy-btn:hover {{ background: #f0c97f; }}
  .status {{ margin-top: 20px; padding: 12px; border-radius: 8px; font-size: 0.9rem; }}
  .status.pending {{ background: #1a1a00; color: #ffcc00; border: 1px solid #ffcc0033; }}
  .status.paid {{ background: #001a00; color: #00ff88; border: 1px solid #00ff8833; }}
  .powered {{ margin-top: 24px; color: #444; font-size: 0.75rem; }}
  .powered a {{ color: #e2b96f; text-decoration: none; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">🪙</div>
  <h1>Pay with Bespin Coin</h1>
  <p class="desc">{description}</p>
  <div class="amount">{amount} <span>BSP</span></div>
  <p class="address-label">Send BSP to this address:</p>
  <div class="address" id="addr">{address}</div>
  <button class="copy-btn" onclick="copyAddress()">Copy Address</button>
  <div class="status pending" id="status">⏳ Waiting for payment...</div>
  <p class="powered">Powered by <a href="https://bespincoin.com">BespinCoin.com</a></p>
</div>
<script>
  function copyAddress() {{
    navigator.clipboard.writeText('{address}');
    document.querySelector('.copy-btn').textContent = 'Copied!';
    setTimeout(() => document.querySelector('.copy-btn').textContent = 'Copy Address', 2000);
  }}
  // Poll for payment status
  setInterval(async () => {{
    const res = await fetch('/payment/{payment_id}');
    const data = await res.json();
    if (data.status === 'paid') {{
      document.getElementById('status').className = 'status paid';
      document.getElementById('status').textContent = '✅ Payment confirmed!';
    }}
  }}, 5000);
</script>
</body>
</html>"""
    return html


# ── Merchant API Endpoints ───────────────────────────────────────────────────

MERCHANT_DB = "/root/merchant.db"

def get_merchant_db():
    conn = sqlite3.connect(MERCHANT_DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_merchant_db():
    with get_merchant_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS merchants (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                bsp_address TEXT NOT NULL,
                webhook_url TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS merchant_payments (
                id TEXT PRIMARY KEY,
                merchant_id TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                bsp_address TEXT NOT NULL,
                txid TEXT,
                created_at REAL DEFAULT (strftime('%s','now')),
                expires_at REAL,
                confirmed_at REAL,
                FOREIGN KEY (merchant_id) REFERENCES merchants(id)
            )
        """)

init_merchant_db()

def generate_merchant_api_key():
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()

@app.route('/merchant/register', methods=['POST'])
def register_merchant():
    data = request.get_json()
    required = ['email', 'bsp_address']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields: email, bsp_address'}), 400
    
    merchant_id = str(uuid.uuid4())
    api_key = generate_merchant_api_key()
    
    try:
        with get_merchant_db() as db:
            db.execute(
                "INSERT INTO merchants (id, email, api_key, bsp_address, webhook_url) VALUES (?,?,?,?,?)",
                (merchant_id, data['email'], api_key, data['bsp_address'], data.get('webhook_url'))
            )
        return jsonify({
            'merchant_id': merchant_id,
            'api_key': api_key,
            'message': 'Merchant registered successfully'
        }), 201
    except Exception as e:
        return jsonify({'error': 'Email already registered'}), 400

@app.route('/merchant/info', methods=['GET'])
def get_merchant_info():
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 401
    
    with get_merchant_db() as db:
        merchant = db.execute("SELECT * FROM merchants WHERE api_key=?", (api_key,)).fetchone()
    
    if not merchant:
        return jsonify({'error': 'Invalid API key'}), 401
    
    return jsonify({
        'merchant_id': merchant['id'],
        'email': merchant['email'],
        'bsp_address': merchant['bsp_address'],
        'webhook_url': merchant['webhook_url'],
        'created_at': merchant['created_at']
    }), 200

@app.route('/merchant/payments', methods=['GET'])
def list_merchant_payments():
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'Missing API key'}), 401
    
    with get_merchant_db() as db:
        merchant = db.execute("SELECT * FROM merchants WHERE api_key=?", (api_key,)).fetchone()
        if not merchant:
            return jsonify({'error': 'Invalid API key'}), 401
        
        limit = request.args.get('limit', 50, type=int)
        payments_list = db.execute(
            "SELECT * FROM merchant_payments WHERE merchant_id=? ORDER BY created_at DESC LIMIT ?",
            (merchant['id'], limit)
        ).fetchall()
    
    return jsonify({'payments': [dict(p) for p in payments_list]}), 200


# Bridge endpoints
import sqlite3 as _sqlite3

BRIDGE_DB = '/root/bridge_requests.db'

def _init_bridge_db():
    conn = _sqlite3.connect(BRIDGE_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS bridge_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  polygon_address TEXT, bsp_amount REAL,
                  bsp_from_address TEXT, email TEXT,
                  timestamp TEXT, status TEXT DEFAULT 'pending',
                  bsp_txid TEXT, polygon_txid TEXT)''')
    conn.commit()
    conn.close()

_init_bridge_db()

@app.route('/bridge/request', methods=['POST', 'OPTIONS'])
def bridge_request():
    if request.method == 'OPTIONS':
        r = app.make_default_options_response()
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return r
    data = request.get_json()
    poly = data.get('polygon_address', '').strip()
    amount = data.get('bsp_amount')
    bsp_from = data.get('bsp_from_address', '').strip()
    if not poly or not amount:
        return jsonify({'error': 'Missing required fields'}), 400

    # Admin key bypasses all limits
    admin_key = data.get('admin_key', '')
    bridge_admin_key = os.environ.get('BRIDGE_ADMIN_KEY', '')
    is_admin = bridge_admin_key and admin_key == bridge_admin_key

    if float(amount) < 1:
        return jsonify({'error': 'Minimum bridge amount is 1 BSP'}), 400
    if not is_admin and float(amount) > 500:
        return jsonify({'error': 'Maximum bridge amount is 500 BSP per request'}), 400
    # Check daily limit per BSP address (500 BSP per wallet per day)
    if not is_admin and bsp_from:
        from datetime import datetime as _dt
        today = _dt.utcnow().strftime('%Y-%m-%d')
        conn_check = _sqlite3.connect(BRIDGE_DB)
        row = conn_check.execute(
            "SELECT COALESCE(SUM(bsp_amount),0) FROM bridge_requests WHERE bsp_from_address=? AND timestamp LIKE ? AND status != 'rejected'",
            (bsp_from, today + '%')
        ).fetchone()
        conn_check.close()
        daily_total = row[0] if row else 0
        if daily_total + float(amount) > 500:
            remaining = max(0, 500 - daily_total)
            return jsonify({'error': f'Daily limit of 500 BSP per wallet reached. You have {remaining:.0f} BSP remaining today.'}), 400
    conn = _sqlite3.connect(BRIDGE_DB)
    c = conn.cursor()
    c.execute("INSERT INTO bridge_requests (polygon_address, bsp_amount, bsp_from_address, timestamp, status) VALUES (?,?,?,?,?)",
              (poly, float(amount), bsp_from, datetime.utcnow().isoformat(), 'pending'))
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    bridge_address = os.environ.get('BRIDGE_ADDRESS', '1BEdzEJXqAcfWpZDK3ePJiCAcjUL4rnMVw')
    r = jsonify({'request_id': req_id, 'bridge_address': bridge_address, 'status': 'pending'})
    r.headers['Access-Control-Allow-Origin'] = '*'
    return r

@app.route('/bridge/status/<int:req_id>', methods=['GET'])
def bridge_status(req_id):
    conn = _sqlite3.connect(BRIDGE_DB)
    row = conn.execute("SELECT id, polygon_address, bsp_amount, status, bsp_txid, polygon_txid FROM bridge_requests WHERE id=?", (req_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'id': row[0], 'polygon_address': row[1], 'bsp_amount': row[2], 'status': row[3], 'bsp_txid': row[4], 'polygon_txid': row[5]})


# ── SitRep / AI Daily Summary ─────────────────────────────────────────────────
import time as _time_module

_sitrep_cache = {'data': None, 'ts': 0}
SITREP_TTL = 3600  # regenerate every hour
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

@app.route('/sitrep', methods=['GET'])
def sitrep():
    global _sitrep_cache
    now = _time_module.time()

    # Return cached if fresh
    if _sitrep_cache['data'] and (now - _sitrep_cache['ts']) < SITREP_TTL:
        r = jsonify(_sitrep_cache['data'])
        r.headers['Access-Control-Allow-Origin'] = '*'
        return r

    try:
        import requests as _req

        # Gather live stats
        height = blockchain.db.get_block_count() or len(blockchain.chain)
        reward = blockchain.get_current_mining_reward()
        supply = blockchain.get_circulating_supply()
        pending = len(blockchain.pending_transactions)
        max_supply = blockchain.max_supply

        # Recent mining activity — blocks in last hour
        try:
            cursor = blockchain.db.conn.cursor()
            one_hour_ago = _time_module.time() - 3600
            cursor.execute("SELECT COUNT(*) FROM blocks WHERE timestamp > ?", (one_hour_ago,))
            blocks_last_hour = cursor.fetchone()[0]
        except:
            blocks_last_hour = 0

        prompt = f"""You are the Bespin Coin (BSP) daily analyst. Write a concise 3-sentence "SitRep" (Situation Report) for the Bespin community based on these live stats:

- Block height: {height:,}
- Circulating supply: {supply:,.0f} BSP ({(supply/max_supply*100):.1f}% of max supply)
- Current block reward: {reward} BSP
- Pending transactions: {pending}
- Blocks mined in last hour: {blocks_last_hour}
- BSP price: $0.01 USD
- wBSP bridge: live on Polygon, 500 BSP/day limit
- QuickSwap liquidity pool: launching 25th March 2026

Also give a "vibe score" from 0-100 representing overall network health and momentum.

Format your response as JSON exactly like this:
{{"score": 72, "summary": "Your 3-sentence summary here."}}

Keep it punchy, informative, and community-friendly. No markdown, just the JSON."""

        resp = _req.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {OPENAI_API_KEY}', 'Content-Type': 'application/json'},
            json={
                'model': 'gpt-4o-mini',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 200,
                'temperature': 0.7
            },
            timeout=15
        )
        content = resp.json()['choices'][0]['message']['content'].strip()
        # Parse JSON from response
        import json as _json
        result = _json.loads(content)
        result['generated_at'] = datetime.utcnow().isoformat()
        result['block_height'] = height
        result['cached'] = False

        _sitrep_cache = {'data': result, 'ts': now}

    except Exception as e:
        # Fallback if OpenAI fails
        result = {
            'score': 70,
            'summary': f'Bespin network is running smoothly at block {height:,}. Mining continues at {reward} BSP per block with {supply:,.0f} BSP in circulation. The wBSP bridge is live on Polygon with QuickSwap liquidity launching 25th March 2026.',
            'generated_at': datetime.utcnow().isoformat(),
            'block_height': height,
            'cached': False,
            'fallback': True
        }
        _sitrep_cache = {'data': result, 'ts': now}

    r = jsonify(result)
    r.headers['Access-Control-Allow-Origin'] = '*'
    return r

if __name__ == '__main__':
    import sys
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    api_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    seed_nodes = sys.argv[3:] if len(sys.argv) > 3 else []
    
    init_node(port, api_port, seed_nodes)
    app.run(host='0.0.0.0', port=api_port, debug=False)
