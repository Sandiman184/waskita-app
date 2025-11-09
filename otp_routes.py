# Routes untuk OTP Authentication System
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app, session
from flask_login import login_required, current_user, login_user
from werkzeug.security import generate_password_hash
from flask_wtf import FlaskForm
from datetime import datetime, timedelta
import secrets
import string
from models import db, User, UserActivity
from models_otp import RegistrationRequest, AdminNotification, OTPEmailLog
from email_service import email_service
from utils import admin_required, log_user_activity, generate_activity_log
from markupsafe import escape
from security_logger import log_registration_attempt, log_admin_action, log_rate_limit_exceeded, log_security_event

# Import limiter from app
from flask import current_app

# Create blueprint
otp_bp = Blueprint('otp', __name__)

def generate_otp(length=6):
    """Generate random OTP code"""
    return ''.join(secrets.choice(string.digits) for _ in range(length))

@otp_bp.route('/register-request', methods=['GET', 'POST'])
def register_request():
    """
    Form permintaan registrasi yang akan mengirim OTP ke admin
    Rate limited: 3 attempts per hour per IP
    """
    if request.method == 'GET':
        return render_template('auth/register_request.html')
    
    try:
        # Get form data with input sanitization
        username = escape(request.form.get('username', '').strip())
        email = escape(request.form.get('email', '').strip())
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = escape(request.form.get('full_name', '').strip())
        
        # Validation
        if not all([username, email, password, confirm_password]):
            flash('Semua field wajib diisi', 'error')
            return render_template('auth/register_request.html')
        
        if password != confirm_password:
            flash('Password dan konfirmasi password tidak cocok', 'error')
            return render_template('auth/register_request.html')
        
        if len(password) < 8:
            flash('Password minimal 8 karakter', 'error')
            return render_template('auth/register_request.html')
        
        # Enhanced password validation
        if not any(c.isupper() for c in password):
            flash('Password harus mengandung minimal 1 huruf besar', 'error')
            return render_template('auth/register_request.html')
        
        if not any(c.islower() for c in password):
            flash('Password harus mengandung minimal 1 huruf kecil', 'error')
            return render_template('auth/register_request.html')
        
        if not any(c.isdigit() for c in password):
            flash('Password harus mengandung minimal 1 angka', 'error')
            return render_template('auth/register_request.html')
        
        # Check if username or email already exists
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            flash('Username atau email sudah terdaftar', 'error')
            return render_template('auth/register_request.html')
        
        # Check if there's pending request
        pending_request = RegistrationRequest.query.filter(
            (RegistrationRequest.username == username) | 
            (RegistrationRequest.email == email)
        ).filter_by(status='pending').first()
        
        if pending_request:
            flash('Sudah ada permintaan registrasi yang sedang menunggu persetujuan untuk username atau email ini', 'warning')
            return render_template('auth/register_request.html')
        
        # Create registration request (OTP akan di-generate otomatis di model)
        registration_request = RegistrationRequest(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name if full_name else None
        )
        
        # Set status ke pending
        registration_request.status = 'pending'
        
        db.session.add(registration_request)
        db.session.commit()
        
        # Log registration attempt
        log_registration_attempt(username, email, request.remote_addr)
        
        flash('Permintaan registrasi berhasil!', 'success')
        return redirect(url_for('otp.registration_status', request_id=registration_request.id))
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in register_request: {str(e)}")
        flash('Terjadi kesalahan sistem. Silakan coba lagi.', 'error')
        return render_template('auth/register_request.html')

@otp_bp.route('/registration-status/<int:request_id>')
def registration_status(request_id):
    """
    Halaman status permintaan registrasi
    """
    registration_request = RegistrationRequest.query.get_or_404(request_id)
    
    # Get email logs for this request
    email_logs = OTPEmailLog.query.filter_by(
        registration_request_id=request_id
    ).order_by(OTPEmailLog.created_at.desc()).all()
    
    return render_template('auth/registration_status.html', 
                         request=registration_request, 
                         email_logs=email_logs,
                         timedelta=timedelta)

