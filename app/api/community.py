# backend/app/api/community.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import uuid
import re
from app.utils.mental_health_analyzer import analyze_text
from app.utils.wellness_notifications import check_and_send_alerts, send_student_encouragement
from app.utils.notification_manager import create_notification_manager
community_bp = Blueprint('community', __name__)

# Badge definitions
BADGE_DEFINITIONS = {
    'helpful_citizen': {
        'name': 'Helpful Citizen',
        'icon': '🤝',
        'description': 'Posted 5 helpful replies',
        'requirement': {'type': 'accepted_answers', 'value': 5}
    },
    'expert': {
        'name': 'Expert',
        'icon': '⭐',
        'description': 'Posted 10 helpful replies',
        'requirement': {'type': 'accepted_answers', 'value': 10}
    },
    'master': {
        'name': 'Master',
        'icon': '👑',
        'description': 'Posted 25 helpful replies',
        'requirement': {'type': 'accepted_answers', 'value': 25}
    },
    'question_asker': {
        'name': 'Question Asker',
        'icon': '❓',
        'description': 'Asked 10 questions',
        'requirement': {'type': 'questions_asked', 'value': 10}
    },
    'community_leader': {
        'name': 'Community Leader',
        'icon': '🏆',
        'description': 'Earned 100+ points',
        'requirement': {'type': 'total_points', 'value': 100}
    }
}

# Content moderation keywords
INAPPROPRIATE_KEYWORDS = [
    'spam', 'scam', 'abuse', 'harassment', 'hate', 'violence',
    'explicit', 'nsfw', 'profanity', 'offensive'
]


def get_time_ago(timestamp):
    """Convert timestamp to 'time ago' format"""
    if not timestamp:
        return "Unknown"
    
    now = datetime.utcnow()
    diff = now - timestamp
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago" if minutes > 1 else "1m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago" if hours > 1 else "1h ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days}d ago" if days > 1 else "1d ago"
    else:
        weeks = int(seconds / 604800)
        return f"{weeks}w ago" if weeks > 1 else "1w ago"


def award_points(user_id, points, reason, db):
    """Award points to a user and check for badge eligibility"""
    try:
        profile = db.profiles.find_one({"user_id": user_id})
        current_points = profile.get("total_points", 0) if profile else 0
        new_total = current_points + points
        
        db.profiles.update_one(
            {"user_id": user_id},
            {
                "$set": {"total_points": new_total},
                "$push": {
                    "points_history": {
                        "points": points,
                        "reason": reason,
                        "timestamp": datetime.utcnow()
                    }
                }
            },
            upsert=True
        )
        
        print(f"✅ Awarded {points} points to {user_id} ({reason}). Total: {new_total}")
        check_and_award_badges(user_id, db)
        return True
    except Exception as e:
        print(f"❌ Error awarding points: {e}")
        return False


def increment_community_stat(user_id, stat_type, db):
    """Increment community activity statistics"""
    try:
        stat_mapping = {
            'questions_asked': 'communityActivity.questionsAsked',
            'answers_given': 'communityActivity.answersGiven',
            'accepted_answers': 'communityActivity.acceptedAnswers',
            'helpful_votes': 'communityActivity.helpfulVotes'
        }
        
        if stat_type not in stat_mapping:
            return False
        
        db.profiles.update_one(
            {"user_id": user_id},
            {"$inc": {stat_mapping[stat_type]: 1}},
            upsert=True
        )
        return True
    except Exception as e:
        print(f"❌ Error incrementing stat: {e}")
        return False


def check_and_award_badges(user_id, db):
    """Check if user qualifies for any new badges"""
    try:
        profile = db.profiles.find_one({"user_id": user_id})
        if not profile:
            return
        
        existing_badges = {b.get('badge_id') for b in profile.get('badges', [])}
        community_activity = profile.get('communityActivity', {})
        total_points = profile.get('total_points', 0)
        
        for badge_id, badge_def in BADGE_DEFINITIONS.items():
            if badge_id in existing_badges:
                continue
            
            requirement = badge_def['requirement']
            req_type = requirement['type']
            req_value = requirement['value']
            
            qualifies = False
            if req_type == 'accepted_answers':
                qualifies = community_activity.get('acceptedAnswers', 0) >= req_value
            elif req_type == 'questions_asked':
                qualifies = community_activity.get('questionsAsked', 0) >= req_value
            elif req_type == 'total_points':
                qualifies = total_points >= req_value
            
            if qualifies:
                badge = {
                    'badge_id': badge_id,
                    'name': badge_def['name'],
                    'icon': badge_def['icon'],
                    'description': badge_def['description'],
                    'earned_date': datetime.utcnow()
                }
                
                db.profiles.update_one(
                    {"user_id": user_id},
                    {"$push": {"badges": badge}}
                )
                
                print(f"🏆 Badge awarded to {user_id}: {badge_def['name']}")
    
    except Exception as e:
        print(f"❌ Error checking badges: {e}")


