Bespin import json
import time
from typing import List
from transaction import Transaction
from merkle_tree import MerkleTree
from crypto_utils import double_sha256


class Block:
    """Bitcoin-style block with Merkle tree and proof-of-work"""
    
    def __init__(self, index: int, transactions: List[Transaction], 
                 previous_hash: str, difficulty: int, nonce: int = 0):
        self.index = index
        self.timestamp = time.time()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.difficulty = difficulty
        self.nonce = nonce
        
        # Build Merkle tree from transactions
        tx_ids = [tx.txid for tx in transactions]
        self.merkle_tree = MerkleTree(tx_ids)
        self.merkle_root = self.merkle_tree.get_root()
        
        self.hash = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """Calculate block hash (double SHA-256)"""
        block_header = {
            'version': 1,
            'index': self.index,
            'timestamp': self.timestamp,
            'previous_hash': self.previous_hash,
            'merkle_root': self.merkle_root,
            'difficulty': self.difficulty,
            'nonce': self.nonce
        }
        header_string = json.dumps(block_header, sort_keys=True)
        return double_sha256(header_string.encode()).hex()
    
    def mine_block(self) -> None:
        """Mine block using proof-of-work"""
        target = '0' * self.difficulty
        print(f"Mining block {self.index} with difficulty {self.difficulty}...")
        
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()
            
            if self.nonce % 100000 == 0:
                print(f"  Tried {self.nonce} nonces...")
        
        print(f"Block mined! Hash: {self.hash}")
        print(f"Nonce: {self.nonce}")
    
    def verify_merkle_root(self) -> bool:
        """Verify the Merkle root matches the transactions"""
        tx_ids = [tx.txid for tx in self.transactions]
        calculated_root = MerkleTree(tx_ids).get_root()
        return calculated_root == self.merkle_root
    
    def to_dict(self) -> dict:
        return {
            'index': self.index,
            'timestamp': self.timestamp,
            'transactions': [tx.to_dict() for tx in self.transactions],
            'previous_hash': self.previous_hash,
            'merkle_root': self.merkle_root,
            'difficulty': self.difficulty,
            'nonce': self.nonce,
            'hash': self.hash
        }
