# backend/app/api/messages.py
from flask import Blueprint, request, jsonify, current_app
from app.extensions import socketio
from flask_socketio import emit, join_room, leave_room
from flask_jwt_extended import decode_token
from bson import ObjectId
from datetime import datetime
import traceback
import json
import uuid

# ✅ MENTAL HEALTH IMPORTS
from app.utils.mental_health_analyzer import analyze_text
from app.utils.wellness_notifications import check_and_send_alerts, send_student_encouragement

messages_bp = Blueprint('messages', __name__)

def safe_content_handler(content):
    """Safely handle content to prevent character splitting"""
    if content is None:
        return ""
    
    if isinstance(content, list):
        return ''.join(str(item) for item in content)
    
    if isinstance(content, str):
        return content
    
    return str(content)

def calculate_unread_count(conversation_id, user_id, db):
    """Calculate unread message count for a user in a conversation"""
    try:
        unread_count = db.messages.count_documents({
            "conversation_id": conversation_id,
            "sender_id": {"$ne": str(user_id)},
            "read_by": {"$ne": str(user_id)}
        })
        return unread_count
    except Exception as e:
        print(f"❌ Error calculating unread count: {e}")
        return 0

# ---------- REST endpoints ----------

@messages_bp.route('/conversations', methods=['GET'])
def get_conversations():
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    db = current_app.db
    convs = list(db.conversations.find({"participants": user_id}).sort("last_updated", -1))

    out = []
    for c in convs:
        other = [p for p in c['participants'] if p != user_id]
        
        # Check if anonymous conversation
        is_anonymous = c.get("isAnonymous", False)
        identity_revealed = c.get("identityRevealed", False)
        
        if is_anonymous and not identity_revealed:
            # Show anonymous IDs instead of real names
            participants_anon = c.get("participantsAnon", {})
            other_names = [participants_anon.get(p, "Anonymous") for p in other]
            other_preview = ", ".join(other_names)
        else:
            # Show real names
            other_user_names = []
            for other_id in other:
                user = db.users.find_one({"user_id": other_id})
                if user:
                    other_user_names.append(user.get('name', 'Unknown'))
            other_preview = ", ".join(other_user_names) if other_user_names else "Unknown"
        
        # Safely handle last_message
        last_message = safe_content_handler(c.get("last_message", ""))
        
        # Calculate unread count
        unread_count = calculate_unread_count(c["_id"], user_id, db)
        
        out.append({
            "conversation_id": str(c["_id"]),
            "participants": [str(p) for p in c["participants"]],
            "other_preview": other_preview,
            "last_message": last_message,
            "last_updated": c.get("last_updated").isoformat() if c.get("last_updated") else None,
            "unread_count": unread_count,
            "is_pinned": c.get("is_pinned", False),
            "isAnonymous": is_anonymous,
            "identityRevealed": identity_revealed
        })
    return jsonify({"conversations": out}), 200

@messages_bp.route('/start', methods=['POST'])
def start_conversation():
    data = request.get_json() or {}
    participants = data.get('participants')
    if not participants or not isinstance(participants, list):
        return jsonify({"error": "participants must be a list"}), 400

    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    if user_id not in participants:
        participants.append(user_id)

    db = current_app.db

    # For 1:1 conversations, try to reuse
    if len(participants) == 2:
        existing = db.conversations.find_one({"participants": {"$all": participants, "$size": 2}})
        if existing:
            return jsonify({"conversation_id": str(existing["_id"])}), 200

    # ✅ USE datetime.utcnow() - SAME AS GROUPS.PY
    now = datetime.utcnow()
    conv = {
        "participants": participants,
        "created_at": now,
        "last_message": "",
        "last_updated": now,
        "is_pinned": False
    }
    res = db.conversations.insert_one(conv)
    return jsonify({"conversation_id": str(res.inserted_id)}), 201

