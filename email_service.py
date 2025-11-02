# Email Service untuk OTP Authentication
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
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
                # If no application context, just print to console
                print(f"Email Configuration issues: {'; '.join(config_errors)}")
    
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
    
    def send_otp_to_admin(self, registration_request):
        """
        Mengirim OTP ke semua admin untuk approval registrasi user baru
        """
        # Get all active admin users
        admins = User.query.filter_by(role='admin', is_active=True).all()
        
        if not admins:
            return False, "Tidak ada admin aktif yang ditemukan"
        
        success_count = 0
        errors = []
        
        for admin in admins:
            try:
                # Create notification record
                notification = AdminNotification(
                    registration_request_id=registration_request.id,
                    title=f"Permintaan Registrasi Baru - {registration_request.username}",
                    message=f"User baru {registration_request.username} ({registration_request.email}) meminta akses ke sistem. Gunakan OTP: {registration_request.otp_code}",
                    notification_type='registration_request'
                )
                db.session.add(notification)
                
                # Prepare email content
                subject = f"[{self.app_name}] Permintaan Registrasi Baru - OTP Required"
                
                html_content = self.get_otp_email_template(
                    admin_name=admin.full_name or admin.username,
                    requester_username=registration_request.username,
                    requester_email=registration_request.email,
                    requester_fullname=registration_request.full_name,
                    otp_code=registration_request.otp_code,
                    expires_at=registration_request.otp_expires_at,
                    approval_url=f"{os.getenv('BASE_URL', 'http://localhost:5000')}/otp/admin/approve-registration/{registration_request.id}"
                )
                
                # Send email
                success, error = self.send_email(admin.email, subject, html_content)
                
                # Log email attempt
                email_log = OTPEmailLog(
                    registration_request_id=registration_request.id,
                    recipient_email=admin.email,
                    subject=subject,
                    email_type='otp_notification',
                    is_sent=success,
                    sent_at=datetime.utcnow() if success else None,
                    error_message=error if not success else None
                )
                db.session.add(email_log)
                
                if success:
                    notification.is_sent = True
                    notification.email_sent_at = datetime.utcnow()
                    success_count += 1
                else:
                    errors.append(f"Admin {admin.email}: {error}")
                
            except Exception as e:
                errors.append(f"Admin {admin.email}: {str(e)}")
        
        db.session.commit()
        
        if success_count > 0:
            return True, f"OTP berhasil dikirim ke {success_count} admin"
        else:
            return False, f"Gagal mengirim OTP: {'; '.join(errors)}"
    
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
    
    def get_otp_email_template(self, admin_name, requester_username, requester_email, 
                              requester_fullname, otp_code, expires_at, approval_url):
        """
        Template email OTP untuk admin
        """
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Permintaan Registrasi Baru</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .otp-code {{ font-size: 24px; font-weight: bold; color: #dc3545; text-align: center; 
                           padding: 15px; background: #fff; border: 2px dashed #dc3545; margin: 20px 0; }}
                .user-info {{ background: white; padding: 15px; margin: 15px 0; border-left: 4px solid #007bff; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #28a745; color: white; 
                          text-decoration: none; border-radius: 5px; margin: 10px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{self.app_name} - Permintaan Registrasi</h1>
                </div>
                
                <div class="content">
                    <h2>Halo {admin_name},</h2>
                    
                    <p>Ada permintaan registrasi baru yang memerlukan persetujuan Anda:</p>
                    
                    <div class="user-info">
                        <h3>Informasi Pendaftar:</h3>
                        <p><strong>Username:</strong> {requester_username}</p>
                        <p><strong>Email:</strong> {requester_email}</p>
                        <p><strong>Nama Lengkap:</strong> {requester_fullname or 'Tidak diisi'}</p>
                        <p><strong>Waktu Pendaftaran:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M WIB')}</p>
                    </div>
                    
                    <div class="otp-code">
                        OTP Code: {otp_code}
                    </div>
                    
                    <p><strong>Kode OTP berlaku hingga:</strong> {expires_at.strftime('%d/%m/%Y %H:%M WIB')}</p>
                    
                    <p>Untuk menyetujui atau menolak registrasi ini, silakan:</p>
                    <ol>
                        <li>Login ke panel admin</li>
                        <li>Masukkan kode OTP di atas</li>
                        <li>Tinjau informasi pendaftar</li>
                        <li>Setujui atau tolak permintaan</li>
                    </ol>
                    
                    <a href="{approval_url}" class="button">Buka Panel Admin</a>
                    
                    <p><em>Email ini dikirim secara otomatis. Jangan balas email ini.</em></p>
                </div>
                
                <div class="footer">
                    <p>&copy; 2024 {self.app_name}. Sistem Klasifikasi Konten Radikal.</p>
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
                    <p>&copy; 2024 {self.app_name}. Sistem Klasifikasi Konten Radikal.</p>
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