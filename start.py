"""Entry point for production deployment (Render.com)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from init_db import init_db
init_db()

import uvicorn

port = int(os.environ.get('PORT', 8000))

if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=port, log_level='info')
