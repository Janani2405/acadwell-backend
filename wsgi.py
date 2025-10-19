"""
WSGI entry point for production (Render deployment)
FIXED: Proper CORS configuration for production
"""

from app import create_app
from app.extensions import socketio
import os
from flask_cors import CORS

# Create app instance
app = create_app()

# CRITICAL FIX: Configure CORS explicitly for production
CORS(app, 
     resources={r"/api/*": {
         "origins": [
             "https://acadwell-frontend.vercel.app",
             "https://acadwell.vercel.app",
             "http://localhost:3000",
             "http://localhost:5173",
             "http://127.0.0.1:3000",
             "http://127.0.0.1:5173"
         ],
         "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
         "allow_headers": ["Content-Type", "Authorization"],
         "expose_headers": ["Content-Type", "Authorization"],
         "supports_credentials": True,
         "max_age": 3600
     }})

# Initialize Socket.IO with CORS
socketio.init_app(
    app,
    cors_allowed_origins=[
        "https://acadwell-frontend.vercel.app",
        "https://acadwell.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173"
    ],
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    async_mode='eventlet',
    manage_session=False,
    transport=['websocket', 'polling']
)

# Debug: Print CORS configuration
@app.before_request
def log_request():
    """Log all incoming requests for debugging"""
    import logging
    logger = logging.getLogger(__name__)
    origin = os.environ.get('HTTP_ORIGIN', 'unknown')
    print(f"Request: {os.environ.get('REQUEST_METHOD')} {os.environ.get('PATH_INFO')} from {origin}")

if __name__ == '__main__':
    # For local testing only
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=False
    )
