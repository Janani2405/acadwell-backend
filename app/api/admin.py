# backend/app/api/admin.py
"""
Admin API Routes - COMPLETE VERSION
Handles admin authentication and content moderation
"""

from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from functools import wraps
from bson import ObjectId

admin_bp = Blueprint('admin', __name__)


# ==================== ADMIN AUTHENTICATION DECORATOR ====================
def admin_required(fn):
    """Decorator to require admin role for protected routes"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt()
        if claims.get('role') != 'admin':
            return jsonify({
                'error': 'Admin access required',
                'message': 'You do not have permission to access this resource'
            }), 403
        return fn(*args, **kwargs)
    return wrapper


# ==================== ADMIN LOGIN ====================
@admin_bp.route('/login', methods=['POST'])
def admin_login():
    """Admin login endpoint"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        db = current_app.db
        admin = db.admins.find_one({
            '$or': [
                {'username': username},
                {'email': username}
            ]
        })
        
        if not admin:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not check_password_hash(admin['password'], password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not admin.get('is_active', True):
            return jsonify({'error': 'Admin account is disabled'}), 403
        
        admin_id = str(admin['admin_id'])
        access_token = create_access_token(
            identity=admin_id,
            additional_claims={
                'role': 'admin',
                'username': admin['username'],
                'email': admin['email']
            },
            expires_delta=timedelta(hours=12)
        )
        
        db.admins.update_one(
            {'admin_id': admin_id},
            {
                '$set': {
                    'last_login': datetime.utcnow(),
                    'last_login_ip': request.remote_addr
                }
            }
        )
        
        db.admin_activity_logs.insert_one({
            'admin_id': admin_id,
            'action': 'login',
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'timestamp': datetime.utcnow(),
            'status': 'success'
        })
        
        print(f"✅ Admin login successful: {admin['username']} ({admin_id})")
        
        return jsonify({
            'message': 'Login successful',
            'token': access_token,
            'admin': {
                'admin_id': admin_id,
                'username': admin['username'],
                'email': admin['email'],
                'name': admin.get('name', 'Admin'),
                'role': 'admin'
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in admin login: {e}")
        return jsonify({
            'error': 'Login failed',
            'message': 'An unexpected error occurred'
        }), 500


# ==================== GET CURRENT ADMIN INFO ====================
@admin_bp.route('/me', methods=['GET'])
@admin_required
def get_admin_info():
    """Get current admin user information"""
    try:
        admin_id = get_jwt_identity()
        db = current_app.db
        
        admin = db.admins.find_one({'admin_id': admin_id}, {'password': 0})
        
        if not admin:
            return jsonify({'error': 'Admin not found'}), 404
        
        return jsonify({
            'admin_id': str(admin['admin_id']),
            'username': admin['username'],
            'email': admin['email'],
            'name': admin.get('name', 'Admin'),
            'role': 'admin',
            'created_at': admin.get('created_at'),
            'last_login': admin.get('last_login')
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching admin info: {e}")
        return jsonify({'error': 'Failed to fetch admin information'}), 500


# ==================== DASHBOARD OVERVIEW ====================
@admin_bp.route('/dashboard/overview', methods=['GET'])
@admin_required
def get_dashboard_overview():
    """Get overview statistics for admin dashboard"""
    try:
        db = current_app.db
        
        total_users = db.users.count_documents({})
        total_students = db.users.count_documents({'role': 'student'})
        total_teachers = db.users.count_documents({'role': 'teacher'})
        total_others = db.users.count_documents({'role': 'others'})
        
        total_posts = db.community_posts.count_documents({})
        total_messages = db.messages.count_documents({})
        total_questions = db.questions.count_documents({})
        
        total_wellness_logs = db.wellness_logs.count_documents({})
        active_wellness_alerts = db.wellness_alerts.count_documents({'resolved': False})
        critical_alerts = db.wellness_alerts.count_documents({
            'resolved': False,
            'severity': 'critical'
        })
        
        yesterday = datetime.utcnow() - timedelta(days=1)
        new_users_today = db.users.count_documents({
            'created_at': {'$gte': yesterday}
        })
        new_posts_today = db.community_posts.count_documents({
            'created_at': {'$gte': yesterday}
        })
        
        week_ago = datetime.utcnow() - timedelta(days=7)
        active_users = db.users.count_documents({
            'last_login': {'$gte': week_ago}
        })
        
        overview = {
            'users': {
                'total': total_users,
                'students': total_students,
                'teachers': total_teachers,
                'others': total_others,
                'new_today': new_users_today,
                'active_last_7_days': active_users
            },
            'content': {
                'posts': total_posts,
                'messages': total_messages,
                'questions': total_questions,
                'new_posts_today': new_posts_today
            },
            'wellness': {
                'total_logs': total_wellness_logs,
                'active_alerts': active_wellness_alerts,
                'critical_alerts': critical_alerts
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(overview), 200
        
    except Exception as e:
        print(f"❌ Error fetching dashboard overview: {e}")
        return jsonify({'error': 'Failed to fetch overview data'}), 500


# ==================== USER MANAGEMENT ====================
@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_all_users():
    """Get all users with pagination and filtering"""
    try:
        db = current_app.db
        
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        role_filter = request.args.get('role', None)
        search_query = request.args.get('search', None)
        
        query = {}
        
        if role_filter:
            query['role'] = role_filter
        
        if search_query:
            query['$or'] = [
                {'name': {'$regex': search_query, '$options': 'i'}},
                {'email': {'$regex': search_query, '$options': 'i'}},
                {'regNumber': {'$regex': search_query, '$options': 'i'}},
                {'empNumber': {'$regex': search_query, '$options': 'i'}}
            ]
        
        total = db.users.count_documents(query)
        skip = (page - 1) * limit
        users = db.users.find(query, {'password': 0}) \
                        .sort('created_at', -1) \
                        .skip(skip) \
                        .limit(limit)
        
        user_list = []
        for user in users:
            user_data = {
                'user_id': str(user['user_id']),
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'created_at': user.get('created_at'),
                'last_login': user.get('last_login'),
                'is_active': user.get('is_active', True)
            }
            
            if user['role'] == 'student':
                user_data['university'] = user.get('university')
                user_data['field'] = user.get('field')
                user_data['year'] = user.get('year')
            elif user['role'] == 'teacher':
                user_data['department'] = user.get('department')
                user_data['designation'] = user.get('designation')
            
            user_list.append(user_data)
        
        return jsonify({
            'users': user_list,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching users: {e}")
        return jsonify({'error': 'Failed to fetch users'}), 500


# ==================== DELETE USER ====================
@admin_bp.route('/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Soft delete a user account"""
    try:
        admin_id = get_jwt_identity()
        db = current_app.db
        
        user = db.users.find_one({'user_id': user_id})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        db.users.update_one(
            {'user_id': user_id},
            {
                '$set': {
                    'is_active': False,
                    'deleted_at': datetime.utcnow(),
                    'deleted_by': admin_id
                }
            }
        )
        
        db.admin_activity_logs.insert_one({
            'admin_id': admin_id,
            'action': 'delete_user',
            'target_user_id': user_id,
            'target_user_name': user['name'],
            'timestamp': datetime.utcnow(),
            'ip_address': request.remote_addr
        })
        
        print(f"✅ User deleted by admin: {user_id} ({user['name']})")
        
        return jsonify({
            'message': 'User deleted successfully',
            'user_id': user_id
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting user: {e}")
        return jsonify({'error': 'Failed to delete user'}), 500


# ==================== SUSPEND/ACTIVATE USER ====================
@admin_bp.route('/users/<user_id>/status', methods=['PUT'])
@admin_required
def toggle_user_status(user_id):
    """Suspend or activate a user account"""
    try:
        admin_id = get_jwt_identity()
        db = current_app.db
        data = request.get_json()
        
        is_active = data.get('is_active')
        
        if is_active is None:
            return jsonify({'error': 'is_active field is required'}), 400
        
        user = db.users.find_one({'user_id': user_id})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        db.users.update_one(
            {'user_id': user_id},
            {'$set': {'is_active': is_active, 'updated_at': datetime.utcnow()}}
        )
        
        action = 'activate_user' if is_active else 'suspend_user'
        db.admin_activity_logs.insert_one({
            'admin_id': admin_id,
            'action': action,
            'target_user_id': user_id,
            'target_user_name': user['name'],
            'timestamp': datetime.utcnow(),
            'ip_address': request.remote_addr
        })
        
        status = 'activated' if is_active else 'suspended'
        print(f"✅ User {status} by admin: {user_id} ({user['name']})")
        
        return jsonify({
            'message': f'User {status} successfully',
            'user_id': user_id,
            'is_active': is_active
        }), 200
        
    except Exception as e:
        print(f"❌ Error toggling user status: {e}")
        return jsonify({'error': 'Failed to update user status'}), 500


# ==================== GET ACTIVITY LOGS ====================
@admin_bp.route('/activity-logs', methods=['GET'])
@admin_required
def get_activity_logs():
    """Get admin activity logs with pagination"""
    try:
        db = current_app.db
        
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        
        skip = (page - 1) * limit
        
        logs = db.admin_activity_logs.find() \
                                     .sort('timestamp', -1) \
                                     .skip(skip) \
                                     .limit(limit)
        
        total = db.admin_activity_logs.count_documents({})
        
        log_list = []
        for log in logs:
            log_data = {
                'admin_id': str(log['admin_id']),
                'action': log['action'],
                'timestamp': log['timestamp'],
                'ip_address': log.get('ip_address')
            }
            
            if 'target_user_id' in log:
                log_data['target_user_id'] = log['target_user_id']
                log_data['target_user_name'] = log.get('target_user_name')
            
            log_list.append(log_data)
        
        return jsonify({
            'logs': log_list,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching activity logs: {e}")
        return jsonify({'error': 'Failed to fetch activity logs'}), 500


# ==================== CONTENT MODERATION - POSTS ====================

@admin_bp.route('/content/posts', methods=['GET'])
@admin_required
def get_all_posts():
    """Get all community posts with pagination"""
    try:
        db = current_app.db
        
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        search_query = request.args.get('search', None)
        flagged_only = request.args.get('flagged', 'false').lower() == 'true'
        
        query = {}
        
        if flagged_only:
            query['flagged'] = True
        
        if search_query:
            query['$or'] = [
                {'title': {'$regex': search_query, '$options': 'i'}},
                {'question': {'$regex': search_query, '$options': 'i'}},
                {'description': {'$regex': search_query, '$options': 'i'}},
                {'content': {'$regex': search_query, '$options': 'i'}},
                {'author_name': {'$regex': search_query, '$options': 'i'}}
            ]
        
        total = db.community_posts.count_documents(query)
        skip = (page - 1) * limit
        posts = list(db.community_posts.find(query)
                                       .sort('created_at', -1)
                                       .skip(skip)
                                       .limit(limit))
        
        post_list = []
        for post in posts:
            # Count replies for this post
            reply_count = db.community_replies.count_documents({
                'post_id': post.get('post_id'),
                'parent_reply_id': None,
                'is_deleted': {'$ne': True}
            })
            
            post_data = {
                'post_id': str(post.get('post_id', post.get('_id', ''))),
                'title': post.get('title', ''),
                'question': post.get('question', ''),
                'description': post.get('description', ''),
                'content': post.get('content', ''),
                'type': post.get('type', 'question'),
                'author_id': str(post.get('author_id', '')),
                'author_name': post.get('author_name', 'Anonymous'),
                'created_at': post.get('created_at'),
                'updated_at': post.get('updated_at'),
                'answers_count': reply_count,
                'upvotes': post.get('like_count', post.get('upvotes', 0)),
                'views': post.get('view_count', post.get('views', 0)),
                'flagged': post.get('flagged', False),
                'tags': post.get('tags', [])
            }
            post_list.append(post_data)
        
        print(f"✅ Fetched {len(post_list)} posts (page {page}/{(total + limit - 1) // limit})")
        
        return jsonify({
            'posts': post_list,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching posts: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch posts', 'details': str(e)}), 500


@admin_bp.route('/content/posts/<post_id>', methods=['GET'])
@admin_required
def get_post_detail(post_id):
    """Get detailed post with all answers/replies"""
    try:
        db = current_app.db
        
        # Find post
        post = db.community_posts.find_one({'post_id': post_id})
        
        if not post:
            try:
                post = db.community_posts.find_one({'_id': ObjectId(post_id)})
            except:
                pass
        
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        # Get all replies for this post from community_replies
        replies = list(db.community_replies.find({
            'post_id': post_id,
            'parent_reply_id': None,
            'is_deleted': {'$ne': True}
        }).sort('created_at', 1))
        
        # Format replies as answers
        formatted_answers = []
        for reply in replies:
            formatted_answer = {
                'answer_id': str(reply.get('reply_id', reply.get('_id', ''))),
                'content': reply.get('content', ''),
                'author_id': str(reply.get('author_id', '')),
                'author_name': reply.get('author_name', 'Anonymous'),
                'created_at': reply.get('created_at'),
                'upvotes': reply.get('like_count', 0),
                'is_accepted': reply.get('is_accepted', False)
            }
            formatted_answers.append(formatted_answer)
        
        # Format post
        post_data = {
            'post_id': str(post.get('post_id', post.get('_id', ''))),
            'title': post.get('title', ''),
            'question': post.get('question', ''),
            'description': post.get('description', ''),
            'content': post.get('content', ''),
            'type': post.get('type', 'question'),
            'author_id': str(post.get('author_id', '')),
            'author_name': post.get('author_name', 'Anonymous'),
            'created_at': post.get('created_at'),
            'updated_at': post.get('updated_at'),
            'answers': formatted_answers,
            'upvotes': post.get('like_count', post.get('upvotes', 0)),
            'views': post.get('view_count', post.get('views', 0)),
            'flagged': post.get('flagged', False),
            'tags': post.get('tags', [])
        }
        
        print(f"✅ Fetched post detail: {post_id} with {len(formatted_answers)} answers")
        
        return jsonify(post_data), 200
        
    except Exception as e:
        print(f"❌ Error fetching post detail: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch post details', 'details': str(e)}), 500


@admin_bp.route('/content/posts/<post_id>', methods=['DELETE'])
@admin_required
def delete_post(post_id):
    """Delete a post"""
    try:
        admin_id = get_jwt_identity()
        db = current_app.db
        
        post = db.community_posts.find_one({'post_id': post_id})
        
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        # Soft delete
        db.community_posts.update_one(
            {'post_id': post_id},
            {
                '$set': {
                    'is_deleted': True,
                    'deleted_at': datetime.utcnow(),
                    'deleted_by': admin_id
                }
            }
        )
        
        db.admin_activity_logs.insert_one({
            'admin_id': admin_id,
            'action': 'delete_post',
            'target_post_id': post_id,
            'target_post_title': post.get('title') or post.get('question', 'Untitled'),
            'target_author': post.get('author_name', 'Unknown'),
            'timestamp': datetime.utcnow(),
            'ip_address': request.remote_addr
        })
        
        print(f"✅ Post deleted by admin: {post_id}")
        
        return jsonify({
            'message': 'Post deleted successfully',
            'post_id': post_id
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting post: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to delete post', 'details': str(e)}), 500


@admin_bp.route('/content/posts/<post_id>/answers/<answer_id>', methods=['DELETE'])
@admin_required
def delete_answer(post_id, answer_id):
    """Delete a specific answer (reply)"""
    try:
        admin_id = get_jwt_identity()
        db = current_app.db
        
        # Find reply
        reply = db.community_replies.find_one({
            'reply_id': answer_id,
            'post_id': post_id
        })
        
        if not reply:
            return jsonify({'error': 'Answer not found'}), 404
        
        # Soft delete reply
        db.community_replies.update_one(
            {'reply_id': answer_id},
            {
                '$set': {
                    'is_deleted': True,
                    'deleted_at': datetime.utcnow(),
                    'deleted_by': admin_id
                }
            }
        )
        
        # Decrement post reply count
        db.community_posts.update_one(
            {'post_id': post_id},
            {'$inc': {'reply_count': -1}}
        )
        
        db.admin_activity_logs.insert_one({
            'admin_id': admin_id,
            'action': 'delete_answer',
            'target_post_id': post_id,
            'target_answer_id': answer_id,
            'target_author': reply.get('author_name', 'Unknown'),
            'timestamp': datetime.utcnow(),
            'ip_address': request.remote_addr
        })
        
        print(f"✅ Answer deleted by admin: {answer_id} from post {post_id}")
        
        return jsonify({
            'message': 'Answer deleted successfully',
            'answer_id': answer_id
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting answer: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to delete answer', 'details': str(e)}), 500


@admin_bp.route('/content/posts/<post_id>', methods=['PUT'])
@admin_required
def update_post(post_id):
    """Update/edit a post"""
    try:
        admin_id = get_jwt_identity()
        db = current_app.db
        data = request.get_json()
        
        post = db.community_posts.find_one({'post_id': post_id})
        
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        update_data = {}
        
        if 'title' in data:
            update_data['title'] = data['title']
        if 'question' in data:
            update_data['question'] = data['question']
        if 'description' in data:
            update_data['description'] = data['description']
        if 'content' in data:
            update_data['content'] = data['content']
        if 'flagged' in data:
            update_data['flagged'] = data['flagged']
        
        if not update_data:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        update_data['updated_at'] = datetime.utcnow()
        
        db.community_posts.update_one(
            {'post_id': post_id},
            {'$set': update_data}
        )
        
        db.admin_activity_logs.insert_one({
            'admin_id': admin_id,
            'action': 'update_post',
            'target_post_id': post_id,
            'changes': list(update_data.keys()),
            'timestamp': datetime.utcnow(),
            'ip_address': request.remote_addr
        })
        
        print(f"✅ Post updated by admin: {post_id}")
        
        return jsonify({
            'message': 'Post updated successfully',
            'post_id': post_id
        }), 200
        
    except Exception as e:
        print(f"❌ Error updating post: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to update post', 'details': str(e)}), 500


@admin_bp.route('/content/stats', methods=['GET'])
@admin_required
def get_content_stats():
    """Get content statistics"""
    try:
        db = current_app.db
        
        total_posts = db.community_posts.count_documents({})
        flagged_posts = db.community_posts.count_documents({'flagged': True})
        
        # Count total replies (answers)
        total_answers = db.community_replies.count_documents({
            'is_deleted': {'$ne': True}
        })
        
        # Recent posts (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_posts = db.community_posts.count_documents({
            'created_at': {'$gte': yesterday}
        })
        
        stats = {
            'total_posts': total_posts,
            'total_answers': total_answers,
            'flagged_posts': flagged_posts,
            'recent_posts_24h': recent_posts
        }
        
        print(f"✅ Stats: {stats}")
        
        return jsonify(stats), 200
        
    except Exception as e:
        print(f"❌ Error fetching content stats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch stats', 'details': str(e)}), 500