@otp_bp.route('/admin/pending-registrations', methods=['GET', 'POST'])
@login_required
@admin_required
def pending_registrations():
    """
    Halaman admin untuk melihat dan memproses permintaan registrasi yang pending
    """
    if request.method == 'POST':
        try:
            request_id = request.form.get('request_id')
            action = request.form.get('action')  # 'approve' or 'reject'
            admin_notes = request.form.get('admin_notes', '').strip()
            
            if not request_id or not action:
                flash('Data tidak valid', 'error')
                return redirect(url_for('otp.pending_registrations'))
            
            registration_request = RegistrationRequest.query.get_or_404(request_id)
            
            if registration_request.status != 'pending':
                flash('Permintaan registrasi ini sudah diproses', 'warning')
                return redirect(url_for('otp.pending_registrations'))
            
            if action == 'approve':
                # Check if username already exists
                existing_user = User.query.filter_by(username=registration_request.username).first()
                if existing_user:
                    flash('Username sudah digunakan. Registrasi tidak dapat disetujui.', 'error')
                    return redirect(url_for('otp.pending_registrations'))
                
                # Check if email already exists
                existing_email = User.query.filter_by(email=registration_request.email).first()
                if existing_email:
                    flash('Email sudah digunakan. Registrasi tidak dapat disetujui.', 'error')
                    return redirect(url_for('otp.pending_registrations'))
                
                # Create new user
                new_user = User(
                    username=registration_request.username,
                    email=registration_request.email,
                    full_name=registration_request.full_name,
                    password_hash=registration_request.password_hash,
                    role='user',
                    is_active=True,
                    first_login=True,
                    created_at=datetime.utcnow()
                )
                
                db.session.add(new_user)
                
                # Update registration request
                registration_request.status = 'approved'
                registration_request.approved_by = current_user.id
                registration_request.approved_at = datetime.utcnow()
                registration_request.admin_notes = admin_notes
                
                # Log admin activity
                log_user_activity(
                    user_id=current_user.id,
                    action='user_registration_approved',
                    description=f'Approved registration for user: {registration_request.username}'
                )
                
                db.session.commit()
                
                # Send approval notification to user
                email_service.send_approval_notification(registration_request, current_user)
                
                flash(f'Registrasi user {registration_request.username} berhasil disetujui!', 'success')
                
            elif action == 'reject':
                # Update registration request
                registration_request.status = 'rejected'
                registration_request.approved_by = current_user.id
                registration_request.approved_at = datetime.utcnow()
                registration_request.admin_notes = admin_notes
                
                # Log admin activity
                log_user_activity(
                    user_id=current_user.id,
                    action='user_registration_rejected',
                    description=f'Rejected registration for user: {registration_request.username}'
                )
                
                db.session.commit()
                
                # Send rejection notification to user
                email_service.send_rejection_notification(registration_request, current_user)
                
                flash(f'Registrasi user {registration_request.username} ditolak.', 'info')
            
            return redirect(url_for('otp.pending_registrations'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error in pending_registrations POST: {str(e)}")
            flash('Terjadi kesalahan sistem. Silakan coba lagi.', 'error')
            return redirect(url_for('otp.pending_registrations'))
    
    # GET request - show pending registrations
    pending_requests = RegistrationRequest.query.filter_by(
        status='pending'
    ).order_by(RegistrationRequest.created_at.desc()).all()
    
    # Get notifications for current admin
    notifications = AdminNotification.query.join(RegistrationRequest).filter(
        RegistrationRequest.status == 'pending'
    ).order_by(AdminNotification.created_at.desc()).all()
    
    return render_template('admin/pending_registrations.html', 
                         pending_requests=pending_requests,
                         notifications=notifications,
                         datetime=datetime)

@otp_bp.route('/admin/approve-registration/<int:request_id>', methods=['GET', 'POST'])
def approve_registration_public(request_id):
    """
    Halaman publik untuk approve/reject registrasi dengan OTP (tanpa login)
    """
    registration_request = RegistrationRequest.query.get_or_404(request_id)
    
    if registration_request.status != 'pending':
        flash('Permintaan registrasi ini sudah diproses', 'warning')
        return render_template('admin/approve_registration_public.html', 
                             request=registration_request, 
                             already_processed=True)
    
    if request.method == 'GET':
        return render_template('admin/approve_registration_public.html', 
                             request=registration_request)
    
    try:
        # Get form data
        action = request.form.get('action')  # 'approve' or 'reject'
        admin_notes = request.form.get('admin_notes', '').strip()
        
        # Get the first active admin
        admin_user = User.query.filter_by(role='admin', is_active=True).first()
        if not admin_user:
            flash('Tidak ada admin aktif yang ditemukan', 'error')
            return render_template('admin/approve_registration_public.html', 
                                 request=registration_request)
        
        if action == 'approve':
            # Check if username already exists
            existing_user = User.query.filter_by(username=registration_request.username).first()
            if existing_user:
                flash('Username sudah digunakan. Registrasi tidak dapat disetujui.', 'error')
                return render_template('admin/approve_registration_public.html', 
                                     request=registration_request)
            
            # Check if email already exists
            existing_email = User.query.filter_by(email=registration_request.email).first()
            if existing_email:
                flash('Email sudah digunakan. Registrasi tidak dapat disetujui.', 'error')
                return render_template('admin/approve_registration_public.html', 
                                     request=registration_request)
            
            # Create new user
            new_user = User(
                username=registration_request.username,
                email=registration_request.email,
                full_name=registration_request.full_name,
                password_hash=registration_request.password_hash,
                role='user',
                is_active=True,
                first_login=True,
                created_at=datetime.utcnow()
            )
            
            db.session.add(new_user)
            
            # Update registration request
            registration_request.status = 'approved'
            registration_request.approved_by = admin_user.id
            registration_request.approved_at = datetime.utcnow()
            registration_request.admin_notes = admin_notes
            
            # Log admin activity
            log_user_activity(
                user_id=admin_user.id,
                action='user_registration_approved',
                description=f'Approved registration for user: {registration_request.username} via public link'
            )
            
            db.session.commit()
            
            # Send approval notification to user
            email_service.send_approval_notification(registration_request, admin_user)
            
            flash(f'Registrasi user {registration_request.username} berhasil disetujui!', 'success')
            
        elif action == 'reject':
            # Update registration request
            registration_request.status = 'rejected'
            registration_request.approved_by = admin_user.id
            registration_request.approved_at = datetime.utcnow()
            registration_request.admin_notes = admin_notes
            
            # Log admin activity
            log_user_activity(
                user_id=admin_user.id,
                action='user_registration_rejected',
                description=f'Rejected registration for user: {registration_request.username} via public link'
            )
            
            db.session.commit()
            
            # Send rejection notification to user
            email_service.send_rejection_notification(registration_request, admin_user)
            
            flash(f'Registrasi user {registration_request.username} ditolak.', 'info')
        
        return render_template('admin/approve_registration_public.html', 
                             request=registration_request, 
                             processed=True)
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in approve_registration_public: {str(e)}")
        flash('Terjadi kesalahan sistem. Silakan coba lagi.', 'error')
        return render_template('admin/approve_registration_public.html', 
                             request=registration_request)



@otp_bp.route('/admin/registration-history')
@login_required
@admin_required
def registration_history():
    """
    Halaman history semua permintaan registrasi
    """
    from utils import format_datetime
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    requests = RegistrationRequest.query.order_by(
        RegistrationRequest.created_at.desc()
    ).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/registration_history.html', 
                         requests=requests, 
                         format_datetime=format_datetime)

@otp_bp.route('/verify-first-login-otp', methods=['GET', 'POST'])
def verify_first_login_otp():
    """
    Endpoint untuk verifikasi OTP pada login pertama
    """
    if 'first_login_user_id' not in session or 'first_login_otp' not in session:
        flash('Sesi OTP tidak valid atau telah kedaluwarsa. Silakan login ulang.', 'error')
        return redirect(url_for('login'))
    
    # Check OTP expiry
    otp_expires_str = session.get('first_login_otp_expires')
    if not otp_expires_str:
        flash('Sesi OTP tidak valid. Silakan login ulang.', 'error')
        return redirect(url_for('login'))
    
    try:
        otp_expires = datetime.fromisoformat(otp_expires_str)
        if datetime.utcnow() > otp_expires:
            flash('Kode OTP telah kedaluwarsa. Silakan login ulang untuk mendapatkan kode baru.', 'error')
            # Clear session
            session.pop('first_login_user_id', None)
            session.pop('first_login_otp', None)
            session.pop('first_login_otp_expires', None)
            session.pop('first_login_remember', None)
            session.pop('first_login_next', None)
            return redirect(url_for('login'))
    except (ValueError, TypeError):
        flash('Sesi OTP tidak valid. Silakan login ulang.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        otp_code = request.form.get('otp', '').strip()
        
        if not otp_code:
            flash('Kode OTP tidak boleh kosong!', 'error')
            return render_template('auth/verify_first_login_otp.html', form=FlaskForm())
        
        if otp_code != session.get('first_login_otp'):
            flash('Kode OTP tidak valid!', 'error')
            return render_template('auth/verify_first_login_otp.html', form=FlaskForm())
        
        # OTP valid - complete first login
        user_id = session.get('first_login_user_id')
        remember = session.get('first_login_remember', False)
        next_page = session.get('first_login_next')
        
        user = User.query.get(user_id)
        if not user:
            flash('User tidak ditemukan!', 'error')
            return redirect(url_for('login'))
        
        # Mark first login as completed (set to False since first login is done)
        user.first_login = False
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        login_user(user, remember=remember)
        
        # Log successful first login with OTP
        log_security_event(
            "FIRST_LOGIN_OTP_SUCCESS", 
            f"First login OTP verification successful for user: {user.username}",
            user_id=user.id,
            ip_address=request.remote_addr
        )
        
        # Log activity
        generate_activity_log(
            action='first_login',
            description=f'Login pertama berhasil dengan verifikasi OTP untuk pengguna: {user.username}',
            user_id=user.id,
            icon='fas fa-shield-check',
            color='success'
        )
        
        # Clear session
        session.pop('first_login_user_id', None)
        session.pop('first_login_otp', None)
        session.pop('first_login_otp_expires', None)
        session.pop('first_login_remember', None)
        session.pop('first_login_next', None)
        
        flash('Login berhasil!', 'success')
        return redirect(next_page) if next_page else redirect(url_for('dashboard'))
    
    return render_template('auth/verify_first_login_otp.html', form=FlaskForm())

@otp_bp.route('/resend-first-login-otp', methods=['POST'])
def resend_first_login_otp():
    """
    Resend OTP untuk login pertama
    """
    try:
        # Check if user is in first login session
        user_id = session.get('first_login_user_id')
        if not user_id:
            return jsonify({
                'success': False, 
                'message': 'Sesi login pertama tidak ditemukan. Silakan login ulang.'
            }), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False, 
                'message': 'User tidak ditemukan'
            }), 404
        
        # Generate new OTP
        from otp_routes import generate_otp
        otp_code = generate_otp()
        
        # Update session with new OTP and expiry
        session['first_login_otp'] = otp_code
        session['first_login_otp_expires'] = (datetime.utcnow() + timedelta(minutes=2)).isoformat()
        
        # Send new OTP email
        from email_service import email_service
        success, message = email_service.send_first_login_otp(user, otp_code)
        
        if success:
            # Log OTP resend
            log_security_event(
                "FIRST_LOGIN_OTP_RESENT", 
                f"First login OTP resent for user: {user.username}",
                user_id=user.id,
                ip_address=request.remote_addr
            )
            
            return jsonify({
                'success': True, 
                'message': 'OTP berhasil dikirim ulang. Silakan cek email Anda.'
            })
        else:
            return jsonify({
                'success': False, 
                'message': f'Gagal mengirim OTP: {message}'
            }), 500
            
    except Exception as e:
        current_app.logger.error(f"Error in resend_first_login_otp: {str(e)}")
        return jsonify({
            'success': False, 
            'message': 'Terjadi kesalahan sistem'
        }), 500

