#!/usr/bin/env python3
"""
Blockchain Node Runner
Starts both P2P node and REST API server
"""

import argparse
from api import init_node

def main():
    parser = argparse.ArgumentParser(description='Run Bespin (BSP) blockchain node')
    parser.add_argument('--p2p-port', type=int, default=5000, 
                       help='P2P network port (default: 5000)')
    parser.add_argument('--api-port', type=int, default=8000,
                       help='REST API port (default: 8000)')
    parser.add_argument('--seeds', nargs='*', default=[],
                       help='Seed nodes (format: host:port)')
    parser.add_argument('--difficulty', type=int, default=4,
                       help='Mining difficulty (default: 4)')
    parser.add_argument('--founder-address', type=str, default=None,
                       help='Founder address for genesis allocation (20M BSP)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("BESPIN (BSP) NODE STARTING")
    print("Currency in the Clouds")
    print("=" * 60)
    print(f"P2P Port: {args.p2p_port}")
    print(f"API Port: {args.api_port}")
    print(f"Seed Nodes: {args.seeds if args.seeds else 'None (standalone mode)'}")
    print(f"Difficulty: {args.difficulty}")
    print(f"Max Supply: 100,000,000 BSP")
    print(f"Founder Allocation: 20,000,000 BSP (20%)")
    print(f"Mining Allocation: 80,000,000 BSP (80%)")
    if args.founder_address:
        print(f"Founder Address: {args.founder_address}")
    print("=" * 60)
    
    app = init_node(args.p2p_port, args.api_port, args.seeds, args.founder_address)
    
    print("\nNode is running!")
    print(f"API available at: http://localhost:{args.api_port}")
    print(f"API docs: http://localhost:{args.api_port}/info")
    print("\nPress Ctrl+C to stop")
    
    app.run(host='0.0.0.0', port=args.api_port, debug=False)

if __name__ == '__main__':
    main()
