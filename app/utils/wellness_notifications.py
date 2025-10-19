# backend/app/utils/wellness_notifications.py
"""
Wellness Notification System
Handles alerts and notifications for mental health concerns
✨ UPDATED: Now includes email notification support
"""

from datetime import datetime, timedelta
import uuid


# ==================== ALERT GENERATION ====================

def check_and_send_alerts(user_id, level, content, db):
    """
    Check if alerts need to be sent based on wellness level
    ✨ UPDATED: Now sends emails for critical/high alerts
    
    Args:
        user_id: Student's user ID
        level: Wellness level (red, orange, yellow, green)
        content: Message/post content that triggered analysis
        db: Database connection
    """
    try:
        # Get user info
        user = db.users.find_one({'user_id': user_id})
        if not user:
            return
        
        # Check if we've already sent an alert recently (avoid spam)
        if should_throttle_alert(user_id, level, db):
            print(f"⏸️ Alert throttled for user {user_id} (level: {level})")
            return
        
        # Create alert based on level
        if level == 'red':
            send_critical_alert(user_id, user, content, db)
        elif level == 'orange':
            send_high_concern_alert(user_id, user, content, db)
        elif level == 'yellow':
            send_monitor_alert(user_id, user, content, db)
        
        # Log that we sent an alert
        log_alert_sent(user_id, level, db)
        
    except Exception as e:
        print(f"❌ Error sending alerts: {e}")


def should_throttle_alert(user_id, level, db):
    """
    Check if we should throttle alerts to avoid spam
    Returns True if we should NOT send alert
    """
    # Get last alert for this user
    last_alert = db.wellness_alerts.find_one(
        {'user_id': user_id, 'level': level},
        sort=[('timestamp', -1)]
    )
    
    if not last_alert:
        return False
    
    # Throttle periods (in hours)
    throttle_periods = {
        'red': 2,      # Send critical alerts max every 2 hours
        'orange': 6,   # Send high concern alerts max every 6 hours
        'yellow': 24   # Send monitor alerts max every 24 hours
    }
    
    time_since_last = datetime.utcnow() - last_alert['timestamp']
    throttle_hours = throttle_periods.get(level, 24)
    
    return time_since_last < timedelta(hours=throttle_hours)


def log_alert_sent(user_id, level, db):
    """Log that an alert was sent"""
    alert_log = {
        'alert_id': str(uuid.uuid4()),
        'user_id': user_id,
        'level': level,
        'timestamp': datetime.utcnow()
    }
    db.wellness_alerts.insert_one(alert_log)


# ==================== ALERT TYPES ====================

def send_critical_alert(user_id, user, content, db):
    """
    Send critical/emergency alert (RED level)
    ✨ UPDATED: Now sends emails to counselors
    """
    print(f"🚨 CRITICAL ALERT: User {user_id} ({user.get('name')}) - Immediate attention needed!")
    
    # Import email service (lazy import to avoid circular dependencies)
    try:
        from app.utils.notification_manager import create_notification_manager
        notif_manager = create_notification_manager(db)
        
        # Send wellness alert with email
        notif_manager.send_wellness_alert(
            student_id=user_id,
            level='red',
            content_preview=content[:200] if content else 'Crisis indicators detected',
            context_type='automated_detection'
        )
        
        print(f"✅ Critical alerts (with email) sent to staff members")
        
    except ImportError:
        print("⚠️ Email service not available, sending in-app notifications only")
        # Fallback to old method
        send_critical_alert_legacy(user_id, user, content, db)


def send_high_concern_alert(user_id, user, content, db):
    """
    Send high concern alert (ORANGE level)
    ✨ UPDATED: Now sends emails to counselors
    """
    print(f"⚠️ HIGH CONCERN: User {user_id} ({user.get('name')}) - Follow-up recommended")
    
    try:
        from app.utils.notification_manager import create_notification_manager
        notif_manager = create_notification_manager(db)
        
        # Send wellness alert with email
        notif_manager.send_wellness_alert(
            student_id=user_id,
            level='orange',
            content_preview=content[:200] if content else 'Concerning indicators detected',
            context_type='automated_detection'
        )
        
        print(f"✅ High concern alerts (with email) sent to counselors")
        
    except ImportError:
        print("⚠️ Email service not available, sending in-app notifications only")
        send_high_concern_alert_legacy(user_id, user, content, db)


def send_monitor_alert(user_id, user, content, db):
    """Send monitoring alert (YELLOW level) - In-app only, no email"""
    print(f"📊 MONITOR: User {user_id} ({user.get('name')}) - Check-in suggested")
    
    # Only send to admins for monitoring (no email)
    admins = list(db.users.find({'role': 'admin'}))
    
    for admin in admins:
        notification = {
            'notification_id': str(uuid.uuid4()),
            'recipient_id': admin['user_id'],
            'type': 'monitor_alert',
            'priority': 'normal',
            'student_id': user_id,
            'student_name': user.get('name', 'Unknown'),
            'level': 'yellow',
            'message': f"📊 Student {user.get('name')} may need support. Consider checking in.",
            'preview': content[:100] if content else 'Stress indicators detected',
            'timestamp': datetime.utcnow(),
            'read': False
        }
        db.notifications.insert_one(notification)
    
    print(f"✅ Monitor alerts sent to {len(admins)} admins")


# ==================== LEGACY METHODS (FALLBACK) ====================

