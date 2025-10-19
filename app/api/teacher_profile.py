# backend/app/api/teacher_profile.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime
import uuid

teacher_profile_bp = Blueprint('teacher_profile', __name__)

# Get current teacher's full profile
@teacher_profile_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_teacher_profile():
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    
    if claims.get('role') != 'teacher':
        return jsonify({"error": "Only teachers can access this"}), 403
    
    db = current_app.db
    
    # Get user basic info
    user = db.users.find_one({"user_id": current_user_id}, {"password": 0})
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Get profile data
    profile_data = db.teacher_profiles.find_one({"user_id": current_user_id})
    
    # If no profile exists, create default one
    if not profile_data:
        profile_data = create_default_teacher_profile(current_user_id, db)
    
    if "_id" in user:
        user["_id"] = str(user["_id"])
    if profile_data and "_id" in profile_data:
        profile_data["_id"] = str(profile_data["_id"])
    
    response = {
        "user_id": str(user["user_id"]),
        "role": user["role"],
        "name": user["name"],
        "email": user["email"],
        "empNumber": user.get("empNumber"),
        "designation": user.get("designation"),
        "department": user.get("department"),
        "expertise": user.get("expertise"),
        "experience": user.get("experience"),
        "created_at": user.get("created_at"),
        "profile": profile_data
    }
    
    return jsonify(response), 200


# Get teacher's teaching overview
@teacher_profile_bp.route('/teaching-overview', methods=['GET'])
@jwt_required()
def get_teaching_overview():
    current_user_id = get_jwt_identity()
    db = current_app.db
    
    profile = db.teacher_profiles.find_one({"user_id": current_user_id})
    if not profile:
        return jsonify({
            "coursesTaught": [],
            "assignmentsManaged": {"total": 0, "active": 0, "graded": 0, "totalSubmissions": 0}
        }), 200
    
    return jsonify({
        "coursesTaught": profile.get("coursesTaught", []),
        "assignmentsManaged": profile.get("assignmentsManaged", {})
    }), 200


# Get teacher's engagement stats
@teacher_profile_bp.route('/engagement-stats', methods=['GET'])
@jwt_required()
def get_engagement_stats():
    current_user_id = get_jwt_identity()
    db = current_app.db
    
    profile = db.teacher_profiles.find_one({"user_id": current_user_id})
    if not profile:
        return jsonify({
            "studentInteraction": {
                "queriesResponded": 0,
                "mentorshipSessions": 0,
                "communityContributions": 0,
                "averageResponseTime": "N/A"
            },
            "systemBadges": [],
            "teachingAwards": []
        }), 200
    
    return jsonify({
        "studentInteraction": profile.get("studentInteraction", {}),
        "systemBadges": profile.get("systemBadges", []),
        "teachingAwards": profile.get("teachingAwards", [])
    }), 200


# Get teacher's analytics
@teacher_profile_bp.route('/analytics', methods=['GET'])
@jwt_required()
def get_analytics():
    current_user_id = get_jwt_identity()
    db = current_app.db
    
    profile = db.teacher_profiles.find_one({"user_id": current_user_id})
    if not profile:
        return jsonify({
            "performanceOverview": {},
            "classParticipation": []
        }), 200
    
    return jsonify({
        "performanceOverview": profile.get("performanceOverview", {}),
        "classParticipation": profile.get("classParticipation", [])
    }), 200


# Update teacher's basic information
@teacher_profile_bp.route('/profile/basic', methods=['PUT'])
@jwt_required()
def update_basic_info():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    db = current_app.db
    
    update_fields = {}
    
    if "name" in data:
        update_fields["name"] = data["name"]
    if "phone" in data:
        update_fields["phone"] = data["phone"]
    if "officeLocation" in data:
        update_fields["officeLocation"] = data["officeLocation"]
    
    # Update users collection
    if update_fields:
        db.users.update_one(
            {"user_id": current_user_id},
            {"$set": update_fields}
        )
    
    # Update teacher_profiles collection
    profile_updates = {}
    if "phone" in data:
        profile_updates["phone"] = data["phone"]
    if "officeLocation" in data:
        profile_updates["officeLocation"] = data["officeLocation"]
    
    if profile_updates:
        db.teacher_profiles.update_one(
            {"user_id": current_user_id},
            {"$set": profile_updates},
            upsert=True
        )
    
    return jsonify({"message": "Profile updated successfully"}), 200


# Update courses taught
@teacher_profile_bp.route('/profile/courses', methods=['PUT'])
@jwt_required()
def update_courses():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    courses = data.get("coursesTaught", [])
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"coursesTaught": courses}},
        upsert=True
    )
    
    return jsonify({"message": "Courses updated successfully"}), 200


