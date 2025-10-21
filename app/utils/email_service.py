# backend/app/utils/email_service.py
"""
Email Service - SendGrid API (Works on Render free tier)
Uses SendGrid HTTP API instead of SMTP to bypass port restrictions
"""

import os
from datetime import datetime, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

# Email configuration
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY', '')
FROM_EMAIL = os.getenv('FROM_EMAIL', 'acadwellteam@gmail.com')
FROM_NAME = os.getenv('FROM_NAME', 'AcadWell Team')
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'true').lower() == 'true'
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://acadwell-frontend.vercel.app')

# Development mode - override recipient for testing
DEV_EMAIL_OVERRIDE = os.getenv('DEV_EMAIL_OVERRIDE', None)
IS_DEVELOPMENT = os.getenv('FLASK_ENV', 'production') == 'development'


def send_email(to_email, subject, html_content, plain_text_content=None, retry_count=2):
    """
    Send email using SendGrid API (HTTP-based)
    
    Args:
        to_email (str): Recipient email address
        subject (str): Email subject
        html_content (str): HTML email content
        plain_text_content (str): Plain text fallback (optional)
        retry_count (int): Number of retry attempts
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    
    # Check if email is enabled
    if not EMAIL_ENABLED:
        print("⚠️ Email sending is disabled in environment")
        return False
    
    # Check if API key is configured
    if not SENDGRID_API_KEY:
        print("⚠️ SENDGRID_API_KEY not configured in environment variables")
        print("📧 To enable emails: Set SENDGRID_API_KEY in .env or Render dashboard")
        return False
    
    # Development mode: Override recipient
    original_recipient = to_email
    if IS_DEVELOPMENT and DEV_EMAIL_OVERRIDE:
        print(f"🔧 DEV MODE: Redirecting email from {to_email} to {DEV_EMAIL_OVERRIDE}")
        to_email = DEV_EMAIL_OVERRIDE
        # Add original recipient info to subject
        subject = f"[DEV: {original_recipient}] {subject}"
    
    try:
        print(f"📧 Sending email to {to_email} via SendGrid API")
        
        # Create SendGrid message
        message = Mail(
            from_email=Email(FROM_EMAIL, FROM_NAME),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_content)
        )
        
        # Add plain text if provided
        if plain_text_content:
            message.plain_text_content = Content("text/plain", plain_text_content)
        
        # Send via SendGrid API
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        
        if response.status_code in [200, 201, 202]:
            print(f"✅ Email sent successfully to {to_email}")
            if IS_DEVELOPMENT and DEV_EMAIL_OVERRIDE:
                print(f"   Original recipient: {original_recipient}")
            return True
        else:
            print(f"❌ Email sending failed: {response.status_code}")
            print(f"Response body: {response.body}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return False


def send_verification_email(to_email, user_name, verification_token):
    """Send email verification link"""
    try:
        verification_link = f"{FRONTEND_URL}/verify-email?token={verification_token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 8px; margin-bottom: 30px; }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .content {{ color: #374151; line-height: 1.6; }}
                .button {{ display: inline-block; background-color: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; margin: 20px 0; font-weight: 600; }}
                .button:hover {{ background-color: #5a67d8; }}
                .code {{ background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 15px 0; word-break: break-all; font-family: monospace; font-size: 12px; }}
                .warning {{ background-color: #fef3c7; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #f59e0b; }}
                .footer {{ text-align: center; color: #6b7280; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div style="font-size: 48px; margin-bottom: 10px;">✉️</div>
                    <h1>Verify Your Email</h1>
                </div>
                <div class="content">
                    <p style="font-size: 16px;">Hi <strong>{user_name}</strong>,</p>
                    <p>Welcome to AcadWell! Please verify your email address to complete your registration.</p>
                    <p style="text-align: center;">
                        <a href="{verification_link}" class="button">Verify Email Address</a>
                    </p>
                    <p style="color: #6b7280; font-size: 14px; text-align: center;">Or copy and paste this link into your browser:</p>
                    <div class="code">{verification_link}</div>
                    <div class="warning">
                        <strong>⏰ Link expires in 24 hours</strong>
                        <p style="margin: 8px 0 0 0; font-size: 14px;">Make sure to verify your email within this time period.</p>
                    </div>
                    <p style="color: #6b7280; font-size: 14px; margin-top: 25px;">
                        <strong>Didn't create this account?</strong> If you didn't sign up for AcadWell, please ignore this email.
                    </p>
                </div>
                <div class="footer">
                    <p><strong>AcadWell Team</strong></p>
                    <p>© {datetime.utcnow().year} AcadWell. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_text = f"""
        Hi {user_name},
        
        Welcome to AcadWell! Please verify your email address to complete your registration.
        
        Click here to verify: {verification_link}
        
        This link expires in 24 hours.
        
        If you didn't create this account, please ignore this email.
        
        ---
        AcadWell Team
        """
        
        return send_email(
            to_email=to_email,
            subject="Verify Your AcadWell Account",
            html_content=html_content,
            plain_text_content=plain_text
        )
        
    except Exception as e:
        print(f"❌ Error sending verification email: {e}")
        return False


def send_registration_confirmation_email(to_email, user_name, role):
    """Send registration confirmation email"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 30px; text-align: center; border-radius: 8px; margin-bottom: 30px; }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .content {{ color: #374151; line-height: 1.6; }}
                .button {{ display: inline-block; background-color: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; margin: 20px 0; font-weight: 600; }}
                .button:hover {{ background-color: #059669; }}
                .footer {{ text-align: center; color: #6b7280; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div style="font-size: 48px; margin-bottom: 10px;">🎉</div>
                    <h1>Welcome to AcadWell!</h1>
                </div>
                <div class="content">
                    <p style="font-size: 16px;">Hi <strong>{user_name}</strong>,</p>
                    <p>Your email has been verified! Welcome to the AcadWell community.</p>
                    <p>You can now log in and start using all features of the platform.</p>
                    <p style="text-align: center;">
                        <a href="{FRONTEND_URL}/login" class="button">Go to Dashboard</a>
                    </p>
                    <p>Thank you for joining us on this journey toward better academic wellness!</p>
                </div>
                <div class="footer">
                    <p><strong>AcadWell Team</strong></p>
                    <p>© {datetime.utcnow().year} AcadWell. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_text = f"""
        Hi {user_name},
        
        Your email has been verified! Welcome to the AcadWell community.
        
        You can now log in and start using all features.
        
        Login here: {FRONTEND_URL}/login
        
        ---
        AcadWell Team
        """
        
        return send_email(
            to_email=to_email,
            subject=f"Welcome to AcadWell, {user_name}!",
            html_content=html_content,
            plain_text_content=plain_text
        )
        
    except Exception as e:
        print(f"❌ Error sending confirmation email: {e}")
        return False


def send_wellness_alert_email(to_email, student_name, level, preview_text, post_or_message_link=None):
    """Send critical wellness alert email to counselors/teachers"""
    try:
        level_text = 'CRITICAL' if level == 'red' else 'HIGH CONCERN'
        level_color = '#dc2626' if level == 'red' else '#ea580c'
        timestamp = datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f3f4f6; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background: {level_color}; color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .alert-box {{ background: #fee2e2; border-left: 4px solid {level_color}; padding: 15px; margin: 20px 0; border-radius: 5px; }}
                .button {{ display: inline-block; background: {level_color}; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; background: #f9fafb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div style="font-size: 48px;">🚨</div>
                    <h1>{level_text}</h1>
                    <p style="margin: 10px 0 0 0;">Student Wellness Alert</p>
                </div>
                <div class="content">
                    <h2>Immediate Attention Required</h2>
                    <div class="alert-box">
                        <strong>Student:</strong> {student_name}<br>
                        <strong>Alert Level:</strong> {level.upper()}<br>
                        <strong>Time:</strong> {timestamp}<br><br>
                        <strong>Preview:</strong><br>
                        <em>{preview_text[:200]}...</em>
                    </div>
                    <p>This student has shown concerning patterns in their recent activity. 
                       Please reach out to provide support as soon as possible.</p>
                    <a href="{FRONTEND_URL}/teacher/dashboard" class="button">
                        View Student Details
                    </a>
                </div>
                <div class="footer">
                    <p><strong>AcadWell Wellness Monitoring System</strong></p>
                    <p>© {datetime.utcnow().year} AcadWell. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_text = f"""
        {level_text}: Student Wellness Alert
        
        Student: {student_name}
        Level: {level.upper()}
        Time: {timestamp}
        
        Preview: {preview_text[:200]}...
        
        Please check the wellness dashboard immediately for more details.
        
        ---
        AcadWell Wellness Monitoring System
        """
        
        subject = f"🚨 {level_text}: Wellness Alert for {student_name}"
        
        return send_email(to_email, subject, html_content, plain_text)
        
    except Exception as e:
        print(f"❌ Error sending wellness alert email: {e}")
        return False


def send_answer_accepted_email(to_email, answerer_name, question_title, post_link, points_earned=10):
    """Send notification email when answer is accepted"""
    try:
        timestamp = datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f3f4f6; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #16a34a 0%, #15803d 100%); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .points {{ background: #dcfce7; border: 2px solid #16a34a; padding: 20px; margin: 20px 0; border-radius: 10px; text-align: center; }}
                .points h2 {{ color: #16a34a; margin: 0; font-size: 32px; }}
                .button {{ display: inline-block; background: #16a34a; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; background: #f9fafb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div style="font-size: 48px;">🎉</div>
                    <h1>Your Answer Was Accepted!</h1>
                </div>
                <div class="content">
                    <p>Hi <strong>{answerer_name}</strong>,</p>
                    <p>Great news! Your answer on the question:</p>
                    <p style="font-style: italic; color: #555; background: #f9fafb; padding: 15px; border-radius: 6px;">"{question_title}"</p>
                    <p>has been accepted as the best answer!</p>
                    
                    <div class="points">
                        <h2>+{points_earned} Points! ⭐</h2>
                        <p style="margin: 10px 0 0 0;">Keep up the excellent work!</p>
                    </div>
                    
                    <p>Your contribution is helping fellow students succeed. Thank you for being an active member of the AcadWell community!</p>
                    
                    <div style="text-align: center;">
                        <a href="{post_link if post_link else FRONTEND_URL}" class="button">
                            View Your Answer
                        </a>
                    </div>
                </div>
                <div class="footer">
                    <p><strong>AcadWell Community</strong></p>
                    <p>© {datetime.utcnow().year} AcadWell. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_text = f"""
        Your Answer Was Accepted!
        
        Hi {answerer_name},
        
        Great news! Your answer on "{question_title}" was accepted as the best answer!
        
        You earned {points_earned} points!
        
        View your answer: {post_link if post_link else FRONTEND_URL}
        
        Keep up the great work helping fellow students!
        
        ---
        AcadWell Community
        """
        
        subject = f"🎉 Your Answer Was Accepted! (+{points_earned} points)"
        
        return send_email(to_email, subject, html_content, plain_text)
        
    except Exception as e:
        print(f"❌ Error sending answer accepted email: {e}")
        return False


def send_welcome_email(to_email, user_name, user_role):
    """Send welcome email to new users"""
    try:
        role_info = {
            'student': ('📚', ['Track your mood and wellbeing', 'Ask questions and get help', 'Access mental health resources']),
            'teacher': ('👨‍🏫', ['Monitor student wellness', 'Respond to questions', 'Identify students needing support']),
            'others': ('👤', ['Track your wellbeing', 'Participate in discussions', 'Access resources'])
        }
        
        icon, features = role_info.get(user_role, role_info['others'])
        features_html = ''.join([f'<li>{f}</li>' for f in features])
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 8px; margin-bottom: 30px; }}
                .features {{ background: #f9fafb; padding: 20px; margin: 20px 0; border-radius: 8px; border-left: 4px solid #667eea; }}
                .features ul {{ margin: 10px 0; padding-left: 20px; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; margin: 20px 0; }}
                .footer {{ text-align: center; color: #6b7280; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div style="font-size: 48px;">🎓</div>
                    <h1>Welcome to AcadWell!</h1>
                </div>
                <div class="content">
                    <h2>Hi {user_name}! 👋</h2>
                    <p>Welcome to <strong>AcadWell</strong> - your comprehensive platform for academic success and wellbeing!</p>
                    
                    <div class="features">
                        <h3>{icon} As a {user_role}, you can:</h3>
                        <ul>{features_html}</ul>
                    </div>
                    
                    <p>We're excited to have you as part of our community!</p>
                    
                    <div style="text-align: center;">
                        <a href="{FRONTEND_URL}/login" class="button">Get Started</a>
                    </div>
                </div>
                <div class="footer">
                    <p>© {datetime.utcnow().year} AcadWell. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return send_email(to_email, f"Welcome to AcadWell, {user_name}! 🎓", html_content)
        
    except Exception as e:
        print(f"❌ Error sending welcome email: {e}")
        return False


def send_daily_wellness_summary_email(to_email, teacher_name, summary_data):
    """Send daily wellness summary to teachers/counselors"""
    try:
        critical = summary_data.get('critical_students', 0)
        concerning = summary_data.get('concerning_students', 0)
        total = summary_data.get('total_students', 0)
        date_str = datetime.utcnow().strftime('%B %d, %Y')
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; }}
                .header {{ background: #3b82f6; color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .stat-box {{ padding: 15px; margin: 15px 0; border-radius: 5px; border-left: 4px solid; }}
                .critical {{ background: #fee2e2; border-color: #dc2626; }}
                .concerning {{ background: #fed7aa; border-color: #ea580c; }}
                .total {{ background: #dbeafe; border-color: #3b82f6; }}
                .button {{ display: inline-block; background: #3b82f6; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; background: #f9fafb; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Daily Wellness Summary</h1>
                    <p>{date_str}</p>
                </div>
                <div class="content">
                    <p>Hi <strong>{teacher_name}</strong>,</p>
                    <div class="stat-box critical">
                        <strong style="color: #dc2626;">🚨 Critical: {critical} student{'s' if critical != 1 else ''}</strong>
                        <p style="margin: 5px 0 0 0; font-size: 14px;">Require immediate attention</p>
                    </div>
                    <div class="stat-box concerning">
                        <strong style="color: #ea580c;">⚠️ Concerning: {concerning} student{'s' if concerning != 1 else ''}</strong>
                        <p style="margin: 5px 0 0 0; font-size: 14px;">Contact within 24 hours</p>
                    </div>
                    <div class="stat-box total">
                        <strong style="color: #3b82f6;">👥 Total Monitored: {total}</strong>
                    </div>
                    <div style="text-align: center; margin-top: 30px;">
                        <a href="{FRONTEND_URL}/teacher/wellness" class="button">View Dashboard</a>
                    </div>
                </div>
                <div class="footer">
                    <p>AcadWell Wellness Monitoring</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return send_email(to_email, f"📊 Daily Wellness Summary - {date_str}", html_content)
        
    except Exception as e:
        print(f"❌ Error sending wellness summary: {e}")
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
        print(f"📝 Email log saved to database")
    except Exception as e:
        print(f"❌ Error logging email: {e}")


def check_email_sent_recently(db, recipient_email, email_type, hours=24):
    """Check if similar email was sent recently to avoid spam"""
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
    'send_verification_email',
    'send_registration_confirmation_email',
    'send_wellness_alert_email',
    'send_answer_accepted_email',
    'send_welcome_email',
    'send_daily_wellness_summary_email',
    'log_email_sent',
    'check_email_sent_recently'
]