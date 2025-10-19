# backend/app/__init__.py
"""
AcadWell Flask Application Factory
Creates and configures the Flask app with all extensions and blueprints
"""
from flask import request  # Add this import at the very top
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime
import os

def create_app(config_name=None):
    """
    Application factory pattern
    Creates and configures the Flask application
    """
    
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    
    from app.config import get_config
    config_class = get_config(config_name)
    app.config.from_object(config_class)
    
    # Initialize configuration
    config_class.init_app(app)
    
    # ✅ CRITICAL FIX: Configure CORS BEFORE registering blueprints
    cors_origins = [
        'https://acadwell-frontend.vercel.app',
        'https://acadwell.vercel.app',
        'http://localhost:3000',
        'http://localhost:5173',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:5173'
    ]
    
    CORS(app,
         origins=cors_origins,
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
         allow_headers=['Content-Type', 'Authorization'],
         expose_headers=['Content-Type', 'Authorization'],
         supports_credentials=True,
         max_age=3600)
    
    # Also enable CORS on every route explicitly
    @app.after_request
    def after_request(response):
        """Add CORS headers to every response"""
        origin = os.environ.get('HTTP_ORIGIN', request.headers.get('Origin', ''))
        
        # Allow the origin if it's in our list
        if origin in cors_origins:
            response.headers.add('Access-Control-Allow-Origin', origin)
        elif 'localhost' in origin or '127.0.0.1' in origin:
            response.headers.add('Access-Control-Allow-Origin', origin)
        else:
            # Allow Vercel frontend
            response.headers.add('Access-Control-Allow-Origin', 'https://acadwell-frontend.vercel.app')
        
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS,PATCH')
        response.headers.add('Access-Control-Expose-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        
        return response
    
    # Initialize JWT
    jwt = JWTManager(app)
    
    # JWT Error Handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'error': 'Token has expired',
            'message': 'Please login again'
        }), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            'error': 'Invalid token',
            'message': 'Token verification failed'
        }), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            'error': 'Authorization required',
            'message': 'Request does not contain a valid token'
        }), 401
    
    # Initialize MongoDB connection
    try:
        client = MongoClient(
            app.config['MONGO_URI'],
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            maxPoolSize=50,
            minPoolSize=10
        )
        
        # Test connection
        client.server_info()
        
        # Set database on app
        app.db = client.acadwell
        
        # Create indexes for performance
        _create_indexes(app.db)
        
        print("✅ MongoDB connected successfully to 'acadwell' database")
        
    except ConnectionFailure as e:
        print(f"❌ MongoDB connection failed: {e}")
        app.db = None
    except Exception as e:
        print(f"❌ Unexpected database error: {e}")
        app.db = None
    
    # Register blueprints
    _register_blueprints(app)
    
    # Register error handlers
    _register_error_handlers(app)
    
    # Register health check and test endpoints
    _register_utility_routes(app)
    
    return app


def _create_indexes(db):
    """Create database indexes for better performance"""
    try:
        # Users collection indexes
        db.users.create_index("email", unique=True)
        db.users.create_index("user_id", unique=True)
        db.users.create_index("role")
        
        # Community posts indexes
        db.community_posts.create_index([("created_at", -1)])
        db.community_posts.create_index("author_id")
        
        # Messages indexes
        db.messages.create_index([("created_at", -1)])
        db.messages.create_index([("sender_id", 1), ("recipient_id", 1)])
        
        # Wellness indexes
        db.wellness_logs.create_index([("user_id", 1), ("created_at", -1)])
        db.wellness_alerts.create_index([("student_id", 1), ("created_at", -1)])
        db.wellness_alerts.create_index("severity")
        
        # Mental health logs indexes
        db.mental_health_logs.create_index([("user_id", 1), ("timestamp", -1)])
        
        print("✅ Database indexes created successfully")
        
    except Exception as e:
        print(f"⚠️  Warning: Could not create indexes: {e}")


def _register_blueprints(app):
    """Register all Flask blueprints"""
    
    # Import blueprints
    from app.api.auth import auth_bp
    from app.api.questions import questions_bp
    from app.api.messages import messages_bp
    from app.api.community import community_bp
    from app.api.profile import profile_bp
    from app.api.mental_health import mental_health_bp
    from app.api.teacher_profile import teacher_profile_bp
    from app.api.wellness import wellness_bp
    from app.api.grades import students_bp, teacher_bp
    from app.api.groups import groups_bp
    from app.api.admin import admin_bp
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(questions_bp, url_prefix='/api/questions')
    app.register_blueprint(messages_bp, url_prefix='/api/messages')
    app.register_blueprint(community_bp, url_prefix='/api/community')
    app.register_blueprint(profile_bp, url_prefix='/api/profile')
    app.register_blueprint(mental_health_bp, url_prefix='/api/mental-health')
    app.register_blueprint(teacher_profile_bp, url_prefix='/api/teacher_profile')
    app.register_blueprint(wellness_bp, url_prefix='/api/wellness')
    app.register_blueprint(students_bp, url_prefix='/api/student')
    app.register_blueprint(teacher_bp, url_prefix='/api/teacher')
    app.register_blueprint(groups_bp, url_prefix='/api/groups')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    
    print("✅ All blueprints registered successfully")


def _register_error_handlers(app):
    """Register global error handlers"""
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'error': 'Bad Request',
            'message': str(error)
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Authentication required'
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({
            'error': 'Forbidden',
            'message': 'You do not have permission to access this resource'
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'Not Found',
            'message': 'The requested resource was not found'
        }), 404
    
    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred'
        }), 500


def _register_utility_routes(app):
    """Register health check and utility routes"""
    
    @app.route('/')
    def index():
        """Root endpoint"""
        return jsonify({
            'service': 'AcadWell API',
            'version': '2.0',
            'status': 'running',
            'environment': os.getenv('FLASK_ENV', 'development'),
            'timestamp': datetime.utcnow().isoformat()
        })
    
    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring"""
        health_status = {
            'status': 'healthy',
            'service': 'acadwell-api',
            'version': '2.0',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Check database connection
        try:
            if app.db is not None:
                app.db.command('ping')
                health_status['database'] = 'connected'
            else:
                health_status['database'] = 'disconnected'
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['database'] = 'error'
            health_status['database_error'] = str(e)
            health_status['status'] = 'unhealthy'
        
        status_code = 200 if health_status['status'] == 'healthy' else 503
        
        return jsonify(health_status), status_code
    
    @app.route('/api/test')
    def test_endpoint():
        """Test endpoint to verify API is working"""
        return jsonify({
            'message': 'AcadWell Backend is working!',
            'environment': os.getenv('FLASK_ENV', 'development'),
            'database': 'connected' if app.db is not None else 'disconnected',
            'timestamp': datetime.utcnow().isoformat()
        })
    
    @app.route('/api/config')
    def get_config_info():
        """Get non-sensitive configuration info"""
        return jsonify({
            'environment': os.getenv('FLASK_ENV', 'development'),
            'debug': app.debug,
            'database': 'connected' if app.db is not None else 'disconnected',
            'email_enabled': app.config.get('EMAIL_ENABLED', False),
            'frontend_url': app.config.get('FRONTEND_URL', 'not set'),
            'cors_origins': [
                'https://acadwell-frontend.vercel.app',
                'https://acadwell.vercel.app'
            ]
        })
