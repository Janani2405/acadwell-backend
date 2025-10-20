# backend/app/utils/email_service.py
"""
Email Service - FIXED with proper timeout handling
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

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
        # Create simple plain text from HTML
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
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s
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


# Export function
__all__ = ['send_email']