from typing import List, Optional
from blockchain import Block
from transaction import Transaction, TxInput, TxOutput, UTXO
from utxo_set import UTXOSet
from crypto_utils import Wallet
from persistence import BlockchainDB
import threading
import time


class Blockchain:
    """Bespin (BSP) - Bitcoin-style blockchain with UTXO model and cryptographic security"""
    
    def __init__(self, difficulty: int = 4, founder_address: str = None, db_path: str = "blockchain.db"):
        self.chain: List[Block] = []
        self.difficulty = difficulty
        self.pending_transactions: List[Transaction] = []
        self.db = BlockchainDB(db_path)
        self.utxo_set = UTXOSet(db=self.db)
        self.mining_reward = 50.0
        self.halving_interval = 210000
        self.max_supply = 100_000_000
        self.founder_allocation = 20_000_000
        self.mining_allocation = 80_000_000
        self.currency_name = "Bespin"
        self.currency_symbol = "BSP"
        self._add_block_lock = threading.Lock()
        
        if self.load_from_db():
            self.founder_address = self.db.get_metadata('founder_address')
            print(f"Loaded existing blockchain with {len(self.chain)} blocks")
        else:
            self.founder_address = founder_address
            self.create_genesis_block()

    def create_genesis_block(self) -> None:
        transactions = []
        if self.founder_address:
            founder_tx = Transaction.create_coinbase(self.founder_address, self.founder_allocation, 0)
            transactions.append(founder_tx)
            print(f"Genesis: Allocated {self.founder_allocation:,.0f} BSP to founder")
        else:
            genesis_tx = Transaction.create_coinbase("GENESIS", 0, 0)
            transactions.append(genesis_tx)
        genesis_block = Block(0, transactions, "0" * 64, self.difficulty)
        genesis_block.mine_block()
        self.chain.append(genesis_block)
        for tx in transactions:
            self.utxo_set.process_transaction(tx)
        self.db.save_block(genesis_block)
        self.db.save_utxo_set(self.utxo_set)
        print("Genesis block saved to database")

    def load_from_db(self) -> bool:
        block_count = self.db.get_block_count()
        if block_count == 0:
            return False
        print(f"Found {block_count} blocks in database")
        print("Loading UTXO set and recent blocks...")
        recent_blocks = self.db.load_recent_blocks(10)
        self.chain = recent_blocks
        self.utxo_set = self.db.load_utxo_set(db=self.db)
        print(f"Loaded {len(self.chain)} recent blocks")
        print(f"Loaded {len(self.utxo_set.utxos)} UTXOs")
        print(f"Blockchain height: {block_count}")
        return True

    def get_latest_block(self) -> Block:
        return self.chain[-1]

    def get_current_mining_reward(self) -> float:
        actual_height = self.db.get_block_count()
        if actual_height is None:
            actual_height = len(self.chain)
        halvings = actual_height // self.halving_interval
        return self.mining_reward / (2 ** halvings)

    def get_total_mined(self) -> float:
        actual_height = self.db.get_block_count()
        if actual_height is None:
            actual_height = len(self.chain)
        total = 0.0
        blocks_mined = actual_height - 1
        current_block = 1
        current_reward = self.mining_reward
        while current_block <= blocks_mined:
            next_halving = ((current_block // self.halving_interval) + 1) * self.halving_interval
            blocks_in_period = min(next_halving - current_block, blocks_mined - current_block + 1)
            total += blocks_in_period * current_reward
            current_block += blocks_in_period
            current_reward /= 2
        return total

    def get_circulating_supply(self) -> float:
        founder_supply = self.founder_allocation if self.founder_address else 0
        return founder_supply + self.get_total_mined()

    def get_remaining_supply(self) -> float:
        return self.max_supply - self.get_circulating_supply()

    def create_genesis_block(self) -> None:
        transactions = []
        if self.founder_address:
            founder_tx = Transaction.create_coinbase(self.founder_address, self.founder_allocation, 0)
            transactions.append(founder_tx)
            print(f"Genesis: Allocated {self.founder_allocation:,.0f} BSP to founder")
        else:
            genesis_tx = Transaction.create_coinbase("GENESIS", 0, 0)
            transactions.append(genesis_tx)
        genesis_block = Block(0, transactions, "0" * 64, self.difficulty)
        genesis_block.mine_block()
        self.chain.append(genesis_block)
        for tx in transactions:
            self.utxo_set.process_transaction(tx)
        self.db.save_block(genesis_block)
        self.db.save_utxo_set(self.utxo_set)
        print("Genesis block saved to database")

    def load_from_db(self) -> bool:
        block_count = self.db.get_block_count()
        if block_count == 0:
            return False
        print(f"Found {block_count} blocks in database")
        print("Loading UTXO set and recent blocks...")
        recent_blocks = self.db.load_recent_blocks(10)
        self.chain = recent_blocks
        self.utxo_set = self.db.load_utxo_set(db=self.db)
        print(f"Loaded {len(self.chain)} recent blocks")
        print(f"Loaded {len(self.utxo_set.utxos)} UTXOs")
        print(f"Blockchain height: {block_count}")
        return True

    def get_latest_block(self) -> Block:
        return self.chain[-1]

    def get_current_mining_reward(self) -> float:
        actual_height = self.db.get_block_count()
        if actual_height is None:
            actual_height = len(self.chain)
        halvings = actual_height // self.halving_interval
        return self.mining_reward / (2 ** halvings)

    def get_total_mined(self) -> float:
        actual_height = self.db.get_block_count()
        if actual_height is None:
            actual_height = len(self.chain)
        total = 0.0
        blocks_mined = actual_height - 1
        current_block = 1
        current_reward = self.mining_reward
        while current_block <= blocks_mined:
            next_halving = ((current_block // self.halving_interval) + 1) * self.halving_interval
            blocks_in_period = min(next_halving - current_block, blocks_mined - current_block + 1)
            total += blocks_in_period * current_reward
            current_block += blocks_in_period
            current_reward /= 2
        return total

    def get_circulating_supply(self) -> float:
        founder_supply = self.founder_allocation if self.founder_address else 0
        return founder_supply + self.get_total_mined()

    def get_remaining_supply(self) -> float:
        return self.max_supply - self.get_circulating_supply()

    def create_transaction(self, sender_wallet: Wallet, recipient_address: str, amount: float) -> Optional[Transaction]:
        sender_utxos = self.utxo_set.get_utxos_for_address(sender_wallet.address)
        selected_utxos = []
        total_input = 0.0
        for utxo in sender_utxos:
            selected_utxos.append(utxo)
            total_input += utxo.amount
            if total_input >= amount:
                break
        if total_input < amount:
            return None
        inputs = []
        for utxo in selected_utxos:
            tx_input = TxInput(txid=utxo.txid, vout=utxo.vout, script_sig="")
            inputs.append(tx_input)
        outputs = [TxOutput(amount=amount, script_pubkey=recipient_address)]
        change = total_input - amount
        if change > 0.00000001:
            outputs.append(TxOutput(amount=change, script_pubkey=sender_wallet.address))
        tx = Transaction(inputs, outputs)
        for i, tx_input in enumerate(tx.inputs):
            signing_data = tx.get_signing_data(i)
            signature = sender_wallet.sign(signing_data)
            tx_input.script_sig = signature.hex() + ":" + sender_wallet.get_public_key_hex()
        return tx

    def verify_transaction_signature(self, tx: Transaction) -> bool:
        if tx.is_coinbase():
            return True
        for i, tx_input in enumerate(tx.inputs):
            try:
                parts = tx_input.script_sig.split(":")
                if len(parts) != 2:
                    return False
                signature_hex, public_key_hex = parts
                signature = bytes.fromhex(signature_hex)
                utxo = self.utxo_set.get_utxo(tx_input.txid, tx_input.vout)
                if not utxo:
                    return False
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
                if derived_address != utxo.script_pubkey:
                    return False
                original_script_sig = tx_input.script_sig
                tx_input.script_sig = ""
                signing_data = tx.get_signing_data(i)
                tx_input.script_sig = original_script_sig
                if not Wallet.verify_signature(public_key_hex, signature, signing_data):
                    return False
            except Exception as e:
                print(f"Signature verification error: {e}")
                return False
        return True

    def add_transaction(self, transaction: Transaction) -> tuple[bool, str]:
        if not self.verify_transaction_signature(transaction):
            return False, "Invalid signature"
        is_valid, error = self.utxo_set.validate_transaction(transaction)
        if not is_valid:
            return False, error
        for pending_tx in self.pending_transactions:
            for pending_input in pending_tx.inputs:
                for tx_input in transaction.inputs:
                    if (pending_input.txid == tx_input.txid and pending_input.vout == tx_input.vout):
                        return False, "Double spend detected in mempool"
        self.pending_transactions.append(transaction)
        return True, ""

    def mine_pending_transactions(self, miner_address: str) -> bool:
        actual_height = self.db.get_block_count()
        latest_block = self.db.get_latest_block_from_db() or self.get_latest_block()
        reward = self.get_current_mining_reward()
        coinbase_tx = Transaction.create_coinbase(miner_address, reward, actual_height)
        transactions = [coinbase_tx] + self.pending_transactions
        block = Block(actual_height, transactions, latest_block.hash, self.difficulty)
        block.mine_block()
        if self.add_block(block):
            self.pending_transactions = []
            return True
        return False

    def add_block(self, block: Block) -> bool:
        """Add a mined block - locked to prevent race conditions"""
        with self._add_block_lock:
            current_height = self.db.get_block_count()
            if current_height is None:
                current_height = len(self.chain)
            if block.index < current_height:
                print(f"Block {block.index} already exists (current height: {current_height})")
                return False
            if block.index != current_height:
                print(f"Invalid block index {block.index}, expected {current_height}")
                return False
            if not block.hash.startswith('0' * self.difficulty):
                print("Invalid proof of work")
                return False
            latest_db_block = self.db.get_latest_block_from_db() or self.get_latest_block()
            if block.previous_hash != latest_db_block.hash:
                print(f"Invalid previous hash - chain moved on, block rejected")
                return False
            if not block.verify_merkle_root():
                print("Invalid Merkle root")
                return False
            for tx in block.transactions:
                if not self.utxo_set.process_transaction(tx):
                    print(f"Failed to process transaction {tx.txid}")
                    return False
            self.chain.append(block)
            self.db.save_block(block)
            self.db.save_utxo_set(self.utxo_set)
            return True

    def get_balance(self, address: str) -> float:
        return self.utxo_set.get_balance(address)

    def is_chain_valid(self) -> bool:
        temp_utxo_set = UTXOSet()
        for i, block in enumerate(self.chain):
            if i == 0:
                for tx in block.transactions:
                    temp_utxo_set.process_transaction(tx)
                continue
            if not block.hash.startswith('0' * self.difficulty):
                print(f"Block {i}: Invalid proof of work")
                return False
            if block.hash != block.calculate_hash():
                print(f"Block {i}: Hash mismatch")
                return False
            if block.previous_hash != self.chain[i-1].hash:
                print(f"Block {i}: Invalid previous hash")
                return False
            if not block.verify_merkle_root():
                print(f"Block {i}: Invalid Merkle root")
                return False
            for tx in block.transactions:
                if not self.verify_transaction_signature(tx):
                    print(f"Block {i}: Invalid transaction signature")
                    return False
                if not tx.is_coinbase():
                    is_valid, error = temp_utxo_set.validate_transaction(tx)
                    if not is_valid:
                        print(f"Block {i}: Transaction validation failed - {error}")
                        return False
                if not temp_utxo_set.process_transaction(tx):
                    print(f"Block {i}: Failed to process transaction")
                    return False
        return True

    def get_transaction(self, txid: str) -> Optional[Transaction]:
        for block in self.chain:
            for tx in block.transactions:
                if tx.txid == txid:
                    return tx
        return None

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        for block in self.chain:
            if block.hash == block_hash:
                return block
        return None
