import hashlib
import ecdsa
from ecdsa import SigningKey, VerifyingKey, SECP256k1
import base58

class Wallet:
    """Bitcoin-style wallet with ECDSA key pairs"""
    
    def __init__(self, private_key: SigningKey = None):
        if private_key:
            self.private_key = private_key
        else:
            self.private_key = SigningKey.generate(curve=SECP256k1)
        
        self.public_key = self.private_key.get_verifying_key()
        self.address = self.generate_address()
    
    def generate_address(self) -> str:
        """Generate Bitcoin-style address from public key"""
        # Get public key bytes
        public_key_bytes = self.public_key.to_string()
        
        # SHA-256 hash
        sha256_hash = hashlib.sha256(public_key_bytes).digest()
        
        # RIPEMD-160 hash
        ripemd160 = hashlib.new('ripemd160')
        ripemd160.update(sha256_hash)
        hashed_public_key = ripemd160.digest()
        
        # Add version byte (0x00 for mainnet)
        versioned_payload = b'\x00' + hashed_public_key
        
        # Double SHA-256 for checksum
        checksum = hashlib.sha256(hashlib.sha256(versioned_payload).digest()).digest()[:4]
        
        # Base58 encode
        address = base58.b58encode(versioned_payload + checksum)
        return address.decode('utf-8')
    
    def sign(self, message: bytes) -> bytes:
        """Sign a message with private key"""
        return self.private_key.sign(message)
    
    def get_public_key_hex(self) -> str:
        """Get public key as hex string"""
        return self.public_key.to_string().hex()
    
    def get_private_key_hex(self) -> str:
        """Get private key as hex string"""
        return self.private_key.to_string().hex()
    
    @staticmethod
    def verify_signature(public_key_hex: str, signature: bytes, message: bytes) -> bool:
        """Verify a signature against a public key"""
        try:
            public_key = VerifyingKey.from_string(
                bytes.fromhex(public_key_hex),
                curve=SECP256k1
            )
            public_key.verify(signature, message)
            return True
        except:
            return False
    
    @staticmethod
    def from_private_key(private_key_hex: str):
        """Create wallet from existing private key"""
        private_key = SigningKey.from_string(
            bytes.fromhex(private_key_hex),
            curve=SECP256k1
        )
        return Wallet(private_key)


def double_sha256(data: bytes) -> bytes:
    """Double SHA-256 hash (used throughout Bitcoin)"""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hash160(data: bytes) -> bytes:
    """SHA-256 followed by RIPEMD-160"""
    sha256_hash = hashlib.sha256(data).digest()
    ripemd160 = hashlib.new('ripemd160')
    ripemd160.update(sha256_hash)
    return ripemd160.digest()