def create_notification(db, user_id, notification_type, title, message, related_id=None):
    """Create a notification for a user"""
    try:
        notification = {
            'notification_id': str(uuid.uuid4()),
            'user_id': user_id,
            'type': notification_type,
            'title': title,
            'message': message,
            'related_id': related_id,
            'read': False,
            'created_at': datetime.utcnow()
        }
        db.notifications.insert_one(notification)
        print(f"🔔 Notification created for {user_id}: {title}")
        return True
    except Exception as e:
        print(f"❌ Error creating notification: {e}")
        return False


def check_inappropriate_content(text):
    """Check if content contains inappropriate keywords"""
    text_lower = text.lower()
    detected = [keyword for keyword in INAPPROPRIATE_KEYWORDS if keyword in text_lower]
    return len(detected) > 0, detected


def calculate_trending_score(post):
    """Calculate trending score based on engagement"""
    # Weight factors
    view_weight = 0.1
    like_weight = 2
    reply_weight = 3
    
    # Time decay (newer posts get boost)
    time_diff = datetime.utcnow() - post.get('created_at', datetime.utcnow())
    hours_old = max(time_diff.total_seconds() / 3600, 1)
    time_decay = 1 / (hours_old ** 0.5)
    
    score = (
        post.get('view_count', 0) * view_weight +
        post.get('like_count', 0) * like_weight +
        post.get('reply_count', 0) * reply_weight
    ) * time_decay
    
    return score


def auto_feature_posts(db):
    """Automatically feature trending posts"""
    try:
        posts = list(db.community_posts.find())
        
        # Calculate scores
        for post in posts:
            score = calculate_trending_score(post)
            db.community_posts.update_one(
                {'post_id': post['post_id']},
                {'$set': {'trending_score': score}}
            )
        
        # Get top 3 trending posts from last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        trending_posts = db.community_posts.find({
            'created_at': {'$gte': week_ago}
        }).sort('trending_score', -1).limit(3)
        
        # Unfeature all posts first
        db.community_posts.update_many({}, {'$set': {'featured': False}})
        
        # Feature top trending
        for post in trending_posts:
            db.community_posts.update_one(
                {'post_id': post['post_id']},
                {'$set': {'featured': True}}
            )
        
        print("✅ Auto-featured trending posts")
    except Exception as e:
        print(f"❌ Error auto-featuring posts: {e}")