@messages_bp.route('/<conv_id>/messages', methods=['GET'])
def get_messages(conv_id):
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    db = current_app.db
    try:
        conv_obj_id = ObjectId(conv_id)
    except Exception:
        return jsonify({"error": "Bad conversation id"}), 400

    conv = db.conversations.find_one({"_id": conv_obj_id, "participants": user_id})
    if not conv:
        return jsonify({"error": "Conversation not found or access denied"}), 404

    # Check if anonymous
    is_anonymous = conv.get("isAnonymous", False)
    identity_revealed = conv.get("identityRevealed", False)
    participants_anon = conv.get("participantsAnon", {})

    msgs = list(db.messages.find({"conversation_id": conv_obj_id}).sort("timestamp", 1))
    out = []
    
    for m in msgs:
        # Skip system messages content handling
        if m.get("system"):
            out.append({
                "message_id": str(m["_id"]),
                "conversation_id": str(m["conversation_id"]),
                "sender_id": "system",
                "sender_name": "System",
                "content": safe_content_handler(m.get("content", "")),
                "timestamp": m["timestamp"].isoformat() if m.get("timestamp") else datetime.utcnow().isoformat(),
                "read_by": [],
                "is_pinned": False,
                "edited": False,
                "system": True
            })
            continue
        
        # Get sender name
        sender_id = str(m["sender_id"])
        
        if is_anonymous and not identity_revealed:
            # Show anonymous name
            sender_name = participants_anon.get(sender_id, "Anonymous")
        else:
            # Show real name
            sender = db.users.find_one({"user_id": sender_id})
            sender_name = sender.get('name', 'Unknown') if sender else 'Unknown'
        
        # Safely handle content
        raw_content = m.get("content", "")
        content = safe_content_handler(raw_content)
        
        # Skip empty messages
        if len(content.strip()) == 0:
            continue
        
        out.append({
            "message_id": str(m["_id"]),
            "conversation_id": str(m["conversation_id"]),
            "sender_id": sender_id,
            "sender_name": sender_name,
            "content": content,
            "timestamp": m["timestamp"].isoformat() if m.get("timestamp") else datetime.utcnow().isoformat(),
            "read_by": [str(u) for u in m.get("read_by", [])],
            "is_pinned": m.get("is_pinned", False),
            "edited": m.get("edited", False)
        })
    
    return jsonify({"messages": out}), 200

@messages_bp.route('/<conv_id>/send', methods=['POST'])
def send_message_rest(conv_id):
    data = request.get_json() or {}
    raw_content = data.get("content", "")
    
    # Safely handle and validate content
    content = safe_content_handler(raw_content).strip()
    
    if not content:
        return jsonify({"error": "Empty message"}), 400
    
    if len(content) < 1:
        return jsonify({"error": "Message too short"}), 400

    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    db = current_app.db
    try:
        conv_obj_id = ObjectId(conv_id)
    except Exception:
        return jsonify({"error": "Bad conversation id"}), 400

    # ✅ USE datetime.utcnow() - SAME AS GROUPS.PY
    now = datetime.utcnow()

    # Store message
    msg = {
        "conversation_id": conv_obj_id,
        "sender_id": str(user_id),
        "content": str(content),
        "timestamp": now,
        "read_by": [str(user_id)],
        "is_pinned": False,
        "edited": False
    }
    
    res = db.messages.insert_one(msg)

    # Update conversation
    db.conversations.update_one(
        {"_id": conv_obj_id},
        {"$set": {"last_message": str(content), "last_updated": now}}
    )

    # ✅ MENTAL HEALTH ANALYSIS
    try:
        analysis = analyze_text(str(content), context='message')
        
        if analysis['score'] > 0:
            mh_log = {
                'log_id': str(uuid.uuid4()),
                'user_id': str(user_id),
                'timestamp': now,
                'message_id': str(res.inserted_id),
                'score': analysis['score'],
                'level': analysis['level'],
                'keywords_detected': analysis['keywords_detected'],
                'sentiment': analysis['sentiment'],
                'confidence': analysis['confidence'],
                'categories': analysis.get('categories', []),
                'recommendations': analysis.get('recommendations', []),
                'context': 'message',
                'needs_attention': analysis['needs_attention']
            }
            db.mental_health_logs.insert_one(mh_log)
            
            db.user_wellness_profile.update_one(
                {'user_id': str(user_id)},
                {
                    '$set': {
                        'last_check': now,
                        'overall_status': analysis['level']
                    }
                },
                upsert=True
            )
            
            if analysis['needs_attention']:
                check_and_send_alerts(str(user_id), analysis['level'], str(content), db)
            
            send_student_encouragement(str(user_id), analysis['level'], db)
            
    except Exception as e:
        print(f"⚠️ Mental health analysis failed: {e}")
        traceback.print_exc()

    # Get sender name
    sender = db.users.find_one({"user_id": str(user_id)})
    sender_name = sender.get('name', 'Unknown') if sender else 'Unknown'

    msg_out = {
        "message_id": str(res.inserted_id),
        "conversation_id": str(conv_id),
        "sender_id": str(user_id),
        "sender_name": sender_name,
        "content": str(content),
        "timestamp": now.isoformat()
    }

    try:
        socketio.emit('new_message', msg_out, room=str(conv_obj_id))
    except Exception as e:
        print(f"❌ Socket emit error: {e}")

    return jsonify({"message": "sent", "data": msg_out}), 201

