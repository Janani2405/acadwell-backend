# backend/app/extensions.py
from flask_socketio import SocketIO

# Initialize SocketIO without app (we'll bind it later)
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True
)