#!/usr/bin/env python3
"""
Simple API to store bridge requests
Users submit: BSP amount + Polygon address
Bot checks this to know where to mint wBSP
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)
DB_FILE = "/root/bridge_requests.db"
REQUEST_EXPIRY_MINUTES = 30

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bridge_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  polygon_address TEXT,
                  bsp_amount REAL,
                  bsp_from_address TEXT,
                  email TEXT,
                  timestamp TEXT,
                  status TEXT DEFAULT 'pending',
                  bsp_txid TEXT,
                  polygon_txid TEXT)''')
    conn.commit()
    conn.close()

@app.route('/bridge/request', methods=['POST'])
def create_request():
    """Create a new bridge request"""
    data = request.json
    
    polygon_addr = data.get('polygon_address')
    bsp_amount = data.get('bsp_amount')
    bsp_from_address = data.get('bsp_from_address', '').strip()
    email = data.get('email', '')
    
    if not polygon_addr or not bsp_amount:
        return jsonify({'error': 'Missing required fields'}), 400

    # One pending request per BSP address at a time
    if bsp_from_address:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id FROM bridge_requests WHERE bsp_from_address=? AND status='pending'", (bsp_from_address,))
        existing = c.fetchone()
        conn.close()
        if existing:
            return jsonify({'error': 'You already have a pending bridge request. Wait for it to complete or expire (30 min).'}), 400
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now()
    expires_at = (now + timedelta(minutes=REQUEST_EXPIRY_MINUTES)).isoformat()
    c.execute("""INSERT INTO bridge_requests 
                 (polygon_address, bsp_amount, bsp_from_address, email, timestamp, status)
                 VALUES (?, ?, ?, ?, ?, 'pending')""",
              (polygon_addr, bsp_amount, bsp_from_address, email, now.isoformat()))
    request_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'request_id': request_id,
        'polygon_address': polygon_addr,
        'bsp_amount': bsp_amount,
        'bsp_from_address': bsp_from_address,
        'expires_at': expires_at,
        'message': f'Send {bsp_amount} BSP to bridge address within 30 minutes'
        'bridge_address': '1BEdzEJXqAcfWpZDK3ePJiCAcjUL4rnMVw',
        'status': 'pending',
        'message': f'Send {bsp_amount} BSP to bridge address from {bsp_from_address or "your BSP wallet"}'
    })

@app.route('/bridge/pending', methods=['GET'])
def get_pending():
    """Get all pending bridge requests"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM bridge_requests WHERE status='pending'")
    rows = c.fetchall()
    conn.close()
    
    requests = []
    for row in rows:
        requests.append({
            'id': row[0],
            'polygon_address': row[1],
            'bsp_amount': row[2],
            'bsp_from_address': row[3],
            'email': row[4],
            'timestamp': row[5],
            'status': row[6]
        })
    
    return jsonify(requests)

@app.route('/bridge/status/<int:request_id>', methods=['GET'])
def get_status(request_id):
    """Get status of a bridge request"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM bridge_requests WHERE id=?", (request_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return jsonify({'error': 'Request not found'}), 404
    
    return jsonify({
        'id': row[0],
        'polygon_address': row[1],
        'bsp_amount': row[2],
        'status': row[6],
        'bsp_txid': row[7],
        'polygon_txid': row[8]
    })

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8001)
