from typing import Dict, List, Optional
from transaction import UTXO, Transaction, TxInput, TxOutput


class UTXOSet:
    """Manages the set of unspent transaction outputs"""
    
    def __init__(self, db=None):
        # Key: "txid:vout", Value: UTXO
        self.utxos: Dict[str, UTXO] = {}
        self.db = db  # Optional database connection for persistence
    
    def add_utxo(self, utxo: UTXO) -> None:
        """Add a UTXO to the set"""
        key = f"{utxo.txid}:{utxo.vout}"
        self.utxos[key] = utxo
        
        # Save to database if available
        if self.db:
            self.db.add_utxo(utxo)
    
    def remove_utxo(self, txid: str, vout: int) -> Optional[UTXO]:
        """Remove and return a UTXO from the set"""
        key = f"{txid}:{vout}"
        utxo = self.utxos.pop(key, None)
        
        # Remove from database if available
        if self.db and utxo:
            self.db.remove_utxo(txid, vout)
        
        return utxo
    
    def get_utxo(self, txid: str, vout: int) -> Optional[UTXO]:
        """Get a UTXO without removing it"""
        key = f"{txid}:{vout}"
        return self.utxos.get(key)
    
    def get_utxos_for_address(self, address: str) -> List[UTXO]:
        """Get all UTXOs for a specific address"""
        return [utxo for utxo in list(self.utxos.values())
                if utxo.script_pubkey == address]
    
    def get_balance(self, address: str) -> float:
        """Get total balance for an address"""
        return sum(utxo.amount for utxo in list(self.utxos.values())
                   if utxo.script_pubkey == address)
    
    def process_transaction(self, tx: Transaction) -> bool:
        """
        Process a transaction: remove spent UTXOs and add new ones
        Returns True if successful
        """
        # Don't process inputs for coinbase transactions
        if not tx.is_coinbase():
            # Remove spent UTXOs
            for tx_input in tx.inputs:
                utxo = self.remove_utxo(tx_input.txid, tx_input.vout)
                if utxo is None:
                    # UTXO doesn't exist (double spend or invalid)
                    return False
        
        # Add new UTXOs from outputs
        for vout, tx_output in enumerate(tx.outputs):
            utxo = UTXO(
                txid=tx.txid,
                vout=vout,
                amount=tx_output.amount,
                script_pubkey=tx_output.script_pubkey
            )
            self.add_utxo(utxo)
        
        return True
    
    def validate_transaction(self, tx: Transaction) -> tuple[bool, str]:
        """
        Validate a transaction without processing it
        Returns (is_valid, error_message)
        """
        if tx.is_coinbase():
            return True, ""
        
        total_input = 0.0
        total_output = sum(out.amount for out in tx.outputs)
        
        # Check all inputs exist and sum them
        for tx_input in tx.inputs:
            utxo = self.get_utxo(tx_input.txid, tx_input.vout)
            if utxo is None:
                return False, f"UTXO not found: {tx_input.txid}:{tx_input.vout}"
            total_input += utxo.amount
        
        # Check input >= output (difference is fee)
        if total_input < total_output:
            return False, f"Insufficient funds: {total_input} < {total_output}"
        
        return True, ""
    
    def copy(self) -> 'UTXOSet':
        """Create a deep copy of the UTXO set"""
        new_set = UTXOSet()
        new_set.utxos = self.utxos.copy()
        return new_set
