#!/bin/bash
# Bespin (BSP) Miner - Client-side Proof of Work
# Usage: ./mine.sh YOUR_WALLET_ADDRESS [API_URL]
# Example: ./mine.sh 1YourAddressHere https://api.bespincoin.com

MINER_ADDRESS="${1:-}"
API_URL="${2:-https://api.bespincoin.com}"

if [ -z "$MINER_ADDRESS" ]; then
    echo "Usage: ./mine.sh YOUR_WALLET_ADDRESS [API_URL]"
    echo "Example: ./mine.sh 1YourAddressHere https://api.bespincoin.com"
    exit 1
fi

mine_block() {
    # Get work template (instant)
    work=$(curl -s -X POST "$API_URL/mine/work" \
        -H "Content-Type: application/json" \
        -d "{\"miner_address\": \"$MINER_ADDRESS\"}")

    if [ -z "$work" ] || echo "$work" | grep -q "error"; then
        echo "Failed to get work: $work"
        return 1
    fi

    # Do PoW in Python (fast, runs locally)
    result=$(python3 - <<EOF
import json, hashlib, time

work = json.loads('''$work''')
index = work['block_index']
prev_hash = work['previous_hash']
difficulty = work['difficulty']
transactions = work['transactions']
timestamp = time.time()

# Calculate merkle root
import hashlib
def merkle(txids):
    if not txids:
        return '0' * 64
    if len(txids) == 1:
        return txids[0]
    while len(txids) > 1:
        if len(txids) % 2 == 1:
            txids.append(txids[-1])
        next_level = []
        for i in range(0, len(txids), 2):
            combined = bytes.fromhex(txids[i]) + bytes.fromhex(txids[i+1])
            h = hashlib.sha256(hashlib.sha256(combined).digest()).hexdigest()
            next_level.append(h)
        txids = next_level
    return txids[0]

txids = [tx['txid'] for tx in transactions]
merkle_root = merkle(txids)
target = '0' * difficulty
nonce = 0

while True:
    header = f"{index}{timestamp}{prev_hash}{merkle_root}{nonce}"
    hash_val = hashlib.sha256(hashlib.sha256(header.encode()).digest()).hexdigest()
    if hash_val.startswith(target):
        block = {
            'index': index,
            'timestamp': timestamp,
            'previous_hash': prev_hash,
            'merkle_root': merkle_root,
            'nonce': nonce,
            'difficulty': difficulty,
            'hash': hash_val,
            'transactions': transactions
        }
        print(json.dumps(block))
        break
    nonce += 1
    if nonce % 100000 == 0:
        import sys
        print(f"Tried {nonce} nonces...", file=sys.stderr)
EOF
)

    if [ -z "$result" ]; then
        echo "PoW failed"
        return 1
    fi

    # Submit solved block (instant)
    response=$(curl -s -X POST "$API_URL/mine/submit" \
        -H "Content-Type: application/json" \
        -d "{\"block\": $result}")

    if echo "$response" | grep -q "Block accepted"; then
        block_index=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['index'])")
        echo "✓ Block $block_index mined!"
    else
        echo "✗ Rejected: $response"
    fi
}

echo "Bespin Miner - $MINER_ADDRESS"
echo "API: $API_URL"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    mine_block
    sleep 1
done
