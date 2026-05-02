"""
Team Operations Hub — Simple Multi-User Backend
================================================
Designed for small trusted teams (2-15 people). No login required.

Features:
  • Per-item updates — two people editing different tasks won't overwrite each other
  • Optional API key — set TEAM_OPS_API_KEY to require X-API-Key header (recommended for production)
  • JSON file storage — single data.json, no database setup
  • CORS-permissive — works from any frontend URL out of the box
  • "Last edited by" tracking — each item records who touched it last (frontend sends user name)

Endpoints:
  GET    /api/health                        → health check
  GET    /api/data                          → fetch all data + last_modified
  PUT    /api/data                          → bulk replace (admin/migration use)
  GET    /api/{collection}                  → list (team / projects / tasks)
  POST   /api/{collection}                  → create or upsert single item
  PATCH  /api/{collection}/{id}             → update single item by id
  DELETE /api/{collection}/{id}             → delete single item by id

Setup (local):
  pip install -r requirements.txt
  python app.py

Setup (Render.com — recommended, free):
  1. Push this folder to GitHub
  2. Render → New Blueprint → connect repo (uses render.yaml)
  3. Open the URL shown after deploy
  4. In frontend: Data & Sync → paste URL → Connect

Environment variables (all optional):
  TEAM_OPS_API_KEY     If set, requires X-API-Key header on all writes
  ALLOWED_ORIGINS      Default: *
  DATA_FILE            Default: data.json
  PORT                 Default: 5000
"""

import os
import json
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, abort
from flask_cors import CORS

# ---------- Config ----------
API_KEY         = os.environ.get('TEAM_OPS_API_KEY', '')  # empty = no auth (trusted team mode)
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*')
DATA_FILE       = Path(os.environ.get('DATA_FILE', 'data.json'))
PORT            = int(os.environ.get('PORT', 5000))

app = Flask(__name__)
CORS(
    app,
    resources={r"/api/*": {"origins": ALLOWED_ORIGINS.split(',') if ALLOWED_ORIGINS != '*' else '*'}},
    expose_headers=['X-Last-Modified'],
    allow_headers=['Content-Type', 'X-API-Key', 'X-User-Name'],
)

_data_lock = threading.RLock()

DEFAULT_DATA = {'team': [], 'projects': [], 'tasks': []}
COLLECTIONS = {'team', 'projects', 'tasks'}

# ---------- Storage ----------
def load_data() -> dict:
    with _data_lock:
        if not DATA_FILE.exists():
            save_data(DEFAULT_DATA)
            return dict(DEFAULT_DATA)
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key in DEFAULT_DATA:
                if key not in data:
                    data[key] = []
            return data
        except (json.JSONDecodeError, OSError) as e:
            app.logger.error(f"Failed to load data file: {e}")
            return dict(DEFAULT_DATA)

def save_data(data: dict) -> None:
    with _data_lock:
        tmp = DATA_FILE.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(DATA_FILE)

def get_last_modified() -> str:
    if DATA_FILE.exists():
        return datetime.fromtimestamp(DATA_FILE.stat().st_mtime).isoformat()
    return datetime.now().isoformat()

# ---------- Auth (optional API key) ----------
@app.before_request
def check_api_key():
    if request.method == 'OPTIONS':
        return  # CORS preflight
    if not API_KEY:
        return  # auth disabled (trusted team mode)
    if not request.path.startswith('/api/'):
        return
    if request.path == '/api/health':
        return  # health check is always public
    provided = request.headers.get('X-API-Key', '')
    if provided != API_KEY:
        abort(401, description='Invalid or missing X-API-Key header')

# ---------- Helpers ----------
def validate_collection(name: str):
    if name not in COLLECTIONS:
        abort(404, description=f"Unknown collection '{name}'. Valid: {sorted(COLLECTIONS)}")

def find_index(items: list, item_id: str):
    for i, item in enumerate(items):
        if item.get('id') == item_id:
            return i
    return -1

