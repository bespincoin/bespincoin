"""
WSGI entry point for gunicorn
Initializes blockchain node and exposes Flask app

Usage:
  gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 16 --timeout 120 --worker-class gthread wsgi:app

Environment variables (optional):
  SEED_NODES       - Comma-separated seed nodes e.g. api.bespincoin.com:5000
  FOUNDER_ADDRESS  - BSP address for founder allocation (genesis block only)
  NODE_PORT        - P2P port (default: 5000)
  API_PORT         - API port (default: 8000)
"""
import sys
import os

# Add current directory to path so imports work from any location
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import init_node

# Parse seed nodes from env var
_seeds_env = os.environ.get('SEED_NODES', '')
seed_nodes = [s.strip() for s in _seeds_env.split(',') if s.strip()]

# Initialize node on startup - runs once per worker
app = init_node(
    port=int(os.environ.get('NODE_PORT', 5000)),
    api_port=int(os.environ.get('API_PORT', 8000)),
    seed_nodes=seed_nodes,
    founder_address=os.environ.get('FOUNDER_ADDRESS', None)
)

if __name__ == '__main__':
    app.run()
