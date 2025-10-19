# backend/app/api/auth.py
# FIXED: Email sending disabled for production deployment
# Registration now works without email verification

from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import uuid
import secrets
import re

auth_bp = Blueprint('auth', __name__)

# ==================== STUDENT REGISTRATION ====================

@auth_bp.route('/register/student', methods=['POST'])
def register_student():
    """Register a new student"""
    try:
        data = request.get_json()
        required_fields = ["name", "regNumber", "email", "password", "university", "year", "field"]

        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        # Validate email format
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', data["email"]):
            return jsonify({"error": "Invalid email format"}), 400

        # Validate password strength
        if len(data["password"]) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400

        db = current_app.db
        users = db.users

        # Check if email already exists
        if users.find_one({"email": data["email"].lower()}):
            return jsonify({"error": "Email already registered"}), 409

        # Check if registration number already exists
        if users.find_one({"regNumber": data["regNumber"]}):
            return jsonify({"error": "Registration number already in use"}), 409

        hashed_pw = generate_password_hash(data["password"])
        user_id = str(uuid.uuid4())
        
        new_user = {
            "user_id": user_id,
            "role": "student",
            "name": data["name"],
            "regNumber": data["regNumber"],
            "email": data["email"].lower(),
            "password": hashed_pw,
            "university": data["university"],
            "year": data["year"],
            "field": data["field"],
            "is_verified": True,  # Auto-verify for production
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        users.insert_one(new_user)
        
        print(f"✅ Student registered: {user_id} - {data['name']}")
        
        return jsonify({
            "message": "Registration successful! You can now login.",
            "user_id": user_id,
            "action": "login"
        }), 201

    except Exception as e:
        print(f"❌ Error in student registration: {e}")
        return jsonify({"error": "Registration failed. Please try again."}), 500


# ==================== TEACHER REGISTRATION ====================

@auth_bp.route('/register/teacher', methods=['POST'])
def register_teacher():
    """Register a new teacher"""
    try:
        data = request.get_json()
        required_fields = ["name", "empNumber", "email", "password", "department", "designation", "expertise", "experience"]

        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', data["email"]):
            return jsonify({"error": "Invalid email format"}), 400

        if len(data["password"]) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400

        db = current_app.db
        users = db.users

        if users.find_one({"email": data["email"].lower()}):
            return jsonify({"error": "Email already registered"}), 409

        if users.find_one({"empNumber": data["empNumber"]}):
            return jsonify({"error": "Employee number already registered"}), 409

        hashed_pw = generate_password_hash(data["password"])
        user_id = str(uuid.uuid4())
        
        new_user = {
            "user_id": user_id,
            "role": "teacher",
            "name": data["name"],
            "empNumber": data["empNumber"],
            "email": data["email"].lower(),
            "password": hashed_pw,
            "department": data["department"],
            "designation": data["designation"],
            "expertise": data["expertise"],
            "experience": data["experience"],
            "is_verified": True,  # Auto-verify for production
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        users.insert_one(new_user)
        
        print(f"✅ Teacher registered: {user_id} - {data['name']}")
        
        return jsonify({
            "message": "Registration successful! You can now login.",
            "user_id": user_id,
            "action": "login"
        }), 201

    except Exception as e:
        print(f"❌ Error in teacher registration: {e}")
        return jsonify({"error": "Registration failed. Please try again."}), 500


# ==================== OTHERS REGISTRATION ====================

@auth_bp.route('/register/others', methods=['POST'])
def register_others():
    """Register others (mentors, counselors, etc.)"""
    try:
        data = request.get_json()
        required_fields = ["name", "regNumber", "email", "password", "organization", "role", "contribution"]

        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        valid_roles = ["mentor", "counselor", "alumni", "contributor"]
        if data["role"].lower() not in valid_roles:
            return jsonify({"error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"}), 400

        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', data["email"]):
            return jsonify({"error": "Invalid email format"}), 400

        if len(data["password"]) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400

        db = current_app.db
        users = db.users

        if users.find_one({"email": data["email"].lower()}):
            return jsonify({"error": "Email already registered"}), 409

        if users.find_one({"regNumber": data["regNumber"]}):
            return jsonify({"error": "Registration number already in use"}), 409

        hashed_pw = generate_password_hash(data["password"])
        user_id = str(uuid.uuid4())
        
        new_user = {
            "user_id": user_id,
            "role": "others",
            "specific_role": data["role"].lower(),
            "name": data["name"],
            "regNumber": data["regNumber"],
            "email": data["email"].lower(),
            "password": hashed_pw,
            "organization": data["organization"],
            "contribution": data["contribution"],
            "is_verified": True,  # Auto-verify for production
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        users.insert_one(new_user)
        
        print(f"✅ Others registered: {user_id} - {data['name']}")
        
        return jsonify({
            "message": "Registration successful! You can now login.",
            "user_id": user_id,
            "action": "login"
        }), 201

    except Exception as e:
        print(f"❌ Error in others registration: {e}")
        return jsonify({"error": "Registration failed. Please try again."}), 500


# ==================== LOGIN ====================

@auth_bp.route('/login', methods=['POST'])
def login():
    """Login for all user types"""
    try:
        data = request.get_json()
        email = data.get("email", "").lower()
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        db = current_app.db
        user = db.users.find_one({"email": email})

        if not user:
            return jsonify({"error": "Invalid email or password"}), 401

        if not check_password_hash(user["password"], password):
            return jsonify({"error": "Invalid email or password"}), 401

        user_id = str(user["user_id"])
        user_role = user["role"]
        user_name = user["name"]
        
        print(f"✅ Login successful: {user_id} ({user_name}) - Role: {user_role}")

        access_token = create_access_token(
            identity=user_id,
            additional_claims={"role": user_role},
            expires_delta=timedelta(hours=24)
        )

        response_data = {
            "message": "Login successful",
            "token": access_token,
            "role": user_role,
            "name": user_name,
            "user_id": user_id,
            "email": user["email"]
        }
        
        if user_role == "others" and "specific_role" in user:
            response_data["specific_role"] = user["specific_role"]
        
        return jsonify(response_data), 200

    except Exception as e:
        print(f"❌ Error in login: {e}")
        return jsonify({"error": "Login failed. Please try again."}), 500


# ==================== GET CURRENT USER ====================

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current logged-in user information"""
    try:
        current_user_id = get_jwt_identity()
        
        db = current_app.db
        user = db.users.find_one({"user_id": current_user_id}, {"password": 0})
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        user_data = {
            "user_id": str(user["user_id"]),
            "name": user["name"],
            "role": user["role"],
            "email": user["email"]
        }
        
        if user["role"] == "student":
            user_data.update({
                "regNumber": user.get("regNumber"),
                "university": user.get("university"),
                "year": user.get("year"),
                "field": user.get("field")
            })
        elif user["role"] == "teacher":
            user_data.update({
                "empNumber": user.get("empNumber"),
                "department": user.get("department"),
                "designation": user.get("designation")
            })
        
        return jsonify(user_data), 200

    except Exception as e:
        print(f"❌ Error fetching current user: {e}")
        return jsonify({"error": "Failed to fetch user information"}), 500


# ==================== UPDATE USER PROFILE ====================

@auth_bp.route('/update-profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile information"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        db = current_app.db
        user = db.users.find_one({"user_id": current_user_id})
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        update_data = {}
        if "name" in data:
            update_data["name"] = data["name"]
        
        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400
        
        update_data["updated_at"] = datetime.utcnow()
        
        db.users.update_one(
            {"user_id": current_user_id},
            {"$set": update_data}
        )
        
        print(f"✅ Profile updated: {current_user_id}")
        
        return jsonify({"message": "Profile updated successfully"}), 200

    except Exception as e:
        print(f"❌ Error updating profile: {e}")
        return jsonify({"error": "Failed to update profile"}), 500


# ==================== CHANGE PASSWORD ====================

@auth_bp.route('/change-password', methods=['PUT'])
@jwt_required()
def change_password():
    """Change password for authenticated user"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        current_password = data.get("current_password")
        new_password = data.get("new_password")
        
        if not current_password or not new_password:
            return jsonify({"error": "Current and new password are required"}), 400
        
        if len(new_password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        
        db = current_app.db
        user = db.users.find_one({"user_id": current_user_id})
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        if not check_password_hash(user["password"], current_password):
            return jsonify({"error": "Current password is incorrect"}), 401
        
        hashed_new_password = generate_password_hash(new_password)
        
        db.users.update_one(
            {"user_id": current_user_id},
            {"$set": {
                "password": hashed_new_password,
                "updated_at": datetime.utcnow()
            }}
        )
        
        print(f"✅ Password changed for user: {current_user_id}")
        
        return jsonify({"message": "Password changed successfully"}), 200

    except Exception as e:
        print(f"❌ Error changing password: {e}")
        return jsonify({"error": "Failed to change password"}), 500


# ==================== DELETE ACCOUNT ====================

@auth_bp.route('/delete-account', methods=['DELETE'])
@jwt_required()
def delete_account():
    """Delete user account"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        password = data.get("password")
        
        if not password:
            return jsonify({"error": "Password confirmation required"}), 400
        
        db = current_app.db
        user = db.users.find_one({"user_id": current_user_id})
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        if not check_password_hash(user["password"], password):
            return jsonify({"error": "Incorrect password"}), 401
        
        db.users.update_one(
            {"user_id": current_user_id},
            {"$set": {
                "is_active": False,
                "deleted_at": datetime.utcnow()
            }}
        )
        
        print(f"✅ Account deleted: {current_user_id}")
        
        return jsonify({"message": "Account deleted successfully"}), 200

    except Exception as e:
        print(f"❌ Error deleting account: {e}")
        return jsonify({"error": "Failed to delete account"}), 500


# ==================== GET ALL USERS ====================

@auth_bp.route('/users', methods=['GET'])
@jwt_required()
def list_users():
    """Get list of all users"""
    try:
        current_user_id = get_jwt_identity()
        
        db = current_app.db
        users = db.users.find({"is_active": True}, {"password": 0})

        user_list = []
        for user in users:
            user_id = str(user["user_id"])
            
            if user_id == str(current_user_id):
                continue
            
            user_data = {
                "user_id": user_id,
                "name": user["name"],
                "role": user["role"],
                "email": user["email"]
            }
            
            user_list.append(user_data)

        return jsonify({"users": user_list, "total": len(user_list)}), 200

    except Exception as e:
        print(f"❌ Error fetching users: {e}")
        return jsonify({"error": "Failed to fetch users"}), 500
