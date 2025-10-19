# backend/app/utils/notification_manager.py
"""
Notification Manager
Unified system for handling both in-app and email notifications
"""

from datetime import datetime, timedelta
import uuid
from app.utils.email_service import (
    send_wellness_alert_email,
    send_answer_accepted_email,
    log_email_sent,
    check_email_sent_recently
)


class NotificationManager:
    """Manages all types of notifications (in-app and email)"""
    
    def __init__(self, db):
        self.db = db
    
    def send_notification(self, user_id, notification_type, title, message, 
                         related_id=None, priority='normal', send_email=False, 
                         email_context=None):
        """
        Send a unified notification (in-app + optional email)
        
        Args:
            user_id (str): Recipient user ID
            notification_type (str): Type of notification
            title (str): Notification title
            message (str): Notification message
            related_id (str): Related entity ID (post_id, reply_id, etc.)
            priority (str): 'urgent', 'high', 'normal', 'low'
            send_email (bool): Whether to send email notification
            email_context (dict): Additional context for email (if send_email=True)
        
        Returns:
            dict: Notification details
        """
        
        # Create in-app notification
        notification = {
            'notification_id': str(uuid.uuid4()),
            'recipient_id': user_id,
            'type': notification_type,
            'priority': priority,
            'title': title,
            'message': message,
            'related_id': related_id,
            'read': False,
            'timestamp': datetime.utcnow(),
            'created_at': datetime.utcnow()
        }
        
        # Add type-specific fields
        if email_context:
            notification.update(email_context)
        
        # Insert into database
        self.db.notifications.insert_one(notification)
        
        print(f"✅ In-app notification created for user {user_id}: {title}")
        
        # Send email if requested
        email_sent = False
        if send_email:
            user = self.db.users.find_one({'user_id': user_id})
            if user and user.get('email'):
                # Check user's email preferences
                profile = self.db.profiles.find_one({'user_id': user_id})
                email_enabled = True
                
                if profile:
                    email_prefs = profile.get('emailNotifications', {})
                    email_enabled = email_prefs.get(notification_type, True)
                
                if email_enabled:
                    email_sent = self._send_email_notification(
                        user,
                        notification_type,
                        title,
                        message,
                        email_context
                    )
        
        return {
            'notification_id': notification['notification_id'],
            'in_app_sent': True,
            'email_sent': email_sent
        }
    
    def _send_email_notification(self, user, notification_type, title, message, context):
        """
        Internal method to send email notifications
        
        Args:
            user (dict): User document
            notification_type (str): Type of notification
            title (str): Notification title
            message (str): Notification message
            context (dict): Additional context
        
        Returns:
            bool: True if email sent successfully
        """
        
        user_email = user.get('email')
        user_name = user.get('name', 'User')
        
        # Check if we've sent similar email recently (anti-spam)
        if notification_type in ['wellness_alert', 'critical_wellness_alert']:
            if check_email_sent_recently(self.db, user_email, notification_type, hours=2):
                print(f"⏸️ Email throttled for {user_email} ({notification_type})")
                return False
        
        email_sent = False
        
        try:
            # Send appropriate email based on type
            if notification_type == 'critical_wellness_alert':
                email_sent = send_wellness_alert_email(
                    to_email=user_email,
                    student_name=context.get('student_name', 'Student'),
                    level='red',
                    preview_text=context.get('preview', message),
                    post_or_message_link=context.get('link')
                )
            
            elif notification_type == 'high_concern_alert':
                email_sent = send_wellness_alert_email(
                    to_email=user_email,
                    student_name=context.get('student_name', 'Student'),
                    level='orange',
                    preview_text=context.get('preview', message),
                    post_or_message_link=context.get('link')
                )
            
            elif notification_type == 'accepted_answer':
                email_sent = send_answer_accepted_email(
                    to_email=user_email,
                    answerer_name=user_name,
                    question_title=context.get('question_title', 'Question'),
                    post_link=context.get('post_link', '#'),
                    points_earned=context.get('points_earned', 10)
                )
            
            # Log email attempt
            log_email_sent(
                self.db,
                user_email,
                notification_type,
                title,
                email_sent
            )
            
        except Exception as e:
            print(f"❌ Error sending email to {user_email}: {e}")
        
        return email_sent
    
    def send_wellness_alert(self, student_id, level, content_preview, context_type='unknown'):
        """
        Send wellness alert to all counselors and teachers
        
        Args:
            student_id (str): Student's user ID
            level (str): Wellness level (red, orange, yellow)
            content_preview (str): Preview of concerning content
            context_type (str): Where alert originated (post, message, mood_log)
        """
        
        # Get student info
        student = self.db.users.find_one({'user_id': student_id})
        if not student:
            return
        
        student_name = student.get('name', 'Unknown Student')
        
        # Determine urgency and recipients
        if level == 'red':
            notification_type = 'critical_wellness_alert'
            title = f"🚨 CRITICAL: Wellness Alert for {student_name}"
            priority = 'urgent'
            send_email = True
            # Send to teachers, counselors, and admins
            recipient_roles = ['teacher', 'counselor', 'admin']
        elif level == 'orange':
            notification_type = 'high_concern_alert'
            title = f"⚠️ HIGH CONCERN: Wellness Alert for {student_name}"
            priority = 'high'
            send_email = True
            # Send to counselors and admins
            recipient_roles = ['counselor', 'admin']
        else:
            notification_type = 'monitor_alert'
            title = f"📊 Monitor: Wellness Check for {student_name}"
            priority = 'normal'
            send_email = False
            # Only send to admins
            recipient_roles = ['admin']
        
        message = f"Student {student_name} may need attention. Context: {context_type}"
        
        # Get all staff members
        staff_members = self.db.users.find({'role': {'$in': recipient_roles}})
        
        alert_count = 0
        for staff in staff_members:
            email_context = {
                'student_id': student_id,
                'student_name': student_name,
                'level': level,
                'preview': content_preview,
                'context_type': context_type,
                'link': f"http://localhost:3000/wellness/student/{student_id}"
            }
            
            self.send_notification(
                user_id=staff['user_id'],
                notification_type=notification_type,
                title=title,
                message=message,
                related_id=student_id,
                priority=priority,
                send_email=send_email,
                email_context=email_context
            )
            alert_count += 1
        
        print(f"✅ Wellness alert sent to {alert_count} staff members for student {student_name}")
    
    def send_answer_accepted_notification(self, answer_author_id, question_title, post_id, points_earned=10):
        """
        Send notification when answer is accepted
        
        Args:
            answer_author_id (str): User ID of answer author
            question_title (str): Title of the question
            post_id (str): Post ID
            points_earned (int): Points awarded
        """
        
        title = "🎉 Your Answer Was Accepted!"
        message = f"Your answer on '{question_title[:50]}...' was accepted. You earned {points_earned} points!"
        
        email_context = {
            'question_title': question_title,
            'post_link': f"http://localhost:3000/community/post/{post_id}",
            'points_earned': points_earned
        }
        
        # Check if user has email notifications enabled
        profile = self.db.profiles.find_one({'user_id': answer_author_id})
        send_email = True
        
        if profile:
            email_prefs = profile.get('emailNotifications', {})
            send_email = email_prefs.get('accepted_answer', True)
        
        self.send_notification(
            user_id=answer_author_id,
            notification_type='accepted_answer',
            title=title,
            message=message,
            related_id=post_id,
            priority='normal',
            send_email=send_email,
            email_context=email_context
        )
    
    def send_reply_notification(self, post_author_id, replier_name, post_title, post_id):
        """
        Send notification when someone replies to a post
        
        Args:
            post_author_id (str): Original post author's user ID
            replier_name (str): Name of person who replied
            post_title (str): Title of post
            post_id (str): Post ID
        """
        
        title = "New Reply on Your Post"
        message = f"{replier_name} replied to your post: {post_title[:50]}..."
        
        self.send_notification(
            user_id=post_author_id,
            notification_type='reply',
            title=title,
            message=message,
            related_id=post_id,
            priority='normal',
            send_email=False
        )
    
    def send_encouragement(self, user_id, level, mood=None):
        """
        Send encouraging message to student based on wellness level
        
        Args:
            user_id (str): Student's user ID
            level (str): Wellness level
            mood (str): Optional mood
        """
        
        encouragement_data = {
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
                    "Don't hesitate to ask for help"
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
        
        data = encouragement_data.get(level, encouragement_data['yellow'])
        
        notification = {
            'notification_id': str(uuid.uuid4()),
            'recipient_id': user_id,
            'type': 'wellness_encouragement',
            'priority': 'normal',
            'title': data['title'],
            'message': data['message'],
            'tips': data['tips'],
            'level': level,
            'read': False,
            'timestamp': datetime.utcnow()
        }
        
        self.db.notifications.insert_one(notification)
        print(f"💌 Encouragement sent to user {user_id} (level: {level})")
    
    def get_user_notifications(self, user_id, limit=20, unread_only=False):
        """
        Get notifications for a user
        
        Args:
            user_id (str): User ID
            limit (int): Maximum number of notifications
            unread_only (bool): Only return unread notifications
        
        Returns:
            list: List of notifications
        """
        
        query = {'recipient_id': user_id}
        if unread_only:
            query['read'] = False
        
        notifications = list(self.db.notifications.find(query)
                           .sort('timestamp', -1)
                           .limit(limit))
        
        formatted = []
        for notif in notifications:
            formatted.append({
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
                'related_id': notif.get('related_id'),
                'timestamp': notif['timestamp'].isoformat(),
                'read': notif.get('read', False)
            })
        
        return formatted
    
    def mark_as_read(self, notification_id, user_id):
        """
        Mark notification as read
        
        Args:
            notification_id (str): Notification ID
            user_id (str): User ID (for security check)
        
        Returns:
            bool: True if successful
        """
        
        result = self.db.notifications.update_one(
            {
                'notification_id': notification_id,
                'recipient_id': user_id
            },
            {'$set': {'read': True}}
        )
        
        return result.modified_count > 0
    
    def mark_all_as_read(self, user_id):
        """
        Mark all notifications as read for a user
        
        Args:
            user_id (str): User ID
        
        Returns:
            int: Number of notifications marked as read
        """
        
        result = self.db.notifications.update_many(
            {'recipient_id': user_id, 'read': False},
            {'$set': {'read': True}}
        )
        
        return result.modified_count
    
    def get_unread_count(self, user_id):
        """
        Get count of unread notifications
        
        Args:
            user_id (str): User ID
        
        Returns:
            int: Number of unread notifications
        """
        
        return self.db.notifications.count_documents({
            'recipient_id': user_id,
            'read': False
        })
    
    def delete_notification(self, notification_id, user_id):
        """
        Delete a notification
        
        Args:
            notification_id (str): Notification ID
            user_id (str): User ID (for security check)
        
        Returns:
            bool: True if successful
        """
        
        result = self.db.notifications.delete_one({
            'notification_id': notification_id,
            'recipient_id': user_id
        })
        
        return result.deleted_count > 0
    
    def cleanup_old_notifications(self, days=30):
        """
        Delete notifications older than specified days
        
        Args:
            days (int): Number of days to keep
        
        Returns:
            int: Number of notifications deleted
        """
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        result = self.db.notifications.delete_many({
            'timestamp': {'$lt': cutoff_date},
            'read': True  # Only delete read notifications
        })
        
        print(f"🧹 Cleaned up {result.deleted_count} old notifications")
        return result.deleted_count
    
    def send_daily_summary_to_teachers(self):
        """
        Send daily wellness summary to all teachers/counselors
        Typically called by a scheduled job (cron)
        """
        
        try:
            from app.utils.wellness_notifications import generate_daily_wellness_summary
            
            summary = generate_daily_wellness_summary(self.db)
            
            if not summary:
                print("ℹ️ No wellness data for daily summary")
                return
            
            # Get all teachers and counselors
            staff = list(self.db.users.find({'role': {'$in': ['teacher', 'counselor']}}))
            
            for staff_member in staff:
                # Check if they want daily summaries
                profile = self.db.profiles.find_one({'user_id': staff_member['user_id']})
                if profile:
                    email_prefs = profile.get('emailNotifications', {})
                    if not email_prefs.get('daily_summary', False):
                        continue  # Skip if they don't want daily summaries
                
                # Send email
                from app.utils.email_service import send_daily_wellness_summary_email
                
                send_daily_wellness_summary_email(
                    to_email=staff_member.get('email'),
                    teacher_name=staff_member.get('name', 'Educator'),
                    summary_data={
                        'critical_students': summary.get('critical_students', 0),
                        'concerning_students': summary.get('concerning_students', 0),
                        'total_students': summary.get('unique_students', 0)
                    }
                )
            
            print(f"✅ Daily summaries sent to {len(staff)} staff members")
            
        except Exception as e:
            print(f"❌ Error sending daily summaries: {e}")
    
    def send_bulk_notification(self, user_ids, notification_type, title, message, **kwargs):
        """
        Send notification to multiple users at once
        
        Args:
            user_ids (list): List of user IDs
            notification_type (str): Type of notification
            title (str): Notification title
            message (str): Notification message
            **kwargs: Additional parameters for send_notification
        
        Returns:
            dict: Summary of sent notifications
        """
        
        success_count = 0
        failure_count = 0
        
        for user_id in user_ids:
            try:
                self.send_notification(
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    **kwargs
                )
                success_count += 1
            except Exception as e:
                print(f"❌ Failed to send notification to {user_id}: {e}")
                failure_count += 1
        
        return {
            'total': len(user_ids),
            'success': success_count,
            'failure': failure_count
        }


# Factory function to create NotificationManager instance
def create_notification_manager(db):
    """Create a NotificationManager instance"""
    return NotificationManager(db)


# Export
__all__ = [
    'NotificationManager',
    'create_notification_manager'
]