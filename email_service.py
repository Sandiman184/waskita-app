# Email Service untuk OTP Authentication
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import current_app, render_template_string
from models import db, User
from models_otp import RegistrationRequest, AdminNotification, OTPEmailLog

class EmailService:
    """
    Service untuk mengirim email OTP dan notifikasi admin
    """
    
    def __init__(self):
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
        Mengirim OTP ke user untuk verifikasi email
        """
        try:
            # Prepare email content
            subject = f"[{self.app_name}] Kode Verifikasi OTP"
            
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
                # Create notification for admin (tanpa OTP)
                admins = User.query.filter_by(role='admin', is_active=True).all()
                for admin in admins:
                    notification = AdminNotification(
                        registration_request_id=registration_request.id,
                        title=f"Permintaan Registrasi Baru - {registration_request.username}",
                        message=f"User baru {registration_request.username} ({registration_request.email}) meminta akses ke sistem. Menunggu approval.",
                        notification_type='registration_request'
                    )
                    db.session.add(notification)
                
                db.session.commit()
                return True, "OTP berhasil dikirim ke user"
            else:
                return False, f"Gagal mengirim OTP ke user: {error}"
            
        except Exception as e:
            return False, str(e)
    
    def send_approval_notification(self, registration_request, approved_by_admin):
        """
        Mengirim notifikasi ke user bahwa registrasi telah disetujui
        """
        try:
            subject = f"[{self.app_name}] Registrasi Anda Telah Disetujui"
            
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
        Mengirim notifikasi ke user bahwa registrasi telah ditolak
        """
        try:
            subject = f"[{self.app_name}] Registrasi Anda Ditolak"
            
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
        Mengirim OTP untuk login pertama kali
        """
        try:
            # Prepare email content
            subject = f"[{self.app_name}] Kode Verifikasi Login Pertama"
            
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
            db.session.commit()
            
            return success, error
            
        except Exception as e:
            return False, str(e)
    
    def get_first_login_otp_template(self, username, full_name, email, otp_code):
        """
        Template email OTP untuk login pertama
        """
        expires_time = (datetime.utcnow() + timedelta(minutes=2)).strftime('%d/%m/%Y %H:%M WIB')
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Verifikasi Login Pertama - {self.app_name}</title>
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
                    <h1>{self.app_name} - Verifikasi Login Pertama</h1>
                </div>
                
                <div class="content">
                    <h2>Halo {full_name or username},</h2>
                    
                    <p>Ini adalah login pertama Anda ke sistem {self.app_name}. Untuk keamanan akun, kami memerlukan verifikasi tambahan.</p>
                    
                    <div class="otp-code">
                        {otp_code}
                    </div>
                    
                    <div class="info-box">
                        <h3>Informasi Verifikasi:</h3>
                        <p><strong>Username:</strong> {username}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Kode berlaku hingga:</strong> {expires_time}</p>
                    </div>
                    
                    <p><strong>Catatan Penting:</strong></p>
                    <ul>
                        <li>Kode OTP ini digunakan untuk verifikasi login pertama Anda</li>
                        <li>Setelah verifikasi berhasil, Anda akan dapat mengakses semua fitur sistem</li>
                        <li>Verifikasi ini hanya diperlukan sekali pada login pertama</li>
                        <li>Jangan bagikan kode OTP ini kepada siapapun</li>
                    </ul>
                    
                    <p><em>Email ini dikirim secara otomatis. Jangan balas email ini.</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2025 {self.app_name}. Sistem Klasifikasi Konten Radikal.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_otp_email_template(self, username, full_name, email, otp_code, expires_at):
        """
        Template email OTP untuk user
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Verifikasi Email - {self.app_name}</title>
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
                    <h1>{self.app_name} - Verifikasi Email</h1>
                </div>
                
                <div class="content">
                    <h2>Halo {full_name or username},</h2>
                    
                    <p>Terima kasih telah mendaftar di {self.app_name}. Berikut adalah kode verifikasi OTP Anda:</p>
                    
                    <div class="otp-code">
                        {otp_code}
                    </div>
                    
                    <div class="info-box">
                        <h3>Informasi Akun:</h3>
                        <p><strong>Username:</strong> {username}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Kode berlaku hingga:</strong> {expires_at.strftime('%d/%m/%Y %H:%M WIB')}</p>
                    </div>
                    
                    <p><strong>Catatan Penting:</strong></p>
                    <ul>
                        <li>Kode OTP ini digunakan untuk verifikasi email Anda</li>
                        <li>Setelah verifikasi, Anda dapat login ke sistem</li>
                        <li>Pada login pertama, Anda akan menerima OTP tambahan untuk verifikasi keamanan</li>
                        <li>Jangan bagikan kode OTP ini kepada siapapun</li>
                    </ul>
                    
                    <p><em>Email ini dikirim secara otomatis. Jangan balas email ini.</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2025 {self.app_name}. Sistem Klasifikasi Konten Radikal.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_approval_email_template(self, username, full_name, approved_by, login_url):
        """
        Template email approval untuk user
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Registrasi Disetujui</title>
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
                    <h1>🎉 Registrasi Berhasil!</h1>
                </div>
                
                <div class="content">
                    <h2>Selamat {full_name or username}!</h2>
                    
                    <div class="success-box">
                        <h3>✅ Akun Anda telah disetujui</h3>
                        <p>Registrasi Anda di sistem {self.app_name} telah disetujui oleh administrator <strong>{approved_by}</strong>.</p>
                    </div>
                    
                    <p>Anda sekarang dapat mengakses sistem dengan kredensial berikut:</p>
                    <ul>
                        <li><strong>Username:</strong> {username}</li>
                        <li><strong>Password:</strong> Password yang Anda buat saat registrasi</li>
                    </ul>
                    
                    <a href="{login_url}" class="button">Login Sekarang</a>
                    
                    <h3>Fitur yang dapat Anda gunakan:</h3>
                    <ul>
                        <li>Upload dan analisis data konten media sosial</li>
                        <li>Klasifikasi otomatis menggunakan AI</li>
                        <li>Web scraping dari berbagai platform</li>
                        <li>Export hasil analisis</li>
                        <li>Dashboard statistik real-time</li>
                    </ul>
                    
                    <p>Jika Anda memiliki pertanyaan, silakan hubungi administrator.</p>
                    
                    <p><em>Selamat menggunakan {self.app_name}!</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2025 {self.app_name}. Sistem Klasifikasi Konten Radikal.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def get_rejection_email_template(self, username, full_name, email, rejected_by, admin_notes):
        """
        Template email rejection untuk user
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Registrasi Ditolak</title>
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
                    <h1>⚠️ Registrasi Ditolak</h1>
                </div>
                
                <div class="content">
                    <h2>Halo {full_name or username},</h2>
                    
                    <div class="warning-box">
                        <h3>❌ Maaf, registrasi Anda ditolak</h3>
                        <p>Permintaan registrasi Anda di sistem {self.app_name} telah ditinjau dan ditolak oleh administrator <strong>{rejected_by}</strong>.</p>
                    </div>
                    
                    <h3>Alasan Penolakan:</h3>
                    <div style="background: #fff; padding: 15px; border-left: 4px solid #dc3545; margin: 15px 0;">
                        {admin_notes if admin_notes else 'Tidak ada catatan khusus dari administrator.'}
                    </div>
                    
                    <h3>Informasi Akun:</h3>
                    <ul>
                        <li><strong>Username:</strong> {username}</li>
                        <li><strong>Email:</strong> {email}</li>
                    </ul>
                    
                    <h3>Langkah Selanjutnya:</h3>
                    <ol>
                        <li>Jika Anda merasa ini adalah kesalahan, silakan hubungi administrator untuk klarifikasi</li>
                        <li>Pastikan informasi registrasi Anda lengkap dan valid</li>
                        <li>Anda dapat mencoba mendaftar kembali dengan informasi yang lebih lengkap</li>
                    </ol>
                    
                    <p><em>Terima kasih atas minat Anda untuk bergabung dengan {self.app_name}.</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2025 {self.app_name}. Sistem Klasifikasi Konten Radikal.</p>
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