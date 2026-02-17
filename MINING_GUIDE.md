# Bespin (BSP) Mining Guide

## What is Mining?

Mining secures the Bespin network and creates new BSP coins. Miners compete to solve cryptographic puzzles, and the winner earns 50 BSP per block.

## Mining Rewards

- **Current Reward**: 50 BSP per block
- **Halving**: Every 210,000 blocks (~4 years)
- **Total Mineable**: 80,000,000 BSP (80% of supply)
- **Algorithm**: SHA-256 Proof-of-Work

## Requirements

### Minimum
- Computer with Python 3.8+
- Internet connection
- Bespin wallet address

### Recommended
- Multi-core CPU (more cores = better)
- 2GB+ RAM
- SSD storage
- Stable internet

## Setup Instructions

### Step 1: Install Python

**Windows:**
Download from https://www.python.org/downloads/

**Mac:**
```bash
brew install python3
```

**Linux:**
```bash
sudo apt-get install python3 python3-pip
```

### Step 2: Get Mining Software

Contact us to receive the mining software package:
- Email: contact@bespincoin.com
- Include your operating system (Windows/Mac/Linux)

We'll send you a download link with:
- All required Python files
- Dependencies list (requirements.txt)
- Setup instructions

### Step 3: Create Wallet

If you don't have a wallet yet:

```bash
python create_founder_wallet.py
```

Save your address and private key securely!

Or create one at: https://wallet.bespincoin.com

### Step 4: Start Mining

```bash
python node.py --mine --miner-address YOUR_WALLET_ADDRESS
```

Replace `YOUR_WALLET_ADDRESS` with your actual Bespin address.

## Mining Commands

### Basic Mining
```bash
python node.py --mine --miner-address 1YourAddressHere
```

### Custom Ports
```bash
python node.py --mine --miner-address 1YourAddressHere --api-port 8001 --p2p-port 5001
```

### Connect to Seed Node
```bash
python node.py --mine --miner-address 1YourAddressHere --seed-node api.bespincoin.com:5000
```

### Background Mining (Linux/Mac)
```bash
nohup python node.py --mine --miner-address 1YourAddressHere > mining.log 2>&1 &
```

### Check Mining Status
```bash
tail -f mining.log
```

## Understanding Output

When mining, you'll see:
```
Mining block #1...
Trying nonce: 12345
✓ Block mined! Hash: 0000abc123...
Reward: 50 BSP sent to 1YourAddress...
```

## Mining Profitability

### Current Network
- Difficulty: 4 (adjusts automatically)
- Block time: ~10 minutes target
- Reward: 50 BSP

### Estimated Earnings
Depends on:
- Your CPU power
- Number of other miners
- Network difficulty

**Example:**
- If you mine 1 block/hour = 50 BSP/hour
- At $0.01/BSP = $0.50/hour
- Daily: ~$12 (if you mine 24/7)

**Note**: As more miners join, difficulty increases and earnings decrease.

## Mining Pools

Currently, Bespin doesn't have mining pools. You mine solo and keep 100% of rewards.

Future: Community may create pools for more consistent payouts.

## Troubleshooting

### "Module not found" error
```bash
pip install -r requirements.txt
```

### "Connection refused"
Check your firewall allows port 5000 and 8000.

### "Invalid address"
Make sure you're using a valid Bespin address (starts with 1).

### Mining too slow
- Lower difficulty (for testing): Edit `chain.py`
- Use faster CPU
- Wait for difficulty adjustment

### No blocks found
- Check you're connected to network
- Verify your address is correct
- Be patient - mining requires luck

## Advanced: Cloud Mining

### DigitalOcean
```bash
# Create droplet (Ubuntu 22.04)
# SSH to server
ssh root@your-server-ip

# Install dependencies
apt-get update
apt-get install -y python3 python3-pip

# Upload mining software (contact us for files)
# Extract and setup
cd bespin-blockchain
pip3 install -r requirements.txt

# Start mining
nohup python3 node.py --mine --miner-address YOUR_ADDRESS > mining.log 2>&1 &
```

### AWS EC2
Similar to DigitalOcean, use t3.medium or larger.

## Mining Best Practices

1. **Secure Your Wallet**: Never share your private key
2. **Monitor Regularly**: Check mining.log for issues
3. **Update Software**: Pull latest code regularly
4. **Backup Wallet**: Keep multiple copies of private key
5. **Calculate Costs**: Electricity + server costs vs rewards

## Network Participation

By mining, you:
- Secure the Bespin network
- Process transactions
- Earn BSP rewards
- Support decentralization

## Mining Economics

### Halving Schedule
| Period | Blocks | Reward | Total BSP |
|--------|--------|--------|-----------|
| 1 | 0-210K | 50 BSP | 10.5M |
| 2 | 210K-420K | 25 BSP | 5.25M |
| 3 | 420K-630K | 12.5 BSP | 2.625M |
| ... | ... | ... | ... |

### Long-term
After all BSP is mined, miners earn from transaction fees only.

## Community

- Website: https://bespincoin.com
- Explorer: https://bespincoin.com/explorer.html
- Wallet: https://wallet.bespincoin.com

## Support

Questions? Contact: contact@bespincoin.com

## Legal

Mining cryptocurrency may have tax implications in your jurisdiction. Consult a tax professional.

Bespin is experimental software. Mine at your own risk.

---

Happy Mining! ⛏️