def stamp_metadata(item: dict) -> dict:
    """Add server-side metadata to item."""
    user = request.headers.get('X-User-Name', '').strip() or 'anonymous'
    return {
        **item,
        '_updated_at': datetime.now().isoformat(),
        '_updated_by': user,
    }

# ---------- Routes ----------
@app.route('/api/health')
def health():
    data = load_data()
    return jsonify({
        'status': 'ok',
        'service': 'team-ops-hub-backend',
        'version': '1.5-simple',
        'auth_required': bool(API_KEY),
        'last_modified': get_last_modified(),
        'counts': {k: len(data.get(k, [])) for k in DEFAULT_DATA},
    })

# Full snapshot
@app.route('/api/data', methods=['GET'])
def get_all_data():
    data = load_data()
    response = jsonify({
        **data,
        '_meta': {'last_modified': get_last_modified()},
    })
    response.headers['X-Last-Modified'] = get_last_modified()
    return response

@app.route('/api/data', methods=['PUT'])
def replace_all_data():
    """Bulk replace — used for backup restore or full migration."""
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict):
        abort(400, description='Body must be a JSON object with keys: team, projects, tasks')
    new_data = {key: payload.get(key, []) for key in DEFAULT_DATA}
    for key, value in new_data.items():
        if not isinstance(value, list):
            abort(400, description=f"'{key}' must be an array")
    save_data(new_data)
    return jsonify({'status': 'ok', 'last_modified': get_last_modified()})

# Single collection
@app.route('/api/<collection>', methods=['GET'])
def get_collection(collection):
    validate_collection(collection)
    data = load_data()
    return jsonify(data[collection])

@app.route('/api/<collection>', methods=['POST'])
def upsert_item(collection):
    """Create or upsert (replace) an item by id. Per-item endpoint."""
    validate_collection(collection)
    item = request.get_json(force=True, silent=True)
    if not isinstance(item, dict) or not item.get('id'):
        abort(400, description="Body must be a JSON object with non-empty 'id'")

    item = stamp_metadata(item)
    with _data_lock:
        data = load_data()
        idx = find_index(data[collection], item['id'])
        if idx >= 0:
            data[collection][idx] = item  # replace
        else:
            data[collection].append(item)
        save_data(data)
    return jsonify(item), 201

@app.route('/api/<collection>/<item_id>', methods=['PATCH'])
def update_item(collection, item_id):
    """Merge-update a single item. Two people editing different fields of the same item still merge cleanly."""
    validate_collection(collection)
    patch = request.get_json(force=True, silent=True)
    if not isinstance(patch, dict):
        abort(400, description='Body must be a JSON object')

    with _data_lock:
        data = load_data()
        idx = find_index(data[collection], item_id)
        if idx < 0:
            abort(404, description=f"Item '{item_id}' not found in {collection}")
        merged = {**data[collection][idx], **patch, 'id': item_id}
        merged = stamp_metadata(merged)
        data[collection][idx] = merged
        save_data(data)
    return jsonify(merged)

@app.route('/api/<collection>/<item_id>', methods=['DELETE'])
def delete_item(collection, item_id):
    validate_collection(collection)
    with _data_lock:
        data = load_data()
        idx = find_index(data[collection], item_id)
        if idx < 0:
            abort(404, description=f"Item '{item_id}' not found in {collection}")
        removed = data[collection].pop(idx)
        save_data(data)
    return jsonify({'status': 'ok', 'removed_id': item_id})

# ---------- Error handlers ----------
@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(404)
def handle_error(e):
    return jsonify({'error': str(e.description) if hasattr(e, 'description') else str(e), 'code': e.code}), e.code

# ---------- Main ----------
if __name__ == '__main__':
    print(f"🚀 Team Ops Hub — Simple Backend")
    print(f"📁 Data file: {DATA_FILE.resolve()}")
    print(f"🔑 API key: {'enabled' if API_KEY else 'disabled (trusted team mode)'}")
    print(f"🌐 Port: {PORT}")
    print(f"💡 Frontend: open Data & Sync, paste this URL")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
