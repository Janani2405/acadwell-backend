# backend/app/middleware/admin_auth.py
"""
Admin Authentication Middleware
Verifies that the user has admin role
"""

from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt

def admin_required(fn):
    """
    Decorator to require admin role for protected routes
    Place this AFTER @jwt_required() if both are used
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Verify JWT is present
        verify_jwt_in_request()
        
        # Get JWT claims
        claims = get_jwt()
        
        # Check if user has admin role
        user_role = claims.get('role')
        
        if user_role != 'admin':
            return jsonify({
                'error': 'Admin access required',
                'message': 'You do not have permission to access this resource',
                'required_role': 'admin',
                'your_role': user_role
            }), 403
        
        return fn(*args, **kwargs)
    
    return wrapper