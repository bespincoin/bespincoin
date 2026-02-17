#!/bin/bash
# Bespin (BSP) Mining Script
# Simple continuous mining loop

# Configuration
MINER_ADDRESS="${1:-YOUR_WALLET_ADDRESS_HERE}"
API_URL="${2:-http://localhost:8000}"

if [ "$MINER_ADDRESS" = "YOUR_WALLET_ADDRESS_HERE" ]; then
    echo "Error: Please provide your wallet address"
    echo "Usage: ./mine.sh YOUR_WALLET_ADDRESS [API_URL]"
    echo "Example: ./mine.sh 1YourBespinAddressHere"
    exit 1
fi

echo "========================================"
echo "Bespin (BSP) Miner"
echo "========================================"
echo "Miner Address: $MINER_ADDRESS"
echo "API URL: $API_URL"
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# Mining loop
while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Mining block..."
    
    response=$(curl -s -X POST "$API_URL/mine" \
        -H "Content-Type: application/json" \
        -d "{\"miner_address\": \"$MINER_ADDRESS\"}")
    
    # Check if block was mined successfully
    if echo "$response" | grep -q "Block mined successfully"; then
        echo "✓ Block mined! Reward: 50 BSP"
    elif echo "$response" | grep -q "error"; then
        echo "✗ Error: $response"
    else
        echo "Response: $response"
    fi
    
    echo ""
    sleep 2
done
