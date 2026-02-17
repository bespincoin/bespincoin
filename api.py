from flask import Flask, jsonify, request
from flask_cors import CORS
from chain import Blockchain
from crypto_utils import Wallet
from network import P2PNode
import threading

app = Flask(__name__)
CORS(app)

# Global blockchain and network node
blockchain = None
p2p_node = None
node_wallet = None


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
    """Mine a new block"""
    data = request.get_json()
    miner_address = data.get('miner_address', node_wallet.address)
    
    success = blockchain.mine_pending_transactions(miner_address)
    
    if success:
        latest_block = blockchain.get_latest_block()
        
        # Broadcast new block to network
        p2p_node.broadcast_block(latest_block)
        
        return jsonify({
            'message': 'Block mined successfully',
            'block': latest_block.to_dict()
        }), 200
    else:
        return jsonify({'error': 'Mining failed'}), 400


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
    
    # Optimized single query to get miner stats
    cursor.execute("""
        SELECT 
            o.script_pubkey as address,
            COUNT(*) as blocks_mined,
            SUM(o.amount) as total_rewards
        FROM tx_outputs o
        JOIN transactions t ON o.txid = t.txid
        WHERE o.vout = 0
        AND t.txid IN (
            SELECT MIN(txid) 
            FROM transactions 
            GROUP BY block_index
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
    
    return jsonify({
        'total_miners': len(miners),
        'total_blocks': total_blocks,
        'miners': miners
    }), 200


if __name__ == '__main__':
    import sys
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    api_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    seed_nodes = sys.argv[3:] if len(sys.argv) > 3 else []
    
    init_node(port, api_port, seed_nodes)
    app.run(host='0.0.0.0', port=api_port, debug=False)
