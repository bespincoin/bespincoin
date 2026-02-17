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
            blocks_data = []
            for block in self.blockchain.chain[start_index:]:
                blocks_data.append(block.to_dict())
            return {'type': Message.BLOCKS_RESPONSE, 'blocks': blocks_data}
        
        elif msg_type == Message.NEW_BLOCK:
            # Handle new block from network
            block_data = message.get('block')
            # TODO: Validate and add block
            print(f"Received new block from {address}")
        
        elif msg_type == Message.NEW_TRANSACTION:
            # Handle new transaction from network
            tx_data = message.get('transaction')
            # TODO: Validate and add transaction
            print(f"Received new transaction from {address}")
        
        return None
    
    def _connect_to_seeds(self):
        """Connect to seed nodes"""
        for seed in self.seed_nodes:
            try:
                host, port = seed.split(':')
                peer = Peer(host, int(port))
                if self._ping_peer(peer):
                    self.peers.add(peer)
                    print(f"Connected to seed node: {peer}")
            except Exception as e:
                print(f"Failed to connect to seed {seed}: {e}")
    
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
        """Sync blockchain with peers"""
        if not self.peers:
            print("No peers to sync with")
            return
        
        # Find longest chain among peers
        longest_chain_length = len(self.blockchain.chain)
        longest_chain_peer = None
        
        for peer in self.peers:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((peer.host, peer.port))
                
                message = {'type': Message.GET_BLOCKS, 'start_index': 0}
                sock.send(json.dumps(message).encode('utf-8'))
                
                response = sock.recv(1048576).decode('utf-8')  # 1MB max
                data = json.loads(response)
                
                if data.get('type') == Message.BLOCKS_RESPONSE:
                    blocks = data.get('blocks', [])
                    if len(blocks) > longest_chain_length:
                        longest_chain_length = len(blocks)
                        longest_chain_peer = peer
                
                sock.close()
            except:
                pass
        
        if longest_chain_peer:
            print(f"Syncing with peer {longest_chain_peer}")
            # TODO: Implement chain replacement logic
