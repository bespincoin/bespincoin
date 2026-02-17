# Bespin (BSP) - Secure Cryptocurrency

A production-grade, Bitcoin-inspired blockchain with P2P networking and REST API, ready for DigitalOcean deployment.

**Bespin** - Currency in the clouds. A decentralized cryptocurrency built with enterprise-grade security.

## Features

### Core Security
- ECDSA digital signatures (secp256k1)
- UTXO model for double-spend prevention
- Merkle trees for transaction verification
- Proof-of-work consensus
- Bitcoin-style addresses with checksums

### Network
- P2P peer-to-peer networking
- Automatic peer discovery
- Block and transaction broadcasting
- Multi-node synchronization

### API
- RESTful API for all operations
- Wallet management
- Transaction creation
- Mining interface
- Network monitoring

## Quick Start

### Local Testing
```bash
# Install dependencies
pip install -r requirements.txt

# Start node
python node.py --p2p-port 5000 --api-port 8000

# In another terminal, test API
curl http://localhost:8000/info
```

### Deploy to DigitalOcean
```bash
# See deploy/DEPLOYMENT.md for complete guide

# Quick deploy (single node)
cd deploy
./deploy.sh YOUR_DROPLET_IP

# Deploy full network (3 nodes)
./deploy-network.sh
```

## Project Structure

```
├── blockchain.py          # Block structure with Merkle trees
├── chain.py              # Blockchain logic and validation
├── transaction.py        # UTXO transactions
├── crypto_utils.py       # ECDSA wallets and signatures
├── merkle_tree.py        # Merkle tree implementation
├── utxo_set.py          # UTXO management
├── network.py           # P2P networking
├── api.py               # REST API server
├── node.py              # Node runner
├── requirements.txt     # Python dependencies
├── API_EXAMPLES.md      # API usage examples
└── deploy/              # Deployment scripts
    ├── DEPLOYMENT.md    # Complete deployment guide
    ├── setup.sh         # Server setup script
    ├── deploy.sh        # Deployment script
    └── terraform/       # Infrastructure as code
```

## API Endpoints

### Blockchain
- `GET /blockchain` - Get entire chain
- `GET /block/<index>` - Get specific block
- `GET /blockchain/validate` - Validate chain

### Transactions
- `POST /transaction/new` - Create transaction
- `GET /transactions/pending` - Get pending transactions

### Mining
- `POST /mine` - Mine new block

### Wallet
- `POST /wallet/new` - Create wallet
- `GET /wallet/balance/<address>` - Get balance

### Network
- `GET /peers` - Get connected peers
- `GET /info` - Node information

See `API_EXAMPLES.md` for detailed examples.

## Deployment

### Requirements
- DigitalOcean account
- 3 droplets (recommended): $18/month total
  - 1 GB RAM, 1 vCPU, 25 GB SSD each
  - Regions: NYC, Frankfurt, Singapore

### Deploy Steps

1. **Create droplets** (via web UI or CLI)
2. **Deploy seed node**:
   ```bash
   cd deploy
   ./deploy.sh SEED_IP
   ```
3. **Deploy additional nodes**:
   ```bash
   ./deploy.sh NODE2_IP SEED_IP:5000
   ./deploy.sh NODE3_IP SEED_IP:5000
   ```

See `deploy/DEPLOYMENT.md` for complete instructions.

## Security Features

✓ No unauthorized transactions (ECDSA signatures)  
✓ No double-spending (UTXO validation)  
✓ No chain tampering (proof-of-work + cryptographic linking)  
✓ No transaction tampering (Merkle tree verification)  
✓ No address spoofing (cryptographic address generation)  

## Architecture

```
┌─────────────────────────────────────────┐
│           Blockchain Node                │
├─────────────────────────────────────────┤
│  REST API (Port 8000)                   │
│  ├─ Wallet operations                   │
│  ├─ Transaction submission              │
│  ├─ Mining interface                    │
│  └─ Blockchain queries                  │
├─────────────────────────────────────────┤
│  P2P Network (Port 5000)                │
│  ├─ Peer discovery                      │
│  ├─ Block propagation                   │
│  ├─ Transaction broadcast               │
│  └─ Chain synchronization               │
├─────────────────────────────────────────┤
│  Blockchain Core                        │
│  ├─ UTXO set management                 │
│  ├─ Transaction validation              │
│  ├─ Block mining (PoW)                  │
│  └─ Chain validation                    │
└─────────────────────────────────────────┘
```

## Usage Examples

### Create wallet and mine
```bash
# Create wallet
curl -X POST http://localhost:8000/wallet/new

# Mine block (use address from above)
curl -X POST http://localhost:8000/mine \
  -H "Content-Type: application/json" \
  -d '{"miner_address": "YOUR_ADDRESS"}'

# Check balance
curl http://localhost:8000/wallet/balance/YOUR_ADDRESS
```

### Send transaction
```bash
curl -X POST http://localhost:8000/transaction/new \
  -H "Content-Type: application/json" \
  -d '{
    "sender_private_key": "YOUR_PRIVATE_KEY",
    "recipient_address": "RECIPIENT_ADDRESS",
    "amount": 10.0
  }'
```

## Monitoring

```bash
# View logs
ssh root@YOUR_IP 'journalctl -u blockchain-node -f'

# Check peers
curl http://YOUR_IP:8000/peers

# Validate chain
curl http://YOUR_IP:8000/blockchain/validate
```

## Cost

- **Development**: Free (run locally)
- **Production**: $18/month (3 DigitalOcean droplets)
- **Enterprise**: Scale as needed

## Documentation

- `API_EXAMPLES.md` - Complete API reference with examples
- `deploy/DEPLOYMENT.md` - Full deployment guide
- `deploy/digitalocean-setup.md` - Step-by-step DigitalOcean setup

## Next Steps

1. Deploy to DigitalOcean
2. Setup domain names
3. Add Cloudflare for DDoS protection
4. Create blockchain explorer UI
5. Build wallet application

## License

MIT License - Use for any purpose

## Support

For issues or questions, check the documentation or create an issue.
