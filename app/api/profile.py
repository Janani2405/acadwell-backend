# backend/app/api/profile.py (Complete with Certificate Upload)
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid
import os

profile_bp = Blueprint('profile', __name__)

# File upload configuration
UPLOAD_FOLDER = 'uploads/certificates'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Get current user's full profile
@profile_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    user_role = claims.get('role')

    db = current_app.db
    user = db.users.find_one({"user_id": current_user_id}, {"password": 0})
    if not user:
        return jsonify({"error": "User not found"}), 404

    profile_data = db.profiles.find_one({"user_id": current_user_id})
    if not profile_data:
        profile_data = create_default_profile(current_user_id, user_role, db)

    if "_id" in user:
        user["_id"] = str(user["_id"])
    if profile_data and "_id" in profile_data:
        profile_data["_id"] = str(profile_data["_id"])

    response = {
        "user_id": str(user["user_id"]),
        "role": user["role"],
        "name": user["name"],
        "email": user["email"],
        "created_at": user.get("created_at"),
        "profile": profile_data
    }

    if user_role == "student":
        response.update({
            "regNumber": user.get("regNumber"),
            "university": user.get("university"),
            "year": user.get("year"),
            "field": user.get("field"),
            "department": user.get("field")
        })

    elif user_role == "teacher":
        response.update({
            "empNumber": user.get("empNumber"),
            "department": user.get("department"),
            "designation": user.get("designation"),
            "expertise": user.get("expertise"),
            "experience": user.get("experience")
        })

    return jsonify(response), 200


# Get user's points and badge summary
@profile_bp.route('/points', methods=['GET'])
@jwt_required()
def get_points():
    current_user_id = get_jwt_identity()
    db = current_app.db
    
    profile = db.profiles.find_one({"user_id": current_user_id})
    if not profile:
        return jsonify({
            "total_points": 0,
            "badges": [],
            "community_activity": {
                "questionsAsked": 0,
                "answersGiven": 0,
                "acceptedAnswers": 0,
                "helpfulVotes": 0
            }
        }), 200
    
    return jsonify({
        "total_points": profile.get("total_points", 0),
        "badges": profile.get("badges", []),
        "community_activity": profile.get("communityActivity", {}),
        "points_history": profile.get("points_history", [])[-10:]  # Last 10 point events
    }), 200


# Get user's rank and leaderboard position
@profile_bp.route('/leaderboard', methods=['GET'])
@jwt_required()
def get_leaderboard():
    current_user_id = get_jwt_identity()
    db = current_app.db
    
    # Get top 10 users by points
    top_users = list(
        db.profiles.find({}, {"user_id": 1, "total_points": 1, "_id": 0})
        .sort("total_points", -1)
        .limit(10)
    )
    
    # Enrich with user names and roles
    leaderboard = []
    for idx, user_profile in enumerate(top_users, 1):
        user = db.users.find_one({"user_id": user_profile["user_id"]})
        leaderboard.append({
            "rank": idx,
            "user_id": str(user_profile["user_id"]),
            "name": user.get("name", "Unknown") if user else "Unknown",
            "points": user_profile.get("total_points", 0)
        })
    
    # Find current user's rank
    user_profile = db.profiles.find_one({"user_id": current_user_id})
    current_user_points = user_profile.get("total_points", 0) if user_profile else 0
    
    user_rank = db.profiles.count_documents(
        {"total_points": {"$gt": current_user_points}}
    ) + 1
    
    return jsonify({
        "leaderboard": leaderboard,
        "your_rank": user_rank,
        "your_points": current_user_points
    }), 200


# Get user's community activity breakdown
@profile_bp.route('/community-activity', methods=['GET'])
@jwt_required()
def get_community_activity():
    current_user_id = get_jwt_identity()
    db = current_app.db
    
    profile = db.profiles.find_one({"user_id": current_user_id})
    if not profile:
        return jsonify({
            "questionsAsked": 0,
            "answersGiven": 0,
            "acceptedAnswers": 0,
            "helpfulVotes": 0
        }), 200
    
    return jsonify(profile.get("communityActivity", {})), 200


