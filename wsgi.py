"""
WSGI entry point for gunicorn
Initializes blockchain node and exposes Flask app
"""
import sys
import os
sys.path.insert(0, '/root')

from api import init_node

# Initialize node on startup - runs once per worker
app = init_node(
    port=5000,
    api_port=8000,
    seed_nodes=[],
    founder_address='1BEdzEJXqAcfWpZDK3ePJiCAcjUL4rnMVw'
)

if __name__ == '__main__':
    app.run()
