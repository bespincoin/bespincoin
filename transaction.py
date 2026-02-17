import json
import time
from typing import List, Optional
from dataclasses import dataclass
from crypto_utils import double_sha256, Wallet


@dataclass
class UTXO:
    """Unspent Transaction Output"""
    txid: str  # Transaction ID that created this output
    vout: int  # Output index in that transaction
    amount: float
    script_pubkey: str  # Locking script (public key hash)
    
    def to_dict(self) -> dict:
        return {
            'txid': self.txid,
            'vout': self.vout,
            'amount': self.amount,
            'script_pubkey': self.script_pubkey
        }


@dataclass
class TxInput:
    """Transaction Input - references a UTXO"""
    txid: str  # Previous transaction ID
    vout: int  # Output index in previous transaction
    script_sig: str  # Unlocking script (signature + public key)
    sequence: int = 0xffffffff
    
    def to_dict(self) -> dict:
        return {
            'txid': self.txid,
            'vout': self.vout,
            'script_sig': self.script_sig,
            'sequence': self.sequence
        }


@dataclass
class TxOutput:
    """Transaction Output - creates new UTXO"""
    amount: float
    script_pubkey: str  # Locking script (recipient's public key hash)
    
    def to_dict(self) -> dict:
        return {
            'amount': self.amount,
            'script_pubkey': self.script_pubkey
        }


class Transaction:
    """Bitcoin-style transaction with inputs and outputs"""
    
    def __init__(self, inputs: List[TxInput], outputs: List[TxOutput], 
                 locktime: int = 0):
        self.version = 1
        self.inputs = inputs
        self.outputs = outputs
        self.locktime = locktime
        self.timestamp = time.time()
        self.txid = self.calculate_txid()
    
    def to_dict(self, include_txid: bool = True) -> dict:
        data = {
            'version': self.version,
            'inputs': [inp.to_dict() for inp in self.inputs],
            'outputs': [out.to_dict() for out in self.outputs],
            'locktime': self.locktime,
            'timestamp': self.timestamp
        }
        if include_txid:
            data['txid'] = self.txid
        return data
    
    def calculate_txid(self) -> str:
        """Calculate transaction ID (double SHA-256 of transaction data)"""
        tx_data = json.dumps(self.to_dict(include_txid=False), sort_keys=True)
        return double_sha256(tx_data.encode()).hex()
    
    def get_signing_data(self, input_index: int) -> bytes:
        """Get data to be signed for a specific input"""
        # Create a copy of the transaction for signing
        # In Bitcoin, we temporarily replace the script_sig of the input being signed
        # with the scriptPubKey of the output being spent
        tx_copy = {
            'version': self.version,
            'inputs': [],
            'outputs': [out.to_dict() for out in self.outputs],
            'locktime': self.locktime,
            'timestamp': self.timestamp
        }
        
        # Add inputs with empty script_sig except for the one being signed
        for i, inp in enumerate(self.inputs):
            input_dict = {
                'txid': inp.txid,
                'vout': inp.vout,
                'script_sig': '' if i != input_index else 'PLACEHOLDER',
                'sequence': inp.sequence
            }
            tx_copy['inputs'].append(input_dict)
        
        return json.dumps(tx_copy, sort_keys=True).encode()
    
    @staticmethod
    def create_coinbase(recipient_address: str, amount: float, block_height: int) -> 'Transaction':
        """Create coinbase transaction (mining reward)"""
        # Coinbase has no inputs, special output
        coinbase_input = TxInput(
            txid="0" * 64,
            vout=0xffffffff,
            script_sig=f"coinbase_block_{block_height}",
            sequence=0xffffffff
        )
        
        output = TxOutput(
            amount=amount,
            script_pubkey=recipient_address
        )
        
        return Transaction([coinbase_input], [output])
    
    def is_coinbase(self) -> bool:
        """Check if this is a coinbase transaction"""
        return (len(self.inputs) == 1 and 
                self.inputs[0].txid == "0" * 64 and
                self.inputs[0].vout == 0xffffffff)