# Update user's basic information
@profile_bp.route('/profile/basic', methods=['PUT'])
@jwt_required()
def update_basic_info():
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    user_role = claims.get('role')
    
    data = request.get_json()
    db = current_app.db
    
    # Fields that can be updated
    update_fields = {}
    
    # Common fields for all users
    if "name" in data:
        update_fields["name"] = data["name"]
    if "phone" in data:
        update_fields["phone"] = data["phone"]
    if "location" in data:
        update_fields["location"] = data["location"]
    
    # Update users collection
    if update_fields:
        db.users.update_one(
            {"user_id": current_user_id},
            {"$set": update_fields}
        )
    
    # Update profile collection
    profile_updates = {}
    if "phone" in data:
        profile_updates["phone"] = data["phone"]
    if "location" in data:
        profile_updates["location"] = data["location"]
    
    if profile_updates:
        db.profiles.update_one(
            {"user_id": current_user_id},
            {"$set": profile_updates},
            upsert=True
        )
    
    return jsonify({"message": "Profile updated successfully"}), 200


# Update enrolled courses (Student only)
@profile_bp.route('/profile/courses', methods=['PUT'])
@jwt_required()
def update_courses():
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    
    if claims.get('role') != 'student':
        return jsonify({"error": "Only students can update courses"}), 403
    
    data = request.get_json()
    courses = data.get("enrolledCourses", [])
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"enrolledCourses": courses}},
        upsert=True
    )
    
    return jsonify({"message": "Courses updated successfully"}), 200


# Update course progress
@profile_bp.route('/profile/courses/<course_id>/progress', methods=['PUT'])
@jwt_required()
def update_course_progress(course_id):
    current_user_id = get_jwt_identity()
    data = request.get_json()
    progress = data.get("progress", 0)
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id, "enrolledCourses.id": int(course_id)},
        {"$set": {"enrolledCourses.$.progress": progress}}
    )
    
    return jsonify({"message": "Course progress updated"}), 200


# Update grades
@profile_bp.route('/profile/grades', methods=['PUT'])
@jwt_required()
def update_grades():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"grades": data}},
        upsert=True
    )
    
    return jsonify({"message": "Grades updated successfully"}), 200


# Add mood log (Student only)
@profile_bp.route('/profile/mood', methods=['POST'])
@jwt_required()
def add_mood_log():
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    
    if claims.get('role') != 'student':
        return jsonify({"error": "Only students can log mood"}), 403
    
    data = request.get_json()
    mood_entry = {
        "date": data.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
        "mood": data.get("mood"),
        "note": data.get("note", "")
    }
    
    db = current_app.db
    
    # Add to beginning of array (most recent first) and limit to last 30 days
    db.profiles.update_one(
        {"user_id": current_user_id},
        {
            "$push": {
                "recentMoods": {
                    "$each": [mood_entry],
                    "$position": 0,
                    "$slice": 30
                }
            }
        },
        upsert=True
    )
    
    return jsonify({"message": "Mood logged successfully"}), 201


# Get mood logs
@profile_bp.route('/profile/mood', methods=['GET'])
@jwt_required()
def get_mood_logs():
    current_user_id = get_jwt_identity()
    
    db = current_app.db
    profile = db.profiles.find_one({"user_id": current_user_id})
    
    if not profile:
        return jsonify({"recentMoods": []}), 200
    
    return jsonify({"recentMoods": profile.get("recentMoods", [])}), 200


# Update community activity stats
@profile_bp.route('/profile/community-stats', methods=['PUT'])
@jwt_required()
def update_community_stats():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"communityActivity": data}},
        upsert=True
    )
    
    return jsonify({"message": "Community stats updated"}), 200


# Award badge
@profile_bp.route('/profile/badges', methods=['POST'])
@jwt_required()
def award_badge():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    badge = {
        "id": str(uuid.uuid4()),
        "name": data.get("name"),
        "icon": data.get("icon"),
        "description": data.get("description"),
        "earned": datetime.utcnow().strftime("%Y-%m-%d")
    }
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$push": {"badges": badge}},
        upsert=True
    )
    
    return jsonify({"message": "Badge awarded", "badge": badge}), 201