def send_critical_alert_legacy(user_id, user, content, db):
    """Legacy critical alert without email"""
    counselors = list(db.users.find({'role': {'$in': ['teacher', 'counselor', 'admin']}}))
    
    for counselor in counselors:
        notification = {
            'notification_id': str(uuid.uuid4()),
            'recipient_id': counselor['user_id'],
            'type': 'critical_wellness_alert',
            'priority': 'urgent',
            'student_id': user_id,
            'student_name': user.get('name', 'Unknown'),
            'level': 'red',
            'message': f"🚨 URGENT: Student {user.get('name')} may be in crisis. Immediate intervention recommended.",
            'preview': content[:100] if content else 'Crisis indicators detected',
            'timestamp': datetime.utcnow(),
            'read': False
        }
        db.notifications.insert_one(notification)


def send_high_concern_alert_legacy(user_id, user, content, db):
    """Legacy high concern alert without email"""
    counselors = list(db.users.find({'role': {'$in': ['counselor', 'admin']}}))
    
    for counselor in counselors:
        notification = {
            'notification_id': str(uuid.uuid4()),
            'recipient_id': counselor['user_id'],
            'type': 'high_concern_alert',
            'priority': 'high',
            'student_id': user_id,
            'student_name': user.get('name', 'Unknown'),
            'level': 'orange',
            'message': f"⚠️ Student {user.get('name')} showing signs of high distress. Please reach out within 24 hours.",
            'preview': content[:100] if content else 'Concerning indicators detected',
            'timestamp': datetime.utcnow(),
            'read': False
        }
        db.notifications.insert_one(notification)


# ==================== STUDENT ENCOURAGEMENT ====================

def send_student_encouragement(user_id, level, db):
    """Send encouraging message to student based on their wellness level"""
    encouragement_messages = {
        'green': {
            'title': "You're doing great! 🌟",
            'message': "Keep up the positive momentum! Remember to maintain healthy habits.",
            'tips': [
                "Continue your regular sleep schedule",
                "Stay connected with friends and family",
                "Keep up with physical activity"
            ]
        },
        'yellow': {
            'title': "We're here for you 💙",
            'message': "It's normal to feel stressed sometimes. Take care of yourself.",
            'tips': [
                "Take short breaks between study sessions",
                "Practice deep breathing exercises",
                "Reach out to a friend or counselor if you need to talk"
            ]
        },
        'orange': {
            'title': "Your wellbeing matters 🤗",
            'message': "We noticed you might be going through a tough time. Please reach out for support.",
            'tips': [
                "Talk to a counselor - they're here to help",
                "Consider taking a mental health day if needed",
                "Don't hesitate to ask for help from professors or friends"
            ]
        },
        'red': {
            'title': "You're not alone ❤️",
            'message': "Please reach out to someone right now. Your safety and wellbeing are important.",
            'tips': [
                "Call campus counseling services immediately",
                "Reach out to a trusted friend or family member",
                "Crisis helpline: 988 (available 24/7)"
            ]
        }
    }
    
    message_data = encouragement_messages.get(level, encouragement_messages['yellow'])
    
    # Create notification for student
    notification = {
        'notification_id': str(uuid.uuid4()),
        'recipient_id': user_id,
        'type': 'wellness_encouragement',
        'priority': 'normal',
        'title': message_data['title'],
        'message': message_data['message'],
        'tips': message_data['tips'],
        'level': level,
        'timestamp': datetime.utcnow(),
        'read': False
    }
    
    db.notifications.insert_one(notification)
    print(f"💌 Encouragement sent to user {user_id}")


# ==================== NOTIFICATION RETRIEVAL ====================

def get_user_notifications(user_id, db, limit=10):
    """Get notifications for a user"""
    notifications = list(db.notifications.find(
        {'recipient_id': user_id}
    ).sort('timestamp', -1).limit(limit))
    
    formatted_notifications = []
    for notif in notifications:
        formatted_notifications.append({
            'notification_id': str(notif['notification_id']),
            'type': notif.get('type'),
            'priority': notif.get('priority'),
            'title': notif.get('title', ''),
            'message': notif.get('message', ''),
            'tips': notif.get('tips', []),
            'student_id': notif.get('student_id'),
            'student_name': notif.get('student_name'),
            'level': notif.get('level'),
            'preview': notif.get('preview'),
            'timestamp': notif['timestamp'].isoformat(),
            'read': notif.get('read', False)
        })
    
    return formatted_notifications


def mark_notification_read(notification_id, db):
    """Mark a notification as read"""
    db.notifications.update_one(
        {'notification_id': notification_id},
        {'$set': {'read': True}}
    )


def get_unread_count(user_id, db):
    """Get count of unread notifications"""
    return db.notifications.count_documents({
        'recipient_id': user_id,
        'read': False
    })


# ==================== DAILY WELLNESS SUMMARY ====================

def generate_daily_wellness_summary(db):
    """Generate daily summary of wellness status across all students"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get today's logs
    today_logs = list(db.mental_health_logs.find({
        'timestamp': {'$gte': today_start}
    }))
    
    if not today_logs:
        return None
    
    # Count by level
    level_counts = {'red': 0, 'orange': 0, 'yellow': 0, 'green': 0}
    unique_students = set()
    
    for log in today_logs:
        level = log.get('level', 'green')
        if level in level_counts:
            level_counts[level] += 1
        unique_students.add(log.get('user_id'))
    
    summary = {
        'date': today_start.strftime('%Y-%m-%d'),
        'total_checks': len(today_logs),
        'unique_students': len(unique_students),
        'level_breakdown': level_counts,
        'critical_students': level_counts['red'],
        'concerning_students': level_counts['orange']
    }
    
    return summary


# ==================== EXPORT FUNCTIONS ====================

__all__ = [
    'check_and_send_alerts',
    'send_student_encouragement',
    'get_user_notifications',
    'mark_notification_read',
    'get_unread_count',
    'generate_daily_wellness_summary'
]