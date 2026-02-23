from flask import Flask, jsonify, request
from flask_cors import CORS
from chain import Blockchain
from crypto_utils import Wallet
from network import P2PNode
import threading

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
@app.route('/transaction/new', methods=['POST'])
def new_transaction():
    """Create new transaction"""
    data = request.get_json()
    
    required = ['sender_private_key', 'recipient_address', 'amount']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        # Create wallet from private key
        sender_wallet = Wallet.from_private_key(data['sender_private_key'])
        
        # Create transaction
        tx = blockchain.create_transaction(
            sender_wallet,
            data['recipient_address'],
            float(data['amount'])
        )
        
        if not tx:
            return jsonify({'error': 'Insufficient funds'}), 400
        
        # Add to blockchain
        success, error = blockchain.add_transaction(tx)
        if not success:
            return jsonify({'error': error}), 400
        
        # Broadcast to network
        p2p_node.broadcast_transaction(tx)
        
        return jsonify({
            'message': 'Transaction added to mempool',
            'txid': tx.txid
        }), 201
    
    except Exception as e:
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
    
    # Get recent transactions from recent blocks
    transactions = []
    for block in reversed(blockchain.chain[-100:]):  # Last 100 blocks
        for tx in block.transactions:
            # Check if address is in outputs
            for i, output in enumerate(tx.outputs):
                if output.script_pubkey == address:
                    transactions.append({
                        'txid': tx.txid,
                        'block': block.index,
                        'timestamp': tx.timestamp,
                        'type': 'received',
                        'amount': output.amount,
                        'vout': i
                    })
            
            # Check if address spent inputs (non-coinbase only)
            if not tx.is_coinbase():
                for tx_input in tx.inputs:
                    utxo = blockchain.utxo_set.get_utxo(tx_input.txid, tx_input.vout)
                    # Check historical - this won't work for spent UTXOs
                    # For now, skip spent tracking in recent blocks
    
    return jsonify({
        'address': address,
        'balance': balance,
        'utxo_count': len(utxos),
        'transactions': transactions[:50]  # Limit to 50 most recent
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
    
    # Optimized query - get first transaction of each block (coinbase)
    cursor.execute("""
        SELECT 
            o.script_pubkey as address,
            COUNT(*) as blocks_mined,
            SUM(o.amount) as total_rewards
        FROM tx_outputs o
        WHERE o.vout = 0
        AND o.txid IN (
            SELECT t.txid
            FROM transactions t
            WHERE t.txid = (
                SELECT MIN(txid) 
                FROM transactions 
                WHERE block_index = t.block_index
            )
        )
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


if __name__ == '__main__':
    import sys
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    api_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    seed_nodes = sys.argv[3:] if len(sys.argv) > 3 else []
    
    init_node(port, api_port, seed_nodes)
    app.run(host='0.0.0.0', port=api_port, debug=False)