@messages_bp.route('/<conv_id>/mark-read', methods=['POST'])
def mark_messages_read(conv_id):
    """Mark all messages in conversation as read"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    db = current_app.db
    try:
        conv_obj_id = ObjectId(conv_id)
    except Exception:
        return jsonify({"error": "Bad conversation id"}), 400

    # Mark all unread messages as read
    result = db.messages.update_many(
        {
            "conversation_id": conv_obj_id,
            "sender_id": {"$ne": str(user_id)},
            "read_by": {"$ne": str(user_id)}
        },
        {
            "$addToSet": {"read_by": str(user_id)}
        }
    )

    # Emit read status to other participants
    socketio.emit('messages_read', {
        'conversation_id': str(conv_obj_id),
        'user_id': str(user_id)
    }, room=str(conv_obj_id))

    return jsonify({
        "success": True,
        "marked_read": result.modified_count
    }), 200

@messages_bp.route('/<conv_id>/pinned', methods=['GET'])
def get_pinned_messages(conv_id):
    """Get pinned messages for a conversation"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    db = current_app.db
    try:
        conv_obj_id = ObjectId(conv_id)
    except Exception:
        return jsonify({"error": "Bad conversation id"}), 400

    conv = db.conversations.find_one({"_id": conv_obj_id, "participants": user_id})
    if not conv:
        return jsonify({"error": "Conversation not found or access denied"}), 404

    pinned_msgs = list(db.messages.find({
        "conversation_id": conv_obj_id,
        "is_pinned": True
    }).sort("timestamp", -1).limit(10))

    out = []
    for m in pinned_msgs:
        sender = db.users.find_one({"user_id": str(m["sender_id"])})
        sender_name = sender.get('name', 'Unknown') if sender else 'Unknown'
        
        content = safe_content_handler(m.get("content", ""))
        
        out.append({
            "message_id": str(m["_id"]),
            "sender_id": str(m["sender_id"]),
            "sender_name": sender_name,
            "content": content,
            "timestamp": m["timestamp"].isoformat() if m.get("timestamp") else None,
            "is_pinned": True
        })
    
    return jsonify({"pinned_messages": out}), 200

@messages_bp.route('/<conv_id>/pin/<message_id>', methods=['POST'])
def toggle_pin_message(conv_id, message_id):
    """Toggle pin status of a message"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    db = current_app.db
    try:
        conv_obj_id = ObjectId(conv_id)
        msg_obj_id = ObjectId(message_id)
    except Exception:
        return jsonify({"error": "Bad id"}), 400

    conv = db.conversations.find_one({"_id": conv_obj_id, "participants": user_id})
    if not conv:
        return jsonify({"error": "Conversation not found or access denied"}), 404

    message = db.messages.find_one({"_id": msg_obj_id, "conversation_id": conv_obj_id})
    if not message:
        return jsonify({"error": "Message not found"}), 404

    current_pin_status = message.get("is_pinned", False)
    new_pin_status = not current_pin_status

    db.messages.update_one(
        {"_id": msg_obj_id},
        {"$set": {"is_pinned": new_pin_status}}
    )

    return jsonify({
        "success": True,
        "message_id": str(msg_obj_id),
        "is_pinned": new_pin_status
    }), 200

@messages_bp.route('/<conv_id>/edit/<message_id>', methods=['PUT'])
def edit_message(conv_id, message_id):
    """Edit a message"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    data = request.get_json() or {}
    new_content = safe_content_handler(data.get("content", "")).strip()

    if not new_content:
        return jsonify({"error": "Content required"}), 400

    db = current_app.db
    try:
        conv_obj_id = ObjectId(conv_id)
        msg_obj_id = ObjectId(message_id)
    except Exception:
        return jsonify({"error": "Bad id"}), 400

    message = db.messages.find_one({
        "_id": msg_obj_id,
        "conversation_id": conv_obj_id,
        "sender_id": str(user_id)
    })
    
    if not message:
        return jsonify({"error": "Message not found or unauthorized"}), 404

    db.messages.update_one(
        {"_id": msg_obj_id},
        {"$set": {
            "content": new_content,
            "edited": True
        }}
    )

    socketio.emit('message_edited', {
        'message_id': str(msg_obj_id),
        'content': new_content
    }, room=str(conv_obj_id))

    return jsonify({
        "success": True,
        "message_id": str(msg_obj_id),
        "content": new_content
    }), 200

