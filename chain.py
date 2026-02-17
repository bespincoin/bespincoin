from typing import List, Optional
from blockchain import Block
from transaction import Transaction, TxInput, TxOutput, UTXO
from utxo_set import UTXOSet
from crypto_utils import Wallet
from persistence import BlockchainDB
import time


class Blockchain:
    """Bespin (BSP) - Bitcoin-style blockchain with UTXO model and cryptographic security"""
    
    def __init__(self, difficulty: int = 4, founder_address: str = None, db_path: str = "blockchain.db"):
        self.chain: List[Block] = []
        self.difficulty = difficulty
        self.pending_transactions: List[Transaction] = []
        self.db = BlockchainDB(db_path)
        self.utxo_set = UTXOSet(db=self.db)  # Pass database to UTXO set
        self.mining_reward = 50.0  # BSP per block
        self.halving_interval = 210000  # Blocks until reward halves
        self.max_supply = 100_000_000  # 100 Million BSP total
        self.founder_allocation = 20_000_000  # 20 Million BSP (20%)
        self.mining_allocation = 80_000_000  # 80 Million BSP (80%)
        self.currency_name = "Bespin"
        self.currency_symbol = "BSP"
        
        # Try to load existing blockchain from database
        if self.load_from_db():
            # Blockchain loaded from DB, restore founder address from metadata
            self.founder_address = self.db.get_metadata('founder_address')
            print(f"Loaded existing blockchain with {len(self.chain)} blocks")
        else:
            # No existing blockchain, create genesis with provided founder address
            self.founder_address = founder_address
            self.create_genesis_block()
    
    def create_genesis_block(self) -> None:
        """Create the first block in the chain with founder allocation"""
        transactions = []
        
        # Founder allocation (20M BSP)
        if self.founder_address:
            founder_tx = Transaction.create_coinbase(
                self.founder_address, 
                self.founder_allocation, 
                0
            )
            transactions.append(founder_tx)
            print(f"Genesis: Allocated {self.founder_allocation:,.0f} BSP to founder")
        else:
            # No founder allocation, just empty genesis
            genesis_tx = Transaction.create_coinbase("GENESIS", 0, 0)
            transactions.append(genesis_tx)
        
        genesis_block = Block(0, transactions, "0" * 64, self.difficulty)
        genesis_block.mine_block()
        
        self.chain.append(genesis_block)
        
        # Process all genesis transactions
        for tx in transactions:
            self.utxo_set.process_transaction(tx)
        
        # Save to database
        self.db.save_block(genesis_block)
        self.db.save_utxo_set(self.utxo_set)
        print("Genesis block saved to database")
    
    def load_from_db(self) -> bool:
        """Load blockchain from database if it exists"""
        block_count = self.db.get_block_count()
        
        if block_count == 0:
            return False
        
        print(f"Found {block_count} blocks in database")
        print("Loading UTXO set and recent blocks...")
        
        # Only load recent blocks (last 100) for quick validation
        # Full blockchain can be loaded on-demand if needed
        recent_blocks = self.db.load_recent_blocks(100)
        self.chain = recent_blocks
        
        # Load UTXO set (this is what we actually need for validation)
        self.utxo_set = self.db.load_utxo_set(db=self.db)
        
        print(f"Loaded {len(self.chain)} recent blocks")
        print(f"Loaded {len(self.utxo_set.utxos)} UTXOs")
        print(f"Blockchain height: {block_count}")
        return True
    
    def get_latest_block(self) -> Block:
        return self.chain[-1]
    
    def get_current_mining_reward(self) -> float:
        """Calculate current mining reward with halving"""
        # Use actual blockchain height from database
        actual_height = self.db.get_block_count()
        halvings = actual_height // self.halving_interval
        return self.mining_reward / (2 ** halvings)
    
    def get_total_mined(self) -> float:
        """Calculate total BSP mined so far (excluding founder allocation)"""
        # Calculate from actual blockchain height in database
        actual_height = self.db.get_block_count()
        
        # Calculate total mined based on halving schedule
        total = 0.0
        blocks_mined = actual_height - 1  # Exclude genesis
        
        # Calculate for each halving period
        current_block = 1  # Start after genesis
        current_reward = self.mining_reward
        
        while current_block <= blocks_mined:
            # How many blocks in this halving period?
            next_halving = ((current_block // self.halving_interval) + 1) * self.halving_interval
            blocks_in_period = min(next_halving - current_block, blocks_mined - current_block + 1)
            
            total += blocks_in_period * current_reward
            current_block += blocks_in_period
            current_reward /= 2
        
        return total
    
    def get_circulating_supply(self) -> float:
        """Get current circulating supply"""
        founder_supply = self.founder_allocation if self.founder_address else 0
        mined_supply = self.get_total_mined()
        return founder_supply + mined_supply
    
    def get_remaining_supply(self) -> float:
        """Get remaining BSP to be mined"""
        return self.max_supply - self.get_circulating_supply()
    
    def create_transaction(self, sender_wallet: Wallet, recipient_address: str, 
                          amount: float) -> Optional[Transaction]:
        """
        Create a properly signed transaction
        Returns None if insufficient funds
        """
        # Get sender's UTXOs
        sender_utxos = self.utxo_set.get_utxos_for_address(sender_wallet.address)
        
        # Select UTXOs to cover amount (simple selection, not optimized)
        selected_utxos = []
        total_input = 0.0
        
        for utxo in sender_utxos:
            selected_utxos.append(utxo)
            total_input += utxo.amount
            if total_input >= amount:
                break
        
        if total_input < amount:
            return None  # Insufficient funds
        
        # Create inputs (without signatures initially)
        inputs = []
        for utxo in selected_utxos:
            tx_input = TxInput(
                txid=utxo.txid,
                vout=utxo.vout,
                script_sig=""  # Empty for now
            )
            inputs.append(tx_input)
        
        # Create outputs
        outputs = [
            TxOutput(amount=amount, script_pubkey=recipient_address)
        ]
        
        # Add change output if necessary
        change = total_input - amount
        if change > 0.00000001:  # Minimum dust threshold
            outputs.append(
                TxOutput(amount=change, script_pubkey=sender_wallet.address)
            )
        
        # Create transaction (txid calculated without signatures)
        tx = Transaction(inputs, outputs)
        
        # Sign each input
        for i, tx_input in enumerate(tx.inputs):
            signing_data = tx.get_signing_data(i)
            signature = sender_wallet.sign(signing_data)
            # Script_sig contains signature + public key
            tx_input.script_sig = signature.hex() + ":" + sender_wallet.get_public_key_hex()
        
        # Don't recalculate txid - it's based on unsigned transaction
        # (In real Bitcoin, signatures are in witness data for SegWit)
        
        return tx
    
    def verify_transaction_signature(self, tx: Transaction) -> bool:
        """Verify all signatures in a transaction"""
        if tx.is_coinbase():
            return True
        
        for i, tx_input in enumerate(tx.inputs):
            # Parse script_sig (signature:public_key)
            try:
                parts = tx_input.script_sig.split(":")
                if len(parts) != 2:
                    return False
                
                signature_hex, public_key_hex = parts
                signature = bytes.fromhex(signature_hex)
                
                # Get the UTXO being spent
                utxo = self.utxo_set.get_utxo(tx_input.txid, tx_input.vout)
                if not utxo:
                    return False
                
                # Verify the public key hash matches the UTXO's address
                # Recreate address from public key
                public_key_bytes = bytes.fromhex(public_key_hex)
                import hashlib
                sha256_hash = hashlib.sha256(public_key_bytes).digest()
                ripemd160 = hashlib.new('ripemd160')
                ripemd160.update(sha256_hash)
                hashed_public_key = ripemd160.digest()
                versioned_payload = b'\x00' + hashed_public_key
                checksum = hashlib.sha256(hashlib.sha256(versioned_payload).digest()).digest()[:4]
                import base58
                derived_address = base58.b58encode(versioned_payload + checksum).decode('utf-8')
                
                # Check if derived address matches UTXO address
                if derived_address != utxo.script_pubkey:
                    return False
                
                # Temporarily clear script_sig for verification (same as signing)
                original_script_sig = tx_input.script_sig
                tx_input.script_sig = ""
                
                # Verify signature
                signing_data = tx.get_signing_data(i)
                
                # Restore script_sig
                tx_input.script_sig = original_script_sig
                
                if not Wallet.verify_signature(public_key_hex, signature, signing_data):
                    return False
                
            except Exception as e:
                print(f"Signature verification error: {e}")
                return False
        
        return True
    
    def add_transaction(self, transaction: Transaction) -> tuple[bool, str]:
        """
        Add a transaction to pending pool after validation
        Returns (success, error_message)
        """
        # Verify signatures
        if not self.verify_transaction_signature(transaction):
            return False, "Invalid signature"
        
        # Validate against UTXO set
        is_valid, error = self.utxo_set.validate_transaction(transaction)
        if not is_valid:
            return False, error
        
        # Check for double-spend in pending transactions
        for pending_tx in self.pending_transactions:
            for pending_input in pending_tx.inputs:
                for tx_input in transaction.inputs:
                    if (pending_input.txid == tx_input.txid and 
                        pending_input.vout == tx_input.vout):
                        return False, "Double spend detected in mempool"
        
        self.pending_transactions.append(transaction)
        return True, ""
    
    def mine_pending_transactions(self, miner_address: str) -> bool:
        """Mine a new block with pending transactions"""
        # Get actual blockchain height from database
        actual_height = self.db.get_block_count()
        
        # Create coinbase transaction
        reward = self.get_current_mining_reward()
        coinbase_tx = Transaction.create_coinbase(
            miner_address, 
            reward,
            actual_height
        )
        
        # Add coinbase as first transaction (can mine empty blocks with just coinbase)
        transactions = [coinbase_tx] + self.pending_transactions
        
        # Create and mine block
        block = Block(
            actual_height,
            transactions,
            self.get_latest_block().hash,
            self.difficulty
        )
        block.mine_block()
        
        # Validate and add block
        if self.add_block(block):
            self.pending_transactions = []
            return True
        
        return False
    
    def add_block(self, block: Block) -> bool:
        """Add a mined block to the chain after validation"""
        # Verify proof of work
        if not block.hash.startswith('0' * self.difficulty):
            print("Invalid proof of work")
            return False
        
        # Verify previous hash
        if block.previous_hash != self.get_latest_block().hash:
            print("Invalid previous hash")
            return False
        
        # Verify Merkle root
        if not block.verify_merkle_root():
            print("Invalid Merkle root")
            return False
        
        # Process all transactions and update UTXO set
        for tx in block.transactions:
            if not self.utxo_set.process_transaction(tx):
                print(f"Failed to process transaction {tx.txid}")
                return False
        
        self.chain.append(block)
        
        # Save to database
        self.db.save_block(block)
        self.db.save_utxo_set(self.utxo_set)
        
        return True
    
    def get_balance(self, address: str) -> float:
        """Get balance for an address from UTXO set"""
        return self.utxo_set.get_balance(address)

    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = self.chain[i - 1]
            
            # Verify current block's hash
            if current_block.hash != current_block.calculate_hash():
                print(f"Block {i} has been tampered with!")
                return False
            
            # Verify link to previous block
            if current_block.previous_hash != previous_block.hash:
                print(f"Block {i} has invalid previous hash!")
                return False
            
            # Verify proof of work
            if not current_block.hash.startswith('0' * self.difficulty):
                print(f"Block {i} has invalid proof of work!")
                return False
        
        return True
    
    def get_transaction_history(self, address: str) -> List[dict]:
        history = []
        
        for block in self.chain:
            for transaction in block.transactions:
                if transaction.sender == address or transaction.recipient == address:
                    history.append({
                        'block': block.index,
                        'sender': transaction.sender,
                        'recipient': transaction.recipient,
                        'amount': transaction.amount,
                        'timestamp': transaction.timestamp
                    })
        
        return history

    
    def is_chain_valid(self) -> bool:
        """Validate entire blockchain"""
        # Rebuild UTXO set from scratch
        temp_utxo_set = UTXOSet()
        
        for i, block in enumerate(self.chain):
            # Skip genesis block validation
            if i == 0:
                for tx in block.transactions:
                    temp_utxo_set.process_transaction(tx)
                continue
            
            # Verify proof of work
            if not block.hash.startswith('0' * self.difficulty):
                print(f"Block {i}: Invalid proof of work")
                return False
            
            # Verify hash is correct
            if block.hash != block.calculate_hash():
                print(f"Block {i}: Hash mismatch")
                return False
            
            # Verify previous hash link
            if block.previous_hash != self.chain[i-1].hash:
                print(f"Block {i}: Invalid previous hash")
                return False
            
            # Verify Merkle root
            if not block.verify_merkle_root():
                print(f"Block {i}: Invalid Merkle root")
                return False
            
            # Verify all transactions
            for tx in block.transactions:
                # Verify signatures
                if not self.verify_transaction_signature(tx):
                    print(f"Block {i}: Invalid transaction signature")
                    return False
                
                # Validate against temp UTXO set
                if not tx.is_coinbase():
                    is_valid, error = temp_utxo_set.validate_transaction(tx)
                    if not is_valid:
                        print(f"Block {i}: Transaction validation failed - {error}")
                        return False
                
                # Process transaction
                if not temp_utxo_set.process_transaction(tx):
                    print(f"Block {i}: Failed to process transaction")
                    return False
        
        return True
    
    def get_transaction(self, txid: str) -> Optional[Transaction]:
        """Find a transaction by ID"""
        for block in self.chain:
            for tx in block.transactions:
                if tx.txid == txid:
                    return tx
        return None
    
    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        """Find a block by hash"""
        for block in self.chain:
            if block.hash == block_hash:
                return block
        return None
