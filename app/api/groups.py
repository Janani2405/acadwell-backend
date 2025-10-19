from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime
import uuid

groups_bp = Blueprint("groups", __name__)

# ============ UTILITY FUNCTIONS ============

def serialize_group(group):
    """Convert MongoDB group to dict with string id"""
    group["_id"] = str(group["_id"])
    return group


def get_user_anon_id(user_id, db):
    """Safely get anonymous ID for user, create if doesn't exist"""
    user = db.users.find_one({"user_id": user_id})
    
    if not user:
        return "Anonymous"
    
    # If user has anonId, use it
    if user.get("anonId"):
        return user["anonId"]
    
    # If not, generate and save one
    if not user.get("anonId"):
        anon_id = f"Anon{uuid.uuid4().hex[:8]}"
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"anonId": anon_id}}
        )
        return anon_id
    
    return "Anonymous"


# ============ CREATE GROUP ============
@groups_bp.route("/create", methods=["POST"])
@jwt_required()
def create_group():
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        is_private = data.get("isPrivate", False)

        if not name:
            return jsonify({"success": False, "message": "Group name is required"}), 400

        db = current_app.db

        # Verify user exists
        user = db.users.find_one({"user_id": user_id})
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        # Generate anonId if needed
        anon_id = get_user_anon_id(user_id, db)

        new_group = {
            "name": name,
            "description": description,
            "isPrivate": is_private,
            "createdBy": user_id,
            "members": [user_id],
            "memberCount": 1,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }

        result = db.groups.insert_one(new_group)
        new_group["_id"] = str(result.inserted_id)

        # System message: user created group
        db.group_messages.insert_one({
            "groupId": str(result.inserted_id),
            "senderId": None,
            "anonId": "System",
            "message": f"Group created by {anon_id}",
            "timestamp": datetime.utcnow(),
            "system": True
        })

        # System message: user joined
        db.group_messages.insert_one({
            "groupId": str(result.inserted_id),
            "senderId": None,
            "anonId": "System",
            "message": f"{anon_id} joined the group",
            "timestamp": datetime.utcnow(),
            "system": True
        })

        return jsonify({
            "success": True,
            "group": serialize_group(new_group)
        }), 201

    except Exception as e:
        print(f"Error creating group: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ GET MY GROUPS ============
@groups_bp.route("/my", methods=["GET"])
@jwt_required()
def my_groups():
    try:
        user_id = get_jwt_identity()
        db = current_app.db

        groups = list(db.groups.find({"members": user_id}).sort("updatedAt", -1))
        groups = [serialize_group(g) for g in groups]

        return jsonify({"success": True, "groups": groups}), 200

    except Exception as e:
        print(f"Error fetching my groups: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ SUGGESTED GROUPS ============
@groups_bp.route("/suggestions", methods=["GET"])
@jwt_required()
def suggestions():
    try:
        user_id = get_jwt_identity()
        db = current_app.db

        # Public groups user is NOT a member of
        public_groups = list(db.groups.find({
            "isPrivate": False,
            "members": {"$ne": user_id}
        }).limit(20))

        # Combine and serialize
        all_groups = public_groups
        all_groups = [serialize_group(g) for g in all_groups]

        return jsonify({"success": True, "groups": all_groups}), 200

    except Exception as e:
        print(f"Error fetching suggestions: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ JOIN GROUP ============
@groups_bp.route("/<group_id>/join", methods=["POST"])
@jwt_required()
def join_group(group_id):
    try:
        user_id = get_jwt_identity()
        db = current_app.db

        try:
            group_oid = ObjectId(group_id)
        except:
            return jsonify({"success": False, "message": "Invalid group ID"}), 400

        group = db.groups.find_one({"_id": group_oid})
        if not group:
            return jsonify({"success": False, "message": "Group not found"}), 404

        if user_id in group.get("members", []):
            return jsonify({"success": False, "message": "Already a member"}), 400

        # Check if group is private
        if group.get("isPrivate"):
            return jsonify({"success": False, "message": "Cannot join private group"}), 403

        # Add member
        anon_id = get_user_anon_id(user_id, db)

        db.groups.update_one(
            {"_id": group_oid},
            {
                "$addToSet": {"members": user_id},
                "$inc": {"memberCount": 1},
                "$set": {"updatedAt": datetime.utcnow()}
            }
        )

        # System message
        db.group_messages.insert_one({
            "groupId": group_id,
            "senderId": None,
            "anonId": "System",
            "message": f"{anon_id} joined the group",
            "timestamp": datetime.utcnow(),
            "system": True
        })

        return jsonify({"success": True, "message": "Joined group successfully"}), 200

    except Exception as e:
        print(f"Error joining group: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ LEAVE GROUP ============
@groups_bp.route("/<group_id>/leave", methods=["POST"])
@jwt_required()
def leave_group(group_id):
    try:
        user_id = get_jwt_identity()
        db = current_app.db

        try:
            group_oid = ObjectId(group_id)
        except:
            return jsonify({"success": False, "message": "Invalid group ID"}), 400

        group = db.groups.find_one({"_id": group_oid})
        if not group:
            return jsonify({"success": False, "message": "Group not found"}), 404

        if user_id not in group.get("members", []):
            return jsonify({"success": False, "message": "Not a member"}), 400

        anon_id = get_user_anon_id(user_id, db)

        db.groups.update_one(
            {"_id": group_oid},
            {
                "$pull": {"members": user_id},
                "$inc": {"memberCount": -1},
                "$set": {"updatedAt": datetime.utcnow()}
            }
        )

        # System message
        db.group_messages.insert_one({
            "groupId": group_id,
            "senderId": None,
            "anonId": "System",
            "message": f"{anon_id} left the group",
            "timestamp": datetime.utcnow(),
            "system": True
        })

        return jsonify({"success": True, "message": "Left group successfully"}), 200

    except Exception as e:
        print(f"Error leaving group: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ GET GROUP DETAILS ============
@groups_bp.route("/<group_id>", methods=["GET"])
@jwt_required()
def get_group_details(group_id):
    try:
        user_id = get_jwt_identity()
        db = current_app.db

        try:
            group_oid = ObjectId(group_id)
        except:
            return jsonify({"success": False, "message": "Invalid group ID"}), 400

        group = db.groups.find_one({"_id": group_oid})
        if not group:
            return jsonify({"success": False, "message": "Group not found"}), 404

        # Get member anonIds
        members_anon = []
        for uid in group.get("members", []):
            anon = get_user_anon_id(uid, db)
            members_anon.append(anon)

        group_data = serialize_group(group)
        group_data["membersAnonIds"] = members_anon
        group_data["isMember"] = user_id in group.get("members", [])

        return jsonify({"success": True, "group": group_data}), 200

    except Exception as e:
        print(f"Error fetching group details: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ GET GROUP MESSAGES ============
@groups_bp.route("/<group_id>/messages", methods=["GET"])
@jwt_required()
def get_messages(group_id):
    try:
        user_id = get_jwt_identity()
        db = current_app.db

        try:
            group_oid = ObjectId(group_id)
        except:
            return jsonify({"success": False, "message": "Invalid group ID"}), 400

        group = db.groups.find_one({"_id": group_oid})
        if not group:
            return jsonify({"success": False, "message": "Group not found"}), 404

        # Check if user is member (only members can see messages)
        if user_id not in group.get("members", []):
            return jsonify({"success": False, "message": "Access denied"}), 403

        messages = list(db.group_messages.find(
            {"groupId": group_id}
        ).sort("timestamp", 1).limit(100))

        result = []
        for m in messages:
            m["_id"] = str(m["_id"])
            result.append(m)

        return jsonify({"success": True, "messages": result}), 200

    except Exception as e:
        print(f"Error fetching messages: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ SEND MESSAGE ============
@groups_bp.route("/<group_id>/messages", methods=["POST"])
@jwt_required()
def send_message(group_id):
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        message_text = data.get("message", "").strip()

        if not message_text:
            return jsonify({"success": False, "message": "Message cannot be empty"}), 400

        db = current_app.db

        try:
            group_oid = ObjectId(group_id)
        except:
            return jsonify({"success": False, "message": "Invalid group ID"}), 400

        group = db.groups.find_one({"_id": group_oid})
        if not group:
            return jsonify({"success": False, "message": "Group not found"}), 404

        # Check membership
        if user_id not in group.get("members", []):
            return jsonify({"success": False, "message": "Not a member"}), 403

        anon_id = get_user_anon_id(user_id, db)

        message = {
            "groupId": group_id,
            "senderId": user_id,
            "anonId": anon_id,
            "message": message_text,
            "timestamp": datetime.utcnow(),
            "system": False
        }

        result = db.group_messages.insert_one(message)
        message["_id"] = str(result.inserted_id)

        return jsonify({"success": True, "message": message}), 201

    except Exception as e:
        print(f"Error sending message: {e}")
        return jsonify({"success": False, "message": str(e)}), 500