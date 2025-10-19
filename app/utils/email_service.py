# backend/app/utils/email_service.py
"""
Email Service
Handles sending emails using SMTP with retry logic and templates
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
import os
from datetime import datetime, timedelta
import time

# Email configuration (from environment variables)
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', SMTP_USERNAME)
SENDER_NAME = os.getenv('SENDER_NAME', 'AcadWell')


def send_email(to_email, subject, html_content, plain_text_content=None, retry_count=3):
    """
    Send an email with retry logic
    
    Args:
        to_email (str): Recipient email address
        subject (str): Email subject
        html_content (str): HTML email content
        plain_text_content (str): Plain text fallback (optional)
        retry_count (int): Number of retry attempts
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    
    # Check if email is configured
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("⚠️ Email not configured. Set SMTP_USERNAME and SMTP_PASSWORD in .env")
        return False
    
    # Create message
    message = MIMEMultipart('alternative')
    message['From'] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    message['To'] = to_email
    message['Subject'] = subject
    
    # Add plain text version (fallback)
    if plain_text_content:
        text_part = MIMEText(plain_text_content, 'plain')
        message.attach(text_part)
    
    # Add HTML version
    html_part = MIMEText(html_content, 'html')
    message.attach(html_part)
    
    # Retry logic
    for attempt in range(retry_count):
        try:
            # Connect to SMTP server
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()  # Enable TLS encryption
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
            
            print(f"✅ Email sent successfully to {to_email}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            print(f"❌ SMTP Authentication failed. Check credentials.")
            return False
            
        except smtplib.SMTPException as e:
            print(f"⚠️ SMTP error on attempt {attempt + 1}/{retry_count}: {e}")
            if attempt < retry_count - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                print(f"❌ Failed to send email after {retry_count} attempts")
                return False
                
        except Exception as e:
            print(f"❌ Unexpected error sending email: {e}")
            return False
    
    return False


def render_email_template(template_path, context):
    """
    Render an email template with context data
    
    Args:
        template_path (str): Path to template file
        context (dict): Variables to inject into template
    
    Returns:
        str: Rendered HTML content
    """
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        template = Template(template_content)
        return template.render(**context)
        
    except FileNotFoundError:
        print(f"❌ Template not found: {template_path}")
        return None
    except Exception as e:
        print(f"❌ Error rendering template: {e}")
        return None


def send_wellness_alert_email(to_email, student_name, level, preview_text, post_or_message_link=None):
    """
    Send critical wellness alert email to counselors/teachers
    
    Args:
        to_email (str): Recipient email
        student_name (str): Name of student
        level (str): Wellness level (red, orange)
        preview_text (str): Preview of concerning content
        post_or_message_link (str): Optional link to content
    """
    
    template_path = 'backend/templates/emails/wellness_alert.html'
    
    context = {
        'student_name': student_name,
        'level': level,
        'level_text': 'CRITICAL' if level == 'red' else 'HIGH CONCERN',
        'level_color': '#dc2626' if level == 'red' else '#ea580c',
        'preview_text': preview_text,
        'link': post_or_message_link,
        'timestamp': datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC'),
        'current_year': datetime.utcnow().year
    }
    
    html_content = render_email_template(template_path, context)
    
    if not html_content:
        # Fallback to simple HTML
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: {context['level_color']};">🚨 {context['level_text']}: Student Wellness Alert</h2>
                <p>Student <strong>{student_name}</strong> may need immediate attention.</p>
                <p><em>Preview:</em> {preview_text[:200]}...</p>
                <p>Please check the wellness dashboard for more details.</p>
                <hr>
                <p style="color: #666; font-size: 12px;">AcadWell Wellness Monitoring System</p>
            </body>
        </html>
        """
    
    subject = f"🚨 {context['level_text']}: Wellness Alert for {student_name}"
    
    plain_text = f"""
    {context['level_text']}: Student Wellness Alert
    
    Student: {student_name}
    Level: {level.upper()}
    Time: {context['timestamp']}
    
    Preview: {preview_text[:200]}...
    
    Please check the wellness dashboard immediately for more details.
    
    ---
    AcadWell Wellness Monitoring System
    """
    
    return send_email(to_email, subject, html_content, plain_text)


def send_answer_accepted_email(to_email, answerer_name, question_title, post_link, points_earned=10):
    """
    Send notification email when answer is accepted
    
    Args:
        to_email (str): Recipient email
        answerer_name (str): Name of person who answered
        question_title (str): Title of the question
        post_link (str): Link to the post
        points_earned (int): Points awarded
    """
    
    template_path = 'backend/templates/emails/answer_accepted.html'
    
    context = {
        'answerer_name': answerer_name,
        'question_title': question_title,
        'post_link': post_link,
        'points_earned': points_earned,
        'timestamp': datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC'),
        'current_year': datetime.utcnow().year
    }
    
    html_content = render_email_template(template_path, context)
    
    if not html_content:
        # Fallback to simple HTML
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #16a34a;">🎉 Your Answer Was Accepted!</h2>
                <p>Hi <strong>{answerer_name}</strong>,</p>
                <p>Great news! Your answer on "<strong>{question_title}</strong>" was accepted as the best answer!</p>
                <p>You earned <strong>{points_earned} points</strong>! 🌟</p>
                <p><a href="{post_link}" style="background: #16a34a; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">View Your Answer</a></p>
                <hr>
                <p style="color: #666; font-size: 12px;">Keep up the great work helping fellow students!</p>
            </body>
        </html>
        """
    
    subject = f"🎉 Your Answer Was Accepted! (+{points_earned} points)"
    
    plain_text = f"""
    Your Answer Was Accepted!
    
    Hi {answerer_name},
    
    Great news! Your answer on "{question_title}" was accepted as the best answer!
    
    You earned {points_earned} points!
    
    View your answer: {post_link}
    
    Keep up the great work helping fellow students!
    
    ---
    AcadWell Community
    """
    
    return send_email(to_email, subject, html_content, plain_text)


def send_welcome_email(to_email, user_name, user_role):
    """
    Send welcome email to new users
    
    Args:
        to_email (str): User's email
        user_name (str): User's name
        user_role (str): User's role (student, teacher, etc.)
    """
    
    subject = f"Welcome to AcadWell, {user_name}!"
    
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0;">Welcome to AcadWell! 🎓</h1>
            </div>
            <div style="padding: 30px;">
                <h2>Hi {user_name},</h2>
                <p>Welcome to AcadWell - your comprehensive platform for academic success and wellbeing!</p>
                
                {'<p>As a <strong>student</strong>, you can:</p><ul><li>Track your mood and wellbeing</li><li>Ask questions and get help from peers</li><li>Access mental health resources</li><li>Connect with counselors when needed</li></ul>' if user_role == 'student' else ''}
                
                {'<p>As a <strong>teacher</strong>, you can:</p><ul><li>Monitor student wellness</li><li>Respond to student questions</li><li>Identify students who need support</li><li>Provide timely interventions</li></ul>' if user_role == 'teacher' else ''}
                
                <p>Get started by logging into your dashboard!</p>
                
                <p style="margin-top: 30px;">Best regards,<br><strong>The AcadWell Team</strong></p>
            </div>
            <div style="background: #f3f4f6; padding: 20px; text-align: center; font-size: 12px; color: #666;">
                <p>© {datetime.utcnow().year} AcadWell. All rights reserved.</p>
            </div>
        </body>
    </html>
    """
    
    plain_text = f"""
    Welcome to AcadWell!
    
    Hi {user_name},
    
    Welcome to AcadWell - your comprehensive platform for academic success and wellbeing!
    
    Get started by logging into your dashboard.
    
    Best regards,
    The AcadWell Team
    """
    
    return send_email(to_email, subject, html_content, plain_text)


def send_daily_wellness_summary_email(to_email, teacher_name, summary_data):
    """
    Send daily wellness summary to teachers/counselors
    
    Args:
        to_email (str): Recipient email
        teacher_name (str): Teacher's name
        summary_data (dict): Summary statistics
    """
    
    subject = f"Daily Wellness Summary - {datetime.utcnow().strftime('%B %d, %Y')}"
    
    critical = summary_data.get('critical_students', 0)
    concerning = summary_data.get('concerning_students', 0)
    total = summary_data.get('total_students', 0)
    
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #3b82f6; padding: 20px; color: white;">
                <h2 style="margin: 0;">Daily Wellness Summary 📊</h2>
                <p style="margin: 5px 0 0 0;">{datetime.utcnow().strftime('%B %d, %Y')}</p>
            </div>
            <div style="padding: 30px;">
                <p>Hi {teacher_name},</p>
                <p>Here's your daily wellness summary:</p>
                
                <div style="background: #fee2e2; border-left: 4px solid #dc2626; padding: 15px; margin: 15px 0;">
                    <strong style="color: #dc2626;">🚨 Critical: {critical} students</strong>
                    <p style="margin: 5px 0 0 0; font-size: 14px;">Require immediate attention</p>
                </div>
                
                <div style="background: #fed7aa; border-left: 4px solid #ea580c; padding: 15px; margin: 15px 0;">
                    <strong style="color: #ea580c;">⚠️ Concerning: {concerning} students</strong>
                    <p style="margin: 5px 0 0 0; font-size: 14px;">Should be contacted within 24 hours</p>
                </div>
                
                <div style="background: #dbeafe; border-left: 4px solid #3b82f6; padding: 15px; margin: 15px 0;">
                    <strong style="color: #3b82f6;">👥 Total Students Monitored: {total}</strong>
                </div>
                
                <p style="margin-top: 30px;">
                    <a href="http://localhost:3000/teacher/wellness" 
                       style="background: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                        View Full Dashboard
                    </a>
                </p>
            </div>
            <div style="background: #f3f4f6; padding: 20px; text-align: center; font-size: 12px; color: #666;">
                <p>© {datetime.utcnow().year} AcadWell Wellness Monitoring</p>
            </div>
        </body>
    </html>
    """
    
    plain_text = f"""
    Daily Wellness Summary - {datetime.utcnow().strftime('%B %d, %Y')}
    
    Hi {teacher_name},
    
    Here's your daily wellness summary:
    
    🚨 CRITICAL: {critical} students - Require immediate attention
    ⚠️ CONCERNING: {concerning} students - Contact within 24 hours
    👥 TOTAL MONITORED: {total} students
    
    View full dashboard: http://localhost:3000/teacher/wellness
    
    ---
    AcadWell Wellness Monitoring
    """
    
    return send_email(to_email, subject, html_content, plain_text)


def log_email_sent(db, recipient_email, email_type, subject, success):
    """
    Log email sending attempt to database
    
    Args:
        db: Database connection
        recipient_email (str): Recipient's email
        email_type (str): Type of email (wellness_alert, answer_accepted, etc.)
        subject (str): Email subject
        success (bool): Whether email was sent successfully
    """
    try:
        email_log = {
            'log_id': str(datetime.utcnow().timestamp()),
            'recipient_email': recipient_email,
            'email_type': email_type,
            'subject': subject,
            'success': success,
            'timestamp': datetime.utcnow(),
            'retry_count': 0
        }
        
        db.email_notifications.insert_one(email_log)
        
    except Exception as e:
        print(f"❌ Error logging email: {e}")


def check_email_sent_recently(db, recipient_email, email_type, hours=24):
    """
    Check if similar email was sent recently to avoid spam
    
    Args:
        db: Database connection
        recipient_email (str): Recipient's email
        email_type (str): Type of email
        hours (int): Time window in hours
    
    Returns:
        bool: True if email was sent recently
    """
    try:
        time_threshold = datetime.utcnow() - timedelta(hours=hours)
        
        recent_email = db.email_notifications.find_one({
            'recipient_email': recipient_email,
            'email_type': email_type,
            'timestamp': {'$gte': time_threshold},
            'success': True
        })
        
        return recent_email is not None
        
    except Exception as e:
        print(f"❌ Error checking email history: {e}")
        return False


# Export functions
__all__ = [
    'send_email',
    'send_wellness_alert_email',
    'send_answer_accepted_email',
    'send_welcome_email',
    'send_daily_wellness_summary_email',
    'log_email_sent',
    'check_email_sent_recently'
]