@otp_bp.route('/api/registration-stats')
@login_required
@admin_required
def registration_stats():
    """
    API endpoint untuk statistik registrasi (untuk dashboard admin)
    """
    try:
        stats = {
            'pending': RegistrationRequest.query.filter_by(status='pending').count(),
            'approved': RegistrationRequest.query.filter_by(status='approved').count(),
            'rejected': RegistrationRequest.query.filter_by(status='rejected').count(),
            'expired': RegistrationRequest.query.filter_by(status='expired').count(),
            'total': RegistrationRequest.query.count()
        }
        
        # Recent requests (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_requests = RegistrationRequest.query.filter(
            RegistrationRequest.created_at >= seven_days_ago
        ).count()
        
        stats['recent'] = recent_requests
        
        return jsonify(stats)
        
    except Exception as e:
        current_app.logger.error(f"Error in registration_stats: {str(e)}")
        return jsonify({'error': 'Failed to fetch stats'}), 500

@otp_bp.route('/admin/resend-otp/<int:request_id>', methods=['POST'])
@login_required
@admin_required
def resend_otp(request_id):
    """
    Resend OTP untuk permintaan registrasi tertentu
    """
    try:
        registration_request = RegistrationRequest.query.get_or_404(request_id)
        
        if registration_request.status != 'pending':
            return jsonify({'success': False, 'message': 'Permintaan sudah diproses'}), 400
        
        # Generate new OTP
        new_otp = generate_otp()
        new_expires_at = datetime.utcnow() + timedelta(hours=24)
        
        registration_request.otp_code = new_otp
        registration_request.otp_expires_at = new_expires_at
        
        db.session.commit()
        
        # Send new OTP to user (bukan ke admin)
        success, message = email_service.send_otp_to_user(registration_request)
        
        if success:
            return jsonify({'success': True, 'message': 'OTP baru berhasil dikirim ke user'})
        else:
            return jsonify({'success': False, 'message': f'Gagal mengirim OTP: {message}'}), 500
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in resend_otp: {str(e)}")
        return jsonify({'success': False, 'message': 'Terjadi kesalahan sistem'}), 500

