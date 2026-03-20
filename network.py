import socket
import json
import threading
import time
from typing import List, Set, Optional, Dict
from blockchain import Block
from transaction import Transaction
from chain import Blockchain


class Message:
    """Network message types"""
    NEW_BLOCK = "NEW_BLOCK"
    NEW_TRANSACTION = "NEW_TRANSACTION"
    GET_BLOCKS = "GET_BLOCKS"
    BLOCKS_RESPONSE = "BLOCKS_RESPONSE"
    GET_PEERS = "GET_PEERS"
    PEERS_RESPONSE = "PEERS_RESPONSE"
    PING = "PING"
    PONG = "PONG"


class Peer:
    """Represents a network peer"""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.last_seen = time.time()
    
    def __eq__(self, other):
        return self.host == other.host and self.port == other.port
    
    def __hash__(self):
        return hash(f"{self.host}:{self.port}")
    
    def __str__(self):
        return f"{self.host}:{self.port}"


class P2PNode:
    """Peer-to-peer network node"""
    
    def __init__(self, blockchain: Blockchain, host: str = "0.0.0.0", 
                 port: int = 5000, seed_nodes: List[str] = None):
        self.blockchain = blockchain
        self.host = host
        self.port = port
        self.peers: Set[Peer] = set()
        self.seed_nodes = seed_nodes or []
        self.running = False
        self.server_socket = None
        
    def start(self):
        """Start the P2P node"""
        self.running = True
        
        # Start server to accept connections
        server_thread = threading.Thread(target=self._start_server, daemon=True)
        server_thread.start()
        
        # Connect to seed nodes
        self._connect_to_seeds()
        
        # Start peer discovery
        discovery_thread = threading.Thread(target=self._peer_discovery_loop, daemon=True)
        discovery_thread.start()
        
        print(f"P2P Node started on {self.host}:{self.port}")
    
    def stop(self):
        """Stop the P2P node"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
    
    def _start_server(self):
        """Start listening for incoming connections"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                thread = threading.Thread(
                    target=self._handle_peer,
                    args=(client_socket, address),
                    daemon=True
                )
                thread.start()
            except:
                break
    
    def _handle_peer(self, client_socket: socket.socket, address):
        """Handle incoming peer connection"""
        try:
            data = client_socket.recv(4096).decode('utf-8')
            if data:
                message = json.loads(data)
                response = self._process_message(message, address)
                if response:
                    client_socket.send(json.dumps(response).encode('utf-8'))
        except Exception as e:
            print(f"Error handling peer {address}: {e}")
        finally:
            client_socket.close()
    
    def _process_message(self, message: dict, address) -> Optional[dict]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        if msg_type == Message.PING:
            return {'type': Message.PONG}
        
        elif msg_type == Message.GET_PEERS:
            peers_list = [str(peer) for peer in self.peers]
            return {'type': Message.PEERS_RESPONSE, 'peers': peers_list}
        
        elif msg_type == Message.GET_BLOCKS:
            start_index = message.get('start_index', 0)
            limit = min(message.get('limit', 500), 500)  # max 500 blocks per request
            blocks_data = []
            total_height = self.blockchain.db.get_block_count() or 0
            end_index = min(start_index + limit, total_height)
            for idx in range(start_index, end_index):
                try:
                    txs = self.blockchain.db.load_transactions_for_block(idx)
                    cursor = self.blockchain.db.conn.cursor()
                    cursor.execute(
                        "SELECT block_index, previous_hash, hash, nonce, timestamp, difficulty, merkle_root "
                        "FROM blocks WHERE block_index=?", (idx,)
                    )
                    row = cursor.fetchone()
                    if row:
                        blocks_data.append({
                            'index': row[0],
                            'previous_hash': row[1],
                            'hash': row[2],
                            'nonce': row[3],
                            'timestamp': row[4],
                            'difficulty': row[5],
                            'merkle_root': row[6],
                            'transactions': [tx.to_dict() for tx in txs]
                        })
                except Exception as e:
                    print(f"Error serialising block {idx}: {e}")
                    break
            return {'type': Message.BLOCKS_RESPONSE, 'blocks': blocks_data, 'total_height': total_height}
        
        elif msg_type == Message.NEW_BLOCK:
            block_data = message.get('block')
            if not block_data:
                return None
            try:
                from transaction import TxInput, TxOutput
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
                if self.blockchain.add_block(block):
                    print(f"Accepted block {block.index} from peer {address}")
                    # Remove included txs from mempool
                    included = {tx.txid for tx in transactions if not tx.is_coinbase()}
                    self.blockchain.pending_transactions = [
                        t for t in self.blockchain.pending_transactions
                        if t.txid not in included
                    ]
                else:
                    print(f"Rejected block {block_data.get('index')} from peer {address}")
            except Exception as e:
                print(f"Error processing NEW_BLOCK from {address}: {e}")

        elif msg_type == Message.NEW_TRANSACTION:
            tx_data = message.get('transaction')
            if not tx_data:
                return None
            try:
                from transaction import TxInput, TxOutput
                inputs = [TxInput(i['txid'], i['vout'], i['script_sig'], i.get('sequence', 4294967295))
                          for i in tx_data.get('inputs', [])]
                outputs = [TxOutput(o['amount'], o['script_pubkey'])
                           for o in tx_data.get('outputs', [])]
                tx = Transaction(inputs, outputs)
                tx.txid = tx_data['txid']
                tx.timestamp = tx_data.get('timestamp', 0)
                # Only add if not already in mempool
                existing_ids = {t.txid for t in self.blockchain.pending_transactions}
                if tx.txid not in existing_ids:
                    self.blockchain.pending_transactions.append(tx)
                    print(f"Added tx {tx.txid[:16]}... from peer {address} to mempool")
            except Exception as e:
                print(f"Error processing NEW_TRANSACTION from {address}: {e}")
        
        return None
    
    def _connect_to_seeds(self):
        """Connect to seed nodes and sync chain"""
        for seed in self.seed_nodes:
            try:
                host, port = seed.split(':')
                peer = Peer(host, int(port))
                if self._ping_peer(peer):
                    self.peers.add(peer)
                    print(f"Connected to seed node: {peer}")
            except Exception as e:
                print(f"Failed to connect to seed {seed}: {e}")

        if self.peers:
            print("Syncing blockchain with peers...")
            sync_thread = threading.Thread(target=self.sync_blockchain, daemon=True)
            sync_thread.start()
    
    def _ping_peer(self, peer: Peer) -> bool:
        """Ping a peer to check if it's alive"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((peer.host, peer.port))
            
            message = {'type': Message.PING}
            sock.send(json.dumps(message).encode('utf-8'))
            
            response = sock.recv(1024).decode('utf-8')
            data = json.loads(response)
            
            sock.close()
            return data.get('type') == Message.PONG
        except:
            return False
    
    def _peer_discovery_loop(self):
        """Periodically discover new peers"""
        while self.running:
            time.sleep(30)  # Every 30 seconds
            self._discover_peers()
            self._cleanup_dead_peers()
    
    def _discover_peers(self):
        """Ask known peers for their peer lists"""
        for peer in list(self.peers):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((peer.host, peer.port))
                
                message = {'type': Message.GET_PEERS}
                sock.send(json.dumps(message).encode('utf-8'))
                
                response = sock.recv(4096).decode('utf-8')
                data = json.loads(response)
                
                if data.get('type') == Message.PEERS_RESPONSE:
                    for peer_str in data.get('peers', []):
                        host, port = peer_str.split(':')
                        new_peer = Peer(host, int(port))
                        if new_peer not in self.peers:
                            if self._ping_peer(new_peer):
                                self.peers.add(new_peer)
                                print(f"Discovered new peer: {new_peer}")
                
                sock.close()
            except:
                pass
    
    def _cleanup_dead_peers(self):
        """Remove peers that don't respond"""
        dead_peers = []
        for peer in self.peers:
            if not self._ping_peer(peer):
                dead_peers.append(peer)
        
        for peer in dead_peers:
            self.peers.remove(peer)
            print(f"Removed dead peer: {peer}")
    
    def broadcast_block(self, block: Block):
        """Broadcast new block to all peers"""
        message = {
            'type': Message.NEW_BLOCK,
            'block': block.to_dict()
        }
        self._broadcast(message)
    
    def broadcast_transaction(self, transaction: Transaction):
        """Broadcast new transaction to all peers"""
        message = {
            'type': Message.NEW_TRANSACTION,
            'transaction': transaction.to_dict()
        }
        self._broadcast(message)
    
    def _broadcast(self, message: dict):
        """Send message to all peers"""
        for peer in list(self.peers):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((peer.host, peer.port))
                sock.send(json.dumps(message).encode('utf-8'))
                sock.close()
            except Exception as e:
                print(f"Failed to broadcast to {peer}: {e}")
    
    def sync_blockchain(self):
        """Sync blockchain with peers — downloads missing blocks in chunks"""
        if not self.peers:
            print("No peers to sync with")
            return

        # Find the peer with the longest chain
        best_peer = None
        best_height = self.blockchain.db.get_block_count() or 0

        for peer in list(self.peers):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((peer.host, peer.port))
                # Request 1 block just to get total_height
                msg = {'type': Message.GET_BLOCKS, 'start_index': 0, 'limit': 1}
                sock.send(json.dumps(msg).encode('utf-8'))
                response = b''
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    response += chunk
                    try:
                        data = json.loads(response.decode('utf-8'))
                        break
                    except:
                        continue
                sock.close()
                peer_height = data.get('total_height', 0)
                if peer_height > best_height:
                    best_height = peer_height
                    best_peer = peer
            except Exception as e:
                print(f"Could not check height from {peer}: {e}")

        if not best_peer:
            print("Already up to date or no peers available")
            return

        print(f"Syncing from {best_peer} — peer height: {best_height}, our height: {self.blockchain.db.get_block_count()}")

        CHUNK = 500
        from transaction import TxInput, TxOutput
        current = self.blockchain.db.get_block_count() or 0

        while current < best_height:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(30)
                sock.connect((best_peer.host, best_peer.port))
                msg = {'type': Message.GET_BLOCKS, 'start_index': current, 'limit': CHUNK}
                sock.send(json.dumps(msg).encode('utf-8'))

                # Read full response (may be large)
                response = b''
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    response += chunk
                    try:
                        data = json.loads(response.decode('utf-8'))
                        break
                    except:
                        continue
                sock.close()

                blocks_data = data.get('blocks', [])
                if not blocks_data:
                    break

                for block_data in blocks_data:
                    try:
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

                        if not self.blockchain.add_block(block):
                            print(f"Sync stopped — block {block_data['index']} rejected")
                            return
                    except Exception as e:
                        print(f"Error reconstructing block {block_data.get('index')}: {e}")
                        return

                current = self.blockchain.db.get_block_count() or current
                print(f"Synced to block {current}/{best_height}")

            except Exception as e:
                print(f"Sync error at block {current}: {e}")
                break

        print(f"Sync complete. Height: {self.blockchain.db.get_block_count()}")