# Add certificate with file upload
@profile_bp.route('/profile/certificates', methods=['POST'])
@jwt_required()
def add_certificate():
    current_user_id = get_jwt_identity()
    
    # Handle file upload
    file_url = None
    file_name = None
    
    if 'certificate_file' in request.files:
        file = request.files['certificate_file']
        
        if file and file.filename and allowed_file(file.filename):
            # Create unique filename
            original_filename = secure_filename(file.filename)
            unique_filename = f"{current_user_id}_{uuid.uuid4()}_{original_filename}"
            
            # Ensure upload directory exists
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            
            # Save file
            file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
            file.save(file_path)
            
            # Generate URL for accessing the file
            file_url = f"/api/profile/certificates/file/{unique_filename}"
            file_name = original_filename
            
            print(f"✅ Certificate uploaded: {file_path}")
        else:
            return jsonify({"error": "Invalid file type. Allowed: PDF, PNG, JPG, JPEG"}), 400
    
    # Get form data
    certificate = {
        "id": str(uuid.uuid4()),
        "name": request.form.get("name"),
        "issuer": request.form.get("issuer"),
        "date": request.form.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
        "file_url": file_url,
        "file_name": file_name
    }
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$push": {"certificates": certificate}},
        upsert=True
    )
    
    return jsonify({"message": "Certificate added", "certificate": certificate}), 201


# Serve certificate files
@profile_bp.route('/certificates/file/<filename>', methods=['GET'])
@jwt_required()
def get_certificate_file(filename):
    """Serve uploaded certificate files"""
    try:
        return send_from_directory(UPLOAD_FOLDER, filename)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404


# Delete certificate
@profile_bp.route('/profile/certificates/<cert_id>', methods=['DELETE'])
@jwt_required()
def delete_certificate(cert_id):
    current_user_id = get_jwt_identity()
    db = current_app.db
    
    # Get certificate to find file path
    profile = db.profiles.find_one({"user_id": current_user_id})
    if profile:
        cert = next((c for c in profile.get("certificates", []) if c.get("id") == cert_id), None)
        
        # Delete file if exists
        if cert and cert.get("file_url"):
            filename = cert["file_url"].split("/")[-1]
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"✅ Deleted certificate file: {file_path}")
    
    # Remove from database
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$pull": {"certificates": {"id": cert_id}}}
    )
    
    return jsonify({"message": "Certificate deleted"}), 200


# Add milestone
@profile_bp.route('/profile/milestones', methods=['POST'])
@jwt_required()
def add_milestone():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    milestone = {
        "id": str(uuid.uuid4()),
        "title": data.get("title"),
        "icon": data.get("icon"),
        "date": data.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
    }
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$push": {"milestones": milestone}},
        upsert=True
    )
    
    return jsonify({"message": "Milestone added", "milestone": milestone}), 201


# Update privacy settings
@profile_bp.route('/profile/privacy', methods=['PUT'])
@jwt_required()
def update_privacy():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"privacy": data}},
        upsert=True
    )
    
    return jsonify({"message": "Privacy settings updated"}), 200


# Update notification preferences
@profile_bp.route('/profile/notifications', methods=['PUT'])
@jwt_required()
def update_notifications():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"notifications": data}},
        upsert=True
    )
    
    return jsonify({"message": "Notification preferences updated"}), 200


# Update assignments data
@profile_bp.route('/profile/assignments', methods=['PUT'])
@jwt_required()
def update_assignments():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"assignments": data}},
        upsert=True
    )
    
    return jsonify({"message": "Assignments data updated"}), 200


# Helper function to create default profile
def create_default_profile(user_id, role, db):
    default_profile = {
        "user_id": user_id,
        "phone": "",
        "location": "",
        "profilePicture": None,
        "enrolledCourses": [],
        "assignments": {
            "total": 0,
            "completed": 0,
            "pending": 0,
            "overdue": 0
        },
        "grades": {
            "gpa": 0.0,
            "lastSemesterGPA": 0.0,
            "totalCredits": 0,
            "completedCredits": 0
        },
        "recentMoods": [],
        "communityActivity": {
            "questionsAsked": 0,
            "answersGiven": 0,
            "acceptedAnswers": 0,
            "helpfulVotes": 0,
            "studyGroupsJoined": 0
        },
        "total_points": 0,
        "points_history": [],
        "badges": [],
        "certificates": [],
        "milestones": [],
        "privacy": {
            "showFullName": True,
            "showEmail": False,
            "showPhone": False,
            "anonymousMode": False
        },
        "notifications": {
            "assignmentReminders": True,
            "wellnessNudges": True,
            "peerMessages": True,
            "groupInvitations": True,
            "gradeUpdates": True
        },
        "created_at": datetime.utcnow()
    }
    
    db.profiles.insert_one(default_profile)
    return default_profile