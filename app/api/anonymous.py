# backend/app/api/anonymous.py
"""
Anonymous Messaging API
Handles anonymous user discovery, chat initiation, and identity management
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson import ObjectId
from datetime import datetime
import uuid
import traceback

anonymous_bp = Blueprint('anonymous', __name__)


# ============ UTILITY FUNCTIONS ============

def ensure_anon_id(user_id, db):
    """Ensure user has an anonymous ID, create if doesn't exist"""
    user = db.users.find_one({"user_id": user_id})
    
    if not user:
        return None
    
    # If user already has anonId, return it
    if user.get("anonId"):
        return user["anonId"]
    
    # Generate new anonId
    anon_id = f"Anon{uuid.uuid4().hex[:8]}"
    
    # ✅ USE datetime.utcnow() - SAME AS groups.py
    db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "anonId": anon_id,
                "anonymousProfile": {
                    "tags": [],
                    "role": "both",
                    "status": "available",
                    "lastActive": datetime.utcnow(),
                    "bio": "",
                    "helpCount": 0,
                    "rating": 0,
                    "reviewCount": 0
                }
            }
        }
    )
    
    return anon_id


def serialize_anonymous_user(user, hide_sensitive=True):
    """Convert user to anonymous profile dict"""
    profile = user.get("anonymousProfile", {})
    
    # ✅ Handle lastActive properly
    last_active = profile.get("lastActive")
    if last_active is None:
        last_active = datetime.utcnow()
    
    # Convert to ISO string
    if isinstance(last_active, datetime):
        last_active_iso = last_active.isoformat()
    else:
        last_active_iso = datetime.utcnow().isoformat()
    
    result = {
        "anonId": user.get("anonId", "Unknown"),
        "tags": profile.get("tags", []),
        "role": profile.get("role", "both"),
        "status": profile.get("status", "available"),
        "lastActive": last_active_iso,
        "bio": profile.get("bio", ""),
        "rating": profile.get("rating", 0),
        "reviewCount": profile.get("reviewCount", 0)
    }
    
    if not hide_sensitive:
        result["user_id"] = user.get("user_id")
    
    return result


# ============ INITIALIZE ANONYMOUS PROFILE ============

