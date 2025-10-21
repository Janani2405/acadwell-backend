# backend/run.py
"""
AcadWell Backend - Production Entry Point
FIXED: Socket.IO connection issues
"""

from app import create_app
from app.extensions import socketio
import os
import socket
#for enbaling email 
from dotenv import load_dotenv
import os

# Load environment variables from .env.development
load_dotenv('.env.development')

# from app import create_app
# from app.extensions import socketio
# import socket
def get_local_ip():
    """Get the local LAN IP address (Windows compatible)"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'

def get_cors_origins():
    """Generate CORS origins based on environment"""
    environment = os.getenv('FLASK_ENV', 'development')
    
    if environment == 'production':
        origins = [
            os.getenv('FRONTEND_URL', 'https://acadwell.vercel.app'),
            'https://acadwell.vercel.app',
        ]
        additional = os.getenv('ADDITIONAL_CORS_ORIGINS', '')
        if additional:
            origins.extend([origin.strip() for origin in additional.split(',')])
    else:
        # Development - Allow multiple ports and IPs
        port = int(os.getenv('FRONTEND_PORT', 3000))
        lan_ip = get_local_ip()
        
        origins = [
            f'http://localhost:{port}',
            f'http://127.0.0.1:{port}',
            f'http://{lan_ip}:{port}',
            'http://localhost:5173',  # Vite default
            'http://127.0.0.1:5173',
            f'http://{lan_ip}:5173',
        ]
        
        additional = os.getenv('ADDITIONAL_CORS_ORIGINS', '')
        if additional:
            origins.extend([origin.strip() for origin in additional.split(',')])
    
    return list(set(origins))

def print_startup_info(environment, port, lan_ip=None):
    """Print startup information"""
    print("\n" + "="*60)
    print("🎓 AcadWell Backend Server")
    print("="*60)
    print(f"📍 Environment: {environment.upper()}")
    print(f"🌐 Port: {port}")
    
    if environment == 'development':
        print(f"\n🖥️  Server accessible at:")
        print(f"   • Local:  http://localhost:{port}")
        print(f"   • LAN:    http://{lan_ip}:{port}")
        print(f"\n🔗 Health Check:")
        print(f"   • http://localhost:{port}/health")
    else:
        print(f"\n🚀 Production Mode")
        print(f"   • Render URL: {os.getenv('RENDER_EXTERNAL_URL', 'pending')}")
    
    print(f"\n📊 Database: {'Connected' if os.getenv('MONGO_URI') else 'Not Configured'}")
    print(f"🔐 JWT: {'Configured' if os.getenv('JWT_SECRET_KEY') else 'Using Default'}")
    print(f"📧 Email: {'Enabled' if os.getenv('EMAIL_ENABLED') == 'true' else 'Disabled'}")
    print("="*60 + "\n")

# Create Flask app instance
app = create_app()

if __name__ == '__main__':
    # Get configuration
    environment = os.getenv('FLASK_ENV', 'development')
    port = int(os.getenv('PORT', 5000))
    
    # Get CORS origins
    cors_origins = get_cors_origins()
    
    # ✅ CRITICAL FIX: Initialize Socket.IO with proper CORS settings
    socketio.init_app(
        app,
        cors_allowed_origins='*',  # Allow all origins in development
        # For production, use: cors_allowed_origins=cors_origins,
        logger=True,  # Enable Socket.IO logging to see connection attempts
        engineio_logger=True,  # Enable Engine.IO logging
        ping_timeout=60,
        ping_interval=25,
        async_mode='eventlet',  # ✅ IMPORTANT: Specify async mode
        manage_session=False  # ✅ Let Flask handle sessions
    )
    
    # Print startup information
    if environment == 'development':
        lan_ip = get_local_ip()
        print_startup_info(environment, port, lan_ip)
        print(f"✅ CORS enabled for all origins (development mode)")
        print(f"✅ Socket.IO initialized with eventlet")
        print(f"✅ Socket.IO endpoint: http://localhost:{port}/socket.io\n")
    else:
        print_startup_info(environment, port)
    
    # Run server with eventlet
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=(environment == 'development'),
        use_reloader=False,  # ✅ IMPORTANT: Disable reloader with eventlet
        log_output=True
    )