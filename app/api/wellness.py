# backend/app/api/wellness.py
"""
Wellness API Endpoints
Handles mood logging, wellness dashboards, and analytics
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
import uuid
from app.utils.mental_health_analyzer import analyze_text, get_wellness_summary, get_trend_analysis
from app.utils.wellness_notifications import check_and_send_alerts, send_student_encouragement

wellness_bp = Blueprint('wellness', __name__)


# backend/app/api/wellness.py (Update the log_mood endpoint)

# ==================== UPDATED: MOOD LOGGING WITH DATE SELECTION ====================

@wellness_bp.route('/mood', methods=['POST'])
@jwt_required()
def log_mood():
    """
    Allow student to manually log their mood for ANY past date (including today)
    
    Request Body:
    {
        "mood": "happy" | "okay" | "stressed" | "sad" | "anxious" | "overwhelmed",
        "note": "Optional note about feelings",
        "emoji": "😊",
        "date": "2025-03-15"  ✨ NEW - Optional. If not provided, uses today's date
    }
    """
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role != 'student':
            return jsonify({'error': 'Only students can log mood'}), 403
        
        data = request.get_json()
        mood = data.get('mood')
        note = data.get('note', '')
        emoji = data.get('emoji', '')
        date_str = data.get('date')  # ✨ NEW - Optional date parameter
        
        if not mood:
            return jsonify({'error': 'Mood is required'}), 400
        
        db = current_app.db
        
        # ✨ NEW: Parse and validate date
        try:
            if date_str:
                # Parse provided date
                from datetime import datetime as dt
                provided_date = dt.strptime(date_str, '%Y-%m-%d').date()
                today = dt.now().date()
                
                # ✨ NEW: Validate date is not in future
                if provided_date > today:
                    return jsonify({'error': 'Cannot log mood for future dates'}), 400
                
                # Set to provided date at midnight UTC
                mood_datetime = dt.combine(provided_date, dt.min.time())
            else:
                # Use today if no date provided
                mood_datetime = datetime.utcnow()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Map mood to wellness score and level
        mood_mapping = {
            'happy': {'score': 0, 'level': 'green'},
            'great': {'score': 0, 'level': 'green'},
            'okay': {'score': 20, 'level': 'green'},
            'neutral': {'score': 25, 'level': 'yellow'},
            'stressed': {'score': 50, 'level': 'yellow'},
            'worried': {'score': 55, 'level': 'yellow'},
            'sad': {'score': 60, 'level': 'orange'},
            'down': {'score': 65, 'level': 'orange'},
            'anxious': {'score': 70, 'level': 'orange'},
            'overwhelmed': {'score': 80, 'level': 'red'},
            'depressed': {'score': 85, 'level': 'red'}
        }
        
        mood_data = mood_mapping.get(mood.lower(), {'score': 30, 'level': 'yellow'})
        score = mood_data['score']
        level = mood_data['level']
        
        # If note provided, analyze it for additional context
        if note:
            analysis = analyze_text(note, context='mood_note')
            # Adjust score based on note analysis
            if analysis['score'] > score:
                score = min(100, (score + analysis['score']) / 2)
                level = analysis['level']
        
        # ✨ NEW: Check if mood already logged for this date
        date_string = mood_datetime.strftime('%Y-%m-%d')
        existing_mood = db.mood_entries.find_one({
            'user_id': current_user_id,
            'date': date_string
        })
        
        if existing_mood:
            # ✨ NEW: Allow updating existing mood for the day
            db.mood_entries.update_one(
                {'entry_id': existing_mood['entry_id']},
                {
                    '$set': {
                        'mood': mood,
                        'emoji': emoji,
                        'note': note,
                        'score': round(score, 2),
                        'level': level,
                        'timestamp': datetime.utcnow()  # Update timestamp
                    }
                }
            )
            
            # Update mental health log
            db.mental_health_logs.delete_many({
                'user_id': current_user_id,
                'mood_entry_id': existing_mood['entry_id']
            })
            
            message = 'Mood updated successfully'
        else:
            # Create new mood entry
            entry_id = str(uuid.uuid4())
            mood_entry = {
                'entry_id': entry_id,
                'user_id': current_user_id,
                'mood': mood,
                'emoji': emoji,
                'note': note,
                'score': round(score, 2),
                'level': level,
                'timestamp': datetime.utcnow(),
                'date': date_string,  # ✨ NEW: Store date for easy querying
                'context': 'manual_mood_log'
            }
            
            db.mood_entries.insert_one(mood_entry)
            message = 'Mood logged successfully'
        
        # Create mental health log
        mh_log = {
            'log_id': str(uuid.uuid4()),
            'user_id': current_user_id,
            'timestamp': datetime.utcnow(),
            'mood_entry_id': existing_mood['entry_id'] if existing_mood else entry_id,
            'score': score,
            'level': level,
            'keywords_detected': [],
            'sentiment': 'positive' if score < 30 else 'neutral' if score < 60 else 'negative',
            'confidence': 85,
            'context': 'manual_mood_log',
            'needs_attention': level in ['orange', 'red']
        }
        db.mental_health_logs.insert_one(mh_log)
        
        # Update wellness profile
        db.user_wellness_profile.update_one(
            {'user_id': current_user_id},
            {
                '$set': {
                    'last_check': datetime.utcnow(),
                    'overall_status': level,
                    'last_mood': mood,
                    'last_mood_emoji': emoji
                },
                '$push': {
                    'mood_history': {
                        '$each': [{
                            'date': date_string,
                            'mood': mood,
                            'emoji': emoji,
                            'level': level,
                            'note': note[:100] if note else ''
                        }],
                        '$slice': -90  # Keep last 90 days
                    }
                }
            },
            upsert=True
        )
        
        # Check if alert needed (only for recent entries, not old backdated ones)
        days_difference = (datetime.utcnow().date() - mood_datetime.date()).days
        if level in ['orange', 'red'] and days_difference <= 1:  # Alert only for today/yesterday
            check_and_send_alerts(current_user_id, level, note or f"Feeling {mood}", db)
        
        # Send encouragement
        if days_difference <= 1:  # Only encourage for recent moods
            send_student_encouragement(current_user_id, level, db)
        
        return jsonify({
            'message': message,
            'entry_id': existing_mood['entry_id'] if existing_mood else entry_id,
            'level': level,
            'date': date_string,  # ✨ NEW: Return the date
            'encouragement': get_encouragement_message(level, mood) if days_difference <= 1 else None
        }), 201 if not existing_mood else 200
        
    except Exception as e:
        print(f"❌ Error logging mood: {e}")
        return jsonify({'error': 'Failed to log mood'}), 500


# ✨ NEW: Check for existing mood on a date
@wellness_bp.route('/mood/check/<date_string>', methods=['GET'])
@jwt_required()
def check_mood_exists(date_string):
    """
    Check if mood already logged for a specific date
    
    Format: /api/wellness/mood/check/2025-03-15
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Validate date format
        try:
            from datetime import datetime as dt
            dt.strptime(date_string, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        db = current_app.db
        
        existing_mood = db.mood_entries.find_one({
            'user_id': current_user_id,
            'date': date_string
        })
        
        if existing_mood:
            return jsonify({
                'exists': True,
                'mood': existing_mood['mood'],
                'emoji': existing_mood.get('emoji', ''),
                'note': existing_mood.get('note', ''),
                'level': existing_mood.get('level', 'green'),
                'score': existing_mood.get('score', 0)
            }), 200
        else:
            return jsonify({'exists': False}), 200
            
    except Exception as e:
        print(f"❌ Error checking mood: {e}")
        return jsonify({'error': 'Failed to check mood'}), 500


# ✨ NEW: Update existing mood entry
@wellness_bp.route('/mood/<entry_id>', methods=['PUT'])
@jwt_required()
def update_mood(entry_id):
    """
    Update an existing mood entry
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        db = current_app.db
        
        # Check if entry belongs to user
        existing_mood = db.mood_entries.find_one({
            'entry_id': entry_id,
            'user_id': current_user_id
        })
        
        if not existing_mood:
            return jsonify({'error': 'Mood entry not found'}), 404
        
        mood = data.get('mood')
        note = data.get('note', '')
        emoji = data.get('emoji', '')
        
        mood_mapping = {
            'happy': {'score': 0, 'level': 'green'},
            'great': {'score': 0, 'level': 'green'},
            'okay': {'score': 20, 'level': 'green'},
            'neutral': {'score': 25, 'level': 'yellow'},
            'stressed': {'score': 50, 'level': 'yellow'},
            'worried': {'score': 55, 'level': 'yellow'},
            'sad': {'score': 60, 'level': 'orange'},
            'down': {'score': 65, 'level': 'orange'},
            'anxious': {'score': 70, 'level': 'orange'},
            'overwhelmed': {'score': 80, 'level': 'red'},
            'depressed': {'score': 85, 'level': 'red'}
        }
        
        mood_data = mood_mapping.get(mood.lower(), {'score': 30, 'level': 'yellow'})
        score = mood_data['score']
        level = mood_data['level']
        
        # Update mood entry
        db.mood_entries.update_one(
            {'entry_id': entry_id},
            {
                '$set': {
                    'mood': mood,
                    'emoji': emoji,
                    'note': note,
                    'score': round(score, 2),
                    'level': level,
                    'timestamp': datetime.utcnow()
                }
            }
        )
        
        return jsonify({
            'message': 'Mood updated successfully',
            'entry_id': entry_id
        }), 200
        
    except Exception as e:
        print(f"❌ Error updating mood: {e}")
        return jsonify({'error': 'Failed to update mood'}), 500


# ✨ NEW: Delete mood entry
@wellness_bp.route('/mood/<entry_id>', methods=['DELETE'])
@jwt_required()
def delete_mood(entry_id):
    """
    Delete a mood entry
    """
    try:
        current_user_id = get_jwt_identity()
        
        db = current_app.db
        
        # Check if entry belongs to user
        existing_mood = db.mood_entries.find_one({
            'entry_id': entry_id,
            'user_id': current_user_id
        })
        
        if not existing_mood:
            return jsonify({'error': 'Mood entry not found'}), 404
        
        # Delete mood entry
        db.mood_entries.delete_one({'entry_id': entry_id})
        
        # Delete associated mental health log
        db.mental_health_logs.delete_many({
            'user_id': current_user_id,
            'mood_entry_id': entry_id
        })
        
        return jsonify({'message': 'Mood entry deleted successfully'}), 200
        
    except Exception as e:
        print(f"❌ Error deleting mood: {e}")
        return jsonify({'error': 'Failed to delete mood'}), 500

@wellness_bp.route('/mood/history', methods=['GET'])
@jwt_required()
def get_mood_history():
    """
    Get mood history for calendar view
    
    Query params:
    - days: Number of days to retrieve (default: 30)
    """
    try:
        current_user_id = get_jwt_identity()
        days = int(request.args.get('days', 30))
        
        db = current_app.db
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        mood_entries = list(db.mood_entries.find({
            'user_id': current_user_id,
            'timestamp': {'$gte': start_date}
        }).sort('timestamp', -1))
        
        formatted_entries = []
        for entry in mood_entries:
            formatted_entries.append({
                'entry_id': entry['entry_id'],
                'date': entry['date'],
                'mood': entry['mood'],
                'emoji': entry.get('emoji', ''),
                'note': entry.get('note', ''),
                'level': entry['level'],
                'score': entry['score'],
                'timestamp': entry['timestamp'].isoformat()
            })
        
        return jsonify({
            'entries': formatted_entries,
            'total': len(formatted_entries),
            'period_days': days
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching mood history: {e}")
        return jsonify({'error': 'Failed to fetch mood history'}), 500


# ==================== STUDENT WELLNESS DASHBOARD ====================

@wellness_bp.route('/dashboard/student', methods=['GET'])
@jwt_required()
def get_student_wellness_dashboard():
    """Get complete wellness dashboard data for student"""
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role != 'student':
            return jsonify({'error': 'Only students can access this dashboard'}), 403
        
        db = current_app.db
        
        # Get wellness profile
        wellness_profile = db.user_wellness_profile.find_one({'user_id': current_user_id})
        
        # Get last 30 days of mood entries
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        mood_entries = list(db.mood_entries.find({
            'user_id': current_user_id,
            'timestamp': {'$gte': thirty_days_ago}
        }).sort('timestamp', -1))
        
        # Get mental health logs for trend analysis
        mh_logs = list(db.mental_health_logs.find({
            'user_id': current_user_id,
            'timestamp': {'$gte': thirty_days_ago}
        }).sort('timestamp', -1))
        
        # Calculate statistics
        total_entries = len(mood_entries)
        
        if mood_entries:
            avg_score = sum(e.get('score', 0) for e in mood_entries) / total_entries
            
            # Level breakdown
            level_counts = {'green': 0, 'yellow': 0, 'orange': 0, 'red': 0}
            for entry in mood_entries:
                level = entry.get('level', 'green')
                if level in level_counts:
                    level_counts[level] += 1
            
            # Calculate streak (consecutive positive days)
            sorted_entries = sorted(mood_entries, key=lambda x: x['timestamp'], reverse=True)
            current_streak = 0
            for entry in sorted_entries:
                if entry['level'] in ['green', 'yellow']:
                    current_streak += 1
                else:
                    break
        else:
            avg_score = 0
            level_counts = {'green': 0, 'yellow': 0, 'orange': 0, 'red': 0}
            current_streak = 0
        
        # Get wellness summary and trends
        summary = get_wellness_summary(mh_logs) if mh_logs else {}
        trends = get_trend_analysis(mh_logs) if mh_logs else {}
        
        # Get insights based on data
        insights = generate_wellness_insights(mood_entries, mh_logs)
        
        return jsonify({
            'overall_status': wellness_profile.get('overall_status', 'green') if wellness_profile else 'green',
            'last_mood': wellness_profile.get('last_mood', '') if wellness_profile else '',
            'last_mood_emoji': wellness_profile.get('last_mood_emoji', '') if wellness_profile else '',
            'last_check': wellness_profile.get('last_check').isoformat() if wellness_profile and wellness_profile.get('last_check') else None,
            'statistics': {
                'total_entries': total_entries,
                'average_score': round(avg_score, 2),
                'current_streak': current_streak,
                'level_breakdown': level_counts
            },
            'trends': trends,
            'insights': insights,
            'mood_calendar': format_mood_calendar(mood_entries),
            'recent_entries': [{
                'date': e['date'],
                'mood': e['mood'],
                'emoji': e.get('emoji', ''),
                'level': e['level'],
                'note': e.get('note', '')[:50] + '...' if len(e.get('note', '')) > 50 else e.get('note', '')
            } for e in mood_entries[:7]]
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching student dashboard: {e}")
        return jsonify({'error': 'Failed to fetch dashboard data'}), 500


# ==================== TEACHER WELLNESS OVERVIEW ====================

@wellness_bp.route('/dashboard/teacher', methods=['GET'])
@jwt_required()
def get_teacher_wellness_overview():
    """Get wellness overview of all students (for teachers)"""
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role not in ['teacher', 'counselor', 'admin']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = current_app.db
        
        # Get all students
        students = list(db.users.find({'role': 'student'}))
        
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        students_data = []
        critical_count = 0
        concerning_count = 0
        monitor_count = 0
        healthy_count = 0
        
        for student in students:
            student_id = student['user_id']
            
            # Get wellness profile
            wellness_profile = db.user_wellness_profile.find_one({'user_id': student_id})
            
            # Get recent mood entries
            recent_moods = list(db.mood_entries.find({
                'user_id': student_id,
                'timestamp': {'$gte': seven_days_ago}
            }).sort('timestamp', -1).limit(7))
            
            # Get recent alerts
            recent_alerts = db.mental_health_logs.count_documents({
                'user_id': student_id,
                'timestamp': {'$gte': seven_days_ago},
                'level': {'$in': ['orange', 'red']}
            })
            
            overall_status = wellness_profile.get('overall_status', 'green') if wellness_profile else 'green'
            
            # Count by status
            if overall_status == 'red':
                critical_count += 1
            elif overall_status == 'orange':
                concerning_count += 1
            elif overall_status == 'yellow':
                monitor_count += 1
            else:
                healthy_count += 1
            
            # Only include students with concerning status or recent alerts
            if overall_status in ['orange', 'red'] or recent_alerts > 0:
                students_data.append({
                    'student_id': student_id,
                    'name': student.get('name', 'Unknown'),
                    'email': student.get('email', ''),
                    'reg_number': student.get('regNumber', ''),
                    'overall_status': overall_status,
                    'last_check': wellness_profile.get('last_check').isoformat() if wellness_profile and wellness_profile.get('last_check') else None,
                    'last_mood': wellness_profile.get('last_mood', '') if wellness_profile else '',
                    'last_mood_emoji': wellness_profile.get('last_mood_emoji', '') if wellness_profile else '',
                    'alert_count_7days': recent_alerts,
                    'recent_mood_count': len(recent_moods),
                    'needs_attention': overall_status in ['orange', 'red'] or recent_alerts >= 3
                })
        
        # Sort by priority (red first, then by alert count)
        students_data.sort(key=lambda x: (
            0 if x['overall_status'] == 'red' else 1 if x['overall_status'] == 'orange' else 2,
            -x['alert_count_7days']
        ))
        
        # Class-wide analytics
        total_students = len(students)
        
        return jsonify({
            'summary': {
                'total_students': total_students,
                'critical': critical_count,
                'concerning': concerning_count,
                'monitor': monitor_count,
                'healthy': healthy_count
            },
            'students_needing_attention': students_data,
            'alerts_last_7days': sum(s['alert_count_7days'] for s in students_data)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching teacher overview: {e}")
        return jsonify({'error': 'Failed to fetch overview'}), 500


@wellness_bp.route('/student/<student_id>/details', methods=['GET'])
@jwt_required()
def get_student_wellness_details(student_id):
    """Get detailed wellness information for a specific student"""
    try:
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        user_role = claims.get('role')
        
        if user_role not in ['teacher', 'counselor', 'admin']:
            return jsonify({'error': 'Unauthorized'}), 403
        
        db = current_app.db
        
        # Get student info
        student = db.users.find_one({'user_id': student_id, 'role': 'student'})
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get wellness profile
        wellness_profile = db.user_wellness_profile.find_one({'user_id': student_id})
        
        # Get last 30 days data
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        mood_entries = list(db.mood_entries.find({
            'user_id': student_id,
            'timestamp': {'$gte': thirty_days_ago}
        }).sort('timestamp', -1))
        
        mh_logs = list(db.mental_health_logs.find({
            'user_id': student_id,
            'timestamp': {'$gte': thirty_days_ago}
        }).sort('timestamp', -1))
        
        # Calculate statistics
        summary = get_wellness_summary(mh_logs)
        trends = get_trend_analysis(mh_logs)
        
        # Get recent alerts
        recent_alerts = [{
            'timestamp': log['timestamp'].isoformat(),
            'level': log['level'],
            'score': log['score'],
            'context': log.get('context', 'unknown'),
            'keywords': log.get('keywords_detected', [])[:3]  # First 3 keywords
        } for log in mh_logs if log.get('level') in ['orange', 'red']][:10]
        
        # Get counselor notes
        counselor_notes = list(db.counselor_notes.find({
            'student_id': student_id
        }).sort('timestamp', -1).limit(5))
        
        formatted_notes = [{
            'note_id': note['note_id'],
            'note': note['note'],
            'counselor_id': note['counselor_id'],
            'timestamp': note['timestamp'].isoformat()
        } for note in counselor_notes]
        
        return jsonify({
            'student': {
                'student_id': student_id,
                'name': student.get('name', 'Unknown'),
                'email': student.get('email', ''),
                'reg_number': student.get('regNumber', '')
            },
            'wellness_status': {
                'overall_status': wellness_profile.get('overall_status', 'green') if wellness_profile else 'green',
                'last_check': wellness_profile.get('last_check').isoformat() if wellness_profile and wellness_profile.get('last_check') else None,
                'last_mood': wellness_profile.get('last_mood', '') if wellness_profile else '',
                'last_mood_emoji': wellness_profile.get('last_mood_emoji', '') if wellness_profile else ''
            },
            'statistics': summary,
            'trends': trends,
            'recent_alerts': recent_alerts,
            'mood_timeline': format_mood_timeline(mood_entries),
            'counselor_notes': formatted_notes,
            'suggested_actions': generate_intervention_suggestions(wellness_profile, mh_logs)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching student details: {e}")
        return jsonify({'error': 'Failed to fetch student data'}), 500


@wellness_bp.route('/student/<student_id>/note', methods=['POST'])
@jwt_required()
def add_counselor_note(student_id):
    """Add a private counselor note for a student"""
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
        
        return jsonify({
            'message': 'Note added successfully',
            'note_id': counselor_note['note_id']
        }), 201
        
    except Exception as e:
        print(f"❌ Error adding note: {e}")
        return jsonify({'error': 'Failed to add note'}), 500


# ==================== WELLNESS RESOURCES ====================

@wellness_bp.route('/resources', methods=['GET'])
@jwt_required()
def get_wellness_resources():
    """Get mental health resources and support information"""
    
    resources = {
        'crisis_helplines': [
            {
                'name': 'National Suicide Prevention Lifeline (US)',
                'number': '988',
                'description': '24/7 crisis support and suicide prevention',
                'available': '24/7',
                'type': 'phone'
            },
            {
                'name': 'Crisis Text Line',
                'number': 'Text HOME to 741741',
                'description': 'Free 24/7 support via text message',
                'available': '24/7',
                'type': 'text'
            },
            {
                'name': 'SAMHSA National Helpline',
                'number': '1-800-662-4357',
                'description': 'Substance abuse and mental health services',
                'available': '24/7',
                'type': 'phone'
            }
        ],
        'campus_resources': [
            {
                'name': 'Campus Counseling Center',
                'description': 'Free confidential counseling for students',
                'contact': 'Contact your university counseling center',
                'icon': '🏫'
            },
            {
                'name': 'Student Health Services',
                'description': 'Medical and mental health support',
                'contact': 'Visit your campus health center',
                'icon': '⚕️'
            },
            {
                'name': 'Academic Advisor',
                'description': 'Academic support and accommodations',
                'contact': 'Schedule through student portal',
                'icon': '📚'
            }
        ],
        'self_help_activities': [
            {
                'title': 'Breathing Exercises',
                'description': '5-minute guided breathing to reduce anxiety',
                'duration': '5 minutes',
                'type': 'exercise',
                'icon': '🌬️'
            },
            {
                'title': 'Meditation',
                'description': 'Calm your mind with short meditation sessions',
                'duration': '10 minutes',
                'type': 'meditation',
                'icon': '🧘'
            },
            {
                'title': 'Journaling',
                'description': 'Express your feelings through writing',
                'duration': '15 minutes',
                'type': 'writing',
                'icon': '📝'
            },
            {
                'title': 'Walk in Nature',
                'description': 'Take a short walk outside to clear your mind',
                'duration': '20 minutes',
                'type': 'physical',
                'icon': '🌳'
            }
        ],
        'online_support': [
            {
                'name': '7 Cups',
                'url': 'https://www.7cups.com',
                'description': 'Free online therapy and emotional support',
                'type': 'chat'
            },
            {
                'name': 'BetterHelp',
                'url': 'https://www.betterhelp.com',
                'description': 'Professional online counseling',
                'type': 'therapy'
            },
            {
                'name': 'Headspace',
                'url': 'https://www.headspace.com',
                'description': 'Meditation and mindfulness app',
                'type': 'app'
            }
        ]
    }
    
    return jsonify(resources), 200


# ==================== HELPER FUNCTIONS ====================

def get_encouragement_message(level, mood):
    """Get personalized encouragement based on level and mood"""
    messages = {
        'green': {
            'happy': "Amazing! Keep spreading that positive energy! 🌟",
            'great': "You're doing wonderfully! Keep it up! 💪",
            'okay': "Steady as she goes! You're doing great! 👍"
        },
        'yellow': {
            'stressed': "Remember to take breaks and breathe. You've got this! 🌈",
            'worried': "It's okay to feel this way. Reach out if you need support! 💙",
            'neutral': "Take it one step at a time. We're here for you! 🤗"
        },
        'orange': {
            'sad': "It's okay to not be okay. Consider talking to someone you trust. 💚",
            'down': "You're not alone in this. Reach out for support when you need it. 🤝",
            'anxious': "Take deep breaths. Consider our wellness resources for help. 🌺"
        },
        'red': {
            'overwhelmed': "Please reach out to a counselor right now. You matter! ❤️",
            'depressed': "Your wellbeing is important. Contact crisis support immediately. 🆘"
        }
    }
    
    return messages.get(level, {}).get(mood, "We're here to support you every step of the way! 💜")


def format_mood_calendar(mood_entries):
    """Format mood entries for calendar display"""
    calendar_data = {}
    
    for entry in mood_entries:
        date = entry['date']
        if date not in calendar_data:
            calendar_data[date] = {
                'date': date,
                'moods': [],
                'dominant_level': entry['level'],
                'emoji': entry.get('emoji', '')
            }
        calendar_data[date]['moods'].append({
            'mood': entry['mood'],
            'emoji': entry.get('emoji', ''),
            'level': entry['level']
        })
    
    return list(calendar_data.values())


def format_mood_timeline(mood_entries):
    """Format mood entries as timeline for teacher view"""
    timeline = []
    
    for entry in mood_entries:
        timeline.append({
            'date': entry['date'],
            'timestamp': entry['timestamp'].isoformat(),
            'mood': entry['mood'],
            'emoji': entry.get('emoji', ''),
            'level': entry['level'],
            'score': entry.get('score', 0),
            'has_note': bool(entry.get('note'))
        })
    
    return timeline


def generate_wellness_insights(mood_entries, mh_logs):
    """Generate AI-like insights from wellness data"""
    insights = []
    
    if not mood_entries:
        return [{
            'type': 'info',
            'title': 'Start Tracking Your Mood',
            'message': 'Log your mood daily to get personalized insights and track your wellbeing over time.'
        }]
    
    # Check for improvement trend
    if len(mood_entries) >= 7:
        recent_scores = [e.get('score', 0) for e in mood_entries[:7]]
        avg_recent = sum(recent_scores) / len(recent_scores)
        
        if avg_recent < 30:
            insights.append({
                'type': 'positive',
                'title': 'Great Progress! 🎉',
                'message': 'Your mood has been consistently positive this week. Keep up the good work!'
            })
        elif avg_recent > 60:
            insights.append({
                'type': 'concern',
                'title': 'We Notice You Might Be Struggling',
                'message': 'Consider reaching out to a counselor or trusted friend for support.'
            })
    
    # Check for consistency
    if len(mood_entries) >= 14:
        insights.append({
            'type': 'achievement',
            'title': 'Consistency Streak! 🏆',
            'message': f'You\'ve logged your mood {len(mood_entries)} times. Self-awareness is the first step to wellness!'
        })
    
    # Suggest resources based on common moods
    common_moods = {}
    for entry in mood_entries[:14]:
        mood = entry['mood']
        common_moods[mood] = common_moods.get(mood, 0) + 1
    
    if common_moods.get('stressed', 0) >= 3:
        insights.append({
            'type': 'suggestion',
            'title': 'Stress Management Tips',
            'message': 'We noticed you\'ve been feeling stressed. Try our breathing exercises or meditation guides.'
        })
    
    return insights


def generate_intervention_suggestions(wellness_profile, mh_logs):
    """Generate suggested interventions for teachers"""
    suggestions = []
    
    if not wellness_profile:
        return suggestions
    
    overall_status = wellness_profile.get('overall_status', 'green')
    
    if overall_status == 'red':
        suggestions.append({
            'priority': 'urgent',
            'action': 'Immediate Contact',
            'description': 'Reach out to student immediately via phone or in-person meeting'
        })
        suggestions.append({
            'priority': 'urgent',
            'action': 'Crisis Protocol',
            'description': 'Follow institutional crisis intervention procedures'
        })
    elif overall_status == 'orange':
        suggestions.append({
            'priority': 'high',
            'action': 'Schedule Check-in',
            'description': 'Schedule a private meeting within 24-48 hours'
        })
        suggestions.append({
            'priority': 'high',
            'action': 'Provide Resources',
            'description': 'Share mental health resources and counseling contact information'
        })
    elif overall_status == 'yellow':
        suggestions.append({
            'priority': 'medium',
            'action': 'Monitor Progress',
            'description': 'Continue monitoring wellness status over next week'
        })
        suggestions.append({
            'priority': 'medium',
            'action': 'Casual Check-in',
            'description': 'Have a brief, informal conversation to show support'
        })
    
    return suggestions