@otp_bp.route('/admin/delete-registration-request/<int:request_id>', methods=['POST'])
@login_required
@admin_required
def delete_registration_request(request_id):
    """
    Hapus permintaan registrasi
    """
    try:
        registration_request = RegistrationRequest.query.get_or_404(request_id)
        username = registration_request.username  # Store username before deletion
        
        # First, delete all related AdminNotifications
        AdminNotification.query.filter_by(registration_request_id=request_id).delete()
        
        # Delete all related OTPEmailLogs
        OTPEmailLog.query.filter_by(registration_request_id=request_id).delete()
        
        # Log admin activity
        log_user_activity(
            user_id=current_user.id,
            action='registration_request_deleted',
            description=f'Deleted registration request for user: {username}'
        )
        
        # Finally, delete the registration request
        db.session.delete(registration_request)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Permintaan registrasi untuk {username} berhasil dihapus'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting registration request: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Terjadi kesalahan sistem'
        }), 500

@otp_bp.route('/admin/delete-all-registration-history', methods=['POST'])
@login_required
@admin_required
def delete_all_registration_history():
    """
    Hapus semua riwayat registrasi yang sudah diproses (approved/rejected/expired)
    """
    try:
        # Hanya hapus data yang sudah diproses, bukan yang masih pending
        processed_requests = RegistrationRequest.query.filter(
            RegistrationRequest.status.in_(['approved', 'rejected', 'expired'])
        ).all()
        
        if not processed_requests:
            return jsonify({
                'success': True,
                'message': 'Tidak ada riwayat registrasi yang perlu dihapus',
                'deleted_count': 0
            })
        
        deleted_count = 0
        
        for request in processed_requests:
            # Delete related AdminNotifications
            AdminNotification.query.filter_by(registration_request_id=request.id).delete()
            
            # Delete related OTPEmailLogs
            OTPEmailLog.query.filter_by(registration_request_id=request.id).delete()
            
            # Delete the registration request
            db.session.delete(request)
            deleted_count += 1
        
        # Log admin activity
        log_user_activity(
            user_id=current_user.id,
            action='all_registration_history_deleted',
            description=f'Deleted all registration history ({deleted_count} records)'
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Berhasil menghapus {deleted_count} riwayat registrasi',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting all registration history: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Terjadi kesalahan sistem saat menghapus semua riwayat'
        }), 500

