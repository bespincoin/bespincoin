# Bespin (BSP) - Peer-to-Peer Cryptocurrency

A Bitcoin-inspired blockchain with UTXO model, P2P networking, proof-of-work mining, and REST API.

- Website: [bespincoin.com](https://bespincoin.com)
- Explorer: [bespincoin.com/explorer](https://bespincoin.com/explorer)
- Wallet: [wallet.bespincoin.com](https://wallet.bespincoin.com)
- Live API: [api.bespincoin.com](https://api.bespincoin.com)

## Running a Full Node

### Requirements
- Python 3.10+
- 2GB RAM minimum (4GB recommended — UTXO set loads into memory)
- Ubuntu 22.04 recommended

### Install

```bash
git clone https://github.com/YOUR_REPO/bespincoin.git
cd bespincoin
pip install -r requirements.txt
```

### Start the node

```bash
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 16 --timeout 120 --worker-class gthread wsgi:app
```

The node takes ~2 minutes to start while it loads the UTXO set. Check it's ready:

```bash
curl http://localhost:8000/health
# {"status":"healthy"}

curl http://localhost:8000/info
```

### Connect to the live network

The seed node is at `api.bespincoin.com:5000`. Set it via env var and your node will automatically sync the full blockchain on startup — this may take several minutes depending on chain height.

```bash
SEED_NODES=api.bespincoin.com:5000 gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 16 --timeout 120 --worker-class gthread wsgi:app
```

Watch the sync progress in the logs — you'll see `Synced to block X/Y` until it catches up.

### Mining

Once your node is running and synced, point your miner at your local API:

```bash
# Get a wallet address
curl -X POST http://localhost:8000/wallet/new

# Start mining (replace with your address)
curl -X POST http://localhost:8000/mine/work \
  -H "Content-Type: application/json" \
  -d '{"miner_address": "YOUR_BSP_ADDRESS"}'
```

Block reward: **25 BSP** | Difficulty: 4 | BSP price: ~$0.01

## Project Structure

```
├── blockchain.py      # Block structure, Merkle trees
├── chain.py           # Blockchain logic and validation
├── transaction.py     # UTXO transactions
├── crypto_utils.py    # ECDSA wallets and signatures
├── merkle_tree.py     # Merkle tree implementation
├── utxo_set.py        # UTXO set management
├── persistence.py     # SQLite persistence layer
├── network.py         # P2P networking
├── api.py             # REST API (Flask)
├── node.py            # Node entry point
├── wsgi.py            # Gunicorn entry point
└── requirements.txt
```

## API Reference

### Node
- `GET /health` — health check
- `GET /info` — node info, chain height, supply, peers

### Blockchain
- `GET /blockchain` — recent blocks
- `GET /block/<index>` — specific block
- `GET /blockchain/validate` — validate chain integrity

### Wallet
- `POST /wallet/new` — create wallet (returns address + private key)
- `GET /wallet/balance/<address>` — get balance
- `GET /wallet/utxos/<address>` — get UTXOs
- `GET /address/<address>` — full address info + transaction history

### Transactions
- `POST /transaction/new` — send BSP
- `GET /transactions/pending` — mempool

### Mining
- `POST /mine/work` — get block template
- `POST /mine/submit` — submit solved block

### Network
- `GET /peers` — connected peers
- `POST /peers/sync` — trigger sync

See `API_EXAMPLES.md` for full request/response examples.

## Security

- ECDSA signatures (secp256k1) — no unauthorised transactions
- UTXO model — no double spending
- Proof-of-work — no chain tampering
- Merkle trees — no transaction tampering
- Bitcoin-style addresses with checksums

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SEED_NODES` | None | Comma-separated seed nodes e.g. `api.bespincoin.com:5000` |
| `FOUNDER_ADDRESS` | None | BSP address for genesis allocation (not needed for regular nodes) |
| `NODE_PORT` | 5000 | P2P port |
| `API_PORT` | 8000 | API port |
| `OPENAI_API_KEY` | None | Optional — only needed for the `/sitrep` endpoint |
| `BRIDGE_ADDRESS` | *(public bridge address)* | BSP→wBSP bridge deposit address |

## License

MIT