@anonymous_bp.route('/init', methods=['POST'])
@jwt_required()
def initialize_anonymous_profile():
    """Initialize or update user's anonymous profile"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        data = request.get_json() or {}
        
        # Ensure user has anonId
        anon_id = ensure_anon_id(user_id, db)
        
        if not anon_id:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        # Update anonymous profile
        update_data = {}
        
        if "tags" in data:
            update_data["anonymousProfile.tags"] = data["tags"]
        
        if "role" in data and data["role"] in ["helper", "seeker", "both"]:
            update_data["anonymousProfile.role"] = data["role"]
        
        if "bio" in data:
            update_data["anonymousProfile.bio"] = data["bio"][:200]
        
        if "status" in data and data["status"] in ["available", "busy", "invisible"]:
            update_data["anonymousProfile.status"] = data["status"]
        
        if update_data:
            db.users.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
        
        # Get updated user
        user = db.users.find_one({"user_id": user_id})
        
        return jsonify({
            "success": True,
            "profile": serialize_anonymous_user(user, hide_sensitive=False)
        }), 200
        
    except Exception as e:
        print(f"❌ Error initializing anonymous profile: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ GET MY ANONYMOUS PROFILE ============

@anonymous_bp.route('/profile/me', methods=['GET'])
@jwt_required()
def get_my_anonymous_profile():
    """Get current user's anonymous profile"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        user = db.users.find_one({"user_id": user_id})
        
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        # Ensure user has anonId
        if not user.get("anonId"):
            anon_id = ensure_anon_id(user_id, db)
            user = db.users.find_one({"user_id": user_id})
        
        return jsonify({
            "success": True,
            "profile": serialize_anonymous_user(user, hide_sensitive=False)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching anonymous profile: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ DISCOVER ANONYMOUS PEERS ============

@anonymous_bp.route('/discover', methods=['GET'])
@jwt_required()
def discover_anonymous_peers():
    """Get list of available anonymous users for chat"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        # Get filter parameters
        subject = request.args.get('subject')
        role = request.args.get('role')
        tags = request.args.getlist('tags')
        
        # Build query
        query = {
            "user_id": {"$ne": user_id},
            "anonymousProfile.status": {"$in": ["available", "busy"]}
        }
        
        # Apply filters
        if role and role in ["helper", "seeker", "both"]:
            query["anonymousProfile.role"] = {"$in": [role, "both"]}
        
        if tags:
            query["anonymousProfile.tags"] = {"$in": tags}
        
        if subject:
            query["anonymousProfile.tags"] = subject
        
        # Fetch users
        users = list(db.users.find(query).limit(50))
        
        # Serialize
        result = [serialize_anonymous_user(u) for u in users]
        
        # Sort by status and lastActive
        result.sort(key=lambda x: (
            0 if x["status"] == "available" else 1,
            x["lastActive"]
        ), reverse=True)
        
        return jsonify({
            "success": True,
            "users": result,
            "count": len(result)
        }), 200
        
    except Exception as e:
        print(f"❌ Error discovering anonymous peers: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ START ANONYMOUS CONVERSATION ============

@anonymous_bp.route('/start', methods=['POST'])
@jwt_required()
def start_anonymous_conversation():
    """Start an anonymous conversation with another user"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        data = request.get_json() or {}
        target_anon_id = data.get('anonId')
        
        if not target_anon_id:
            return jsonify({"success": False, "message": "Target anonId required"}), 400
        
        # Find target user by anonId
        target_user = db.users.find_one({"anonId": target_anon_id})
        
        if not target_user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        target_user_id = target_user["user_id"]
        
        # Don't allow self-chat
        if target_user_id == user_id:
            return jsonify({"success": False, "message": "Cannot chat with yourself"}), 400
        
        # Check if anonymous conversation already exists
        existing_conv = db.conversations.find_one({
            "participants": {"$all": [user_id, target_user_id], "$size": 2},
            "isAnonymous": True
        })
        
        if existing_conv:
            return jsonify({
                "success": True,
                "conversation_id": str(existing_conv["_id"]),
                "message": "Conversation already exists"
            }), 200
        
        # Ensure both users have anonIds
        my_anon_id = ensure_anon_id(user_id, db)
        their_anon_id = ensure_anon_id(target_user_id, db)
        
        # ✅ USE datetime.utcnow() - SAME AS groups.py
        now = datetime.utcnow()
        conv = {
            "participants": [user_id, target_user_id],
            "participantsAnon": {
                user_id: my_anon_id,
                target_user_id: their_anon_id
            },
            "isAnonymous": True,
            "identityRevealed": False,
            "revealRequests": [],
            "created_at": now,
            "last_message": "",
            "last_updated": now,
            "is_pinned": False
        }
        
        result = db.conversations.insert_one(conv)
        
        return jsonify({
            "success": True,
            "conversation_id": str(result.inserted_id),
            "message": "Anonymous conversation started"
        }), 201
        
    except Exception as e:
        print(f"❌ Error starting anonymous conversation: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ REQUEST IDENTITY REVEAL ============

@anonymous_bp.route('/reveal/request', methods=['POST'])
@jwt_required()
def request_identity_reveal():
    """Request to reveal identities in an anonymous conversation"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        data = request.get_json() or {}
        conv_id = data.get('conversation_id')
        
        if not conv_id:
            return jsonify({"success": False, "message": "conversation_id required"}), 400
        
        try:
            conv_obj_id = ObjectId(conv_id)
        except:
            return jsonify({"success": False, "message": "Invalid conversation_id"}), 400
        
        conv = db.conversations.find_one({
            "_id": conv_obj_id,
            "participants": user_id,
            "isAnonymous": True
        })
        
        if not conv:
            return jsonify({"success": False, "message": "Conversation not found"}), 404
        
        # Check if already revealed
        if conv.get("identityRevealed"):
            return jsonify({
                "success": False,
                "message": "Identities already revealed"
            }), 400
        
        # Check if user already requested
        reveal_requests = conv.get("revealRequests", [])
        
        if user_id in reveal_requests:
            return jsonify({
                "success": False,
                "message": "You already requested reveal"
            }), 400
        
        # Add user to reveal requests
        reveal_requests.append(user_id)
        
        # ✅ USE datetime.utcnow()
        now = datetime.utcnow()
        
        # If both users requested, reveal identities
        if len(reveal_requests) >= 2:
            db.conversations.update_one(
                {"_id": conv_obj_id},
                {
                    "$set": {
                        "identityRevealed": True,
                        "revealedAt": now
                    }
                }
            )
            
            # Send system message
            db.messages.insert_one({
                "conversation_id": conv_obj_id,
                "sender_id": "system",
                "content": "🎭 Both users agreed to reveal identities. You can now see each other's real names.",
                "timestamp": now,
                "read_by": [],
                "is_pinned": False,
                "edited": False,
                "system": True
            })
            
            return jsonify({
                "success": True,
                "message": "Identities revealed!",
                "revealed": True
            }), 200
        else:
            # Update with pending request
            db.conversations.update_one(
                {"_id": conv_obj_id},
                {"$set": {"revealRequests": reveal_requests}}
            )
            
            # Send system message
            db.messages.insert_one({
                "conversation_id": conv_obj_id,
                "sender_id": "system",
                "content": "🎭 One user requested to reveal identities. Both must agree to proceed.",
                "timestamp": now,
                "read_by": [],
                "is_pinned": False,
                "edited": False,
                "system": True
            })
            
            return jsonify({
                "success": True,
                "message": "Reveal request sent. Waiting for other user's approval.",
                "revealed": False,
                "pending": True
            }), 200
        
    except Exception as e:
        print(f"❌ Error requesting identity reveal: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ RATE ANONYMOUS USER ============

@anonymous_bp.route('/rate', methods=['POST'])
@jwt_required()
def rate_anonymous_user():
    """Rate an anonymous user after conversation"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        data = request.get_json() or {}
        conv_id = data.get('conversation_id')
        rating = data.get('rating')
        feedback = data.get('feedback', '').strip()
        
        if not conv_id or not rating:
            return jsonify({"success": False, "message": "conversation_id and rating required"}), 400
        
        if rating < 1 or rating > 5:
            return jsonify({"success": False, "message": "Rating must be 1-5"}), 400
        
        try:
            conv_obj_id = ObjectId(conv_id)
        except:
            return jsonify({"success": False, "message": "Invalid conversation_id"}), 400
        
        conv = db.conversations.find_one({
            "_id": conv_obj_id,
            "participants": user_id,
            "isAnonymous": True
        })
        
        if not conv:
            return jsonify({"success": False, "message": "Conversation not found"}), 404
        
        # Get other participant
        other_user_id = [p for p in conv["participants"] if p != user_id][0]
        
        # Check if already rated
        existing_rating = db.anonymous_ratings.find_one({
            "conversation_id": str(conv_id),
            "rater_id": user_id
        })
        
        if existing_rating:
            return jsonify({"success": False, "message": "Already rated this conversation"}), 400
        
        # ✅ USE datetime.utcnow()
        rating_doc = {
            "conversation_id": str(conv_id),
            "rater_id": user_id,
            "rated_user_id": other_user_id,
            "rating": rating,
            "feedback": feedback[:500],
            "created_at": datetime.utcnow()
        }
        
        db.anonymous_ratings.insert_one(rating_doc)
        
        # Update rated user's average rating
        all_ratings = list(db.anonymous_ratings.find({"rated_user_id": other_user_id}))
        
        if all_ratings:
            avg_rating = sum(r["rating"] for r in all_ratings) / len(all_ratings)
            
            db.users.update_one(
                {"user_id": other_user_id},
                {
                    "$set": {
                        "anonymousProfile.rating": round(avg_rating, 2),
                        "anonymousProfile.reviewCount": len(all_ratings)
                    },
                    "$inc": {"anonymousProfile.helpCount": 1}
                }
            )
        
        return jsonify({
            "success": True,
            "message": "Rating submitted successfully"
        }), 200
        
    except Exception as e:
        print(f"❌ Error rating user: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ REPORT ANONYMOUS USER ============

@anonymous_bp.route('/report', methods=['POST'])
@jwt_required()
def report_anonymous_user():
    """Report an anonymous user for inappropriate behavior"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        data = request.get_json() or {}
        conv_id = data.get('conversation_id')
        reason = data.get('reason', '').strip()
        details = data.get('details', '').strip()
        
        if not conv_id or not reason:
            return jsonify({"success": False, "message": "conversation_id and reason required"}), 400
        
        try:
            conv_obj_id = ObjectId(conv_id)
        except:
            return jsonify({"success": False, "message": "Invalid conversation_id"}), 400
        
        conv = db.conversations.find_one({
            "_id": conv_obj_id,
            "participants": user_id,
            "isAnonymous": True
        })
        
        if not conv:
            return jsonify({"success": False, "message": "Conversation not found"}), 404
        
        # Get reported user
        reported_user_id = [p for p in conv["participants"] if p != user_id][0]
        
        # ✅ USE datetime.utcnow()
        report_doc = {
            "report_id": str(uuid.uuid4()),
            "conversation_id": str(conv_id),
            "reporter_id": user_id,
            "reported_user_id": reported_user_id,
            "reason": reason,
            "details": details[:1000],
            "status": "pending",
            "created_at": datetime.utcnow(),
            "reviewed_at": None,
            "reviewed_by": None
        }
        
        db.anonymous_reports.insert_one(report_doc)
        
        # Auto-block if multiple reports
        report_count = db.anonymous_reports.count_documents({
            "reported_user_id": reported_user_id,
            "status": "pending"
        })
        
        if report_count >= 3:
            db.users.update_one(
                {"user_id": reported_user_id},
                {"$set": {"anonymousProfile.status": "invisible"}}
            )
        
        return jsonify({
            "success": True,
            "message": "Report submitted. We'll review it shortly.",
            "report_id": report_doc["report_id"]
        }), 200
        
    except Exception as e:
        print(f"❌ Error reporting user: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ BLOCK ANONYMOUS USER ============

@anonymous_bp.route('/block', methods=['POST'])
@jwt_required()
def block_anonymous_user():
    """Block an anonymous user from contacting you"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        data = request.get_json() or {}
        anon_id = data.get('anonId')
        
        if not anon_id:
            return jsonify({"success": False, "message": "anonId required"}), 400
        
        # Find user to block
        blocked_user = db.users.find_one({"anonId": anon_id})
        
        if not blocked_user:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        blocked_user_id = blocked_user["user_id"]
        
        # Add to blocked list
        db.users.update_one(
            {"user_id": user_id},
            {"$addToSet": {"blockedUsers": blocked_user_id}}
        )
        
        return jsonify({
            "success": True,
            "message": "User blocked successfully"
        }), 200
        
    except Exception as e:
        print(f"❌ Error blocking user: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# ============ UPDATE STATUS ============

@anonymous_bp.route('/status', methods=['PUT'])
@jwt_required()
def update_anonymous_status():
    """Update anonymous availability status"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        data = request.get_json() or {}
        status = data.get('status')
        
        if status not in ["available", "busy", "invisible"]:
            return jsonify({"success": False, "message": "Invalid status"}), 400
        
        # ✅ USE datetime.utcnow()
        db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "anonymousProfile.status": status,
                    "anonymousProfile.lastActive": datetime.utcnow()
                }
            }
        )
        
        return jsonify({
            "success": True,
            "message": "Status updated",
            "status": status
        }), 200
        
    except Exception as e:
        print(f"❌ Error updating status: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

        # Add these new endpoints to backend/app/api/anonymous.py

# ============ DELETE ANONYMOUS CONVERSATION ============

@anonymous_bp.route('/conversation/<conv_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_anonymous_conversation(conv_id):
    """Delete an entire anonymous conversation and all its messages"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        try:
            conv_obj_id = ObjectId(conv_id)
        except:
            return jsonify({"success": False, "message": "Invalid conversation_id"}), 400
        
        # Verify user is participant
        conv = db.conversations.find_one({
            "_id": conv_obj_id,
            "participants": user_id,
            "isAnonymous": True
        })
        
        if not conv:
            return jsonify({"success": False, "message": "Conversation not found"}), 404
        
        # Delete all messages in this conversation
        messages_deleted = db.messages.delete_many({"conversation_id": conv_obj_id})
        
        # Delete the conversation itself
        db.conversations.delete_one({"_id": conv_obj_id})
        
        # Delete related ratings
        db.anonymous_ratings.delete_many({"conversation_id": str(conv_id)})
        
        # Note: We keep reports for moderation purposes
        
        return jsonify({
            "success": True,
            "message": "Conversation deleted successfully",
            "messages_deleted": messages_deleted.deleted_count
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting conversation: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ RESET CONVERSATION TO ANONYMOUS ============

@anonymous_bp.route('/conversation/<conv_id>/reset', methods=['POST'])
@jwt_required()
def reset_conversation_to_anonymous(conv_id):
    """Reset a revealed conversation back to anonymous mode"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        try:
            conv_obj_id = ObjectId(conv_id)
        except:
            return jsonify({"success": False, "message": "Invalid conversation_id"}), 400
        
        # Verify user is participant
        conv = db.conversations.find_one({
            "_id": conv_obj_id,
            "participants": user_id,
            "isAnonymous": True
        })
        
        if not conv:
            return jsonify({"success": False, "message": "Conversation not found"}), 404
        
        # Check if identities were revealed
        if not conv.get("identityRevealed"):
            return jsonify({
                "success": False,
                "message": "Identities are not revealed yet"
            }), 400
        
        # Reset to anonymous
        now = datetime.utcnow()
        db.conversations.update_one(
            {"_id": conv_obj_id},
            {
                "$set": {
                    "identityRevealed": False,
                    "revealRequests": [],
                    "resetAt": now
                },
                "$unset": {"revealedAt": ""}
            }
        )
        
        # Add system message
        db.messages.insert_one({
            "conversation_id": conv_obj_id,
            "sender_id": "system",
            "content": "🎭 Conversation has been reset to anonymous mode. Identities are now hidden again.",
            "timestamp": now,
            "read_by": [],
            "is_pinned": False,
            "edited": False,
            "system": True
        })
        
        return jsonify({
            "success": True,
            "message": "Conversation reset to anonymous successfully"
        }), 200
        
    except Exception as e:
        print(f"❌ Error resetting conversation: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ GET ALL REPORTS (ADMIN) ============

@anonymous_bp.route('/admin/reports', methods=['GET'])
@jwt_required()
def get_all_reports():
    """Get all anonymous reports for admin review"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        # Check if user is admin (add your admin check here)
        user = db.users.find_one({"user_id": user_id})
        if not user or user.get('role') != 'admin':
            return jsonify({"success": False, "message": "Admin access required"}), 403
        
        # Get filter parameters
        status = request.args.get('status', 'pending')  # pending, reviewed, resolved
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        # Fetch reports
        reports = list(db.anonymous_reports.find(query).sort("created_at", -1).limit(100))
        
        # Enrich with user info
        result = []
        for report in reports:
            # Get reporter info
            reporter = db.users.find_one({"user_id": report["reporter_id"]})
            reported = db.users.find_one({"user_id": report["reported_user_id"]})
            
            result.append({
                "report_id": report["report_id"],
                "conversation_id": report["conversation_id"],
                "reporter": {
                    "user_id": report["reporter_id"],
                    "name": reporter.get("name", "Unknown") if reporter else "Unknown",
                    "anonId": reporter.get("anonId", "Unknown") if reporter else "Unknown"
                },
                "reported_user": {
                    "user_id": report["reported_user_id"],
                    "name": reported.get("name", "Unknown") if reported else "Unknown",
                    "anonId": reported.get("anonId", "Unknown") if reported else "Unknown"
                },
                "reason": report["reason"],
                "details": report["details"],
                "status": report["status"],
                "created_at": report["created_at"].isoformat(),
                "reviewed_at": report.get("reviewed_at").isoformat() if report.get("reviewed_at") else None,
                "reviewed_by": report.get("reviewed_by")
            })
        
        return jsonify({
            "success": True,
            "reports": result,
            "count": len(result)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching reports: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============ UPDATE REPORT STATUS (ADMIN) ============

@anonymous_bp.route('/admin/reports/<report_id>', methods=['PUT'])
@jwt_required()
def update_report_status(report_id):
    """Update report status (admin only)"""
    try:
        user_id = get_jwt_identity()
        db = current_app.db
        
        # Check if user is admin
        user = db.users.find_one({"user_id": user_id})
        if not user or user.get('role') != 'admin':
            return jsonify({"success": False, "message": "Admin access required"}), 403
        
        data = request.get_json() or {}
        new_status = data.get('status')
        
        if new_status not in ['reviewed', 'resolved', 'dismissed']:
            return jsonify({"success": False, "message": "Invalid status"}), 400
        
        # Update report
        result = db.anonymous_reports.update_one(
            {"report_id": report_id},
            {
                "$set": {
                    "status": new_status,
                    "reviewed_at": datetime.utcnow(),
                    "reviewed_by": user_id
                }
            }
        )
        
        if result.modified_count == 0:
            return jsonify({"success": False, "message": "Report not found"}), 404
        
        return jsonify({
            "success": True,
            "message": f"Report marked as {new_status}"
        }), 200
        
    except Exception as e:
        print(f"❌ Error updating report: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500