@otp_bp.route('/admin/delete-registration-history/<int:request_id>', methods=['POST'])
@login_required
@admin_required
def delete_registration_history(request_id):
    """
    Hapus riwayat registrasi (untuk data yang sudah diproses)
    """
    try:
        registration_request = RegistrationRequest.query.get_or_404(request_id)
        username = registration_request.username  # Store username before deletion
        
        # Pastikan hanya bisa hapus yang sudah diproses (approved/rejected)
        if registration_request.status == 'pending':
            return jsonify({
                'success': False,
                'message': 'Tidak dapat menghapus permintaan yang masih pending. Gunakan halaman Pending Registrations.'
            }), 400
        
        # First, delete all related AdminNotifications
        AdminNotification.query.filter_by(registration_request_id=request_id).delete()
        
        # Delete all related OTPEmailLogs
        OTPEmailLog.query.filter_by(registration_request_id=request_id).delete()
        
        # Log admin activity
        log_user_activity(
            user_id=current_user.id,
            action='registration_history_deleted',
            description=f'Deleted registration history for user: {username} (status: {registration_request.status})'
        )
        
        # Finally, delete the registration request
        db.session.delete(registration_request)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Riwayat registrasi untuk {username} berhasil dihapus'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting registration history: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Terjadi kesalahan sistem'
        }), 500