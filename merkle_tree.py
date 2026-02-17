from typing import List
from crypto_utils import double_sha256


class MerkleTree:
    """Merkle tree for efficient transaction verification"""
    
    def __init__(self, transactions: List[str]):
        """
        Build Merkle tree from transaction IDs
        Args:
            transactions: List of transaction IDs (hex strings)
        """
        self.transactions = transactions
        self.root = self.build_tree(transactions)
    
    def build_tree(self, txids: List[str]) -> str:
        """Build Merkle tree and return root hash"""
        if not txids:
            return "0" * 64
        
        if len(txids) == 1:
            return txids[0]
        
        # If odd number of transactions, duplicate the last one
        if len(txids) % 2 != 0:
            txids.append(txids[-1])
        
        # Build next level
        next_level = []
        for i in range(0, len(txids), 2):
            combined = bytes.fromhex(txids[i]) + bytes.fromhex(txids[i + 1])
            parent_hash = double_sha256(combined).hex()
            next_level.append(parent_hash)
        
        return self.build_tree(next_level)
    
    def get_root(self) -> str:
        """Get Merkle root hash"""
        return self.root
    
    def get_proof(self, tx_index: int) -> List[tuple]:
        """
        Get Merkle proof for a transaction
        Returns list of (hash, is_left) tuples
        """
        if tx_index >= len(self.transactions):
            return []
        
        proof = []
        txids = self.transactions.copy()
        index = tx_index
        
        while len(txids) > 1:
            if len(txids) % 2 != 0:
                txids.append(txids[-1])
            
            # Determine sibling
            if index % 2 == 0:
                sibling_index = index + 1
                is_left = False
            else:
                sibling_index = index - 1
                is_left = True
            
            proof.append((txids[sibling_index], is_left))
            
            # Move to next level
            next_level = []
            for i in range(0, len(txids), 2):
                combined = bytes.fromhex(txids[i]) + bytes.fromhex(txids[i + 1])
                parent_hash = double_sha256(combined).hex()
                next_level.append(parent_hash)
            
            txids = next_level
            index = index // 2
        
        return proof
    
    @staticmethod
    def verify_proof(txid: str, proof: List[tuple], root: str) -> bool:
        """
        Verify a Merkle proof
        Args:
            txid: Transaction ID to verify
            proof: List of (hash, is_left) tuples
            root: Expected Merkle root
        """
        current_hash = txid
        
        for sibling_hash, is_left in proof:
            if is_left:
                combined = bytes.fromhex(sibling_hash) + bytes.fromhex(current_hash)
            else:
                combined = bytes.fromhex(current_hash) + bytes.fromhex(sibling_hash)
            
            current_hash = double_sha256(combined).hex()
        
        return current_hash == root
