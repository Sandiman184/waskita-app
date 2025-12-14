# Email Service untuk OTP Authentication
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import current_app, render_template_string, render_template
from models.models import db, User
from models.models_otp import RegistrationRequest, AdminNotification, OTPEmailLog

class EmailService:
    """
    Service untuk mengirim email OTP dan notifikasi admin
    """
    
    def __init__(self):
        # Ensure environment variables are loaded
        from dotenv import load_dotenv
        load_dotenv()
        
        # Use environment variables for email configuration
        self.smtp_server = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('MAIL_PORT', '587'))
        self.smtp_username = os.getenv('MAIL_USERNAME')
        self.smtp_password = os.getenv('MAIL_PASSWORD')
        self.from_email = os.getenv('MAIL_DEFAULT_SENDER')
        self.app_name = os.getenv('APP_NAME', 'Waskita')
        
        # Validate configuration on initialization
        config_errors = self.validate_config()
        if config_errors:
            # Only log if we're within application context
            try:
                current_app.logger.warning(f"Email Configuration issues: {'; '.join(config_errors)}")
            except RuntimeError:
                # If no application context, just log silently
                pass
    
    def send_email(self, to_email, subject, html_content, text_content=None):
        """
        Mengirim email dengan SMTP
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Add text and HTML parts
            if text_content:
                text_part = MIMEText(text_content, 'plain', 'utf-8')
                msg.attach(text_part)
            
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    def send_otp_to_user(self, registration_request):
        """
        Send OTP to user for email verification
        """
        try:
            # Prepare email content
            subject = f"[{self.app_name}] OTP Verification Code"
            
            html_content = self.get_otp_email_template(
                username=registration_request.username,
                full_name=registration_request.full_name,
                email=registration_request.email,
                otp_code=registration_request.otp_code,
                expires_at=registration_request.otp_expires_at
            )
            
            # Send email to user
            success, error = self.send_email(registration_request.email, subject, html_content)
            
            # Log email attempt
            email_log = OTPEmailLog(
                registration_request_id=registration_request.id,
                recipient_email=registration_request.email,
                subject=subject,
                email_type='otp_verification',
                is_sent=success,
                sent_at=datetime.utcnow() if success else None,
                error_message=error if not success else None
            )
            db.session.add(email_log)
            db.session.commit()
            
            if success:
                # Create notification for admin (without OTP)
                admins = User.query.filter_by(role='admin', is_active=True).all()
                for admin in admins:
                    notification = AdminNotification(
                        registration_request_id=registration_request.id,
                        title=f"New Registration Request - {registration_request.username}",
                        message=f"New user {registration_request.username} ({registration_request.email}) requested access. Waiting for approval.",
                        notification_type='registration_request'
                    )
                    db.session.add(notification)
                
                db.session.commit()
                return True, "OTP successfully sent to user"
            else:
                return False, f"Failed to send OTP to user: {error}"
            
        except Exception as e:
            return False, str(e)
    
    def send_approval_notification(self, registration_request, approved_by_admin):
        """
        Send notification to user that registration has been approved
        """
        try:
            subject = f"[{self.app_name}] Your Registration Has Been Approved"
            
            html_content = self.get_approval_email_template(
                username=registration_request.username,
                full_name=registration_request.full_name,
                approved_by=approved_by_admin.full_name or approved_by_admin.username,
                login_url=f"{os.getenv('BASE_URL', 'http://localhost:5000')}/login"
            )
            
            success, error = self.send_email(registration_request.email, subject, html_content)
            
            # Log email attempt
            email_log = OTPEmailLog(
                registration_request_id=registration_request.id,
                recipient_email=registration_request.email,
                subject=subject,
                email_type='approval_notification',
                is_sent=success,
                sent_at=datetime.utcnow() if success else None,
                error_message=error if not success else None
            )
            db.session.add(email_log)
            db.session.commit()
            
            return success, error
            
        except Exception as e:
            return False, str(e)
    
    def send_rejection_notification(self, registration_request, rejected_by_admin):
        """
        Send notification to user that registration has been rejected
        """
        try:
            subject = f"[{self.app_name}] Your Registration Has Been Rejected"
            
            html_content = self.get_rejection_email_template(
                username=registration_request.username,
                full_name=registration_request.full_name,
                email=registration_request.email,
                rejected_by=rejected_by_admin.full_name or rejected_by_admin.username,
                admin_notes=registration_request.admin_notes
            )
            
            success, error = self.send_email(registration_request.email, subject, html_content)
            
            # Log email attempt
            email_log = OTPEmailLog(
                registration_request_id=registration_request.id,
                recipient_email=registration_request.email,
                subject=subject,
                email_type='rejection_notification',
                is_sent=success,
                sent_at=datetime.utcnow() if success else None,
                error_message=error if not success else None
            )
            db.session.add(email_log)
            db.session.commit()
            
            return success, error
            
        except Exception as e:
            return False, str(e)
    
    def send_first_login_otp(self, user, otp_code):
        """
        Send OTP for first time login
        """
        try:
            # Prepare email content
            subject = f"[{self.app_name}] First Login Verification Code"
            
            html_content = self.get_first_login_otp_template(
                username=user.username,
                full_name=user.full_name,
                email=user.email,
                otp_code=otp_code
            )
            
            # Send email to user
            success, error = self.send_email(user.email, subject, html_content)
            
            # Log email attempt
            email_log = OTPEmailLog(
                user_id=user.id,
                recipient_email=user.email,
                subject=subject,
                email_type='first_login_otp',
                is_sent=success,
                sent_at=datetime.utcnow() if success else None,
                error_message=error if not success else None
            )
            db.session.add(email_log)
            try:
                db.session.commit()
            except Exception as db_error:
                db.session.rollback()
                # Log database error but don't fail the email sending
                try:
                    current_app.logger.error(f"Database error logging OTP email: {db_error}")
                except RuntimeError:
                    pass
            
            return success, error
            
        except Exception as e:
            return False, str(e)
    
    def get_first_login_otp_template(self, username, full_name, email, otp_code):
        """
        Email template for first login OTP
        """
        expires_time = (datetime.utcnow() + timedelta(minutes=current_app.config['OTP_EXPIRY_MINUTES'])).strftime('%d/%m/%Y %H:%M UTC')
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>First Login Verification - {self.app_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .otp-code {{ font-size: 24px; font-weight: bold; color: #dc3545; text-align: center; 
                           padding: 15px; background: #fff; border: 2px dashed #dc3545; margin: 20px 0; }}
                .info-box {{ background: white; padding: 15px; margin: 15px 0; border-left: 4px solid #28a745; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{self.app_name} - First Login Verification</h1>
                </div>
                
                <div class="content">
                    <h2>Hello {full_name or username},</h2>
                    
                    <p>This is your first login to the {self.app_name} system. For account security, we require additional verification.</p>
                    
                    <div class="otp-code">
                        {otp_code}
                    </div>
                    
                    <div class="info-box">
                        <h3>Verification Information:</h3>
                        <p><strong>Username:</strong> {username}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Code expires at:</strong> {expires_time}</p>
                    </div>
                    
                    <p><strong>Important Notes:</strong></p>
                    <ul>
                        <li>This OTP code is used for your first login verification</li>
                        <li>After successful verification, you will be able to access all system features</li>
                        <li>This verification is only required once during the first login</li>
                        <li>Do not share this OTP code with anyone</li>
                    </ul>
                    
                    <p><em>This email is sent automatically. Do not reply to this email.</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2025 {self.app_name}. Radical Content Classification System.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_otp_email_template(self, username, full_name, email, otp_code, expires_at):
        """
        Email template for OTP
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Email Verification - {self.app_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .otp-code {{ font-size: 24px; font-weight: bold; color: #dc3545; text-align: center; 
                           padding: 15px; background: #fff; border: 2px dashed #dc3545; margin: 20px 0; }}
                .info-box {{ background: white; padding: 15px; margin: 15px 0; border-left: 4px solid #28a745; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{self.app_name} - Email Verification</h1>
                </div>
                
                <div class="content">
                    <h2>Hello {full_name or username},</h2>
                    
                    <p>Thank you for registering at {self.app_name}. Here is your OTP verification code:</p>
                    
                    <div class="otp-code">
                        {otp_code}
                    </div>
                    
                    <div class="info-box">
                        <h3>Account Information:</h3>
                        <p><strong>Username:</strong> {username}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Code expires at:</strong> {expires_at.strftime('%d/%m/%Y %H:%M UTC')}</p>
                    </div>
                    
                    <p><strong>Important Notes:</strong></p>
                    <ul>
                        <li>This OTP code is used to verify your email</li>
                        <li>After verification, you can login to the system</li>
                        <li>On first login, you will receive an additional OTP for security verification</li>
                        <li>Do not share this OTP code with anyone</li>
                    </ul>
                    
                    <p><em>This email is sent automatically. Do not reply to this email.</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2025 {self.app_name}. Radical Content Classification System.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_approval_email_template(self, username, full_name, approved_by, login_url):
        """
        Email template for approval
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Registration Approved</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #28a745; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .success-box {{ background: #d4edda; border: 1px solid #c3e6cb; color: #155724; 
                               padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #007bff; color: white; 
                          text-decoration: none; border-radius: 5px; margin: 10px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 Registration Successful!</h1>
                </div>
                
                <div class="content">
                    <h2>Congratulations {full_name or username}!</h2>
                    
                    <div class="success-box">
                        <h3>✅ Your account has been approved</h3>
                        <p>Your registration in the {self.app_name} system has been approved by administrator <strong>{approved_by}</strong>.</p>
                    </div>
                    
                    <p>You can now access the system with the following credentials:</p>
                    <ul>
                        <li><strong>Username:</strong> {username}</li>
                        <li><strong>Password:</strong> The password you created during registration</li>
                    </ul>
                    
                    <a href="{login_url}" class="button">Login Now</a>
                    
                    <h3>Features you can use:</h3>
                    <ul>
                        <li>Upload and analyze social media content data</li>
                        <li>Automatic classification using AI</li>
                        <li>Web scraping from various platforms</li>
                        <li>Export analysis results</li>
                        <li>Real-time statistics dashboard</li>
                    </ul>
                    
                    <p>If you have any questions, please contact the administrator.</p>
                    
                    <p><em>Welcome to {self.app_name}!</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2025 {self.app_name}. Radical Content Classification System.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_rejection_email_template(self, username, full_name, email, rejected_by, admin_notes):
        """
        Email template for rejection
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Registration Rejected</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .warning-box {{ background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; 
                               padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚠️ Registration Rejected</h1>
                </div>
                
                <div class="content">
                    <h2>Hello {full_name or username},</h2>
                    
                    <div class="warning-box">
                        <h3>❌ Sorry, your registration was rejected</h3>
                        <p>Your registration request in the {self.app_name} system has been reviewed and rejected by administrator <strong>{rejected_by}</strong>.</p>
                    </div>
                    
                    <h3>Reason for Rejection:</h3>
                    <div style="background: #fff; padding: 15px; border-left: 4px solid #dc3545; margin: 15px 0;">
                        {admin_notes if admin_notes else 'No specific notes from administrator.'}
                    </div>
                    
                    <h3>Account Information:</h3>
                    <ul>
                        <li><strong>Username:</strong> {username}</li>
                        <li><strong>Email:</strong> {email}</li>
                    </ul>
                    
                    <h3>Next Steps:</h3>
                    <ol>
                        <li>If you feel this is a mistake, please contact the administrator for clarification</li>
                        <li>Ensure your registration information is complete and valid</li>
                        <li>You can try registering again with more complete information</li>
                    </ol>
                    
                    <p><em>Thank you for your interest in joining {self.app_name}.</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2025 {self.app_name}. Radical Content Classification System.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def validate_config(self):
        """
        Validate email configuration
        """
        errors = []
        
        if not self.smtp_server:
            errors.append("MAIL_SERVER not configured")
        if not self.smtp_username:
            errors.append("MAIL_USERNAME not configured")
        if not self.smtp_password:
            errors.append("MAIL_PASSWORD not configured")
        if not self.from_email:
            errors.append("MAIL_DEFAULT_SENDER not configured")
            
        return errors

# Initialize email service
email_service = EmailService()