# Update assignments data
@teacher_profile_bp.route('/profile/assignments', methods=['PUT'])
@jwt_required()
def update_assignments():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"assignmentsManaged": data}},
        upsert=True
    )
    
    return jsonify({"message": "Assignments data updated"}), 200


# Update research publications
@teacher_profile_bp.route('/profile/publications', methods=['PUT'])
@jwt_required()
def update_publications():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    publications = data.get("researchPublications", [])
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"researchPublications": publications}},
        upsert=True
    )
    
    return jsonify({"message": "Publications updated"}), 200


# Add publication
@teacher_profile_bp.route('/profile/publications', methods=['POST'])
@jwt_required()
def add_publication():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    publication = {
        "id": str(uuid.uuid4()),
        "title": data.get("title"),
        "journal": data.get("journal"),
        "year": data.get("year")
    }
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$push": {"researchPublications": publication}},
        upsert=True
    )
    
    return jsonify({"message": "Publication added", "publication": publication}), 201


# Delete publication
@teacher_profile_bp.route('/profile/publications/<pub_id>', methods=['DELETE'])
@jwt_required()
def delete_publication(pub_id):
    current_user_id = get_jwt_identity()
    db = current_app.db
    
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$pull": {"researchPublications": {"id": pub_id}}}
    )
    
    return jsonify({"message": "Publication deleted"}), 200


# Update student interaction stats
@teacher_profile_bp.route('/profile/student-interaction', methods=['PUT'])
@jwt_required()
def update_student_interaction():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"studentInteraction": data}},
        upsert=True
    )
    
    return jsonify({"message": "Student interaction stats updated"}), 200


# Award badge to teacher
@teacher_profile_bp.route('/profile/badges', methods=['POST'])
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
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$push": {"systemBadges": badge}},
        upsert=True
    )
    
    return jsonify({"message": "Badge awarded", "badge": badge}), 201


# Add teaching award
@teacher_profile_bp.route('/profile/awards', methods=['POST'])
@jwt_required()
def add_award():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    award = {
        "id": str(uuid.uuid4()),
        "name": data.get("name"),
        "issuer": data.get("issuer"),
        "year": data.get("year")
    }
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$push": {"teachingAwards": award}},
        upsert=True
    )
    
    return jsonify({"message": "Award added", "award": award}), 201


# Update privacy settings
@teacher_profile_bp.route('/profile/privacy', methods=['PUT'])
@jwt_required()
def update_privacy():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"privacy": data}},
        upsert=True
    )
    
    return jsonify({"message": "Privacy settings updated"}), 200


# Update notification preferences
@teacher_profile_bp.route('/profile/notifications', methods=['PUT'])
@jwt_required()
def update_notifications():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {"notifications": data}},
        upsert=True
    )
    
    return jsonify({"message": "Notification preferences updated"}), 200


# Update performance analytics
@teacher_profile_bp.route('/profile/analytics', methods=['PUT'])
@jwt_required()
def update_analytics():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    db = current_app.db
    db.teacher_profiles.update_one(
        {"user_id": current_user_id},
        {"$set": {
            "performanceOverview": data.get("performanceOverview"),
            "classParticipation": data.get("classParticipation")
        }},
        upsert=True
    )
    
    return jsonify({"message": "Analytics updated"}), 200


# Helper function to create default teacher profile
def create_default_teacher_profile(user_id, db):
    default_profile = {
        "user_id": user_id,
        "phone": "",
        "officeLocation": "",
        "coursesTaught": [],
        "assignmentsManaged": {
            "total": 0,
            "active": 0,
            "graded": 0,
            "totalSubmissions": 0
        },
        "researchPublications": [],
        "studentInteraction": {
            "queriesResponded": 0,
            "mentorshipSessions": 0,
            "communityContributions": 0,
            "averageResponseTime": "N/A"
        },
        "performanceOverview": {
            "averageClassGPA": 0.0,
            "studentSatisfactionRate": 0,
            "courseCompletionRate": 0,
            "participationRate": 0
        },
        "classParticipation": [],
        "systemBadges": [],
        "teachingAwards": [],
        "privacy": {
            "showFullName": True,
            "showEmail": False,
            "showPhone": False,
            "showOfficeLocation": True,
            "allowStudentContact": True
        },
        "notifications": {
            "assignmentSubmissions": True,
            "studentQueries": True,
            "peerActivity": True,
            "systemUpdates": True,
            "gradeReminders": True
        },
        "created_at": datetime.utcnow()
    }
    
    db.teacher_profiles.insert_one(default_profile)
    return default_profile