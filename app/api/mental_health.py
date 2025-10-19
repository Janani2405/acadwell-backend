# backend/app/api/mental_health.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from app.utils.mental_health_analyzer import analyze_text, get_wellness_summary, get_trend_analysis
from app.utils.wellness_notifications import check_and_send_alerts, send_student_encouragement
import uuid

mental_health_bp = Blueprint('mental_health', __name__)

# ==================== STUDENT ENDPOINTS ====================

@mental_health_bp.route('/wellness/dashboard', methods=['GET'])
@jwt_required()
def get_wellness_dashboard():
    """Get student's wellness dashboard data"""
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role != 'student':
            return jsonify({'error': 'Only students can access wellness dashboard'}), 403
        
        db = current_app.db
        
        # Get last 30 days of wellness data
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        wellness_logs = list(db.mental_health_logs.find({
            'user_id': current_user_id,
            'timestamp': {'$gte': thirty_days_ago}
        }).sort('timestamp', -1))
        
        # Get wellness profile
        wellness_profile = db.user_wellness_profile.find_one({'user_id': current_user_id})
        
        if not wellness_profile:
            # Create default profile
            wellness_profile = {
                'user_id': current_user_id,
                'overall_status': 'green',
                'last_check': datetime.utcnow(),
                'consent_given': True,
                'created_at': datetime.utcnow()
            }
            db.user_wellness_profile.insert_one(wellness_profile)
        
        # Calculate summary
        summary = get_wellness_summary(wellness_logs)
        
        # Get trend analysis
        trends = get_trend_analysis(wellness_logs)
        
        return jsonify({
            'overall_status': wellness_profile.get('overall_status', 'green'),
            'summary': summary,
            'trends': trends,
            'recent_logs': [{
                'timestamp': log['timestamp'].isoformat(),
                'level': log['level'],
                'score': log['score'],
                'context': log['context']
            } for log in wellness_logs[:10]],
            'total_checks': len(wellness_logs)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching wellness dashboard: {e}")
        return jsonify({'error': 'Failed to fetch wellness data'}), 500


@mental_health_bp.route('/wellness/mood-log', methods=['POST'])
@jwt_required()
def log_mood():
    """Allow student to manually log their mood"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        mood = data.get('mood')  # happy, okay, stressed, sad, anxious
        note = data.get('note', '')
        
        if not mood:
            return jsonify({'error': 'Mood is required'}), 400
        
        db = current_app.db
        
        # Map mood to score
        mood_scores = {
            'happy': 0,
            'okay': 20,
            'stressed': 50,
            'sad': 60,
            'anxious': 70,
            'overwhelmed': 80
        }
        
        score = mood_scores.get(mood, 30)
        level = 'green' if score < 30 else 'yellow' if score < 60 else 'orange' if score < 80 else 'red'
        
        # Create mood log
        mood_log = {
            'log_id': str(uuid.uuid4()),
            'user_id': current_user_id,
            'timestamp': datetime.utcnow(),
            'mood': mood,
            'note': note,
            'score': score,
            'level': level,
            'context': 'manual_mood_log',
            'keywords_detected': []
        }
        
        db.mental_health_logs.insert_one(mood_log)
        
        # Update wellness profile
        db.user_wellness_profile.update_one(
            {'user_id': current_user_id},
            {
                '$set': {
                    'last_check': datetime.utcnow(),
                    'overall_status': level
                },
                '$push': {
                    'mood_history': {
                        '$each': [{
                            'date': datetime.utcnow().strftime('%Y-%m-%d'),
                            'mood': mood,
                            'note': note
                        }],
                        '$slice': -30  # Keep last 30 days
                    }
                }
            },
            upsert=True
        )
        
        # Check if alert needed
        if level in ['orange', 'red']:
            check_and_send_alerts(current_user_id, level, note, db)
        
        return jsonify({
            'message': 'Mood logged successfully',
            'level': level,
            'encouragement': get_encouragement_message(level)
        }), 201
        
    except Exception as e:
        print(f"❌ Error logging mood: {e}")
        return jsonify({'error': 'Failed to log mood'}), 500


@mental_health_bp.route('/wellness/resources', methods=['GET'])
@jwt_required()
def get_wellness_resources():
    """Get mental health resources and helplines"""
    resources = {
        'crisis_helplines': [
            {
                'name': 'National Suicide Prevention Lifeline (US)',
                'number': '988',
                'available': '24/7'
            },
            {
                'name': 'Crisis Text Line',
                'number': 'Text HOME to 741741',
                'available': '24/7'
            },
            {
                'name': 'SAMHSA National Helpline',
                'number': '1-800-662-4357',
                'available': '24/7'
            }
        ],
        'campus_resources': [
            {
                'name': 'Campus Counseling Center',
                'description': 'Free confidential counseling for students',
                'contact': 'Contact your university counseling center'
            },
            {
                'name': 'Student Health Services',
                'description': 'Medical and mental health support',
                'contact': 'Visit your campus health center'
            }
        ],
        'self_help': [
            {
                'title': 'Breathing Exercises',
                'description': '5-minute guided breathing to reduce anxiety',
                'type': 'exercise'
            },
            {
                'title': 'Meditation',
                'description': 'Calm your mind with short meditation sessions',
                'type': 'meditation'
            },
            {
                'title': 'Journaling',
                'description': 'Express your feelings through writing',
                'type': 'writing'
            }
        ],
        'online_support': [
            {
                'name': '7 Cups',
                'url': 'https://www.7cups.com',
                'description': 'Free online therapy and emotional support'
            },
            {
                'name': 'BetterHelp',
                'url': 'https://www.betterhelp.com',
                'description': 'Professional online counseling'
            }
        ]
    }
    
    return jsonify(resources), 200


# ==================== TEACHER/COUNSELOR ENDPOINTS ====================

@mental_health_bp.route('/wellness/students-overview', methods=['GET'])
@jwt_required()
def get_students_wellness_overview():
    """Get overview of students' wellness (for teachers/counselors)"""
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role not in ['teacher', 'counselor', 'admin']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = current_app.db
        
        # Get all students with recent concerning activity
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        # Find students with orange or red levels in last 7 days
        concerning_logs = list(db.mental_health_logs.find({
            'timestamp': {'$gte': seven_days_ago},
            'level': {'$in': ['orange', 'red']}
        }))
        
        # Group by student
        students_map = {}
        for log in concerning_logs:
            user_id = log['user_id']
            if user_id not in students_map:
                user = db.users.find_one({'user_id': user_id})
                if user and user.get('role') == 'student':
                    students_map[user_id] = {
                        'user_id': user_id,
                        'name': user.get('name', 'Unknown'),
                        'email': user.get('email', ''),
                        'highest_level': 'green',
                        'alert_count': 0,
                        'last_alert': None
                    }
            
            if user_id in students_map:
                students_map[user_id]['alert_count'] += 1
                
                # Update highest level
                level_priority = {'green': 0, 'yellow': 1, 'orange': 2, 'red': 3}
                current_priority = level_priority.get(students_map[user_id]['highest_level'], 0)
                new_priority = level_priority.get(log['level'], 0)
                
                if new_priority > current_priority:
                    students_map[user_id]['highest_level'] = log['level']
                
                # Update last alert time
                if not students_map[user_id]['last_alert'] or log['timestamp'] > students_map[user_id]['last_alert']:
                    students_map[user_id]['last_alert'] = log['timestamp']
        
        # Convert to list and sort by priority
        students_list = list(students_map.values())
        level_priority = {'red': 0, 'orange': 1, 'yellow': 2, 'green': 3}
        students_list.sort(key=lambda x: (level_priority.get(x['highest_level'], 4), x['alert_count']), reverse=True)
        
        # Format response
        formatted_students = []
        for student in students_list:
            formatted_students.append({
                'user_id': student['user_id'],
                'name': student['name'],
                'email': student['email'],
                'status': student['highest_level'],
                'alert_count': student['alert_count'],
                'last_alert': student['last_alert'].isoformat() if student['last_alert'] else None
            })
        
        return jsonify({
            'students_needing_attention': formatted_students,
            'total_students': len(formatted_students),
            'critical_count': sum(1 for s in formatted_students if s['status'] == 'red'),
            'concerning_count': sum(1 for s in formatted_students if s['status'] == 'orange')
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching students overview: {e}")
        return jsonify({'error': 'Failed to fetch students data'}), 500


@mental_health_bp.route('/wellness/student/<student_id>/details', methods=['GET'])
@jwt_required()
def get_student_wellness_details(student_id):
    """Get detailed wellness info for a specific student (for teachers/counselors)"""
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role not in ['teacher', 'counselor', 'admin']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = current_app.db
        
        # Get student info
        student = db.users.find_one({'user_id': student_id})
        if not student or student.get('role') != 'student':
            return jsonify({'error': 'Student not found'}), 404
        
        # Get last 30 days of logs
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        wellness_logs = list(db.mental_health_logs.find({
            'user_id': student_id,
            'timestamp': {'$gte': thirty_days_ago}
        }).sort('timestamp', -1))
        
        # Get wellness profile
        wellness_profile = db.user_wellness_profile.find_one({'user_id': student_id})
        
        # Calculate summary
        summary = get_wellness_summary(wellness_logs)
        trends = get_trend_analysis(wellness_logs)
        
        return jsonify({
            'student': {
                'user_id': student_id,
                'name': student.get('name', 'Unknown'),
                'email': student.get('email', ''),
                'regNumber': student.get('regNumber', '')
            },
            'overall_status': wellness_profile.get('overall_status', 'green') if wellness_profile else 'green',
            'summary': summary,
            'trends': trends,
            'recent_alerts': [{
                'timestamp': log['timestamp'].isoformat(),
                'level': log['level'],
                'score': log['score'],
                'context': log['context'],
                'keywords': log.get('keywords_detected', [])
            } for log in wellness_logs[:20]]
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching student details: {e}")
        return jsonify({'error': 'Failed to fetch student data'}), 500


@mental_health_bp.route('/wellness/student/<student_id>/note', methods=['POST'])
@jwt_required()
def add_counselor_note(student_id):
    """Add a counselor note for a student"""
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role not in ['teacher', 'counselor', 'admin']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        note = data.get('note', '')
        
        if not note:
            return jsonify({'error': 'Note is required'}), 400
        
        db = current_app.db
        
        counselor_note = {
            'note_id': str(uuid.uuid4()),
            'student_id': student_id,
            'counselor_id': current_user_id,
            'note': note,
            'timestamp': datetime.utcnow()
        }
        
        db.counselor_notes.insert_one(counselor_note)
        
        return jsonify({'message': 'Note added successfully'}), 201
        
    except Exception as e:
        print(f"❌ Error adding note: {e}")
        return jsonify({'error': 'Failed to add note'}), 500
    



# ==================== HELPER FUNCTIONS ====================

def get_encouragement_message(level):
    """Get encouragement message based on wellness level"""
    messages = {
        'green': "Great to see you're doing well! Keep up the positive momentum! 🌟",
        'yellow': "Remember to take breaks and practice self-care. You're doing your best! 💪",
        'orange': "It's okay to not be okay. Consider reaching out to a counselor or friend. We're here for you. 🤗",
        'red': "Your wellbeing matters. Please reach out to a counselor or call a helpline. You don't have to face this alone. ❤️"
    }
    return messages.get(level, messages['yellow'])


# ==================== ADMIN/STATS ENDPOINTS ====================

@mental_health_bp.route('/wellness/stats/overall', methods=['GET'])
@jwt_required()
def get_overall_wellness_stats():
    """Get overall wellness statistics (for admin)"""
    try:
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = current_app.db
        
        # Get last 7 days stats
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        total_logs = db.mental_health_logs.count_documents({
            'timestamp': {'$gte': seven_days_ago}
        })
        
        red_logs = db.mental_health_logs.count_documents({
            'timestamp': {'$gte': seven_days_ago},
            'level': 'red'
        })
        
        orange_logs = db.mental_health_logs.count_documents({
            'timestamp': {'$gte': seven_days_ago},
            'level': 'orange'
        })
        
        yellow_logs = db.mental_health_logs.count_documents({
            'timestamp': {'$gte': seven_days_ago},
            'level': 'yellow'
        })
        
        green_logs = db.mental_health_logs.count_documents({
            'timestamp': {'$gte': seven_days_ago},
            'level': 'green'
        })
        
        return jsonify({
            'period': 'last_7_days',
            'total_checks': total_logs,
            'breakdown': {
                'critical': red_logs,
                'concerning': orange_logs,
                'monitor': yellow_logs,
                'healthy': green_logs
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching stats: {e}")
        return jsonify({'error': 'Failed to fetch statistics'}), 500