@community_bp.route('/posts', methods=['GET'])
@jwt_required()
def get_posts():
    """Get all community posts"""
    try:
        db = current_app.db
        
        # Auto-feature trending posts
        auto_feature_posts(db)
        
        posts = list(db.community_posts.find({'is_deleted': {'$ne': True}}).sort('created_at', -1))
        
        formatted_posts = []
        for post in posts:
            author_user = db.users.find_one({"user_id": post['author_id']})
            
            formatted_post = {
                'post_id': str(post['post_id']),
                'title': post['title'],
                'description': post['description'][:200] + '...' if len(post.get('description', '')) > 200 else post.get('description', ''),
                'category': post.get('category', 'general'),
                'tags': post.get('tags', []),
                'is_anonymous': post.get('is_anonymous', False),
                'author_id': str(post['author_id']),
                'author_name': author_user['name'] if author_user else 'Unknown',
                'author_role': author_user['role'] if author_user else 'student',
                'reply_count': post.get('reply_count', 0),
                'like_count': post.get('like_count', 0),
                'view_count': post.get('view_count', 0),
                'status': post.get('status', 'active'),
                'has_accepted_answer': post.get('has_accepted_answer', False),
                'featured': post.get('featured', False),
                'time_ago': get_time_ago(post.get('created_at')),
                'created_at': str(post.get('created_at', '')),
                'attachments': post.get('attachments', []),
                'is_reported': post.get('is_reported', False)
            }
            formatted_posts.append(formatted_post)
        
        return jsonify({
            'posts': formatted_posts,
            'total': len(formatted_posts)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching posts: {e}")
        return jsonify({'error': 'Failed to fetch posts'}), 500


@community_bp.route('/posts', methods=['POST'])
@jwt_required()
def create_post():
    """Create a new community post"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        required_fields = ['title', 'description', 'category', 'tags']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Check for inappropriate content
        combined_text = f"{data['title']} {data['description']}"
        is_inappropriate, keywords = check_inappropriate_content(combined_text)
        
        db = current_app.db
        post_id = str(uuid.uuid4())
        
        new_post = {
            'post_id': post_id,
            'title': data['title'],
            'description': data['description'],
            'category': data['category'],
            'tags': data['tags'],
            'is_anonymous': data.get('is_anonymous', False),
            'author_id': current_user_id,
            'reply_count': 0,
            'like_count': 0,
            'view_count': 0,
            'status': 'active',
            'has_accepted_answer': False,
            'featured': False,
            'attachments': data.get('attachments', []),
            'is_reported': False,
            'is_deleted': False,
            'flagged_inappropriate': is_inappropriate,
            'flagged_keywords': keywords if is_inappropriate else [],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        db.community_posts.insert_one(new_post)
        
        # Mental health analysis
        try:
            analysis = analyze_text(combined_text, context='community_post')
            
            if analysis['score'] > 0:
                mh_log = {
                    'log_id': str(uuid.uuid4()),
                    'user_id': current_user_id,
                    'timestamp': datetime.utcnow(),
                    'post_id': post_id,
                    'score': analysis['score'],
                    'level': analysis['level'],
                    'keywords_detected': analysis['keywords_detected'],
                    'sentiment': analysis['sentiment'],
                    'confidence': analysis['confidence'],
                    'categories': analysis.get('categories', []),
                    'recommendations': analysis.get('recommendations', []),
                    'context': 'community_post',
                    'needs_attention': analysis['needs_attention']
                }
                db.mental_health_logs.insert_one(mh_log)
                
                db.user_wellness_profile.update_one(
                    {'user_id': current_user_id},
                    {
                        '$set': {
                            'last_check': datetime.utcnow(),
                            'overall_status': analysis['level']
                        }
                    },
                    upsert=True
                )
                
                if analysis['needs_attention']:
                    check_and_send_alerts(current_user_id, analysis['level'], combined_text, db)
                
                send_student_encouragement(current_user_id, analysis['level'], db)
                
        except Exception as e:
            print(f"⚠️ Mental health analysis failed: {e}")
        
        award_points(current_user_id, 2, 'Asked a question', db)
        increment_community_stat(current_user_id, 'questions_asked', db)
        
        print(f"✅ Post created: {post_id} by user {current_user_id}")
        
        return jsonify({
            'message': 'Post created successfully',
            'post_id': post_id,
            'flagged_inappropriate': is_inappropriate
        }), 201
        
    except Exception as e:
        print(f"❌ Error creating post: {e}")
        return jsonify({'error': 'Failed to create post'}), 500


@community_bp.route('/posts/<post_id>', methods=['GET'])
@jwt_required()
def get_post_detail(post_id):
    """Get detailed post with replies"""
    try:
        db = current_app.db
        
        # Increment view count
        db.community_posts.update_one(
            {'post_id': post_id},
            {'$inc': {'view_count': 1}}
        )
        
        post = db.community_posts.find_one({'post_id': post_id, 'is_deleted': {'$ne': True}})
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        author = db.users.find_one({'user_id': post['author_id']})
        
        # Get replies with nested structure
        replies = list(db.community_replies.find({
            'post_id': post_id,
            'is_deleted': {'$ne': True}
        }).sort('created_at', 1))
        
        formatted_replies = []
        for reply in replies:
            reply_author = db.users.find_one({'user_id': reply['author_id']})
            
            # Get nested replies
            nested_replies = list(db.community_replies.find({
                'parent_reply_id': reply['reply_id'],
                'is_deleted': {'$ne': True}
            }).sort('created_at', 1))
            
            formatted_nested = []
            for nested in nested_replies:
                nested_author = db.users.find_one({'user_id': nested['author_id']})
                formatted_nested.append({
                    'reply_id': str(nested['reply_id']),
                    'content': nested['content'],
                    'author_id': str(nested['author_id']),
                    'author_name': nested_author['name'] if nested_author else 'Unknown',
                    'author_role': nested_author['role'] if nested_author else 'student',
                    'is_anonymous': nested.get('is_anonymous', False),
                    'like_count': nested.get('like_count', 0),
                    'dislike_count': nested.get('dislike_count', 0),
                    'time_ago': get_time_ago(nested.get('created_at')),
                    'created_at': str(nested.get('created_at', ''))
                })
            
            formatted_reply = {
                'reply_id': str(reply['reply_id']),
                'content': reply['content'],
                'author_id': str(reply['author_id']),
                'author_name': reply_author['name'] if reply_author else 'Unknown',
                'author_role': reply_author['role'] if reply_author else 'student',
                'is_anonymous': reply.get('is_anonymous', False),
                'like_count': reply.get('like_count', 0),
                'dislike_count': reply.get('dislike_count', 0),
                'is_accepted': reply.get('is_accepted', False),
                'attachments': reply.get('attachments', []),
                'nested_replies': formatted_nested,
                'time_ago': get_time_ago(reply.get('created_at')),
                'created_at': str(reply.get('created_at', ''))
            }
            formatted_replies.append(formatted_reply)
        
        formatted_post = {
            'post_id': str(post['post_id']),
            'title': post['title'],
            'description': post['description'],
            'category': post.get('category', 'general'),
            'tags': post.get('tags', []),
            'is_anonymous': post.get('is_anonymous', False),
            'author_id': str(post['author_id']),
            'author_name': author['name'] if author else 'Unknown',
            'author_role': author['role'] if author else 'student',
            'reply_count': post.get('reply_count', 0),
            'like_count': post.get('like_count', 0),
            'view_count': post.get('view_count', 0),
            'status': post.get('status', 'active'),
            'has_accepted_answer': post.get('has_accepted_answer', False),
            'attachments': post.get('attachments', []),
            'time_ago': get_time_ago(post.get('created_at')),
            'created_at': str(post.get('created_at', '')),
            'replies': formatted_replies
        }
        
        return jsonify(formatted_post), 200
        
    except Exception as e:
        print(f"❌ Error fetching post detail: {e}")
        return jsonify({'error': 'Failed to fetch post'}), 500


@community_bp.route('/posts/<post_id>', methods=['PUT'])
@jwt_required()
def update_post(post_id):
    """Update a post (only by author)"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        db = current_app.db
        
        post = db.community_posts.find_one({'post_id': post_id})
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        if str(post['author_id']) != str(current_user_id):
            return jsonify({'error': 'Unauthorized'}), 403
        
        update_fields = {}
        if 'title' in data:
            update_fields['title'] = data['title']
        if 'description' in data:
            update_fields['description'] = data['description']
        if 'tags' in data:
            update_fields['tags'] = data['tags']
        
        update_fields['updated_at'] = datetime.utcnow()
        
        db.community_posts.update_one(
            {'post_id': post_id},
            {'$set': update_fields}
        )
        
        return jsonify({'message': 'Post updated successfully'}), 200
        
    except Exception as e:
        print(f"❌ Error updating post: {e}")
        return jsonify({'error': 'Failed to update post'}), 500


@community_bp.route('/posts/<post_id>', methods=['DELETE'])
@jwt_required()
def delete_post(post_id):
    """Soft delete a post"""
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        post = db.community_posts.find_one({'post_id': post_id})
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        # Check if user is author or admin
        user = db.users.find_one({'user_id': current_user_id})
        is_author = str(post['author_id']) == str(current_user_id)
        is_admin = user and user.get('role') in ['teacher', 'counselor']
        
        if not (is_author or is_admin):
            return jsonify({'error': 'Unauthorized'}), 403
        
        db.community_posts.update_one(
            {'post_id': post_id},
            {'$set': {'is_deleted': True, 'deleted_at': datetime.utcnow()}}
        )
        
        return jsonify({'message': 'Post deleted successfully'}), 200
        
    except Exception as e:
        print(f"❌ Error deleting post: {e}")
        return jsonify({'error': 'Failed to delete post'}), 500


@community_bp.route('/posts/<post_id>/replies', methods=['POST'])
@jwt_required()
def create_reply(post_id):
    """Create a reply to a post or another reply"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data.get('content'):
            return jsonify({'error': 'Content is required'}), 400
        
        db = current_app.db
        
        post = db.community_posts.find_one({'post_id': post_id})
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        reply_id = str(uuid.uuid4())
        new_reply = {
            'reply_id': reply_id,
            'post_id': post_id,
            'parent_reply_id': data.get('parent_reply_id'),  # For nested replies
            'content': data['content'],
            'author_id': current_user_id,
            'is_anonymous': data.get('is_anonymous', False),
            'like_count': 0,
            'dislike_count': 0,
            'is_accepted': False,
            'attachments': data.get('attachments', []),
            'is_deleted': False,
            'created_at': datetime.utcnow()
        }
        
        db.community_replies.insert_one(new_reply)

        # Mental health analysis
        try:
            analysis = analyze_text(data['content'], context='community_reply')
            
            if analysis['score'] > 0:
                mh_log = {
                    'log_id': str(uuid.uuid4()),
                    'user_id': current_user_id,
                    'timestamp': datetime.utcnow(),
                    'reply_id': reply_id,
                    'post_id': post_id,
                    'score': analysis['score'],
                    'level': analysis['level'],
                    'keywords_detected': analysis['keywords_detected'],
                    'sentiment': analysis['sentiment'],
                    'confidence': analysis['confidence'],
                    'categories': analysis.get('categories', []),
                    'context': 'community_reply',
                    'needs_attention': analysis['needs_attention']
                }
                db.mental_health_logs.insert_one(mh_log)
                
                db.user_wellness_profile.update_one(
                    {'user_id': current_user_id},
                    {'$set': {'last_check': datetime.utcnow(), 'overall_status': analysis['level']}},
                    upsert=True
                )
                
                if analysis['needs_attention']:
                    check_and_send_alerts(current_user_id, analysis['level'], data['content'], db)
                
                send_student_encouragement(current_user_id, analysis['level'], db)
                
        except Exception as e:
            print(f"⚠️ Mental health analysis failed: {e}")
        
        # Update post reply count (only for top-level replies)
        if not data.get('parent_reply_id'):
            db.community_posts.update_one(
                {'post_id': post_id},
                {
                    '$inc': {'reply_count': 1},
                    '$set': {'updated_at': datetime.utcnow()}
                }
            )
        
        # Create notification for post author
        if str(post['author_id']) != str(current_user_id):
            author_user = db.users.find_one({'user_id': current_user_id})
            author_name = author_user['name'] if author_user else 'Someone'
            
            create_notification(
                db,
                post['author_id'],
                'reply',
                'New Reply on Your Post',
                f"{author_name} replied to your post: {post['title'][:50]}...",
                post_id
            )
        
        award_points(current_user_id, 1, 'Posted a reply', db)
        increment_community_stat(current_user_id, 'answers_given', db)
        
        print(f"✅ Reply created: {reply_id} on post {post_id}")
        
        return jsonify({
            'message': 'Reply created successfully',
            'reply_id': reply_id
        }), 201
        
    except Exception as e:
        print(f"❌ Error creating reply: {e}")
        return jsonify({'error': 'Failed to create reply'}), 500


@community_bp.route('/replies/<reply_id>', methods=['PUT'])
@jwt_required()
def update_reply(reply_id):
    """Update a reply"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        db = current_app.db
        
        reply = db.community_replies.find_one({'reply_id': reply_id})
        if not reply:
            return jsonify({'error': 'Reply not found'}), 404
        
        if str(reply['author_id']) != str(current_user_id):
            return jsonify({'error': 'Unauthorized'}), 403
        
        db.community_replies.update_one(
            {'reply_id': reply_id},
            {
                '$set': {
                    'content': data['content'],
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        return jsonify({'message': 'Reply updated successfully'}), 200
        
    except Exception as e:
        print(f"❌ Error updating reply: {e}")
        return jsonify({'error': 'Failed to update reply'}), 500


@community_bp.route('/replies/<reply_id>', methods=['DELETE'])
@jwt_required()
def delete_reply(reply_id):
    """Soft delete a reply"""
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        reply = db.community_replies.find_one({'reply_id': reply_id})
        if not reply:
            return jsonify({'error': 'Reply not found'}), 404
        
        user = db.users.find_one({'user_id': current_user_id})
        is_author = str(reply['author_id']) == str(current_user_id)
        is_admin = user and user.get('role') in ['teacher', 'counselor']
        
        if not (is_author or is_admin):
            return jsonify({'error': 'Unauthorized'}), 403
        
        db.community_replies.update_one(
            {'reply_id': reply_id},
            {'$set': {'is_deleted': True, 'deleted_at': datetime.utcnow()}}
        )
        
        return jsonify({'message': 'Reply deleted successfully'}), 200
        
    except Exception as e:
        print(f"❌ Error deleting reply: {e}")
        return jsonify({'error': 'Failed to delete reply'}), 500


@community_bp.route('/posts/<post_id>/like', methods=['POST'])
@jwt_required()
def like_post(post_id):
    """Like/unlike a post"""
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        existing_like = db.community_likes.find_one({
            'post_id': post_id,
            'user_id': current_user_id,
            'type': 'post'
        })
        
        if existing_like:
            db.community_likes.delete_one({'_id': existing_like['_id']})
            db.community_posts.update_one(
                {'post_id': post_id},
                {'$inc': {'like_count': -1}}
            )
            return jsonify({'message': 'Post unliked', 'liked': False}), 200
        else:
            db.community_likes.insert_one({
                'post_id': post_id,
                'user_id': current_user_id,
                'type': 'post',
                'created_at': datetime.utcnow()
            })
            db.community_posts.update_one(
                {'post_id': post_id},
                {'$inc': {'like_count': 1}}
            )
            return jsonify({'message': 'Post liked', 'liked': True}), 200
            
    except Exception as e:
        print(f"❌ Error liking post: {e}")
        return jsonify({'error': 'Failed to like post'}), 500


@community_bp.route('/replies/<reply_id>/like', methods=['POST'])
@jwt_required()
def like_reply(reply_id):
    """Like a reply"""
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        existing_like = db.community_likes.find_one({
            'reply_id': reply_id,
            'user_id': current_user_id,
            'type': 'reply_like'
        })
        
        if existing_like:
            db.community_likes.delete_one({'_id': existing_like['_id']})
            db.community_replies.update_one(
                {'reply_id': reply_id},
                {'$inc': {'like_count': -1}}
            )
            return jsonify({'message': 'Reply unliked', 'liked': False}), 200
        else:
            # Remove dislike if exists
            db.community_likes.delete_one({
                'reply_id': reply_id,
                'user_id': current_user_id,
                'type': 'reply_dislike'
            })
            
            db.community_likes.insert_one({
                'reply_id': reply_id,
                'user_id': current_user_id,
                'type': 'reply_like',
                'created_at': datetime.utcnow()
            })
            db.community_replies.update_one(
                {'reply_id': reply_id},
                {'$inc': {'like_count': 1}}
            )
            
            # Increment helpful votes stat for reply author
            reply = db.community_replies.find_one({'reply_id': reply_id})
            if reply:
                increment_community_stat(reply['author_id'], 'helpful_votes', db)
            
            return jsonify({'message': 'Reply liked', 'liked': True}), 200
            
    except Exception as e:
        print(f"❌ Error liking reply: {e}")
        return jsonify({'error': 'Failed to like reply'}), 500


@community_bp.route('/replies/<reply_id>/dislike', methods=['POST'])
@jwt_required()
def dislike_reply(reply_id):
    """Dislike a reply"""
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        existing_dislike = db.community_likes.find_one({
            'reply_id': reply_id,
            'user_id': current_user_id,
            'type': 'reply_dislike'
        })
        
        if existing_dislike:
            db.community_likes.delete_one({'_id': existing_dislike['_id']})
            db.community_replies.update_one(
                {'reply_id': reply_id},
                {'$inc': {'dislike_count': -1}}
            )
            return jsonify({'message': 'Reply undisliked', 'disliked': False}), 200
        else:
            # Remove like if exists
            db.community_likes.delete_one({
                'reply_id': reply_id,
                'user_id': current_user_id,
                'type': 'reply_like'
            })
            
            db.community_likes.insert_one({
                'reply_id': reply_id,
                'user_id': current_user_id,
                'type': 'reply_dislike',
                'created_at': datetime.utcnow()
            })
            db.community_replies.update_one(
                {'reply_id': reply_id},
                {'$inc': {'dislike_count': 1}}
            )
            return jsonify({'message': 'Reply disliked', 'disliked': True}), 200
            
    except Exception as e:
        print(f"❌ Error disliking reply: {e}")
        return jsonify({'error': 'Failed to dislike reply'}), 500



@community_bp.route('/replies/<reply_id>/accept', methods=['POST'])
@jwt_required()
def accept_reply(reply_id):
    """
    Accept a reply as the answer
    ✨ UPDATED: Now sends email notification to answer author
    """
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        reply = db.community_replies.find_one({'reply_id': reply_id})
        if not reply:
            return jsonify({'error': 'Reply not found'}), 404
        
        post = db.community_posts.find_one({'post_id': reply['post_id']})
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        if str(post['author_id']) != str(current_user_id):
            return jsonify({'error': 'Only post author can accept answers'}), 403
        
        was_already_accepted = reply.get('is_accepted', False)
        
        # Unaccept all other replies for this post
        db.community_replies.update_many(
            {'post_id': reply['post_id'], 'reply_id': {'$ne': reply_id}},
            {'$set': {'is_accepted': False}}
        )
        
        # Accept this reply
        db.community_replies.update_one(
            {'reply_id': reply_id},
            {'$set': {'is_accepted': True}}
        )
        
        # Mark post as having accepted answer
        db.community_posts.update_one(
            {'post_id': reply['post_id']},
            {'$set': {'has_accepted_answer': True, 'status': 'answered'}}
        )
        
        # Award points to the reply author
        if not was_already_accepted:
            reply_author_id = str(reply['author_id'])
            award_points(reply_author_id, 10, 'Answer accepted', db)
            increment_community_stat(reply_author_id, 'accepted_answers', db)
            
            # ⭐ NEW: Send notification with email using NotificationManager
            try:
                from app.utils.notification_manager import create_notification_manager
                notif_manager = create_notification_manager(db)
                
                notif_manager.send_answer_accepted_notification(
                    answer_author_id=reply_author_id,
                    question_title=post['title'],
                    post_id=reply['post_id'],
                    points_earned=10
                )
                
                print(f"✅ Answer accepted notification (with email) sent to {reply_author_id}")
                
            except ImportError:
                print("⚠️ Email service not available, sending basic notification")
                # Fallback to old notification method
                reply_author = db.users.find_one({'user_id': reply_author_id})
                if reply_author:
                    create_notification(
                        db,
                        reply_author_id,
                        'accepted_answer',
                        '🎉 Your Answer Was Accepted!',
                        f"Your answer on '{post['title'][:50]}...' was accepted. You earned 10 points!",
                        reply['post_id']
                    )
        
        return jsonify({'message': 'Reply accepted as answer'}), 200
        
    except Exception as e:
        print(f"❌ Error accepting reply: {e}")
        return jsonify({'error': 'Failed to accept reply'}), 500




@community_bp.route('/posts/<post_id>/report', methods=['POST'])
@jwt_required()
def report_post(post_id):
    """Report a post for moderation"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        db = current_app.db
        
        post = db.community_posts.find_one({'post_id': post_id})
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        report_id = str(uuid.uuid4())
        report = {
            'report_id': report_id,
            'post_id': post_id,
            'reported_by': current_user_id,
            'reason': data.get('reason', 'No reason provided'),
            'description': data.get('description', ''),
            'status': 'pending',
            'created_at': datetime.utcnow()
        }
        
        db.community_reports.insert_one(report)
        
        # Mark post as reported
        db.community_posts.update_one(
            {'post_id': post_id},
            {'$set': {'is_reported': True}}
        )
        
        # Notify counselors/teachers
        counselors = db.users.find({'role': {'$in': ['counselor', 'teacher']}})
        for counselor in counselors:
            create_notification(
                db,
                counselor['user_id'],
                'moderation',
                '⚠️ Content Reported',
                f"A post has been reported: {post['title'][:50]}...",
                post_id
            )
        
        print(f"⚠️ Post reported: {post_id} by {current_user_id}")
        
        return jsonify({'message': 'Post reported successfully'}), 200
        
    except Exception as e:
        print(f"❌ Error reporting post: {e}")
        return jsonify({'error': 'Failed to report post'}), 500


@community_bp.route('/replies/<reply_id>/report', methods=['POST'])
@jwt_required()
def report_reply(reply_id):
    """Report a reply for moderation"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        db = current_app.db
        
        reply = db.community_replies.find_one({'reply_id': reply_id})
        if not reply:
            return jsonify({'error': 'Reply not found'}), 404
        
        report_id = str(uuid.uuid4())
        report = {
            'report_id': report_id,
            'reply_id': reply_id,
            'reported_by': current_user_id,
            'reason': data.get('reason', 'No reason provided'),
            'description': data.get('description', ''),
            'status': 'pending',
            'created_at': datetime.utcnow()
        }
        
        db.community_reports.insert_one(report)
        
        return jsonify({'message': 'Reply reported successfully'}), 200
        
    except Exception as e:
        print(f"❌ Error reporting reply: {e}")
        return jsonify({'error': 'Failed to report reply'}), 500


@community_bp.route('/posts/<post_id>/share', methods=['POST'])
@jwt_required()
def share_post(post_id):
    """Track post shares and return shareable link"""
    try:
        db = current_app.db
        current_user_id = get_jwt_identity()
        
        post = db.community_posts.find_one({'post_id': post_id})
        if not post:
            return jsonify({'error': 'Post not found'}), 404
        
        # Track share
        db.community_shares.insert_one({
            'post_id': post_id,
            'shared_by': current_user_id,
            'shared_at': datetime.utcnow()
        })
        
        # Increment share count
        db.community_posts.update_one(
            {'post_id': post_id},
            {'$inc': {'share_count': 1}}
        )
        
        # Create shareable link (adjust domain as needed)
        shareable_link = f"https://yourapp.com/community/post/{post_id}"
        
        return jsonify({
            'message': 'Post shared successfully',
            'share_link': shareable_link,
            'share_text': f"Check out this discussion: {post['title']}"
        }), 200
        
    except Exception as e:
        print(f"❌ Error sharing post: {e}")
        return jsonify({'error': 'Failed to share post'}), 500


@community_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    """Get user notifications"""
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        notifications = list(db.notifications.find({
            'user_id': current_user_id
        }).sort('created_at', -1).limit(50))
        
        formatted_notifications = []
        for notif in notifications:
            formatted_notifications.append({
                'notification_id': str(notif['notification_id']),
                'type': notif['type'],
                'title': notif['title'],
                'message': notif['message'],
                'related_id': notif.get('related_id'),
                'read': notif.get('read', False),
                'time_ago': get_time_ago(notif.get('created_at')),
                'created_at': str(notif.get('created_at', ''))
            })
        
        unread_count = db.notifications.count_documents({
            'user_id': current_user_id,
            'read': False
        })
        
        return jsonify({
            'notifications': formatted_notifications,
            'unread_count': unread_count
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching notifications: {e}")
        return jsonify({'error': 'Failed to fetch notifications'}), 500


@community_bp.route('/notifications/<notification_id>/read', methods=['PUT'])
@jwt_required()
def mark_notification_read(notification_id):
    """Mark notification as read"""
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        db.notifications.update_one(
            {
                'notification_id': notification_id,
                'user_id': current_user_id
            },
            {'$set': {'read': True}}
        )
        
        return jsonify({'message': 'Notification marked as read'}), 200
        
    except Exception as e:
        print(f"❌ Error marking notification: {e}")
        return jsonify({'error': 'Failed to mark notification'}), 500


@community_bp.route('/moderation/reports', methods=['GET'])
@jwt_required()
def get_reports():
    """Get all reports (counselors/teachers only)"""
    try:
        current_user_id = get_jwt_identity()
        db = current_app.db
        
        user = db.users.find_one({'user_id': current_user_id})
        if not user or user.get('role') not in ['counselor', 'teacher']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        reports = list(db.community_reports.find({
            'status': 'pending'
        }).sort('created_at', -1))
        
        formatted_reports = []
        for report in reports:
            # Get reported content
            if 'post_id' in report:
                content = db.community_posts.find_one({'post_id': report['post_id']})
                content_type = 'post'
            else:
                content = db.community_replies.find_one({'reply_id': report['reply_id']})
                content_type = 'reply'
            
            reporter = db.users.find_one({'user_id': report['reported_by']})
            
            formatted_reports.append({
                'report_id': str(report['report_id']),
                'content_type': content_type,
                'content_id': report.get('post_id') or report.get('reply_id'),
                'content_preview': content.get('title' if content_type == 'post' else 'content', '')[:100],
                'reason': report['reason'],
                'description': report.get('description', ''),
                'reported_by': reporter['name'] if reporter else 'Unknown',
                'status': report['status'],
                'time_ago': get_time_ago(report.get('created_at')),
                'created_at': str(report.get('created_at', ''))
            })
        
        return jsonify({
            'reports': formatted_reports,
            'total': len(formatted_reports)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching reports: {e}")
        return jsonify({'error': 'Failed to fetch reports'}), 500


@community_bp.route('/moderation/reports/<report_id>/resolve', methods=['PUT'])
@jwt_required()
def resolve_report(report_id):
    """Resolve a report (counselors/teachers only)"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        db = current_app.db
        
        user = db.users.find_one({'user_id': current_user_id})
        if not user or user.get('role') not in ['counselor', 'teacher']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        action = data.get('action')  # 'dismiss', 'delete_content', 'warn_user'
        
        report = db.community_reports.find_one({'report_id': report_id})
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        # Update report status
        db.community_reports.update_one(
            {'report_id': report_id},
            {
                '$set': {
                    'status': 'resolved',
                    'resolved_by': current_user_id,
                    'action_taken': action,
                    'resolved_at': datetime.utcnow()
                }
            }
        )
        
        # Take action
        if action == 'delete_content':
            if 'post_id' in report:
                db.community_posts.update_one(
                    {'post_id': report['post_id']},
                    {'$set': {'is_deleted': True, 'deleted_at': datetime.utcnow()}}
                )
            else:
                db.community_replies.update_one(
                    {'reply_id': report['reply_id']},
                    {'$set': {'is_deleted': True, 'deleted_at': datetime.utcnow()}}
                )
        
        return jsonify({'message': 'Report resolved successfully'}), 200
        
    except Exception as e:
        print(f"❌ Error resolving report: {e}")
        return jsonify({'error': 'Failed to resolve report'}), 500