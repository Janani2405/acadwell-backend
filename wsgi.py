# FILE 2: backend/wsgi.py
# Create this NEW file in your backend root directory

"""
WSGI entry point for production (Render, Heroku, etc.)
"""

from app import create_app
from app.extensions import socketio
import os

# Create app instance
app = create_app()

# Initialize Socket.IO
socketio.init_app(
    app,
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    async_mode='eventlet',
    manage_session=False
)

if __name__ == '__main__':
    # For local testing only
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=False
    )