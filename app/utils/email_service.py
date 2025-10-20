# backend/app/utils/email_service.py
"""
Email Service - Complete with all required functions
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
from datetime import datetime

# Email configuration (from environment variables)
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', SMTP_USERNAME)
SENDER_NAME = os.getenv('SENDER_NAME', 'AcadWell')


def send_email(to_email, subject, html_content, plain_text_content=None, retry_count=2):
    """
    Send an email with retry logic and timeout
    
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
    else:
        text_part = MIMEText("Please view this email in HTML format", 'plain')
        message.attach(text_part)
    
    # Add HTML version
    html_part = MIMEText(html_content, 'html')
    message.attach(html_part)
    
    # Retry logic
    for attempt in range(retry_count):
        try:
            print(f"📧 Attempting to send email to {to_email} (attempt {attempt + 1}/{retry_count})")
            
            # Connect to SMTP server with timeout
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
                server.starttls()  # Enable TLS encryption
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
            
            print(f"✅ Email sent successfully to {to_email}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP Authentication failed: {e}")
            print("⚠️ Check SMTP_USERNAME and SMTP_PASSWORD in environment variables")
            return False
            
        except smtplib.SMTPException as e:
            print(f"⚠️ SMTP error on attempt {attempt + 1}/{retry_count}: {e}")
            if attempt < retry_count - 1:
                wait_time = 2 ** attempt
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"❌ Failed to send email after {retry_count} attempts")
                return False
                
        except TimeoutError as e:
            print(f"⚠️ SMTP connection timeout on attempt {attempt + 1}/{retry_count}: {e}")
            if attempt < retry_count - 1:
                print("⏳ Retrying...")
                time.sleep(1)
            else:
                print(f"❌ Email send failed - connection timeout")
                return False
                
        except Exception as e:
            print(f"❌ Unexpected error sending email: {e}")
            return False
    
    return False


def send_wellness_alert_email(to_email, student_name, level, preview_text, post_or_message_link=None):
    """Send wellness alert email to counselors/teachers"""
    try:
        level_text = 'CRITICAL' if level == 'red' else 'HIGH CONCERN'
        level_color = '#dc2626' if level == 'red' else '#ea580c'
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: {level_color};">🚨 {level_text}: Student Wellness Alert</h2>
                <p>Student <strong>{student_name}</strong> may need immediate attention.</p>
                <p><em>Preview:</em> {preview_text[:200]}...</p>
                <p>Please check the wellness dashboard for more details.</p>
                <hr>
                <p style="color: #666; font-size: 12px;">AcadWell Wellness Monitoring System</p>
            </body>
        </html>
        """
        
        subject = f"🚨 {level_text}: Wellness Alert for {student_name}"
        
        return send_email(to_email, subject, html_content)
    except Exception as e:
        print(f"❌ Error sending wellness alert email: {e}")
        return False


def send_answer_accepted_email(to_email, answerer_name, question_title, post_link, points_earned=10):
    """Send notification email when answer is accepted"""
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #16a34a;">🎉 Your Answer Was Accepted!</h2>
                <p>Hi <strong>{answerer_name}</strong>,</p>
                <p>Great news! Your answer on "<strong>{question_title}</strong>" was accepted as the best answer!</p>
                <p>You earned <strong>{points_earned} points</strong>! ⭐</p>
                <p><a href="{post_link}" style="background: #16a34a; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">View Your Answer</a></p>
                <hr>
                <p style="color: #666; font-size: 12px;">Keep up the great work helping fellow students!</p>
            </body>
        </html>
        """
        
        subject = f"🎉 Your Answer Was Accepted! (+{points_earned} points)"
        
        return send_email(to_email, subject, html_content)
    except Exception as e:
        print(f"❌ Error sending answer accepted email: {e}")
        return False


def send_welcome_email(to_email, user_name, user_role):
    """Send welcome email to new users"""
    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Welcome to AcadWell! 🎓</h1>
                </div>
                <div style="padding: 30px;">
                    <h2>Hi {user_name},</h2>
                    <p>Welcome to AcadWell - your comprehensive platform for academic success and wellbeing!</p>
                    <p>Get started by logging into your dashboard.</p>
                    <p style="margin-top: 30px;">Best regards,<br><strong>The AcadWell Team</strong></p>
                </div>
                <div style="background: #f3f4f6; padding: 20px; text-align: center; font-size: 12px; color: #666;">
                    <p>© {datetime.utcnow().year} AcadWell. All rights reserved.</p>
                </div>
            </body>
        </html>
        """
        
        subject = f"Welcome to AcadWell, {user_name}!"
        
        return send_email(to_email, subject, html_content)
    except Exception as e:
        print(f"❌ Error sending welcome email: {e}")
        return False


def send_daily_wellness_summary_email(to_email, teacher_name, summary_data):
    """Send daily wellness summary to teachers/counselors"""
    try:
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
                </div>
                <div style="background: #f3f4f6; padding: 20px; text-align: center; font-size: 12px; color: #666;">
                    <p>© {datetime.utcnow().year} AcadWell Wellness Monitoring</p>
                </div>
            </body>
        </html>
        """
        
        subject = f"Daily Wellness Summary - {datetime.utcnow().strftime('%B %d, %Y')}"
        
        return send_email(to_email, subject, html_content)
    except Exception as e:
        print(f"❌ Error sending wellness summary email: {e}")
        return False


def log_email_sent(db, recipient_email, email_type, subject, success):
    """Log email sending attempt to database"""
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
    """Check if similar email was sent recently to avoid spam"""
    try:
        from datetime import timedelta
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