#!/bin/bash
# Bespin (BSP) Mining Script - Client-side PoW
# MINER_ADDRESS and API_URL set by caller

mine_block() {
    work=$(curl -s -X POST "$API_URL/mine/work" \
        -H "Content-Type: application/json" \
        -d "{\"miner_address\": \"$MINER_ADDRESS\"}")

    if [ -z "$work" ] || echo "$work" | grep -q '"error"'; then
        echo "Failed to get work: $work"
        sleep 2
        return 1
    fi

    result=$(python3 - <<PYEOF
import json, hashlib, time, sys

work = json.loads('''$work''')
index = work['block_index']
prev_hash = work['previous_hash']
difficulty = work['difficulty']
transactions = work['transactions']
timestamp = time.time()

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
        print(json.dumps({
            'index': index,
            'timestamp': timestamp,
            'previous_hash': prev_hash,
            'merkle_root': merkle_root,
            'nonce': nonce,
            'difficulty': difficulty,
            'hash': hash_val,
            'transactions': transactions
        }))
        break
    nonce += 1
    if nonce % 300000 == 0:
        print(f"Tried {nonce} nonces...", file=sys.stderr)
PYEOF
)

    if [ -z "$result" ]; then
        echo "PoW failed"
        return 1
    fi

    response=$(curl -s -X POST "$API_URL/mine/submit" \
        -H "Content-Type: application/json" \
        -d "{\"block\": $result}")

    if echo "$response" | grep -q "Block accepted"; then
        idx=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['index'])")
        echo "✓ Block $idx accepted"
    else
        echo "✗ $response"
    fi
}

echo "Miner: $MINER_ADDRESS @ $API_URL"
while true; do
    mine_block
done