@messages_bp.route('/<conv_id>/delete/<message_id>', methods=['DELETE'])
def delete_message(conv_id, message_id):
    """Delete a message"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    db = current_app.db
    try:
        conv_obj_id = ObjectId(conv_id)
        msg_obj_id = ObjectId(message_id)
    except Exception:
        return jsonify({"error": "Bad id"}), 400

    message = db.messages.find_one({
        "_id": msg_obj_id,
        "conversation_id": conv_obj_id,
        "sender_id": str(user_id)
    })
    
    if not message:
        return jsonify({"error": "Message not found or unauthorized"}), 404

    db.messages.delete_one({"_id": msg_obj_id})

    socketio.emit('message_deleted', {
        'message_id': str(msg_obj_id)
    }, room=str(conv_obj_id))

    return jsonify({
        "success": True,
        "message_id": str(msg_obj_id)
    }), 200

@messages_bp.route('/<conv_id>/info', methods=['GET'])
def get_conversation_info(conv_id):
    """Get conversation details with participants"""
    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else None
    if not token:
        return jsonify({"error": "Missing token"}), 401

    try:
        decoded = decode_token(token)
        user_id = decoded.get('sub') or decoded.get('identity')
    except Exception:
        return jsonify({"error": "Invalid token"}), 401

    db = current_app.db
    try:
        conv_obj_id = ObjectId(conv_id)
    except Exception:
        return jsonify({"error": "Bad conversation id"}), 400

    conv = db.conversations.find_one({"_id": conv_obj_id, "participants": user_id})
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    # Handle anonymous conversations
    is_anonymous = conv.get("isAnonymous", False)
    identity_revealed = conv.get("identityRevealed", False)
    
    participants_data = []
    for participant_id in conv.get('participants', []):
        user = db.users.find_one({"user_id": participant_id})
        if user:
            if is_anonymous and not identity_revealed:
                # Show anonymous info
                participants_anon = conv.get("participantsAnon", {})
                anon_id = participants_anon.get(participant_id, user.get("anonId", "Anonymous"))
                
                participants_data.append({
                    'user_id': participant_id,
                    'name': anon_id,
                    'email': '',
                    'role': 'Anonymous',
                    'status': 'online',
                    'isAnonymous': True
                })
            else:
                # Show real info
                participants_data.append({
                    'user_id': participant_id,
                    'name': user.get('name', 'Unknown'),
                    'email': user.get('email', ''),
                    'role': user.get('role', ''),
                    'status': 'online',
                    'isAnonymous': False
                })

    if len(participants_data) > 2:
        conv_name = f"Group Chat ({len(participants_data)} members)"
    else:
        other_users = [p for p in participants_data if p['user_id'] != user_id]
        conv_name = other_users[0]['name'] if other_users else 'Chat'

    return jsonify({
        "conversation": {
            "conversation_id": str(conv["_id"]),
            "name": conv_name,
            "participants": participants_data,
            "created_at": conv.get("created_at").isoformat() if conv.get("created_at") else None,
            "is_group": len(participants_data) > 2,
            "isAnonymous": is_anonymous,
            "identityRevealed": identity_revealed,
            "revealRequests": conv.get("revealRequests", [])
        }
    }), 200

# ---------- Socket.IO handlers ----------

@socketio.on('connect')
def on_connect(auth):
    try:
        token = None
        if isinstance(auth, dict):
            token = auth.get('token')
        if not token:
            token = request.args.get('token')

        if not token:
            print("❌ No token provided for socket connection")
            return False

        decoded = decode_token(token)
        user_id = str(decoded.get('sub') or decoded.get('identity'))
        print(f"✅ Socket connected for user: {user_id}")

        db = current_app.db
        convs = db.conversations.find({"participants": user_id})
        for c in convs:
            join_room(str(c["_id"]))

        emit('connected', {'message': 'connected', 'user_id': user_id})
        return True
    except Exception as e:
        print(f"❌ Socket connection error: {e}")
        traceback.print_exc()
        return False

@socketio.on('join_conversation')
def on_join_conversation(data):
    conv_id = data.get('conversation_id')
    try:
        join_room(str(conv_id))
        emit('joined', {'conversation_id': str(conv_id)})
    except Exception as e:
        print(f"❌ Error joining conversation: {e}")

@socketio.on('leave_conversation')
def on_leave_conversation(data):
    conv_id = data.get('conversation_id')
    try:
        leave_room(str(conv_id))
    except Exception as e:
        print(f"❌ Error leaving conversation: {e}")

@socketio.on('send_message')
def on_send_message(data):
    try:
        token = None
        if isinstance(data, dict) and data.get('token'):
            token = data.get('token')
        if not token:
            token = request.args.get('token')
        if not token:
            emit('error', {'error': 'missing token'})
            return

        decoded = decode_token(token)
        user_id = str(decoded.get('sub') or decoded.get('identity'))

        conv_id = data.get('conversation_id')
        raw_content = data.get('content') or ''
        
        content = safe_content_handler(raw_content).strip()
        
        if not conv_id or not content:
            emit('error', {'error': 'bad payload'})
            return

        db = current_app.db
        conv_obj_id = ObjectId(conv_id)
        
        # ✅ USE datetime.utcnow() - SAME AS GROUPS.PY
        now = datetime.utcnow()

        msg = {
            "conversation_id": conv_obj_id,
            "sender_id": str(user_id),
            "content": str(content),
            "timestamp": now,
            "read_by": [str(user_id)],
            "is_pinned": False,
            "edited": False
        }
        
        res = db.messages.insert_one(msg)

        db.conversations.update_one(
            {"_id": conv_obj_id},
            {"$set": {"last_message": str(content), "last_updated": now}}
        )

        # ✅ MENTAL HEALTH ANALYSIS
        try:
            analysis = analyze_text(str(content), context='message')
            
            if analysis['score'] > 0:
                mh_log = {
                    'log_id': str(uuid.uuid4()),
                    'user_id': str(user_id),
                    'timestamp': now,
                    'message_id': str(res.inserted_id),
                    'score': analysis['score'],
                    'level': analysis['level'],
                    'keywords_detected': analysis['keywords_detected'],
                    'sentiment': analysis['sentiment'],
                    'confidence': analysis['confidence'],
                    'categories': analysis.get('categories', []),
                    'recommendations': analysis.get('recommendations', []),
                    'context': 'message',
                    'needs_attention': analysis['needs_attention']
                }
                db.mental_health_logs.insert_one(mh_log)
                
                db.user_wellness_profile.update_one(
                    {'user_id': str(user_id)},
                    {
                        '$set': {
                            'last_check': now,
                            'overall_status': analysis['level']
                        }
                    },
                    upsert=True
                )
                
                if analysis['needs_attention']:
                    check_and_send_alerts(str(user_id), analysis['level'], str(content), db)
                
                send_student_encouragement(str(user_id), analysis['level'], db)
                
        except Exception as e:
            print(f"⚠️ Mental health analysis failed: {e}")
            traceback.print_exc()

        sender = db.users.find_one({"user_id": str(user_id)})
        sender_name = sender.get('name', 'Unknown') if sender else 'Unknown'

        msg_out = {
            "message_id": str(res.inserted_id),
            "conversation_id": str(conv_id),
            "sender_id": str(user_id),
            "sender_name": sender_name,
            "content": str(content),
            "timestamp": now.isoformat()
        }

        socketio.emit('new_message', msg_out, room=str(conv_obj_id))
        
    except Exception as e:
        print(f"❌ Send message error: {e}")
        traceback.print_exc()
        emit('error', {'error': 'server error'})

@socketio.on('typing')
def on_typing(data):
    """Handle typing indicator"""
    try:
        conv_id = data.get('conversation_id')
        token = data.get('token')
        
        if not token:
            return
            
        decoded = decode_token(token)
        user_id = str(decoded.get('sub') or decoded.get('identity'))
        
        socketio.emit('user_typing', {
            'user_id': user_id,
            'conversation_id': conv_id
        }, room=str(conv_id), skip_sid=request.sid)
        
    except Exception as e:
        print(f"❌ Typing error: {e}")

@socketio.on('stop_typing')
def on_stop_typing(data):
    """Handle stop typing"""
    try:
        conv_id = data.get('conversation_id')
        token = data.get('token')
        
        if not token:
            return
            
        decoded = decode_token(token)
        user_id = str(decoded.get('sub') or decoded.get('identity'))
        
        socketio.emit('user_stop_typing', {
            'user_id': user_id,
            'conversation_id': conv_id
        }, room=str(conv_id), skip_sid=request.sid)
        
    except Exception as e:
        print(f"❌ Stop typing error: {e}")