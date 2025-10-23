"""
WSGI entry point for production (Render deployment)
"""
import eventlet
eventlet.monkey_patch()

from app import create_app
from app.extensions import socketio
import os

# Create app instance
app = create_app()

if __name__ == '__main__':
    # Run with socketio for production
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=False
    )