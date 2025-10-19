# backend/app/config.py
"""
Configuration classes for different environments
"""

import os
from datetime import timedelta

class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # MongoDB
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/acadwell')
    
    # Admin Credentials (hashed passwords stored in DB)
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@acadwell.com')
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    
    # Email Configuration
    MAIL_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('SMTP_PORT', 587))
    MAIL_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.getenv('SMTP_USERNAME', '')
    MAIL_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('SENDER_EMAIL', 'acadwellteam@gmail.com')
    EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
    
    # File Upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}
    
    # Rate Limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URL = "memory://"
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Frontend URL (for CORS and email links)
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    
    # Socket.IO
    SOCKETIO_MESSAGE_QUEUE = os.getenv('SOCKETIO_MESSAGE_QUEUE', None)
    
    @staticmethod
    def init_app(app):
        """Initialize application with this configuration"""
        pass


class DevelopmentConfig(Config):
    """Development configuration"""
    
    DEBUG = True
    TESTING = False
    
    # Development CORS (allow all origins)
    CORS_ORIGINS = [
        'http://localhost:5173',
        'http://localhost:3000',
        'http://127.0.0.1:5173',
        'http://127.0.0.1:3000'
    ]
    
    # Development logging
    LOG_LEVEL = 'DEBUG'
    
    # Disable rate limiting in development
    RATELIMIT_ENABLED = False
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        print("🔧 Running in DEVELOPMENT mode")


class ProductionConfig(Config):
    """Production configuration"""
    
    DEBUG = False
    TESTING = False
    
    # Production CORS (strict origins)
    CORS_ORIGINS = [
        os.getenv('FRONTEND_URL', 'https://acadwell.vercel.app'),
        'https://acadwell.vercel.app',
        'https://www.acadwell.com',  # If you add custom domain
    ]
    
    # Production logging
    LOG_LEVEL = 'WARNING'
    
    # Enable rate limiting in production
    RATELIMIT_ENABLED = True
    
    # Use Redis for rate limiting if available
    REDIS_URL = os.getenv('REDIS_URL', None)
    if REDIS_URL:
        RATELIMIT_STORAGE_URL = REDIS_URL
    
    # Socket.IO with Redis (if available)
    SOCKETIO_MESSAGE_QUEUE = os.getenv('REDIS_URL', None)
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        
        # Production-specific initialization
        import logging
        from logging.handlers import RotatingFileHandler
        
        # Set up file logging
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = RotatingFileHandler(
            'logs/acadwell.log',
            maxBytes=10240000,  # 10MB
            backupCount=10
        )
        
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('🚀 AcadWell Production Startup')


class TestingConfig(Config):
    """Testing configuration"""
    
    DEBUG = True
    TESTING = True
    
    # Use test database
    MONGO_URI = os.getenv('TEST_MONGO_URI', 'mongodb://localhost:27017/acadwell_test')
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False
    
    # Disable rate limiting in tests
    RATELIMIT_ENABLED = False
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        print("🧪 Running in TESTING mode")


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(config_name=None):
    """Get configuration based on environment"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    
    return config.get(config_name, config['default'])